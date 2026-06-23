# Etapa 5 - Analisis de Ventas y Reportes  [IMPLEMENTADA]

## Objetivo

Explicar el comportamiento comercial de la empresa a partir de los datos
normalizados y los grafos.

## Decision de formato

El reporte vive como **tablas CSV + resumen JSON** generados por
`etapa5_analisis_ventas.py` y se visualiza en la app Streamlit (resuelve el
"Pendiente" original).

## Que se implemento

### 1. Familias de productos: Leiden (`core/community_leiden.py`)

Deteccion de comunidades **Leiden** (Traag et al. 2019) sobre la proyeccion
producto-producto ponderada (Jaccard ponderado por confianza). Baseline
comparado: componentes conexos. Con datos de Vidra: 6 componentes (el mayor
con 444 productos, inservible como familia) → **15 comunidades, modularidad
0.567** (goteros vidrio ambar, tapas 410, frascos PET, etc.).

### 2. Relevancia y recomendacion: Personalized PageRank (`core/pagerank_personalized.py`)

- PageRank global sobre G_business → productos y clientes estructuralmente
  importantes (no solo los mas frecuentes).
- PageRank **personalizado** (reinicio en un producto) → "relacionados a X"
  capturando relaciones multi-salto que la co-ocurrencia directa no ve.
- Implementacion propia (iteracion de potencias, d=0.85), O(k·E).
- Baseline comparado: co-ocurrencia en documento (`cooccurrence_baseline`).

### 3. Reportes clasicos (`core/sales_reports.py`)

- **Analisis ABC** (Pareto 80/15/5) sobre el valor vendido.
- **Co-venta**: pares de productos vendidos juntos (pseudo-doc cliente+fecha).
- **Dependencia de proveedor**: concentracion del valor comprado con alertas
  (>30% ALTA, >15% MEDIA). Con datos reales: ENVIPLAST concentra 27% (MEDIA).

## Ejecucion

```powershell
py TF-Final\etapa5_analisis_ventas.py
py TF-Final\etapa5_analisis_ventas.py --related-to 5019   # demo PPR para un SKU
```

Outputs: `outputs/stage5_analisis/` (comunidades, rankings PageRank, ABC,
co-ventas, dependencia, `stage5_summary.json`).

## Mediciones

Ver `docs/ALGORITMOS_EVOLUCION.md`, secciones 4 y 5.
