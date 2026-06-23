from pathlib import Path
import argparse

from core.semantic_graph import export_stage2_graph, run_stage2_graph


BASE_DIR = Path(__file__).parent
STAGE1_OUTPUT_DIR = BASE_DIR / "outputs" / "stage1_datos"
STAGE15_OUTPUT_DIR = BASE_DIR / "outputs" / "stage15_datos"
STAGE2_OUTPUT_DIR = BASE_DIR / "outputs" / "stage2_graph_datos"


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera G_attr desde outputs de Stage 1.5.")
    parser.add_argument("--input", default=str(STAGE15_OUTPUT_DIR), help="Carpeta con product_attributes.csv")
    parser.add_argument("--output", default=str(STAGE2_OUTPUT_DIR), help="Carpeta de salida del grafo")
    parser.add_argument("--stage1", default=str(STAGE1_OUTPUT_DIR), help="Carpeta de Stage 1 para actividad")
    parser.add_argument("--min-confidence", type=float, default=0.75)
    args = parser.parse_args()

    result = run_stage2_graph(
        args.input,
        args.stage1,
        min_confidence=args.min_confidence,
    )
    paths = export_stage2_graph(result, args.output)
    metrics = result["metrics"]

    print("Etapa 2 ejecutada: G_attr / semantic_attribute_graph.")
    print(f"Nodos: {metrics['node_count']}")
    print(f"Aristas: {metrics['edge_count']}")
    print(f"Productos con atributos: {metrics['products_with_attribute_edges']}/{metrics['products_total']}")
    print(f"Componentes conectados: {metrics['connected_components']}")
    print(f"Componente mayor: {metrics['largest_component_size']} nodos")
    print("Nodos por tipo:")
    for node_type, count in metrics["node_type_counts"].items():
        print(f"- {node_type}: {count}")
    print("Aristas por relacion:")
    for relation, count in metrics["relation_counts"].items():
        print(f"- {relation}: {count}")
    print("Outputs:")
    for name, path in paths.items():
        print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
