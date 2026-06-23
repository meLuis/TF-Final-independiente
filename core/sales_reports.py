"""Etapa 5 - Reportes de ventas: analisis ABC y co-venta.

Soporte clasico del reporte ejecutivo (complementa Leiden y PageRank):

- Analisis ABC (regla de Pareto): clase A ~80% del valor acumulado, B el
  siguiente 15%, C el 5% restante. O(n log n) por el ordenamiento.
- Co-venta: pares de productos vendidos en el mismo documento (pseudo-doc =
  cliente + fecha, ver core/transaction_graphs.py). O(sum_d lineas_d^2).
- Dependencia de proveedor: % de lineas de compra concentradas por proveedor.
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from pathlib import Path

import pandas as pd


def _active(table: pd.DataFrame) -> pd.DataFrame:
    if "is_active" in table.columns:
        return table.loc[table["is_active"].astype(str).str.lower().isin({"true", "1"})]
    return table


def abc_analysis(sales: pd.DataFrame) -> pd.DataFrame:
    """Clasifica productos por participacion acumulada en el valor vendido."""
    data = _active(sales).copy()
    data["analysis_total"] = pd.to_numeric(data["analysis_total"], errors="coerce").fillna(0)
    summary = (
        data.groupby(["product_id", "product_name"], as_index=False)
        .agg(total_value=("analysis_total", "sum"), sale_lines=("analysis_total", "size"))
        .sort_values("total_value", ascending=False)
        .reset_index(drop=True)
    )
    total = summary["total_value"].sum()
    summary["value_share"] = (summary["total_value"] / total).round(6) if total else 0.0
    summary["cumulative_share"] = summary["value_share"].cumsum().round(6)
    summary["abc_class"] = summary["cumulative_share"].map(
        lambda share: "A" if share <= 0.80 else ("B" if share <= 0.95 else "C")
    )
    return summary


def co_sales(sales: pd.DataFrame, top_k: int = 50) -> pd.DataFrame:
    """Pares de productos vendidos juntos (mismo cliente, mismo dia)."""
    data = _active(sales)
    pair_counter: Counter[tuple[str, str]] = Counter()
    names: dict[str, str] = {}
    for _, group in data.groupby(["customer_norm", "date"]):
        products = sorted(set(zip(group["product_id"].astype(str), group["product_name"])))
        for (id_a, name_a), (id_b, name_b) in combinations(products, 2):
            pair_counter[(id_a, id_b)] += 1
            names[id_a] = name_a
            names[id_b] = name_b
    rows = [
        {
            "product_a": id_a,
            "product_a_name": names[id_a],
            "product_b": id_b,
            "product_b_name": names[id_b],
            "co_sale_docs": count,
        }
        for (id_a, id_b), count in pair_counter.most_common(top_k)
    ]
    return pd.DataFrame(rows)


def supplier_dependency(purchases: pd.DataFrame) -> pd.DataFrame:
    """Concentracion de compras por proveedor (alerta de dependencia)."""
    data = _active(purchases).copy()
    data["analysis_total"] = pd.to_numeric(data["analysis_total"], errors="coerce").fillna(0)
    summary = (
        data.groupby("supplier", as_index=False)
        .agg(purchase_lines=("supplier", "size"), total_value=("analysis_total", "sum"))
        .sort_values("total_value", ascending=False)
        .reset_index(drop=True)
    )
    total_lines = summary["purchase_lines"].sum()
    total_value = summary["total_value"].sum()
    summary["line_share"] = (summary["purchase_lines"] / total_lines).round(4) if total_lines else 0.0
    summary["value_share"] = (summary["total_value"] / total_value).round(4) if total_value else 0.0
    summary["alert"] = summary["value_share"].map(
        lambda share: "ALTA" if share > 0.30 else ("MEDIA" if share > 0.15 else "ok")
    )
    return summary


def run_sales_reports(stage1_output_dir: str | Path) -> dict[str, pd.DataFrame]:
    stage1_path = Path(stage1_output_dir)
    sales = pd.read_csv(stage1_path / "sales_clean.csv", encoding="utf-8-sig")
    purchases = pd.read_csv(stage1_path / "purchases_clean.csv", encoding="utf-8-sig")
    return {
        "abc": abc_analysis(sales),
        "co_sales": co_sales(sales),
        "supplier_dependency": supplier_dependency(purchases),
    }
