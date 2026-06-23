from pathlib import Path

from core.pipeline import export_stage1, read_table_flexible, run_stage1


BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data" / "base"
OUTPUT_DIR = BASE_DIR / "outputs" / "stage1_datos"


def main() -> None:
    dataframes = {
        "products": read_table_flexible(DATA_DIR / "productos.xlsx"),
        "sales": read_table_flexible(DATA_DIR / "ventas.xlsx"),
        "purchases": read_table_flexible(DATA_DIR / "items_compras.xlsx"),
    }
    result = run_stage1(dataframes)
    paths = export_stage1(result, OUTPUT_DIR)

    print("Etapa 1 procesada con datos/*.xlsx.")
    print(f"Confianza columnas: {result['report']['column_mapping_confidence']:.2%}")
    print(f"Coverage matching: {result['report']['product_match_coverage']:.2%}")
    print("Tablas utiles:")
    for name in (
        "quality_summary.csv",
        "transaction_flags_summary.csv",
        "product_activity_summary.csv",
        "code_pattern_summary.csv",
    ):
        print(f"- {name}: {paths[name]}")


if __name__ == "__main__":
    main()

