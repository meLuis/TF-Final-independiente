"""Seccion 6 - Presupuesto y mochila (cascara delgada sobre el motor)."""

import streamlit as st

from assistant_ui import render_response
from core.assistant.engine_presupuesto_mochila import engine_presupuesto_mochila
from core.assistant.loaders import load_supply_options, stage1_ready

st.set_page_config(page_title="Presupuesto y mochila", layout="wide")
st.title("6. Presupuesto y mochila")
st.caption("Cuanto puedes comprar con un presupuesto fijo (Knapsack DP vs greedy).")

if not stage1_ready():
    st.warning("Primero corre la Etapa 1: py etapa1_ingesta.py")
    st.stop()

options = load_supply_options()
products = (
    options[["product_id", "product_name"]]
    .drop_duplicates("product_id")
    .assign(display=lambda df: df["product_id"] + " - " + df["product_name"].str.slice(0, 60))
)

budget = st.number_input("Presupuesto (S/)", min_value=1.0, value=2000.0, step=100.0)
selected = st.multiselect("Productos candidatos", products["display"].tolist())
order: dict[str, float] = {}
for display in selected:
    product_id = display.split(" - ")[0]
    qty = st.number_input(f"Cantidad maxima: {display}", min_value=1.0, value=1000.0, key=f"kqty_{product_id}")
    order[product_id] = float(qty)

if order and st.button("Calcular compra", type="primary"):
    render_response(engine_presupuesto_mochila(order, budget))
