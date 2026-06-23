"""Seccion 9 - Venta cruzada y recomendacion (cascara delgada sobre el motor)."""

import streamlit as st

from assistant_ui import render_response
from core.assistant.engine_venta_cruzada import engine_venta_cruzada
from core.assistant.loaders import stage1_ready

st.set_page_config(page_title="Venta cruzada", layout="wide")
st.title("9. Venta cruzada y recomendacion")
st.caption("Si vende esto, que mas ofrecer: reglas de asociacion (lift/Apriori) vs co-ocurrencia.")

if not stage1_ready():
    st.warning("Primero corre la Etapa 1: py etapa1_ingesta.py")
    st.stop()

product = st.text_input("Producto base", placeholder="ej. 5004 o frasco gotero ambar 30ml")

if product:
    with st.spinner("Minando reglas de asociacion (la primera vez tarda)..."):
        render_response(engine_venta_cruzada(product))
