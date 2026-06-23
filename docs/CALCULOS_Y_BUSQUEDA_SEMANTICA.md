# Cálculos, indicadores (%) y búsqueda semántica

Documento dedicado a los **algoritmos de cálculo** del proyecto: el scoring de la
búsqueda semántica, el score de recuperabilidad, la similitud Jaccard ponderada y
todos los indicadores porcentuales. Es el complemento de
[ALGORITMOS_EVOLUCION.md](ALGORITMOS_EVOLUCION.md) (que cubre los algoritmos de
grafos: BFS bidireccional, A\*, min-cost flow, Leiden, PageRank).

Cada sección trae: **fórmula exacta** (tal como está en el código, con sus
constantes), **justificación término por término**, **complejidad O(·)** y, al
final, **qué leer/citar** para respaldar la heurística con literatura.

> Convención: un *token* es una palabra normalizada (sin tildes, mayúsculas, solo
> `[A-Z0-9]`), ver `core/text_utils.py::normalize_text`.

---

## 1. Búsqueda semántica sobre G_attr (`core/semantic_search.py`)

Es la pieza que más se subestima: **no es un BFS plano**, es una función de
*spreading activation* (activación por propagación) con tres factores diseñados.
Responde "¿qué productos busca el usuario?" recorriendo el grafo bipartito
G_attr (PRODUCT ↔ ATRIBUTO) desde las semillas del query.

### 1.1 Flujo

```
query → tokens → semillas (nodos atributo del grafo)
      → BFS multi-semilla con decaimiento por distancia
      → multiplicador por cobertura de semillas
      → filtro EXACTO para atributos numéricos
      → top-k
```

El vocabulario **se aprende del grafo**: cada nodo atributo es un término
reconocible, así que no hay regex de dominio. Por eso el mismo buscador sirve para
plásticos o ferretería.

### 1.2 Extracción de semillas

- **Atributos textuales:** cada token del query se busca (exacto o singularizado)
  contra las etiquetas de los nodos del grafo; los que existen son semillas.
- **Atributos numéricos (capacidad, boca):** se extrae el valor con el *mismo*
  extractor y constructor de id de nodo de la Etapa 2, para que la semilla coincida
  exactamente. **Se registra el filtro aunque el nodo no exista** en el grafo (clave
  para el filtro exacto, §1.5).

### 1.3 Score base: BFS con decaimiento por distancia

Constante (heredada del proyecto base):

```
DISTANCE_DECAY = (5, 4, 3, 2, 1)        # índice = distancia BFS, saturada en 4
decay(d) = DISTANCE_DECAY[min(d, 4)]     # d=0→5, 1→4, 2→3, 3→2, d≥4→1
```

BFS multi-semilla: todas las semillas entran a distancia 0. Al **extraer** un nodo
a distancia `d`, por cada vecino que sea un PRODUCT se acumula:

$$\text{score}_{\text{base}}(p) \mathrel{+}= \text{decay}(d)\cdot w(e)$$

donde `w(e)` es el **peso de la arista** = la **confianza del atributo** extraído
(Etapa 2; ver §3.3). Es decir, un producto:

- conectado **directo** a una semilla suma `5 · w` (la semilla está a `d=0`);
- alcanzado a través de un nodo a `d=1` suma `4 · w`; y así decreciendo.

**Interpretación:** la "energía" parte de las semillas y se propaga por el grafo
perdiendo fuerza con la distancia; los productos que más energía acumulan (más
atributos relevantes, más confiables, más cercanos) puntúan más alto. Esto es
*spreading activation* clásico de redes semánticas, no un BFS de alcanzabilidad.

### 1.4 Multiplicador por cobertura de semillas

`cov(p)` = número de semillas **distintas** conectadas directamente a `p`;
`S` = total de semillas. El score base se multiplica por:

$$\text{score}(p) = \text{score}_{\text{base}}(p)\cdot\left[\left(\frac{\text{cov}(p)}{S}\right)^{2}\cdot 20 + 1\right]$$

Término por término:

- `cov(p)/S` ∈ [0,1]: fracción de las intenciones del usuario que el producto
  satisface. Si el usuario pidió "frasco vidrio ámbar 5ml" (4 semillas) y el
  producto tiene las 4, la fracción es 1.
- **Cuadrado:** premia desproporcionadamente la cobertura **alta**. Un producto que
  cubre el 100% se separa fuerte de uno que cubre el 50% (1.0 vs 0.25 antes de
  escalar), evitando que muchos atributos parciales empaten a uno completo.
- `· 20 + 1`: el `+1` hace que cobertura 0 deje el score base intacto (multiplicador
  neutro = 1); el `· 20` da al producto de cobertura total un multiplicador de
  **21×**. La cobertura es el factor dominante del ranking.

### 1.5 Filtro exacto numérico (regla dura del proyecto)

Para cada filtro numérico pedido se calcula el conjunto de productos adyacentes a
ese nodo y se **intersectan**:

$$\text{allowed} = \bigcap_{f\in\text{filtros}} N_{\text{PRODUCT}}(f)$$

Un producto solo pasa si está en `allowed`. **Si el nodo numérico no existe en el
grafo** (p. ej. piden 123ML y nadie tiene 123ML), su `N(f)=∅`, la intersección es
vacía y el resultado es **cero a propósito**: 100ML es exactamente 100ML, nunca se
aproxima. Esta es una decisión de diseño explícita, no una limitación.

### 1.6 Complejidad

| Operación | Costo |
|-----------|-------|
| Construir el índice | O(V + E) |
| Extraer semillas | O(\|query\| · t), t = tamaño del vocabulario tocado |
| BFS + scoring | O(V + E) peor caso |
| Multiplicador cobertura | O(p) sobre p productos puntuados |
| Ordenar top-k | O(p log p) |

**Total por consulta:** O(V + E + p log p).

### 1.7 Qué leer / citar

- **Spreading activation en recuperación de información** — Crestani, F. (1997),
  *"Application of Spreading Activation Techniques in Information Retrieval"*,
  Artificial Intelligence Review. Es el marco teórico exacto del §1.3: propagación
  con decaimiento sobre una red semántica. **Cita principal recomendada.**
- Collins, A. & Loftus, E. (1975), *"A spreading-activation theory of semantic
  processing"* — origen psicológico del modelo.
- Como analogía de "función de scoring con normalización", la familia **TF-IDF /
  BM25** (ver §2.7): tu multiplicador de cobertura cumple el rol que en BM25
  cumplen la saturación de término y la normalización por cobertura del query.

---

## 2. Score de recuperabilidad (`core/semantic_retrievability.py`)

Mide **qué tan encontrable** es cada producto a partir de los atributos extraídos.
Es el indicador con el que se acepta o rechaza la capa LLM (§4): si enriquecer
atributos no mejora (o empeora) la recuperabilidad, no se acepta.

### 2.1 Recuperabilidad de un producto

Se usa el **propio nombre del producto como query** y se mide qué fracción de sus
tokens significativos está cubierta por sus atributos extraídos:

$$\text{retrievability}(p) = \frac{|\{\text{tokens del nombre}\}\cap\{\text{tokens de atributos}\}|}{|\{\text{tokens del nombre}\}|}$$

(Se descartan stopwords del dominio: `CON`, `DE`, `PARA`, `UND`, `PACK`, …, y
tokens de largo ≤ 1.) Un score de 1.0 significa que cada palabra del nombre quedó
representada como atributo estructurado; 0.5 significa que la mitad del nombre no
es recuperable por atributos.

**Promedio del catálogo** = `avg_retrievability_score`. Medición real:
0.5153 (solo reglas) → **0.5548 con LLM** (sin regresión).

### 2.2 Score interno de ranking (`search_score`)

Para evaluar el top-k, se rankean todos los productos contra el query con:

```
coverage   = (attr_hits · 1.1 + name_hits · 1.4) / max(|tokens|, 1)
score      = coverage + fuzzy · 0.35 + exact_name_boost + log1p(|attr_tokens|) · 0.01
```

- `attr_hits` / `name_hits`: tokens del query presentes en atributos / en el nombre.
- Pesos **1.4 (nombre) > 1.1 (atributos):** coincidir en el nombre es señal más
  fuerte que en un atributo derivado, pero ambos suman (recuperación por atributo
  es el valor agregado del sistema).
- `fuzzy · 0.35`: similitud difusa nombre-query (token_set_ratio, §5) como red de
  seguridad ante variaciones; peso bajo para no dominar a las coincidencias exactas.
- `exact_name_boost = 1` si el query normalizado == nombre normalizado: garantiza
  que un producto se recupere a sí mismo en el tope.
- `log1p(|attr_tokens|) · 0.01`: desempate mínimo que favorece documentos más
  ricos en atributos. Coeficiente diminuto: solo rompe empates.

### 2.3 Tasas top-k

`top1_found`, `top5_found`, `top10_found` por producto (¿se recupera a sí mismo en
las primeras 1/5/10 posiciones?). Promediadas dan `top1_rate`, `top5_rate`,
`top10_rate`. Medición: top5_rate = top10_rate = **1.0** (todo producto se
recupera dentro del top-5).

### 2.4 Qué leer / citar

- Manning, Raghavan & Schütze (2008), *Introduction to Information Retrieval*,
  caps. 8 (evaluación) y 11 — define **recall@k / precision@k**; tus tasas top-k son
  exactamente *self-retrieval recall@k*. **Lectura base recomendada.**
- El score §2.2 es una función de ranking *ad hoc*: enmárcala como variante
  simplificada de **TF-IDF/BM25** (§2.7) con realce por coincidencia exacta.

---

## 3. Similitud Jaccard ponderada (proyección producto-producto)

`core/product_projection.py`. Construye el grafo "¿qué productos se parecen?" a
partir de G_attr (bipartito). Es el cálculo más sólido del proyecto y el más
"matemático".

### 3.1 Definición

$$\text{sim}(p,q) = \frac{\sum_{a\in A(p)\cap A(q)} \min(w_{pa}, w_{qa})}{\sum_{a\in A(p)\cup A(q)} \max(w_{pa}, w_{qa})}$$

`w_pa` = confianza del atributo `a` en el producto `p`. Es el **Jaccard ponderado**
(generaliza el Jaccard binario: con todos los pesos = 1 se recupera
|A∩B| / |A∪B|).

### 3.2 Identidad que evita iterar la unión

Para atributos compartidos, `min(w_pa,w_qa) + max(w_pa,w_qa) = w_pa + w_qa`. Sea
`num` el numerador y `W(x) = Σ_a w_xa` la suma de pesos del producto. Entonces:

$$\text{denominador} = W(p) + W(q) - \text{num}$$

Así **solo se acumula el numerador por atributo** (recorriendo la lista de
adyacencia de cada atributo) y nunca se itera explícitamente la unión por cada par.

### 3.3 Atributos hub y costo

Un atributo conectado a más de `hub_fraction · n_productos` (default 0.35) productos
no discrimina similitud (p. ej. `ACCESSORY:TAPA`, grado 357 de 630) y **se excluye**.
Además acota el costo: generar pares es

$$O\!\left(\sum_{a\ \text{no-hub}} \deg(a)^2\right)$$

y excluir hubs elimina los términos cuadráticos dominantes. Filtros de calidad:
`min_shared_attributes` (≥ 2, evita pares unidos por una sola coincidencia débil) y
`min_similarity` (≥ 0.30).

### 3.4 Qué leer / citar

- Jaccard, P. (1901) — índice original.
- Para la versión ponderada y su escalamiento: Broder, A. (1997), *"On the
  resemblance and containment of documents"* (weighted Jaccard / MinHash).

---

## 4. Indicadores porcentuales (%) por etapa

Todos los % del proyecto, con su fórmula exacta.

### 4.1 Etapa 1 — Ingesta (`core/pipeline.py`, `core/product_matcher.py`)

| Indicador | Fórmula | Significado |
|-----------|---------|-------------|
| `column_mapping_confidence` | media de la confianza de los campos canónicos **mapeados** | qué tan seguro fue inferir el esquema |
| `all_field_confidence` | media sobre **todos** los campos canónicos | idem, incluyendo no mapeados |
| `product_match_coverage` | `accepted / total_matches` | % de transacciones ligadas a un producto del maestro |

**Matcher de productos** (umbrales): id exacto → confianza 1.0; id numérico
equivalente → 0.98; nombre exacto normalizado → 0.95; si no, **fuzzy**:

```
accepted   si  best ≥ 0.82  Y  (best − second) ≥ 0.05
ambiguous  si  best ≥ 0.65
rejected   en otro caso
```

El `ambiguity_gap` de 0.05 evita aceptar cuando dos candidatos están casi empatados
(decisión dudosa → revisión humana en vez de adivinar).

### 4.2 Etapa 1.5 — Atributos (`core/attribute_extractor.py`)

- **Confianza por atributo:** cada regla declara su confianza (p. ej. material 0.94,
  tipos de producto 0.84–0.95, default 0.85), acotada a [0,1]. En atributos multivalor se toma el
  `max` de las reglas que dispararon.
- **Confianza del producto** = media de las confianzas de los atributos presentes
  (los de valor 0 no cuentan):

$$\text{conf}(p) = \frac{1}{|C|}\sum_{c\in C} \text{conf}_c,\quad C=\{\text{atributos con confianza}>0\}$$

- **Cobertura por atributo** = `filled / total` (fracción de productos con ese
  atributo no vacío). Es el % que reporta `attribute_coverage_report.csv`.

### 4.3 Etapa 2 — Grafo (`core/semantic_graph.py`)

- **Peso de cada arista PRODUCT↔ATRIBUTO = la confianza de *ese* atributo** (no la
  confianza global del producto). Este es el peso `w(e)` que alimenta el scoring
  (§1.3) y el Jaccard (§3).
- **Gating `min_confidence` (default 0.75):** una arista se descarta si la confianza
  del atributo es menor al umbral. El umbral **no es arbitrario**: lo justifica el
  barrido de `etapa2_sensibilidad_umbral.py`, que muestra una **meseta estable en
  [0.60, 0.80]** (cobertura y fragmentación casi constantes) y degradación recién
  desde 0.85 → 0.75 vive dentro de la meseta.

### 4.4 Aceptación conservadora del LLM (`etapa1_5_atributos_llm_finalize.py`)

La capa Gemini se acepta solo si **ningún** check regresiona:

- `*_accuracy_no_regression` por atributo crítico (tipo, material, color, capacidad,
  boca): `accuracy_on_both_filled` candidato ≥ baseline.
- `avg_confidence_no_regression`, coberturas semánticas (subtype/accessory/shape/
  feature) y `retrievability_score_no_regression` (§2).
- `accepted = AND` de todos los checks. La evidencia queda en
  `outputs/stage15_final/llm_acceptance_summary.json`.

`accuracy_on_both_filled` = aciertos / casos donde **ambos** (extracción y golden
set `catalogo.csv`) tienen valor → mide exactitud sin penalizar cobertura faltante.

---

## 5. Similitud difusa de texto (`core/text_utils.py::similarity`)

```
similarity(a,b) = token_set_ratio(norm(a), norm(b)) / 100      # rapidfuzz, ∈ [0,1]
                  (fallback: SequenceMatcher.ratio si no hay rapidfuzz)
```

`token_set_ratio` compara conjuntos de tokens (ignora orden y duplicados), robusto a
nombres reordenados ("FRASCO AMBAR 50ML" ≈ "AMBAR FRASCO 50 ML"). Sustenta el
matcher (§4.1) y el `fuzzy` del score de recuperabilidad (§2.2).

**Qué leer:** distancia de Levenshtein (edición) como base; `token_set_ratio` es de
la familia FuzzyWuzzy/RapidFuzz construida sobre ratio de Levenshtein.

---

## 6. Tabla maestra de cálculos

| Cálculo | Dónde | Fórmula núcleo | Complejidad |
|---------|-------|----------------|-------------|
| Score búsqueda semántica | `semantic_search.py` | `Σ decay(d)·w` × `[(cov/S)²·20+1]` | O(V+E+p log p) |
| Recuperabilidad | `semantic_retrievability.py` | `|nombre∩atributos| / |nombre|` | O(N·M) por reporte |
| Score de ranking interno | `semantic_retrievability.py` | `cov + fuzzy·0.35 + exact + log1p·0.01` | O(N) por query |
| Jaccard ponderado | `product_projection.py` | `num / (W(p)+W(q)−num)` | O(Σ deg(a)² no-hub) |
| Confianza producto | `attribute_extractor.py` | media de confianzas de atributos | O(atributos) |
| Cobertura atributo | `attribute_extractor.py` | `filled / total` | O(N) |
| Match coverage | `pipeline.py` | `accepted / total` | — |
| Similitud difusa | `text_utils.py` | `token_set_ratio / 100` | O(\|a\|+\|b\|) |

---

## 7. Resumen de fuentes recomendadas

| Tema | Fuente principal para citar |
|------|------------------------------|
| Scoring por propagación (búsqueda semántica) | Crestani 1997, *Spreading Activation Techniques in IR* |
| Evaluación recall@k / top-k | Manning, Raghavan & Schütze 2008, *Introduction to IR* (caps. 8, 11) |
| Funciones de ranking (analogía) | TF-IDF (Salton & McGill 1983); BM25 (Robertson & Zaragoza 2009) |
| Similitud de conjuntos | Jaccard 1901; weighted Jaccard / MinHash (Broder 1997) |
| Similitud difusa de cadenas | Levenshtein 1966; token_set_ratio (RapidFuzz) |

> Para los algoritmos de **grafos** (no de cálculo) ver
> [ALGORITMOS_EVOLUCION.md](ALGORITMOS_EVOLUCION.md): BFS bidireccional (Pohl 1971),
> A\* (Hart, Nilsson & Raphael 1968), min-cost flow (Edmonds & Karp 1972),
> Leiden (Traag et al. 2019), Personalized PageRank (Page et al. 1999; Jeh & Widom 2003).
```
