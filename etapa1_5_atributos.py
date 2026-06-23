from pathlib import Path

from core.attribute_extractor import export_stage15, run_stage15


BASE_DIR = Path(__file__).parent
STAGE1_OUTPUT_DIR = BASE_DIR / "outputs" / "stage1_datos"
STAGE15_OUTPUT_DIR = BASE_DIR / "outputs" / "stage15_datos"
CATALOG_PATH = BASE_DIR / "data" / "base" / "catalogo.csv"


def main() -> None:
    result = run_stage15(STAGE1_OUTPUT_DIR, CATALOG_PATH)
    paths = export_stage15(result, STAGE15_OUTPUT_DIR)

    coverage = result["coverage_report"]
    comparison = result["comparison_summary"]

    print("Etapa 1.5 ejecutada sobre outputs/stage1_datos.")
    print(f"Productos procesados: {len(result['attributes'])}")
    print(f"Confianza promedio: {result['attributes']['confidence'].mean():.2%}")
    print("Cobertura principal:")
    for attribute in ("product_type", "material", "color", "capacity_value", "mouth_size_mm"):
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

    print("Outputs utiles:")
    for name in (
        "product_attributes.csv",
        "attribute_coverage_report.csv",
        "attribute_review_sample.csv",
        "attribute_unvalidated_sample.csv",
        "attribute_gold_comparison_summary.csv",
        "attribute_gold_comparison_detail.csv",
        "attribute_rules.json",
    ):
        if name in paths:
            print(f"- {name}: {paths[name]}")


if __name__ == "__main__":
    main()
