# Evolución de algoritmos: cómo se resolvía antes vs cómo se resuelve ahora

Documento de sustentación. Cada problema de negocio se resolvió primero con un
algoritmo clásico del curso (el "antes", heredado del proyecto base) y luego se
**investigó y aplicó un algoritmo superior** (el "ahora"). Los baselines no se
eliminaron: siguen en el código (`core/optimization_baseline.py`, métodos
`bfs_path`, `cooccurrence_baseline`...) y cada comparativa es
**ejecutable y medida con los datos reales de Vidra Plastic** (630 productos,
6,928 ventas, 1,907 compras; ver `data/base/PROCEDENCIA.md` para qué es real y
qué es sintético).

---

## 1. Conexión entre entidades: BFS → BFS bidireccional

**Problema:** "¿Qué relación hay entre el cliente X y el proveedor Y?" sobre
G_business (3,678 nodos, 12,567 aristas).

| | Antes | Ahora |
|---|---|---|
| Algoritmo | BFS desde el origen | BFS bidireccional (dos frentes que se encuentran) |
| Complejidad | O(b^d) | O(b^(d/2)) por frente — reducción exponencial |
| Código | `core/graph_paths.py::bfs_path` | `core/graph_paths.py::bidirectional_bfs_path` |
| Referencia | — (curso) | Pohl, I. (1971), *Bi-directional search*, Machine Intelligence 6 |

**Medición real** (cliente ODONTOLOGIA SAN ANTONIO → proveedor ENVIPLAST):
mismo camino óptimo de longitud 4, BFS expandió 8 nodos y el bidireccional 4
(ratio 2.0×). La ventaja crece exponencialmente con la distancia: expandir
siempre la frontera más pequeña acota el frente de búsqueda.

---

## 2. Ruteo logístico (DESCARTADO): por qué NO forzamos A*

**Decisión:** el problema de "ruta geográfica más corta a la sede de un
proveedor" **no aplica al negocio de Vidra Plastic**. No hay decisión real de
ruteo de reparto en la operación y las ubicaciones de sedes de proveedores eran
**sintéticas** (PROCEDENCIA.md). Exhibir A* sobre datos inventados demostraba el
algoritmo pero no resolvía un problema real, así que **se descarta el caso y se
retira `core/logistics_astar.py`** (con él, Dijkstra y A* salen del proyecto).

Para el profesor A* era buen ejemplo de algoritmo investigado, pero en nuestro
caso forzarlo restaba en vez de sumar: un algoritmo sin problema real detrás se
nota. La regla del proyecto es "sin datos sintéticos como protagonistas" (la
misma por la que se descartó esta sección).

**Qué ocupa su lugar como algoritmos investigados, ahora sobre datos reales:**

- **Dinic max-flow / min-cut** (`core/supply_flow_risk.py`) — riesgo y cuello de
  botella de abastecimiento. Ref: Dinic (1970); Ford & Fulkerson (1956).
- **Centralidad de intermediación de Brandes** (`core/centrality_brandes.py`) —
  proveedor más crítico estructuralmente. Ref: Brandes (2001).
- **Reglas de asociación lift/Apriori** (`core/association_rules.py`) — venta
  cruzada. Ref: Agrawal & Srikant (1994).

Mediciones reales de estos tres pendientes de su implementación (ver
`docs/PLAN_ASISTENTE_GRAFOS.md`). BFS bidireccional (sección 1) se conserva: ya no
para mapas, sino como camino explicativo cliente → producto → proveedor.

---

## 3. Pedido multi-SKU: greedy por-SKU → flujo de costo mínimo

**Problema:** asignar un pedido de varios SKUs entre proveedores con
capacidad limitada, minimizando el costo total.

| | Antes | Ahora |
|---|---|---|
| Algoritmo | Heap de precios por SKU independiente (Dijkstra-greedy del proyecto base) | Min-cost flow (successive shortest paths + potenciales de Johnson) |
| Complejidad | O(n log n) por SKU | O(F · E log V), F = caminos aumentantes |
| Código | `core/optimization_baseline.py::per_sku_order` | `core/optimization_flow.py::optimize_order_flow` |
| Referencia | — (curso) | Edmonds & Karp (1972); Ahuja, Magnanti & Orlin (1993), *Network Flows*, cap. 9 |

**La falla del "antes":** optimizar cada SKU por separado ignora que varios
SKUs compiten por la capacidad global del mismo proveedor barato. Nadie decide
*cuál* SKU merece la capacidad escasa.

**Medición real** (pedido demo de 4 SKUs de ENVIPLAST, `etapa4_optimizacion_compras.py`):

| | Baseline por-SKU | Min-cost flow |
|---|---|---|
| Costo reportado | S/ 3,179.98 | S/ 672.00 |
| ¿Factible? | **No** — asigna 6,500 u a ENVIPLAST (capacidad inferida: 2,050 u/día) | Sí — respeta todas las capacidades |
| Unidades sin cubrir | 0 (ilusorio) | 3,900 (déficit honesto) |

El baseline "se ve" más barato por unidad y completo, pero su plan es
**inejecutable**. El flujo asigna la capacidad escasa al SKU donde más reduce
el costo y reporta el déficit real — información accionable (buscar otro
proveedor o escalonar la compra). Capacidades inferidas del historial real
(mayor línea comprada / mayor despacho diario, `core/purchase_options.py`).

**Red de flujo:** FUENTE →(cantidad, S/0) SKU →(capacidad oferta, precio)
PROVEEDOR →(capacidad global, S/0) SUMIDERO.

---

## 4. Familias de productos: componentes conexos → Leiden

**Problema:** descubrir familias semánticas de productos para surtido,
sustitutos y reportes.

| | Antes | Ahora |
|---|---|---|
| Algoritmo | Componentes conexos (BFS) | Leiden sobre la proyección producto–producto ponderada |
| Complejidad | O(V+E) | O(n log n) empírico |
| Código | `core/semantic_graph.py` (métricas) | `core/community_leiden.py` |
| Referencia | — (curso) | Traag, Waltman & van Eck (2019), *From Louvain to Leiden: guaranteeing well-connected communities*, Scientific Reports 9:5233 |

**Medición real:** el baseline ve 6 componentes (el mayor con 444 productos —
inservible como "familia"). Leiden encuentra **15 comunidades con modularidad
0.567**, p.ej. familias de goteros de vidrio ámbar, tapas plásticas 410,
frascos PET transparentes. Se eligió Leiden sobre Louvain porque garantiza
comunidades internamente conectadas (Louvain puede producir comunidades rotas)
y porque la proyección ponderada por confianza (Jaccard ponderado, ver punto 6)
le da pesos significativos.

---

## 5. Relevancia y recomendación: frecuencia → Personalized PageRank

**Problema:** ¿qué productos/clientes son estructuralmente importantes? ¿Qué
recomendar junto a un producto X?

| | Antes | Ahora |
|---|---|---|
| Algoritmo | Ranking por frecuencia de venta; co-ocurrencia directa en factura | PageRank global + PageRank personalizado (random walk con reinicio en X) |
| Complejidad | O(R) | O(k·E) por iteración de potencias hasta convergencia |
| Código | `core/pagerank_personalized.py::cooccurrence_baseline` | `core/pagerank_personalized.py::pagerank` (implementación propia) |
| Referencia | — (curso) | Page, Brin, Motwani & Winograd (1999); Jeh & Widom (2003), *Scaling Personalized Web Search* |

**Diferencia clave medida:** la co-ocurrencia solo ve productos que comparten
documento (distancia 2). PPR puntúa **relaciones multi-salto**: productos que
comparten clientes y fechas sin haber compartido nunca una factura. PageRank no
se dicta en el curso → entra como algoritmo investigado, y se implementó desde
cero (iteración de potencias con amortiguación 0.85) en vez de usar una caja
negra.

---

## 6. La limpieza también es un algoritmo

La detección de esquema y la extracción de atributos (Etapas 1 y 1.5) son una
**cascada de decisión por costo creciente**: alias exacto → similitud de
nombres (token set ratio de rapidfuzz, orden-invariante) → validación
matemática cruzada (cantidad × precio ≈ total) → LLM opcional → humano. Cada
nivel solo se invoca si el anterior no decide: el sistema es determinístico,
auditable y barato por diseño.

Mejora medida de esta entrega: el peso de cada arista de G_attr pasó de la
confianza promedio del producto a la **confianza por atributo**
(`attribute_confidence`), y el umbral 0.75 dejó de ser arbitrario: el análisis
de sensibilidad (`etapa2_sensibilidad_umbral.py`) muestra que el grafo es estable
en [0.60, 0.80] y solo se degrada desde 0.85 — el umbral vive en una meseta y
no manipula el resultado.

La proyección producto–producto usa **Jaccard ponderado** con una identidad
algebraica que evita iterar la unión por par: sim = num / (W(p)+W(q)−num), con
num = Σ min(pesos compartidos), acumulable por atributo en O(Σ_a deg(a)²). Los
atributos hub (ACCESSORY:TAPA, grado 357/630) se excluyen: no discriminan y
dominan el costo cuadrático.

---

## Resumen de complejidades

| Algoritmo | Grafo | Complejidad | Pregunta de negocio |
|---|---|---|---|
| BFS con semillas + scoring | G_attr (790 n) | O(V+E) | ¿Qué producto busca el usuario? |
| BFS bidireccional | G_business (3,678 n) | O(b^(d/2)) | ¿Qué conecta a X con Y? |
| Heap por-SKU (baseline) | opciones compra | O(n log n) | ¿Proveedor más barato por SKU? |
| Knapsack DP (baseline) | opciones compra | O(n·W) | ¿Máximas unidades con presupuesto? |
| **Min-cost flow** | red FUENTE→SKU→PROV→SUMIDERO | O(F·E log V) | ¿Asignación global óptima y factible? |
| Componentes conexos (baseline) | proyección | O(V+E) | ¿Qué está conectado? |
| **Leiden** | proyección producto–producto | O(n log n) | ¿Qué familias de productos existen? |
| **Personalized PageRank** | G_business | O(k·E) | ¿Qué es importante? ¿Qué recomendar? |
| Jaccard ponderado (proyección) | G_attr | O(Σ deg(a)²) | ¿Qué productos se parecen? |
| **Max-flow / Min-cut (Dinic)** | red SUPPLIER→PRODUCT→SINK | O(V²E) | ¿Cuello de botella de abastecimiento? |
| **Betweenness (Brandes)** | G_business | O(V·E) | ¿Proveedor más crítico estructuralmente? |
| **Reglas de asociación (Apriori)** | pseudo-docs de venta | exponencial acotado por soporte | ¿Qué se vende junto (por lift)? |
