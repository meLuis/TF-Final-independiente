"""Prueba de generalidad: pipeline completo con el dataset demo de ferreteria.

Corre Etapas 1, 1.5, 2 (grafo + proyeccion + grafos transaccionales) y los
analisis de Etapa 5 sobre data/demo/ferreteria **sin tocar codigo**: es la
evidencia de que el motor no esta hardcodeado para Vidra Plastic.
"""

from pathlib import Path

import pandas as pd

from core.attribute_extractor import export_stage15, run_stage15
from core.pipeline import export_stage1, read_table_flexible, run_stage1
from core.product_projection import export_projection, run_stage2_projection
from core.sales_reports import run_sales_reports
from core.semantic_graph import export_stage2_graph, run_stage2_graph
from core.semantic_search import SemanticSearchIndex
from core.transaction_graphs import export_transaction_graphs, run_transaction_graphs


BASE_DIR = Path(__file__).parent
DEMO_DIR = BASE_DIR / "data" / "demo" / "ferreteria"
OUT = BASE_DIR / "outputs" / "ferreteria_full"


def main() -> None:
    print("=== Etapa 1: ingesta y normalizacion ===")
    dataframes = {
        "products": read_table_flexible(DEMO_DIR / "productos.csv"),
        "sales": read_table_flexible(DEMO_DIR / "ventas.csv"),
        "purchases": read_table_flexible(DEMO_DIR / "compras.csv"),
    }
    stage1 = run_stage1(dataframes)
    export_stage1(stage1, OUT / "stage1")
    print(f"  confianza columnas: {stage1['report']['column_mapping_confidence']:.2%}")

    print("=== Etapa 1.5: extraccion de atributos ===")
    stage15 = run_stage15(OUT / "stage1")
    export_stage15(stage15, OUT / "stage15")
    print(f"  productos: {len(stage15['attributes'])} | confianza media: {stage15['attributes']['confidence'].mean():.2%}")

    print("=== Etapa 2: G_attr + proyeccion ===")
    graph = run_stage2_graph(OUT / "stage15", OUT / "stage1")
    export_stage2_graph(graph, OUT / "stage2")
    print(f"  G_attr: {graph['metrics']['node_count']} nodos, {graph['metrics']['edge_count']} aristas")
    projection = run_stage2_projection(OUT / "stage2", min_shared_attributes=1)
    export_projection(projection, OUT / "stage2")
    print(f"  proyeccion: {projection['metrics']['edge_count']} aristas de similitud")

    print("=== Etapa 2: grafos transaccionales ===")
    graphs = run_transaction_graphs(OUT / "stage1")
    export_transaction_graphs(graphs, OUT / "stage2_transactions")
    for kind in ("purchases", "sales", "business"):
        m = graphs[kind]["metrics"]
        print(f"  {m['graph_name']}: {m['node_count']} nodos, {m['edge_count']} aristas")

    print("=== Etapa 3: busqueda semantica ===")
    index = SemanticSearchIndex.from_frames(graph["nodes"], graph["edges"])
    sample = pd.read_csv(OUT / "stage1" / "products_clean.csv", encoding="utf-8-sig")["product_name"].iloc[0]
    query = " ".join(str(sample).split()[:3])
    results = index.search(query, k=3)
    print(f"  query '{query}' -> {len(results)} resultados")
    for r in results:
        print(f"   - {r['label']} (rel {r['relevance']})")

    print("=== Etapa 5: reportes ===")
    reports = run_sales_reports(OUT / "stage1")
    print(f"  ABC: {reports['abc']['abc_class'].value_counts().to_dict()}")
    print(f"  co-ventas: {len(reports['co_sales'])} pares | proveedores: {len(reports['supplier_dependency'])}")

    print(f"\nPipeline completo OK sin codigo especifico del dominio. Outputs: {OUT}")


if __name__ == "__main__":
    main()
