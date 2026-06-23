"""Seccion 11 - Reportes ejecutivos y vista tecnica.

Contiene lo que no encaja 1:1 en las otras secciones, garantizando que ninguna
funcionalidad previa se pierda:
- Rankings PageRank global, ABC (Pareto) y co-venta (antes en 5_Reportes).
- Explorador generico de conexiones entre dos entidades cualesquiera (antes en
  3_Conexiones_y_Rutas: BFS vs BFS bidireccional sobre G_business).
- Sensibilidad del umbral de confianza (Etapa 2).
- Comparacion antes/despues del LLM (grafo deterministas vs grafo + Gemini).
"""

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from core.assistant.loaders import (
    STAGE2_GRAPH_DIR,
    STAGE5_DIR,
    load_paths,
    tx_ready,
)

st.set_page_config(page_title="Reportes y vista tecnica", layout="wide")
st.title("11. Reportes ejecutivos y vista tecnica")
st.caption("Reportes precalculados, explorador de conexiones y comparativas para sustentacion.")

BASE = Path(__file__).parent.parent
SENSITIVITY = BASE / "outputs" / "stage2_sensitivity" / "min_confidence_sensitivity.csv"
GRAPH_FINAL_METRICS = BASE / "outputs" / "stage2_graph_final" / "semantic_attribute_graph_metrics.json"
GRAPH_DATOS_METRICS = STAGE2_GRAPH_DIR / "semantic_attribute_graph_metrics.json"


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig") if path.exists() else pd.DataFrame()


tab_rank, tab_abc, tab_conn, tab_sens, tab_llm = st.tabs(
    ["Relevancia (PageRank)", "ABC y co-venta", "Explorador de conexiones", "Sensibilidad umbral", "Antes/despues LLM"]
)

with tab_rank:
    st.caption("PageRank global sobre G_business: importancia estructural, no solo frecuencia.")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Productos")
        st.dataframe(_read_csv(STAGE5_DIR / "pagerank_top_products.csv"), use_container_width=True, hide_index=True)
    with col2:
        st.subheader("Clientes")
        st.dataframe(_read_csv(STAGE5_DIR / "pagerank_top_clients.csv"), use_container_width=True, hide_index=True)
    st.subheader("Relacionados via Personalized PageRank")
    st.dataframe(_read_csv(STAGE5_DIR / "ppr_related_products.csv"), use_container_width=True, hide_index=True)

with tab_abc:
    abc = _read_csv(STAGE5_DIR / "abc.csv")
    if not abc.empty:
        counts = abc["abc_class"].value_counts()
        col1, col2, col3 = st.columns(3)
        col1.metric("Clase A (80% del valor)", int(counts.get("A", 0)))
        col2.metric("Clase B (15%)", int(counts.get("B", 0)))
        col3.metric("Clase C (5%)", int(counts.get("C", 0)))
        st.dataframe(abc.head(100), use_container_width=True, hide_index=True)
    else:
        st.info("Genera los reportes: py etapa5_analisis_ventas.py")
    st.subheader("Co-venta (mismo cliente, mismo dia)")
    st.dataframe(_read_csv(STAGE5_DIR / "co_sales.csv"), use_container_width=True, hide_index=True)

with tab_conn:
    st.caption(
        "BFS clasico vs BFS bidireccional entre DOS entidades cualesquiera "
        "(cliente, producto o proveedor) sobre G_business."
    )
    if not tx_ready():
        st.warning("Primero genera los grafos: py etapa2_grafos_transaccionales.py")
    else:
        graph = load_paths()
        col1, col2 = st.columns(2)
        source_text = col1.text_input("Entidad origen", placeholder="ej. ODONTOLOGIA SAN ANTONIO")
        target_text = col2.text_input("Entidad destino", placeholder="ej. ENVIPLAST")
        if source_text and target_text:
            result = graph.compare(source_text, target_text)
            if "error" in result:
                st.error(
                    f"{result['error']} (origen: {result['source_resolved']}, "
                    f"destino: {result['target_resolved']})"
                )
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric("BFS expandio", result["bfs"]["expanded_nodes"])
                c2.metric("Bidireccional expandio", result["bidirectional_bfs"]["expanded_nodes"])
                c3.metric("Ratio de mejora", f"{result['expansion_ratio']}x")
                if result["bidirectional_bfs"]["found"]:
                    st.write("**Camino encontrado:**")
                    for step in result["bidirectional_bfs"]["path_labels"]:
                        st.write(f"- {step}")
                else:
                    st.info("No hay conexion entre esas entidades.")

with tab_sens:
    st.caption("Como cambia G_attr al mover el umbral de confianza (justifica el valor elegido).")
    sens = _read_csv(SENSITIVITY)
    if sens.empty:
        st.info("Genera la sensibilidad: py etapa2_sensibilidad_umbral.py")
    else:
        st.dataframe(sens, use_container_width=True, hide_index=True)
        if {"min_confidence", "orphan_rate"}.issubset(sens.columns):
            st.line_chart(sens.set_index("min_confidence")[["orphan_rate"]])

with tab_llm:
    st.caption("Grafo con reglas deterministas (sin LLM) vs grafo enriquecido con Gemini.")

    def _metrics(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    sin_llm = _metrics(GRAPH_DATOS_METRICS)
    con_llm = _metrics(GRAPH_FINAL_METRICS)
    if not sin_llm:
        st.info("Genera el grafo base: py etapa2_grafo_semantico.py")
    elif not con_llm:
        st.info("Genera el track LLM (ver GUIA seccion 4) para comparar antes/despues.")
    else:
        rows = []
        for key in ("node_count", "edge_count", "products_with_attribute_edges", "products_without_attribute_edges"):
            rows.append({"metrica": key, "sin_LLM": sin_llm.get(key), "con_LLM": con_llm.get(key)})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
