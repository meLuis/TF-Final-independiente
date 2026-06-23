"""Seccion 7 - Ofertas y descuentos (ahorros historicos).

Baseline (curso): costo de referencia por producto / orden topologico (el grafo
es un DAG, asi que el camino minimo se resuelve en O(V+E)).
Investigado: Bellman-Ford, porque admite pesos negativos (ahorros) y deja lista
la deteccion de ciclos negativos para cuando se carguen ofertas cruzadas.
"""

from __future__ import annotations

from core.assistant_contract import AlgoVariant, AssistantResponse

from .loaders import load_offers, stage1_ready

INTENT = "ofertas_descuentos"


def engine_ofertas_descuentos(top: int = 20) -> AssistantResponse:
    if not stage1_ready():
        return AssistantResponse.fail(INTENT, "Primero corre la Etapa 1 (purchases_clean.csv).")

    result = load_offers()
    summary = result.get("summary", {})
    if summary.get("status") != "ready":
        return AssistantResponse.fail(INTENT, summary.get("message", "Sin opciones de compra validas."))

    best_paths = result["best_paths"]
    savers = best_paths.loc[best_paths["has_negative_edge"]].head(top)
    main_table = (savers if not savers.empty else best_paths.head(top)).reset_index(drop=True)

    warnings: list[str] = []
    if summary.get("has_negative_cycle"):
        warnings.append(
            "Aparecio un ciclo negativo: alguna oferta genera ganancia artificial en el modelo; revisar."
        )

    if not savers.empty:
        top_row = savers.iloc[0]
        answer = (
            f"Mayor ahorro historico: **{top_row['product_name']}** con **{top_row['best_supplier']}** "
            f"(referencia S/ {top_row['reference_unit_cost']} -> efectivo S/ {top_row['effective_unit_cost']}, "
            f"ahorro {top_row['savings_pct'] * 100:.1f}%).  \n"
            f"{summary.get('products_with_savings', 0)} productos con ahorro frente a su referencia."
        )
    else:
        answer = "Ningun proveedor esta por debajo del costo de referencia de su producto."

    return AssistantResponse(
        intent=INTENT,
        answer=answer,
        table=main_table,
        algorithm="Bellman-Ford (admite pesos negativos; salvaguarda de ciclos)",
        warnings=warnings,
        baseline=AlgoVariant(
            name="Costo de referencia / orden topologico",
            role="baseline",
            metrics={"productos": summary.get("products_analyzed")},
            summary="El grafo es un DAG: el camino minimo bastaria con orden topologico O(V+E).",
        ),
        investigated=AlgoVariant(
            name="Bellman-Ford",
            role="investigado",
            table=main_table,
            metrics={
                "aristas_negativas": summary.get("negative_edges"),
                "productos_con_ahorro": summary.get("products_with_savings"),
                "ciclo_negativo": summary.get("has_negative_cycle"),
            },
            summary="Distancias del algoritmo (no un sort): correcto si las ofertas encadenan saltos.",
        ),
        evidence=["purchases_clean.csv (compras reales)"],
        technical=summary,
    )
