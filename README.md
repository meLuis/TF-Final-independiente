# TF Final - Motor Universal de Inteligencia Comercial

Este proyecto busca generalizar el trabajo inicial de Vidra Plastic hacia una plataforma que pueda recibir datos de cualquier empresa y convertirlos en una base limpia para analisis con grafos, algoritmos de optimizacion y asistencia opcional de modelos locales o de pago.

El objetivo ya no es resolver un caso unico, sino construir un flujo adaptable para empresas de distintos rubros: ferreteria, material medico, plasticos, alimentos, farmacia, retail u otros negocios que manejen productos, compras y ventas.

## Entrada esperada

La primera version trabajara con tres archivos tabulares (`.csv`, `.xlsx` o `.xls`):

- `productos`: catalogo o maestro de productos.
- `compras`: historial de compras a proveedores.
- `ventas`: historial de ventas a clientes.

Los nombres de columnas pueden variar por empresa. El sistema debe inferir, validar y permitir corregir el mapeo antes de procesar los datos. Para archivos Excel con varias hojas, la primera version lee la primera hoja.

## Ejecutar la Etapa 1

Instalar dependencias:

```bash
pip install -r TF-Final/requirements.txt
```

Ejecutar la app:

```bash
cd TF-Final
streamlit run app.py
```

La app genera los archivos procesados en:

```text
TF-Final/outputs/stage1_latest/
```

## Ejecutar demo por consola

El proyecto incluye un dataset pequeno de ferreteria para probar la Etapa 1 sin subir archivos manualmente:

```bash
cd TF-Final
python demo_etapa1_ferreteria.py
```

Los resultados se exportan en:

```text
TF-Final/outputs/stage1_demo_ferreteria/
```

## Procesar los Excel reales de `datos/`

```bash
cd TF-Final
python etapa1_ingesta.py
```

Los resultados se exportan en:

```text
TF-Final/outputs/stage1_datos/
```

Ademas de los datasets limpios, esta ejecucion genera tablas de revision:

- `quality_summary.csv`
- `transaction_flags_summary.csv`
- `product_activity_summary.csv`
- `code_pattern_summary.csv`

## Pipeline completo (datos reales de Vidra)

Los nombres de los scripts siguen el orden de etapas. Para un mapa archivo-por-archivo
(que consume y que produce cada uno) ver **[GUIA.md](GUIA.md)**.

```powershell
py etapa1_ingesta.py                   # Etapa 1: ingesta y normalizacion
py etapa1_5_atributos.py               # Etapa 1.5: extraccion de atributos (reglas)
py etapa2_grafo_semantico.py           # Etapa 2: G_attr (790 nodos)
py etapa2_proyeccion_productos.py      # Etapa 2: proyeccion producto-producto
py etapa2_sensibilidad_umbral.py       # Etapa 2: justificacion del umbral 0.75
py etapa2_grafos_transaccionales.py    # Etapa 2: G_purchases / G_sales / G_business (3,678 nodos)
py etapa2_visualizaciones.py           # Etapa 2: PNGs estaticos de G_attr
py etapa4_optimizacion_compras.py      # Etapa 4: baselines vs min-cost flow
py etapa5_analisis_ventas.py           # Etapa 5: Leiden, PageRank, ABC, co-venta
py demo_ferreteria_completo.py         # Prueba de generalidad (otro rubro, mismo codigo)
```

Etapa 3 (busqueda, conexiones y rutas) no tiene script de consola: vive en la app
(`pages/`) sobre los grafos ya generados. La Etapa 1.5 admite una capa opcional de
LLM (Gemini) para enriquecer atributos; ver GUIA.md y `docs/etapas/01.5_extraccion_atributos.md`.

### Antes vs despues del LLM (Etapa 1.5)

El track determinista (sin LLM) y el track con Gemini son comparables y producen
dos grafos:

| Grafo | Origen | Nodos | Aristas |
|-------|--------|-------|---------|
| `outputs/stage2_graph_datos` | reglas deterministas | 790 | 2,518 |
| `outputs/stage2_graph_final` | reglas + Gemini (aceptado, sin regresion) | 805 | 2,651 |

Las visualizaciones de cada uno (`.../visualizations/*.png`) son el "antes/despues"
de grafos para la sustentacion. Regenerar el track Gemini no requiere API key
(reusa las reglas cacheadas): `py etapa1_5_atributos_llm_finalize.py`.

La data base (3 xlsx reales + enriquecimientos sinteticos declarados) vive en
`data/base/` — ver `data/base/PROCEDENCIA.md`.

## Grafos

| Grafo | Nodos | Aristas | Pregunta que responde |
|-------|-------|---------|----------------------|
| G_attr (semantic_attribute_graph) | 790 | 2,518 | ¿Que producto busca el usuario? |
| Proyeccion producto-producto | 472 conectados | 6,159 | ¿Que productos se parecen? |
| G_purchases | 1,361 | 2,887 | ¿A quien se compro, cuando y a que precio? |
| G_sales | 3,063 | 9,680 | ¿Quien compra que? |
| **G_business** (union) | **3,678** | **12,567** | Vista integral del negocio |

## Algoritmos (antes vs ahora)

Cada problema tiene un baseline del curso (se conserva en el codigo) y un
algoritmo investigado con su comparativa medida — ver
[docs/ALGORITMOS_EVOLUCION.md](docs/ALGORITMOS_EVOLUCION.md):

| Problema | Antes (curso) | Ahora (investigado) |
|---|---|---|
| Conexion entre entidades | BFS O(b^d) | **BFS bidireccional** O(b^(d/2)) |
| Ruteo de proveedores | Dijkstra | **A\*** con heuristica haversine |
| Pedido multi-SKU | greedy por-SKU | **Min-cost flow** (successive shortest paths) |
| Familias de productos | componentes conexos | **Leiden** (Traag et al. 2019) |
| Relevancia / recomendacion | frecuencia, co-ocurrencia | **Personalized PageRank** |

## Documentacion por etapas

- [Etapa 1 - Ingesta y normalizacion](docs/etapas/01_ingesta_normalizacion.md)
- [Etapa 1.5 - Extraccion de atributos](docs/etapas/01.5_extraccion_atributos.md)
- [Etapa 2 - Modelo canonico y grafos](docs/etapas/02_modelo_canonico_grafos.md)
- [Etapa 3 - Busqueda y consulta semantica](docs/etapas/03_busqueda_consulta_semantica.md)
- [Etapa 4 - Optimizacion de compras](docs/etapas/04_optimizacion_compras.md)
- [Etapa 5 - Analisis de ventas y reportes](docs/etapas/05_analisis_ventas_reportes.md)
- [Evolucion de algoritmos (sustentacion)](docs/ALGORITMOS_EVOLUCION.md)
- [Calculos, indicadores (%) y busqueda semantica](docs/CALCULOS_Y_BUSQUEDA_SEMANTICA.md)

## Principio tecnico

El sistema debe ser economico, auditable y robusto. Por eso la base sera:

1. Reglas deterministicas con `pandas`.
2. Validaciones estadisticas y matematicas.
3. Coincidencia difusa con `rapidfuzz`.
4. Revision humana de casos ambiguos.
5. LLM local o de pago solo como ayuda opcional, no como unica fuente de verdad.
