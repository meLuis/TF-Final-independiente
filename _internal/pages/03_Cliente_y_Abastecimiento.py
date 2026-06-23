"""Seccion 3 - Cliente y abastecimiento (cascara delgada sobre el motor)."""

import streamlit as st

from assistant_ui import render_response
from core.assistant.engine_cliente_abastecimiento import engine_cliente_abastecimiento
from core.assistant.loaders import load_sales, stage1_ready, tx_ready

st.set_page_config(page_title="Cliente y abastecimiento", layout="wide")
st.title("3. Cliente y abastecimiento")
st.caption("De donde se compra lo que pide un cliente; camino explicativo con BFS bidireccional.")

if not (stage1_ready() and tx_ready()):
    st.warning("Necesita Etapa 1 y los grafos transaccionales (py etapa2_grafos_transaccionales.py).")
    st.stop()

clientes = sorted(load_sales()["customer"].dropna().unique().tolist())
choice = st.selectbox("Cliente", ["(escribir abajo)"] + clientes)
typed = st.text_input("...o escribe el nombre del cliente", placeholder="ej. ODONTOLOGIA SAN ANTONIO")
customer = typed.strip() or (choice if choice != "(escribir abajo)" else "")

if customer:
    render_response(engine_cliente_abastecimiento(customer))
