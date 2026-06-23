"""Seccion 6 - Presupuesto y mochila.

Baseline (curso): greedy por costo unitario (toma lotes baratos hasta agotar).
Investigado: Knapsack 0/1 por programacion dinamica (maximiza unidades dentro
del presupuesto). El mismo motor cae al greedy si el presupuesto excede el limite
de memoria del DP; eso se reporta en 'method'.
"""

from __future__ import annotations

import pandas as pd

from core.assistant_contract import AlgoVariant, AssistantResponse
from core.optimization_baseline import knapsack_budget

from .loaders import load_supply_options

INTENT = "presupuesto_mochila"


def engine_presupuesto_mochila(order: dict[str, float], budget: float) -> AssistantResponse:
    order = {str(k): float(v) for k, v in (order or {}).items() if float(v) > 0}
    budget = float(budget or 0)
    if not order:
        return AssistantResponse.fail(INTENT, "Elige al menos un producto candidato.")
    if budget <= 0:
        return AssistantResponse.fail(INTENT, "Indica un presupuesto mayor a 0.")

    options = load_supply_options()
    invest = knapsack_budget(options, order, budget)
    # Mismo motor, forzando el fallback greedy => baseline comparable.
    base = knapsack_budget(options, order, budget, dp_budget_limit=0.0)

    invest_table = pd.DataFrame(invest["plan"]) if invest["plan"] else None
    base_table = pd.DataFrame(base["plan"]) if base["plan"] else None

    warnings: list[str] = []
    if invest["method"] != "knapsack_dp":
        warnings.append(
            "El presupuesto supera el limite del DP exacto; se uso el fallback greedy "
            "(mismo resultado que el baseline)."
        )

    answer = (
        f"Con S/ {budget:,.2f} puedes comprar **{invest['total_units']:.0f} unidades** "
        f"(costo S/ {invest['total_cost']:,.2f}, sobrante S/ {invest['budget_left']:,.2f}).  \n"
        f"El DP gana {invest['total_units'] - base['total_units']:.0f} unidades sobre el greedy."
    )

    return AssistantResponse(
        intent=INTENT,
        answer=answer,
        entities={"pedido": order, "presupuesto": budget},
        table=invest_table,
        algorithm="Knapsack 0/1 por programacion dinamica",
        warnings=warnings,
        baseline=AlgoVariant(
            name="Greedy por costo unitario",
            role="baseline",
            table=base_table,
            metrics={"unidades": base["total_units"], "costo": base["total_cost"]},
            summary="Toma lotes baratos hasta agotar; no garantiza el optimo.",
        ),
        investigated=AlgoVariant(
            name=f"Knapsack DP ({invest['method']})",
            role="investigado",
            table=invest_table,
            metrics={
                "unidades": invest["total_units"],
                "costo": invest["total_cost"],
                "sobrante": invest["budget_left"],
            },
            summary="Maximiza unidades dentro del presupuesto (optimo exacto bajo el limite del DP).",
        ),
        evidence=["purchase_options (inferido de purchases_clean.csv)"],
        technical={"method": invest["method"]},
    )
