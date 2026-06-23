"""App Streamlit del asistente comercial en modo caja de texto.

Entry point separado de app.py:

    streamlit run assistant_app.py

Las secciones numeradas siguen viviendo en app.py + pages/. Esta app solo enruta
lenguaje natural a los mismos motores core/assistant/engine_*.py.
"""

from __future__ import annotations

import streamlit as st

from core.assistant_contract import AssistantResponse
from core.assistant.dispatch import handle_message


st.set_page_config(page_title="Asistente comercial", layout="wide")

st.title("Asistente comercial")
st.caption("Pregunta por productos, clientes, proveedores, compras, ofertas o riesgo.")


def render_commercial_response(resp: AssistantResponse) -> None:
    """Render limpio para la app publica: respuesta comercial + tabla principal."""
    if not resp.ok:
        st.error(resp.error)
        return
    if resp.answer:
        st.markdown(resp.answer)
    for warning in resp.warnings:
        st.warning(warning)
    if resp.table is not None and not resp.table.empty:
        st.dataframe(resp.table, use_container_width=True, hide_index=True)


if "assistant_pending" not in st.session_state:
    st.session_state.assistant_pending = None
if "assistant_last_response" not in st.session_state:
    st.session_state.assistant_last_response = None
if "assistant_last_question" not in st.session_state:
    st.session_state.assistant_last_question = ""
if "assistant_memory" not in st.session_state:
    st.session_state.assistant_memory = {}


if st.session_state.assistant_last_response is not None:
    if st.button("Limpiar conversacion"):
        st.session_state.assistant_pending = None
        st.session_state.assistant_last_response = None
        st.session_state.assistant_last_question = ""
        st.session_state.assistant_memory = {}
        st.rerun()


pending = st.session_state.assistant_pending
if pending:
    st.info("Hay una aclaracion pendiente. Responde con el dato solicitado o con el numero de candidato.")

question = st.chat_input("Escribe tu pregunta comercial")

if question:
    with st.spinner("Interpretando pregunta y ejecutando motor..."):
        outcome = handle_message(
            question,
            pending=pending,
            memory=st.session_state.assistant_memory,
    )
    st.session_state.assistant_pending = outcome.pending
    st.session_state.assistant_last_response = outcome.response
    st.session_state.assistant_last_question = question
    if outcome.memory_update:
        st.session_state.assistant_memory.update(outcome.memory_update)
    st.rerun()


last_question = st.session_state.assistant_last_question
last_response = st.session_state.assistant_last_response

if not last_response:
    st.info("Escribe una pregunta para empezar.")
else:
    if last_question:
        st.markdown(f"**Pregunta:** {last_question}")
    render_commercial_response(last_response)
