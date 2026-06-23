"""Seccion 3 - Cliente y abastecimiento.

Baseline (curso): join ventas+compras y ranking proveedor-producto.
Investigado: BFS bidireccional como camino explicativo cliente -> producto ->
proveedor sobre G_business, comparado honestamente contra BFS clasico.
"""

from __future__ import annotations

import pandas as pd

from core.assistant_contract import AlgoVariant, AssistantResponse

from .aggregations import client_top_products, product_top_suppliers, resolve_customer
from .loaders import load_paths, load_purchases, load_sales, tx_ready

INTENT = "cliente_abastecimiento"


def engine_cliente_abastecimiento(customer_text: str, k: int = 8) -> AssistantResponse:
    customer_text = (customer_text or "").strip()
    if not customer_text:
        return AssistantResponse.fail(INTENT, "Indica el cliente a analizar.")

    sales = load_sales()
    resolved = resolve_customer(sales, customer_text)
    if resolved is None:
        return AssistantResponse.fail(INTENT, f"No encontre al cliente '{customer_text}'.")
    customer_norm, label = resolved

    products = client_top_products(sales, customer_norm, k=k)
    if products.empty:
        return AssistantResponse.fail(INTENT, f"El cliente '{label}' no tiene ventas activas.")

    purchases = load_purchases()
    rows = []
    critical = None
    for product in products.itertuples():
        suppliers = product_top_suppliers(purchases, product.product_id, k=10)
        n_suppliers = int(len(suppliers))
        best = suppliers.iloc[0] if n_suppliers else None
        rows.append(
            {
                "producto": product.product_name,
                "mejor_proveedor": str(best["supplier"]) if best is not None else "sin compras",
                "costo_min": float(best["costo_min"]) if best is not None else None,
                "n_proveedores": n_suppliers,
                "critico": n_suppliers == 1,
            }
        )
        if critical is None and n_suppliers == 1:
            critical = product.product_name
    join_table = pd.DataFrame(rows)

    # Investigado: camino explicativo cliente -> ... -> proveedor (BFS bidireccional).
    invest_variant = None
    compare = {}
    path_table = None
    warnings: list[str] = []
    if tx_ready():
        target_supplier_norm = None
        for product in products.itertuples():
            suppliers = product_top_suppliers(purchases, product.product_id, k=1)
            if not suppliers.empty:
                target_supplier_norm = str(suppliers.iloc[0]["supplier_norm"])
                break
        if target_supplier_norm:
            graph = load_paths()
            compare = graph.compare(f"CLIENT:{customer_norm}", f"SUPPLIER:{target_supplier_norm}")
            if "error" not in compare:
                bidir = compare["bidirectional_bfs"]
                path_table = pd.DataFrame({"camino": bidir.get("path_labels", [])})
                invest_variant = AlgoVariant(
                    name="BFS bidireccional",
                    role="investigado",
                    table=path_table,
                    metrics={
                        "expandio_bfs": compare["bfs"]["expanded_nodes"],
                        "expandio_bidireccional": bidir["expanded_nodes"],
                        "ratio_mejora": compare["expansion_ratio"],
                    },
                    summary="Dos frentes que se encuentran: explica como se conecta el cliente con su proveedor.",
                )
            else:
                warnings.append("No se hallo un camino cliente -> proveedor en G_business.")

    answer = (
        f"**{label}** pide principalmente {', '.join(products.head(3)['product_name'])}.  \n"
        + (f"Producto critico (un solo proveedor): **{critical}**." if critical else
           "Ningun producto top depende de un unico proveedor.")
    )

    return AssistantResponse(
        intent=INTENT,
        answer=answer,
        entities={"cliente": label, "customer_norm": customer_norm},
        table=join_table,
        algorithm="BFS bidireccional (Pohl 1971) sobre G_business",
        warnings=warnings,
        baseline=AlgoVariant(
            name="Join ventas+compras + ranking",
            role="baseline",
            table=join_table,
            metrics={"productos": int(len(join_table))},
            summary="Que pide el cliente y a quien se le compra normalmente.",
        ),
        investigated=invest_variant,
        evidence=["G_business (stage2_transaction_graphs)", "sales_clean.csv", "purchases_clean.csv"],
        technical=compare,
    )
