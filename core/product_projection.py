"""Proyeccion producto-producto de G_attr.

G_attr es bipartito (PRODUCT <-> ATRIBUTO) y no puede responder directamente
"que productos se parecen a X". Esta proyeccion construye un grafo de similitud
entre productos usando Jaccard ponderado sobre los atributos compartidos, con
el peso de extraccion (confianza por atributo) de la Etapa 2.

Definicion:

    sim(p, q) = sum_{a en A(p) ∩ A(q)} min(w_pa, w_qa)
                ------------------------------------------
                sum_{a en A(p) ∪ A(q)} max(w_pa, w_qa)

Como para atributos compartidos max + min = w_pa + w_qa, el denominador se
reduce a W(p) + W(q) - num, donde W(x) es la suma de pesos de x y num el
numerador. Asi solo se acumula el numerador por atributo y nunca se itera la
union por par.

Atributos "hub" (conectados a una fraccion alta de productos, p.ej.
ACCESSORY:TAPA con grado 357 de 630) no discriminan similitud y se excluyen;
ademas acotan el costo: la generacion de pares es O(sum_a deg(a)^2) sobre los
atributos incluidos, por lo que excluir hubs elimina los terminos cuadraticos
dominantes.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd


def build_product_projection(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    hub_fraction: float = 0.35,
    min_similarity: float = 0.30,
    min_shared_attributes: int = 2,
    top_k: int = 10,
) -> dict[str, Any]:
    """Construye la proyeccion producto-producto.

    Args:
        nodes/edges: salida de build_semantic_attribute_graph.
        hub_fraction: un atributo conectado a mas de hub_fraction * n_productos
            se excluye de la similitud (no discrimina).
        min_similarity: umbral minimo de Jaccard ponderado para emitir arista.
        min_shared_attributes: minimo de atributos compartidos (evita pares
            unidos solo por una coincidencia debil).
        top_k: tamano del ranking de similares por producto.

    Complejidad: O(E) para indexar + O(sum_a deg(a)^2) para acumular pares,
    con a recorriendo solo atributos no-hub.
    """
    product_nodes = set(nodes.loc[nodes["node_type"] == "PRODUCT", "node_id"]) if not nodes.empty else set()
    product_labels = (
        nodes.loc[nodes["node_type"] == "PRODUCT"].set_index("node_id")["label"].to_dict()
        if not nodes.empty
        else {}
    )
    n_products = len(product_nodes)

    # attr -> {producto: peso}; producto -> suma de pesos (solo atributos incluidos)
    attr_products: dict[str, dict[str, float]] = defaultdict(dict)
    for _, edge in edges.iterrows():
        source, target = str(edge["source"]), str(edge["target"])
        if source in product_nodes:
            attr_products[target][source] = float(edge["weight"])

    hub_threshold = max(2, int(hub_fraction * n_products))
    hubs = {attr for attr, prods in attr_products.items() if len(prods) > hub_threshold}
    included = {attr: prods for attr, prods in attr_products.items() if attr not in hubs}

    product_weight_sum: dict[str, float] = defaultdict(float)
    for prods in included.values():
        for product, weight in prods.items():
            product_weight_sum[product] += weight

    numerator: dict[tuple[str, str], float] = defaultdict(float)
    shared_count: dict[tuple[str, str], int] = defaultdict(int)
    shared_attrs: dict[tuple[str, str], list[str]] = defaultdict(list)
    for attr, prods in included.items():
        for (prod_a, weight_a), (prod_b, weight_b) in combinations(sorted(prods.items()), 2):
            pair = (prod_a, prod_b)
            numerator[pair] += min(weight_a, weight_b)
            shared_count[pair] += 1
            shared_attrs[pair].append(attr)

    rows = []
    for (prod_a, prod_b), num in numerator.items():
        if shared_count[(prod_a, prod_b)] < min_shared_attributes:
            continue
        denominator = product_weight_sum[prod_a] + product_weight_sum[prod_b] - num
        similarity = num / denominator if denominator > 0 else 0.0
        if similarity < min_similarity:
            continue
        rows.append(
            {
                "product_a": prod_a,
                "product_a_label": product_labels.get(prod_a, ""),
                "product_b": prod_b,
                "product_b_label": product_labels.get(prod_b, ""),
                "similarity": round(similarity, 4),
                "shared_attributes": shared_count[(prod_a, prod_b)],
                "shared_attribute_nodes": "|".join(shared_attrs[(prod_a, prod_b)]),
            }
        )

    projection_edges = pd.DataFrame(rows)
    if not projection_edges.empty:
        projection_edges = projection_edges.sort_values("similarity", ascending=False).reset_index(drop=True)

    top_similar = build_top_similar(projection_edges, top_k)
    connected_products = (
        set(projection_edges["product_a"]) | set(projection_edges["product_b"])
        if not projection_edges.empty
        else set()
    )

    metrics = {
        "graph_name": "G_attr_projection",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "params": {
            "hub_fraction": hub_fraction,
            "hub_degree_threshold": hub_threshold,
            "min_similarity": min_similarity,
            "min_shared_attributes": min_shared_attributes,
            "top_k": top_k,
        },
        "products_total": n_products,
        "products_connected": len(connected_products),
        "edge_count": int(len(projection_edges)),
        "excluded_hub_attributes": sorted(
            {f"{attr} (grado {len(attr_products[attr])})" for attr in hubs}
        ),
        "attribute_nodes_used": len(included),
        "pair_generation_cost": int(sum(len(p) * (len(p) - 1) // 2 for p in included.values())),
    }

    return {"edges": projection_edges, "top_similar": top_similar, "metrics": metrics}


def build_top_similar(projection_edges: pd.DataFrame, top_k: int) -> pd.DataFrame:
    """Ranking top-k de similares por producto (vista simetrica de las aristas)."""
    if projection_edges.empty:
        return pd.DataFrame()
    directed = pd.concat(
        [
            projection_edges.rename(
                columns={
                    "product_a": "product",
                    "product_a_label": "product_label",
                    "product_b": "similar",
                    "product_b_label": "similar_label",
                }
            ),
            projection_edges.rename(
                columns={
                    "product_b": "product",
                    "product_b_label": "product_label",
                    "product_a": "similar",
                    "product_a_label": "similar_label",
                }
            ),
        ],
        ignore_index=True,
    )
    directed["rank"] = directed.groupby("product")["similarity"].rank(method="first", ascending=False)
    top = directed.loc[directed["rank"] <= top_k].sort_values(["product", "rank"])
    return top[
        ["product", "product_label", "rank", "similar", "similar_label", "similarity", "shared_attributes"]
    ].reset_index(drop=True)


def run_stage2_projection(stage2_output_dir: str | Path, **kwargs: Any) -> dict[str, Any]:
    stage2_path = Path(stage2_output_dir)
    nodes = pd.read_csv(stage2_path / "semantic_attribute_graph_nodes.csv", encoding="utf-8-sig")
    edges = pd.read_csv(stage2_path / "semantic_attribute_graph_edges.csv", encoding="utf-8-sig")
    return build_product_projection(nodes, edges, **kwargs)


def export_projection(result: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}

    for filename, table in (
        ("product_projection_edges.csv", result["edges"]),
        ("product_projection_top_similar.csv", result["top_similar"]),
    ):
        path = output_path / filename
        table.to_csv(path, index=False, encoding="utf-8-sig")
        paths[filename] = str(path)

    metrics_path = output_path / "product_projection_metrics.json"
    metrics_path.write_text(json.dumps(result["metrics"], indent=2, ensure_ascii=False), encoding="utf-8")
    paths["product_projection_metrics.json"] = str(metrics_path)
    return paths
