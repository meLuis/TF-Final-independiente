from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import pandas as pd

from .text_utils import normalize_column_name, similarity


CANONICAL_FIELDS = {
    "products": [
        "product_id",
        "product_name",
        "software_category",
        "brand",
        "unit",
        "description",
        "current_price",
        "stock_available",
    ],
    "sales": [
        "sale_id",
        "date",
        "product_id",
        "product_name",
        "customer",
        "quantity",
        "unit_price_net",
        "unit_price_gross",
        "subtotal_net",
        "tax_amount",
        "total_gross",
        "is_cancelled",
    ],
    "purchases": [
        "purchase_id",
        "date",
        "product_id",
        "product_name",
        "supplier",
        "quantity",
        "unit_cost_net",
        "unit_cost_gross",
        "subtotal_net",
        "tax_amount",
        "total_gross",
    ],
}


ALIASES = {
    "date": ["fecha", "fec", "fecdoc", "fecha_doc", "fecha_emision", "fecha_compra", "date", "created_at"],
    "product_id": ["sku", "codigo", "cod", "coditem", "cod_art", "codigo_interno", "id_producto", "codigo_producto", "item"],
    "product_name": ["producto", "descripcion", "desc", "nomitem", "nombre_producto", "articulo", "item_desc"],
    "quantity": ["cantidad", "cant", "qty", "unidades", "unds", "stock", "cantidad_vendida"],
    "unit_price_net": ["valor_unitario", "valor_venta_unitario_sin_igv", "precio_sin_igv", "unit_price_net"],
    "unit_price_gross": ["precio_unitario", "precio_venta_unitario_con_igv", "precio_con_igv", "unit_price_gross"],
    "unit_cost_net": ["valor_unitario", "costo_unitario_sin_igv", "precio_compra_sin_igv", "unit_cost_net"],
    "unit_cost_gross": ["precio_unitario", "precio_compra_unitario_con_igv", "precio_con_igv", "unit_cost_gross"],
    "subtotal_net": ["subtotal", "importe_sin_igv", "monto_sin_igv", "total_sin_igv", "subtotal_net"],
    "tax_amount": ["igv", "impuesto", "tax", "tax_amount"],
    "total_gross": ["total", "importe_con_igv", "monto_total", "total_con_igv", "total_gross"],
    "supplier": ["proveedor", "denominacion_entidad", "razsoc", "razon_social", "supplier", "vendor", "ruc_proveedor"],
    "customer": ["cliente", "denominacion_entidad", "customer", "comprador", "razsoc", "razon_social", "ruc_cliente"],
    "software_category": ["descripcion_de_categoria", "categoria", "familia", "linea", "rubro", "grupo"],
    "brand": ["marca", "brand"],
    "unit": ["unidad", "codigo_unidad_de_medida", "unidad_de_medida", "um", "u_medida", "medida", "unit"],
    "current_price": ["precio_venta_unitario_con_igv", "valor_venta_unitario_sin_igv", "precio", "precio_actual", "pvp", "lista", "current_price"],
    "stock_available": ["stock_actual_disponible", "stock_actual", "stock", "existencia", "disponible"],
    "is_cancelled": ["anulado", "cancelado", "void", "cancelled"],
    "sale_id": ["venta_id", "id_venta", "comprobante", "factura", "boleta", "documento"],
    "purchase_id": ["compra_id", "id_compra", "comprobante", "factura", "documento"],
    "description": ["descripcion", "detalle", "observacion", "notas"],
}


@dataclass
class FieldCandidate:
    field: str
    column: str | None
    confidence: float
    reason: str
    alternatives: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _name_score(column: str, field: str) -> tuple[float, str]:
    normalized = normalize_column_name(column)
    aliases = ALIASES.get(field, [field])

    if normalized == field:
        return 1.0, "nombre exacto"
    if normalized in aliases:
        return 0.95, "alias exacto"

    best = max(similarity(normalized, alias) for alias in aliases)
    if best >= 0.85:
        return best * 0.9, "nombre similar"
    return best * 0.55, "similitud debil de nombre"


def _profile_score(profile: dict[str, Any], field: str) -> tuple[float, str]:
    date_ratio = float(profile.get("parseable_as_date", 0))
    number_ratio = float(profile.get("parseable_as_number", 0))
    unique_count = int(profile.get("unique_count", 0))

    if field == "date":
        return min(date_ratio, 1.0), "valores parseables como fecha"
    if field in {
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
    }:
        return min(number_ratio, 1.0), "valores parseables como numero"
    if field in {"product_id", "sale_id", "purchase_id"}:
        score = 0.45 if unique_count > 0 else 0.0
        return score, "columna con identificadores posibles"
    if field in {"product_name", "supplier", "customer", "software_category", "brand", "unit", "description", "is_cancelled"}:
        score = 0.35 if unique_count > 0 else 0.0
        return score, "columna textual/categorica posible"
    return 0.0, "sin senal estadistica"


def detect_schema(
    df: pd.DataFrame,
    profiles: dict[str, dict[str, Any]],
    dataset_type: str,
) -> dict[str, dict[str, Any]]:
    fields = CANONICAL_FIELDS[dataset_type]
    used_columns: set[str] = set()
    mapping: dict[str, dict[str, Any]] = {}

    for field in fields:
        candidates = []
        for column in df.columns:
            name_score, name_reason = _name_score(str(column), field)
            profile_score, profile_reason = _profile_score(profiles[str(column)], field)
            score = (name_score * 0.65) + (profile_score * 0.35)
            candidates.append(
                {
                    "column": str(column),
                    "confidence": round(float(score), 4),
                    "reason": f"{name_reason}; {profile_reason}",
                }
            )

        candidates.sort(key=lambda item: item["confidence"], reverse=True)
        best = candidates[0] if candidates else {"column": None, "confidence": 0.0, "reason": ""}

        if best["confidence"] >= 0.45 and best["column"] not in used_columns:
            column = best["column"]
            used_columns.add(column)
            confidence = best["confidence"]
            reason = best["reason"]
        else:
            column = None
            confidence = 0.0
            reason = "sin candidato confiable"

        mapping[field] = FieldCandidate(
            field=field,
            column=column,
            confidence=round(float(confidence), 4),
            reason=reason,
            alternatives=candidates[:3],
        ).to_dict()

    return mapping


def _mapped_column(mapping: dict[str, dict[str, Any]], field: str) -> str | None:
    candidate = mapping.get(field, {})
    return candidate.get("column")


def _numeric(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype(str)
        .str.replace(r"[^\d,\.\-]", "", regex=True)
        .str.replace(",", ".", regex=False)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def _amount_match_rate(df: pd.DataFrame, qty_col: str, unit_col: str, total_col: str) -> float:
    qty = _numeric(df[qty_col])
    unit = _numeric(df[unit_col])
    total = _numeric(df[total_col])
    mask = qty.notna() & unit.notna() & total.notna() & (total.abs() > 0)
    if int(mask.sum()) == 0:
        return 0.0
    expected = qty[mask] * unit[mask]
    diff = (expected - total[mask]).abs() / total[mask].abs()
    return float((diff <= 0.03).mean())


def refine_amount_mapping(
    df: pd.DataFrame,
    mapping: dict[str, dict[str, Any]],
    unit_field: str,
    total_field: str,
) -> dict[str, dict[str, Any]]:
    qty_col = _mapped_column(mapping, "quantity")
    if not qty_col:
        return mapping

    unit_candidates = [
        item["column"]
        for item in mapping.get(unit_field, {}).get("alternatives", [])
        if item.get("confidence", 0) >= 0.45 and item.get("column") in df.columns
    ]
    total_candidates = [
        item["column"]
        for item in mapping.get(total_field, {}).get("alternatives", [])
        if item.get("confidence", 0) >= 0.45 and item.get("column") in df.columns
    ]

    current_unit = _mapped_column(mapping, unit_field)
    current_total = _mapped_column(mapping, total_field)
    if current_unit:
        unit_candidates.append(current_unit)
    if current_total:
        total_candidates.append(current_total)

    unit_candidates = list(dict.fromkeys(unit_candidates))
    total_candidates = list(dict.fromkeys(total_candidates))

    best = None
    for unit_col in unit_candidates:
        for total_col in total_candidates:
            if unit_col == total_col:
                continue
            rate = _amount_match_rate(df, qty_col, unit_col, total_col)
            if best is None or rate > best[0]:
                best = (rate, unit_col, total_col)

    if best and best[0] >= 0.85:
        rate, unit_col, total_col = best
        mapping[unit_field]["column"] = unit_col
        mapping[unit_field]["confidence"] = max(float(mapping[unit_field].get("confidence", 0)), 0.98)
        mapping[unit_field]["reason"] = f"validacion matematica cantidad * unitario ~= total ({rate:.1%})"
        mapping[total_field]["column"] = total_col
        mapping[total_field]["confidence"] = max(float(mapping[total_field].get("confidence", 0)), 0.98)
        mapping[total_field]["reason"] = f"validacion matematica cantidad * unitario ~= total ({rate:.1%})"

    return mapping


def detect_all_schemas(
    dataframes: dict[str, pd.DataFrame],
    profiles: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, dict[str, dict[str, Any]]]:
    mappings = {
        dataset_type: detect_schema(dataframes[dataset_type], profiles[dataset_type], dataset_type)
        for dataset_type in ("products", "sales", "purchases")
    }
    mappings["sales"] = refine_amount_mapping(dataframes["sales"], mappings["sales"], "unit_price_net", "subtotal_net")
    mappings["purchases"] = refine_amount_mapping(dataframes["purchases"], mappings["purchases"], "unit_cost_net", "subtotal_net")
    return mappings
