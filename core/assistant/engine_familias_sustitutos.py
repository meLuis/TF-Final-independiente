"""Seccion 8 - Familias, sustitutos y productos parecidos.

Baseline (curso): componentes conexos de la proyeccion producto-producto.
Investigado: comunidades Leiden (familias con sentido comercial) + Personalized
PageRank para sustitutos cercanos.
"""

from __future__ import annotations

import pandas as pd

from core.assistant_contract import AlgoVariant, AssistantResponse

from .aggregations import resolve_product
from .loaders import load_communities, load_pagerank, load_products, tx_ready

INTENT = "familias_sustitutos"


def engine_familias_sustitutos(product_text: str | None = None, k: int = 10) -> AssistantResponse:
    communities = load_communities()
    membership: pd.DataFrame = communities.get("membership", pd.DataFrame())
    descriptions: pd.DataFrame = communities.get("descriptions", pd.DataFrame())
    metrics: dict = communities.get("metrics", {})

    baseline_variant = AlgoVariant(
        name="Componentes conexos",
        role="baseline",
        metrics={
            "componentes": metrics.get("baseline_connected_components"),
            "mayor_componente": metrics.get("largest_connected_component"),
        },
        summary="Vision binaria y gruesa: el componente mayor agrupa cientos de productos sin familias.",
    )
    investigated_variant = AlgoVariant(
        name="Leiden (modularidad)",
        role="investigado",
        table=descriptions if not descriptions.empty else None,
        metrics={
            "comunidades": metrics.get("leiden_communities"),
            "modularidad": metrics.get("leiden_modularity"),
        },
        summary="Familias bien conectadas con sentido comercial.",
    )

    entities: dict = {}
    main_table = descriptions if not descriptions.empty else None
    extra: dict[str, pd.DataFrame] = {}
    answer = (
        f"El catalogo se agrupa en **{metrics.get('leiden_communities', '?')} familias** (Leiden) "
        f"frente a {metrics.get('baseline_connected_components', '?')} componentes conexos del baseline."
    )

    product_text = (product_text or "").strip()
    if product_text:
        resolved = resolve_product(load_products(), product_text)
        if resolved is None:
            return AssistantResponse.fail(INTENT, f"No encontre el producto '{product_text}'.")
        product_id, product_name = resolved
        node = f"PRODUCT:{product_id}"
        entities = {"product_id": product_id, "producto": product_name}

        if not membership.empty and node in set(membership["product"]):
            community = membership.loc[membership["product"] == node, "leiden_community"].iloc[0]
            family = membership.loc[
                membership["leiden_community"] == community, ["product", "product_label"]
            ]
            main_table = family.reset_index(drop=True)
            answer = f"**{product_name}** pertenece a la familia Leiden #{community} ({len(family)} productos)."
        else:
            answer = f"**{product_name}** no aparece en la proyeccion (sin atributos suficientes para agrupar)."

        # Sustitutos cercanos via Personalized PageRank.
        if tx_ready():
            try:
                related = load_pagerank("business").related_products(node, k=k)
                if not related.empty:
                    extra["Sustitutos cercanos (Personalized PageRank)"] = related
            except Exception:
                pass

    return AssistantResponse(
        intent=INTENT,
        answer=answer,
        entities=entities,
        table=main_table,
        algorithm="Leiden (Traag et al. 2019) + Personalized PageRank",
        baseline=baseline_variant,
        investigated=investigated_variant,
        evidence=[f"Proyeccion producto-producto ({communities.get('source', '')})"],
        technical=metrics,
        extra_tables=extra,
    )
