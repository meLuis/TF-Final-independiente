# Asistente comercial

App Streamlit de una sola interfaz: caja de texto para consultar productos,
clientes, proveedores, compras, ofertas y riesgo usando motores locales.

## Ejecutar

```powershell
pip install -r requirements.txt
python -m streamlit run assistant_app.py
```

La app usa los datos y outputs incluidos en este proyecto para responder sin
regenerar el pipeline.

## Interno

Las vistas por seccion quedaron fuera de la app publica en `_internal/`. Solo se
usan para pruebas internas de nuevas demos.
