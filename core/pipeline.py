from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .normalizer import normalize_all
from .product_matcher import match_all_products
from .profiler import profile_files
from .schema_detector import detect_all_schemas
from .summaries import build_summary_tables
from .validators import validate_dataset


DATASET_ORDER = ("products", "sales", "purchases")


def read_table_flexible(file_or_path: Any) -> pd.DataFrame:
    filename = str(getattr(file_or_path, "name", file_or_path)).lower()
    if filename.endswith((".xlsx", ".xls")):
        if hasattr(file_or_path, "seek"):
            file_or_path.seek(0)
        return pd.read_excel(file_or_path, sheet_name=0)

    return read_csv_flexible(file_or_path)


def read_csv_flexible(file_or_path: Any) -> pd.DataFrame:
    last_error: Exception | None = None
    for sep in (",", ";", "\t", "|"):
        try:
            if hasattr(file_or_path, "seek"):
                file_or_path.seek(0)
            df = pd.read_csv(file_or_path, sep=sep, encoding="utf-8-sig")
            if len(df.columns) > 1:
                return df
        except Exception as exc:
            last_error = exc
            if hasattr(file_or_path, "seek"):
                file_or_path.seek(0)

    try:
        if hasattr(file_or_path, "seek"):
            file_or_path.seek(0)
        return pd.read_csv(file_or_path, sep=None, engine="python", encoding="utf-8-sig")
    except Exception as exc:
        raise ValueError(f"No se pudo leer el CSV: {exc}") from last_error


def run_stage1(
    dataframes: dict[str, pd.DataFrame],
    schema_mapping: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    missing = [name for name in DATASET_ORDER if name not in dataframes]
    if missing:
        raise ValueError(f"Faltan datasets requeridos: {missing}")

    profiles = profile_files(dataframes)
    mappings = schema_mapping or detect_all_schemas(dataframes, profiles)
    validations = {
        name: validate_dataset(dataframes[name], mappings[name], name)
        for name in DATASET_ORDER
    }
    cleaned = normalize_all(dataframes, mappings)
    product_matches = match_all_products(cleaned)
    report = build_report(dataframes, mappings, validations, product_matches)
    summary_tables = build_summary_tables(cleaned, report)

    return {
        "profiles": profiles,
        "schema_mapping": mappings,
        "validations": validations,
        "cleaned": cleaned,
        "product_matches": product_matches,
        "report": report,
        "summary_tables": summary_tables,
    }


def build_report(
    dataframes: dict[str, pd.DataFrame],
    mappings: dict[str, Any],
    validations: dict[str, Any],
    product_matches: pd.DataFrame,
) -> dict[str, Any]:
    total_matches = int(len(product_matches))
    accepted = int((product_matches["status"] == "accepted").sum()) if total_matches else 0
    ambiguous = int((product_matches["status"] == "ambiguous").sum()) if total_matches else 0
    rejected = int((product_matches["status"] == "rejected").sum()) if total_matches else 0
    high_conf = int((product_matches["confidence"] >= 0.9).sum()) if total_matches else 0

    mapped_confidences = []
    all_confidences = []
    for dataset_mapping in mappings.values():
        for candidate in dataset_mapping.values():
            confidence = float(candidate.get("confidence", 0))
            all_confidences.append(confidence)
            if candidate.get("column"):
                mapped_confidences.append(confidence)

    return {
        "processed_at": datetime.now().isoformat(timespec="seconds"),
        "row_counts": {name: int(len(df)) for name, df in dataframes.items()},
        "column_mapping_confidence": round(
            sum(mapped_confidences) / max(len(mapped_confidences), 1), 4
        ),
        "all_field_confidence": round(sum(all_confidences) / max(len(all_confidences), 1), 4),
        "mapped_fields": len(mapped_confidences),
        "total_canonical_fields": len(all_confidences),
        "validations": validations,
        "product_match_total": total_matches,
        "product_match_coverage": round(accepted / max(total_matches, 1), 4),
        "high_confidence_matches": high_conf,
        "ambiguous_matches": ambiguous,
        "rejected_matches": rejected,
        "requires_human_review": ambiguous > 0 or rejected > 0,
    }


def export_stage1(result: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    paths: dict[str, str] = {}
    cleaned_names = {
        "products": "products_clean.csv",
        "sales": "sales_clean.csv",
        "purchases": "purchases_clean.csv",
    }
    for key, filename in cleaned_names.items():
        path = output_path / filename
        result["cleaned"][key].to_csv(path, index=False, encoding="utf-8-sig")
        paths[filename] = str(path)

    match_path = output_path / "product_matches.csv"
    result["product_matches"].to_csv(match_path, index=False, encoding="utf-8-sig")
    paths["product_matches.csv"] = str(match_path)

    for name, table in result.get("summary_tables", {}).items():
        path = output_path / f"{name}.csv"
        table.to_csv(path, index=False, encoding="utf-8-sig")
        paths[f"{name}.csv"] = str(path)

    json_outputs = {
        "schema_mapping.json": result["schema_mapping"],
        "normalization_report.json": result["report"],
        "profiles.json": result["profiles"],
    }
    for filename, payload in json_outputs.items():
        path = output_path / filename
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        paths[filename] = str(path)

    company_rules = {
        "normalization_rules": {
            "date_format": "auto",
            "decimal_separator": "auto",
            "currency": "unknown",
            "remove_patterns": ["S.A.C.", "E.I.R.L.", "S.R.L.", "UND", "UNID"],
        },
        "product_match_rules": {
            "confirmed_matches": {},
            "rejected_strings": ["FLETE", "DESCUENTO", "SERVICIO"],
        },
    }
    rules_path = output_path / "company_rules.json"
    rules_path.write_text(json.dumps(company_rules, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["company_rules.json"] = str(rules_path)

    return paths
