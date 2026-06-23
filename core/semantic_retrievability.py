from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from .text_utils import normalize_text, similarity


IGNORED_QUERY_TOKENS = {
    "A",
    "AL",
    "C",
    "CON",
    "DE",
    "DEL",
    "EL",
    "EN",
    "FORMA",
    "LA",
    "LAS",
    "LOS",
    "PACK",
    "PAQ",
    "PARA",
    "POR",
    "SIN",
    "UND",
    "UNID",
    "UNIDAD",
    "UNIDADES",
    "X",
    "Y",
}

ATTRIBUTE_COLUMNS = [
    "product_type",
    "subtype",
    "accessory",
    "shape",
    "feature",
    "material",
    "color",
    "capacity_text",
    "mouth_size_text",
    "use_category",
    "material_family",
]


def stable_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def split_compound_value(value: object) -> list[str]:
    text = stable_text(value)
    if not text:
        return []
    return [part.strip() for part in re.split(r"[|,/;]+", text) if part.strip()]


def query_tokens(value: object) -> list[str]:
    tokens = []
    for token in normalize_text(value).split():
        if token in IGNORED_QUERY_TOKENS:
            continue
        if len(token) <= 1:
            continue
        tokens.append(token)
    return list(dict.fromkeys(tokens))


def value_tokens(value: object) -> set[str]:
    tokens: set[str] = set()
    for part in split_compound_value(value):
        normalized = normalize_text(part)
        if not normalized:
            continue
        tokens.add(normalized)
        tokens.update(query_tokens(normalized))
    return tokens


def prepare_attributes(attributes: pd.DataFrame) -> pd.DataFrame:
    prepared = attributes.copy()
    prepared["capacity_text"] = ""
    capacity_mask = prepared["capacity_value"].notna() & prepared["capacity_unit"].notna()
    prepared.loc[capacity_mask, "capacity_text"] = (
        prepared.loc[capacity_mask, "capacity_value"].map(lambda value: f"{float(value):g}")
        + prepared.loc[capacity_mask, "capacity_unit"].astype(str).str.upper()
    )
    prepared["mouth_size_text"] = ""
    mouth_mask = prepared["mouth_size_mm"].notna()
    prepared.loc[mouth_mask, "mouth_size_text"] = prepared.loc[mouth_mask, "mouth_size_mm"].map(
        lambda value: f"{float(value):g}MM"
    )
    return prepared


def row_attribute_tokens(row: pd.Series) -> tuple[set[str], dict[str, list[str]]]:
    tokens: set[str] = set()
    by_attribute: dict[str, list[str]] = {}
    for column in ATTRIBUTE_COLUMNS:
        if column not in row:
            continue
        column_tokens = value_tokens(row.get(column))
        if column_tokens:
            tokens.update(column_tokens)
            by_attribute[column] = sorted(column_tokens)
    return tokens, by_attribute


def build_search_documents(attributes: pd.DataFrame) -> list[dict[str, Any]]:
    prepared = prepare_attributes(attributes)
    documents = []
    for _, row in prepared.iterrows():
        product_id = stable_text(row.get("product_id"))
        product_name = stable_text(row.get("product_name"))
        name_tokens = set(query_tokens(product_name))
        attr_tokens, attr_by_column = row_attribute_tokens(row)
        documents.append(
            {
                "product_id": product_id,
                "product_name": product_name,
                "name_tokens": name_tokens,
                "attribute_tokens": attr_tokens,
                "attribute_tokens_by_column": attr_by_column,
                "all_tokens": name_tokens | attr_tokens,
            }
        )
    return documents


def search_score(query: str, tokens: list[str], document: dict[str, Any]) -> float:
    if not tokens:
        return 0.0
    name_tokens = document["name_tokens"]
    attr_tokens = document["attribute_tokens"]
    attr_hits = sum(1 for token in tokens if token in attr_tokens)
    name_hits = sum(1 for token in tokens if token in name_tokens)
    fuzzy = similarity(query, document["product_name"])
    exact_name_boost = 1.0 if normalize_text(query) == normalize_text(document["product_name"]) else 0.0
    coverage = (attr_hits * 1.1 + name_hits * 1.4) / max(len(tokens), 1)
    return coverage + fuzzy * 0.35 + exact_name_boost + math.log1p(len(attr_tokens)) * 0.01


def rank_products(query: str, documents: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    tokens = query_tokens(query)
    ranked = []
    for document in documents:
        score = search_score(query, tokens, document)
        ranked.append(
            {
                "product_id": document["product_id"],
                "product_name": document["product_name"],
                "score": score,
            }
        )
    return sorted(ranked, key=lambda row: row["score"], reverse=True)[:limit]


def build_semantic_retrievability_report(attributes: pd.DataFrame) -> pd.DataFrame:
    documents = build_search_documents(attributes)
    document_by_id = {document["product_id"]: document for document in documents}
    rows = []
    for document in documents:
        product_id = document["product_id"]
        query = document["product_name"]
        tokens = query_tokens(query)
        attr_tokens = document["attribute_tokens"]
        matched = [token for token in tokens if token in attr_tokens]
        unmatched = [token for token in tokens if token not in attr_tokens]
        matched_by_attribute = {}
        for column, column_tokens in document["attribute_tokens_by_column"].items():
            overlap = sorted(set(tokens) & set(column_tokens))
            if overlap:
                matched_by_attribute[column] = overlap

        ranked = rank_products(query, documents, limit=10)
        ranked_ids = [row["product_id"] for row in ranked]
        best = ranked[0] if ranked else {"product_id": "", "product_name": "", "score": 0.0}
        rows.append(
            {
                "product_id": product_id,
                "product_name": query,
                "query": query,
                "query_tokens": "|".join(tokens),
                "matched_tokens": "|".join(matched),
                "unmatched_tokens": "|".join(unmatched),
                "matched_attributes_json": json.dumps(matched_by_attribute, ensure_ascii=False),
                "retrievability_score": round(len(matched) / len(tokens), 4) if tokens else 0.0,
                "top1_found": bool(ranked_ids[:1] == [product_id]),
                "top5_found": product_id in ranked_ids[:5],
                "top10_found": product_id in ranked_ids[:10],
                "best_match_product_id": best["product_id"],
                "best_match_product_name": best["product_name"],
                "best_match_score": round(float(best["score"]), 4),
            }
        )
    return pd.DataFrame(rows)


def build_retrievability_summary(report: pd.DataFrame) -> dict[str, Any]:
    if report.empty:
        return {
            "rows": 0,
            "avg_retrievability_score": 0.0,
            "top1_rate": 0.0,
            "top5_rate": 0.0,
            "top10_rate": 0.0,
        }
    return {
        "rows": int(len(report)),
        "avg_retrievability_score": round(float(report["retrievability_score"].mean()), 4),
        "top1_rate": round(float(report["top1_found"].mean()), 4),
        "top5_rate": round(float(report["top5_found"].mean()), 4),
        "top10_rate": round(float(report["top10_found"].mean()), 4),
    }


def export_retrievability(
    attributes: pd.DataFrame,
    output_dir: str | Path,
    report_name: str = "semantic_retrievability_report.csv",
    summary_name: str = "semantic_retrievability_summary.json",
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    report = build_semantic_retrievability_report(attributes)
    summary = build_retrievability_summary(report)

    report_path = output_path / report_name
    summary_path = output_path / summary_name
    report.to_csv(report_path, index=False, encoding="utf-8-sig")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        report_name: str(report_path),
        summary_name: str(summary_path),
    }
