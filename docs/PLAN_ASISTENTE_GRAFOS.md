# Plan del asistente local basado en grafos y algoritmos

## Idea central

El proyecto debe evolucionar hacia una caja de texto principal donde el gerente
pueda escribir preguntas naturales sobre la tienda. El sistema no debe mostrar
primero nombres tecnicos como BFS, PageRank o min-cost flow; esos algoritmos
deben funcionar como motores internos.

Ejemplos de preguntas objetivo:

- "Que me pide mas el cliente X?"
- "De donde suelo comprar lo que me pide el cliente X?"
- "Tengo S/ 2000, cuanto puedo comprar de frasco gotero ambar 30 ml?"
- "Que proveedor me conviene para este pedido?"
- "Que productos se venden junto con este?"
- "Que pasa si pierdo este proveedor?"

La arquitectura general seria:

```text
Pregunta del gerente
  -> router de intencion
  -> resolver de entidades
  -> motor algoritmico
  -> respuesta natural + tabla + evidencia
```

Todo debe funcionar sin internet, usando los datos locales ya procesados.

## Validacion de grafos existentes

El proyecto ya tiene grafos grandes, por lo que no parte de cero:

| Grafo | Nodos | Aristas | Uso principal |
|---|---:|---:|---|
| G_attr | 790 | 2,518 | Busqueda semantica de productos por atributos |
| G_attr con LLM | 805 | 2,651 | Variante enriquecida para comparacion antes/despues |
| G_purchases | 1,361 | 2,887 | Compras producto-proveedor-documento-fecha |
| G_sales | 3,063 | 9,680 | Ventas cliente-producto-documento-fecha |
| G_business | 3,678 | 12,567 | Union de compras y ventas sobre productos |
| Proyeccion producto-producto | 472 productos conectados | 6,159 | Similitud, familias y sustitutos |

Conclusion: ya existen al menos dos grafos de mas de 1,500 nodos:
`G_sales` y `G_business`. El objetivo ahora no es solo crear grafos mas grandes,
sino crear grafos derivados que respondan preguntas concretas.

## Decision sobre rutas fisicas (descartadas)

La seccion de rutas fisicas con Dijkstra/A* se **elimina por completo** del
producto. Aunque el algoritmo era correcto, dependia de sedes sinteticas y se
sentia alejado de la realidad comercial de la tienda. Se retira
`core/logistics_astar.py`, su pestaña y toda mencion a mapas/sedes/rutas
geograficas.

Con esto **Dijkstra y A* salen del proyecto**. El hueco de "algoritmo investigado"
que dejan se cubre con algoritmos nuevos sobre datos reales (ver seccion
"Algoritmos investigados nuevos"): Dinic max-flow/min-cut, centralidad de
intermediacion de Brandes y reglas de asociacion (lift/Apriori).

> `core/graph_paths.py` (BFS bidireccional) **se conserva**: ya no para mapas, sino
> como camino explicativo cliente -> producto -> proveedor (seccion 3). Solo se
> retira lo geografico.

## Inventario de algoritmos ya implementados

Punto de partida real: la mayoria de motores avanzados ya existe en `core/`. El
trabajo no es crearlos de cero, sino orquestarlos tras una caja de texto y sumar
los tres que faltan.

| Algoritmo investigado | Modulo | Baseline que conserva |
|---|---|---|
| Min-cost flow (successive shortest paths + potenciales de Johnson) | `optimization_flow.py` | greedy por SKU (`optimization_baseline.py`) |
| Personalized PageRank + PageRank global | `pagerank_personalized.py` | co-ocurrencia directa |
| Leiden (comunidades) | `community_leiden.py` | componentes conexos |
| BFS bidireccional (Pohl 1971) | `graph_paths.py` | BFS clasico |
| Bellman-Ford (ahorros/ofertas) | `bellman_ford_offers.py` | costo de referencia / orden topologico |
| Busqueda semantica BFS + filtro exacto | `semantic_search.py` | fuzzy/substring |

## Algoritmos investigados nuevos (datos reales, no sinteticos)

Tres modulos nuevos en `core/`, todos sobre outputs reales ya existentes
(`stage1_datos/`, `stage2_transaction_graphs/`):

- **Dinic max-flow / min-cut** (`core/supply_flow_risk.py`) -> seccion 10. Red
  SOURCE -> SUPPLIER -> PRODUCT -> SINK con capacidades inferidas del historial.
  El min-cut identifica el cuello de botella de abastecimiento. Refs: Dinic
  (1970); Ford & Fulkerson (1956).
- **Centralidad de intermediacion de Brandes** (`core/centrality_brandes.py`) ->
  secciones 4 y 10. Betweenness exacta O(VE) sobre G_business; detecta
  proveedores/productos "puente" criticos aunque no sean los de mayor grado. Ref:
  Brandes (2001).
- **Reglas de asociacion lift/Apriori** (`core/association_rules.py`) -> seccion 9.
  Soporte/confianza/lift sobre pseudo-documentos de venta; "si compra A -> ofrece
  B" priorizado por lift, no por conteo bruto. Ref: Agrawal & Srikant (1994).

## Diez secciones propuestas

### 1. Buscador de producto

Pregunta que responde:

- "Que producto quiso decir el usuario?"
- "Busca frasco gotero ambar 30 ml."
- "Que alternativas parecidas tengo?"

Grafo o datos:

- G_attr.
- Catalogo limpio.
- Historial de ventas para desempatar por popularidad.

Algoritmos:

- BFS semantico sobre atributos.
- Fuzzy matching por nombre.
- Filtros exactos para capacidad, boca o medida.
- Personalized PageRank para productos similares.

Resultado esperado:

```text
Producto mas probable: FRASCO GOTERO VIDRIO AMBAR 30ML
Confianza: alta
Alternativas: producto A, producto B, producto C
```

### 2. Perfil de cliente

Pregunta que responde:

- "Que me pide mas el cliente X?"
- "Cuales son sus productos frecuentes?"
- "Cuanto representa este cliente?"

Grafo nuevo:

- G_cliente_producto.

Nodos:

- CLIENT.
- PRODUCT.

Aristas:

- CLIENT -> PRODUCT con peso por monto, cantidad, frecuencia y ultima compra.

Algoritmos:

- Ranking ponderado.
- Agregacion por cliente-producto.
- PageRank personalizado desde el cliente.

Resultado esperado:

```text
El cliente X compra principalmente estos productos:
1. Producto A - cantidad total, monto total, frecuencia
2. Producto B - cantidad total, monto total, frecuencia
3. Producto C - cantidad total, monto total, frecuencia
```

### 3. Cliente y abastecimiento

Pregunta que responde:

- "De donde suelo comprar lo que me pide el cliente X?"
- "Que proveedor abastece los productos que mas compra este cliente?"
- "Si este cliente vuelve a pedir, que proveedores necesito revisar?"

Grafo nuevo:

- G_cliente_producto_proveedor.

Nodos:

- CLIENT.
- PRODUCT.
- SUPPLIER.

Aristas:

- CLIENT -> PRODUCT desde ventas.
- PRODUCT -> SUPPLIER desde compras.

Algoritmos:

- Base: join ventas+compras y ranking proveedor-producto por frecuencia, costo y
  ultima compra (agregacion, no es un problema de caminos).
- Investigado: **BFS bidireccional** solo como camino explicativo
  cliente -> producto -> proveedor, comparado honestamente contra BFS clasico
  (ratio de expansion sobre G_business).

Resultado esperado:

```text
El cliente X pide principalmente producto A, B y C.
Esos productos normalmente se compran a proveedor P1 y P2.
Producto critico: producto A, porque depende de un solo proveedor.
```

### 4. Proveedor conveniente

Pregunta que responde:

- "A quien le compro este producto?"
- "Que proveedor me conviene por precio?"
- "Que proveedor tiene mejor historial para este SKU?"

Grafo nuevo:

- G_producto_proveedor.

Nodos:

- PRODUCT.
- SUPPLIER.

Aristas:

- PRODUCT -> SUPPLIER con costo unitario, frecuencia, capacidad inferida,
  ultima compra y variacion de precio.

Algoritmos:

- Base: ranking multicriterio (precio minimo, frecuencia, ultima compra). Elegir
  proveedor de un SKU es un ranking, no un camino: no se usa Dijkstra.
- Investigado: **centralidad de intermediacion de Brandes** sobre G_business como
  señal de confiabilidad/criticidad estructural del proveedor, contra el baseline
  de centralidad de grado.

Resultado esperado:

```text
Para este producto, el proveedor mas conveniente historicamente es P1.
Precio minimo observado: S/ X
Capacidad inferida: Y unidades
Ultima compra: fecha
```

### 5. Pedido optimo multi-SKU

Pregunta que responde:

- "Necesito 1000 de A y 500 de B, a quien compro?"
- "El proveedor mas barato puede cubrir todo?"
- "Que parte queda sin cubrir?"

Grafo o red:

- Red de flujo: SOURCE -> SKU -> SUPPLIER -> SINK.

Algoritmos:

- Min-cost flow.
- Baseline greedy por SKU para comparar.

Resultado esperado:

```text
Plan optimo:
- Comprar 1000 unidades de A a P1.
- Comprar 300 unidades de B a P2.
- Quedan 200 unidades sin cubrir.

El plan greedy parecia mas barato, pero violaba capacidad del proveedor.
```

### 6. Presupuesto y mochila

Pregunta que responde:

- "Tengo S/ 2000, cuanto puedo comprar de este producto?"
- "Con S/ 5000, que combinacion me conviene comprar?"
- "Como maximizo unidades, margen o cobertura con presupuesto limitado?"

Grafo o estructura:

- Opciones producto-proveedor como items o lotes.

Algoritmos:

- Knapsack 0/1 para elegir lotes.
- Knapsack acotado si cada proveedor tiene capacidad maxima.
- Knapsack no acotado si se permite comprar unidades repetidas.
- Programacion dinamica.

Resultado esperado:

```text
Con S/ 2000 puedes comprar hasta X unidades del producto A.
Proveedor recomendado: P1
Costo total: S/ Y
Sobrante: S/ Z
```

### 7. Ofertas y descuentos

Pregunta que responde:

- "Conviene esta oferta?"
- "Si el proveedor me descuenta por volumen, cambia la decision?"
- "Hay una combinacion con bonificacion que reduzca el costo real?"

Estado: **ya implementado** en `etapa6_bellman_ford_ofertas.py` +
`core/bellman_ford_offers.py`. Corre sobre las compras reales que sube el cliente
(`purchases_clean.csv` de Etapa 1); no inventa promociones.

Grafo (real, derivado del historial):

- SOURCE -> PRODUCT -> OPTION(producto, proveedor) -> SINK.
- Peso de cada arista producto->opcion = costo unitario - costo de referencia
  (mediana por producto). Peso negativo = ahorro historico real frente a la
  referencia.

Algoritmos:

- Base: costo de referencia por producto / orden topologico (el grafo es un DAG,
  asi que el camino minimo se resuelve en O(V+E)).
- Investigado: **Bellman-Ford** porque admite pesos negativos y deja lista la
  deteccion de ciclos negativos para cuando el cliente cargue ofertas/canjes
  cruzados que si formen ciclos.

> Matiz honesto para sustentacion: con el grafo actual (DAG) **nunca** hay ciclo
> negativo; esa parte de Bellman-Ford queda como salvaguarda para el `.csv` de
> ofertas reales. La narrativa es "Bellman-Ford es el algoritmo general; para
> nuestro DAG el orden topologico bastaria, pero lo usamos porque habilita los
> casos con ciclos".

Resultado esperado:

```text
Para producto A, el proveedor con mayor ahorro historico es P1.
Costo de referencia: S/ X  ->  costo efectivo: S/ Y  (ahorro Z%).
Advertencia: si al cargar ofertas aparece un ciclo negativo, la oferta genera una
ganancia artificial en el modelo y debe revisarse.
```

### 8. Familias, sustitutos y productos parecidos

Pregunta que responde:

- "Que productos son parecidos a este?"
- "Si no tengo stock, que alternativa puedo ofrecer?"
- "Que familias comerciales tengo?"

Grafo existente:

- Proyeccion producto-producto.

Algoritmos:

- Jaccard ponderado.
- Leiden para comunidades.
- Componentes conexos como baseline.
- Personalized PageRank para sustitutos cercanos.

Resultado esperado:

```text
Este producto pertenece a la familia: frascos goteros de vidrio ambar.
Alternativas cercanas:
1. Producto A
2. Producto B
3. Producto C
```

### 9. Venta cruzada y recomendacion

Pregunta que responde:

- "Si compra esto, que mas le ofrezco?"
- "Que productos se venden juntos?"
- "Que combo podria armar?"

Grafos o datos:

- G_sales.
- G_business.
- Tabla de co-venta.

Algoritmos:

- Base: co-ocurrencia directa (`sales_reports.co_sales`).
- Investigado: **reglas de asociacion lift/Apriori** (`core/association_rules.py`)
  para priorizar por lift y no por conteo bruto, mas Personalized PageRank para
  cercania estructural multi-salto.

Resultado esperado:

```text
Cuando se vende producto A, suelen aparecer tambien:
1. Producto B
2. Producto C
3. Producto D

Recomendacion: ofrecer B como complemento principal.
```

### 10. Riesgo y dependencia

Pregunta que responde:

- "Que pasa si pierdo este proveedor?"
- "Que productos quedan en riesgo?"
- "Cual es mi cuello de botella de abastecimiento?"
- "Que proveedor es mas critico?"

Grafo nuevo:

- G_riesgo_abastecimiento.

Nodos:

- SUPPLIER.
- PRODUCT.
- CLIENT o DEMAND.

Aristas:

- SUPPLIER -> PRODUCT con capacidad/costo/frecuencia.
- PRODUCT -> DEMAND con demanda historica.

Algoritmos:

- Base: % de dependencia por proveedor (`sales_reports.supplier_dependency`) e
  impacto por componentes ante eliminacion de un proveedor.
- Investigado: **Max-flow / Min-cut con Dinic** (`core/supply_flow_risk.py`) para
  la capacidad maxima de abastecimiento; el min-cut marca el cuello de botella.
  **Centralidad de Brandes** (`core/centrality_brandes.py`) para el proveedor mas
  critico estructuralmente.

Resultado esperado:

```text
Si se pierde proveedor P1, se afectan X productos y S/ Y de ventas historicas.
Productos mas vulnerables:
1. Producto A
2. Producto B
3. Producto C

Cuello de botella principal: proveedor P1 -> producto A.
```

## Tabla maestra: baseline (curso) vs investigado por seccion

Columna vertebral de la sustentacion. Cada seccion conserva su baseline del curso
y expone el algoritmo investigado ("usamos este, pero investigamos este otro mejor
porque...").

| # | Seccion | Baseline (curso) | Investigado (se expone) | Modulo |
|---|---|---|---|---|
| 1 | Buscador producto | fuzzy/substring | BFS semantico + filtro exacto + PPR | `semantic_search`, `pagerank_personalized` |
| 2 | Perfil cliente | ranking por monto/frecuencia | Personalized PageRank (reinicio en CLIENT) | `pagerank_personalized` |
| 3 | Cliente -> abastecimiento | join + ranking | BFS bidireccional (camino explicativo) | `graph_paths` |
| 4 | Proveedor conveniente | min. precio / grado | Betweenness (Brandes) + ranking multicriterio | `centrality_brandes` (nuevo) |
| 5 | Pedido optimo multi-SKU | greedy por SKU | Min-cost flow | `optimization_flow` |
| 6 | Presupuesto/mochila | greedy por ratio | Knapsack DP (0/1, acotado, no acotado) | `optimization_baseline` |
| 7 | Ofertas/ahorros | costo de referencia / topologico | Bellman-Ford (negativos; DAG) | `bellman_ford_offers` |
| 8 | Familias/sustitutos | componentes conexos | Leiden + PPR | `community_leiden`, `pagerank_personalized` |
| 9 | Venta cruzada | co-ocurrencia directa | Reglas de asociacion lift/Apriori + PPR | `association_rules` (nuevo) |
| 10 | Riesgo/dependencia | % dependencia + componentes | Max-flow/Min-cut (Dinic) + Brandes | `supply_flow_risk` (nuevo), `centrality_brandes` (nuevo) |

## Router de intenciones

El asistente debe usar reglas locales para clasificar la pregunta. No necesita
internet ni LLM externo para la primera version.

Ejemplos:

| Palabras o patrones | Intencion |
|---|---|
| "busca", "producto", "parecido", "alternativa" | buscar_producto |
| "cliente", "pide", "compra mas" | perfil_cliente |
| "de donde", "suelo comprar", "abastecer" | cliente_abastecimiento |
| "proveedor", "conviene", "barato" | proveedor_conveniente |
| "necesito", "pedido", cantidades multiples | pedido_optimo |
| "presupuesto", "S/", "cuanto puedo" | presupuesto_mochila |
| "oferta", "descuento", "bonificacion" | ofertas_descuentos |
| "familia", "sustituto", "similar" | familias_sustitutos |
| "junto", "combo", "recomendar" | venta_cruzada |
| "riesgo", "dependo", "pierdo proveedor" | riesgo_dependencia |

## Salida estandar de cada motor

Cada motor deberia devolver la misma estructura:

```text
answer: respuesta breve en lenguaje natural
table: tabla con evidencia
intent: intencion detectada
entities: entidades detectadas
algorithm: algoritmo usado
evidence: archivos o grafos consultados
```

Esto permite que Streamlit muestre cualquier respuesta de manera uniforme.

## Prioridad de implementacion

### Fase 1: caja de texto util

- Router de intenciones.
- Resolver de producto.
- Perfil de cliente.
- Cliente y abastecimiento.
- Presupuesto/mochila.
- Pedido optimo.

### Fase 2: motores avanzados

- Ofertas con Bellman-Ford (ya implementado en Etapa 6; ajustar `best_paths` para
  que derive de las distancias del algoritmo, no de un sort).
- Riesgo con max-flow/min-cut Dinic (`core/supply_flow_risk.py`, nuevo).
- Proveedor/riesgo critico con Brandes (`core/centrality_brandes.py`, nuevo).
- Venta cruzada con reglas de asociacion lift/Apriori (`core/association_rules.py`,
  nuevo).
- Sustitutos con Leiden/PPR (ya implementado).

### Fase 3: presentacion final

- Respuesta natural.
- Tabla de evidencia.
- Algoritmo usado.
- Explicacion corta de por que ese algoritmo aplica.
- Vista tecnica opcional para sustentacion.

## Decision de secuencia (2026-06-23): 10 secciones ahora, caja de texto despues

Hay una tension en este plan: la "Idea central" pide **una caja de texto** y al
mismo tiempo lista **diez secciones**. Quedan resueltas asi, por fases:

1. **Ahora (esta etapa):** se construyen las **10 secciones VISIBLES** como
   pestañas, para mostrarle al equipo algo concreto y navegable. Meta de alcance:
   las 10 funcionando con datos reales (incluye los 3 grafos y 3 modulos nuevos).
2. **Despues (otra sesion):** se antepone la **caja de texto** + router. Las 10
   pestañas pasan a ser "Vista tecnica / sustentacion", no la experiencia
   principal.

Para que el paso 2 sea barato (no una reescritura), el paso 1 debe respetar dos
reglas de arquitectura desde el inicio:

- **Cascara delgada:** cada pestaña solo pinta; toda la logica de algoritmos vive
  en `core/`. (Pendiente: `pages/3_Conexiones_y_Rutas.py` aun mezcla logica en la
  pagina; mover a `core/`.)
- **Contrato unico:** cada motor devuelve la misma estructura
  (`answer/table/intent/entities/algorithm/evidence`, ver "Salida estandar de cada
  motor"). Asi la futura caja de texto solo agrega el router por delante y reusa
  los mismos motores.

Estado: decision registrada; implementacion aun no iniciada.

## Narrativa final del proyecto

El proyecto no debe presentarse como una coleccion de algoritmos sueltos.
Debe presentarse como:

> Un asistente local de inteligencia comercial que responde preguntas naturales
> sobre ventas, clientes, productos, proveedores, compras, ofertas y riesgo,
> usando grafos y algoritmos de optimizacion sin depender de internet.

Los algoritmos no sobran: quedan ocultos como motores especializados que
resuelven preguntas reales del negocio.

