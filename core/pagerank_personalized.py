"""Etapa 5 - Relevancia y recomendacion: frecuencia vs Personalized PageRank.

Antes (proyecto base): la relevancia de un producto era su frecuencia de
venta, y "productos relacionados" eran los co-comprados en la misma factura
(conteo directo a distancia 2). Esto ignora relaciones indirectas: dos
productos que nunca comparten documento pero comparten clientes y fechas no
se relacionan nunca.

Ahora: **PageRank personalizado** sobre G_business. El random walk reinicia
con probabilidad (1 - d) hacia el nodo de interes, de modo que el puntaje
mide proximidad estructural global (multi-salto) y no solo co-ocurrencia
directa. PageRank global (reinicio uniforme) da la relevancia general de
productos/clientes/proveedores. Implementacion propia por iteracion de
potencias: O(k * E) con k iteraciones hasta converger (||delta||_1 < tol).
Referencias: Page, Brin, Motwani & Winograd (1999); Jeh & Widom (2003)
"Scaling Personalized Web Search".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class PageRankEngine:
    adjacency: dict[str, list[tuple[str, float]]] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    node_type: dict[str, str] = field(default_factory=dict)
    out_weight: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_frames(cls, nodes: pd.DataFrame, edges: pd.DataFrame) -> "PageRankEngine":
        engine = cls()
        for _, node in nodes.iterrows():
            node_id = str(node["node_id"])
            engine.labels[node_id] = str(node.get("label", ""))
            engine.node_type[node_id] = str(node.get("node_type", ""))
        for _, edge in edges.iterrows():
            source, target = str(edge["source"]), str(edge["target"])
            weight = max(float(edge.get("weight", 1.0)), 1e-9)
            engine.adjacency.setdefault(source, []).append((target, weight))
            engine.adjacency.setdefault(target, []).append((source, weight))
        engine.out_weight = {
            node: sum(weight for _, weight in neighbors)
            for node, neighbors in engine.adjacency.items()
        }
        return engine

    @classmethod
    def from_transaction_dir(cls, output_dir: str | Path, kind: str = "business") -> "PageRankEngine":
        path = Path(output_dir)
        nodes = pd.read_csv(path / f"transaction_graph_{kind}_nodes.csv", encoding="utf-8-sig")
        edges = pd.read_csv(path / f"transaction_graph_{kind}_edges.csv", encoding="utf-8-sig")
        return cls.from_frames(nodes, edges)

    def pagerank(
        self,
        personalization: dict[str, float] | None = None,
        damping: float = 0.85,
        max_iter: int = 100,
        tol: float = 1e-8,
    ) -> dict[str, float]:
        """Iteracion de potencias. personalization=None -> PageRank global."""
        nodes = list(self.adjacency)
        n = len(nodes)
        if n == 0:
            return {}

        if personalization:
            total = sum(personalization.values())
            restart = {node: value / total for node, value in personalization.items()}
        else:
            restart = {node: 1.0 / n for node in nodes}

        rank = dict(restart) if personalization else {node: 1.0 / n for node in nodes}
        for node in nodes:
            rank.setdefault(node, 0.0)

        for _ in range(max_iter):
            next_rank = {node: (1.0 - damping) * restart.get(node, 0.0) for node in nodes}
            for node in nodes:
                mass = rank[node]
                if mass <= 0.0:
                    continue
                out = self.out_weight.get(node, 0.0)
                if out <= 0.0:
                    continue
                share = damping * mass / out
                for neighbor, weight in self.adjacency[node]:
                    next_rank[neighbor] += share * weight
            delta = sum(abs(next_rank[node] - rank[node]) for node in nodes)
            rank = next_rank
            if delta < tol:
                break
        return rank

    # ── Consultas ───────────────────────────────────────────────────────────

    def top_nodes(
        self, rank: dict[str, float], node_types: set[str], k: int = 10, exclude: set[str] | None = None
    ) -> pd.DataFrame:
        exclude = exclude or set()
        rows = [
            {
                "node_id": node,
                "node_type": self.node_type.get(node, ""),
                "label": self.labels.get(node, ""),
                "score": score,
            }
            for node, score in rank.items()
            if self.node_type.get(node) in node_types and node not in exclude
        ]
        table = pd.DataFrame(rows).sort_values("score", ascending=False).head(k).reset_index(drop=True)
        if not table.empty:
            table["score"] = table["score"].round(6)
        return table

    def related_products(self, product_node: str, k: int = 10) -> pd.DataFrame:
        """Productos relacionados a uno dado via PPR (reinicio en el producto)."""
        rank = self.pagerank(personalization={product_node: 1.0})
        return self.top_nodes(rank, {"PRODUCT"}, k=k, exclude={product_node})

    def cooccurrence_baseline(self, product_node: str, k: int = 10) -> pd.DataFrame:
        """Baseline 'antes': co-ocurrencia directa en el mismo documento."""
        scores: dict[str, float] = {}
        for doc, _ in self.adjacency.get(product_node, []):
            if self.node_type.get(doc) != "DOC":
                continue
            for neighbor, _ in self.adjacency.get(doc, []):
                if neighbor != product_node and self.node_type.get(neighbor) == "PRODUCT":
                    scores[neighbor] = scores.get(neighbor, 0.0) + 1.0
        rows = [
            {"node_id": node, "label": self.labels.get(node, ""), "co_docs": score}
            for node, score in scores.items()
        ]
        return (
            pd.DataFrame(rows).sort_values("co_docs", ascending=False).head(k).reset_index(drop=True)
            if rows
            else pd.DataFrame()
        )
