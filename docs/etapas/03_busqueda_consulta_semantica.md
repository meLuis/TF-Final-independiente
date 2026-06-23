# Etapa 3 - Busqueda y Consulta Semantica  [IMPLEMENTADA]

## Objetivo

Permitir consultar productos y relaciones comerciales usando lenguaje natural
o filtros simples, sobre los grafos de la Etapa 2.

> La derivación completa del **scoring** (decaimiento por distancia, multiplicador
> de cobertura `(cov/S)²·20+1`, ponderación por confianza de arista, filtro exacto)
> con sus fórmulas, complejidad y fuentes para citar está en
> [../CALCULOS_Y_BUSQUEDA_SEMANTICA.md](../CALCULOS_Y_BUSQUEDA_SEMANTICA.md) §1.

## Que se implemento

### 1. Busqueda semantica con BFS (`core/semantic_search.py`)

- El vocabulario se **aprende del grafo** (labels de los nodos atributo de
  G_attr): cero reglas de dominio hardcodeadas — el mismo buscador funciona
  para plasticos o ferreteria.
- Flujo: query → semillas (nodos atributo) → BFS O(V+E) con decaimiento por
  distancia → boost por cobertura de semillas → top-k.
- **Filtro exacto numerico** (regla heredada del proyecto base): si el usuario
  pide 100ML solo se devuelven productos de exactamente 100ML; si pide una
  capacidad que no existe (123ML), el resultado es vacio — nunca se aproxima.
- El puntaje pondera cada arista por su confianza de extraccion (Etapa 2).

```python
from core.semantic_search import SemanticSearchIndex
idx = SemanticSearchIndex.from_stage2_dir("outputs/stage2_graph_datos")
idx.search("frasco gotero vidrio ambar 5ml", k=10)
```

### 2. Conexiones entre entidades (`core/graph_paths.py`)

"¿Que conecta al cliente X con el proveedor Y?" sobre G_business: el camino
mas corto (cliente → documento → producto → documento → proveedor) es una
explicacion legible de la relacion.

- Baseline: BFS clasico O(b^d).
- **BFS bidireccional** O(b^(d/2)): dos frentes que se encuentran; se expande
  siempre la frontera mas chica. `compare()` corre ambos y reporta nodos
  expandidos por cada uno.

### 3. Ruteo logistico (DESCARTADO)

El caso de ruta geografica más corta (Dijkstra vs A* con heurística haversine) se
**elimina**: no aplica al negocio y dependía de sedes de proveedores sintéticas.
No se fuerza A*; se retira `core/logistics_astar.py`. Su rol de "algoritmo
investigado" lo ocupan, sobre datos reales, Dinic max-flow/min-cut (riesgo),
Brandes (proveedor crítico) y reglas de asociación lift/Apriori (venta cruzada).
Ver `docs/PLAN_ASISTENTE_GRAFOS.md`.

## Mediciones

Ver `docs/ALGORITMOS_EVOLUCION.md`, sección 1 (BFS bidireccional).
