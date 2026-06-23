from pathlib import Path

from core.pipeline import export_stage1, read_table_flexible, run_stage1


BASE_DIR = Path(__file__).parent
DEMO_DIR = BASE_DIR / "data" / "demo" / "ferreteria"
OUTPUT_DIR = BASE_DIR / "outputs" / "stage1_demo_ferreteria"


def main() -> None:
    dataframes = {
        "products": read_table_flexible(DEMO_DIR / "productos.csv"),
        "sales": read_table_flexible(DEMO_DIR / "ventas.csv"),
        "purchases": read_table_flexible(DEMO_DIR / "compras.csv"),
    }
    result = run_stage1(dataframes)
    paths = export_stage1(result, OUTPUT_DIR)

    print("Etapa 1 procesada correctamente.")
    print(f"Confianza columnas: {result['report']['column_mapping_confidence']:.2%}")
    print(f"Coverage matching: {result['report']['product_match_coverage']:.2%}")
    print("Archivos exportados:")
    for name, path in paths.items():
        print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
