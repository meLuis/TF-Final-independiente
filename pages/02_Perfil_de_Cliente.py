"""Seccion 2 - Perfil de cliente (cascara delgada sobre el motor)."""

import streamlit as st

from assistant_ui import render_response
from core.assistant.engine_perfil_cliente import engine_perfil_cliente
from core.assistant.loaders import load_sales, stage1_ready

st.set_page_config(page_title="Perfil de cliente", layout="wide")
st.title("2. Perfil de cliente")
st.caption("Que le compra mas un cliente, por monto/frecuencia y por proximidad estructural (PPR).")

if not stage1_ready():
    st.warning("Primero corre la Etapa 1: py etapa1_ingesta.py")
    st.stop()

clientes = sorted(load_sales()["customer"].dropna().unique().tolist())
choice = st.selectbox("Cliente", ["(escribir abajo)"] + clientes)
typed = st.text_input("...o escribe el nombre del cliente", placeholder="ej. ODONTOLOGIA SAN ANTONIO")
customer = typed.strip() or (choice if choice != "(escribir abajo)" else "")

if customer:
    render_response(engine_perfil_cliente(customer))
