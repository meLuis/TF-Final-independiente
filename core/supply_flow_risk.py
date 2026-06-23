"""Riesgo y cuello de botella de abastecimiento.

Baseline (curso): % de dependencia por proveedor + impacto al eliminar uno.
Investigado: Max-flow / Min-cut con Dinic (1970) sobre la red

    SOURCE -> SUPPLIER -> PRODUCT -> SINK

con capacidades inferidas del historial. El flujo maximo es cuanta demanda
historica puede cubrir el abastecimiento; el min-cut marca el cuello de botella.
Refs: Dinic (1970); Ford & Fulkerson (1956).
"""

from __future__ import annotations

from collections import defaultdict, deque

import pandas as pd


class Dinic:
    """Max-flow de Dinic: BFS por niveles + DFS de flujo bloqueante."""

    def __init__(self) -> None:
        self.graph: dict[str, list[int]] = defaultdict(list)
        self.edges: list[list] = []  # [u, v, cap, flow]

    def add_edge(self, u: str, v: str, cap: float) -> None:
        self.graph[u].append(len(self.edges))
        self.edges.append([u, v, float(cap), 0.0])
        self.graph[v].append(len(self.edges))
        self.edges.append([v, u, 0.0, 0.0])  # arista residual

    def _bfs(self, source: str, sink: str) -> bool:
        self.level = {source: 0}
        queue = deque([source])
        while queue:
            u = queue.popleft()
            for ei in self.graph[u]:
                _, v, cap, flow = self.edges[ei]
                if v not in self.level and cap - flow > 1e-9:
                    self.level[v] = self.level[u] + 1
                    queue.append(v)
        return sink in self.level

    def _dfs(self, u: str, sink: str, pushed: float, it: dict[str, int]) -> float:
        if u == sink:
            return pushed
        while it[u] < len(self.graph[u]):
            ei = self.graph[u][it[u]]
            _, v, cap, flow = self.edges[ei]
            if cap - flow > 1e-9 and self.level.get(v, -1) == self.level[u] + 1:
                delta = self._dfs(v, sink, min(pushed, cap - flow), it)
                if delta > 1e-9:
                    self.edges[ei][3] += delta
                    self.edges[ei ^ 1][3] -= delta
                    return delta
            it[u] += 1
        return 0.0

    def max_flow(self, source: str, sink: str) -> float:
        flow = 0.0
        while self._bfs(source, sink):
            it = defaultdict(int)
            while True:
                pushed = self._dfs(source, sink, float("inf"), it)
                if pushed <= 1e-9:
                    break
                flow += pushed
        return flow

    def min_cut_reachable(self, source: str) -> set[str]:
        """Nodos alcanzables desde la fuente en el grafo residual (lado S del corte)."""
        seen = {source}
        queue = deque([source])
        while queue:
            u = queue.popleft()
            for ei in self.graph[u]:
                _, v, cap, flow = self.edges[ei]
                if v not in seen and cap - flow > 1e-9:
                    seen.add(v)
                    queue.append(v)
        return seen


def build_demand(sales: pd.DataFrame) -> dict[str, float]:
    """Demanda historica por producto = unidades activas vendidas."""
    data = sales
    if "is_active" in data.columns:
        data = data.loc[data["is_active"].astype(str).str.lower().isin({"true", "1"})]
    qty = pd.to_numeric(data["quantity"], errors="coerce").fillna(0)
    grouped = qty.groupby(data["product_id"].astype(str)).sum()
    return {pid: float(units) for pid, units in grouped.items() if units > 0}


def max_flow_min_cut(options: pd.DataFrame, demand: dict[str, float]) -> dict:
    """Flujo maximo de abastecimiento y cuello de botella (min-cut) con Dinic."""
    net = Dinic()
    labels = dict(zip(options["product_id"].astype(str), options["product_name"].astype(str)))
    supplier_labels = dict(zip(options["supplier_norm"].astype(str), options["supplier"].astype(str)))

    suppliers_added: set[str] = set()
    products_used: set[str] = set()
    for row in options.itertuples():
        pid = str(row.product_id)
        if pid not in demand:
            continue
        supplier_node = f"S:{row.supplier_norm}"
        product_node = f"P:{pid}"
        net.add_edge(supplier_node, product_node, float(row.capacity_units))
        products_used.add(pid)
        if row.supplier_norm not in suppliers_added:
            suppliers_added.add(str(row.supplier_norm))
            net.add_edge("SOURCE", supplier_node, float(row.supplier_capacity))

    for pid in products_used:
        net.add_edge(f"P:{pid}", "SINK", float(demand[pid]))

    total_demand = round(sum(demand[p] for p in products_used), 2)
    if not products_used:
        return {
            "max_flow": 0.0,
            "total_demand": 0.0,
            "min_cut_edges": pd.DataFrame(),
            "bottleneck_suppliers": pd.DataFrame(),
            "metrics": {"algorithm": "Dinic max-flow/min-cut", "note": "sin productos con demanda y oferta"},
        }

    flow = round(net.max_flow("SOURCE", "SINK"), 2)
    reachable = net.min_cut_reachable("SOURCE")

    cut_rows = []
    for u, v, cap, _ in net.edges:
        if cap <= 0:
            continue
        if u in reachable and v not in reachable:
            if u == "SOURCE":
                kind, frm, to = "SOURCE->SUPPLIER", "SOURCE", supplier_labels.get(v[2:], v)
            elif u.startswith("S:") and v.startswith("P:"):
                kind = "SUPPLIER->PRODUCT"
                frm, to = supplier_labels.get(u[2:], u), labels.get(v[2:], v)
            elif v == "SINK":
                kind, frm, to = "PRODUCT->SINK", labels.get(u[2:], u), "SINK"
            else:
                kind, frm, to = "otro", u, v
            cut_rows.append({"tipo": kind, "desde": frm, "hacia": to, "capacidad": round(cap, 2)})
    cut_edges = pd.DataFrame(cut_rows)

    bottleneck = pd.DataFrame()
    if not cut_edges.empty:
        suppliers_cut = cut_edges.loc[cut_edges["tipo"] == "SOURCE->SUPPLIER"]
        if not suppliers_cut.empty:
            bottleneck = (
                suppliers_cut.groupby("hacia", as_index=False)["capacidad"]
                .sum()
                .rename(columns={"hacia": "proveedor", "capacidad": "capacidad_saturada"})
                .sort_values("capacidad_saturada", ascending=False)
                .reset_index(drop=True)
            )

    return {
        "max_flow": flow,
        "total_demand": total_demand,
        "coverage_pct": round(flow / total_demand, 4) if total_demand else 0.0,
        "min_cut_edges": cut_edges,
        "bottleneck_suppliers": bottleneck,
        "metrics": {
            "algorithm": "Dinic max-flow/min-cut",
            "suppliers": len(suppliers_added),
            "products": len(products_used),
            "max_flow": flow,
            "total_demand": total_demand,
        },
    }


def supplier_dependency_table(purchases: pd.DataFrame) -> pd.DataFrame:
    """Baseline: % de dependencia por proveedor (reusa sales_reports)."""
    from .sales_reports import supplier_dependency

    return supplier_dependency(purchases)


def supplier_removal_impact(
    sales: pd.DataFrame, purchases: pd.DataFrame, supplier_norm: str
) -> dict:
    """Que productos y cuanto valor de ventas quedan en riesgo si se pierde un proveedor."""
    pur = purchases
    if "is_active" in pur.columns:
        pur = pur.loc[pur["is_active"].astype(str).str.lower().isin({"true", "1"})]

    suppliers_per_product = pur.groupby(pur["product_id"].astype(str))["supplier_norm"].nunique()
    affected = pur.loc[pur["supplier_norm"].astype(str) == str(supplier_norm)]
    if affected.empty:
        return {"lost_products": pd.DataFrame(), "affected_sales_value": 0.0, "single_source_products": pd.DataFrame()}

    affected_ids = sorted(set(affected["product_id"].astype(str)))

    sal = sales
    if "is_active" in sal.columns:
        sal = sal.loc[sal["is_active"].astype(str).str.lower().isin({"true", "1"})]
    sal = sal.copy()
    sal["analysis_total"] = pd.to_numeric(sal["analysis_total"], errors="coerce").fillna(0)
    sales_value = sal.loc[sal["product_id"].astype(str).isin(affected_ids)].groupby(
        sal["product_id"].astype(str)
    )["analysis_total"].sum()

    names = dict(zip(affected["product_id"].astype(str), affected["product_name"].astype(str)))
    rows = []
    for pid in affected_ids:
        n_suppliers = int(suppliers_per_product.get(pid, 1))
        rows.append(
            {
                "product_id": pid,
                "product_name": names.get(pid, ""),
                "n_proveedores": n_suppliers,
                "valor_ventas": round(float(sales_value.get(pid, 0.0)), 2),
                "fuente_unica": n_suppliers == 1,
            }
        )
    lost = pd.DataFrame(rows).sort_values("valor_ventas", ascending=False).reset_index(drop=True)
    return {
        "lost_products": lost,
        "affected_sales_value": round(float(lost["valor_ventas"].sum()), 2),
        "single_source_products": lost.loc[lost["fuente_unica"]].reset_index(drop=True),
    }
