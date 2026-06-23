from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .text_utils import normalize_text


DEFAULT_RULES_VERSION = "2026-06-11"
ALLOWED_RULE_METHODS = {"keyword_first_match", "keyword_any", "contains_any", "not_contains_any"}
CONFIGURABLE_ATTRIBUTES = {
    "product_type",
    "subtype",
    "accessory",
    "shape",
    "feature",
    "use_category",
}
AUTO_MERGE_LLM_ATTRIBUTES = {"subtype", "accessory", "shape", "feature"}
AUTO_MERGE_LLM_MATERIALS = False
AUTO_MERGE_LLM_COLORS = False

STOPWORDS = {
    "A",
    "AL",
    "C",
    "CADA",
    "CON",
    "DE",
    "DEL",
    "EL",
    "EN",
    "LA",
    "LAS",
    "LOS",
    "PACK",
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

COLORS = {
    "AMARILLO",
    "AMBAR",
    "AZUL",
    "BEIGE",
    "BLANCO",
    "CELESTE",
    "DORADO",
    "FOSFORESCENTE",
    "FUCSIA",
    "GRIS",
    "MARRON",
    "MORADO",
    "NARANJA",
    "NATURAL",
    "NEGRO",
    "PLATEADO",
    "ROJO",
    "ROSADO",
    "TRANSPARENTE",
    "VERDE",
}

MATERIAL_RULES = [
    ("POLICARBONATO", "PC", "POLICARBONATO"),
    ("ACRILICO", "ACRILICO", "ACRILICO"),
    ("ALUMINIO", "ALUMINIO", "METAL"),
    ("CARTON", "CARTON", "PAPEL_CARTON"),
    ("LDPE", "LDPE", "POLIETILENO"),
    ("PEAD", "PEAD", "POLIETILENO"),
    ("PETG", "PETG", "POLIETILENO TEREFTALATO"),
    ("PET", "PET", "POLIETILENO TEREFTALATO"),
    ("PAPEL", "PAPEL", "PAPEL_CARTON"),
    ("METAL", "METAL", "METAL"),
    ("NYLON", "NYLON", "POLIAMIDA"),
    ("PLASTICO", "PLASTICO", "PLASTICO"),
    ("PP", "PP", "POLIPROPILENO"),
    ("PVC", "PVC", "PVC"),
    ("VIDRIO", "VIDRIO", "VIDRIO"),
]

PRODUCT_TYPE_RULES = [
    (("CREMERO", "VASELINERO"), "cremero", 0.94),
    (("PASTILLERO",), "accesorio", 0.90),
    (("PISETA", "GRADILLA", "TALQUERA", "PROBETA", "PROPIPETA"), "accesorio", 0.88),
    (("GOTERO",), "gotero", 0.95),
    (("POTE", "CREMERO"), "pote", 0.92),
    (("TUBO", "TUBOS"), "tubo", 0.90),
    (("FRASCO", "BOTELLA", "ENVASE"), "frasco", 0.93),
    (("BOMBA", "ATOMIZADORA", "ATOMIZADOR", "SPRAY", "GATILLO", "PULVERIZADOR", "TRIGGER"), "atomizador", 0.92),
    (("TAPA", "TAPON", "VALVULA", "DISPENSADOR", "ATOMIZADOR"), "tapa", 0.90),
    (("BOLSA", "BOLSAS", "ZIPLOC"), "bolsa", 0.91),
    (("CAJA", "CAJAS"), "caja", 0.90),
    (("KIT", "SET"), "kit", 0.86),
    (("ETIQUETA", "STICKER"), "etiqueta", 0.90),
    (("MAQUINA", "EQUIPO", "LAPTOP", "IMPRESORA"), "equipo", 0.84),
    (("REPUESTO", "ACCESORIO"), "accesorio", 0.84),
]

SUBTYPE_RULES = [
    (("AIRLESS",), "airless", 0.96),
    (("ATOMIZADOR", "SPRAY"), "atomizador", 0.95),
    (("BULLET",), "bullet", 0.97),
    (("CAMPANA",), "campana", 0.94),
    (("CHUPON",), "chupon", 0.94),
    (("CREMERO",), "cremero", 0.95),
    (("DISPENSADOR", "DISPENSADORA"), "dispensador", 0.95),
    (("ESPUMERO",), "espumero", 0.97),
    (("GATILLO",), "gatillo", 0.94),
    (("LAINA",), "laina", 0.92),
    (("RIMEL",), "rimel", 0.95),
    (("ROSCA",), "rosca", 0.90),
    (("ZIPLOC",), "ziploc", 0.95),
]

USE_RULES = [
    (("RIMEL", "LIPSTICK", "CREMERO", "COSMET", "BULLET", "AIRLESS"), "cosmetica", 0.89),
    (("ODONTO", "MEDIC", "CLINIC", "ORTOPEDIA", "PH", "CLORO"), "medico_laboratorio", 0.84),
    (("PINTURA", "BROCHA", "TORNILLO", "TUERCA", "MANGUERA"), "ferreteria", 0.84),
    (("BOLSA", "CAJA", "ENVASE", "FRASCO", "POTE"), "empaque_envase", 0.82),
]

DEFAULT_ATTRIBUTE_RULES = {
    "rules_version": DEFAULT_RULES_VERSION,
    "domain": "generic_commerce_catalog",
    "llm_status": "not_used",
    "allowed_methods": sorted(ALLOWED_RULE_METHODS),
    "attribute_rules": {
        "product_type": {
            "method": "keyword_first_match",
            "rules": [
                {"keywords": list(keywords), "value": value, "confidence": confidence}
                for keywords, value, confidence in PRODUCT_TYPE_RULES
            ],
        },
        "subtype": {
            "method": "keyword_first_match",
            "rules": [
                {"keywords": list(keywords), "value": value, "confidence": confidence}
                for keywords, value, confidence in SUBTYPE_RULES
            ]
            + [
                {"keywords": ["ESMALTE"], "value": "esmalte", "confidence": 0.92},
                {"keywords": ["BALSAMO", "LIPSTICK"], "value": "lipstick", "confidence": 0.90},
                {"keywords": ["VIAL"], "value": "vial", "confidence": 0.88},
                {"keywords": ["DOSIFICADOR"], "value": "dosificador", "confidence": 0.86},
            ],
        },
        "accessory": {
            "method": "keyword_any",
            "rules": [
                {"keywords": ["BROCHA"], "value": "brocha", "confidence": 0.92},
                {"keywords": ["CHUPON"], "value": "chupon", "confidence": 0.92},
                {"keywords": ["LAINA"], "value": "laina", "confidence": 0.90},
                {"keywords": ["TAPA", "TAPON"], "value": "tapa", "confidence": 0.88},
                {"keywords": ["REJILLA"], "value": "rejilla", "confidence": 0.88},
                {"keywords": ["GATILLO", "TRIGGER"], "value": "gatillo", "confidence": 0.90},
            ],
        },
        "shape": {
            "method": "keyword_first_match",
            "rules": [
                {"keywords": ["OVALADO", "OVALADA"], "value": "ovalado", "confidence": 0.90},
                {"keywords": ["CONICO", "CONICA"], "value": "conico", "confidence": 0.88},
                {"keywords": ["TUBULAR"], "value": "tubular", "confidence": 0.88},
                {"keywords": ["CILINDRICO", "CILINDRICA"], "value": "cilindrico", "confidence": 0.86},
            ],
        },
        "feature": {
            "method": "keyword_first_match",
            "rules": [
                {"keywords": ["NO ESTERIL"], "value": "no_esteril", "confidence": 0.88},
                {"keywords": ["ESTERIL", "ESTERILES"], "value": "esteril", "confidence": 0.90},
                {"keywords": ["GRADUADO", "GRADUADA"], "value": "graduado", "confidence": 0.90},
                {"keywords": ["DESCARTABLE"], "value": "descartable", "confidence": 0.88},
                {"keywords": ["IMPORTADO", "IMPORTADA"], "value": "importado", "confidence": 0.80},
            ],
        },
        "use_category": {
            "method": "keyword_first_match",
            "rules": [
                {"keywords": list(keywords), "value": value, "confidence": confidence}
                for keywords, value, confidence in USE_RULES
            ],
        },
    },
    "material_rules": [
        {"keyword": keyword, "material": material, "family": family, "confidence": 0.94}
        for keyword, material, family in MATERIAL_RULES
    ],
    "color_keywords": sorted(COLORS),
}


def tokenize_description(value: object) -> list[str]:
    text = normalize_text(value)
    return [token for token in text.split() if token and token not in STOPWORDS]


def first_keyword_match(text: str, rules: list[tuple[tuple[str, ...], str, float]]) -> tuple[str | None, float, str]:
    tokens = set(text.split())
    for keywords, value, confidence in rules:
        for keyword in keywords:
            if keyword in tokens:
                return value, confidence, keyword
    return None, 0.0, ""


def normalize_rule_keywords(rule: dict[str, Any]) -> list[str]:
    raw_keywords = rule.get("keywords", rule.get("match", []))
    if isinstance(raw_keywords, str):
        raw_keywords = [raw_keywords]
    return [normalize_text(keyword) for keyword in raw_keywords if normalize_text(keyword)]


def phrase_or_token_in_text(keyword: str, text: str, tokens: set[str]) -> bool:
    if " " in keyword:
        return keyword in text
    return keyword in tokens


def apply_configured_attribute_rule(text: str, rule_def: dict[str, Any]) -> tuple[str | None, float, str]:
    method = rule_def.get("method", "keyword_first_match")
    if method not in ALLOWED_RULE_METHODS:
        return None, 0.0, ""

    tokens = set(text.split())
    matched_values: list[tuple[str, float, str]] = []
    for rule in rule_def.get("rules", []):
        keywords = normalize_rule_keywords(rule)
        if not keywords:
            continue
        confidence = float(rule.get("confidence", 0.85))
        value = str(rule.get("value", "")).strip()
        if not value:
            continue

        has_match = any(phrase_or_token_in_text(keyword, text, tokens) for keyword in keywords)
        if method == "not_contains_any":
            has_match = not has_match
        if not has_match:
            continue
        if method == "keyword_first_match":
            return value, confidence, ",".join(keywords)
        matched_values.append((value, confidence, ",".join(keywords)))

    if matched_values:
        values = []
        confidences = []
        evidence = []
        for value, confidence, keyword in matched_values:
            if value not in values:
                values.append(value)
                confidences.append(confidence)
                evidence.append(keyword)
        return "|".join(values), max(confidences), "|".join(evidence)
    return None, 0.0, ""


def validate_attribute_rules(rules: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(rules, dict):
        raise ValueError("attribute_rules debe ser un objeto JSON.")

    merged = json.loads(json.dumps(DEFAULT_ATTRIBUTE_RULES, ensure_ascii=False))
    for key in ("rules_version", "domain", "llm_status"):
        if key in rules:
            merged[key] = rules[key]

    incoming_attribute_rules = rules.get("attribute_rules", {})
    if not isinstance(incoming_attribute_rules, dict):
        raise ValueError("attribute_rules.attribute_rules debe ser un objeto.")

    for attr, rule_def in incoming_attribute_rules.items():
        if attr not in CONFIGURABLE_ATTRIBUTES:
            continue
        if not isinstance(rule_def, dict):
            continue
        method = rule_def.get("method", "keyword_first_match")
        if method not in ALLOWED_RULE_METHODS:
            continue
        safe_rules = []
        for rule in rule_def.get("rules", []):
            if not isinstance(rule, dict):
                continue
            keywords = normalize_rule_keywords(rule)
            value = str(rule.get("value", "")).strip()
            if not keywords or not value:
                continue
            confidence = min(max(float(rule.get("confidence", 0.85)), 0.0), 1.0)
            safe_rules.append(
                {
                    "keywords": keywords,
                    "value": value,
                    "confidence": confidence,
                }
            )
        if safe_rules:
            merged["attribute_rules"][attr] = {"method": method, "rules": safe_rules}

    if isinstance(rules.get("material_rules"), list):
        safe_materials = []
        for rule in rules["material_rules"]:
            keyword = normalize_text(rule.get("keyword", ""))
            material = str(rule.get("material", "")).strip().upper()
            family = str(rule.get("family", material)).strip().upper()
            if keyword and material:
                safe_materials.append(
                    {
                        "keyword": keyword,
                        "material": material,
                        "family": family,
                        "confidence": min(max(float(rule.get("confidence", 0.94)), 0.0), 1.0),
                    }
                )
        if safe_materials:
            merged["material_rules"] = safe_materials

    if isinstance(rules.get("color_keywords"), list):
        colors = sorted(
            {
                color
                for color in (normalize_text(raw_color) for raw_color in rules["color_keywords"])
                if re.fullmatch(r"[A-ZÑ]{3,24}", color)
            }
        )
        if colors:
            merged["color_keywords"] = colors
    return merged


def sanitize_attribute_rule_additions(rules: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(rules, dict):
        raise ValueError("Las reglas propuestas por LLM deben ser un objeto JSON.")

    sanitized = {
        "rules_version": rules.get("rules_version", DEFAULT_RULES_VERSION),
        "domain": rules.get("domain", "unknown"),
        "llm_status": rules.get("llm_status", "proposed_additions"),
        "allowed_methods": sorted(ALLOWED_RULE_METHODS),
        "attribute_rules": {},
        "material_rules": [],
        "color_keywords": [],
    }

    incoming_attribute_rules = rules.get("attribute_rules", {})
    if isinstance(incoming_attribute_rules, dict):
        for attr, rule_def in incoming_attribute_rules.items():
            if attr not in AUTO_MERGE_LLM_ATTRIBUTES:
                continue
            if not isinstance(rule_def, dict):
                continue
            method = rule_def.get("method", "keyword_first_match")
            if method not in ALLOWED_RULE_METHODS:
                continue
            safe_rules = []
            for rule in rule_def.get("rules", []):
                if not isinstance(rule, dict):
                    continue
                keywords = normalize_rule_keywords(rule)
                value = normalize_text(rule.get("value", "")).lower().replace(" ", "_")
                if not keywords or not value:
                    continue
                confidence = min(max(float(rule.get("confidence", 0.85)), 0.0), 1.0)
                safe_rules.append(
                    {
                        "keywords": keywords,
                        "value": value,
                        "confidence": confidence,
                    }
                )
            if safe_rules:
                sanitized["attribute_rules"][attr] = {"method": method, "rules": safe_rules}

    if isinstance(rules.get("material_rules"), list):
        for rule in rules["material_rules"]:
            keyword = normalize_text(rule.get("keyword", ""))
            material = str(rule.get("material", "")).strip().upper()
            family = str(rule.get("family", material)).strip().upper()
            if keyword and material:
                sanitized["material_rules"].append(
                    {
                        "keyword": keyword,
                        "material": material,
                        "family": family,
                        "confidence": min(max(float(rule.get("confidence", 0.94)), 0.0), 1.0),
                    }
                )

    if isinstance(rules.get("color_keywords"), list):
        sanitized["color_keywords"] = sorted(
            {
                color
                for color in (normalize_text(raw_color) for raw_color in rules["color_keywords"])
                if re.fullmatch(r"[A-ZÑ]{3,24}", color)
            }
        )
    return sanitized


def load_attribute_rules(rules_path: str | Path | None = None) -> dict[str, Any]:
    if rules_path is None or not Path(rules_path).exists():
        return validate_attribute_rules(DEFAULT_ATTRIBUTE_RULES)
    payload = json.loads(Path(rules_path).read_text(encoding="utf-8"))
    return validate_attribute_rules(payload)


def extract_capacity(text: str) -> tuple[float | None, str | None, float, str]:
    pattern = r"\b(\d+(?:[\.,]\d+)?)\s*(ML|CC|L|LT|LTR|GR|G|KG|MG|W|V)\b"
    match = re.search(pattern, text)
    if not match:
        return None, None, 0.0, ""
    value = float(match.group(1).replace(",", "."))
    unit = match.group(2)
    if unit in {"LT", "LTR"}:
        unit = "L"
    if unit == "G":
        unit = "GR"
    return value, unit, 0.95, match.group(0)


def extract_mouth_size(text: str) -> tuple[float | None, float, str]:
    patterns = [
        r"\b[BTN]\s*([0-9]{2,3})\s*(?:MM)?\b",
        r"\b([0-9]{2,3})\s*/\s*410\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1)), 0.92, match.group(0)
    return None, 0.0, ""


def extract_size_text(text: str) -> tuple[str | None, float, str]:
    pattern = r"\b\d+(?:[\.,]\d+)?\s*(?:CM|MM|M)?\s*[*X]\s*\d+(?:[\.,]\d+)?\s*(?:CM|MM|M)?\b"
    match = re.search(pattern, text)
    if not match:
        return None, 0.0, ""
    return match.group(0), 0.93, match.group(0)


def extract_color(text: str, rules: dict[str, Any] | None = None) -> tuple[str | None, float, str]:
    tokens = text.split()
    colors = rules.get("color_keywords", sorted(COLORS)) if rules else sorted(COLORS)
    for color in colors:
        if color in tokens:
            return color, 0.94, color
    return None, 0.0, ""


def extract_material(text: str, rules: dict[str, Any] | None = None) -> tuple[str | None, str | None, float, str]:
    tokens = set(text.split())
    material_rules = (
        rules.get("material_rules", DEFAULT_ATTRIBUTE_RULES["material_rules"])
        if rules
        else DEFAULT_ATTRIBUTE_RULES["material_rules"]
    )
    for rule in material_rules:
        keyword = normalize_text(rule.get("keyword", ""))
        material = rule.get("material")
        family = rule.get("family", material)
        if keyword in tokens:
            return material, family, float(rule.get("confidence", 0.94)), keyword
    return None, None, 0.0, ""


def extract_brand(text: str) -> tuple[str | None, float, str]:
    # Brand inference is intentionally disabled in the baseline. In generic
    # catalogs, alphanumeric packaging/model tokens such as 100UND, BLS100 or
    # BX200 look brand-like but are usually not brands.
    return None, 0.0, ""


def extract_attributes_for_product(product: pd.Series, rules: dict[str, Any] | None = None) -> dict[str, Any]:
    rules = rules or load_attribute_rules()
    product_name = product.get("product_name", "")
    text = normalize_text(product_name)
    tokens = tokenize_description(product_name)

    capacity_value, capacity_unit, capacity_conf, capacity_evidence = extract_capacity(text)
    mouth_size, mouth_conf, mouth_evidence = extract_mouth_size(text)
    size_text, size_conf, size_evidence = extract_size_text(text)
    color, color_conf, color_evidence = extract_color(text, rules)
    material, material_family, material_conf, material_evidence = extract_material(text, rules)
    attr_rules = rules.get("attribute_rules", {})
    product_type, type_conf, type_evidence = apply_configured_attribute_rule(
        text, attr_rules.get("product_type", {})
    )
    subtype, subtype_conf, subtype_evidence = apply_configured_attribute_rule(
        text, attr_rules.get("subtype", {})
    )
    accessory, accessory_conf, accessory_evidence = apply_configured_attribute_rule(
        text, attr_rules.get("accessory", {})
    )
    shape, shape_conf, shape_evidence = apply_configured_attribute_rule(
        text, attr_rules.get("shape", {})
    )
    feature, feature_conf, feature_evidence = apply_configured_attribute_rule(
        text, attr_rules.get("feature", {})
    )
    use_category, use_conf, use_evidence = apply_configured_attribute_rule(
        text, attr_rules.get("use_category", {})
    )
    brand, brand_conf, brand_evidence = extract_brand(text)

    if not use_category:
        use_category = "general"
        use_conf = 0.60
        use_evidence = "default"

    confidence_values = [
        value
        for value in (
            capacity_conf,
            mouth_conf,
            size_conf,
            color_conf,
            material_conf,
            type_conf,
            subtype_conf,
            accessory_conf,
            shape_conf,
            feature_conf,
            use_conf,
            brand_conf,
        )
        if value > 0
    ]
    avg_confidence = sum(confidence_values) / max(len(confidence_values), 1)
    extraction_method = "deterministic_rules" if confidence_values else "unclassified"
    attribute_confidence = {
        attr: round(conf, 4)
        for attr, conf in (
            ("product_type", type_conf),
            ("subtype", subtype_conf),
            ("accessory", accessory_conf),
            ("shape", shape_conf),
            ("feature", feature_conf),
            ("material", material_conf),
            ("color", color_conf),
            ("capacity", capacity_conf),
            ("mouth_size", mouth_conf),
            ("size_text", size_conf),
            ("use_category", use_conf),
        )
        if conf > 0
    }
    evidence = {
        "product_type": type_evidence,
        "subtype": subtype_evidence,
        "accessory": accessory_evidence,
        "shape": shape_evidence,
        "feature": feature_evidence,
        "material": material_evidence,
        "color": color_evidence,
        "capacity": capacity_evidence,
        "mouth_size": mouth_evidence,
        "size_text": size_evidence,
        "use_category": use_evidence,
        "brand": brand_evidence,
    }

    return {
        "product_id": product.get("product_id"),
        "product_name": product_name,
        "product_type": product_type,
        "subtype": subtype,
        "material": material,
        "color": color,
        "capacity_value": capacity_value,
        "capacity_unit": capacity_unit,
        "mouth_size_mm": mouth_size,
        "size_text": size_text,
        "closure_type": subtype if subtype in {"atomizador", "dispensador", "rosca", "chupon", "gatillo"} else None,
        "accessory": accessory,
        "shape": shape,
        "feature": feature,
        "brand": brand,
        "use_category": use_category,
        "material_family": material_family,
        "keywords": json.dumps(tokens[:8], ensure_ascii=False),
        "confidence": round(avg_confidence, 4),
        "attribute_confidence": json.dumps(attribute_confidence, ensure_ascii=False),
        "extraction_method": extraction_method,
        "rules_version": rules.get("rules_version", DEFAULT_RULES_VERSION),
        "attribute_evidence": json.dumps(evidence, ensure_ascii=False),
    }


def build_token_profile(products: pd.DataFrame) -> pd.DataFrame:
    rows = []
    descriptions = products.get("product_name", pd.Series(dtype=str)).fillna("")
    product_count = len(descriptions)
    token_counter: Counter[str] = Counter()
    product_presence: Counter[str] = Counter()

    for description in descriptions:
        tokens = tokenize_description(description)
        token_counter.update(tokens)
        product_presence.update(set(tokens))

    for token, count in token_counter.most_common(100):
        rows.append(
            {
                "token": token,
                "token_count": int(count),
                "product_count": int(product_presence[token]),
                "product_coverage": round(product_presence[token] / max(product_count, 1), 4),
            }
        )
    return pd.DataFrame(rows)


def build_coverage_report(attributes: pd.DataFrame) -> pd.DataFrame:
    checked = [
        "product_type",
        "subtype",
        "material",
        "color",
        "accessory",
        "shape",
        "feature",
        "capacity_value",
        "mouth_size_mm",
        "size_text",
        "closure_type",
        "brand",
        "use_category",
        "material_family",
    ]
    rows = []
    total = len(attributes)
    for column in checked:
        filled_mask = attributes[column].notna() & (attributes[column].astype(str).str.strip() != "")
        top_values = attributes.loc[filled_mask, column].astype(str).value_counts().head(10).to_dict()
        rows.append(
            {
                "attribute": column,
                "filled": int(filled_mask.sum()),
                "total": int(total),
                "coverage": round(float(filled_mask.sum()) / max(total, 1), 4),
                "unique_values": int(attributes.loc[filled_mask, column].nunique()),
                "top_values_json": json.dumps(top_values, ensure_ascii=False),
            }
        )
    rows.append(
        {
            "attribute": "confidence",
            "filled": int(attributes["confidence"].notna().sum()),
            "total": int(total),
            "coverage": round(float(attributes["confidence"].mean()), 4) if total else 0,
            "unique_values": int(attributes["confidence"].nunique()) if total else 0,
            "top_values_json": "{}",
        }
    )
    return pd.DataFrame(rows)


def build_review_sample(
    attributes: pd.DataFrame,
    activity: pd.DataFrame | None = None,
    sample_size: int = 40,
) -> pd.DataFrame:
    review = attributes.copy()
    if activity is not None and not activity.empty:
        activity_cols = ["product_id", "sales_rows", "purchases_rows", "sales_total", "purchases_total"]
        available = [column for column in activity_cols if column in activity.columns]
        review = review.merge(activity[available], on="product_id", how="left")

    for column in ["sales_rows", "purchases_rows", "sales_total", "purchases_total"]:
        if column not in review.columns:
            review[column] = 0
        review[column] = pd.to_numeric(review[column], errors="coerce").fillna(0)

    review["needs_review_reason"] = ""
    review.loc[review["product_type"].isna(), "needs_review_reason"] += "sin_tipo;"
    review.loc[review["confidence"] < 0.78, "needs_review_reason"] += "baja_confianza;"
    review.loc[
        (review["product_type"] == "tapa") & review["capacity_value"].notna(),
        "needs_review_reason",
    ] += "tapa_con_capacidad;"

    review["activity_score"] = (
        review["sales_rows"] + review["purchases_rows"] + review["sales_total"].abs() / 100
    )
    review = review.sort_values(
        by=["needs_review_reason", "activity_score", "confidence"],
        ascending=[False, False, True],
    )
    columns = [
        "product_id",
        "product_name",
        "product_type",
        "subtype",
        "material",
        "color",
        "accessory",
        "shape",
        "feature",
        "capacity_value",
        "capacity_unit",
        "mouth_size_mm",
        "use_category",
        "confidence",
        "needs_review_reason",
        "sales_rows",
        "purchases_rows",
    ]
    return review[columns].head(sample_size)


def build_unvalidated_sample(
    attributes: pd.DataFrame,
    catalog_path: str | Path | None = None,
    activity: pd.DataFrame | None = None,
    sample_size: int = 50,
) -> pd.DataFrame:
    unvalidated = attributes.copy()
    if catalog_path is not None and Path(catalog_path).exists():
        catalog = pd.read_csv(catalog_path, encoding="utf-8-sig")
        catalog_ids = set(catalog["codigo"].astype(str))
        unvalidated = unvalidated.loc[~unvalidated["product_id"].astype(str).isin(catalog_ids)].copy()

    if activity is not None and not activity.empty:
        activity_cols = ["product_id", "sales_rows", "purchases_rows", "sales_total", "purchases_total"]
        available = [column for column in activity_cols if column in activity.columns]
        unvalidated = unvalidated.merge(activity[available], on="product_id", how="left")

    for column in ["sales_rows", "purchases_rows", "sales_total", "purchases_total"]:
        if column not in unvalidated.columns:
            unvalidated[column] = 0
        unvalidated[column] = pd.to_numeric(unvalidated[column], errors="coerce").fillna(0)

    unvalidated["activity_score"] = (
        unvalidated["sales_rows"]
        + unvalidated["purchases_rows"]
        + unvalidated["sales_total"].abs() / 100
        + unvalidated["purchases_total"].abs() / 100
    )
    unvalidated = unvalidated.sort_values(
        by=["activity_score", "confidence"],
        ascending=[False, True],
    )
    columns = [
        "product_id",
        "product_name",
        "product_type",
        "subtype",
        "material",
        "color",
        "accessory",
        "shape",
        "feature",
        "capacity_value",
        "capacity_unit",
        "mouth_size_mm",
        "confidence",
        "sales_rows",
        "purchases_rows",
    ]
    return unvalidated[columns].head(sample_size)


def infer_rules_summary() -> dict[str, Any]:
    rules = validate_attribute_rules(DEFAULT_ATTRIBUTE_RULES)
    rules["generated_at"] = datetime.now().isoformat(timespec="seconds")
    rules["mode"] = "deterministic_configurable_baseline"
    rules["contract"] = "LLM may propose JSON rules only; Python code is not generated or executed."
    return rules


def collect_rule_keywords(rules: dict[str, Any]) -> set[str]:
    covered: set[str] = set()
    for rule_def in rules.get("attribute_rules", {}).values():
        for rule in rule_def.get("rules", []):
            covered.update(normalize_rule_keywords(rule))
    for rule in rules.get("material_rules", []):
        keyword = normalize_text(rule.get("keyword", ""))
        if keyword:
            covered.add(keyword)
    covered.update(normalize_text(color) for color in rules.get("color_keywords", []))
    return covered


def build_uncovered_token_candidates(
    token_profile: pd.DataFrame,
    current_rules: dict[str, Any],
    limit: int = 50,
) -> list[dict[str, Any]]:
    covered = collect_rule_keywords(current_rules)
    ignored_patterns = [
        r"^\d+$",
        r"^\d+(ML|CC|L|LT|GR|G|KG|MG|MM|CM|UND|UNID)$",
        r"^[BTN]?\d{2,3}$",
    ]
    candidates = []
    for _, row in token_profile.iterrows():
        token = normalize_text(row["token"])
        if not token or token in covered or token in STOPWORDS:
            continue
        if any(re.fullmatch(pattern, token) for pattern in ignored_patterns):
            continue
        if len(token) <= 2:
            continue
        candidates.append(
            {
                "token": token,
                "token_count": int(row.get("token_count", 0)),
                "product_count": int(row.get("product_count", 0)),
                "product_coverage": float(row.get("product_coverage", 0)),
            }
        )
        if len(candidates) >= limit:
            break
    return candidates


def build_llm_additive_rules_prompt(
    descriptions: list[str],
    token_profile: pd.DataFrame,
    current_rules: dict[str, Any] | None = None,
    max_tokens: int = 45,
    max_descriptions: int = 25,
) -> str:
    rules = current_rules or validate_attribute_rules(DEFAULT_ATTRIBUTE_RULES)
    candidates = build_uncovered_token_candidates(token_profile, rules, limit=max_tokens)
    sample = descriptions[:max_descriptions]
    schema = {
        "rules_version": DEFAULT_RULES_VERSION,
        "domain": "short_domain_name",
        "llm_status": "proposed_additions",
        "attribute_rules": {
            "product_type": {"method": "keyword_first_match", "rules": []},
            "subtype": {"method": "keyword_first_match", "rules": []},
            "accessory": {"method": "keyword_any", "rules": []},
            "shape": {"method": "keyword_first_match", "rules": []},
            "feature": {"method": "keyword_first_match", "rules": []},
            "use_category": {"method": "keyword_first_match", "rules": []},
        },
        "material_rules": [],
        "color_keywords": [],
    }
    return (
        "Eres un asistente de normalizacion de catalogos empresariales.\n"
        "Debes proponer SOLO reglas NUEVAS que no esten ya cubiertas.\n"
        "No reconstruyas las reglas existentes. Si no hay reglas utiles, devuelve listas vacias.\n"
        "No escribas Python. No inventes productos. No agregues atributos fuera del esquema.\n"
        "Prioriza subtype, accessory, shape y feature, porque son las reglas que se aceptan automaticamente.\n"
        "Puedes proponer product_type, use_category, material_rules o color_keywords solo si son muy evidentes, "
        "pero esas reglas requeriran revision y no se autoaceptan.\n"
        "Usa keywords en MAYUSCULAS sin tildes. Usa values en espanol, minusculas y snake_case; no traduzcas al ingles.\n"
        "Devuelve SOLO JSON valido.\n"
        "Reglas estrictas de formato: comillas dobles, sin comentarios, sin trailing commas, "
        "sin markdown y sin texto fuera del JSON.\n\n"
        "Atributos permitidos:\n"
        "- product_type: objeto principal del producto.\n"
        "- subtype: variante comercial o familia especifica.\n"
        "- accessory: piezas incluidas o asociadas como tapa, brocha, chupon.\n"
        "- shape: forma fisica como ovalado, conico, tubular.\n"
        "- feature: cualidad como esteril, graduado, importado.\n"
        "- use_category: uso general del producto.\n"
        "- material_rules: materiales explicitos.\n"
        "- color_keywords: colores explicitos.\n\n"
        "Formato obligatorio de cada regla:\n"
        '{"keywords":["TOKEN"],"value":"valor_normalizado","confidence":0.85}\n\n'
        f"ESQUEMA DE SALIDA:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
        f"TOKENS CANDIDATOS NO CUBIERTOS:\n{json.dumps(candidates, ensure_ascii=False, indent=2)}\n\n"
        f"MUESTRA DE DESCRIPCIONES:\n{json.dumps(sample, ensure_ascii=False, indent=2)}\n"
    )


def merge_attribute_rules(base_rules: dict[str, Any], additional_rules: dict[str, Any]) -> dict[str, Any]:
    merged = validate_attribute_rules(base_rules)
    additions = sanitize_attribute_rule_additions(additional_rules)

    for attr, add_def in additions.get("attribute_rules", {}).items():
        if attr not in AUTO_MERGE_LLM_ATTRIBUTES:
            continue
        base_def = merged["attribute_rules"].setdefault(
            attr, {"method": add_def.get("method", "keyword_first_match"), "rules": []}
        )
        existing = {
            (tuple(rule.get("keywords", [])), rule.get("value"))
            for rule in base_def.get("rules", [])
        }
        for rule in add_def.get("rules", []):
            key = (tuple(rule.get("keywords", [])), rule.get("value"))
            if key not in existing:
                base_def["rules"].append(rule)
                existing.add(key)

    if AUTO_MERGE_LLM_MATERIALS:
        existing_materials = {
            (rule.get("keyword"), rule.get("material"))
            for rule in merged.get("material_rules", [])
        }
        for rule in additions.get("material_rules", []):
            key = (rule.get("keyword"), rule.get("material"))
            if key not in existing_materials:
                merged["material_rules"].append(rule)
                existing_materials.add(key)

    if AUTO_MERGE_LLM_COLORS:
        merged["color_keywords"] = sorted(
            set(merged.get("color_keywords", [])) | set(additions.get("color_keywords", []))
        )
    merged["llm_status"] = additional_rules.get("llm_status", "merged_additions")
    return merged


def compare_with_catalog(attributes: pd.DataFrame, catalog_path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    path = Path(catalog_path)
    if not path.exists():
        return pd.DataFrame(), pd.DataFrame()

    catalog = pd.read_csv(path, encoding="utf-8-sig")
    catalog["product_id"] = catalog["codigo"].astype(str)
    attrs = attributes.copy()
    attrs["product_id"] = attrs["product_id"].astype(str)
    merged = attrs.merge(catalog, on="product_id", how="inner", suffixes=("", "_gold"))

    comparisons = [
        ("product_type", "tipo_producto"),
        ("subtype", "subtipo"),
        ("material", "material_principal"),
        ("color", "color"),
        ("capacity_value", "volumen_ml"),
        ("mouth_size_mm", "tam_boca_mm"),
        ("use_category", "uso_categoria"),
        ("material_family", "familia_material"),
    ]
    rows = []
    detail = merged[["product_id", "product_name"]].copy()

    def comparable(value: object) -> str:
        if pd.isna(value):
            return ""
        return normalize_text(value)

    for predicted, expected in comparisons:
        if expected not in merged.columns:
            continue
        pred_norm = merged[predicted].map(comparable)
        exp_norm = merged[expected].map(comparable)
        both_filled = (pred_norm != "") & (exp_norm != "")
        matches = pred_norm == exp_norm
        detail[f"{predicted}_predicted"] = merged[predicted]
        detail[f"{predicted}_expected"] = merged[expected]
        detail[f"{predicted}_match"] = matches.where(both_filled, pd.NA)
        rows.append(
            {
                "attribute": predicted,
                "overlap_rows": int(len(merged)),
                "expected_filled": int((exp_norm != "").sum()),
                "predicted_filled_on_expected": int((both_filled).sum()),
                "accuracy_on_both_filled": round(float(matches[both_filled].mean()), 4)
                if both_filled.any()
                else None,
                "recall_against_expected": round(
                    float((matches & (exp_norm != "")).sum()) / max(int((exp_norm != "").sum()), 1),
                    4,
                ),
            }
        )
    return pd.DataFrame(rows), detail


def run_stage15(
    stage1_output_dir: str | Path,
    catalog_path: str | Path | None = None,
    rules_path: str | Path | None = None,
) -> dict[str, Any]:
    input_dir = Path(stage1_output_dir)
    products = pd.read_csv(input_dir / "products_clean.csv", encoding="utf-8-sig")
    activity_path = input_dir / "product_activity_summary.csv"
    activity = pd.read_csv(activity_path, encoding="utf-8-sig") if activity_path.exists() else pd.DataFrame()

    rules = load_attribute_rules(rules_path)
    attributes = pd.DataFrame([extract_attributes_for_product(row, rules) for _, row in products.iterrows()])
    token_profile = build_token_profile(products)
    coverage_report = build_coverage_report(attributes)
    review_sample = build_review_sample(attributes, activity)
    unvalidated_sample = build_unvalidated_sample(attributes, catalog_path, activity)

    comparison_summary = pd.DataFrame()
    comparison_detail = pd.DataFrame()
    if catalog_path is not None:
        comparison_summary, comparison_detail = compare_with_catalog(attributes, catalog_path)

    return {
        "attributes": attributes,
        "token_profile": token_profile,
        "coverage_report": coverage_report,
        "review_sample": review_sample,
        "unvalidated_sample": unvalidated_sample,
        "rules": rules,
        "comparison_summary": comparison_summary,
        "comparison_detail": comparison_detail,
    }


def export_stage15(result: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}

    table_outputs = {
        "product_attributes.csv": result["attributes"],
        "token_profile.csv": result["token_profile"],
        "attribute_coverage_report.csv": result["coverage_report"],
        "attribute_review_sample.csv": result["review_sample"],
        "attribute_unvalidated_sample.csv": result["unvalidated_sample"],
    }
    if not result["comparison_summary"].empty:
        table_outputs["attribute_gold_comparison_summary.csv"] = result["comparison_summary"]
        table_outputs["attribute_gold_comparison_detail.csv"] = result["comparison_detail"]

    for filename, table in table_outputs.items():
        path = output_path / filename
        table.to_csv(path, index=False, encoding="utf-8-sig")
        paths[filename] = str(path)

    rules_path = output_path / "attribute_rules.json"
    rules_path.write_text(json.dumps(result["rules"], indent=2, ensure_ascii=False), encoding="utf-8")
    paths["attribute_rules.json"] = str(rules_path)

    report_path = output_path / "attribute_extraction_report.json"
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "rows": int(len(result["attributes"])),
        "avg_confidence": round(float(result["attributes"]["confidence"].mean()), 4),
        "outputs": paths,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["attribute_extraction_report.json"] = str(report_path)
    return paths
