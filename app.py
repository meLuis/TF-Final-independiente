from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from core.pipeline import export_stage1, read_table_flexible, run_stage1


st.set_page_config(
    page_title="TF Final - Etapa 1",
    layout="wide",
)


OUTPUT_DIR = Path(__file__).parent / "outputs" / "stage1_latest"


def _load_uploaded_csv(uploaded_file):
    if uploaded_file is None:
        return None
    return read_table_flexible(uploaded_file)


def _mapping_table(mapping: dict) -> pd.DataFrame:
    rows = []
    for field, candidate in mapping.items():
        rows.append(
            {
                "campo_canonico": field,
                "columna_detectada": candidate.get("column"),
                "confianza": candidate.get("confidence"),
                "razon": candidate.get("reason"),
            }
        )
    return pd.DataFrame(rows)


def _mapping_from_editor(
    edited: pd.DataFrame,
    original_mapping: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    updated: dict[str, dict[str, Any]] = {}
    for _, row in edited.iterrows():
        field = row["campo_canonico"]
        selected = row.get("columna_detectada")
        selected = None if pd.isna(selected) or selected == "" else str(selected)
        original = original_mapping.get(field, {})
        original_column = original.get("column")
        was_changed = selected != original_column
        updated[field] = {
            "field": field,
            "column": selected,
            "confidence": 1.0 if was_changed and selected else float(original.get("confidence", 0.0)),
            "reason": "confirmado manualmente" if was_changed else original.get("reason", ""),
            "alternatives": original.get("alternatives", []),
        }
    return updated


def _render_mapping_editor(dataset_key: str, result: dict[str, Any], dataframes: dict[str, pd.DataFrame]):
    mapping = result["schema_mapping"][dataset_key]
    table = _mapping_table(mapping)
    options = [""] + [str(col) for col in dataframes[dataset_key].columns]
    return st.data_editor(
        table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "columna_detectada": st.column_config.SelectboxColumn(
                "columna_detectada",
                options=options,
            ),
            "confianza": st.column_config.NumberColumn("confianza", format="%.2f"),
        },
        disabled=["campo_canonico", "confianza", "razon"],
        key=f"editor_{dataset_key}",
    )


def _show_dataframe_preview(title: str, df: pd.DataFrame):
    with st.expander(title, expanded=False):
        st.caption(f"{len(df):,} filas x {len(df.columns):,} columnas")
        st.dataframe(df.head(30), use_container_width=True)


st.title("TF Final - Asistente comercial (Etapa 1: Ingesta)")

st.caption(
    "Sube tres CSV de una empresa. El sistema perfila columnas, propone un esquema, "
    "normaliza datos y vincula compras/ventas con el catalogo de productos."
)
st.info(
    "Esta es la pagina de datos. Las 10 secciones del asistente (buscador, perfil de "
    "cliente, proveedor, pedido optimo, presupuesto, ofertas, familias, venta cruzada, "
    "riesgo...) estan en el menu lateral. Cada una muestra el baseline del curso y el "
    "algoritmo investigado."
)

with st.sidebar:
    st.header("Archivos")
    products_file = st.file_uploader("productos", type=["csv", "xlsx", "xls"], key="products")
    sales_file = st.file_uploader("ventas", type=["csv", "xlsx", "xls"], key="sales")
    purchases_file = st.file_uploader("compras", type=["csv", "xlsx", "xls"], key="purchases")
    run_button = st.button("Procesar etapa 1", type="primary", use_container_width=True)


if "stage1_dataframes" not in st.session_state:
    st.session_state.stage1_dataframes = None
if "stage1_result" not in st.session_state:
    st.session_state.stage1_result = None
if "stage1_exported_paths" not in st.session_state:
    st.session_state.stage1_exported_paths = None


if not run_button and st.session_state.stage1_result is None:
    st.info("Sube los tres CSV y ejecuta el procesamiento.")
    st.stop()

if run_button and (not products_file or not sales_file or not purchases_file):
    st.warning("Faltan archivos. Debes subir productos, ventas y compras.")
    st.stop()

if run_button:
    try:
        dataframes = {
            "products": _load_uploaded_csv(products_file),
            "sales": _load_uploaded_csv(sales_file),
            "purchases": _load_uploaded_csv(purchases_file),
        }
    except Exception as exc:
        st.error(f"No se pudo leer uno de los CSV: {exc}")
        st.stop()

    for name, df in dataframes.items():
        if df is None or df.empty:
            st.error(f"El archivo {name} esta vacio o no pudo leerse correctamente.")
            st.stop()

    with st.spinner("Procesando CSVs..."):
        result = run_stage1(dataframes)
        exported_paths = export_stage1(result, OUTPUT_DIR)
        st.session_state.stage1_dataframes = dataframes
        st.session_state.stage1_result = result
        st.session_state.stage1_exported_paths = exported_paths

dataframes = st.session_state.stage1_dataframes
result = st.session_state.stage1_result
exported_paths = st.session_state.stage1_exported_paths

report = result["report"]

st.subheader("Resumen de calidad")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Confianza columnas", f"{report['column_mapping_confidence']:.0%}")
col2.metric("Coverage matching", f"{report['product_match_coverage']:.0%}")
col3.metric("Ambiguos", report["ambiguous_matches"])
col4.metric("Rechazados", report["rejected_matches"])

if report["requires_human_review"]:
    st.warning("Hay productos ambiguos o rechazados. Deben revisarse antes de usar estos datos para optimizacion.")
else:
    st.success("No se detectaron casos que requieran revision humana.")

st.subheader("Mapeo de columnas sugerido")

tabs = st.tabs(["Productos", "Ventas", "Compras"])
edited_tables = {}
for tab, key in zip(tabs, ["products", "sales", "purchases"]):
    with tab:
        edited_tables[key] = _render_mapping_editor(key, result, dataframes)
        st.json(result["validations"][key], expanded=False)

if st.button("Aplicar mapeo editado y reprocesar", use_container_width=True):
    edited_mapping = {
        key: _mapping_from_editor(edited_tables[key], result["schema_mapping"][key])
        for key in ["products", "sales", "purchases"]
    }
    with st.spinner("Reprocesando con el mapeo confirmado..."):
        result = run_stage1(dataframes, schema_mapping=edited_mapping)
        exported_paths = export_stage1(result, OUTPUT_DIR)
        st.session_state.stage1_result = result
        st.session_state.stage1_exported_paths = exported_paths
    st.success("Mapeo aplicado. Los outputs fueron regenerados.")
    st.rerun()

st.subheader("Matching de productos")
matches = result["product_matches"]
status_counts = matches["status"].value_counts().reset_index()
status_counts.columns = ["status", "filas"]
st.dataframe(status_counts, use_container_width=True, hide_index=True)

with st.expander("Ver matches ambiguos o rechazados", expanded=True):
    review = matches[matches["status"].isin(["ambiguous", "rejected"])]
    if review.empty:
        st.write("No hay casos pendientes.")
    else:
        st.dataframe(review.head(200), use_container_width=True, hide_index=True)

st.subheader("Tablas utiles generadas")
summary_tabs = st.tabs(["Calidad", "Flags", "Actividad productos", "Patrones codigos"])
summary_keys = [
    "quality_summary",
    "transaction_flags_summary",
    "product_activity_summary",
    "code_pattern_summary",
]
for tab, key in zip(summary_tabs, summary_keys):
    with tab:
        table = result.get("summary_tables", {}).get(key, pd.DataFrame())
        if table.empty:
            st.write("Sin datos para esta tabla.")
        else:
            st.dataframe(table.head(300), use_container_width=True, hide_index=True)

st.subheader("Datos normalizados")
_show_dataframe_preview("products_clean.csv", result["cleaned"]["products"])
_show_dataframe_preview("sales_clean.csv", result["cleaned"]["sales"])
_show_dataframe_preview("purchases_clean.csv", result["cleaned"]["purchases"])

st.subheader("Archivos exportados")
paths_df = pd.DataFrame(
    [{"archivo": name, "ruta": path} for name, path in exported_paths.items()]
)
st.dataframe(paths_df, use_container_width=True, hide_index=True)
