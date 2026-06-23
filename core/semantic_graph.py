from __future__ import annotations

import json
from collections import Counter, defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .text_utils import normalize_text


GRAPH_NAME = "G_attr"
GRAPH_FULL_NAME = "semantic_attribute_graph"

ATTRIBUTE_SPECS = [
    ("product_type", "TYPE", "HAS_TYPE"),
    ("subtype", "SUBTYPE", "HAS_SUBTYPE"),
    ("accessory", "ACCESSORY", "HAS_ACCESSORY"),
    ("shape", "SHAPE", "HAS_SHAPE"),
    ("feature", "FEATURE", "HAS_FEATURE"),
    ("material", "MATERIAL", "HAS_MATERIAL"),
    ("color", "COLOR", "HAS_COLOR"),
    ("capacity_text", "CAPACITY", "HAS_CAPACITY"),
    ("mouth_size_text", "MOUTH_SIZE", "HAS_MOUTH_SIZE"),
]

# Clave dentro del JSON attribute_confidence (Etapa 1.5) para cada columna de atributo.
CONFIDENCE_KEYS = {
    "product_type": "product_type",
    "subtype": "subtype",
    "accessory": "accessory",
    "shape": "shape",
    "feature": "feature",
    "material": "material",
    "color": "color",
    "capacity_text": "capacity",
    "mouth_size_text": "mouth_size",
}


def stable_value(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def node_id(node_type: str, value: object) -> str:
    norm = normalize_text(value).replace(" ", "_")
    return f"{node_type}:{norm}"


def product_node_id(product_id: object) -> str:
    return f"PRODUCT:{stable_value(product_id)}"


def split_attribute_values(value: object) -> list[str]:
    text = stable_value(value)
    if not text:
        return []
    return [part.strip() for part in text.split("|") if part.strip()]


def prepare_attributes(attributes: pd.DataFrame) -> pd.DataFrame:
    prepared = attributes.copy()
    prepared["capacity_text"] = ""
    capacity_mask = prepared["capacity_value"].notna() & prepared["capacity_unit"].notna()
    prepared.loc[capacity_mask, "capacity_text"] = (
        prepared.loc[capacity_mask, "capacity_value"].map(lambda value: f"{float(value):g}")
        + prepared.loc[capacity_mask, "capacity_unit"].astype(str).str.upper()
    )

    prepared["mouth_size_text"] = ""
    mouth_mask = prepared["mouth_size_mm"].notna()
    prepared.loc[mouth_mask, "mouth_size_text"] = prepared.loc[mouth_mask, "mouth_size_mm"].map(
        lambda value: f"{float(value):g}MM"
    )
    return prepared


def parse_attribute_confidence(value: object) -> dict[str, float]:
    text = stable_value(value)
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): float(conf) for key, conf in payload.items() if isinstance(conf, (int, float))}


def build_semantic_attribute_graph(
    attributes: pd.DataFrame,
    activity: pd.DataFrame | None = None,
    min_confidence: float = 0.75,
) -> dict[str, Any]:
    """Construye G_attr (producto <-> atributo).

    El peso de cada arista es la confianza de extraccion **del atributo**
    (columna attribute_confidence de la Etapa 1.5) y el filtro min_confidence
    se aplica por atributo: un producto con un atributo debil no pierde sus
    atributos fuertes. Si el CSV de entrada no trae attribute_confidence
    (corridas antiguas), se usa la confianza promedio del producto como
    respaldo, replicando el comportamiento anterior.
    """
    data = prepare_attributes(attributes)
    if activity is not None and not activity.empty:
        activity_cols = ["product_id", "sales_rows", "purchases_rows", "sales_total", "purchases_total"]
        available = [column for column in activity_cols if column in activity.columns]
        data = data.merge(activity[available], on="product_id", how="left")

    for column in ["sales_rows", "purchases_rows", "sales_total", "purchases_total"]:
        if column not in data.columns:
            data[column] = 0
        data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0)

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    for _, row in data.iterrows():
        product_id = stable_value(row.get("product_id"))
        if not product_id:
            continue

        product_node = product_node_id(product_id)
        product_confidence = float(row.get("confidence", 0) or 0)
        nodes[product_node] = {
            "node_id": product_node,
            "node_type": "PRODUCT",
            "label": stable_value(row.get("product_name")),
            "product_id": product_id,
            "confidence": round(product_confidence, 4),
            "sales_rows": float(row.get("sales_rows", 0) or 0),
            "purchases_rows": float(row.get("purchases_rows", 0) or 0),
            "sales_total": float(row.get("sales_total", 0) or 0),
            "purchases_total": float(row.get("purchases_total", 0) or 0),
        }

        confidences = parse_attribute_confidence(row.get("attribute_confidence"))

        for column, attr_type, relation in ATTRIBUTE_SPECS:
            attr_confidence = confidences.get(CONFIDENCE_KEYS[column], product_confidence)
            if attr_confidence < min_confidence:
                continue
            for value in split_attribute_values(row.get(column)):
                attr_node = node_id(attr_type, value)
                nodes.setdefault(
                    attr_node,
                    {
                        "node_id": attr_node,
                        "node_type": attr_type,
                        "label": value,
                        "product_id": "",
                        "confidence": "",
                        "sales_rows": "",
                        "purchases_rows": "",
                        "sales_total": "",
                        "purchases_total": "",
                    },
                )
                edges.append(
                    {
                        "source": product_node,
                        "target": attr_node,
                        "relation": relation,
                        "weight": round(attr_confidence, 4),
                        "evidence": stable_value(row.get("product_name")),
                    }
                )

    nodes_df = pd.DataFrame(nodes.values())
    edges_df = pd.DataFrame(edges)
    metrics = build_graph_metrics(nodes_df, edges_df, min_confidence)
    adjacency_sample = build_adjacency_sample(nodes_df, edges_df)

    return {
        "nodes": nodes_df,
        "edges": edges_df,
        "metrics": metrics,
        "adjacency_sample": adjacency_sample,
    }


def build_graph_metrics(nodes: pd.DataFrame, edges: pd.DataFrame, min_confidence: float) -> dict[str, Any]:
    node_type_counts = (
        nodes["node_type"].value_counts().sort_index().to_dict() if not nodes.empty else {}
    )
    relation_counts = (
        edges["relation"].value_counts().sort_index().to_dict() if not edges.empty else {}
    )

    adjacency: dict[str, set[str]] = defaultdict(set)
    if not edges.empty:
        for _, edge in edges.iterrows():
            source = edge["source"]
            target = edge["target"]
            adjacency[source].add(target)
            adjacency[target].add(source)

    node_ids = set(nodes["node_id"].tolist()) if not nodes.empty else set()
    visited: set[str] = set()
    component_sizes: list[int] = []
    for start in node_ids:
        if start in visited:
            continue
        queue: deque[str] = deque([start])
        visited.add(start)
        size = 0
        while queue:
            current = queue.popleft()
            size += 1
            for neighbor in adjacency.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        component_sizes.append(size)

    product_nodes = nodes.loc[nodes["node_type"] == "PRODUCT", "node_id"].tolist() if not nodes.empty else []
    products_without_edges = [node for node in product_nodes if not adjacency.get(node)]
    degree_counter = Counter({node_id: len(neighbors) for node_id, neighbors in adjacency.items()})
    top_degree_nodes = [
        {"node_id": node, "degree": degree}
        for node, degree in degree_counter.most_common(20)
    ]

    return {
        "graph_name": GRAPH_NAME,
        "graph_full_name": GRAPH_FULL_NAME,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "min_confidence": min_confidence,
        "node_count": int(len(nodes)),
        "edge_count": int(len(edges)),
        "node_type_counts": {key: int(value) for key, value in node_type_counts.items()},
        "relation_counts": {key: int(value) for key, value in relation_counts.items()},
        "connected_components": int(len(component_sizes)),
        "largest_component_size": int(max(component_sizes) if component_sizes else 0),
        "products_total": int(len(product_nodes)),
        "products_with_attribute_edges": int(len(product_nodes) - len(products_without_edges)),
        "products_without_attribute_edges": int(len(products_without_edges)),
        "top_degree_nodes": top_degree_nodes,
    }


def build_adjacency_sample(nodes: pd.DataFrame, edges: pd.DataFrame, sample_size: int = 80) -> pd.DataFrame:
    if nodes.empty or edges.empty:
        return pd.DataFrame()

    node_labels = nodes.set_index("node_id")["label"].to_dict()
    product_edges = edges.loc[edges["source"].astype(str).str.startswith("PRODUCT:")].copy()
    product_edges["source_label"] = product_edges["source"].map(node_labels)
    product_edges["target_label"] = product_edges["target"].map(node_labels)
    return product_edges[
        ["source", "source_label", "relation", "target", "target_label", "weight"]
    ].head(sample_size)


def run_stage2_graph(
    stage15_output_dir: str | Path,
    stage1_output_dir: str | Path | None = None,
    min_confidence: float = 0.75,
) -> dict[str, Any]:
    stage15_path = Path(stage15_output_dir)
    attributes = pd.read_csv(stage15_path / "product_attributes.csv", encoding="utf-8-sig")

    activity = pd.DataFrame()
    if stage1_output_dir is not None:
        activity_path = Path(stage1_output_dir) / "product_activity_summary.csv"
        if activity_path.exists():
            activity = pd.read_csv(activity_path, encoding="utf-8-sig")

    return build_semantic_attribute_graph(attributes, activity, min_confidence=min_confidence)


def export_stage2_graph(result: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    paths: dict[str, str] = {}
    table_outputs = {
        "semantic_attribute_graph_nodes.csv": result["nodes"],
        "semantic_attribute_graph_edges.csv": result["edges"],
        "semantic_attribute_graph_adjacency_sample.csv": result["adjacency_sample"],
    }
    for filename, table in table_outputs.items():
        path = output_path / filename
        table.to_csv(path, index=False, encoding="utf-8-sig")
        paths[filename] = str(path)

    metrics_path = output_path / "semantic_attribute_graph_metrics.json"
    metrics_path.write_text(json.dumps(result["metrics"], indent=2, ensure_ascii=False), encoding="utf-8")
    paths["semantic_attribute_graph_metrics.json"] = str(metrics_path)
    return paths
