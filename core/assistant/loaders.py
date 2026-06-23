"""Loaders cacheados de datos y motores para las secciones del asistente.

Esta es la unica capa de core/assistant que puede tocar Streamlit: centraliza el
cacheo (@st.cache_resource para motores/objetos pesados, @st.cache_data para
DataFrames) para que las paginas no repitan rutas ni recomputos. Los algoritmos
siguen viviendo en core/ puro; aqui solo se construyen y se guardan en cache.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from core.graph_paths import BusinessGraphPaths
from core.pagerank_personalized import PageRankEngine
from core.purchase_options import build_supply_options
from core.semantic_search import SemanticSearchIndex

BASE = Path(__file__).resolve().parents[2]
STAGE1_DIR = BASE / "outputs" / "stage1_datos"
STAGE2_GRAPH_DIR = BASE / "outputs" / "stage2_graph_datos"
STAGE2_TX_DIR = BASE / "outputs" / "stage2_transaction_graphs"
STAGE5_DIR = BASE / "outputs" / "stage5_analisis"
SUPPLIERS_CSV = BASE / "data" / "base" / "proveedores.csv"


def stage1_ready() -> bool:
    return (STAGE1_DIR / "sales_clean.csv").exists()


def tx_ready() -> bool:
    return (STAGE2_TX_DIR / "transaction_graph_business_nodes.csv").exists()


def semantic_ready() -> bool:
    return (STAGE2_GRAPH_DIR / "semantic_attribute_graph_nodes.csv").exists()


# ── DataFrames (cache_data) ──────────────────────────────────────────────────


@st.cache_data
def load_sales() -> pd.DataFrame:
    return pd.read_csv(STAGE1_DIR / "sales_clean.csv", encoding="utf-8-sig", dtype={"product_id": str})


@st.cache_data
def load_purchases() -> pd.DataFrame:
    return pd.read_csv(STAGE1_DIR / "purchases_clean.csv", encoding="utf-8-sig", dtype={"product_id": str})


@st.cache_data
def load_products() -> pd.DataFrame:
    return pd.read_csv(STAGE1_DIR / "products_clean.csv", encoding="utf-8-sig", dtype={"product_id": str})


@st.cache_data
def load_projection_edges() -> pd.DataFrame:
    path = STAGE2_GRAPH_DIR / "product_projection_edges.csv"
    return pd.read_csv(path, encoding="utf-8-sig") if path.exists() else pd.DataFrame()


@st.cache_data
def load_business_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    nodes = pd.read_csv(STAGE2_TX_DIR / "transaction_graph_business_nodes.csv", encoding="utf-8-sig")
    edges = pd.read_csv(STAGE2_TX_DIR / "transaction_graph_business_edges.csv", encoding="utf-8-sig")
    return nodes, edges


# ── Motores (cache_resource) ─────────────────────────────────────────────────


@st.cache_resource
def load_semantic_index() -> SemanticSearchIndex:
    return SemanticSearchIndex.from_stage2_dir(STAGE2_GRAPH_DIR)


@st.cache_resource
def load_pagerank(kind: str = "business") -> PageRankEngine:
    return PageRankEngine.from_transaction_dir(STAGE2_TX_DIR, kind=kind)


@st.cache_resource
def load_paths() -> BusinessGraphPaths:
    return BusinessGraphPaths.from_transaction_dir(STAGE2_TX_DIR, kind="business")


@st.cache_resource
def load_supply_options() -> pd.DataFrame:
    return build_supply_options(STAGE1_DIR, SUPPLIERS_CSV)


@st.cache_resource
def load_communities() -> dict:
    """Leiden + descripciones sobre la proyeccion producto-producto.

    Calcula en vivo (on-the-fly); si igraph/leidenalg no estan instalados, cae a
    los CSV ya generados por etapa5_analisis_ventas.py para no romper la demo.
    """
    try:
        from core.community_leiden import describe_communities, detect_communities

        edges = load_projection_edges()
        result = detect_communities(edges)
        result["descriptions"] = describe_communities(result.get("membership", pd.DataFrame()))
        result["source"] = "on-the-fly"
        return result
    except Exception:
        import json

        def _read(name: str) -> pd.DataFrame:
            path = STAGE5_DIR / name
            return pd.read_csv(path, encoding="utf-8-sig") if path.exists() else pd.DataFrame()

        metrics_path = STAGE5_DIR / "leiden_metrics.json"
        metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
        return {
            "membership": _read("leiden_communities.csv"),
            "descriptions": _read("leiden_community_descriptions.csv"),
            "metrics": metrics,
            "source": "stage5_analisis (precalculado)",
        }


@st.cache_resource
def load_brandes() -> dict:
    """Betweenness de Brandes sobre G_business (pesado: O(V*E), por eso cacheado)."""
    from core.centrality_brandes import supplier_betweenness

    nodes, edges = load_business_frames()
    return supplier_betweenness(nodes, edges)


@st.cache_resource
def load_offers() -> dict:
    """Analisis Bellman-Ford de ofertas/ahorros sobre las compras reales."""
    from core.bellman_ford_offers import run_bellman_ford_offer_analysis

    return run_bellman_ford_offer_analysis(STAGE1_DIR)


@st.cache_resource
def load_assoc_rules() -> pd.DataFrame:
    """Reglas de asociacion (Apriori) sobre pseudo-documentos de venta (on-the-fly)."""
    from core.association_rules import association_rules, build_transactions

    transactions = build_transactions(load_sales())
    return association_rules(transactions)
