"""Seccion 4 - Proveedor conveniente.

Baseline (curso): ranking multicriterio por precio minimo / grado.
Investigado: centralidad de intermediacion de Brandes sobre G_business como señal
de confiabilidad/criticidad estructural del proveedor (no solo precio).
"""

from __future__ import annotations

from core.assistant_contract import AlgoVariant, AssistantResponse

from .aggregations import product_top_suppliers, resolve_product
from .loaders import load_brandes, load_products, load_purchases, tx_ready

INTENT = "proveedor_conveniente"


def engine_proveedor_conveniente(product_text: str, k: int = 10) -> AssistantResponse:
    product_text = (product_text or "").strip()
    if not product_text:
        return AssistantResponse.fail(INTENT, "Indica el producto a abastecer.")

    resolved = resolve_product(load_products(), product_text)
    if resolved is None:
        return AssistantResponse.fail(INTENT, f"No encontre el producto '{product_text}'.")
    product_id, product_name = resolved

    ranking = product_top_suppliers(load_purchases(), product_id, k=k)
    if ranking.empty:
        return AssistantResponse.fail(INTENT, f"'{product_name}' no tiene compras registradas.")

    # Investigado: anotar el betweenness de cada proveedor del producto.
    betweenness_variant = None
    if tx_ready():
        try:
            brandes = load_brandes()
            scores = brandes["betweenness_scores"]
            ranking = ranking.assign(
                betweenness=ranking["supplier_norm"].map(
                    lambda norm: scores.get(f"SUPPLIER:{norm}", 0.0)
                )
            )
            most_critical = brandes["betweenness"].loc[brandes["betweenness"]["node_type"] == "SUPPLIER"]
            betweenness_variant = AlgoVariant(
                name="Betweenness (Brandes)",
                role="investigado",
                table=most_critical.reset_index(drop=True),
                metrics={"proveedores_evaluados": int(len(scores))},
                summary="Proveedores 'puente': por cuantos caminos minimos pasan en G_business.",
            )
        except Exception:
            pass

    best = ranking.iloc[0]
    answer = (
        f"Para **{product_name}**, el proveedor mas conveniente por precio es **{best['supplier']}** "
        f"(costo min S/ {best['costo_min']}, {int(best['lineas'])} compras).  \n"
        "El betweenness añade la lectura estructural: un proveedor puente es mas critico de perder."
    )

    return AssistantResponse(
        intent=INTENT,
        answer=answer,
        entities={"product_id": product_id, "producto": product_name},
        table=ranking,
        algorithm="Centralidad de intermediacion de Brandes + ranking multicriterio",
        baseline=AlgoVariant(
            name="Ranking por precio minimo / frecuencia",
            role="baseline",
            table=ranking,
            metrics={"proveedores": int(len(ranking))},
            summary="Elegir proveedor de un SKU es un ranking, no un camino: no se usa Dijkstra.",
        ),
        investigated=betweenness_variant,
        evidence=["purchases_clean.csv", "G_business (stage2_transaction_graphs)"],
        technical={"mejor_precio": best["supplier"]},
    )
