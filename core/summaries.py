from __future__ import annotations

import re
from typing import Any

import pandas as pd


def _text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def classify_code_pattern(value: Any) -> str:
    text = _text(value).upper()
    if not text:
        return "EMPTY"
    if any(word in text for word in ("ANULADO", "CANCELADO", "QUITADO", "VOID", "DELETED")):
        return "HAS_CANCEL_KEYWORD"
    if re.fullmatch(r"\d+", text):
        if len(text) > 1 and text.startswith("0"):
            return f"LEADING_ZERO_NUM_{len(text)}"
        return f"NUM_{len(text)}_DIGITS"
    if re.fullmatch(r"[A-Z]+", text):
        return "ALPHA_ONLY"
    if "-" in text:
        return "ALPHANUM_WITH_DASH"
    if re.search(r"[A-Z]", text) and re.search(r"\d", text):
        return "ALPHANUM"
    return "OTHER"


def build_quality_summary(report: dict[str, Any]) -> pd.DataFrame:
    rows = [
        {"metric": "column_mapping_confidence", "value": report.get("column_mapping_confidence")},
        {"metric": "product_match_coverage", "value": report.get("product_match_coverage")},
        {"metric": "high_confidence_matches", "value": report.get("high_confidence_matches")},
        {"metric": "ambiguous_matches", "value": report.get("ambiguous_matches")},
        {"metric": "rejected_matches", "value": report.get("rejected_matches")},
        {"metric": "requires_human_review", "value": report.get("requires_human_review")},
    ]
    for dataset, count in report.get("row_counts", {}).items():
        rows.append({"metric": f"{dataset}_rows", "value": count})
    return pd.DataFrame(rows)


def build_transaction_flags_summary(cleaned: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for dataset in ("sales", "purchases"):
        df = cleaned.get(dataset, pd.DataFrame())
        if df.empty:
            continue
        rows.append(
            {
                "dataset": dataset,
                "rows": len(df),
                "active_rows": int(df.get("is_active", pd.Series(True, index=df.index)).sum()),
                "cancelled_rows": int(df.get("is_cancelled", pd.Series(False, index=df.index)).sum()),
                "adjustment_rows": int(df.get("is_adjustment", pd.Series(False, index=df.index)).sum()),
                "analysis_total_sum": float(pd.to_numeric(df.get("analysis_total", 0), errors="coerce").fillna(0).sum()),
            }
        )
    return pd.DataFrame(rows)


def build_product_activity_summary(cleaned: dict[str, pd.DataFrame]) -> pd.DataFrame:
    products = cleaned.get("products", pd.DataFrame()).copy()
    sales = cleaned.get("sales", pd.DataFrame()).copy()
    purchases = cleaned.get("purchases", pd.DataFrame()).copy()

    if products.empty or "product_id" not in products:
        return pd.DataFrame()

    products["product_id_key"] = products["product_id"].astype(str).str.strip()
    base_cols = ["product_id", "product_name"]
    for optional in ("software_category", "stock_available", "stock_available_raw", "stock_status"):
        if optional in products:
            base_cols.append(optional)
    summary = products[base_cols + ["product_id_key"]].copy()

    if not sales.empty and "product_id" in sales:
        sales_mask = sales["is_active"] if "is_active" in sales else pd.Series(True, index=sales.index)
        active_sales = sales[sales_mask].copy()
        active_sales["product_id_key"] = active_sales["product_id"].astype(str).str.strip()
        sales_agg = active_sales.groupby("product_id_key", dropna=False).agg(
            sales_rows=("product_id_key", "size"),
            sales_units=("quantity", "sum"),
            sales_total=("analysis_total", "sum"),
        )
        summary = summary.merge(sales_agg, on="product_id_key", how="left")

    if not purchases.empty and "product_id" in purchases:
        purchases_mask = purchases["is_active"] if "is_active" in purchases else pd.Series(True, index=purchases.index)
        active_purchases = purchases[purchases_mask].copy()
        active_purchases["product_id_key"] = active_purchases["product_id"].astype(str).str.strip()
        purchases_agg = active_purchases.groupby("product_id_key", dropna=False).agg(
            purchases_rows=("product_id_key", "size"),
            purchases_units=("quantity", "sum"),
            purchases_total=("analysis_total", "sum"),
        )
        summary = summary.merge(purchases_agg, on="product_id_key", how="left")

    numeric_cols = [
        "sales_rows",
        "sales_units",
        "sales_total",
        "purchases_rows",
        "purchases_units",
        "purchases_total",
    ]
    for col in numeric_cols:
        if col in summary:
            summary[col] = summary[col].fillna(0)

    summary["has_sales"] = summary.get("sales_rows", 0).astype(float) > 0
    summary["has_purchases"] = summary.get("purchases_rows", 0).astype(float) > 0
    return summary.drop(columns=["product_id_key"])


def build_code_pattern_summary(cleaned: dict[str, pd.DataFrame]) -> pd.DataFrame:
    activity = build_product_activity_summary(cleaned)
    if activity.empty or "product_id" not in activity:
        return pd.DataFrame()

    activity["code_pattern"] = activity["product_id"].map(classify_code_pattern)
    grouped = activity.groupby("code_pattern", dropna=False).agg(
        products=("product_id", "size"),
        products_with_sales=("has_sales", "sum"),
        products_with_purchases=("has_purchases", "sum"),
        sales_total=("sales_total", "sum"),
        purchases_total=("purchases_total", "sum"),
    )
    grouped = grouped.reset_index()
    total_sales = max(float(grouped["sales_total"].sum()), 1.0)
    total_purchases = max(float(grouped["purchases_total"].sum()), 1.0)
    grouped["sales_total_share"] = grouped["sales_total"] / total_sales
    grouped["purchases_total_share"] = grouped["purchases_total"] / total_purchases
    grouped["suggested_interpretation"] = "review"
    grouped.loc[grouped["sales_total_share"] >= 0.95, "suggested_interpretation"] = "dominant_commercial_pattern"
    grouped.loc[
        (grouped["products_with_sales"] == 0) & (grouped["products_with_purchases"] == 0),
        "suggested_interpretation",
    ] = "inactive_pattern"
    grouped.loc[
        grouped["code_pattern"].eq("HAS_CANCEL_KEYWORD"),
        "suggested_interpretation",
    ] = "cancel_or_adjustment_pattern"
    return grouped.sort_values(["sales_total_share", "purchases_total_share"], ascending=False)


def build_summary_tables(cleaned: dict[str, pd.DataFrame], report: dict[str, Any]) -> dict[str, pd.DataFrame]:
    return {
        "quality_summary": build_quality_summary(report),
        "transaction_flags_summary": build_transaction_flags_summary(cleaned),
        "product_activity_summary": build_product_activity_summary(cleaned),
        "code_pattern_summary": build_code_pattern_summary(cleaned),
    }
