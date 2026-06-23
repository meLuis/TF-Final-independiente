"""Reglas de asociacion (Apriori / lift) para venta cruzada.

Baseline (curso): co-ocurrencia directa (conteo bruto de pares co-vendidos).
Investigado: reglas de asociacion con soporte / confianza / lift (Agrawal &
Srikant, 1994, "Fast Algorithms for Mining Association Rules"). El lift prioriza
"si compra A -> ofrece B" por sorpresa estadistica, no por conteo bruto: un par
muy frecuente pero trivial (ambos best-sellers) tiene lift ~1 y se descarta.

Transaccion = pseudo-documento de venta (cliente + fecha), mismo agrupamiento que
core/sales_reports.co_sales y core/transaction_graphs.
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations

import pandas as pd


def build_transactions(sales: pd.DataFrame) -> list[set[str]]:
    """Lista de canastas: productos vendidos al mismo cliente el mismo dia."""
    data = sales
    if "is_active" in data.columns:
        data = data.loc[data["is_active"].astype(str).str.lower().isin({"true", "1"})]
    transactions: list[set[str]] = []
    for _, group in data.groupby(["customer_norm", "date"]):
        basket = set(group["product_id"].astype(str))
        if len(basket) >= 2:
            transactions.append(basket)
    return transactions


def association_rules(
    transactions: list[set[str]],
    min_support: float = 0.005,
    min_confidence: float = 0.25,
) -> pd.DataFrame:
    """Reglas de a un item (A -> B) con soporte, confianza y lift (Apriori)."""
    n = len(transactions)
    columns = ["antecedent", "consequent", "support", "confidence", "lift", "co_count"]
    if n == 0:
        return pd.DataFrame(columns=columns)

    item_counts: Counter[str] = Counter()
    for basket in transactions:
        item_counts.update(basket)

    min_count = min_support * n
    frequent = {item for item, count in item_counts.items() if count >= min_count}

    pair_counts: Counter[tuple[str, str]] = Counter()
    for basket in transactions:
        items = sorted(item for item in basket if item in frequent)
        for pair in combinations(items, 2):
            pair_counts[pair] += 1

    rows = []
    for (a, b), count in pair_counts.items():
        if count < min_count:
            continue
        for antecedent, consequent in ((a, b), (b, a)):
            confidence = count / item_counts[antecedent]
            if confidence < min_confidence:
                continue
            lift = confidence / (item_counts[consequent] / n)
            rows.append(
                {
                    "antecedent": antecedent,
                    "consequent": consequent,
                    "support": round(count / n, 6),
                    "confidence": round(confidence, 4),
                    "lift": round(lift, 4),
                    "co_count": count,
                }
            )
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows).sort_values("lift", ascending=False).reset_index(drop=True)


def rules_for_product(
    product_id: str, rules: pd.DataFrame, labels: dict[str, str], k: int = 10
) -> pd.DataFrame:
    """Recomendaciones 'si vende este, ofrece...' ordenadas por lift."""
    if rules.empty:
        return pd.DataFrame()
    subset = rules.loc[rules["antecedent"].astype(str) == str(product_id)].head(k).copy()
    if subset.empty:
        return pd.DataFrame()
    subset["recomendado"] = subset["consequent"].map(lambda pid: labels.get(str(pid), str(pid)))
    return subset[["recomendado", "lift", "confidence", "support", "co_count"]].reset_index(drop=True)


def cooccurrence_for_product(product_id: str, sales: pd.DataFrame, k: int = 10) -> pd.DataFrame:
    """Baseline: co-ocurrencia directa filtrada para un producto (reusa co_sales)."""
    from .sales_reports import co_sales

    pairs = co_sales(sales, top_k=500)
    if pairs.empty:
        return pd.DataFrame()
    pid = str(product_id)
    rows = []
    for row in pairs.itertuples(index=False):
        if str(row.product_a) == pid:
            rows.append({"recomendado": row.product_b_name, "co_sale_docs": row.co_sale_docs})
        elif str(row.product_b) == pid:
            rows.append({"recomendado": row.product_a_name, "co_sale_docs": row.co_sale_docs})
    return pd.DataFrame(rows).head(k).reset_index(drop=True) if rows else pd.DataFrame()
