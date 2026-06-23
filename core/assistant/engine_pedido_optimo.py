"""Seccion 5 - Pedido optimo multi-SKU.

Baseline (curso): greedy por SKU (cada producto se resuelve por separado).
Investigado: min-cost flow (asigna el pedido completo respetando todas las
capacidades a la vez).
"""

from __future__ import annotations

import pandas as pd

from core.assistant_contract import AlgoVariant, AssistantResponse
from core.optimization_flow import compare_with_baseline

from .loaders import load_supply_options

INTENT = "pedido_optimo"


def _baseline_rows(baseline: dict) -> pd.DataFrame:
    rows = []
    for product_id, plan in baseline.get("plans", {}).items():
        for item in plan["plan"]:
            rows.append(
                {
                    "product_id": product_id,
                    "supplier": item["supplier"],
                    "units": item["units"],
                    "unit_cost": item["unit_cost"],
                    "subtotal": item["subtotal"],
                }
            )
    return pd.DataFrame(rows)


def engine_pedido_optimo(order: dict[str, float]) -> AssistantResponse:
    order = {str(k): float(v) for k, v in (order or {}).items() if float(v) > 0}
    if not order:
        return AssistantResponse.fail(INTENT, "Arma un pedido con al menos un producto y cantidad.")

    options = load_supply_options()
    result = compare_with_baseline(options, order)
    flow = result["min_cost_flow"]
    base = result["baseline_per_sku"]

    flow_table = pd.DataFrame(flow["plan"]) if flow["plan"] else None

    warnings: list[str] = []
    for supplier, info in result["baseline_capacity_violations"].items():
        warnings.append(
            f"El baseline asigna {info['assigned']} a {supplier} > capacidad {info['capacity']} (infactible)."
        )

    answer = (
        f"**Plan optimo:** costo S/ {flow['total_cost']:,.2f}, "
        f"{flow['units_assigned']:.0f} unidades asignadas, "
        f"{flow['units_unfilled']:.0f} sin cubrir.  \n"
        + (f"El baseline parecia costar S/ {base['total_cost']:,.2f} (delta S/ {result['cost_delta']:,.2f}), "
           "pero violaba capacidad de proveedor." if warnings else
           f"Coincide con el baseline factible (delta S/ {result['cost_delta']:,.2f}).")
    )

    return AssistantResponse(
        intent=INTENT,
        answer=answer,
        entities={"pedido": order},
        table=flow_table,
        algorithm="Min-cost flow (successive shortest paths + potenciales de Johnson)",
        warnings=warnings,
        baseline=AlgoVariant(
            name="Greedy por SKU",
            role="baseline",
            table=_baseline_rows(base),
            metrics={"costo": base["total_cost"], "sin_cubrir": base["units_unfilled"]},
            summary="Optimiza cada SKU por separado; ignora la capacidad global del proveedor.",
        ),
        investigated=AlgoVariant(
            name="Min-cost flow",
            role="investigado",
            table=flow_table,
            metrics={
                "costo": flow["total_cost"],
                "sin_cubrir": flow["units_unfilled"],
                "caminos_aumentantes": flow["augmenting_paths"],
            },
            summary="Asigna el pedido completo respetando todas las capacidades; siempre factible.",
        ),
        evidence=["purchase_options (inferido de purchases_clean.csv)", "proveedores.csv (SLA sintetico)"],
        technical={"cost_delta": result["cost_delta"], "baseline_is_feasible": result["baseline_is_feasible"]},
    )
