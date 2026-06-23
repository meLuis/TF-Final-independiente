"""Seccion 7 - Ofertas y descuentos (cascara delgada sobre el motor)."""

import streamlit as st

from assistant_ui import render_response
from core.assistant.engine_ofertas_descuentos import engine_ofertas_descuentos
from core.assistant.loaders import stage1_ready

st.set_page_config(page_title="Ofertas y descuentos", layout="wide")
st.title("7. Ofertas y descuentos")
st.caption("Ahorros historicos reales por proveedor frente al costo de referencia (Bellman-Ford).")

if not stage1_ready():
    st.warning("Primero corre la Etapa 1: py etapa1_ingesta.py")
    st.stop()

with st.spinner("Analizando ofertas..."):
    render_response(engine_ofertas_descuentos())
