from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from core.attribute_extractor import export_stage15, run_stage15
from core.semantic_retrievability import (
    build_retrievability_summary,
    build_semantic_retrievability_report,
)


BASE_DIR = Path(__file__).parent
STAGE1_OUTPUT_DIR = BASE_DIR / "outputs" / "stage1_datos"
STAGE15_OUTPUT_DIR = BASE_DIR / "outputs" / "stage15_datos"
STAGE15_FINAL_DIR = BASE_DIR / "outputs" / "stage15_final"
STAGE15_REJECTED_DIR = BASE_DIR / "outputs" / "stage15_final_rejected"
BASELINE_RULES_PATH = STAGE15_OUTPUT_DIR / "attribute_rules.json"
GEMINI_RULES_PATH = STAGE15_OUTPUT_DIR / "attribute_rules_gemini_merged.json"
CATALOG_PATH = BASE_DIR / "data" / "base" / "catalogo.csv"

CRITICAL_ATTRIBUTES = [
    "product_type",
    "material",
    "color",
    "capacity_value",
    "mouth_size_mm",
]
SEMANTIC_ATTRIBUTES = ["subtype", "accessory", "shape", "feature"]


def metric_value(summary: pd.DataFrame, attribute: str, column: str) -> float:
    if summary.empty:
        return 0.0
    row = summary.loc[summary["attribute"] == attribute]
    if row.empty:
        return 0.0
    value = row.iloc[0].get(column)
    if pd.isna(value):
        return 0.0
    return float(value)


def coverage_value(coverage: pd.DataFrame, attribute: str) -> float:
    row = coverage.loc[coverage["attribute"] == attribute]
    if row.empty:
        return 0.0
    return float(row.iloc[0]["coverage"])


def build_delta_report(baseline: pd.DataFrame, candidate: pd.DataFrame) -> pd.DataFrame:
    base = baseline.copy()
    cand = candidate.copy()
    base["product_id"] = base["product_id"].astype(str)
    cand["product_id"] = cand["product_id"].astype(str)
    merged = base.merge(cand, on="product_id", suffixes=("_baseline", "_llm"), how="inner")
    attributes = [
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
    rows = []
    for _, row in merged.iterrows():
        for attr in attributes:
            base_value = "" if pd.isna(row.get(f"{attr}_baseline")) else str(row.get(f"{attr}_baseline")).strip()
            llm_value = "" if pd.isna(row.get(f"{attr}_llm")) else str(row.get(f"{attr}_llm")).strip()
            if base_value == llm_value:
                continue
            change_type = "changed_by_llm"
            if not base_value and llm_value:
                change_type = "filled_by_llm"
            elif base_value and not llm_value:
                change_type = "removed_by_llm"
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


def compare_acceptance(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    baseline_retrievability: dict[str, Any],
    candidate_retrievability: dict[str, Any],
) -> dict[str, Any]:
    checks = []
    for attr in CRITICAL_ATTRIBUTES:
        baseline_accuracy = metric_value(baseline["comparison_summary"], attr, "accuracy_on_both_filled")
        candidate_accuracy = metric_value(candidate["comparison_summary"], attr, "accuracy_on_both_filled")
        checks.append(
            {
                "check": f"{attr}_accuracy_no_regression",
                "passed": candidate_accuracy >= baseline_accuracy,
                "baseline": baseline_accuracy,
                "candidate": candidate_accuracy,
            }
        )

    baseline_confidence = float(baseline["attributes"]["confidence"].mean())
    candidate_confidence = float(candidate["attributes"]["confidence"].mean())
    checks.append(
        {
            "check": "avg_confidence_no_regression",
            "passed": candidate_confidence >= baseline_confidence,
            "baseline": baseline_confidence,
            "candidate": candidate_confidence,
        }
    )

    semantic_improvements = []
    for attr in SEMANTIC_ATTRIBUTES:
        baseline_coverage = coverage_value(baseline["coverage_report"], attr)
        candidate_coverage = coverage_value(candidate["coverage_report"], attr)
        semantic_improvements.append(candidate_coverage > baseline_coverage)
        checks.append(
            {
                "check": f"{attr}_coverage",
                "passed": candidate_coverage >= baseline_coverage,
                "baseline": baseline_coverage,
                "candidate": candidate_coverage,
            }
        )

    checks.append(
        {
            "check": "semantic_coverage_improved",
            "passed": any(semantic_improvements),
            "baseline": "",
            "candidate": "",
        }
    )
    checks.append(
        {
            "check": "retrievability_top5_no_regression",
            "passed": candidate_retrievability["top5_rate"] >= baseline_retrievability["top5_rate"],
            "baseline": baseline_retrievability["top5_rate"],
            "candidate": candidate_retrievability["top5_rate"],
        }
    )
    checks.append(
        {
            "check": "retrievability_score_no_regression",
            "passed": candidate_retrievability["avg_retrievability_score"]
            >= baseline_retrievability["avg_retrievability_score"],
            "baseline": baseline_retrievability["avg_retrievability_score"],
            "candidate": candidate_retrievability["avg_retrievability_score"],
        }
    )

    accepted = all(bool(check["passed"]) for check in checks)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "conservative",
        "accepted": accepted,
        "checks": checks,
        "baseline_retrievability": baseline_retrievability,
        "candidate_retrievability": candidate_retrievability,
    }


def write_extra_outputs(
    output_dir: Path,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    acceptance: dict[str, Any],
) -> dict[str, str]:
    paths: dict[str, str] = {}
    delta = build_delta_report(baseline["attributes"], candidate["attributes"])
    delta_path = output_dir / "attribute_llm_delta.csv"
    delta.to_csv(delta_path, index=False, encoding="utf-8-sig")
    paths["attribute_llm_delta.csv"] = str(delta_path)

    retrievability = build_semantic_retrievability_report(candidate["attributes"])
    retrievability_path = output_dir / "semantic_retrievability_report.csv"
    retrievability.to_csv(retrievability_path, index=False, encoding="utf-8-sig")
    paths["semantic_retrievability_report.csv"] = str(retrievability_path)

    retrievability_summary_path = output_dir / "semantic_retrievability_summary.json"
    retrievability_summary_path.write_text(
        json.dumps(build_retrievability_summary(retrievability), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    paths["semantic_retrievability_summary.json"] = str(retrievability_summary_path)

    acceptance_path = output_dir / "llm_acceptance_summary.json"
    acceptance_path.write_text(json.dumps(acceptance, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["llm_acceptance_summary.json"] = str(acceptance_path)
    return paths


def replace_output_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def main() -> None:
    if not GEMINI_RULES_PATH.exists():
        raise FileNotFoundError(f"No existe {GEMINI_RULES_PATH}. Ejecuta etapa1_5_atributos_llm_gemini.py primero.")

    baseline = run_stage15(STAGE1_OUTPUT_DIR, CATALOG_PATH, rules_path=BASELINE_RULES_PATH)
    candidate = run_stage15(STAGE1_OUTPUT_DIR, CATALOG_PATH, rules_path=GEMINI_RULES_PATH)
    baseline_report = build_semantic_retrievability_report(baseline["attributes"])
    candidate_report = build_semantic_retrievability_report(candidate["attributes"])
    baseline_retrievability = build_retrievability_summary(baseline_report)
    candidate_retrievability = build_retrievability_summary(candidate_report)
    acceptance = compare_acceptance(
        baseline,
        candidate,
        baseline_retrievability,
        candidate_retrievability,
    )

    output_dir = STAGE15_FINAL_DIR if acceptance["accepted"] else STAGE15_REJECTED_DIR
    replace_output_dir(output_dir)
    paths = export_stage15(candidate if acceptance["accepted"] else baseline, output_dir)
    paths.update(write_extra_outputs(output_dir, baseline, candidate, acceptance))

    status = "ACEPTADO" if acceptance["accepted"] else "RECHAZADO"
    print(f"Finalizacion Stage 1.5: {status}")
    print(f"Carpeta: {output_dir}")
    print(f"Recuperabilidad baseline top5: {baseline_retrievability['top5_rate']:.2%}")
    print(f"Recuperabilidad Gemini top5: {candidate_retrievability['top5_rate']:.2%}")
    print("Checks:")
    for check in acceptance["checks"]:
        marker = "OK" if check["passed"] else "FAIL"
        print(f"- {marker}: {check['check']} ({check['baseline']} -> {check['candidate']})")
    print("Outputs:")
    for name, path in paths.items():
        print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
