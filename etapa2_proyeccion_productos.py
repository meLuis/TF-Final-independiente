from pathlib import Path
import argparse

from core.product_projection import export_projection, run_stage2_projection


BASE_DIR = Path(__file__).parent
STAGE2_OUTPUT_DIR = BASE_DIR / "outputs" / "stage2_graph_datos"


def main() -> None:
    parser = argparse.ArgumentParser(description="Proyeccion producto-producto desde G_attr.")
    parser.add_argument("--input", default=str(STAGE2_OUTPUT_DIR), help="Carpeta con el grafo de Etapa 2")
    parser.add_argument("--output", default=None, help="Carpeta de salida (default: la misma de entrada)")
    parser.add_argument("--hub-fraction", type=float, default=0.35)
    parser.add_argument("--min-similarity", type=float, default=0.30)
    parser.add_argument("--min-shared", type=int, default=2)
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()

    result = run_stage2_projection(
        args.input,
        hub_fraction=args.hub_fraction,
        min_similarity=args.min_similarity,
        min_shared_attributes=args.min_shared,
        top_k=args.top_k,
    )
    paths = export_projection(result, args.output or args.input)
    metrics = result["metrics"]

    print("Proyeccion producto-producto generada.")
    print(f"Productos conectados: {metrics['products_connected']}/{metrics['products_total']}")
    print(f"Aristas de similitud: {metrics['edge_count']}")
    print(f"Atributos hub excluidos: {len(metrics['excluded_hub_attributes'])}")
    for hub in metrics["excluded_hub_attributes"]:
        print(f"- {hub}")
    print(f"Costo de generacion de pares (sum deg^2): {metrics['pair_generation_cost']}")
    print("Outputs:")
    for name, path in paths.items():
        print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
