"""App Streamlit del asistente comercial en modo caja de texto.

Entry point separado de app.py:

    streamlit run assistant_app.py

Las secciones numeradas siguen viviendo en app.py + pages/. Esta app solo enruta
lenguaje natural a los mismos motores core/assistant/engine_*.py.
"""

from __future__ import annotations

import streamlit as st

from assistant_ui import render_response
from core.assistant.dispatch import handle_message


st.set_page_config(page_title="Asistente comercial", layout="wide")

st.title("Asistente comercial")
st.caption(
    "Pregunta en lenguaje natural. El router local elige una de las 10 capacidades "
    "y ejecuta los motores algoritmicos existentes."
)


if "assistant_pending" not in st.session_state:
    st.session_state.assistant_pending = None
if "assistant_last_response" not in st.session_state:
    st.session_state.assistant_last_response = None
if "assistant_last_route" not in st.session_state:
    st.session_state.assistant_last_route = None
if "assistant_last_question" not in st.session_state:
    st.session_state.assistant_last_question = ""
if "assistant_memory" not in st.session_state:
    st.session_state.assistant_memory = {}


with st.sidebar:
    st.header("Modo caja")
    st.write("Ejemplos:")
    st.code(
        "\n".join(
            [
                "Busca frasco gotero ambar 30 ml",
                "Que me compra mas ODONTOLOGIA SAN ANTONIO",
                "De donde compro lo que pide ODONTOLOGIA SAN ANTONIO",
                "Que proveedor me conviene para frasco gotero",
                "Necesito 100 de 5004 y 50 de 5041",
                "Tengo S/ 2000 para comprar frasco gotero",
                "Que productos se venden junto con 5004",
                "Que pasa si pierdo ENVIPLAST",
            ]
        ),
        language="text",
    )
    if st.button("Limpiar conversacion", use_container_width=True):
        st.session_state.assistant_pending = None
        st.session_state.assistant_last_response = None
        st.session_state.assistant_last_route = None
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
    st.session_state.assistant_last_route = outcome.route
    st.session_state.assistant_last_question = question
    if outcome.memory_update:
        st.session_state.assistant_memory.update(outcome.memory_update)
    st.rerun()


last_question = st.session_state.assistant_last_question
last_response = st.session_state.assistant_last_response
last_route = st.session_state.assistant_last_route

if not last_response:
    st.info("Escribe una pregunta para empezar.")
else:
    if last_question:
        st.markdown(f"**Pregunta:** {last_question}")
    render_response(last_response)

    if last_route:
        with st.expander("Router local"):
            st.write(
                {
                    "intent": last_route.intent,
                    "confidence": last_route.confidence,
                    "slots": last_route.slots,
                    "scores": last_route.scores,
                    "missing_slots": last_route.missing_slots,
                    "memory": st.session_state.assistant_memory,
                }
            )
