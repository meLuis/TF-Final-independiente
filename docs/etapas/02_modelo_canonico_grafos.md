# Etapa 2 - Modelo canonico y grafos

## Objetivo

Construir, a partir de los archivos limpios de la Etapa 1, una representacion estructurada de la empresa usando grafos.

## Entrada

- `products_clean.csv`
- `sales_clean.csv`
- `purchases_clean.csv`
- `product_matches.csv`
- `product_attributes.csv` de Etapa 1.5

## Salida esperada

- `semantic_attribute_graph_nodes.csv`
- `semantic_attribute_graph_edges.csv`
- `semantic_attribute_graph_metrics.json`
- `semantic_attribute_graph_adjacency_sample.csv`

## Nombre del grafo

`G_attr` es un nombre valido para el documento academico y para el codigo como
alias corto de "grafo de atributos".

Para archivos y funciones se usa el nombre mas explicito:

- `semantic_attribute_graph`

Ambos se refieren al mismo grafo.

## G_attr / semantic_attribute_graph

Este primer grafo conecta productos con atributos semanticos confiables.

Nodo principal:

- `PRODUCT:<product_id>`

Nodos de atributo:

- `TYPE:<product_type>`
- `SUBTYPE:<subtype>`
- `ACCESSORY:<accessory>`
- `SHAPE:<shape>`
- `FEATURE:<feature>`
- `MATERIAL:<material>`
- `COLOR:<color>`
- `CAPACITY:<value><unit>`
- `MOUTH_SIZE:<mm>MM`

Aristas:

- `PRODUCT -> TYPE` con relacion `HAS_TYPE`
- `PRODUCT -> SUBTYPE` con relacion `HAS_SUBTYPE`
- `PRODUCT -> ACCESSORY` con relacion `HAS_ACCESSORY`
- `PRODUCT -> SHAPE` con relacion `HAS_SHAPE`
- `PRODUCT -> FEATURE` con relacion `HAS_FEATURE`
- `PRODUCT -> MATERIAL` con relacion `HAS_MATERIAL`
- `PRODUCT -> COLOR` con relacion `HAS_COLOR`
- `PRODUCT -> CAPACITY` con relacion `HAS_CAPACITY`
- `PRODUCT -> MOUTH_SIZE` con relacion `HAS_MOUTH_SIZE`

La arista usa como peso la **confianza de extraccion del atributo** (columna
`attribute_confidence` de la Etapa 1.5), no la confianza promedio del producto.
Asi dos aristas del mismo producto pueden pesar distinto (p.ej. TYPE 0.95 y
ACCESSORY 0.92), reflejando que tan confiable fue cada extraccion individual.
La confianza promedio del producto se conserva como atributo del nodo PRODUCT.

El filtro `min_confidence = 0.75` tambien se aplica **por atributo**: un
producto con un atributo debil no pierde sus atributos fuertes. El valor 0.75
esta justificado empiricamente con `etapa2_sensibilidad_umbral.py`: el grafo es
estable en todo el rango [0.60, 0.80] (las reglas deterministicas emiten
confianzas >= 0.80) y recien a partir de 0.85 se degradan cobertura y
conectividad, de modo que 0.75 vive en una meseta donde el umbral no manipula
el resultado (ver `outputs/stage2_sensitivity/min_confidence_sensitivity.csv`).

### Proyeccion producto-producto

`core/product_projection.py` proyecta el grafo bipartito a un grafo de
similitud entre productos (Jaccard ponderado por confianza sobre atributos
compartidos, excluyendo atributos hub como `ACCESSORY:TAPA` que no
discriminan). Responde "que productos se parecen a X" y alimenta la deteccion
de comunidades (Etapa 5):

```powershell
py TF-Final\etapa2_proyeccion_productos.py
```

Outputs: `product_projection_edges.csv`, `product_projection_top_similar.csv`,
`product_projection_metrics.json` en la carpeta del grafo.

## Que no entra aun

`use_category` no se usa todavia como nodo fuerte porque su precision actual es
menor que la de `product_type`, `color`, `capacity` y `mouth_size`.

Compras, ventas, clientes y proveedores se agregaran en grafos posteriores:

- `G_sales`: producto-cliente-documento/fecha.
- `G_purchases`: producto-proveedor-documento/fecha.
- `G_business`: grafo integrado.

## Ejecucion local

Despues de correr Etapa 1 y Etapa 1.5:

```powershell
py TF-Final\etapa2_grafo_semantico.py
```

Outputs:

```text
TF-Final/outputs/stage2_graph_datos/
```

## Visualizacion para exposicion

Para presentar el grafo no se usa una red con movimiento. La exposicion necesita
imagenes 2D estaticas, reproducibles y faciles de insertar en diapositivas.

Se generan tres PNG:

- `g_attr_attribute_projection.png`: proyeccion de atributos, similar al enfoque
  del proyecto base. Conecta atributos que aparecen juntos en productos.
- `g_attr_product_attribute_focus.png`: subgrafo producto-atributo enfocado en
  los atributos mas conectados y productos representativos.
- `g_attr_frasco_vidrio_ambar.png`: subgrafo de ejemplo para explicar una familia
  semantica concreta.

Ejecucion:

```powershell
py TF-Final\etapa2_visualizaciones.py
```

Outputs:

```text
TF-Final/outputs/stage2_graph_datos/visualizations/
```
