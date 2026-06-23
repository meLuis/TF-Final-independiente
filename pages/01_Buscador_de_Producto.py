"""Seccion 1 - Buscador de producto (cascara delgada sobre el motor)."""

import streamlit as st

from assistant_ui import render_response
from core.assistant.engine_buscar_producto import engine_buscar_producto
from core.assistant.loaders import semantic_ready

st.set_page_config(page_title="Buscador de producto", layout="wide")
st.title("1. Buscador de producto")
st.caption("Escribe en lenguaje natural; el vocabulario se aprende del grafo y los numericos son exactos.")

if not semantic_ready():
    st.warning("Primero genera el grafo: py etapa2_grafo_semantico.py")
    st.stop()

query = st.text_input("Que producto buscas?", placeholder="ej. frasco gotero vidrio ambar 30ml")
k = st.slider("Resultados", 5, 30, 10)

if query:
    render_response(engine_buscar_producto(query, k=k))
