"""Etapa 3 - Busqueda semantica sobre G_attr (BFS con semillas).

Generalizacion del buscador del proyecto base (streamlit_app/motor/bfs.py):
alli el parser tenia regex hardcodeadas por dominio (FRASCO, PET, AMBAR...);
aqui el vocabulario se **aprende del grafo**: cada nodo atributo de G_attr es
un termino reconocible, asi el mismo buscador funciona para plasticos,
ferreteria o cualquier catalogo procesado por las Etapas 1-2.

Flujo:
    query -> tokens normalizados -> semillas (nodos atributo de G_attr)
          -> BFS O(V+E) con decaimiento por distancia
          -> boost por cobertura de semillas
          -> filtro EXACTO para atributos numericos (capacidad, boca)
          -> top-k

Reglas heredadas del proyecto base (decisiones ya validadas):
- Atributos numericos se filtran de forma EXACTA post-BFS: si el usuario pide
  100ML solo se devuelven productos de exactamente 100ML, sin aproximaciones.
- Cobertura: un producto que toca mas semillas distintas multiplica su puntaje
  con ((cobertura/total)^2 * 20 + 1).

Complejidad: construir el indice es O(V+E); cada busqueda es O(V+E) en el peor
caso (BFS completo) + O(p log p) para ordenar p productos puntuados.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .attribute_extractor import extract_capacity, extract_mouth_size
from .semantic_graph import node_id
from .text_utils import normalize_text


NUMERIC_NODE_TYPES = {"CAPACITY", "MOUTH_SIZE"}
DISTANCE_DECAY = (5, 4, 3, 2, 1)  # peso por distancia BFS 0..4+, igual que el proyecto base


def _singular(token: str) -> str:
    if len(token) > 4 and token.endswith("ES"):
        return token[:-2]
    if len(token) > 3 and token.endswith("S"):
        return token[:-1]
    return token


@dataclass
class SemanticSearchIndex:
    """Indice de busqueda construido desde los CSV de G_attr (Etapa 2)."""

    adjacency: dict[str, list[tuple[str, float]]] = field(default_factory=dict)
    node_type: dict[str, str] = field(default_factory=dict)
    label_to_nodes: dict[str, list[str]] = field(default_factory=dict)
    product_labels: dict[str, str] = field(default_factory=dict)
    last_stats: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_frames(cls, nodes: pd.DataFrame, edges: pd.DataFrame) -> "SemanticSearchIndex":
        index = cls()
        for _, node in nodes.iterrows():
            node_id = str(node["node_id"])
            index.node_type[node_id] = str(node["node_type"])
            label = normalize_text(node.get("label"))
            if node["node_type"] == "PRODUCT":
                index.product_labels[node_id] = str(node.get("label", ""))
            elif label:
                index.label_to_nodes.setdefault(label, []).append(node_id)
        for _, edge in edges.iterrows():
            source, target = str(edge["source"]), str(edge["target"])
            weight = float(edge["weight"])
            index.adjacency.setdefault(source, []).append((target, weight))
            index.adjacency.setdefault(target, []).append((source, weight))
        return index

    @classmethod
    def from_stage2_dir(cls, stage2_output_dir: str | Path) -> "SemanticSearchIndex":
        stage2_path = Path(stage2_output_dir)
        nodes = pd.read_csv(stage2_path / "semantic_attribute_graph_nodes.csv", encoding="utf-8-sig")
        edges = pd.read_csv(stage2_path / "semantic_attribute_graph_edges.csv", encoding="utf-8-sig")
        return cls.from_frames(nodes, edges)

    # ── Semillas ────────────────────────────────────────────────────────────

    def extract_seeds(self, query: str) -> tuple[list[str], list[str]]:
        """Resuelve el query contra el vocabulario del grafo (sin reglas de dominio).

        Devuelve (semillas presentes en el grafo, filtros numericos pedidos).
        Un filtro numerico se registra aunque su nodo NO exista en el grafo:
        pedir 123ML cuando ningun producto tiene 123ML debe dar cero
        resultados, nunca una aproximacion.
        """
        text = normalize_text(query)
        seeds: list[str] = []
        seen: set[str] = set()
        numeric_filters: list[str] = []

        def add(candidate_node: str) -> None:
            if candidate_node not in seen and candidate_node in self.node_type:
                seen.add(candidate_node)
                seeds.append(candidate_node)

        # Atributos numericos: mismos extractores y mismo constructor de id de
        # nodo que la Etapa 2, para que la semilla coincida exactamente.
        capacity_value, capacity_unit, _, _ = extract_capacity(text)
        if capacity_value is not None and capacity_unit:
            capacity_node = node_id("CAPACITY", f"{capacity_value:g}{capacity_unit.upper()}")
            numeric_filters.append(capacity_node)
            add(capacity_node)
        mouth_size, _, _ = extract_mouth_size(text)
        if mouth_size is not None:
            mouth_node = node_id("MOUTH_SIZE", f"{mouth_size:g}MM")
            numeric_filters.append(mouth_node)
            add(mouth_node)

        # Atributos textuales: match exacto o singularizado contra labels del grafo.
        for token in text.split():
            for candidate in (token, _singular(token)):
                for matched_node in self.label_to_nodes.get(candidate, []):
                    add(matched_node)
        return seeds, numeric_filters

    # ── Busqueda ────────────────────────────────────────────────────────────

    def search(self, query: str, k: int = 10) -> list[dict[str, Any]]:
        seeds, numeric_filters = self.extract_seeds(query)
        if not seeds:
            self.last_stats = {"seeds": [], "numeric_filters": numeric_filters, "expanded_nodes": 0}
            return []

        total_seeds = len(seeds)

        # Cobertura: cuantas semillas tiene el producto como atributo directo.
        coverage: dict[str, int] = {}
        for seed in seeds:
            for neighbor, _ in self.adjacency.get(seed, []):
                if self.node_type.get(neighbor) == "PRODUCT":
                    coverage[neighbor] = coverage.get(neighbor, 0) + 1

        # BFS multi-semilla con decaimiento: productos cercanos a las semillas
        # acumulan puntaje ponderado por la confianza de la arista.
        visited: set[str] = set(seeds)
        queue: deque[tuple[str, int]] = deque((seed, 0) for seed in seeds)
        score: dict[str, float] = {}
        expanded = 0

        while queue:
            node, dist = queue.popleft()
            expanded += 1
            decay = DISTANCE_DECAY[min(dist, len(DISTANCE_DECAY) - 1)]
            for neighbor, weight in self.adjacency.get(node, []):
                if self.node_type.get(neighbor) == "PRODUCT":
                    score[neighbor] = score.get(neighbor, 0.0) + decay * weight
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, dist + 1))

        if not score:
            self.last_stats = {"seeds": seeds, "numeric_filters": numeric_filters, "expanded_nodes": expanded}
            return []

        for product in score:
            cov = coverage.get(product, 0)
            score[product] *= (cov / total_seeds) ** 2 * 20 + 1

        # Filtro exacto numerico: el producto debe estar conectado directamente
        # al nodo numerico pedido (100ML es 100ML, nunca 120ML). Si el nodo no
        # existe en el grafo, el conjunto permitido queda vacio a proposito.
        allowed: set[str] | None = None
        for filter_node in numeric_filters:
            adjacent = {
                neighbor
                for neighbor, _ in self.adjacency.get(filter_node, [])
                if self.node_type.get(neighbor) == "PRODUCT"
            }
            allowed = adjacent if allowed is None else (allowed & adjacent)

        results = []
        for product in sorted(score, key=score.get, reverse=True):
            if allowed is not None and product not in allowed:
                continue
            results.append(
                {
                    "product": product,
                    "label": self.product_labels.get(product, ""),
                    "relevance": round(score[product], 2),
                    "seed_coverage": coverage.get(product, 0),
                    "total_seeds": total_seeds,
                }
            )
            if len(results) >= k:
                break

        self.last_stats = {
            "seeds": seeds,
            "numeric_filters": numeric_filters,
            "expanded_nodes": expanded,
            "scored_products": len(score),
        }
        return results
