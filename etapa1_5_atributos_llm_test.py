from pathlib import Path

import pandas as pd

from core.attribute_extractor import export_stage15, run_stage15
from core.semantic_retrievability import (
    build_retrievability_summary,
    build_semantic_retrievability_report,
)


BASE_DIR = Path(__file__).parent
STAGE1_OUTPUT_DIR = BASE_DIR / "outputs" / "stage1_datos"
CATALOG_PATH = BASE_DIR / "data" / "base" / "catalogo.csv"
BASELINE_RULES_PATH = BASE_DIR / "outputs" / "stage15_datos" / "attribute_rules.json"
DEFAULT_LLM_RULES_PATH = BASE_DIR / "outputs" / "stage15_datos" / "attribute_rules_gemini_merged.json"
DELTA_ATTRIBUTES = [
    "product_type",
    "subtype",
    "accessory",
    "shape",
    "feature",
    "material",
    "color",
    "capacity_value",
    "capacity_unit",
    "mouth_size_mm",
    "use_category",
    "material_family",
]


def output_dir_for_rules(rules_path: Path) -> Path:
    stem = rules_path.stem.lower()
    if "gemini" in stem:
        provider = "gemini"
    else:
        provider = "custom"
    return BASE_DIR / "outputs" / f"stage15_datos_llm_test_{provider}"


def comparable(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def build_delta_report(baseline: pd.DataFrame, candidate: pd.DataFrame) -> pd.DataFrame:
    base = baseline.copy()
    cand = candidate.copy()
    base["product_id"] = base["product_id"].astype(str)
    cand["product_id"] = cand["product_id"].astype(str)
    merged = base.merge(
        cand,
        on="product_id",
        suffixes=("_baseline", "_llm"),
        how="inner",
    )

    rows = []
    for _, row in merged.iterrows():
        for attr in DELTA_ATTRIBUTES:
            base_value = comparable(row.get(f"{attr}_baseline"))
            llm_value = comparable(row.get(f"{attr}_llm"))
            if base_value == llm_value:
                continue
            if not base_value and llm_value:
                change_type = "filled_by_llm"
            elif base_value and not llm_value:
                change_type = "removed_by_llm"
            else:
                change_type = "changed_by_llm"
            rows.append(
                {
                    "product_id": row["product_id"],
                    "product_name": row.get("product_name_llm", row.get("product_name_baseline", "")),
                    "attribute": attr,
                    "baseline_value": base_value,
                    "llm_value": llm_value,
                    "change_type": change_type,
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    import os

    llm_rules_path = Path(os.environ.get("LLM_RULES_PATH", str(DEFAULT_LLM_RULES_PATH)))
    output_dir = output_dir_for_rules(llm_rules_path)
    baseline = run_stage15(STAGE1_OUTPUT_DIR, CATALOG_PATH, rules_path=BASELINE_RULES_PATH)
    result = run_stage15(STAGE1_OUTPUT_DIR, CATALOG_PATH, rules_path=llm_rules_path)
    paths = export_stage15(result, output_dir)
    delta = build_delta_report(baseline["attributes"], result["attributes"])
    delta_path = output_dir / "attribute_llm_delta.csv"
    delta.to_csv(delta_path, index=False, encoding="utf-8-sig")
    paths["attribute_llm_delta.csv"] = str(delta_path)
    retrievability = build_semantic_retrievability_report(result["attributes"])
    retrievability_path = output_dir / "semantic_retrievability_report.csv"
    retrievability.to_csv(retrievability_path, index=False, encoding="utf-8-sig")
    paths["semantic_retrievability_report.csv"] = str(retrievability_path)
    retrievability_summary = build_retrievability_summary(retrievability)

    coverage = result["coverage_report"]
    comparison = result["comparison_summary"]

    print(f"Etapa 1.5 test ejecutada con {llm_rules_path.name}.")
    print(f"Carpeta de comparacion: {output_dir}")
    print(f"Productos procesados: {len(result['attributes'])}")
    print(f"Cambios vs baseline: {len(delta)}")
    print(f"Confianza promedio: {result['attributes']['confidence'].mean():.2%}")
    print(
        "Recuperabilidad: "
        f"score={retrievability_summary['avg_retrievability_score']:.2%}, "
        f"top5={retrievability_summary['top5_rate']:.2%}"
    )
    print("Cobertura principal:")
    for attribute in (
        "product_type",
        "subtype",
        "accessory",
        "shape",
        "feature",
        "material",
        "color",
        "capacity_value",
        "mouth_size_mm",
    ):
        row = coverage.loc[coverage["attribute"] == attribute]
        if not row.empty:
            print(f"- {attribute}: {float(row.iloc[0]['coverage']):.2%}")

    if not comparison.empty:
        print("Comparacion contra datos/catalogo.csv:")
        for _, row in comparison.iterrows():
            accuracy = row["accuracy_on_both_filled"]
            recall = row["recall_against_expected"]
            accuracy_text = "n/a" if accuracy is None else f"{float(accuracy):.2%}"
            print(f"- {row['attribute']}: accuracy={accuracy_text}, recall={float(recall):.2%}")

    print("Outputs:")
    for name, path in paths.items():
        print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
