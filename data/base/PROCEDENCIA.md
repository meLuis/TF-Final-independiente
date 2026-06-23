# Procedencia de la data base de TF-Final

Esta carpeta es la **fuente canónica** de datos de entrada de TF-Final. Todo lo que
el pipeline consume como información base vive aquí (o en `data/demo/` para la demo
de ferretería). Cualquier dato que no esté en esta carpeta es **derivado** (outputs
de etapas) y se regenera ejecutando los scripts `run_stage*.py`.

## Datos reales (exportados de los sistemas de Vidra Plastic)

| Archivo | Contenido | Filas aprox. |
|---------|-----------|--------------|
| `productos.xlsx` | Catálogo maestro completo (630 productos) | 630 |
| `ventas.xlsx` | Historial de ventas a clientes | 6,928 |
| `items_compras.xlsx` | Historial de compras a proveedores (precios, fechas, facturas) | 1,907 |

Estos tres archivos son los **únicos datos 100% reales** del proyecto. Ninguno
contiene información de ubicación geográfica.

## Datos generados (enriquecimiento sintético)

| Archivo | Contenido | Qué es sintético |
|---------|-----------|------------------|
| `proveedores.csv` | 38 sedes de 22 proveedores con departamento/provincia/distrito y tiempo de entrega | **Toda la ubicación geográfica y los tiempos de entrega son generados.** Los nombres de proveedores sí son reales (provienen de `items_compras.xlsx`). La columna `tipo_sede` distingue sedes "Real" (el proveedor existe en el historial) de "Ficticia" (sede agregada para cobertura), pero **incluso las sedes "Real" tienen ubicación asignada sintéticamente**, porque los xlsx originales no traen ubicación. |

Origen: generado en el proyecto base (`datos/generar_dataset.py`, seed=42) para
garantizar ≥2 opciones de proveedor por SKU y habilitar análisis logístico.

## Datos derivados usados como benchmark

| Archivo | Contenido | Rol |
|---------|-----------|-----|
| `catalogo.csv` | 282 productos plásticos con atributos curados (tipo, material, color, volumen, boca, cierre) | **Golden set** para validar la extracción de atributos de la Etapa 1.5 (`etapa1_5_atributos.py`, `etapa1_5_atributos_llm_finalize.py`). Derivado de `productos.xlsx` con curaduría manual + reglas en el proyecto base; no es dato crudo, pero sí información base del pipeline de validación. |

## Implicancia para la sustentación

- Los algoritmos sobre precios, fechas, productos, clientes y proveedores
  (búsqueda, min-cost flow, Leiden, PageRank, ABC, y los nuevos Dinic
  max-flow/min-cut, Brandes y reglas de asociación) trabajan sobre **datos
  reales**.
- El ruteo geográfico (Dijkstra/A* con heurística haversine) se **descartó**
  precisamente porque dependía de la ubicación sintética y no aplica al negocio.
  No se fuerza ese algoritmo. La ubicación geográfica de `proveedores.csv` queda
  sin uso en el producto; solo `tiempo_entrega_dias` se sigue usando (declarado
  como sintético) en `core/purchase_options.py`.

## Regla de mantenimiento

Si se incorpora cualquier archivo nuevo como información base (de Vidra o de otra
empresa), debe copiarse a esta carpeta y registrarse en este documento indicando
si es real o generado, y cómo se generó.
