"""Analisis de sensibilidad del umbral min_confidence de la Etapa 2.

Justifica empiricamente el umbral elegido en lugar de fijarlo por intuicion:
barre valores de min_confidence y reporta como cambian cobertura, aristas,
productos huerfanos y fragmentacion del grafo. El umbral elegido debe estar
en la zona donde el grafo conserva cobertura sin admitir atributos debiles.
"""

from pathlib import Path
import argparse
import json

import pandas as pd

from core.semantic_graph import run_stage2_graph


BASE_DIR = Path(__file__).parent
STAGE1_OUTPUT_DIR = BASE_DIR / "outputs" / "stage1_datos"
STAGE15_OUTPUT_DIR = BASE_DIR / "outputs" / "stage15_datos"
OUTPUT_DIR = BASE_DIR / "outputs" / "stage2_sensitivity"

DEFAULT_THRESHOLDS = [0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]


def main() -> None:
    parser = argparse.ArgumentParser(description="Sensibilidad de min_confidence en G_attr.")
    parser.add_argument("--input", default=str(STAGE15_OUTPUT_DIR))
    parser.add_argument("--stage1", default=str(STAGE1_OUTPUT_DIR))
    parser.add_argument("--output", default=str(OUTPUT_DIR))
    parser.add_argument("--thresholds", type=float, nargs="*", default=DEFAULT_THRESHOLDS)
    args = parser.parse_args()

    rows = []
    for threshold in args.thresholds:
        metrics = run_stage2_graph(args.input, args.stage1, min_confidence=threshold)["metrics"]
        rows.append(
            {
                "min_confidence": threshold,
                "node_count": metrics["node_count"],
                "edge_count": metrics["edge_count"],
                "products_with_edges": metrics["products_with_attribute_edges"],
                "products_orphan": metrics["products_without_attribute_edges"],
                "orphan_rate": round(
                    metrics["products_without_attribute_edges"] / max(metrics["products_total"], 1), 4
                ),
                "connected_components": metrics["connected_components"],
                "largest_component": metrics["largest_component_size"],
            }
        )

    table = pd.DataFrame(rows)
    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)
    csv_path = output_path / "min_confidence_sensitivity.csv"
    table.to_csv(csv_path, index=False, encoding="utf-8-sig")
    (output_path / "min_confidence_sensitivity.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("Sensibilidad de min_confidence (gating por atributo):")
    print(table.to_string(index=False))
    print(f"\nGuardado en: {csv_path}")


if __name__ == "__main__":
    main()
