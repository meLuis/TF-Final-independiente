"""Grafos transaccionales: G_purchases, G_sales y G_business.

Construye, desde los datasets limpios de la Etapa 1 (esquema canonico), los
grafos heterogeneos que el plan de la Etapa 2 dejaba pendientes:

- G_purchases: PRODUCT, SUPPLIER, DOC, DATE — historial de compras.
- G_sales:     PRODUCT, CLIENT,   DOC, DATE — historial de ventas.
- G_business:  union de ambos sobre los nodos PRODUCT compartidos.

Pseudo-documento: el esquema canonico no incluye numero de factura, asi que un
documento se aproxima como (contraparte, fecha): todas las lineas compradas al
mismo proveedor (o vendidas al mismo cliente) el mismo dia se agrupan en un
nodo DOC. Es una aproximacion declarada — habilita co-compra/co-venta sin
exigir una columna que muchas empresas no exportan.

Solo se grafican filas activas (is_active == True): anulados y ajustes quedan
fuera del analisis pero auditables en los datasets limpios.

Aristas:
- DOC -CONTAINS->  PRODUCT  (weight = total de la linea; attrs cantidad/precio)
- DOC -ISSUED_BY-> SUPPLIER (compras) / DOC -SOLD_TO-> CLIENT (ventas)
- DOC -ON_DATE->   DATE     (dia)

Complejidad de construccion: O(R) con R filas activas; cada linea aporta a lo
sumo 3 aristas y los nodos se deduplican con diccionarios O(1).
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .semantic_graph import stable_value


SPEC_BY_KIND = {
    "purchases": {
        "counterpart_column": "supplier_norm",
        "counterpart_label_column": "supplier",
        "counterpart_type": "SUPPLIER",
        "counterpart_relation": "ISSUED_BY",
        "unit_value_column": "analysis_unit_cost",
        "graph_name": "G_purchases",
    },
    "sales": {
        "counterpart_column": "customer_norm",
        "counterpart_label_column": "customer",
        "counterpart_type": "CLIENT",
        "counterpart_relation": "SOLD_TO",
        "unit_value_column": "analysis_unit_price",
        "graph_name": "G_sales",
    },
}


def doc_node_id(kind: str, counterpart: str, date: str) -> str:
    prefix = "DOCP" if kind == "purchases" else "DOCS"
    return f"{prefix}:{counterpart}|{date}"


def build_transaction_graph(transactions: pd.DataFrame, kind: str) -> dict[str, Any]:
    """Construye G_purchases o G_sales desde un dataset limpio de Etapa 1."""
    if kind not in SPEC_BY_KIND:
        raise ValueError(f"kind debe ser uno de {sorted(SPEC_BY_KIND)}")
    spec = SPEC_BY_KIND[kind]

    data = transactions.copy()
    if "is_active" in data.columns:
        data = data.loc[data["is_active"].astype(str).str.lower().isin({"true", "1"})]

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    for _, row in data.iterrows():
        product_id = stable_value(row.get("product_id"))
        counterpart = stable_value(row.get(spec["counterpart_column"]))
        date = stable_value(row.get("date"))
        if not product_id or not counterpart or not date:
            continue

        product_node = f"PRODUCT:{product_id}"
        counterpart_node = f"{spec['counterpart_type']}:{counterpart}"
        date_node = f"DATE:{date}"
        doc_node = doc_node_id(kind, counterpart, date)

        nodes.setdefault(
            product_node,
            {"node_id": product_node, "node_type": "PRODUCT", "label": stable_value(row.get("product_name"))},
        )
        nodes.setdefault(
            counterpart_node,
            {
                "node_id": counterpart_node,
                "node_type": spec["counterpart_type"],
                "label": stable_value(row.get(spec["counterpart_label_column"])) or counterpart,
            },
        )
        nodes.setdefault(date_node, {"node_id": date_node, "node_type": "DATE", "label": date})
        is_new_doc = doc_node not in nodes
        nodes.setdefault(doc_node, {"node_id": doc_node, "node_type": "DOC", "label": f"{counterpart} {date}"})

        quantity = pd.to_numeric(row.get("quantity"), errors="coerce")
        unit_value = pd.to_numeric(row.get(spec["unit_value_column"]), errors="coerce")
        line_total = pd.to_numeric(row.get("analysis_total"), errors="coerce")
        edges.append(
            {
                "source": doc_node,
                "target": product_node,
                "relation": "CONTAINS",
                "weight": round(float(line_total), 4) if pd.notna(line_total) else 0.0,
                "quantity": float(quantity) if pd.notna(quantity) else 0.0,
                "unit_value": round(float(unit_value), 6) if pd.notna(unit_value) else 0.0,
                "date": date,
            }
        )
        if is_new_doc:
            edges.append(
                {
                    "source": doc_node,
                    "target": counterpart_node,
                    "relation": spec["counterpart_relation"],
                    "weight": 1.0,
                    "quantity": 0.0,
                    "unit_value": 0.0,
                    "date": date,
                }
            )
            edges.append(
                {
                    "source": doc_node,
                    "target": date_node,
                    "relation": "ON_DATE",
                    "weight": 1.0,
                    "quantity": 0.0,
                    "unit_value": 0.0,
                    "date": date,
                }
            )

    nodes_df = pd.DataFrame(nodes.values())
    edges_df = pd.DataFrame(edges)
    metrics = build_transaction_metrics(nodes_df, edges_df, spec["graph_name"])
    return {"nodes": nodes_df, "edges": edges_df, "metrics": metrics}


def build_business_graph(purchases_graph: dict[str, Any], sales_graph: dict[str, Any]) -> dict[str, Any]:
    """G_business: union de G_purchases y G_sales (PRODUCT y DATE compartidos)."""
    nodes = (
        pd.concat([purchases_graph["nodes"], sales_graph["nodes"]], ignore_index=True)
        .drop_duplicates(subset="node_id")
        .reset_index(drop=True)
    )
    edges = pd.concat([purchases_graph["edges"], sales_graph["edges"]], ignore_index=True)
    metrics = build_transaction_metrics(nodes, edges, "G_business")
    return {"nodes": nodes, "edges": edges, "metrics": metrics}


def build_transaction_metrics(nodes: pd.DataFrame, edges: pd.DataFrame, graph_name: str) -> dict[str, Any]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    if not edges.empty:
        for source, target in zip(edges["source"], edges["target"]):
            adjacency[source].add(target)
            adjacency[target].add(source)

    node_ids = set(nodes["node_id"]) if not nodes.empty else set()
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

    degree_top = sorted(
        ({"node_id": node, "degree": len(neighbors)} for node, neighbors in adjacency.items()),
        key=lambda item: item["degree"],
        reverse=True,
    )[:20]

    return {
        "graph_name": graph_name,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "node_count": int(len(nodes)),
        "edge_count": int(len(edges)),
        "node_type_counts": (
            {key: int(value) for key, value in nodes["node_type"].value_counts().sort_index().items()}
            if not nodes.empty
            else {}
        ),
        "relation_counts": (
            {key: int(value) for key, value in edges["relation"].value_counts().sort_index().items()}
            if not edges.empty
            else {}
        ),
        "connected_components": int(len(component_sizes)),
        "largest_component_size": int(max(component_sizes) if component_sizes else 0),
        "top_degree_nodes": degree_top,
    }


def run_transaction_graphs(stage1_output_dir: str | Path) -> dict[str, dict[str, Any]]:
    stage1_path = Path(stage1_output_dir)
    purchases = pd.read_csv(stage1_path / "purchases_clean.csv", encoding="utf-8-sig")
    sales = pd.read_csv(stage1_path / "sales_clean.csv", encoding="utf-8-sig")

    purchases_graph = build_transaction_graph(purchases, "purchases")
    sales_graph = build_transaction_graph(sales, "sales")
    business_graph = build_business_graph(purchases_graph, sales_graph)
    return {"purchases": purchases_graph, "sales": sales_graph, "business": business_graph}


def export_transaction_graphs(graphs: dict[str, dict[str, Any]], output_dir: str | Path) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}

    for kind, graph in graphs.items():
        for suffix, table in (("nodes", graph["nodes"]), ("edges", graph["edges"])):
            filename = f"transaction_graph_{kind}_{suffix}.csv"
            path = output_path / filename
            table.to_csv(path, index=False, encoding="utf-8-sig")
            paths[filename] = str(path)
        metrics_name = f"transaction_graph_{kind}_metrics.json"
        metrics_path = output_path / metrics_name
        metrics_path.write_text(
            json.dumps(graph["metrics"], indent=2, ensure_ascii=False), encoding="utf-8"
        )
        paths[metrics_name] = str(metrics_path)
    return paths
