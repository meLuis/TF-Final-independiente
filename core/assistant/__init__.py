"""Capa de asistente: motores por intencion sobre un contrato de salida uniforme.

Cada modulo engine_*.py expone una funcion engine_<intencion>(...) que devuelve un
core.assistant_contract.AssistantResponse. Hoy cada seccion (pagina Streamlit) llama
a su engine; cuando llegue la caja de texto, un router elegira el engine sin cambiar
ni los motores ni el render.
"""
