"""Seccion 10 - Riesgo y dependencia de abastecimiento.

Baseline (curso): % de dependencia por proveedor + impacto al eliminar uno.
Investigado: Max-flow/Min-cut con Dinic (cuello de botella de abastecimiento) y
centralidad de Brandes (proveedor mas critico estructuralmente).
"""

from __future__ import annotations

from core.assistant_contract import AlgoVariant, AssistantResponse
from core.supply_flow_risk import build_demand, max_flow_min_cut, supplier_removal_impact

from .aggregations import resolve_supplier
from .loaders import (
    load_brandes,
    load_purchases,
    load_sales,
    load_supply_options,
    stage1_ready,
    tx_ready,
)
from core.sales_reports import supplier_dependency

INTENT = "riesgo_dependencia"


def engine_riesgo_dependencia(supplier_text: str | None = None) -> AssistantResponse:
    if not stage1_ready():
        return AssistantResponse.fail(INTENT, "Primero corre la Etapa 1.")

    purchases = load_purchases()
    sales = load_sales()
    dependency = supplier_dependency(purchases)

    # Investigado A: cuello de botella con Dinic.
    flow = max_flow_min_cut(load_supply_options(), build_demand(sales))
    flow_variant = AlgoVariant(
        name="Max-flow / Min-cut (Dinic)",
        role="investigado",
        table=flow["bottleneck_suppliers"] if not flow["bottleneck_suppliers"].empty else None,
        metrics={
            "flujo_maximo": flow["max_flow"],
            "demanda_total": flow["total_demand"],
            "cobertura": flow.get("coverage_pct"),
        },
        summary="El min-cut marca el cuello de botella: donde se satura el abastecimiento.",
    )

    # Investigado B: proveedor mas critico estructuralmente (Brandes).
    critical_supplier = None
    if tx_ready():
        try:
            brandes = load_brandes()
            suppliers_bc = brandes["betweenness"].loc[brandes["betweenness"]["node_type"] == "SUPPLIER"]
            if not suppliers_bc.empty:
                critical_supplier = suppliers_bc.iloc[0]["label"]
        except Exception:
            pass

    entities: dict = {}
    main_table = dependency
    extra = {}
    warnings: list[str] = []

    supplier_text = (supplier_text or "").strip()
    if supplier_text:
        resolved = resolve_supplier(purchases, supplier_text)
        if resolved is None:
            return AssistantResponse.fail(INTENT, f"No encontre al proveedor '{supplier_text}'.")
        supplier_norm, label = resolved
        impact = supplier_removal_impact(sales, purchases, supplier_norm)
        entities = {"proveedor": label, "supplier_norm": supplier_norm}
        main_table = impact["lost_products"]
        if not impact["single_source_products"].empty:
            extra["Productos de fuente unica (criticos)"] = impact["single_source_products"]
            warnings.append(
                f"{len(impact['single_source_products'])} productos dependen SOLO de {label}."
            )
        answer = (
            f"Si se pierde **{label}**: {len(main_table)} productos afectados y "
            f"S/ {impact['affected_sales_value']:,.2f} de ventas historicas en riesgo."
        )
    else:
        alerts = dependency.loc[dependency["alert"] != "ok"]
        if not alerts.empty:
            warnings.append(f"{len(alerts)} proveedores con concentracion MEDIA o ALTA.")
        bottleneck_txt = ""
        if not flow["bottleneck_suppliers"].empty:
            bottleneck_txt = f"Cuello de botella: {flow['bottleneck_suppliers'].iloc[0]['proveedor']}. "
        critical_txt = f"Proveedor mas critico (betweenness): {critical_supplier}." if critical_supplier else ""
        answer = (
            f"Cobertura de demanda: {flow.get('coverage_pct', 0)*100:.0f}% del historico. "
            f"{bottleneck_txt}{critical_txt}"
        )

    return AssistantResponse(
        intent=INTENT,
        answer=answer,
        entities=entities,
        table=main_table,
        algorithm="Dinic max-flow/min-cut + centralidad de Brandes",
        warnings=warnings,
        baseline=AlgoVariant(
            name="% de dependencia por proveedor",
            role="baseline",
            table=dependency,
            metrics={"proveedores": int(len(dependency))},
            summary="Concentracion de compras por proveedor (alerta ALTA/MEDIA).",
        ),
        investigated=flow_variant,
        evidence=["purchases_clean.csv", "sales_clean.csv", "G_business"],
        technical={
            "proveedor_mas_critico": critical_supplier,
            "min_cut": flow["min_cut_edges"],
            "max_flow_metrics": flow["metrics"],
        },
        extra_tables=extra,
    )
