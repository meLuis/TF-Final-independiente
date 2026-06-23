from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pandas as pd

from core.attribute_extractor import (
    build_llm_additive_rules_prompt,
    build_token_profile,
    load_attribute_rules,
    merge_attribute_rules,
    run_stage15,
    sanitize_attribute_rule_additions,
)


BASE_DIR = Path(__file__).parent
STAGE1_OUTPUT_DIR = BASE_DIR / "outputs" / "stage1_datos"
STAGE15_OUTPUT_DIR = BASE_DIR / "outputs" / "stage15_datos"
OUTPUT_ADDITIONS_PATH = STAGE15_OUTPUT_DIR / "attribute_rules_gemini_additions.json"
OUTPUT_RULES_PATH = STAGE15_OUTPUT_DIR / "attribute_rules_gemini_merged.json"
CURRENT_RULES_PATH = STAGE15_OUTPUT_DIR / "attribute_rules.json"
RAW_RESPONSE_PATH = STAGE15_OUTPUT_DIR / "attribute_rules_gemini_raw.txt"
REPAIRED_RAW_RESPONSE_PATH = STAGE15_OUTPUT_DIR / "attribute_rules_gemini_repaired_raw.txt"
DEFAULT_SAMPLE_SIZE = 10_000
DEFAULT_TOKEN_LIMIT = 260


def parse_limit(value: str | None, default: int, total: int) -> int:
    if value is None:
        return min(default, total)
    normalized = value.strip().lower()
    if normalized in {"all", "todo", "*"}:
        return total
    return min(max(int(normalized), 1), total)


def sample_descriptions(
    products: pd.DataFrame,
    attributes: pd.DataFrame,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
) -> list[str]:
    products = products.copy()
    attributes = attributes.copy()
    products["product_name"] = products["product_name"].fillna("").astype(str)
    products["product_id"] = products["product_id"].astype(str)
    attributes["product_id"] = attributes["product_id"].astype(str)
    scoped = products.merge(attributes, on="product_id", how="left", suffixes=("", "_attr"))
    products["name_len"] = products["product_name"].str.len()
    scoped["missing_signal"] = scoped[
        ["subtype", "accessory", "shape", "feature"]
    ].isna().sum(axis=1)
    scoped["confidence"] = pd.to_numeric(scoped["confidence"], errors="coerce").fillna(0)

    low_structure = scoped.sort_values(
        by=["missing_signal", "confidence"],
        ascending=[False, True],
    ).head(sample_size // 2)
    low_confidence = scoped.sort_values("confidence", ascending=True).head(sample_size // 4)
    long_names = scoped.assign(name_len=scoped["product_name"].str.len()).sort_values(
        "name_len",
        ascending=False,
    ).head(sample_size // 6)
    random_names = scoped.sample(min(sample_size, len(scoped)), random_state=43)
    combined = pd.concat([low_structure, low_confidence, long_names, random_names], ignore_index=True)
    combined = combined.drop_duplicates(subset=["product_name"]).head(sample_size)
    return combined["product_name"].tolist()


def gemini_api_key() -> str:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Falta GEMINI_API_KEY o GOOGLE_API_KEY en variables de entorno.")
    return api_key


def call_gemini(prompt: str) -> str:
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError(
            "Falta instalar google-genai. Ejecuta: py -m pip install google-genai"
        ) from exc

    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    client = genai.Client(api_key=gemini_api_key())
    response = client.models.generate_content(
        model=model,
        contents=prompt,
    )
    return response.text or "{}"


def extract_json_object(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def repair_json_with_gemini(raw_text: str) -> str:
    repair_prompt = (
        "Corrige la sintaxis del siguiente JSON. No cambies el significado, "
        "no agregues explicaciones, no uses markdown, no incluyas texto fuera del JSON. "
        "Usa comillas dobles en todas las claves y strings, sin trailing commas.\n\n"
        f"{raw_text[:12000]}"
    )
    return call_gemini(repair_prompt)


def main() -> None:
    products = pd.read_csv(STAGE1_OUTPUT_DIR / "products_clean.csv", encoding="utf-8-sig")
    token_profile = build_token_profile(products)
    current_rules = load_attribute_rules(CURRENT_RULES_PATH if CURRENT_RULES_PATH.exists() else None)
    baseline = run_stage15(STAGE1_OUTPUT_DIR, rules_path=CURRENT_RULES_PATH if CURRENT_RULES_PATH.exists() else None)
    sample_size = parse_limit(os.environ.get("LLM_SAMPLE_SIZE"), DEFAULT_SAMPLE_SIZE, len(products))
    token_limit = int(os.environ.get("LLM_TOKEN_LIMIT", str(DEFAULT_TOKEN_LIMIT)))
    descriptions = sample_descriptions(products, baseline["attributes"], sample_size=sample_size)
    prompt = build_llm_additive_rules_prompt(
        descriptions,
        token_profile,
        current_rules,
        max_tokens=token_limit,
        max_descriptions=sample_size,
    )

    STAGE15_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Gemini modo 1: {len(descriptions)} descripciones, {token_limit} tokens candidatos.")
    raw_response = call_gemini(prompt)
    RAW_RESPONSE_PATH.write_text(raw_response, encoding="utf-8")
    try:
        parsed_response = extract_json_object(raw_response)
    except json.JSONDecodeError:
        repaired_response = repair_json_with_gemini(raw_response)
        REPAIRED_RAW_RESPONSE_PATH.write_text(repaired_response, encoding="utf-8")
        try:
            parsed_response = extract_json_object(repaired_response)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Gemini devolvio JSON invalido incluso despues de repararlo. "
                f"Revisa {RAW_RESPONSE_PATH} y {REPAIRED_RAW_RESPONSE_PATH}."
            ) from exc

    additions = sanitize_attribute_rule_additions(parsed_response)
    additions["llm_status"] = "additions_proposed_by_gemini"
    additions["source_model"] = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    merged = merge_attribute_rules(current_rules, additions)
    merged["llm_status"] = "merged_with_gemini_additions"
    merged["source_model"] = additions["source_model"]

    OUTPUT_ADDITIONS_PATH.write_text(
        json.dumps(additions, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    OUTPUT_RULES_PATH.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("Reglas propuestas por Gemini guardadas.")
    print(f"- {OUTPUT_ADDITIONS_PATH}")
    print(f"- {OUTPUT_RULES_PATH}")
    print("Para probarlas sin reemplazar las actuales:")
    print(f'$env:LLM_RULES_PATH="{OUTPUT_RULES_PATH}"')
    print("py .\\etapa1_5_atributos_llm_test.py")


if __name__ == "__main__":
    main()
