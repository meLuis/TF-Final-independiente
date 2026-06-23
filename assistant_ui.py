"""Render uniforme del contrato del asistente (capa de presentacion).

Vive en la raiz a proposito: fuera de core/ (que no debe depender de Streamlit)
y fuera de pages/ (para que Streamlit no lo trate como una pagina mas). Las 10
paginas de seccion importan render_response() y quedan en ~10 lineas.

Cuando llegue la caja de texto + router, este mismo render mostrara la respuesta
del engine que el router elija: no hay que tocar nada aqui.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from core.assistant_contract import AlgoVariant, AssistantResponse


def _show_table(table: pd.DataFrame | None) -> bool:
    if table is None or table.empty:
        return False
    st.dataframe(table, use_container_width=True, hide_index=True)
    return True


def _render_variant(column, variant: AlgoVariant | None, badge: str) -> None:
    if variant is None:
        return
    with column:
        st.markdown(f"**{badge}: {variant.name}**")
        if variant.summary:
            st.caption(variant.summary)
        numeric = {k: v for k, v in variant.metrics.items() if isinstance(v, (int, float))}
        if numeric:
            cols = st.columns(min(len(numeric), 3))
            for i, (key, value) in enumerate(numeric.items()):
                cols[i % len(cols)].metric(key, value)
        _show_table(variant.table)


def render_baseline_vs_investigated(
    baseline: AlgoVariant | None, investigated: AlgoVariant | None
) -> None:
    """Bloque 'antes (curso) vs ahora (investigado)' en dos columnas."""
    if baseline is None and investigated is None:
        return
    st.subheader("Baseline del curso vs algoritmo investigado")
    col_base, col_inv = st.columns(2)
    _render_variant(col_base, baseline, "Antes (baseline)")
    _render_variant(col_inv, investigated, "Ahora (investigado)")


def render_technical(resp: AssistantResponse) -> None:
    """Vista tecnica plegable para sustentacion."""
    with st.expander("Vista tecnica / sustentacion"):
        if resp.algorithm:
            st.markdown(f"**Algoritmo investigado:** {resp.algorithm}")
        if resp.entities:
            st.markdown("**Entidades resueltas:**")
            st.json(resp.entities, expanded=False)
        if resp.technical:
            st.markdown("**Detalle tecnico:**")
            st.json(_jsonable(resp.technical), expanded=False)
        for name, table in resp.extra_tables.items():
            st.markdown(f"**{name}:**")
            _show_table(table)
        if resp.evidence:
            st.markdown("**Evidencia (grafos/archivos consultados):**")
            for item in resp.evidence:
                st.write(f"- {item}")


def render_response(resp: AssistantResponse) -> None:
    """Punto de entrada unico: pinta cualquier AssistantResponse de forma uniforme."""
    if not resp.ok:
        st.error(resp.error)
        return

    if resp.answer:
        st.markdown(resp.answer)
    for warning in resp.warnings:
        st.warning(warning)
    if resp.algorithm:
        st.caption(f"Algoritmo: {resp.algorithm}")

    _show_table(resp.table)

    render_baseline_vs_investigated(resp.baseline, resp.investigated)
    render_technical(resp)


def _jsonable(value: Any) -> Any:
    """Convierte DataFrames anidados en algo serializable por st.json."""
    if isinstance(value, pd.DataFrame):
        return value.to_dict(orient="records")
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value
