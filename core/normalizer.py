from __future__ import annotations

from typing import Any

import pandas as pd

from .text_utils import normalize_text


CANCEL_KEYWORDS = (
    "ANULADO",
    "ANULADA",
    "CANCELADO",
    "CANCELADA",
    "QUITADO",
    "QUITADA",
    "VOID",
    "DELETED",
)
ADJUSTMENT_KEYWORDS = (
    "AJUSTE",
    "AJUSTES",
    "REGULARIZACION",
    "REGULARIZACIÓN",
    "ANULADO",
    "ANULADA",
    "CANCELADO",
    "CANCELADA",
)


def _mapped_column(mapping: dict[str, Any], field: str) -> str | None:
    value = mapping.get(field, {})
    if isinstance(value, dict):
        return value.get("column")
    return value


def parse_number(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype(str)
        .str.replace(r"[^\d,\.\-]", "", regex=True)
        .str.replace(",", ".", regex=False)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def _contains_keywords(series: pd.Series, keywords: tuple[str, ...]) -> pd.Series:
    normalized = series.fillna("").astype(str).map(normalize_text)
    pattern = "|".join(keywords)
    return normalized.str.contains(pattern, regex=True, na=False)


def _truthy_cancelled(series: pd.Series) -> pd.Series:
    normalized = series.fillna("").astype(str).map(normalize_text)
    return normalized.isin({"SI", "S", "YES", "TRUE", "1", "ANULADO", "CANCELADO"})


def normalize_dataset(
    df: pd.DataFrame,
    mapping: dict[str, Any],
    dataset_type: str,
) -> pd.DataFrame:
    output = pd.DataFrame(index=df.index)

    for field, candidate in mapping.items():
        column = candidate.get("column") if isinstance(candidate, dict) else candidate
        if column and column in df.columns:
            output[field] = df[column]

    for field in ("date",):
        if field in output:
            output[field] = pd.to_datetime(output[field], errors="coerce", dayfirst=True).dt.date.astype("string")

    for field in (
        "quantity",
        "unit_price_net",
        "unit_price_gross",
        "unit_cost_net",
        "unit_cost_gross",
        "subtotal_net",
        "tax_amount",
        "total_gross",
        "current_price",
        "stock_available",
    ):
        if field in output:
            output[field] = parse_number(output[field])

    for field in (
        "product_id",
        "product_name",
        "supplier",
        "customer",
        "software_category",
        "brand",
        "unit",
        "description",
        "is_cancelled",
    ):
        if field in output:
            output[field] = output[field].astype("string").str.strip()

    if dataset_type == "products":
        if "stock_available" in output:
            raw_stock = parse_number(output["stock_available"])
            output["stock_available_raw"] = raw_stock
            output["stock_available"] = raw_stock.clip(lower=0)
            output["stock_status"] = "positive"
            output.loc[raw_stock.fillna(0) == 0, "stock_status"] = "zero"
            output.loc[raw_stock < 0, "stock_status"] = "negative_raw_clipped"
        if "software_category" in output:
            category_norm = output["software_category"].fillna("").astype(str).map(normalize_text)
            low_conf = category_norm.isin({"", "-", "SIN CATEGORIA", "SIN CATEGORÍA"})
            output["software_category_confidence"] = "normal"
            output.loc[low_conf, "software_category_confidence"] = "low"
        output["is_commercial_product"] = True

    if dataset_type in {"sales", "purchases"}:
        if "is_cancelled" in output:
            explicit_cancelled = _truthy_cancelled(output["is_cancelled"])
            output["is_cancelled_source"] = output["is_cancelled"]
        else:
            explicit_cancelled = pd.Series(False, index=output.index)

        searchable = pd.Series("", index=output.index, dtype="string")
        for field in ("product_id", "product_name", "description"):
            if field in output:
                searchable = searchable.fillna("") + " " + output[field].fillna("").astype(str)

        keyword_cancelled = _contains_keywords(searchable, CANCEL_KEYWORDS)
        keyword_adjustment = _contains_keywords(searchable, ADJUSTMENT_KEYWORDS)

        output["is_cancelled"] = explicit_cancelled | keyword_cancelled
        output["is_adjustment"] = keyword_adjustment
        output["is_active"] = ~(output["is_cancelled"] | output["is_adjustment"])

        if dataset_type == "sales":
            if "unit_price_gross" in output:
                output["analysis_unit_price"] = output["unit_price_gross"]
            elif "unit_price_net" in output:
                output["analysis_unit_price"] = output["unit_price_net"]
            if "total_gross" in output:
                output["analysis_total"] = output["total_gross"]
            elif "subtotal_net" in output:
                output["analysis_total"] = output["subtotal_net"]
        if dataset_type == "purchases":
            if "unit_cost_gross" in output:
                output["analysis_unit_cost"] = output["unit_cost_gross"]
            elif "unit_cost_net" in output:
                output["analysis_unit_cost"] = output["unit_cost_net"]
            if "total_gross" in output:
                output["analysis_total"] = output["total_gross"]
            elif "subtotal_net" in output:
                output["analysis_total"] = output["subtotal_net"]

    if "product_name" in output:
        output["product_name_norm"] = output["product_name"].map(normalize_text)
    if "supplier" in output:
        output["supplier_norm"] = output["supplier"].map(normalize_text)
    if "customer" in output:
        output["customer_norm"] = output["customer"].map(normalize_text)

    output["source_dataset"] = dataset_type
    return output


def normalize_all(
    dataframes: dict[str, pd.DataFrame],
    mappings: dict[str, dict[str, Any]],
) -> dict[str, pd.DataFrame]:
    return {
        dataset_type: normalize_dataset(dataframes[dataset_type], mappings[dataset_type], dataset_type)
        for dataset_type in ("products", "sales", "purchases")
    }
