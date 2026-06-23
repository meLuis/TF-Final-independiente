from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import pandas as pd

from .text_utils import normalize_text, similarity


@dataclass
class ProductMatch:
    source_dataset: str
    row_index: int
    source_product_id: str | None
    source_product_name: str | None
    matched_product_id: str | None
    matched_product_name: str | None
    confidence: float
    method: str
    status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _as_str(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def build_product_indexes(products: pd.DataFrame) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    by_id: dict[str, dict[str, Any]] = {}
    by_numeric_id: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}

    for idx, row in products.iterrows():
        product_id = _as_str(row.get("product_id"))
        product_name = _as_str(row.get("product_name"))
        record = {
            "index": int(idx),
            "product_id": product_id,
            "product_name": product_name,
            "product_name_norm": normalize_text(product_name or ""),
        }
        if product_id:
            by_id[normalize_text(product_id)] = record
            if str(product_id).strip().isdigit():
                by_numeric_id[str(int(str(product_id).strip()))] = record
        if product_name:
            by_name[normalize_text(product_name)] = record

    return by_id, by_numeric_id, by_name


def match_transaction_products(
    transactions: pd.DataFrame,
    products: pd.DataFrame,
    source_dataset: str,
    fuzzy_threshold: float = 0.82,
    ambiguity_gap: float = 0.05,
) -> pd.DataFrame:
    by_id, by_numeric_id, by_name = build_product_indexes(products)
    product_records = list(by_name.values())
    matches: list[dict[str, Any]] = []

    for idx, row in transactions.iterrows():
        source_id = _as_str(row.get("product_id"))
        source_name = _as_str(row.get("product_name"))
        source_id_norm = normalize_text(source_id or "")
        source_name_norm = normalize_text(source_name or "")

        selected = None
        confidence = 0.0
        method = "sin_match"
        status = "rejected"

        if source_id_norm and source_id_norm in by_id:
            selected = by_id[source_id_norm]
            confidence = 1.0
            method = "product_id_exact"
            status = "accepted"
        elif source_id and str(source_id).strip().isdigit() and str(int(str(source_id).strip())) in by_numeric_id:
            selected = by_numeric_id[str(int(str(source_id).strip()))]
            confidence = 0.98
            method = "product_id_numeric_equivalent"
            status = "accepted"
        elif source_name_norm and source_name_norm in by_name:
            selected = by_name[source_name_norm]
            confidence = 0.95
            method = "product_name_exact_normalized"
            status = "accepted"
        elif source_name_norm and product_records:
            scored = [
                (similarity(source_name_norm, product["product_name_norm"]), product)
                for product in product_records
            ]
            scored.sort(key=lambda item: item[0], reverse=True)
            best_score, best_product = scored[0]
            second_score = scored[1][0] if len(scored) > 1 else 0.0

            selected = best_product
            confidence = round(float(best_score), 4)
            method = "fuzzy_name"
            if best_score >= fuzzy_threshold and (best_score - second_score) >= ambiguity_gap:
                status = "accepted"
            elif best_score >= 0.65:
                status = "ambiguous"
            else:
                selected = None
                status = "rejected"

        matches.append(
            ProductMatch(
                source_dataset=source_dataset,
                row_index=int(idx),
                source_product_id=source_id,
                source_product_name=source_name,
                matched_product_id=selected.get("product_id") if selected else None,
                matched_product_name=selected.get("product_name") if selected else None,
                confidence=round(float(confidence), 4),
                method=method,
                status=status,
            ).to_dict()
        )

    return pd.DataFrame(matches)


def match_all_products(cleaned: dict[str, pd.DataFrame]) -> pd.DataFrame:
    products = cleaned["products"]
    frames = []
    for dataset_type in ("sales", "purchases"):
        frames.append(match_transaction_products(cleaned[dataset_type], products, dataset_type))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
