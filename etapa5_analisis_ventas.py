"""Etapa 5 - Analisis de ventas: Leiden, Personalized PageRank, ABC, co-venta.

Corre los cuatro analisis sobre los outputs ya generados (Etapas 1, 2 y
proyeccion) y exporta tablas + metricas a outputs/stage5_analisis/.
"""

from pathlib import Path
import argparse
import json

import pandas as pd

from core.community_leiden import describe_communities, detect_communities, export_communities
from core.pagerank_personalized import PageRankEngine
from core.sales_reports import run_sales_reports


BASE_DIR = Path(__file__).parent
STAGE1_OUTPUT_DIR = BASE_DIR / "outputs" / "stage1_datos"
STAGE2_GRAPH_DIR = BASE_DIR / "outputs" / "stage2_graph_datos"
TRANSACTION_DIR = BASE_DIR / "outputs" / "stage2_transaction_graphs"
OUTPUT_DIR = BASE_DIR / "outputs" / "stage5_analisis"


def main() -> None:
    parser = argparse.ArgumentParser(description="Analisis de ventas y reportes (Etapa 5).")
    parser.add_argument("--stage1", default=str(STAGE1_OUTPUT_DIR))
    parser.add_argument("--graph", default=str(STAGE2_GRAPH_DIR))
    parser.add_argument("--transactions", default=str(TRANSACTION_DIR))
    parser.add_argument("--output", default=str(OUTPUT_DIR))
    parser.add_argument("--related-to", default=None, help="product_id para demo de PPR")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)

    # 1) Leiden sobre la proyeccion producto-producto.
    projection_edges = pd.read_csv(
        Path(args.graph) / "product_projection_edges.csv", encoding="utf-8-sig"
    )
    communities = detect_communities(projection_edges)
    descriptions = describe_communities(communities["membership"])
    export_communities(communities, descriptions, output_path)
    metrics = communities["metrics"]
    print("Leiden vs componentes conexos:")
    print(f"  comunidades Leiden: {metrics['leiden_communities']} (modularidad {metrics['leiden_modularity']})")
    print(f"  componentes conexos (baseline): {metrics['baseline_connected_components']}")
    print(f"  comunidad mayor: {metrics['largest_leiden_community']} vs componente mayor {metrics['largest_connected_component']}")
    print("  familias detectadas (top 5):")
    for _, row in descriptions.head(5).iterrows():
        print(f"  - [{row['size']} productos] {row['top_terms']}")

    # 2) PageRank global + PPR demo.
    engine = PageRankEngine.from_transaction_dir(args.transactions)
    global_rank = engine.pagerank()
    top_products = engine.top_nodes(global_rank, {"PRODUCT"}, k=15)
    top_clients = engine.top_nodes(global_rank, {"CLIENT"}, k=15)
    top_products.to_csv(output_path / "pagerank_top_products.csv", index=False, encoding="utf-8-sig")
    top_clients.to_csv(output_path / "pagerank_top_clients.csv", index=False, encoding="utf-8-sig")
    print("\nPageRank global — top 5 productos:")
    for _, row in top_products.head(5).iterrows():
        print(f"  - {row['label']} ({row['score']})")

    demo_product = f"PRODUCT:{args.related_to}" if args.related_to else top_products.iloc[0]["node_id"]
    related = engine.related_products(demo_product, k=10)
    baseline = engine.cooccurrence_baseline(demo_product, k=10)
    related.to_csv(output_path / "ppr_related_products.csv", index=False, encoding="utf-8-sig")
    baseline.to_csv(output_path / "ppr_baseline_cooccurrence.csv", index=False, encoding="utf-8-sig")
    print(f"\nPPR — relacionados a {engine.labels.get(demo_product, demo_product)}:")
    for _, row in related.head(5).iterrows():
        print(f"  - {row['label']} ({row['score']})")
    print(f"  (baseline co-ocurrencia encontro {len(baseline)} productos; PPR puntua {len(related)} via multi-salto)")

    # 3) ABC + co-venta + dependencia.
    reports = run_sales_reports(args.stage1)
    for name, table in reports.items():
        table.to_csv(output_path / f"{name}.csv", index=False, encoding="utf-8-sig")
    abc_counts = reports["abc"]["abc_class"].value_counts().to_dict()
    print(f"\nABC: {abc_counts} | co-ventas top: {len(reports['co_sales'])} pares")
    print(f"Dependencia — proveedor top: {reports['supplier_dependency'].iloc[0]['supplier']} "
          f"({reports['supplier_dependency'].iloc[0]['value_share']:.0%} del valor, "
          f"alerta {reports['supplier_dependency'].iloc[0]['alert']})")

    summary = {
        "leiden": metrics,
        "abc_classes": abc_counts,
        "ppr_demo_product": demo_product,
        "outputs_dir": str(output_path),
    }
    (output_path / "stage5_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nOutputs en: {output_path}")


if __name__ == "__main__":
    main()
