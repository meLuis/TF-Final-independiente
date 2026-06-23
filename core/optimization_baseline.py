"""Etapa 4 - Algoritmos BASELINE de optimizacion de compras.

Portados del proyecto base (streamlit_app/motor/optimizacion.py) y
generalizados sobre las opciones inferidas del historial
(core/purchase_options.py). **No se eliminan**: son la linea base contra la
que se mide el min-cost flow (core/optimization_flow.py); la comparativa
"antes vs ahora" se documenta en docs/ALGORITMOS_EVOLUCION.md.

Limitacion conocida (y razon de ser del min-cost flow): estos algoritmos
optimizan cada SKU **por separado**. Cuando varios SKUs compiten por la
capacidad del mismo proveedor barato, la asignacion por-SKU puede ser
suboptima o infactible a nivel global.
"""

from __future__ import annotations

import heapq
from typing import Any

import pandas as pd


def _options_for(options: pd.DataFrame, product_id: str) -> pd.DataFrame:
    return options.loc[options["product_id"] == str(product_id)]


def cheapest_split(options: pd.DataFrame, product_id: str, quantity: float) -> dict[str, Any]:
    """Minimo costo para un SKU con split de capacidad (heap de precios).

    Equivale al 'dijkstra_precio' del proyecto base: pop del proveedor mas
    barato, asignar min(capacidad, pendiente) y seguir con el siguiente.
    Complejidad: O(n log n) con n proveedores del SKU.
    """
    rows = _options_for(options, product_id)
    heap = [
        (float(row.unit_cost), str(row.supplier), float(row.capacity_units), int(row.delivery_days))
        for row in rows.itertuples()
    ]
    heapq.heapify(heap)

    remaining = float(quantity)
    plan: list[dict[str, Any]] = []
    while heap and remaining > 0:
        unit_cost, supplier, capacity, delivery = heapq.heappop(heap)
        units = min(capacity, remaining)
        plan.append(
            {
                "supplier": supplier,
                "unit_cost": unit_cost,
                "units": units,
                "subtotal": round(units * unit_cost, 2),
                "delivery_days": delivery,
            }
        )
        remaining -= units

    return {
        "product_id": str(product_id),
        "criterion": "precio",
        "plan": plan,
        "total_cost": round(sum(item["subtotal"] for item in plan), 2),
        "units_assigned": float(quantity) - remaining,
        "units_unfilled": max(remaining, 0.0),
    }


def greedy_time(options: pd.DataFrame, product_id: str, quantity: float) -> dict[str, Any]:
    """Minimo tiempo de entrega (greedy: ordenar por tiempo, desempate precio).

    Complejidad: O(n log n).
    """
    rows = _options_for(options, product_id).sort_values(["delivery_days", "unit_cost"])
    remaining = float(quantity)
    plan: list[dict[str, Any]] = []
    for row in rows.itertuples():
        if remaining <= 0:
            break
        units = min(float(row.capacity_units), remaining)
        plan.append(
            {
                "supplier": str(row.supplier),
                "unit_cost": float(row.unit_cost),
                "units": units,
                "subtotal": round(units * float(row.unit_cost), 2),
                "delivery_days": int(row.delivery_days),
            }
        )
        remaining -= units

    return {
        "product_id": str(product_id),
        "criterion": "tiempo",
        "plan": plan,
        "total_cost": round(sum(item["subtotal"] for item in plan), 2),
        "max_delivery_days": max((item["delivery_days"] for item in plan), default=None),
        "units_assigned": float(quantity) - remaining,
        "units_unfilled": max(remaining, 0.0),
    }


def knapsack_budget(
    options: pd.DataFrame,
    order: dict[str, float],
    budget: float,
    dp_budget_limit: float = 5000.0,
) -> dict[str, Any]:
    """Maximizar unidades compradas con presupuesto fijo (Knapsack DP 0/1).

    Cada item es un lote (SKU, proveedor) = min(capacidad, cantidad pedida).
    DP sobre el presupuesto en centavos: O(n * W) con W = presupuesto x 100.
    Si el presupuesto excede dp_budget_limit se usa el fallback greedy
    O(n log n) (mismo criterio del proyecto base para acotar memoria).
    """
    items: list[dict[str, Any]] = []
    for product_id, quantity in order.items():
        for row in _options_for(options, product_id).itertuples():
            units = min(float(row.capacity_units), float(quantity))
            if units <= 0:
                continue
            cost = units * float(row.unit_cost)
            items.append(
                {
                    "product_id": str(product_id),
                    "supplier": str(row.supplier),
                    "units": units,
                    "unit_cost": float(row.unit_cost),
                    "cost": cost,
                }
            )

    if budget > dp_budget_limit:
        return _greedy_budget(items, budget)

    capacity_cents = int(round(budget * 100))
    costs = [min(int(round(item["cost"] * 100)), capacity_cents + 1) for item in items]
    values = [item["units"] for item in items]

    dp = [0.0] * (capacity_cents + 1)
    keep = [[False] * (capacity_cents + 1) for _ in items]
    for i, (cost_cents, value) in enumerate(zip(costs, values)):
        for w in range(capacity_cents, cost_cents - 1, -1):
            candidate = dp[w - cost_cents] + value
            if candidate > dp[w]:
                dp[w] = candidate
                keep[i][w] = True

    chosen: list[dict[str, Any]] = []
    w = capacity_cents
    for i in range(len(items) - 1, -1, -1):
        if keep[i][w]:
            chosen.append(items[i])
            w -= costs[i]
    chosen.reverse()

    total_cost = sum(item["cost"] for item in chosen)
    return {
        "criterion": "presupuesto",
        "method": "knapsack_dp",
        "plan": chosen,
        "total_units": round(sum(item["units"] for item in chosen), 2),
        "total_cost": round(total_cost, 2),
        "budget_left": round(budget - total_cost, 2),
    }


def _greedy_budget(items: list[dict[str, Any]], budget: float) -> dict[str, Any]:
    """Fallback greedy por menor costo unitario. O(n log n)."""
    chosen: list[dict[str, Any]] = []
    left = budget
    for item in sorted(items, key=lambda it: it["unit_cost"]):
        if item["cost"] <= left:
            chosen.append(item)
            left -= item["cost"]
    return {
        "criterion": "presupuesto",
        "method": "greedy_fallback",
        "plan": chosen,
        "total_units": round(sum(item["units"] for item in chosen), 2),
        "total_cost": round(budget - left, 2),
        "budget_left": round(left, 2),
    }


def per_sku_order(options: pd.DataFrame, order: dict[str, float]) -> dict[str, Any]:
    """Plan multi-SKU resolviendo cada SKU por separado (la practica 'antes').

    Ignora que dos SKUs pueden agotar la capacidad global del mismo proveedor:
    esa es la limitacion que el min-cost flow corrige.
    """
    plans = {product_id: cheapest_split(options, product_id, qty) for product_id, qty in order.items()}
    return {
        "method": "per_sku_cheapest",
        "plans": plans,
        "total_cost": round(sum(plan["total_cost"] for plan in plans.values()), 2),
        "units_unfilled": round(sum(plan["units_unfilled"] for plan in plans.values()), 2),
    }
