"""Etapa 5 - Familias de productos: componentes conexos vs Leiden.

Antes (proyecto base / Etapa 2): la unica nocion de "grupo" era el componente
conexo del grafo — binaria y gruesa: el componente mayor de G_attr agrupa
~700 nodos sin distinguir familias internas.

Ahora: deteccion de comunidades con **Leiden** (Traag, Waltman & van Eck,
2019, "From Louvain to Leiden: guaranteeing well-connected communities",
Scientific Reports 9:5233) sobre la proyeccion producto-producto ponderada
(core/product_projection.py). Leiden mejora a Louvain garantizando
comunidades bien conectadas (Louvain puede producir comunidades internamente
desconectadas) y converge mas rapido. Complejidad empirica O(n log n).

La comparacion contra el baseline (componentes conexos) se reporta con ambos
resultados para mostrar la ganancia de resolucion.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .text_utils import normalize_text


def detect_communities(projection_edges: pd.DataFrame) -> dict[str, Any]:
    """Leiden (modularidad, ponderado) + baseline de componentes conexos."""
    import igraph as ig
    import leidenalg

    if projection_edges.empty:
        return {"membership": pd.DataFrame(), "metrics": {}}

    vertices = sorted(set(projection_edges["product_a"]) | set(projection_edges["product_b"]))
    vertex_index = {vertex: position for position, vertex in enumerate(vertices)}
    edge_list = [
        (vertex_index[a], vertex_index[b])
        for a, b in zip(projection_edges["product_a"], projection_edges["product_b"])
    ]
    weights = projection_edges["similarity"].astype(float).tolist()

    graph = ig.Graph(n=len(vertices), edges=edge_list)
    graph.es["weight"] = weights

    partition = leidenalg.find_partition(
        graph,
        leidenalg.ModularityVertexPartition,
        weights="weight",
        seed=42,
    )
    components = graph.connected_components()

    labels = dict(
        zip(projection_edges["product_a"], projection_edges["product_a_label"])
    ) | dict(zip(projection_edges["product_b"], projection_edges["product_b_label"]))

    membership = pd.DataFrame(
        {
            "product": vertices,
            "product_label": [labels.get(vertex, "") for vertex in vertices],
            "leiden_community": partition.membership,
            "connected_component": components.membership,
        }
    )

    community_sizes = membership["leiden_community"].value_counts()
    metrics = {
        "algorithm": "leiden_modularity",
        "reference": "Traag, Waltman & van Eck (2019), Scientific Reports 9:5233",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "products": len(vertices),
        "leiden_communities": int(len(set(partition.membership))),
        "leiden_modularity": round(float(partition.modularity), 4),
        "baseline_connected_components": int(len(components)),
        "largest_leiden_community": int(community_sizes.max()),
        "largest_connected_component": int(max(components.sizes())),
        "community_size_distribution": {
            str(community): int(size) for community, size in community_sizes.head(15).items()
        },
    }
    return {"membership": membership, "metrics": metrics}


def describe_communities(membership: pd.DataFrame, top_terms: int = 5, min_size: int = 3) -> pd.DataFrame:
    """Etiqueta cada comunidad con los tokens dominantes de sus productos."""
    if membership.empty:
        return pd.DataFrame()
    rows = []
    for community, group in membership.groupby("leiden_community"):
        if len(group) < min_size:
            continue
        tokens: Counter[str] = Counter()
        for label in group["product_label"]:
            tokens.update(token for token in normalize_text(label).split() if len(token) > 2)
        rows.append(
            {
                "leiden_community": community,
                "size": len(group),
                "top_terms": " ".join(token for token, _ in tokens.most_common(top_terms)),
                "sample_products": " | ".join(group["product_label"].head(3)),
            }
        )
    return pd.DataFrame(rows).sort_values("size", ascending=False).reset_index(drop=True)


def export_communities(result: dict[str, Any], descriptions: pd.DataFrame, output_dir: str | Path) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}

    membership_path = output_path / "leiden_communities.csv"
    result["membership"].to_csv(membership_path, index=False, encoding="utf-8-sig")
    paths["leiden_communities.csv"] = str(membership_path)

    desc_path = output_path / "leiden_community_descriptions.csv"
    descriptions.to_csv(desc_path, index=False, encoding="utf-8-sig")
    paths["leiden_community_descriptions.csv"] = str(desc_path)

    metrics_path = output_path / "leiden_metrics.json"
    metrics_path.write_text(json.dumps(result["metrics"], indent=2, ensure_ascii=False), encoding="utf-8")
    paths["leiden_metrics.json"] = str(metrics_path)
    return paths
