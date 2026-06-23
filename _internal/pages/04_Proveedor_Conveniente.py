"""Seccion 4 - Proveedor conveniente (cascara delgada sobre el motor)."""

import streamlit as st

from assistant_ui import render_response
from core.assistant.engine_proveedor_conveniente import engine_proveedor_conveniente
from core.assistant.loaders import stage1_ready

st.set_page_config(page_title="Proveedor conveniente", layout="wide")
st.title("4. Proveedor conveniente")
st.caption("Mejor proveedor por precio + lectura estructural con betweenness (Brandes).")

if not stage1_ready():
    st.warning("Primero corre la Etapa 1: py etapa1_ingesta.py")
    st.stop()

product = st.text_input("Producto a abastecer", placeholder="ej. 5004 o frasco gotero ambar 30ml")

if product:
    with st.spinner("Calculando ranking y betweenness (la primera vez tarda)..."):
        render_response(engine_proveedor_conveniente(product))
