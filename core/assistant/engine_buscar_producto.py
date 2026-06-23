"""Seccion 1 - Buscador de producto.

Baseline (curso): fuzzy / substring sobre los nombres del catalogo.
Investigado: BFS semantico sobre G_attr + filtro numerico exacto + Personalized
PageRank para alternativas cercanas.
"""

from __future__ import annotations

import pandas as pd

from core.assistant_contract import AlgoVariant, AssistantResponse
from core.text_utils import normalize_text

from .loaders import load_pagerank, load_semantic_index, tx_ready

INTENT = "buscar_producto"


def _fuzzy_baseline(index, query: str, k: int) -> pd.DataFrame:
    """Baseline 'antes': coincidencia por substring / solapamiento de tokens."""
    q = normalize_text(query)
    q_tokens = set(q.split())
    rows = []
    for node, label in index.product_labels.items():
        norm = normalize_text(label)
        if not norm:
            continue
        overlap = len(q_tokens & set(norm.split()))
        is_substring = bool(q) and q in norm
        if overlap or is_substring:
            rows.append(
                {
                    "product": node,
                    "label": label,
                    "tokens_en_comun": overlap,
                    "substring": is_substring,
                }
            )
    if not rows:
        return pd.DataFrame()
    return (
        pd.DataFrame(rows)
        .sort_values(["substring", "tokens_en_comun"], ascending=[False, False])
        .head(k)
        .reset_index(drop=True)
    )


def engine_buscar_producto(query: str, k: int = 10) -> AssistantResponse:
    query = (query or "").strip()
    if not query:
        return AssistantResponse.fail(INTENT, "Escribe que producto buscas.")

    index = load_semantic_index()
    results = index.search(query, k=k)
    stats = dict(index.last_stats)
    invest_table = pd.DataFrame(results)
    baseline_table = _fuzzy_baseline(index, query, k)

    if results:
        best = results[0]
        answer = (
            f"**Producto mas probable:** {best['label']}  \n"
            f"Relevancia: {best['relevance']} | cobertura de semillas: "
            f"{best['seed_coverage']}/{best['total_seeds']} | {len(results)} resultados."
        )
    else:
        answer = (
            "Sin resultados. Si pediste una capacidad o boca que no existe en el catalogo, "
            "el filtro exacto devuelve vacio a proposito (nunca aproxima)."
        )

    # Alternativas via Personalized PageRank sobre G_business (multi-salto real).
    extra: dict[str, pd.DataFrame] = {}
    if results and tx_ready():
        try:
            related = load_pagerank("business").related_products(results[0]["product"], k=k)
            if not related.empty:
                extra["Alternativas cercanas (Personalized PageRank)"] = related
        except Exception:
            pass

    return AssistantResponse(
        intent=INTENT,
        answer=answer,
        entities={
            "query": query,
            "semillas": stats.get("seeds", []),
            "filtros_exactos": stats.get("numeric_filters", []),
        },
        table=invest_table if not invest_table.empty else None,
        algorithm="BFS semantico sobre G_attr + filtro exacto + Personalized PageRank",
        baseline=AlgoVariant(
            name="Fuzzy / substring",
            role="baseline",
            table=baseline_table if not baseline_table.empty else None,
            metrics={"candidatos": int(len(baseline_table))},
            summary="Coincidencia textual directa contra los nombres del catalogo.",
        ),
        investigated=AlgoVariant(
            name="BFS semantico + filtro exacto",
            role="investigado",
            table=invest_table if not invest_table.empty else None,
            metrics={
                "nodos_expandidos": int(stats.get("expanded_nodes", 0)),
                "productos_puntuados": int(stats.get("scored_products", 0)),
                "semillas": int(len(stats.get("seeds", []))),
            },
            summary="Vocabulario aprendido del grafo; numericos exactos (100ML es 100ML).",
        ),
        evidence=["G_attr (stage2_graph_datos)", "G_business (stage2_transaction_graphs)"],
        technical=stats,
        extra_tables=extra,
    )
