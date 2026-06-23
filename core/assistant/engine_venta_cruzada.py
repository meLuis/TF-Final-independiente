"""Seccion 9 - Venta cruzada y recomendacion.

Baseline (curso): co-ocurrencia directa (conteo de pares co-vendidos).
Investigado: reglas de asociacion lift/Apriori (prioriza por sorpresa estadistica)
+ Personalized PageRank para cercania estructural multi-salto.
"""

from __future__ import annotations

from core.assistant_contract import AlgoVariant, AssistantResponse
from core.association_rules import cooccurrence_for_product, rules_for_product

from .aggregations import resolve_product
from .loaders import load_assoc_rules, load_pagerank, load_products, load_sales, tx_ready

INTENT = "venta_cruzada"


def engine_venta_cruzada(product_text: str, k: int = 10) -> AssistantResponse:
    product_text = (product_text or "").strip()
    if not product_text:
        return AssistantResponse.fail(INTENT, "Indica el producto base de la recomendacion.")

    products = load_products()
    resolved = resolve_product(products, product_text)
    if resolved is None:
        return AssistantResponse.fail(INTENT, f"No encontre el producto '{product_text}'.")
    product_id, product_name = resolved

    sales = load_sales()
    labels = dict(zip(products["product_id"].astype(str), products["product_name"].astype(str)))

    baseline_table = cooccurrence_for_product(product_id, sales, k=k)
    rules_table = rules_for_product(product_id, load_assoc_rules(), labels, k=k)

    extra = {}
    if tx_ready():
        try:
            related = load_pagerank("business").related_products(f"PRODUCT:{product_id}", k=k)
            if not related.empty:
                extra["Cercania estructural (Personalized PageRank)"] = related
        except Exception:
            pass

    if rules_table is not None and not rules_table.empty:
        top = rules_table.iloc[0]
        answer = (
            f"Cuando se vende **{product_name}**, conviene ofrecer **{top['recomendado']}** "
            f"(lift {top['lift']}, confianza {top['confidence']*100:.0f}%)."
        )
        main_table = rules_table
    elif not baseline_table.empty:
        answer = f"**{product_name}** no genero reglas con lift suficiente; se muestra la co-venta directa."
        main_table = baseline_table
    else:
        return AssistantResponse.fail(
            INTENT, f"'{product_name}' no tiene suficientes co-ventas para recomendar."
        )

    return AssistantResponse(
        intent=INTENT,
        answer=answer,
        entities={"product_id": product_id, "producto": product_name},
        table=main_table,
        algorithm="Reglas de asociacion lift/Apriori + Personalized PageRank",
        baseline=AlgoVariant(
            name="Co-ocurrencia directa",
            role="baseline",
            table=baseline_table if not baseline_table.empty else None,
            metrics={"pares": int(len(baseline_table))},
            summary="Cuenta cuantas veces se vendieron juntos; premia best-sellers triviales.",
        ),
        investigated=AlgoVariant(
            name="Lift / Apriori",
            role="investigado",
            table=rules_table if rules_table is not None and not rules_table.empty else None,
            metrics={"reglas": 0 if rules_table is None else int(len(rules_table))},
            summary="Lift > 1: la pareja aparece mas de lo esperado por azar (recomendacion no trivial).",
        ),
        evidence=["sales_clean.csv (pseudo-documentos cliente+fecha)", "G_business"],
        technical={"producto": product_name},
        extra_tables=extra,
    )
