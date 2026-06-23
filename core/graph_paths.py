"""Etapa 3 - Conexiones entre entidades: BFS clasico vs BFS bidireccional.

Responde preguntas tipo "¿que conecta al cliente X con el producto Y?" o
"¿que relacion hay entre dos proveedores?" sobre G_business (Etapa 2):
el camino mas corto pasa por documentos, fechas y productos compartidos y
constituye una explicacion legible de la relacion.

Antes (proyecto base): BFS desde el origen hasta tocar el destino, O(b^d)
nodos explorados con factor de ramificacion b y distancia d.

Ahora: BFS bidireccional — se expande simultaneamente desde origen y destino
y se detiene al encontrarse las dos fronteras. Explora O(b^(d/2)) por lado,
es decir O(2·b^(d/2)) total: una reduccion exponencial frente a O(b^d).
Referencia: Pohl, I. (1971) "Bi-directional search", Machine Intelligence 6.

Ambas implementaciones devuelven cuantos nodos expandieron para poder medir
la mejora con datos reales (no solo citarla).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .text_utils import normalize_text


@dataclass
class PathResult:
    path: list[str]
    path_labels: list[str]
    expanded_nodes: int
    found: bool
    algorithm: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "found": self.found,
            "path_length": max(len(self.path) - 1, 0) if self.found else None,
            "expanded_nodes": self.expanded_nodes,
            "path": self.path,
            "path_labels": self.path_labels,
        }


@dataclass
class BusinessGraphPaths:
    adjacency: dict[str, list[str]] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    node_type: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_frames(cls, nodes: pd.DataFrame, edges: pd.DataFrame) -> "BusinessGraphPaths":
        graph = cls()
        for _, node in nodes.iterrows():
            node_id = str(node["node_id"])
            graph.labels[node_id] = str(node.get("label", ""))
            graph.node_type[node_id] = str(node.get("node_type", ""))
        for source, target in zip(edges["source"], edges["target"]):
            graph.adjacency.setdefault(str(source), []).append(str(target))
            graph.adjacency.setdefault(str(target), []).append(str(source))
        return graph

    @classmethod
    def from_transaction_dir(cls, output_dir: str | Path, kind: str = "business") -> "BusinessGraphPaths":
        path = Path(output_dir)
        nodes = pd.read_csv(path / f"transaction_graph_{kind}_nodes.csv", encoding="utf-8-sig")
        edges = pd.read_csv(path / f"transaction_graph_{kind}_edges.csv", encoding="utf-8-sig")
        return cls.from_frames(nodes, edges)

    # ── Resolucion de entidades ─────────────────────────────────────────────

    def find_node(self, text: str, node_types: set[str] | None = None) -> str | None:
        """Localiza un nodo por id exacto o por coincidencia de label."""
        if text in self.adjacency:
            return text
        target = normalize_text(text)
        best = None
        for node_id, label in self.labels.items():
            if node_types and self.node_type.get(node_id) not in node_types:
                continue
            norm = normalize_text(label)
            if norm == target:
                return node_id
            if target and target in norm and best is None:
                best = node_id
        return best

    # ── Algoritmos ──────────────────────────────────────────────────────────

    def bfs_path(self, source: str, target: str) -> PathResult:
        """BFS clasico O(V+E). Linea base para la comparacion."""
        if source == target:
            return PathResult([source], [self.labels.get(source, "")], 0, True, "bfs")
        parent: dict[str, str] = {source: source}
        queue: deque[str] = deque([source])
        expanded = 0
        while queue:
            current = queue.popleft()
            expanded += 1
            for neighbor in self.adjacency.get(current, []):
                if neighbor in parent:
                    continue
                parent[neighbor] = current
                if neighbor == target:
                    return self._build_result(parent, {}, neighbor, None, expanded, "bfs")
                queue.append(neighbor)
        return PathResult([], [], expanded, False, "bfs")

    def bidirectional_bfs_path(self, source: str, target: str) -> PathResult:
        """BFS bidireccional: dos frentes que se encuentran a mitad de camino."""
        if source == target:
            return PathResult([source], [self.labels.get(source, "")], 0, True, "bidirectional_bfs")
        parent_fwd: dict[str, str] = {source: source}
        parent_bwd: dict[str, str] = {target: target}
        frontier_fwd: deque[str] = deque([source])
        frontier_bwd: deque[str] = deque([target])
        expanded = 0

        while frontier_fwd and frontier_bwd:
            # Expandir siempre la frontera mas chica acota el crecimiento.
            if len(frontier_fwd) <= len(frontier_bwd):
                frontier, parent_own, parent_other = frontier_fwd, parent_fwd, parent_bwd
                direction = "fwd"
            else:
                frontier, parent_own, parent_other = frontier_bwd, parent_bwd, parent_fwd
                direction = "bwd"

            for _ in range(len(frontier)):
                current = frontier.popleft()
                expanded += 1
                for neighbor in self.adjacency.get(current, []):
                    if neighbor in parent_own:
                        continue
                    parent_own[neighbor] = current
                    if neighbor in parent_other:
                        if direction == "fwd":
                            return self._build_result(
                                parent_fwd, parent_bwd, neighbor, neighbor, expanded, "bidirectional_bfs"
                            )
                        return self._build_result(
                            parent_fwd, parent_bwd, neighbor, neighbor, expanded, "bidirectional_bfs"
                        )
                    frontier.append(neighbor)
        return PathResult([], [], expanded, False, "bidirectional_bfs")

    def compare(self, source_text: str, target_text: str) -> dict[str, Any]:
        """Resuelve entidades, corre ambos algoritmos y reporta la comparacion."""
        source = self.find_node(source_text)
        target = self.find_node(target_text)
        if source is None or target is None:
            return {
                "error": "entidad no encontrada",
                "source_resolved": source,
                "target_resolved": target,
            }
        baseline = self.bfs_path(source, target)
        improved = self.bidirectional_bfs_path(source, target)
        return {
            "source": source,
            "source_label": self.labels.get(source, ""),
            "target": target,
            "target_label": self.labels.get(target, ""),
            "bfs": baseline.as_dict(),
            "bidirectional_bfs": improved.as_dict(),
            "expansion_ratio": round(baseline.expanded_nodes / max(improved.expanded_nodes, 1), 2),
        }

    # ── Reconstruccion de caminos ───────────────────────────────────────────

    def _build_result(
        self,
        parent_fwd: dict[str, str],
        parent_bwd: dict[str, str],
        meet_fwd: str,
        meet_bwd: str | None,
        expanded: int,
        algorithm: str,
    ) -> PathResult:
        path: list[str] = []
        node = meet_fwd
        while parent_fwd[node] != node:
            path.append(node)
            node = parent_fwd[node]
        path.append(node)
        path.reverse()

        if meet_bwd is not None and parent_bwd:
            node = parent_bwd[meet_bwd]
            while parent_bwd[node] != node:
                path.append(node)
                node = parent_bwd[node]
            if path[-1] != node:
                path.append(node)

        labels = [f"{self.node_type.get(n, '')}:{self.labels.get(n, n)}" for n in path]
        return PathResult(path, labels, expanded, True, algorithm)
