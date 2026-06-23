from __future__ import annotations

from typing import Any

import pandas as pd


def _numeric(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype(str)
        .str.replace(r"[^\d,\.\-]", "", regex=True)
        .str.replace(",", ".", regex=False)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def _col(mapping: dict[str, Any], field: str) -> str | None:
    value = mapping.get(field, {})
    if isinstance(value, dict):
        return value.get("column")
    return value


def validate_amount_identity(
    df: pd.DataFrame,
    mapping: dict[str, Any],
    qty_field: str,
    unit_field: str,
    total_field: str,
    tolerance: float = 0.03,
) -> dict[str, Any]:
    qty_col = _col(mapping, qty_field)
    unit_col = _col(mapping, unit_field)
    total_col = _col(mapping, total_field)

    if not qty_col or not unit_col or not total_col:
        return {"available": False, "match_rate": None, "valid_rows": 0}

    qty = _numeric(df[qty_col])
    unit = _numeric(df[unit_col])
    total = _numeric(df[total_col])

    mask = qty.notna() & unit.notna() & total.notna() & (total.abs() > 0)
    valid_rows = int(mask.sum())
    if valid_rows == 0:
        return {"available": True, "match_rate": 0.0, "valid_rows": 0}

    expected = qty[mask] * unit[mask]
    diff = (expected - total[mask]).abs() / total[mask].abs()
    match_rate = float((diff <= tolerance).mean())

    return {
        "available": True,
        "match_rate": round(match_rate, 4),
        "valid_rows": valid_rows,
        "passes": match_rate >= 0.85,
    }


def validate_dataset(df: pd.DataFrame, mapping: dict[str, Any], dataset_type: str) -> dict[str, Any]:
    total_rows = int(len(df))
    required = {
        "products": ["product_id", "product_name"],
        "sales": ["date", "quantity"],
        "purchases": ["date", "supplier", "quantity"],
    }[dataset_type]

    mapped_required = [
        field
        for field in required
        if _col(mapping, field) is not None
    ]

    result: dict[str, Any] = {
        "total_rows": total_rows,
        "required_fields": required,
        "mapped_required_fields": mapped_required,
        "required_coverage": round(len(mapped_required) / max(len(required), 1), 4),
    }

    if dataset_type == "sales":
        result["net_amount_identity"] = validate_amount_identity(
            df, mapping, "quantity", "unit_price_net", "subtotal_net"
        )
        result["gross_amount_identity"] = validate_amount_identity(
            df, mapping, "quantity", "unit_price_gross", "total_gross"
        )
    elif dataset_type == "purchases":
        result["net_amount_identity"] = validate_amount_identity(
            df, mapping, "quantity", "unit_cost_net", "subtotal_net"
        )
        result["gross_amount_identity"] = validate_amount_identity(
            df, mapping, "quantity", "unit_cost_gross", "total_gross"
        )

    return result
