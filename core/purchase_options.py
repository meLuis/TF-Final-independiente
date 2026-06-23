"""Etapa 4 - Opciones de compra SKU -> proveedor derivadas del historial.

Equivalente generalizado del G_opt del proyecto base: alli las opciones
(precio, tiempo, stock) venian de un dataset sintetico; aqui se **infieren
del historial limpio de compras** (Etapa 1), que es dato real:

- unit_cost: costo unitario minimo observado para (producto, proveedor).
- capacity_units: disponibilidad inferida = mayor cantidad comprada en una
  sola linea a ese proveedor (lo que demostro poder entregar de una vez).
- supplier_capacity: capacidad global inferida del proveedor = mayor volumen
  total despachado en un mismo dia (suma de lineas de ese dia).
- delivery_days: si existe data/base/proveedores.csv se usa su tiempo de
  entrega (dato SINTETICO, declarado en PROCEDENCIA.md); si no, default.

Complejidad: O(R) sobre las filas activas de compras + O(S) proveedores.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .text_utils import normalize_text


DEFAULT_DELIVERY_DAYS = 3


def build_supply_options(
    stage1_output_dir: str | Path,
    suppliers_csv: str | Path | None = None,
) -> pd.DataFrame:
    stage1_path = Path(stage1_output_dir)
    purchases = pd.read_csv(stage1_path / "purchases_clean.csv", encoding="utf-8-sig")
    if "is_active" in purchases.columns:
        purchases = purchases.loc[purchases["is_active"].astype(str).str.lower().isin({"true", "1"})]

    purchases = purchases.assign(
        quantity=pd.to_numeric(purchases["quantity"], errors="coerce"),
        unit_cost=pd.to_numeric(purchases["analysis_unit_cost"], errors="coerce"),
    )
    purchases = purchases.dropna(subset=["quantity", "unit_cost"])
    purchases = purchases.loc[(purchases["quantity"] > 0) & (purchases["unit_cost"] > 0)]

    options = (
        purchases.groupby(["product_id", "supplier_norm"], as_index=False)
        .agg(
            product_name=("product_name", "first"),
            supplier=("supplier", "first"),
            unit_cost=("unit_cost", "min"),
            avg_unit_cost=("unit_cost", "mean"),
            capacity_units=("quantity", "max"),
            purchase_lines=("quantity", "size"),
            last_purchase=("date", "max"),
        )
    )

    # Capacidad global inferida por proveedor: mayor despacho total en un dia.
    daily = (
        purchases.groupby(["supplier_norm", "date"])["quantity"].sum().reset_index()
        .groupby("supplier_norm")["quantity"].max()
        .rename("supplier_capacity")
    )
    options = options.merge(daily, on="supplier_norm", how="left")

    options["delivery_days"] = DEFAULT_DELIVERY_DAYS
    if suppliers_csv is not None and Path(suppliers_csv).exists():
        suppliers = pd.read_csv(suppliers_csv, encoding="utf-8-sig")
        suppliers["supplier_norm"] = suppliers["proveedor"].map(normalize_text)
        delivery = (
            suppliers.groupby("supplier_norm")["tiempo_entrega_dias"].min().rename("synthetic_delivery")
        )
        options = options.merge(delivery, on="supplier_norm", how="left")
        options["delivery_days"] = options["synthetic_delivery"].fillna(DEFAULT_DELIVERY_DAYS).astype(int)
        options = options.drop(columns=["synthetic_delivery"])

    options["unit_cost"] = options["unit_cost"].round(6)
    options["avg_unit_cost"] = options["avg_unit_cost"].round(6)
    options["product_id"] = options["product_id"].astype(str)
    return options
