"""Seccion 8 - Familias, sustitutos y productos parecidos (cascara delgada)."""

import streamlit as st

from assistant_ui import render_response
from core.assistant.engine_familias_sustitutos import engine_familias_sustitutos
from core.assistant.loaders import stage1_ready

st.set_page_config(page_title="Familias y sustitutos", layout="wide")
st.title("8. Familias, sustitutos y parecidos")
st.caption("Comunidades Leiden (familias) y sustitutos cercanos via Personalized PageRank.")

if not stage1_ready():
    st.warning("Primero corre la Etapa 1 y la proyeccion (py etapa2_proyeccion_productos.py).")
    st.stop()

product = st.text_input(
    "Producto (opcional: deja vacio para ver todas las familias)",
    placeholder="ej. 5041 o frasco gotero ambar 30ml",
)

render_response(engine_familias_sustitutos(product or None))
