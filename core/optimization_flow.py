"""Etapa 4 - Asignacion optima de un pedido multi-SKU: flujo de costo minimo.

Antes (proyecto base y optimization_baseline.py): cada SKU se optimiza por
separado con un heap de precios. Si dos SKUs comparten al proveedor mas
barato y su capacidad global no alcanza para ambos, el resultado por-SKU es
infactible o suboptimo: nadie decide *cual* SKU deberia quedarse con la
capacidad barata.

Ahora: el pedido completo se modela como una red de flujo:

    FUENTE --(cap=cantidad pedida, costo 0)--> SKU_i
    SKU_i  --(cap=capacidad oferta, costo=precio unitario)--> PROV_j
    PROV_j --(cap=capacidad global proveedor, costo 0)--> SUMIDERO

El flujo de costo minimo asigna unidades respetando TODAS las capacidades a
la vez y minimiza el costo total global del pedido. Algoritmo: successive
shortest paths con potenciales de Johnson (Dijkstra sobre costos reducidos,
validos porque los costos originales son no negativos).

Complejidad: O(F * (E log V)) con F = numero de caminos aumentantes (acotado
por el numero de aristas saturadas, no por las unidades: cada aumento empuja
el cuello de botella completo). Referencias: Ahuja, Magnanti, Orlin (1993)
"Network Flows", cap. 9; Edmonds & Karp (1972).

Las capacidades provienen de la disponibilidad inferida del historial
(core/purchase_options.py).
"""

from __future__ import annotations

import heapq
from typing import Any

import pandas as pd

from .optimization_baseline import per_sku_order


class MinCostFlow:
    """Red de flujo con lista de adyacencia y aristas residuales."""

    def __init__(self) -> None:
        self.graph: list[list[list[float]]] = []  # nodo -> [destino, cap, costo, idx_reversa]
        self.node_ids: dict[str, int] = {}
        self.node_names: list[str] = []

    def node(self, name: str) -> int:
        if name not in self.node_ids:
            self.node_ids[name] = len(self.node_names)
            self.node_names.append(name)
            self.graph.append([])
        return self.node_ids[name]

    def add_edge(self, source: str, target: str, capacity: float, cost: float) -> None:
        u, v = self.node(source), self.node(target)
        self.graph[u].append([v, capacity, cost, len(self.graph[v])])
        self.graph[v].append([u, 0.0, -cost, len(self.graph[u]) - 1])

    def solve(self, source_name: str, sink_name: str) -> dict[str, Any]:
        """Empuja el maximo flujo posible al minimo costo total."""
        source, sink = self.node(source_name), self.node(sink_name)
        n = len(self.graph)
        potential = [0.0] * n  # costos no negativos: potenciales iniciales 0 validos
        total_flow = 0.0
        total_cost = 0.0
        augmenting_paths = 0

        while True:
            dist = [float("inf")] * n
            dist[source] = 0.0
            parent_edge: list[tuple[int, int] | None] = [None] * n
            heap: list[tuple[float, int]] = [(0.0, source)]
            while heap:
                d, u = heapq.heappop(heap)
                if d > dist[u]:
                    continue
                for edge_index, edge in enumerate(self.graph[u]):
                    v, capacity, cost, _ = edge
                    if capacity <= 1e-9:
                        continue
                    reduced = d + cost + potential[u] - potential[v]
                    if reduced < dist[v] - 1e-9:
                        dist[v] = reduced
                        parent_edge[v] = (u, edge_index)
                        heapq.heappush(heap, (reduced, v))

            if parent_edge[sink] is None:
                break

            for i in range(n):
                if dist[i] < float("inf"):
                    potential[i] += dist[i]

            bottleneck = float("inf")
            node = sink
            while node != source:
                u, edge_index = parent_edge[node]
                bottleneck = min(bottleneck, self.graph[u][edge_index][1])
                node = u

            node = sink
            while node != source:
                u, edge_index = parent_edge[node]
                edge = self.graph[u][edge_index]
                edge[1] -= bottleneck
                self.graph[edge[0]][edge[3]][1] += bottleneck
                total_cost += bottleneck * edge[2]
                node = u

            total_flow += bottleneck
            augmenting_paths += 1

        return {
            "flow": total_flow,
            "cost": round(total_cost, 2),
            "augmenting_paths": augmenting_paths,
        }

    def flow_on_edges(self, prefix_source: str, prefix_target: str) -> list[dict[str, Any]]:
        """Extrae el flujo asignado leyendo las aristas residuales reversas."""
        rows = []
        for u, edges in enumerate(self.graph):
            name_u = self.node_names[u]
            if not name_u.startswith(prefix_source):
                continue
            for v, _, cost, reverse_index in edges:
                name_v = self.node_names[v]
                if not name_v.startswith(prefix_target):
                    continue
                flow = self.graph[v][reverse_index][1]  # capacidad acumulada en la reversa
                if flow > 1e-9 and cost >= 0:
                    rows.append(
                        {
                            "from": name_u,
                            "to": name_v,
                            "units": round(flow, 2),
                            "unit_cost": cost,
                            "subtotal": round(flow * cost, 2),
                        }
                    )
        return rows


def optimize_order_flow(options: pd.DataFrame, order: dict[str, float]) -> dict[str, Any]:
    """Asignacion optima global de un pedido multi-SKU.

    Devuelve el plan por (SKU, proveedor), el costo total minimo y cuantas
    unidades quedaron sin cubrir si la capacidad inferida no alcanza.
    """
    network = MinCostFlow()
    requested = 0.0
    for product_id, quantity in order.items():
        requested += float(quantity)
        network.add_edge("SOURCE", f"SKU:{product_id}", float(quantity), 0.0)

    suppliers_seen: set[str] = set()
    for product_id in order:
        for row in options.loc[options["product_id"] == str(product_id)].itertuples():
            supplier = str(row.supplier)
            network.add_edge(
                f"SKU:{product_id}", f"PROV:{supplier}", float(row.capacity_units), float(row.unit_cost)
            )
            if supplier not in suppliers_seen:
                suppliers_seen.add(supplier)
                network.add_edge(f"PROV:{supplier}", "SINK", float(row.supplier_capacity), 0.0)

    solution = network.solve("SOURCE", "SINK")
    plan = network.flow_on_edges("SKU:", "PROV:")
    return {
        "method": "min_cost_flow",
        "plan": plan,
        "total_cost": solution["cost"],
        "units_assigned": solution["flow"],
        "units_unfilled": round(requested - solution["flow"], 2),
        "augmenting_paths": solution["augmenting_paths"],
    }


def compare_with_baseline(options: pd.DataFrame, order: dict[str, float]) -> dict[str, Any]:
    """Min-cost flow vs asignacion por-SKU del baseline, sobre el mismo pedido.

    El baseline ignora la capacidad global del proveedor; para una comparacion
    justa se reporta ademas si su plan la viola (infactibilidad oculta).
    """
    flow_result = optimize_order_flow(options, order)
    baseline_result = per_sku_order(options, order)

    supplier_capacity = (
        options.drop_duplicates("supplier").set_index("supplier")["supplier_capacity"].to_dict()
    )
    used: dict[str, float] = {}
    for plan in baseline_result["plans"].values():
        for item in plan["plan"]:
            used[item["supplier"]] = used.get(item["supplier"], 0.0) + item["units"]
    violations = {
        supplier: {"assigned": round(units, 2), "capacity": supplier_capacity.get(supplier)}
        for supplier, units in used.items()
        if supplier_capacity.get(supplier) is not None and units > supplier_capacity[supplier] + 1e-9
    }

    return {
        "order": order,
        "min_cost_flow": flow_result,
        "baseline_per_sku": baseline_result,
        "baseline_capacity_violations": violations,
        "baseline_is_feasible": not violations,
        "cost_delta": round(baseline_result["total_cost"] - flow_result["total_cost"], 2),
    }
