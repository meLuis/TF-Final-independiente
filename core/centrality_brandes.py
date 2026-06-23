"""Centralidad de intermediacion de Brandes sobre G_business.

Baseline (curso): centralidad de grado (cuantas conexiones tiene un nodo).
Investigado: betweenness de Brandes (2001), "A faster algorithm for betweenness
centrality", J. Math. Sociology 25(2). Mide cuantos caminos minimos pasan por un
nodo: detecta proveedores/productos "puente" criticos aunque no sean los de mayor
grado. Exacto, no ponderado, O(V*E) (una BFS por fuente + acumulacion de
dependencias en orden inverso).
"""

from __future__ import annotations

from collections import deque

import pandas as pd


def build_adjacency(edges: pd.DataFrame) -> dict[str, list[str]]:
    """Lista de adyacencia no dirigida desde aristas source/target."""
    adjacency: dict[str, list[str]] = {}
    for source, target in zip(edges["source"].astype(str), edges["target"].astype(str)):
        adjacency.setdefault(source, []).append(target)
        adjacency.setdefault(target, []).append(source)
    return adjacency


def degree_centrality(adjacency: dict[str, list[str]]) -> dict[str, float]:
    """Baseline: grado de cada nodo."""
    return {node: float(len(neighbors)) for node, neighbors in adjacency.items()}


def betweenness_centrality(adjacency: dict[str, list[str]]) -> dict[str, float]:
    """Brandes exacto para grafos no dirigidos y no ponderados."""
    betweenness = {node: 0.0 for node in adjacency}

    for source in adjacency:
        stack: list[str] = []
        predecessors: dict[str, list[str]] = {node: [] for node in adjacency}
        sigma = {node: 0.0 for node in adjacency}
        sigma[source] = 1.0
        distance = {node: -1 for node in adjacency}
        distance[source] = 0
        queue: deque[str] = deque([source])

        while queue:
            v = queue.popleft()
            stack.append(v)
            for w in adjacency[v]:
                if distance[w] < 0:
                    queue.append(w)
                    distance[w] = distance[v] + 1
                if distance[w] == distance[v] + 1:
                    sigma[w] += sigma[v]
                    predecessors[w].append(v)

        delta = {node: 0.0 for node in adjacency}
        while stack:
            w = stack.pop()
            for v in predecessors[w]:
                delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
            if w != source:
                betweenness[w] += delta[w]

    # No dirigido: cada camino se cuenta dos veces.
    return {node: value / 2.0 for node, value in betweenness.items()}


def supplier_betweenness(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    top_k: int = 15,
    node_types: tuple[str, ...] = ("SUPPLIER", "PRODUCT"),
) -> dict:
    """Ranking de intermediacion (investigado) vs grado (baseline) sobre G_business."""
    adjacency = build_adjacency(edges)
    labels = dict(zip(nodes["node_id"].astype(str), nodes["label"].astype(str)))
    types = dict(zip(nodes["node_id"].astype(str), nodes["node_type"].astype(str)))

    bc = betweenness_centrality(adjacency)
    dc = degree_centrality(adjacency)

    def _rank(scores: dict[str, float], column: str) -> pd.DataFrame:
        rows = [
            {
                "node_id": node,
                "node_type": types.get(node, ""),
                "label": labels.get(node, node),
                column: round(value, 4),
            }
            for node, value in scores.items()
            if types.get(node) in node_types
        ]
        return (
            pd.DataFrame(rows)
            .sort_values(column, ascending=False)
            .head(top_k)
            .reset_index(drop=True)
        )

    return {
        "betweenness": _rank(bc, "betweenness"),
        "degree": _rank(dc, "degree"),
        "betweenness_scores": {node: round(bc[node], 4) for node in bc if types.get(node) in node_types},
        "degree_scores": {node: dc[node] for node in dc if types.get(node) in node_types},
        "metrics": {
            "algorithm": "Brandes (2001) betweenness centrality",
            "nodes": len(adjacency),
            "edges": int(len(edges)),
            "node_types_ranked": list(node_types),
        },
    }
