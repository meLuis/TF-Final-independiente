# Etapa 1 - Ingesta y Normalizacion de Raw Data

## Objetivo

Transformar tres archivos tabulares arbitrarios de una empresa en datasets limpios, consistentes y vinculados entre si:

- catalogo de productos,
- historial de compras,
- historial de ventas.

Esta etapa debe funcionar aunque cada empresa use nombres de columnas, formatos de fecha, separadores decimales, monedas, hojas Excel simples y descripciones de productos diferentes.

El resultado no debe depender exclusivamente de un LLM. El pipeline debe ser auditable: cada decision importante debe tener una regla, una validacion o un score de confianza.

## Alcance de la etapa

Entrada:

- `productos.csv`, `productos.xlsx` o `productos.xls`
- `compras.csv`, `compras.xlsx` o `compras.xls`
- `ventas.csv`, `ventas.xlsx` o `ventas.xls`

Salida:

- `products_clean.csv`
- `sales_clean.csv`
- `purchases_clean.csv`
- `product_matches.csv`
- `quality_summary.csv`
- `transaction_flags_summary.csv`
- `product_activity_summary.csv`
- `code_pattern_summary.csv`
- `schema_mapping.json`
- `company_rules.json`
- `normalization_report.json`

Esta etapa termina cuando los datos estan listos para construir grafos y ejecutar algoritmos. No incluye todavia optimizacion de compras, prediccion de demanda ni dashboards avanzados.

## Problema central

Cada empresa puede representar los mismos conceptos con nombres distintos:

| Concepto | Ejemplo 1 | Ejemplo 2 | Ejemplo 3 |
|---|---|---|---|
| Fecha | `fecha` | `FecDoc` | `fecha_emision` |
| Producto | `sku` | `CodItem` | `codigo_producto` |
| Descripcion | `producto` | `descripcion` | `NomItem` |
| Cantidad | `cantidad` | `Cant` | `qty` |
| Precio unitario | `precio` | `PUnit` | `valor_unitario` |
| Total | `importe` | `total` | `monto_total` |
| Proveedor | `proveedor` | `RazSoc` | `ruc_proveedor` |
| Cliente | `cliente` | `RazSoc` | `customer_name` |

Por eso el sistema no debe asumir nombres fijos. Debe inferir un esquema canonico y pedir confirmacion cuando exista ambiguedad.

## Esquema canonico minimo

### Productos

Campos recomendados:

- `product_id`
- `product_name`
- `category`
- `brand`
- `unit`
- `description`
- `current_price`
- `stock_available`

Campos minimos:

- `product_id` o `product_name`

### Ventas

Campos recomendados:

- `sale_id`
- `date`
- `product_id`
- `product_name`
- `customer`
- `quantity`
- `unit_price_net`
- `unit_price_gross`
- `subtotal_net`
- `tax_amount`
- `total_gross`
- `is_cancelled`

Campos minimos:

- `date`
- `product_id` o `product_name`
- `quantity`
- `unit_price_gross` o `total_gross`

### Compras

Campos recomendados:

- `purchase_id`
- `date`
- `product_id`
- `product_name`
- `supplier`
- `quantity`
- `unit_cost_net`
- `unit_cost_gross`
- `subtotal_net`
- `tax_amount`
- `total_gross`

Campos minimos:

- `date`
- `product_id` o `product_name`
- `supplier`
- `quantity`
- `unit_cost_gross` o `total_gross`

## Pipeline propuesto

```text
1. Cargar los 3 archivos tabulares
2. Perfilar columnas y valores con pandas
3. Proponer mapeo de columnas con reglas + fuzzy matching
4. Usar LLM opcional solo si hay ambiguedad
5. Validar relaciones matematicas y rangos
6. Mostrar UI de confirmacion/correccion del mapeo
7. Normalizar fechas, numeros, moneda, texto y duplicados
8. Vincular productos entre catalogo, compras y ventas
9. Asignar scores de confianza
10. Generar reporte de calidad
11. Guardar reglas persistentes por empresa
```

## 1. Perfilado automatico

El perfilado debe ejecutarse sin LLM usando `pandas`.

Por cada archivo y columna se debe calcular:

- nombre original de columna,
- tipo inferido,
- porcentaje de nulos,
- cantidad de valores unicos,
- ejemplos de valores,
- si parece fecha,
- si parece numero,
- si parece monto monetario,
- si parece identificador,
- si parece texto descriptivo,
- rango minimo y maximo cuando aplique.

Ejemplo de salida interna:

```json
{
  "column": "FecDoc",
  "inferred_type": "date",
  "null_rate": 0.0,
  "parseable_as_date": 0.98,
  "sample_values": ["10/01/2024", "11/01/2024", "12/01/2024"]
}
```

## 2. Deteccion de columnas

La deteccion debe usar una cascada, de menor costo a mayor costo:

```text
alias exacto
-> similitud del nombre de columna
-> inferencia por tipo de datos
-> validacion cruzada entre columnas
-> LLM opcional si sigue ambiguo
-> confirmacion manual
```

### Senales recomendadas

Para detectar `date`:

- nombre parecido a fecha, date, fec, emision,
- valores parseables como fecha,
- rango temporal razonable,
- cardinalidad compatible con un historial.

Para detectar `quantity`:

- valores numericos,
- muchos enteros positivos,
- nombre parecido a cantidad, cant, qty, unidades.

Para detectar `unit_price`, `unit_cost`, `total_amount` o `total_cost`:

- valores numericos decimales,
- nombre parecido a precio, costo, importe, total,
- validacion con cantidad.

Para detectar `product_id`:

- valores repetidos entre archivos,
- codigos alfanumericos o enteros,
- nombre parecido a sku, codigo, item, codprod.

Para detectar `product_name`:

- texto descriptivo,
- alta cardinalidad,
- palabras de producto,
- coincidencia parcial con el catalogo.

## 3. Validacion cruzada

La validacion cruzada corrige ambiguedades sin usar LLM.

Ejemplo:

```text
quantity * unit_price_net ~= subtotal_net
quantity * unit_cost_net ~= subtotal_net
subtotal_net + tax_amount ~= total_gross
```

Si la relacion se cumple en una proporcion alta de filas, se aumenta la confianza del mapeo.

Reglas sugeridas:

- tolerancia relativa: 1% a 3%,
- aceptar si la identidad se cumple en al menos 85% o 90% de filas validas,
- excluir filas con nulos, descuentos extremos o totales cero.

Tambien se validan:

- fechas dentro de un rango razonable,
- cantidades positivas,
- precios no negativos,
- totales coherentes,
- productos presentes en catalogo o vinculables por nombre.

## 4. Uso del LLM

El LLM no debe procesar todos los datos. Solo debe recibir:

- nombres de columnas,
- perfil estadistico,
- 5 a 20 filas de muestra,
- candidatos ya detectados por reglas,
- dudas concretas.

Uso recomendado:

- desempatar columnas ambiguas,
- sugerir mapeo inicial cuando los nombres son muy raros,
- explicar por que una columna podria representar un rol,
- clasificar errores de datos dificiles.

No recomendado:

- limpiar fila por fila,
- decidir sin validacion,
- recibir el archivo completo,
- reemplazar reglas deterministicas.

Proveedores posibles:

- `none`: sin IA, solo reglas y confirmacion manual.
- `ollama`: modelo local gratuito.
- `openai`: modelo de pago opcional.

## 5. Normalizacion

Despues de confirmar el mapeo, se normalizan los datos.

### Fechas

- convertir a formato ISO `YYYY-MM-DD`,
- detectar formato dominante,
- marcar fechas invalidas.

### Numeros y moneda

- soportar coma o punto decimal,
- eliminar simbolos monetarios,
- convertir cantidades, precios y totales a `float` o `int`,
- registrar moneda si se detecta,
- conservar montos netos y brutos cuando existan,
- usar los montos brutos como columnas de trabajo (`analysis_total`) para flujos operativos.

### Stock

- conservar el stock original como `stock_available_raw`,
- generar un stock natural como `stock_available`, truncado a minimo 0,
- marcar `stock_status` como `positive`, `zero` o `negative_raw_clipped`.

### Anulados y ajustes

- detectar anulados por columna explicita cuando exista,
- detectar anulados o ajustes por palabras clave en codigo o descripcion,
- conservar las filas, pero marcarlas con `is_cancelled`, `is_adjustment` e `is_active`.

### Texto

- quitar espacios duplicados,
- normalizar mayusculas/minusculas,
- quitar tildes para matching,
- conservar texto original en columna auxiliar cuando sea util,
- eliminar sufijos frecuentes en empresas si aplica: `S.A.C.`, `E.I.R.L.`, `S.R.L.`.

### Duplicados

- detectar productos duplicados,
- detectar transacciones repetidas,
- no eliminar automaticamente sin dejar registro.

## 6. Matching de productos

El matching conecta ventas y compras con el catalogo de productos.

Cascada recomendada:

```text
1. Match exacto por product_id
2. Match exacto por nombre normalizado
3. Match fuzzy con rapidfuzz
4. LLM opcional para desempatar ambiguos
5. Revision manual
```

### Scores sugeridos

- match exacto por ID: `1.00`
- match exacto por nombre normalizado: `0.95`
- fuzzy alto y sin competidor cercano: `0.85` a `0.95`
- fuzzy con candidatos cercanos: ambiguo
- sin match suficiente: rechazado o pendiente
- match confirmado por humano: `1.00`

Un caso debe marcarse como ambiguo si:

- el mejor candidato tiene score menor al umbral,
- la diferencia entre primer y segundo candidato es pequena,
- el precio o categoria no parece coherente,
- el producto parece ser servicio, descuento, flete u otro no-producto.

## 7. Metricas de calidad

Esta etapa no se evalua principalmente con train/test, porque no se esta entrenando un modelo predictivo. Se evalua como calidad de datos y record linkage.

Metricas recomendadas:

| Componente | Metrica |
|---|---|
| Mapeo de columnas | columnas confirmadas / columnas requeridas |
| Filas validas | filas limpias / filas totales |
| Matching de ventas | ventas vinculadas a producto / ventas totales |
| Matching de compras | compras vinculadas a producto / compras totales |
| Alta confianza | matches con score >= 0.90 / matches totales |
| Ambiguos | matches que requieren revision humana |
| Rechazados | filas o productos sin match confiable |
| Consistencia matematica | filas donde cantidad * precio ~= total |

## Golden set

Para validar objetivamente el sistema se usaran dos mecanismos:

1. Datasets de demo controlados, con respuesta correcta conocida.
2. Muestra manual opcional por empresa real.

Para la sustentacion, conviene crear al menos dos datasets de prueba:

- ferreteria,
- material medico.

Cada dataset debe incluir columnas con nombres distintos pero roles equivalentes. Asi se puede demostrar que el sistema generaliza.

Si se trabaja con datos reales de una empresa, el usuario puede validar una muestra pequena:

- 30 a 50 filas de ventas,
- 30 a 50 filas de compras,
- mapeo final de columnas.

Esa muestra se guarda como `golden_set.json` y permite calcular:

- accuracy,
- precision,
- recall,
- F1,
- tasa de ambiguedad.

## Archivos de salida

### `schema_mapping.json`

Guarda el mapeo confirmado entre columnas originales y esquema canonico.

```json
{
  "company_id": "ferreteria_demo",
  "version": "2026-06-11",
  "products": {
    "product_id": "cod_art",
    "product_name": "desc_articulo",
    "category": "categoria"
  },
  "sales": {
    "date": "FecDoc",
    "product_id": "CodItem",
    "quantity": "Cant",
    "unit_price": "Precio",
    "total_amount": "Importe",
    "customer": "Cliente"
  },
  "purchases": {
    "date": "FechaCompra",
    "product_id": "CodItem",
    "quantity": "Cantidad",
    "unit_cost": "CostoUnit",
    "total_cost": "Total",
    "supplier": "Proveedor"
  }
}
```

### `company_rules.json`

Guarda reglas aprendidas para reutilizarlas en futuras cargas.

```json
{
  "normalization_rules": {
    "date_format": "DD/MM/YYYY",
    "decimal_separator": ",",
    "currency": "PEN",
    "remove_patterns": ["S.A.C.", "E.I.R.L.", "UND", "UNID"]
  },
  "product_match_rules": {
    "confirmed_matches": {
      "TALADRO BOSCH 500 WATTS": "SKU-0012"
    },
    "rejected_strings": ["FLETE", "DESCUENTO", "SERVICIO"]
  }
}
```

### `normalization_report.json`

Resume la calidad del procesamiento.

```json
{
  "processed_at": "2026-06-11T14:30:00",
  "column_mapping_confidence": 0.93,
  "sales_clean_rows": 1785,
  "sales_total_rows": 1800,
  "purchases_clean_rows": 1965,
  "purchases_total_rows": 2000,
  "sales_product_match_coverage": 0.955,
  "purchases_product_match_coverage": 0.91,
  "high_confidence_matches": 1600,
  "ambiguous_matches": 80,
  "rejected_matches": 120,
  "requires_human_review": true
}
```

## Stack inicial recomendado

| Componente | Herramienta |
|---|---|
| UI | Streamlit |
| Perfilado y limpieza | pandas |
| Validacion | pandas + reglas propias |
| Matching difuso | rapidfuzz |
| Modelo local opcional | Ollama |
| Modelo pago opcional | OpenAI |
| Persistencia | JSON + CSV |

No se recomienda usar embeddings en la primera version. Pueden agregarse despues si `rapidfuzz` y el desempate con LLM no son suficientes.

## Criterios de exito de la etapa

La etapa se considera exitosa si:

- los 3 archivos se cargan sin asumir nombres fijos,
- el sistema propone un mapeo razonable,
- el usuario puede corregir el mapeo,
- las columnas numericas y de fecha quedan normalizadas,
- ventas y compras quedan vinculadas al catalogo con score de confianza,
- los casos dudosos se separan en vez de aceptarse silenciosamente,
- se genera un reporte de calidad,
- se guardan reglas reutilizables por empresa.

## Decision de diseno

El enfoque final para esta etapa es:

```text
pandas + reglas + rapidfuzz como base
LLM local o de pago solo para ambiguedades
revision humana para decisiones dudosas
metricas de confianza para demostrar calidad
```

Esta decision reduce costos, evita depender de tokens, mejora la trazabilidad y mantiene la IA como una ventaja sin convertirla en un punto unico de falla.
