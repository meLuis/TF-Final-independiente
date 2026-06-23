"""Seccion 2 - Perfil de cliente.

Baseline (curso): ranking de productos del cliente por monto / frecuencia.
Investigado: Personalized PageRank con reinicio en el nodo CLIENT sobre G_sales
(proximidad estructural multi-salto, no solo lo que ya le facturamos).
"""

from __future__ import annotations

from core.assistant_contract import AlgoVariant, AssistantResponse

from .aggregations import client_top_products, resolve_customer
from .loaders import load_pagerank, load_sales, tx_ready

INTENT = "perfil_cliente"


def engine_perfil_cliente(customer_text: str, k: int = 15) -> AssistantResponse:
    customer_text = (customer_text or "").strip()
    if not customer_text:
        return AssistantResponse.fail(INTENT, "Indica el cliente a analizar.")

    sales = load_sales()
    resolved = resolve_customer(sales, customer_text)
    if resolved is None:
        return AssistantResponse.fail(INTENT, f"No encontre al cliente '{customer_text}'.")
    customer_norm, label = resolved

    baseline_table = client_top_products(sales, customer_norm, k=k)
    if baseline_table.empty:
        return AssistantResponse.fail(INTENT, f"El cliente '{label}' no tiene ventas activas.")

    top3 = baseline_table.head(3)["product_name"].tolist()
    answer = (
        f"**{label}** compra principalmente: " + ", ".join(top3) + ".  \n"
        f"Monto total top {len(baseline_table)}: S/ {baseline_table['monto_total'].sum():,.2f}."
    )

    # Investigado: PPR con reinicio en el cliente sobre G_sales.
    ppr_table = None
    ppr_metrics: dict = {}
    if tx_ready():
        try:
            engine = load_pagerank("sales")
            client_node = f"CLIENT:{customer_norm}"
            if client_node in engine.node_type:
                rank = engine.pagerank(personalization={client_node: 1.0})
                ppr_table = engine.top_nodes(rank, {"PRODUCT"}, k=k)
                ppr_metrics = {"productos_rankeados": int(len(ppr_table))}
        except Exception:
            pass

    return AssistantResponse(
        intent=INTENT,
        answer=answer,
        entities={"cliente": label, "customer_norm": customer_norm},
        table=baseline_table,
        algorithm="Personalized PageRank (reinicio en CLIENT) sobre G_sales",
        baseline=AlgoVariant(
            name="Ranking por monto / frecuencia",
            role="baseline",
            table=baseline_table,
            metrics={"productos": int(len(baseline_table))},
            summary="Agregacion directa de lo facturado al cliente.",
        ),
        investigated=AlgoVariant(
            name="Personalized PageRank",
            role="investigado",
            table=ppr_table,
            metrics=ppr_metrics,
            summary="Reinicio en el cliente: pondera proximidad estructural multi-salto.",
        ),
        evidence=["G_sales (stage2_transaction_graphs)", "sales_clean.csv"],
        technical={"top_baseline": top3},
    )
