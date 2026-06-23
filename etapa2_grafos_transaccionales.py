from pathlib import Path
import argparse

from core.transaction_graphs import export_transaction_graphs, run_transaction_graphs


BASE_DIR = Path(__file__).parent
STAGE1_OUTPUT_DIR = BASE_DIR / "outputs" / "stage1_datos"
OUTPUT_DIR = BASE_DIR / "outputs" / "stage2_transaction_graphs"


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera G_purchases, G_sales y G_business desde Etapa 1.")
    parser.add_argument("--input", default=str(STAGE1_OUTPUT_DIR), help="Carpeta con *_clean.csv de Etapa 1")
    parser.add_argument("--output", default=str(OUTPUT_DIR), help="Carpeta de salida")
    args = parser.parse_args()

    graphs = run_transaction_graphs(args.input)
    paths = export_transaction_graphs(graphs, args.output)

    for kind in ("purchases", "sales", "business"):
        metrics = graphs[kind]["metrics"]
        print(f"\n{metrics['graph_name']}:")
        print(f"  Nodos: {metrics['node_count']}")
        print(f"  Aristas: {metrics['edge_count']}")
        print(f"  Componentes: {metrics['connected_components']} (mayor: {metrics['largest_component_size']})")
        for node_type, count in metrics["node_type_counts"].items():
            print(f"  - {node_type}: {count}")

    print("\nOutputs:")
    for name, path in paths.items():
        print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
