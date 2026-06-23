"""Dispatcher del asistente de caja de texto.

Recibe texto libre o una aclaracion pendiente, valida slots contra los datos
locales y llama al engine_* correspondiente. La interfaz Streamlit solo necesita
guardar el pending que retorna esta capa.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from core.assistant_contract import AssistantResponse
from core.text_utils import similarity

from .aggregations import resolve_customer, resolve_product, resolve_supplier
from .engine_buscar_producto import engine_buscar_producto
from .engine_cliente_abastecimiento import engine_cliente_abastecimiento
from .engine_familias_sustitutos import engine_familias_sustitutos
from .engine_ofertas_descuentos import engine_ofertas_descuentos
from .engine_pedido_optimo import engine_pedido_optimo
from .engine_perfil_cliente import engine_perfil_cliente
from .engine_presupuesto_mochila import engine_presupuesto_mochila
from .engine_proveedor_conveniente import engine_proveedor_conveniente
from .engine_riesgo_dependencia import engine_riesgo_dependencia
from .engine_venta_cruzada import engine_venta_cruzada
from .loaders import load_products, load_purchases, load_sales, load_supply_options
from .router import CHAT_INTENT, RouteResult, extract_money, extract_order_items, route_text


DEFAULT_MAX_QTY = 1_000_000.0


@dataclass
class DispatchOutcome:
    response: AssistantResponse
    pending: dict[str, Any] | None = None
    route: RouteResult | None = None
    executed: bool = False
    memory_update: dict[str, Any] | None = None


def handle_message(
    text: str,
    pending: dict[str, Any] | None = None,
    memory: dict[str, Any] | None = None,
) -> DispatchOutcome:
    if pending:
        route = _complete_pending(text, pending)
    else:
        route = route_text(text)
        _apply_memory(route, memory or {})

    if not route.understood:
        return DispatchOutcome(_unknown_response(route), None, route, False)

    return dispatch_route(route)


def dispatch_route(route: RouteResult) -> DispatchOutcome:
    intent = route.intent
    slots = dict(route.slots)

    if intent == CHAT_INTENT:
        return _done(_chat_response(route), route)

    if route.confidence < 0.45:
        return _ask(
            intent,
            "Entendi una intencion probable, pero necesito confirmarla. "
            f"Quieres ejecutar **{intent}**?",
            slots,
            "confirm_intent",
            route,
        )

    if intent == "buscar_producto":
        query = slots.get("query") or route.text
        return _done(engine_buscar_producto(str(query)), route)

    if intent == "perfil_cliente":
        customer = slots.get("customer_text") or route.text
        pending = _maybe_ask_entity("customer_text", customer, slots, intent, route)
        if pending:
            return pending
        return _done(engine_perfil_cliente(str(customer)), route, {"customer_text": str(customer)})

    if intent == "cliente_abastecimiento":
        customer = slots.get("customer_text") or route.text
        pending = _maybe_ask_entity("customer_text", customer, slots, intent, route)
        if pending:
            return pending
        return _done(engine_cliente_abastecimiento(str(customer)), route, {"customer_text": str(customer)})

    if intent == "proveedor_conveniente":
        product = slots.get("product_text") or ""
        if not product:
            return _ask(intent, "Que producto quieres abastecer?", slots, "product_text", route)
        pending = _maybe_ask_entity("product_text", product, slots, intent, route)
        if pending:
            return pending
        return _done(engine_proveedor_conveniente(str(product)), route, {"product_text": str(product)})

    if intent == "pedido_optimo":
        order_result = _resolve_order(slots, intent, route)
        if isinstance(order_result, DispatchOutcome):
            return order_result
        return _done(engine_pedido_optimo(order_result), route, {"order": order_result})

    if intent == "presupuesto_mochila":
        amount = slots.get("amount")
        if amount is None:
            return _ask(intent, "Que presupuesto tienes? Ejemplo: S/ 2000.", slots, "amount", route)
        order_result = _resolve_budget_order(slots, intent, route)
        if isinstance(order_result, DispatchOutcome):
            return order_result
        return _done(engine_presupuesto_mochila(order_result, float(amount)), route, {"order": order_result, "amount": amount})

    if intent == "ofertas_descuentos":
        return _done(engine_ofertas_descuentos(), route)

    if intent == "familias_sustitutos":
        product = slots.get("product_text")
        if product:
            pending = _maybe_ask_entity("product_text", product, slots, intent, route)
            if pending:
                return pending
        return _done(engine_familias_sustitutos(str(product) if product else None), route, {"product_text": str(product)} if product else None)

    if intent == "venta_cruzada":
        product = slots.get("product_text") or ""
        if not product:
            return _ask(intent, "Sobre que producto quieres una recomendacion de venta cruzada?", slots, "product_text", route)
        pending = _maybe_ask_entity("product_text", product, slots, intent, route)
        if pending:
            return pending
        return _done(engine_venta_cruzada(str(product)), route, {"product_text": str(product)})

    if intent == "riesgo_dependencia":
        supplier = slots.get("supplier_text")
        if "supplier_text" in route.missing_slots:
            return _ask(intent, "Que proveedor quieres simular que se pierde?", slots, "supplier_text", route)
        if supplier:
            pending = _maybe_ask_entity("supplier_text", supplier, slots, intent, route)
            if pending:
                return pending
        return _done(engine_riesgo_dependencia(str(supplier) if supplier else None), route, {"supplier_text": str(supplier)} if supplier else None)

    return DispatchOutcome(_unknown_response(route), None, route, False)


def _resolve_order(slots: dict[str, Any], intent: str, route: RouteResult) -> dict[str, float] | DispatchOutcome:
    items = slots.get("order_items") or []
    if not items:
        return _ask(
            intent,
            "Indica productos y cantidades. Ejemplo: 100 de 5004, 50 de 5041.",
            slots,
            "order_items",
            route,
        )
    return _items_to_order(items, slots, intent, route)


def _resolve_budget_order(slots: dict[str, Any], intent: str, route: RouteResult) -> dict[str, float] | DispatchOutcome:
    items = slots.get("order_items") or []
    if items:
        return _items_to_order(items, slots, intent, route)

    product = slots.get("product_text") or ""
    if not product:
        return _ask(intent, "Que producto o productos quieres comprar con ese presupuesto?", slots, "product_text", route)

    pending = _maybe_ask_entity("product_text", product, slots, intent, route)
    if pending:
        return pending
    resolved = resolve_product(load_products(), str(product))
    if resolved is None:
        return _ask_candidates("product_text", product, slots, intent, route)
    product_id, _ = resolved
    return {product_id: _default_quantity(product_id)}


def _items_to_order(
    items: list[dict[str, Any]], slots: dict[str, Any], intent: str, route: RouteResult
) -> dict[str, float] | DispatchOutcome:
    order: dict[str, float] = {}
    for index, item in enumerate(items):
        text = str(item.get("item_text", "")).strip()
        quantity = float(item.get("quantity", 0))
        resolved = resolve_product(load_products(), text)
        if resolved is None:
            return _ask_candidates("order_item", text, slots, intent, route, order_index=index)
        product_id, _ = resolved
        order[product_id] = order.get(product_id, 0.0) + quantity
    return order


def _maybe_ask_entity(
    slot: str, value: str, slots: dict[str, Any], intent: str, route: RouteResult
) -> DispatchOutcome | None:
    value = str(value or "").strip()
    if not value:
        return _ask(intent, _question_for_slot(slot), slots, slot, route)

    resolved = _resolve_slot(slot, value)
    if resolved is not None:
        return None
    return _ask_candidates(slot, value, slots, intent, route)


def _ask_candidates(
    slot: str,
    value: str,
    slots: dict[str, Any],
    intent: str,
    route: RouteResult,
    order_index: int | None = None,
) -> DispatchOutcome:
    candidates = _candidate_rows(slot, value)
    if not candidates:
        return _ask(intent, f"No encontre '{value}'. Puedes escribirlo de otra forma?", slots, slot, route)

    table = pd.DataFrame(
        {"opcion": i + 1, "candidato": row["label"], "score": round(row["score"], 2)}
        for i, row in enumerate(candidates)
    )
    response = AssistantResponse(
        intent=intent,
        answer=f"Encontre varios candidatos para **{value}**. Responde con el numero correcto.",
        table=table,
        warnings=["No ejecuto el motor hasta confirmar la entidad."],
    )
    pending = {
        "intent": intent,
        "slots": slots,
        "missing_slot": slot,
        "choice_slot": slot,
        "candidates": candidates,
        "order_index": order_index,
    }
    return DispatchOutcome(response, pending, route, False)


def _complete_pending(text: str, pending: dict[str, Any]) -> RouteResult:
    intent = str(pending["intent"])
    slots = dict(pending.get("slots") or {})
    reply = (text or "").strip()

    if pending.get("choice_slot"):
        selected = _select_candidate(reply, pending.get("candidates", []))
        if selected is not None:
            slot = str(pending["choice_slot"])
            if slot == "order_item":
                items = list(slots.get("order_items") or [])
                index = int(pending.get("order_index") or 0)
                if 0 <= index < len(items):
                    items[index] = {**items[index], "item_text": selected["value"]}
                    slots["order_items"] = items
            else:
                slots[slot] = selected["value"]
        else:
            slot = str(pending.get("missing_slot") or "")
            if slot:
                slots[slot] = reply
    else:
        slot = str(pending.get("missing_slot") or "")
        if slot == "amount":
            slots["amount"] = extract_money(reply)
        elif slot == "order_items":
            slots["order_items"] = extract_order_items(reply)
        elif slot:
            slots[slot] = reply

    return RouteResult(text=reply, intent=intent, confidence=0.99, slots=slots, scores={intent: 1.0})


def _select_candidate(reply: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if reply.strip().isdigit():
        index = int(reply.strip()) - 1
        if 0 <= index < len(candidates):
            return candidates[index]
    for row in candidates:
        if similarity(reply, row["label"]) >= 0.85:
            return row
    return None


def _resolve_slot(slot: str, value: str) -> tuple[str, str] | None:
    if slot in {"product_text", "order_item"}:
        return resolve_product(load_products(), value)
    if slot == "customer_text":
        return resolve_customer(load_sales(), value)
    if slot == "supplier_text":
        return resolve_supplier(load_purchases(), value)
    return (value, value)


def _candidate_rows(slot: str, value: str, k: int = 5) -> list[dict[str, Any]]:
    if slot in {"product_text", "order_item"}:
        table = load_products()
        rows = [
            {"value": str(row.product_id), "label": f"{row.product_id} - {row.product_name}", "score": similarity(value, row.product_name)}
            for row in table[["product_id", "product_name"]].dropna().drop_duplicates("product_id").itertuples()
        ]
    elif slot == "customer_text":
        table = load_sales()[["customer_norm", "customer"]].dropna().drop_duplicates()
        rows = [
            {"value": str(row.customer), "label": str(row.customer), "score": similarity(value, row.customer)}
            for row in table.itertuples()
        ]
    elif slot == "supplier_text":
        table = load_purchases()[["supplier_norm", "supplier"]].dropna().drop_duplicates()
        rows = [
            {"value": str(row.supplier), "label": str(row.supplier), "score": similarity(value, row.supplier)}
            for row in table.itertuples()
        ]
    else:
        return []
    return [row for row in sorted(rows, key=lambda r: r["score"], reverse=True)[:k] if row["score"] >= 0.35]


def _default_quantity(product_id: str) -> float:
    options = load_supply_options()
    data = options.loc[options["product_id"].astype(str) == str(product_id)]
    if data.empty:
        return DEFAULT_MAX_QTY
    return max(float(data["capacity_units"].sum()), 1.0)


def _ask(
    intent: str,
    message: str,
    slots: dict[str, Any],
    missing_slot: str,
    route: RouteResult,
) -> DispatchOutcome:
    response = AssistantResponse(
        intent=intent,
        answer=message,
        warnings=["Respuesta pendiente: escribe el dato faltante en el siguiente mensaje."],
    )
    pending = {"intent": intent, "slots": slots, "missing_slot": missing_slot}
    return DispatchOutcome(response, pending, route, False)


def _done(
    response: AssistantResponse,
    route: RouteResult,
    memory_update: dict[str, Any] | None = None,
) -> DispatchOutcome:
    if memory_update is None:
        memory_update = _memory_from_response(response)
    return DispatchOutcome(response, None, route, True, memory_update)


def _apply_memory(route: RouteResult, memory: dict[str, Any]) -> None:
    text = route.text
    slots = route.slots
    norm = route.text.upper()

    if _mentions_previous_product(text) and memory.get("product_text"):
        slots["product_text"] = memory["product_text"]
    if _mentions_previous_customer(text) and memory.get("customer_text"):
        slots["customer_text"] = memory["customer_text"]
    if _mentions_previous_supplier(text) and memory.get("supplier_text"):
        slots["supplier_text"] = memory["supplier_text"]

    # Follow-ups without explicit noun: "y que proveedor conviene?"
    if route.intent in {"proveedor_conveniente", "venta_cruzada", "familias_sustitutos"}:
        if (not slots.get("product_text") or _is_generic_product_text(slots.get("product_text"))) and memory.get("product_text"):
            slots["product_text"] = memory["product_text"]
    if route.intent in {"perfil_cliente", "cliente_abastecimiento"}:
        if not slots.get("customer_text") and memory.get("customer_text"):
            slots["customer_text"] = memory["customer_text"]
    if route.intent == "riesgo_dependencia":
        if not slots.get("supplier_text") and memory.get("supplier_text") and "VISION GLOBAL" not in norm:
            slots["supplier_text"] = memory["supplier_text"]

    route.missing_slots[:] = [
        slot for slot in route.missing_slots if slots.get(slot) in (None, "", [])
    ]


def _memory_from_response(response: AssistantResponse) -> dict[str, Any] | None:
    if not response.ok:
        return None
    update: dict[str, Any] = {}
    entities = response.entities or {}
    if entities.get("producto"):
        update["product_text"] = str(entities["producto"])
    if entities.get("product_id"):
        update["product_id"] = str(entities["product_id"])
    if entities.get("cliente"):
        update["customer_text"] = str(entities["cliente"])
    if entities.get("proveedor"):
        update["supplier_text"] = str(entities["proveedor"])
    if response.intent == "buscar_producto" and response.table is not None and not response.table.empty:
        first = response.table.iloc[0]
        label = first.get("label")
        product = str(first.get("product", ""))
        if label:
            update["product_text"] = str(label)
        if product:
            update["product_id"] = product.replace("PRODUCT:", "")
    return update or None


def _mentions_previous_product(text: str) -> bool:
    upper = text.upper()
    return any(marker in upper for marker in ["ESE PRODUCTO", "ESTE PRODUCTO", "EL PRODUCTO", "LO MISMO", "EL ANTERIOR"])


def _mentions_previous_customer(text: str) -> bool:
    upper = text.upper()
    return any(marker in upper for marker in ["ESE CLIENTE", "ESTE CLIENTE", "EL CLIENTE", "MISMO CLIENTE"])


def _mentions_previous_supplier(text: str) -> bool:
    upper = text.upper()
    return any(marker in upper for marker in ["ESE PROVEEDOR", "ESTE PROVEEDOR", "EL PROVEEDOR", "MISMO PROVEEDOR"])


def _is_generic_product_text(value: object) -> bool:
    upper = str(value or "").upper().strip(" ?.!")
    generic_fragments = [
        "QUE PROVEEDOR CONVIENE",
        "PROVEEDOR CONVIENE",
        "QUE PRODUCTOS SE VENDEN",
        "QUE MAS OFREZCO",
        "QUE MAS RECOMIENDO",
        "ESE PRODUCTO",
        "ESTE PRODUCTO",
    ]
    return not upper or any(fragment in upper for fragment in generic_fragments)


def _chat_response(route: RouteResult) -> AssistantResponse:
    norm = route.text.upper()
    if "GRACIAS" in norm:
        answer = "De nada. Puedes seguir preguntando por productos, clientes, proveedores, pedidos, presupuesto o riesgo."
    else:
        answer = (
            "Hola. Puedo ayudarte con preguntas comerciales como:\n\n"
            "- buscar productos por nombre natural\n"
            "- ver que compra un cliente\n"
            "- encontrar proveedores convenientes\n"
            "- optimizar pedidos con cantidades\n"
            "- calcular compras con presupuesto\n"
            "- ver sustitutos, venta cruzada, ofertas y riesgo de proveedores"
        )
    return AssistantResponse(intent=CHAT_INTENT, answer=answer)


def _unknown_response(route: RouteResult) -> AssistantResponse:
    return AssistantResponse(
        intent="desconocido",
        answer=(
            "No pude clasificar la pregunta con suficiente confianza. Prueba con ejemplos como:\n\n"
            "- Busca frasco gotero ambar 30 ml\n"
            "- Que me compra mas ODONTOLOGIA SAN ANTONIO\n"
            "- Necesito 100 de 5004 y 50 de 5041\n"
            "- Tengo S/ 2000 para comprar frasco gotero\n"
            "- Que pasa si pierdo ENVIPLAST"
        ),
        technical={"scores": route.scores, "slots": route.slots},
    )


def _question_for_slot(slot: str) -> str:
    return {
        "product_text": "Que producto quieres analizar?",
        "customer_text": "Que cliente quieres analizar?",
        "supplier_text": "Que proveedor quieres analizar?",
        "order_item": "Que producto corresponde a esa linea?",
    }.get(slot, "Que dato falta?")
