from pathlib import Path

import pandas as pd

from core.pipeline import export_stage1, read_table_flexible, run_stage1


BASE_DIR = Path(__file__).parent
CSV_DEMO_DIR = BASE_DIR / "data" / "demo" / "ferreteria"
XLSX_DEMO_DIR = BASE_DIR / "outputs" / "stage1_excel_smoke_input"
OUTPUT_DIR = BASE_DIR / "outputs" / "stage1_excel_smoke"


def main() -> None:
    XLSX_DEMO_DIR.mkdir(parents=True, exist_ok=True)
    files = {
        "products": ("productos.csv", "productos.xlsx"),
        "sales": ("ventas.csv", "ventas.xlsx"),
        "purchases": ("compras.csv", "compras.xlsx"),
    }

    dataframes = {}
    for key, (csv_name, xlsx_name) in files.items():
        csv_path = CSV_DEMO_DIR / csv_name
        xlsx_path = XLSX_DEMO_DIR / xlsx_name
        df = pd.read_csv(csv_path, sep=";")
        df.to_excel(xlsx_path, index=False)
        dataframes[key] = read_table_flexible(xlsx_path)

    result = run_stage1(dataframes)
    export_stage1(result, OUTPUT_DIR)

    print("Smoke test XLSX procesado correctamente.")
    print(f"Confianza columnas: {result['report']['column_mapping_confidence']:.2%}")
    print(f"Coverage matching: {result['report']['product_match_coverage']:.2%}")


if __name__ == "__main__":
    main()

