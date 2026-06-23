"""Seccion 5 - Pedido optimo multi-SKU (cascara delgada sobre el motor)."""

import streamlit as st

from assistant_ui import render_response
from core.assistant.engine_pedido_optimo import engine_pedido_optimo
from core.assistant.loaders import load_supply_options, stage1_ready

st.set_page_config(page_title="Pedido optimo", layout="wide")
st.title("5. Pedido optimo multi-SKU")
st.caption("Asigna un pedido completo al minimo costo respetando todas las capacidades (min-cost flow).")

if not stage1_ready():
    st.warning("Primero corre la Etapa 1: py etapa1_ingesta.py")
    st.stop()

options = load_supply_options()
products = (
    options[["product_id", "product_name"]]
    .drop_duplicates("product_id")
    .assign(display=lambda df: df["product_id"] + " - " + df["product_name"].str.slice(0, 60))
)

selected = st.multiselect("Productos del pedido", products["display"].tolist())
order: dict[str, float] = {}
for display in selected:
    product_id = display.split(" - ")[0]
    qty = st.number_input(f"Cantidad: {display}", min_value=1.0, value=500.0, key=f"qty_{product_id}")
    order[product_id] = float(qty)

if order and st.button("Optimizar pedido", type="primary"):
    render_response(engine_pedido_optimo(order))
