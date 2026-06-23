# Bellman-Ford en el proyecto: ofertas, descuentos y ahorros historicos

## Objetivo

Este documento define un uso defendible de Bellman-Ford dentro del proyecto.
No debe usarse para elegir un proveedor normal cuando todos los costos son
positivos: eso es ranking. Bellman-Ford entra cuando el modelo puede tener
pesos negativos, por ejemplo:

- descuentos por volumen;
- bonificaciones;
- notas de credito;
- cashback;
- combos;
- precio historico por debajo del costo de referencia.

En la version actual no se inventan ofertas. El script genera un CSV desde el
historial real de compras limpio (`purchases_clean.csv`). Si una opcion
producto-proveedor esta por debajo del costo de referencia del producto, esa
diferencia se modela como una arista negativa. Esa arista representa un ahorro
historico observado, no una promocion inventada.

## Regla principal

Bellman-Ford solo se vende como insight real si los pesos salen de datos reales
o de una oferta ingresada explicitamente por el usuario.

No se debe decir:

```text
El sistema descubrio ofertas reales.
```

Si no existe una tabla de ofertas real, se debe decir:

```text
El sistema detecto opciones historicas de ahorro frente al costo de referencia.
Para ofertas nuevas, el gerente puede ingresar escenarios y Bellman-Ford evalua
si el descuento cambia la decision.
```

## Por que Bellman-Ford si encaja aqui

Dijkstra no funciona correctamente con aristas negativas. Si una arista
representa una bonificacion o descuento, el costo puede bajar durante el camino.
Bellman-Ford permite pesos negativos y ademas detecta ciclos negativos.

En negocio, un ciclo negativo significa una inconsistencia del modelo:

```text
comprar -> aplicar descuento -> recibir bonificacion -> volver a comprar
```

Si el costo baja indefinidamente, la promocion esta mal modelada o tiene una
condicion imposible. Detectarlo es util porque evita vender una recomendacion
falsa.

## Entrada requerida

El flujo funciona para cualquier empresa que pase por la Etapa 1 del proyecto.
La empresa sube sus tres archivos:

- productos;
- compras;
- ventas.

Luego se ejecuta la Etapa 1 y se genera:

```text
outputs/stage1_datos/purchases_clean.csv
```

El modulo de Bellman-Ford usa principalmente compras. No necesita internet ni
datos externos.

## Script

Comando principal:

```powershell
cd TF-Final
py etapa6_bellman_ford_ofertas.py
```

Entradas y salidas configurables:

```powershell
py etapa6_bellman_ford_ofertas.py `
  --stage1 outputs/stage1_datos `
  --output outputs/stage6_bellman_ford
```

Para otra empresa, basta con que su Etapa 1 haya generado un directorio con
`purchases_clean.csv`:

```powershell
py etapa6_bellman_ford_ofertas.py `
  --stage1 outputs/empresa_x_stage1 `
  --output outputs/empresa_x_bellman_ford
```

## Archivos generados

El script genera cuatro archivos:

```text
outputs/stage6_bellman_ford/
  bellman_ford_candidates.csv
  bellman_ford_edges.csv
  bellman_ford_best_paths.csv
  bellman_ford_summary.json
```

### 1. `bellman_ford_candidates.csv`

Tabla principal para revisar las opciones producto-proveedor.

Columnas:

| Columna | Significado |
|---|---|
| product_id | Codigo del producto |
| product_name | Nombre del producto |
| supplier | Proveedor |
| supplier_norm | Proveedor normalizado |
| supplier_options | Cantidad de proveedores historicos para ese producto |
| effective_unit_cost | Costo unitario de esa opcion |
| reference_unit_cost | Costo de referencia del producto |
| edge_weight | Peso de la arista: costo efectivo - costo referencia |
| savings_per_unit | Ahorro por unidad: referencia - costo efectivo |
| savings_pct | Ahorro relativo |
| capacity_units | Capacidad inferida para ese producto-proveedor |
| supplier_capacity | Capacidad global inferida del proveedor |
| purchase_lines | Cantidad de lineas historicas de compra |
| last_purchase | Ultima compra observada |
| is_negative_edge | `True` si hay ahorro frente a referencia |
| scenario_type | `historical_saving` o `at_or_above_reference` |

Interpretacion:

- `edge_weight < 0`: opcion mas barata que la referencia.
- `edge_weight = 0`: opcion igual a la referencia.
- `edge_weight > 0`: opcion mas cara que la referencia.

### 2. `bellman_ford_edges.csv`

Grafo que consume Bellman-Ford.

Modelo:

```text
SOURCE -> PRODUCT -> OPTION(producto, proveedor) -> SINK(producto)
```

Aristas:

| Arista | Peso | Significado |
|---|---:|---|
| SOURCE -> PRODUCT | 0 | Inicio del analisis para un producto |
| PRODUCT -> OPTION | costo - referencia | Ahorro o sobrecosto de proveedor |
| OPTION -> SINK | 0 | Fin del camino para ese producto |

La arista importante es `PRODUCT -> OPTION`. Si es negativa, representa ahorro.

### 3. `bellman_ford_best_paths.csv`

Resultado gerencial por producto.

Columnas clave:

| Columna | Significado |
|---|---|
| product_id | Producto analizado |
| best_supplier | Mejor proveedor historico frente a referencia |
| reference_unit_cost | Costo de referencia |
| effective_unit_cost | Costo del proveedor recomendado |
| bellman_ford_distance | Distancia minima; negativa si hay ahorro |
| savings_per_unit | Ahorro por unidad |
| savings_pct | Ahorro porcentual |
| capacity_units | Capacidad inferida para ese producto |
| supplier_capacity | Capacidad global del proveedor |
| has_negative_edge | Indica si la mejor opcion tiene ahorro |

Ejemplo de lectura:

```text
Producto A tiene referencia S/ 1.20.
Proveedor P1 ofrece costo efectivo historico S/ 0.95.
Bellman-Ford devuelve distancia -0.25.
Interpretacion: P1 genera ahorro historico de S/ 0.25 por unidad.
```

### 4. `bellman_ford_summary.json`

Resumen tecnico:

- cantidad de nodos;
- cantidad de aristas;
- productos analizados;
- cantidad de aristas negativas;
- productos con ahorro;
- si existe ciclo negativo.

En el modo automatico actual, el grafo es aciclico por diseno. Por eso no se
esperan ciclos negativos. La deteccion queda lista para escenarios manuales de
ofertas complejas.

## Como se calcula el costo de referencia

Para cada producto:

```text
reference_unit_cost = mediana de avg_unit_cost por proveedor
```

Se usa mediana, no maximo, para evitar inflar artificialmente el ahorro por un
proveedor extremadamente caro.

Luego:

```text
edge_weight = effective_unit_cost - reference_unit_cost
savings_per_unit = reference_unit_cost - effective_unit_cost
savings_pct = savings_per_unit / reference_unit_cost
```

Si `edge_weight` es negativo, Bellman-Ford esta trabajando con una arista
negativa valida.

## Preguntas que puede responder

Preguntas actuales con datos historicos:

- "Que productos tienen opciones historicas por debajo del costo de referencia?"
- "Que proveedor tuvo el mejor costo efectivo para este producto?"
- "Cuanto ahorro por unidad frente al costo de referencia?"
- "Que productos tienen mayor oportunidad de ahorro historico?"

Preguntas futuras con ofertas ingresadas:

- "Conviene esta oferta?"
- "Desde que cantidad el descuento empieza a valer la pena?"
- "Si compro producto A y B juntos, el combo reduce el costo real?"
- "La oferta genera una inconsistencia o ciclo negativo?"

## Diferencia entre ranking y Bellman-Ford

Si solo se quiere elegir el proveedor mas barato:

```text
usar ranking
```

Si hay descuentos, bonificaciones o ahorros representados como pesos negativos:

```text
usar Bellman-Ford
```

Esta distincion es importante para la sustentacion. No se debe forzar
Bellman-Ford donde no hace falta.

## Uso correcto en la narrativa del proyecto

Frase recomendada:

```text
Bellman-Ford se usa para evaluar escenarios donde el costo puede disminuir por
descuentos, bonificaciones o ahorros historicos frente a una referencia. En el
modo automatico, el sistema genera aristas negativas solo cuando el historial de
compras muestra un proveedor por debajo del costo de referencia del producto.
```

Frase que se debe evitar:

```text
Bellman-Ford se usa para elegir el proveedor mas barato.
```

Eso es ranking y seria un encaje forzado.

## Reglas para que funcione en cualquier empresa

El script asume que la Etapa 1 ya normalizo las compras a estas columnas:

- `product_id`;
- `product_name`;
- `supplier`;
- `supplier_norm`;
- `quantity`;
- `analysis_unit_cost`;
- `analysis_total`;
- `date`;
- `is_active`.

Si la empresa sube productos, compras y ventas con nombres de columnas
distintos, la Etapa 1 se encarga de mapearlos. Bellman-Ford no debe leer los
Excel originales; debe leer solo el esquema canonico ya limpio.

## Validaciones minimas

El script debe excluir:

- compras anuladas o inactivas;
- cantidades menores o iguales a cero;
- costos unitarios menores o iguales a cero;
- filas sin producto o proveedor;
- productos sin costo de referencia valido.

El script debe reportar:

- cantidad de productos analizados;
- cantidad de opciones producto-proveedor;
- cantidad de aristas negativas;
- si hay ciclos negativos;
- productos con mayor ahorro.

## Limitaciones honestas

El modo automatico no prueba que exista una promocion vigente. Solo identifica
ahorros historicos frente a una referencia.

Para hablar de "ofertas reales" se necesita una fuente adicional:

- CSV de ofertas ingresado por el gerente;
- cotizaciones de proveedores;
- reglas comerciales reales de descuento;
- bonificaciones documentadas.

Si esas reglas no existen, Bellman-Ford queda como motor de escenarios, no como
descubridor automatico de promociones.

## Extension futura: CSV manual de ofertas

Cuando se quiera agregar ofertas reales, se puede crear un CSV como:

```text
offer_id, supplier, product_id, min_quantity, discount_type, discount_value, bonus_product_id, bonus_quantity, valid_from, valid_to
```

Ejemplos:

```text
OFERTA_001, ENVIPLAST, 5005, 1000, percent, 10, , , 2026-06-01, 2026-06-30
OFERTA_002, PROMELAB, 5004, 500, fixed, 150, , , 2026-06-01, 2026-06-30
OFERTA_003, ENVIPLAST, 5005, 1000, bonus, 0, 5007, 100, 2026-06-01, 2026-06-30
```

Esas reglas se convertirian en aristas negativas adicionales. Ahi la deteccion
de ciclos negativos se vuelve especialmente importante.

## Criterio de exito

El modulo esta bien usado si cumple tres condiciones:

1. Las aristas negativas vienen de datos reales o de escenarios declarados.
2. La respuesta del sistema explica el ahorro, no solo el algoritmo.
3. Se declara si el resultado es historico, simulado o ingresado por usuario.

Si una de esas condiciones falla, Bellman-Ford se vuelve decorativo y debe
quedar fuera de la demo principal.

