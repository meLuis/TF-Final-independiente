"""Bellman-Ford para escenarios de ofertas y ahorros historicos.

Este modulo no inventa promociones. Genera un grafo desde el historial limpio
de compras: para cada producto se calcula un costo de referencia y cada opcion
producto-proveedor recibe un peso = costo_unitario - costo_referencia.

Si el proveedor esta por debajo de la referencia, la arista tiene peso negativo:
representa ahorro real observado frente al precio de referencia. Bellman-Ford
se usa porque admite pesos negativos y deja lista la deteccion de ciclos
negativos cuando se agreguen ofertas manuales mas complejas.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .purchase_options import build_supply_options


@dataclass
class BellmanFordGraph:
    edges: list[dict[str, Any]] = field(default_factory=list)
    nodes: set[str] = field(default_factory=set)

    def add_edge(self, source: str, target: str, weight: float, **attrs: Any) -> None:
        self.nodes.add(source)
        self.nodes.add(target)
        row = {"source": source, "target": target, "weight": float(weight)}
        row.update(attrs)
        self.edges.append(row)

    def shortest_paths(self, source: str) -> dict[str, Any]:
        distance = {node: float("inf") for node in self.nodes}
        predecessor: dict[str, str | None] = {node: None for node in self.nodes}
        distance[source] = 0.0

        for _ in range(max(len(self.nodes) - 1, 0)):
            changed = False
            for edge in self.edges:
                u, v, w = edge["source"], edge["target"], float(edge["weight"])
                if distance[u] != float("inf") and distance[u] + w < distance[v] - 1e-12:
                    distance[v] = distance[u] + w
                    predecessor[v] = u
                    changed = True
            if not changed:
                break

        negative_cycle_edges = []
        for edge in self.edges:
            u, v, w = edge["source"], edge["target"], float(edge["weight"])
            if distance[u] != float("inf") and distance[u] + w < distance[v] - 1e-12:
                negative_cycle_edges.append(edge)

        return {
            "distance": distance,
            "predecessor": predecessor,
            "negative_cycle_edges": negative_cycle_edges,
            "has_negative_cycle": bool(negative_cycle_edges),
        }


def _reference_costs(options: pd.DataFrame) -> pd.DataFrame:
    """Costo de referencia por producto.

    Se usa la mediana de costos promedio por proveedor. La mediana evita que un
    proveedor extremadamente caro infle artificialmente el ahorro.
    """
    refs = (
        options.groupby("product_id", as_index=False)
        .agg(
            reference_unit_cost=("avg_unit_cost", "median"),
            supplier_options=("supplier_norm", "nunique"),
        )
    )
    return refs


def build_offer_candidates(stage1_output_dir: str | Path) -> pd.DataFrame:
    """Genera candidatos producto-proveedor con pesos compatibles con Bellman-Ford."""
    options = build_supply_options(stage1_output_dir)
    if options.empty:
        return pd.DataFrame()

    refs = _reference_costs(options)
    candidates = options.merge(refs, on="product_id", how="left")
    candidates["effective_unit_cost"] = pd.to_numeric(candidates["unit_cost"], errors="coerce")
    candidates["reference_unit_cost"] = pd.to_numeric(candidates["reference_unit_cost"], errors="coerce")
    candidates = candidates.dropna(subset=["effective_unit_cost", "reference_unit_cost"])
    candidates = candidates.loc[candidates["reference_unit_cost"] > 0].copy()

    candidates["edge_weight"] = (
        candidates["effective_unit_cost"] - candidates["reference_unit_cost"]
    ).round(6)
    candidates["savings_per_unit"] = (
        candidates["reference_unit_cost"] - candidates["effective_unit_cost"]
    ).round(6)
    candidates["savings_pct"] = (
        candidates["savings_per_unit"] / candidates["reference_unit_cost"]
    ).round(6)
    candidates["is_negative_edge"] = candidates["edge_weight"] < 0
    candidates["scenario_type"] = candidates["is_negative_edge"].map(
        lambda flag: "historical_saving" if flag else "at_or_above_reference"
    )

    keep = [
        "product_id",
        "product_name",
        "supplier",
        "supplier_norm",
        "supplier_options",
        "effective_unit_cost",
        "reference_unit_cost",
        "edge_weight",
        "savings_per_unit",
        "savings_pct",
        "capacity_units",
        "supplier_capacity",
        "purchase_lines",
        "last_purchase",
        "is_negative_edge",
        "scenario_type",
    ]
    return candidates[keep].sort_values(
        ["product_id", "edge_weight", "purchase_lines"], ascending=[True, True, False]
    )


def build_bellman_ford_edges(candidates: pd.DataFrame) -> pd.DataFrame:
    """Construye aristas SOURCE -> PRODUCT -> SUPPLIER_OPTION -> SINK."""
    rows: list[dict[str, Any]] = []
    for product_id, group in candidates.groupby("product_id"):
        product_node = f"PRODUCT:{product_id}"
        sink_node = f"SINK:{product_id}"
        rows.append(
            {
                "source": "SOURCE",
                "target": product_node,
                "weight": 0.0,
                "edge_type": "start_product",
                "product_id": product_id,
                "supplier": "",
            }
        )
        for row in group.itertuples(index=False):
            supplier_node = f"OPTION:{row.product_id}:{row.supplier_norm}"
            rows.append(
                {
                    "source": product_node,
                    "target": supplier_node,
                    "weight": float(row.edge_weight),
                    "edge_type": row.scenario_type,
                    "product_id": row.product_id,
                    "product_name": row.product_name,
                    "supplier": row.supplier,
                    "effective_unit_cost": float(row.effective_unit_cost),
                    "reference_unit_cost": float(row.reference_unit_cost),
                    "savings_per_unit": float(row.savings_per_unit),
                    "savings_pct": float(row.savings_pct),
                    "capacity_units": float(row.capacity_units),
                    "supplier_capacity": float(row.supplier_capacity),
                    "purchase_lines": int(row.purchase_lines),
                    "last_purchase": row.last_purchase,
                }
            )
            rows.append(
                {
                    "source": supplier_node,
                    "target": sink_node,
                    "weight": 0.0,
                    "edge_type": "finish_product",
                    "product_id": row.product_id,
                    "supplier": row.supplier,
                }
            )
    return pd.DataFrame(rows)


def run_bellman_ford_offer_analysis(stage1_output_dir: str | Path) -> dict[str, Any]:
    candidates = build_offer_candidates(stage1_output_dir)
    if candidates.empty:
        return {
            "candidates": candidates,
            "edges": pd.DataFrame(),
            "best_paths": pd.DataFrame(),
            "summary": {"status": "empty", "message": "No hay opciones de compra validas."},
        }

    edges_df = build_bellman_ford_edges(candidates)
    graph = BellmanFordGraph()
    for row in edges_df.to_dict("records"):
        attrs = {k: v for k, v in row.items() if k not in {"source", "target", "weight"}}
        graph.add_edge(str(row["source"]), str(row["target"]), float(row["weight"]), **attrs)

    solution = graph.shortest_paths("SOURCE")
    distance = solution["distance"]
    best_rows = []
    option_edges = edges_df.loc[edges_df["edge_type"].isin(["historical_saving", "at_or_above_reference"])]

    for product_id, group in option_edges.groupby("product_id"):
        # La mejor opcion sale de las DISTANCIAS de Bellman-Ford (no de un sort del
        # peso): en este DAG coincide con el menor peso, pero asi el resultado sigue
        # siendo correcto si el grafo gana saltos intermedios (ofertas encadenadas).
        group = group.assign(
            bf_distance=group["target"].map(lambda node: float(distance.get(node, float("inf"))))
        )
        best = group.loc[group["bf_distance"].idxmin()]
        best_distance = float(best["bf_distance"])
        best_rows.append(
            {
                "product_id": product_id,
                "product_name": best.get("product_name", ""),
                "best_supplier": best.get("supplier", ""),
                "reference_unit_cost": round(float(best.get("reference_unit_cost", 0.0)), 6),
                "effective_unit_cost": round(float(best.get("effective_unit_cost", 0.0)), 6),
                "bellman_ford_distance": round(best_distance, 6),
                "savings_per_unit": round(float(best.get("savings_per_unit", 0.0)), 6),
                "savings_pct": round(float(best.get("savings_pct", 0.0)), 6),
                "capacity_units": round(float(best.get("capacity_units", 0.0)), 2),
                "supplier_capacity": round(float(best.get("supplier_capacity", 0.0)), 2),
                "purchase_lines": int(best.get("purchase_lines", 0)),
                "last_purchase": best.get("last_purchase", ""),
                "has_negative_edge": bool(best_distance < 0),
            }
        )

    best_paths = pd.DataFrame(best_rows).sort_values(
        ["has_negative_edge", "savings_per_unit"], ascending=[False, False]
    )
    summary = {
        "status": "ready",
        "algorithm": "Bellman-Ford",
        "source": str(stage1_output_dir),
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "candidate_rows": int(len(candidates)),
        "products_analyzed": int(candidates["product_id"].nunique()),
        "negative_edges": int(candidates["is_negative_edge"].sum()),
        "products_with_savings": int(best_paths["has_negative_edge"].sum()),
        "has_negative_cycle": bool(solution["has_negative_cycle"]),
        "negative_cycle_edge_count": int(len(solution["negative_cycle_edges"])),
        "note": (
            "Modo automatico: pesos negativos representan ahorros historicos "
            "frente al costo de referencia, no ofertas inventadas."
        ),
    }
    return {
        "candidates": candidates,
        "edges": edges_df,
        "best_paths": best_paths,
        "summary": summary,
    }


def export_bellman_ford_offer_analysis(result: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}

    for name in ("candidates", "edges", "best_paths"):
        table = result.get(name)
        if isinstance(table, pd.DataFrame):
            filename = f"bellman_ford_{name}.csv"
            path = output_path / filename
            table.to_csv(path, index=False, encoding="utf-8-sig")
            paths[filename] = str(path)

    summary_path = output_path / "bellman_ford_summary.json"
    summary_path.write_text(
        json.dumps(result.get("summary", {}), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    paths["bellman_ford_summary.json"] = str(summary_path)
    return paths

