"""Etapa 6 - Bellman-Ford para ahorros historicos y ofertas simulables."""





#implementar una caja de texto que reciba (usando fuzzy wuzzy y regular expressions)









from __future__ import annotations

import argparse
from pathlib import Path

from core.bellman_ford_offers import (
    export_bellman_ford_offer_analysis,
    run_bellman_ford_offer_analysis,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera CSVs para Bellman-Ford desde las compras limpias."
    )
    parser.add_argument(
        "--stage1",
        default="outputs/stage1_datos",
        help="Directorio con purchases_clean.csv generado por Etapa 1.",
    )
    parser.add_argument(
        "--output",
        default="outputs/stage6_bellman_ford",
        help="Directorio de salida para candidates, edges, best_paths y summary.",
    )
    args = parser.parse_args()

    result = run_bellman_ford_offer_analysis(Path(args.stage1))
    paths = export_bellman_ford_offer_analysis(result, Path(args.output))

    print("Bellman-Ford listo.")
    for name, path in paths.items():
        print(f"- {name}: {path}")
    print("Resumen:", result["summary"])


if __name__ == "__main__":
    main()

