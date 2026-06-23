"""Seccion 10 - Riesgo y dependencia (cascara delgada sobre el motor)."""

import streamlit as st

from assistant_ui import render_response
from core.assistant.engine_riesgo_dependencia import engine_riesgo_dependencia
from core.assistant.loaders import load_purchases, stage1_ready

st.set_page_config(page_title="Riesgo y dependencia", layout="wide")
st.title("10. Riesgo y dependencia")
st.caption("Que pasa si pierdo un proveedor; cuello de botella (Dinic min-cut) y proveedor critico (Brandes).")

if not stage1_ready():
    st.warning("Primero corre la Etapa 1: py etapa1_ingesta.py")
    st.stop()

proveedores = sorted(load_purchases()["supplier"].dropna().unique().tolist())
choice = st.selectbox("Proveedor (opcional: vacio para vision global)", ["(vision global)"] + proveedores)
typed = st.text_input("...o escribe el proveedor", placeholder="ej. ENVIPLAST")
supplier = typed.strip() or (choice if choice != "(vision global)" else None)

with st.spinner("Calculando flujo, min-cut y betweenness (la primera vez tarda)..."):
    render_response(engine_riesgo_dependencia(supplier))
