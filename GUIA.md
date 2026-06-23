# GUIA del proyecto TF-Final

Manual de navegacion: que es cada archivo, en que orden corre, que consume y que
produce. Pensado para entender el proyecto a simple vista sin leer el codigo.

- Para el **por que** de cada algoritmo (antes vs ahora) ver [docs/ALGORITMOS_EVOLUCION.md](docs/ALGORITMOS_EVOLUCION.md).
- Para los **calculos, indicadores (%) y el scoring de busqueda semantica** ver [docs/CALCULOS_Y_BUSQUEDA_SEMANTICA.md](docs/CALCULOS_Y_BUSQUEDA_SEMANTICA.md).
- Para el **detalle de cada etapa** ver [docs/etapas/](docs/etapas/).
- Para el **origen de los datos** ver [data/base/PROCEDENCIA.md](data/base/PROCEDENCIA.md).

---

## 1. Como arrancar

```powershell
cd TF-Final
pip install -r requirements.txt
streamlit run app.py          # la aplicacion (Etapas 1 a 5 en pestanas)
```

La app lee los resultados ya generados en `outputs/`. Si una pestana avisa que
falta un archivo, corre el script de la etapa correspondiente (tabla de la
seccion 3) y recarga.

---

## 2. Mapa de carpetas

| Carpeta | Contenido |
|---------|-----------|
| `app.py` | Aplicacion Streamlit. Etapa 1 (subir y limpiar datos) + portada del asistente. Debe quedarse en la raiz. |
| `pages/` | Las 10 secciones del asistente comercial (`01_`..`10_`) + `11_` (reportes y vista tecnica). Cada pagina es una cascara delgada sobre un motor de `core/assistant/`. |
| `assistant_ui.py` | Render uniforme del contrato del asistente (capa de presentacion). En la raiz a proposito: fuera de `core/` (que no depende de Streamlit) y fuera de `pages/`. |
| `core/` | Logica reutilizable e independiente de la interfaz (el "motor"). Ver seccion 6. |
| `core/assistant/` | Capa de orquestacion: un `engine_<intencion>.py` por seccion que devuelve el contrato uniforme (`core/assistant_contract.py`); `loaders.py` cachea datos/motores, `aggregations.py` resuelve entidades y rankings base. |
| `etapa*.py`, `demo_*.py`, `util_*.py` | Scripts de consola que ejecutan el pipeline por etapas. Ver secciones 3 y 5. |
| `data/base/` | Datos base reales + enriquecimientos sinteticos declarados. Fuente canonica. |
| `data/demo/ferreteria/` | Dataset chico de otro rubro para probar la generalidad del motor. |
| `docs/` | Documentacion: una nota por etapa + la evolucion de algoritmos para sustentacion. |
| `outputs/` | Todo lo que generan los scripts. Regenerable y excluido de git. Ver seccion 7. |

---

## 3. El pipeline en orden

Los scripts estan nombrados por etapa para que el orden sea evidente. Cada etapa
consume lo que produjo la anterior.

| # | Script | Etapa | Consume | Produce (en `outputs/`) |
|---|--------|-------|---------|-------------------------|
| 1 | `etapa1_ingesta.py` | 1 — Ingesta y normalizacion | `data/base/*.xlsx` | `stage1_datos/` (`products_clean.csv`, `sales_clean.csv`, `purchases_clean.csv`, mapeo de esquema, perfiles, calidad) |
| 2 | `etapa1_5_atributos.py` | 1.5 — Extraccion de atributos | `stage1_datos/`, `data/base/catalogo.csv` | `stage15_datos/` (`product_attributes.csv`, `attribute_rules.json`, cobertura, comparacion vs golden) |
| 3 | `etapa2_grafo_semantico.py` | 2 — Grafo G_attr | `stage15_datos/` | `stage2_graph_datos/` (G_attr: nodos, aristas, metricas) |
| 4 | `etapa2_proyeccion_productos.py` | 2 — Proyeccion producto-producto | `stage2_graph_datos/` | `stage2_graph_datos/product_projection_*` |
| 5 | `etapa2_sensibilidad_umbral.py` | 2 — Justificacion del umbral | `stage1_datos/`, `stage15_datos/` | `stage2_sensitivity/` (barrido de `min_confidence`) |
| 6 | `etapa2_grafos_transaccionales.py` | 2 — Grafos de negocio | `stage1_datos/` | `stage2_transaction_graphs/` (G_purchases, G_sales, **G_business** 3,678 nodos) |
| 7 | `etapa2_visualizaciones.py` | 2 — PNGs de G_attr | `stage2_graph_datos/` | `stage2_graph_datos/visualizations/*.png` |
| 8 | `etapa4_optimizacion_compras.py` | 4 — Compras | `stage1_datos/`, `data/base/proveedores.csv` | `stage4_optimizacion/` (baseline vs min-cost flow) |
| 9 | `etapa5_analisis_ventas.py` | 5 — Analisis | `stage1_datos/`, `stage2_graph_datos/`, `stage2_transaction_graphs/` | `stage5_analisis/` (Leiden, PageRank, ABC, co-venta, dependencia) |

**Las 10 secciones del asistente no tienen script de consola.** Corren en vivo
dentro de la app sobre los grafos/outputs ya generados. Cada seccion expone su
baseline del curso y su algoritmo investigado:

| # | Seccion (pagina) | Motor `core/assistant/` | Investigado |
|---|---|---|---|
| 1 | Buscador de producto | `engine_buscar_producto` | BFS semantico + filtro exacto + PPR |
| 2 | Perfil de cliente | `engine_perfil_cliente` | Personalized PageRank (reinicio en CLIENT) |
| 3 | Cliente y abastecimiento | `engine_cliente_abastecimiento` | BFS bidireccional |
| 4 | Proveedor conveniente | `engine_proveedor_conveniente` | Betweenness de Brandes (`core/centrality_brandes.py`) |
| 5 | Pedido optimo multi-SKU | `engine_pedido_optimo` | Min-cost flow |
| 6 | Presupuesto y mochila | `engine_presupuesto_mochila` | Knapsack DP |
| 7 | Ofertas y descuentos | `engine_ofertas_descuentos` | Bellman-Ford |
| 8 | Familias y sustitutos | `engine_familias_sustitutos` | Leiden + PPR |
| 9 | Venta cruzada | `engine_venta_cruzada` | Reglas lift/Apriori (`core/association_rules.py`) + PPR |
| 10 | Riesgo y dependencia | `engine_riesgo_dependencia` | Dinic max-flow/min-cut (`core/supply_flow_risk.py`) + Brandes |

La seccion `11_Reportes_y_Vista_Tecnica.py` agrupa lo que no encaja 1:1: rankings
PageRank, ABC, co-venta, el explorador generico de conexiones (BFS vs
bidireccional entre dos entidades cualesquiera), sensibilidad de umbral y la
comparacion antes/despues del LLM. Motores base reusados: `core/semantic_search.py`,
`core/graph_paths.py`, `core/pagerank_personalized.py`, `core/optimization_*.py`,
`core/community_leiden.py`, `core/bellman_ford_offers.py`, `core/sales_reports.py`.

> Rutas geograficas / A* DESCARTADAS: no aplican al negocio (sedes sinteticas);
> se retira `core/logistics_astar.py`. No se fuerza ese algoritmo. Ver
> `docs/PLAN_ASISTENTE_GRAFOS.md`.

---

## 4. Track LLM opcional (antes vs despues del LLM)

La Etapa 1.5 funciona 100% con reglas deterministas. Encima se puede aplicar una
capa opcional con Gemini que enriquece atributos (accesorios, features) **sin
perder exactitud** (politica conservadora con gating de aceptacion).

| Script | Necesita API key | Que hace |
|--------|------------------|----------|
| `etapa1_5_atributos_llm_gemini.py` | Si (`GEMINI_API_KEY`) | Llama a Gemini y cachea reglas en `stage15_datos/attribute_rules_gemini_*` |
| `etapa1_5_atributos_llm_finalize.py` | No (reusa reglas cacheadas) | Aplica las reglas Gemini, valida que no haya regresion y escribe `stage15_final/` |
| `etapa1_5_atributos_llm_test.py` | No | Arnes de prueba para comparar reglas baseline vs LLM (apoyo, no pipeline) |

Para tener el grafo "con LLM" comparable al "sin LLM":

```powershell
py etapa1_5_atributos_llm_finalize.py
py etapa2_grafo_semantico.py  --input outputs/stage15_final  --output outputs/stage2_graph_final
py etapa2_visualizaciones.py  --input outputs/stage2_graph_final
```

Resultado: dos grafos comparables y sus PNGs para mostrar el antes/despues.

| Grafo | Origen | Nodos | Aristas |
|-------|--------|-------|---------|
| `stage2_graph_datos` | reglas deterministas (sin LLM) | 790 | 2,518 |
| `stage2_graph_final` | reglas + Gemini (con LLM) | 805 | 2,651 |

---

## 5. Scripts auxiliares (no son el pipeline principal)

Se conservan como utilidades de apoyo y demostracion; no hace falta correrlos para
la sustentacion.

| Script | Para que sirve | Produce |
|--------|----------------|---------|
| `demo_ferreteria_completo.py` | **Prueba de generalidad**: corre Etapas 1 a 5 sobre otro rubro (ferreteria) sin tocar codigo. | `outputs/ferreteria_full/` |
| `demo_etapa1_ferreteria.py` | Corrida rapida de solo la Etapa 1 sobre el dataset de ferreteria. | `outputs/stage1_demo_ferreteria/` |
| `util_smoke_excel.py` | Verifica que el lector acepte `.xlsx` (genera fixtures sinteticos y corre Etapa 1). | `outputs/stage1_excel_smoke*/` |

---

## 6. Modulos de `core/` (el motor)

Logica independiente de Streamlit; la usan tanto los scripts como las paginas.

**Etapa 1 — limpieza:** `pipeline.py` (orquesta), `schema_detector.py` (infiere
columnas), `normalizer.py`, `product_matcher.py` (fuzzy matching), `profiler.py`,
`validators.py`, `summaries.py`, `text_utils.py` (normalizacion y similitud).

**Etapa 1.5 — atributos:** `attribute_extractor.py` (reglas + extraccion),
`semantic_retrievability.py` (mide recuperabilidad para aceptar/rechazar el LLM).

**Etapa 2 — grafos:** `semantic_graph.py` (G_attr), `product_projection.py`
(similitud producto-producto), `transaction_graphs.py` (G_purchases/sales/business),
`graph_visualizer.py` (PNGs).

**Etapa 3 — busqueda y conexiones:** `semantic_search.py` (BFS + filtro exacto),
`graph_paths.py` (BFS bidireccional). `logistics_astar.py` (Dijkstra/A\*) se
**elimina**: el ruteo geografico no aplica al negocio.

**Etapa 4 — compras:** `purchase_options.py` (opciones SKU-proveedor),
`optimization_baseline.py` (greedy / knapsack, baselines del curso),
`optimization_flow.py` (min-cost flow).

**Etapa 5 — analisis:** `community_leiden.py` (familias), `pagerank_personalized.py`
(relevancia y recomendacion), `sales_reports.py` (ABC, co-venta, dependencia).

> Los baselines (`optimization_baseline.py`, la variante simple `bfs_path` dentro
> de `graph_paths.py`) se conservan a proposito: son el "antes" contra el que se
> compara el algoritmo investigado. No son codigo muerto.

---

## 7. Carpeta `outputs/`

Todo aqui es **regenerable** y esta **excluido de git** (`.gitignore`). Si se borra,
se reconstruye corriendo los scripts de la seccion 3.

| Subcarpeta | Generada por |
|------------|--------------|
| `stage1_datos/` | `etapa1_ingesta.py` |
| `stage15_datos/` | `etapa1_5_atributos.py` (incluye reglas Gemini cacheadas) |
| `stage15_final/` | `etapa1_5_atributos_llm_finalize.py` (track con LLM) |
| `stage2_graph_datos/` | `etapa2_grafo_semantico.py` + proyeccion + visualizaciones |
| `stage2_graph_final/` | grafo del track con LLM (antes/despues) |
| `stage2_sensitivity/` | `etapa2_sensibilidad_umbral.py` |
| `stage2_transaction_graphs/` | `etapa2_grafos_transaccionales.py` |
| `stage4_optimizacion/` | `etapa4_optimizacion_compras.py` |
| `stage5_analisis/` | `etapa5_analisis_ventas.py` |
| `ferreteria_full/` | `demo_ferreteria_completo.py` (prueba de generalidad) |
| `stage1_latest/` | salida temporal de la app cuando subes archivos manualmente |
| `stage1_demo_ferreteria/`, `stage1_excel_smoke*/` | scripts auxiliares (seccion 5) |
