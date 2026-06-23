"""Agregaciones y resolucion de entidades compartidas por las secciones.

Funciones puras sobre DataFrames (sin Streamlit): resuelven texto del usuario a
ids reales (cliente, producto) y arman los rankings base (cliente->producto,
producto->proveedor) que son el "baseline del curso" de varias secciones.
"""

from __future__ import annotations

import pandas as pd

from ..text_utils import normalize_text


def _active(table: pd.DataFrame) -> pd.DataFrame:
    if "is_active" in table.columns:
        return table.loc[table["is_active"].astype(str).str.lower().isin({"true", "1"})]
    return table


def resolve_customer(sales: pd.DataFrame, text: str) -> tuple[str, str] | None:
    """Resuelve texto libre a (customer_norm, label legible). None si no hay match."""
    if not text:
        return None
    target = normalize_text(text)
    pairs = sales[["customer_norm", "customer"]].dropna().drop_duplicates()
    exact = pairs.loc[pairs["customer_norm"] == target]
    if not exact.empty:
        row = exact.iloc[0]
        return str(row["customer_norm"]), str(row["customer"])
    partial = pairs.loc[pairs["customer_norm"].str.contains(target, regex=False, na=False)]
    if not partial.empty:
        row = partial.iloc[0]
        return str(row["customer_norm"]), str(row["customer"])
    return None


def resolve_product(products: pd.DataFrame, text: str) -> tuple[str, str] | None:
    """Resuelve texto libre a (product_id, product_name). Acepta el id directo."""
    if not text:
        return None
    text = str(text).strip()
    by_id = products.loc[products["product_id"].astype(str) == text]
    if not by_id.empty:
        row = by_id.iloc[0]
        return str(row["product_id"]), str(row["product_name"])
    target = normalize_text(text)
    norm_col = products["product_name"].map(normalize_text)
    exact = products.loc[norm_col == target]
    if not exact.empty:
        row = exact.iloc[0]
        return str(row["product_id"]), str(row["product_name"])
    partial = products.loc[norm_col.str.contains(target, regex=False, na=False)]
    if not partial.empty:
        row = partial.iloc[0]
        return str(row["product_id"]), str(row["product_name"])
    # Subconjunto de tokens (orden libre): "gotero ambar 30ml" matchea aunque el
    # nombre real intercale otras palabras. Se elige el nombre mas corto (mas especifico).
    q_tokens = set(target.split())
    if q_tokens:
        mask = norm_col.map(lambda n: q_tokens.issubset(set(str(n).split())))
        candidates = products.loc[mask]
        if not candidates.empty:
            row = candidates.loc[candidates["product_name"].str.len().idxmin()]
            return str(row["product_id"]), str(row["product_name"])
    return None


def resolve_supplier(purchases: pd.DataFrame, text: str) -> tuple[str, str] | None:
    """Resuelve texto libre a (supplier_norm, label legible). None si no hay match."""
    if not text:
        return None
    target = normalize_text(text)
    pairs = purchases[["supplier_norm", "supplier"]].dropna().drop_duplicates()
    exact = pairs.loc[pairs["supplier_norm"] == target]
    if not exact.empty:
        row = exact.iloc[0]
        return str(row["supplier_norm"]), str(row["supplier"])
    partial = pairs.loc[pairs["supplier_norm"].str.contains(target, regex=False, na=False)]
    if not partial.empty:
        row = partial.iloc[0]
        return str(row["supplier_norm"]), str(row["supplier"])
    return None


def client_top_products(sales: pd.DataFrame, customer_norm: str, k: int = 15) -> pd.DataFrame:
    """Ranking baseline de productos de un cliente por monto/frecuencia."""
    data = _active(sales)
    data = data.loc[data["customer_norm"] == customer_norm].copy()
    if data.empty:
        return pd.DataFrame()
    data["analysis_total"] = pd.to_numeric(data["analysis_total"], errors="coerce").fillna(0)
    data["quantity"] = pd.to_numeric(data["quantity"], errors="coerce").fillna(0)
    ranking = (
        data.groupby(["product_id", "product_name"], as_index=False)
        .agg(
            monto_total=("analysis_total", "sum"),
            cantidad_total=("quantity", "sum"),
            docs=("date", "nunique"),
            ultima_compra=("date", "max"),
        )
        .sort_values("monto_total", ascending=False)
        .head(k)
        .reset_index(drop=True)
    )
    ranking["monto_total"] = ranking["monto_total"].round(2)
    return ranking


def product_top_suppliers(purchases: pd.DataFrame, product_id: str, k: int = 10) -> pd.DataFrame:
    """Ranking baseline de proveedores de un producto por precio/frecuencia."""
    data = _active(purchases)
    data = data.loc[data["product_id"].astype(str) == str(product_id)].copy()
    if data.empty:
        return pd.DataFrame()
    data["unit_cost"] = pd.to_numeric(data["analysis_unit_cost"], errors="coerce")
    data["quantity"] = pd.to_numeric(data["quantity"], errors="coerce").fillna(0)
    data = data.dropna(subset=["unit_cost"])
    ranking = (
        data.groupby(["supplier_norm", "supplier"], as_index=False)
        .agg(
            costo_min=("unit_cost", "min"),
            costo_prom=("unit_cost", "mean"),
            cantidad_total=("quantity", "sum"),
            lineas=("quantity", "size"),
            ultima_compra=("date", "max"),
        )
        .sort_values(["costo_min", "lineas"], ascending=[True, False])
        .head(k)
        .reset_index(drop=True)
    )
    ranking["costo_min"] = ranking["costo_min"].round(4)
    ranking["costo_prom"] = ranking["costo_prom"].round(4)
    return ranking
