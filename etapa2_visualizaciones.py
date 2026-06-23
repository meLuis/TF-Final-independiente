from pathlib import Path
import argparse

from core.graph_visualizer import render_graph_visualizations


BASE_DIR = Path(__file__).parent
STAGE2_OUTPUT_DIR = BASE_DIR / "outputs" / "stage2_graph_datos"
VIS_OUTPUT_DIR = BASE_DIR / "outputs" / "stage2_graph_datos" / "visualizations"


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera PNGs estaticos de G_attr.")
    parser.add_argument("--input", default=str(STAGE2_OUTPUT_DIR), help="Carpeta con tablas del grafo")
    parser.add_argument("--output", default="", help="Carpeta para PNGs")
    args = parser.parse_args()
    output_dir = args.output or str(Path(args.input) / "visualizations")
    paths = render_graph_visualizations(args.input, output_dir)
    print("Visualizaciones de G_attr generadas.")
    for name, path in paths.items():
        print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
