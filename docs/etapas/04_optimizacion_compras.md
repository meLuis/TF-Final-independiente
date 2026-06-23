# Etapa 4 - Optimizacion de Compras  [IMPLEMENTADA]

## Objetivo

Recomendar a que proveedor comprar y como dividir un pedido multi-SKU,
usando historial de compras y disponibilidad inferida.

## Decision de alcance

La primera version **optimiza un pedido ingresado por el usuario** (resuelve
el "Pendiente" original). La cantidad sugerida puede derivarse de la demanda
promedio de G_sales.

## Que se implemento

### 1. Opciones de compra inferidas (`core/purchase_options.py`)

Equivalente generalizado del G_opt del proyecto base, pero inferido de datos
reales (compras limpias de Etapa 1):

- `unit_cost`: costo minimo observado por (producto, proveedor).
- `capacity_units`: mayor cantidad entregada en una linea (disponibilidad inferida).
- `supplier_capacity`: mayor despacho total en un dia (capacidad global inferida).
- `delivery_days`: de `data/base/proveedores.csv` si existe (**sintetico**,
  declarado), si no default.

### 2. Baselines portados del proyecto base (`core/optimization_baseline.py`) — no se eliminan

- `cheapest_split`: heap de precios con split de capacidad, O(n log n).
- `greedy_time`: minimizar tiempo de entrega, desempate por precio, O(n log n).
- `knapsack_budget`: DP 0/1 en centavos O(n·W), fallback greedy si W > S/5000.
- `per_sku_order`: plan multi-SKU resolviendo cada SKU por separado — la
  practica "antes", cuya falla motiva el min-cost flow.

### 3. Min-cost flow (`core/optimization_flow.py`) — algoritmo investigado

Red FUENTE →(cantidad) SKU →(capacidad oferta, costo=precio) PROVEEDOR
→(capacidad global) SUMIDERO. Successive shortest paths con potenciales de
Johnson (Dijkstra sobre costos reducidos). Asigna el pedido completo
respetando todas las capacidades a la vez, al minimo costo global.

## Ejecucion

```powershell
py TF-Final\etapa4_optimizacion_compras.py                      # caso demo vinculante
py TF-Final\etapa4_optimizacion_compras.py --item 5615=2000 --item 5070=1500
```

Outputs: `outputs/stage4_optimizacion/` (`optimization_comparison.json`,
`supply_options.csv`).

## Resultado clave

Con el pedido demo, el baseline por-SKU reporta S/3,179.98 "sin deficit" pero
asigna 6,500 unidades a un proveedor con capacidad inferida de 2,050: **plan
infactible**. El flujo entrega el optimo factible y reporta el deficit real.
Ver `docs/ALGORITMOS_EVOLUCION.md`, seccion 3.
