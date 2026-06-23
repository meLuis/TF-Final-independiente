"""Router local de lenguaje natural para el asistente comercial.

No depende de Streamlit ni de datos cargados. Su responsabilidad es acotada:
clasificar la pregunta, extraer slots textuales simples y reportar confianza.
La resolucion contra CSVs y la llamada a motores vive en dispatch.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from core.text_utils import normalize_text


UNKNOWN_INTENT = "desconocido"
CHAT_INTENT = "chat"


@dataclass
class RouteResult:
    text: str
    intent: str
    confidence: float
    slots: dict[str, Any] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    missing_slots: list[str] = field(default_factory=list)

    @property
    def understood(self) -> bool:
        return self.intent != UNKNOWN_INTENT and self.confidence >= 0.35


INTENT_PATTERNS: dict[str, list[tuple[str, float]]] = {
    CHAT_INTENT: [
        ("HOLA", 6),
        ("BUENAS", 6),
        ("BUENOS DIAS", 6),
        ("BUENAS TARDES", 6),
        ("BUENAS NOCHES", 6),
        ("AYUDA", 6),
        ("QUE PUEDES HACER", 7),
        ("COMO FUNCIONAS", 6),
        ("GRACIAS", 6),
    ],
    "buscar_producto": [
        ("BUSCA", 4),
        ("BUSCAR", 4),
        ("ENCUENTRA", 3),
        ("QUIERO COMPRAR", 3),
        ("ESTOY BUSCANDO", 4),
        ("QUE PRODUCTO", 3),
        ("PRODUCTO QUISO DECIR", 5),
        ("ALTERNATIVAS PARECIDAS", 3),
    ],
    "perfil_cliente": [
        ("CLIENTE", 1.5),
        ("COMPRA MAS", 5),
        ("COMPRA", 2),
        ("PIDE MAS", 5),
        ("PIDE", 2),
        ("QUE LE VENDO", 4),
        ("QUE ME PIDE", 4),
        ("PRODUCTOS FRECUENTES", 4),
        ("PERFIL", 3),
        ("CUANTO REPRESENTA", 4),
    ],
    "cliente_abastecimiento": [
        ("DE DONDE", 5),
        ("SUELO COMPRAR", 5),
        ("DONDE COMPRO", 5),
        ("QUE COMPRO PARA", 5),
        ("DE QUIEN COMPRO", 5),
        ("ABASTECE", 4),
        ("ABASTECIMIENTO", 4),
        ("PROVEEDORES NECESITO", 4),
        ("LO QUE PIDE", 3),
    ],
    "proveedor_conveniente": [
        ("PROVEEDOR CONVIENE", 6),
        ("QUE PROVEEDOR", 4),
        ("A QUIEN LE COMPRO", 5),
        ("A QUIEN COMPRO", 5),
        ("QUIEN ME VENDE", 5),
        ("ME VENDE MAS BARATO", 5),
        ("MAS BARATO", 4),
        ("BARATO", 2),
        ("MEJOR PROVEEDOR", 5),
        ("HISTORIAL PARA", 3),
    ],
    "pedido_optimo": [
        ("NECESITO", 3),
        ("ARMA UN PEDIDO", 6),
        ("ARMAR PEDIDO", 6),
        ("QUIERO PEDIR", 4),
        ("PEDIDO", 5),
        ("MULTI SKU", 5),
        ("SKU", 2),
        ("REPARTO", 4),
        ("OPTIMIZAR", 4),
        ("CUBRIR TODO", 4),
        ("MENOR COSTO", 4),
    ],
    "presupuesto_mochila": [
        ("PRESUPUESTO", 6),
        ("CUANTO PUEDO", 5),
        ("CUANTO ME ALCANZA", 6),
        ("ME ALCANZA", 5),
        ("TENGO S", 5),
        ("CON S", 5),
        ("SOLES", 4),
        ("PLATA", 3),
        ("DINERO", 3),
        ("MAXIMIZO", 4),
        ("SOBRANTE", 3),
    ],
    "ofertas_descuentos": [
        ("OFERTA", 5),
        ("OFERTAS", 5),
        ("DESCUENTO", 5),
        ("BONIFICACION", 5),
        ("AHORRO", 4),
        ("AHORROS", 4),
        ("COSTO REFERENCIA", 3),
    ],
    "familias_sustitutos": [
        ("FAMILIA", 5),
        ("FAMILIAS", 5),
        ("SUSTITUTO", 5),
        ("SUSTITUTOS", 5),
        ("REEMPLAZO", 4),
        ("REEMPLAZAR", 4),
        ("NO HAY", 3),
        ("SIMILAR", 4),
        ("PARECIDO", 4),
        ("PARECIDOS", 4),
        ("ALTERNATIVA", 3),
        ("NO TENGO STOCK", 4),
    ],
    "venta_cruzada": [
        ("JUNTO", 5),
        ("VENDEN JUNTOS", 6),
        ("SE VENDEN", 3),
        ("COMBO", 5),
        ("COMPLEMENTO", 4),
        ("COMPLEMENTOS", 4),
        ("OFREZCO", 4),
        ("OFRECER", 4),
        ("RECOMENDAR", 5),
        ("VENTA CRUZADA", 6),
        ("QUE MAS", 4),
    ],
    "riesgo_dependencia": [
        ("RIESGO", 5),
        ("DEPENDENCIA", 5),
        ("DEPENDO", 5),
        ("PIERDO", 6),
        ("NO ME ATIENDE", 5),
        ("FALLA", 4),
        ("PERDER", 5),
        ("CUELLO DE BOTELLA", 6),
        ("CRITICO", 4),
        ("PROVEEDOR CRITICO", 6),
    ],
}


def route_text(text: str) -> RouteResult:
    raw = (text or "").strip()
    norm = normalize_text(raw)
    slots = extract_slots(raw)
    scores = _score_intents(norm, slots)
    intent, confidence = _best_intent(scores)

    if intent == UNKNOWN_INTENT:
        return RouteResult(raw, UNKNOWN_INTENT, 0.0, slots, scores, [])

    missing = _static_missing_slots(intent, slots, norm)
    return RouteResult(raw, intent, confidence, slots, scores, missing)


def extract_slots(text: str) -> dict[str, Any]:
    clean = (text or "").strip()
    amount = extract_money(clean)
    scrubbed = _remove_money(clean)
    order_items = extract_order_items(scrubbed)

    return {
        "query": _cleanup_entity(clean),
        "amount": amount,
        "order_items": order_items,
        "product_text": extract_product_text(clean, order_items),
        "customer_text": extract_customer_text(clean),
        "supplier_text": extract_supplier_text(clean),
    }


def extract_money(text: str) -> float | None:
    raw_patterns = [
        r"(?:S\/|S\.\/)\s*(\d+(?:[.,]\d+)?)",
        r"(\d+(?:[.,]\d+)?)\s*(?:soles?)",
    ]
    for pattern in raw_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _to_float(match.group(1))

    norm_patterns = [
        r"(?:S|SOLES?|PRESUPUESTO(?:\s+DE)?)\s*(\d+(?:[.,]\d+)?)",
        r"(\d+(?:[.,]\d+)?)\s*(?:SOLES?)",
    ]
    norm = normalize_text(text)
    for pattern in norm_patterns:
        match = re.search(pattern, norm, flags=re.IGNORECASE)
        if match:
            return _to_float(match.group(1))
    return None


def extract_order_items(text: str) -> list[dict[str, Any]]:
    normalized_separators = re.sub(r"\s+(?:Y|E)\s+(?=\d)", ", ", text, flags=re.IGNORECASE)
    rows: list[dict[str, Any]] = []
    pattern = re.compile(
        r"(?P<qty>\d+(?:[.,]\d+)?)\s*"
        r"(?:UNIDADES?|UNDS?|UND|U)?\s*"
        r"(?:DE|DEL|X)?\s+"
        r"(?P<item>[^,;]+)",
        flags=re.IGNORECASE,
    )
    for match in pattern.finditer(normalized_separators):
        item = _cleanup_entity(match.group("item"))
        if not item or _looks_like_money_context(item) or _looks_like_measure_unit(item):
            continue
        rows.append({"quantity": _to_float(match.group("qty")), "item_text": item})
    return rows


def extract_product_text(text: str, order_items: list[dict[str, Any]] | None = None) -> str:
    if order_items:
        return str(order_items[0]["item_text"])
    without_money = _remove_money(text)
    patterns = [
        r"(?:JUNTO CON|JUNTO A|VENDEN JUNTO CON|VENDE JUNTO CON|COMBO CON|RECOMENDAR PARA)\s+(.+)$",
        r"(?:QUIEN ME VENDE MAS BARATO|ME VENDE MAS BARATO|MAS BARATO)\s+(.+)$",
        r"(?:PRODUCTO BASE|PRODUCTO A ABASTECER|PRODUCTO|SKU)\s+(.+)$",
        r"(?:BUSCA|BUSCAR|ENCUENTRA)\s+(.+)$",
        r"(?:QUIERO COMPRAR|ESTOY BUSCANDO|COMPRAR|COMPRO|COMPRAR DE|OFRECER|RECOMENDAR|SUSTITUTO DE|PARECIDO A|PARECIDOS A|PARECIDOS AL|PARECIDOS A LA|SIMILAR A|SIMILAR AL|ALTERNATIVA A|ALTERNATIVA AL)\s+(.+)$",
        r"(?:PARA|DE|DEL)\s+(.+)$",
    ]
    return _first_capture(without_money, patterns) or _cleanup_entity(without_money)


def extract_customer_text(text: str) -> str:
    patterns = [
        r"(?:CLIENTE)\s+(.+)$",
        r"(?:QUE ME COMPRA MAS|QUE COMPRA MAS|QUE ME PIDE MAS|QUE PIDE MAS|QUE LE VENDO A|QUE ME PIDE|QUE COMPRO PARA|PERFIL DE)\s+(.+)$",
        r"(?:LO QUE PIDE|LO QUE COMPRA)\s+(.+)$",
    ]
    return _first_capture(text, patterns) or ""


def extract_supplier_text(text: str) -> str:
    patterns = [
        r"(?:PROVEEDOR)\s+(.+)$",
        r"(?:PIERDO|PERDER|SIN|DEPENDO DE|NO ME ATIENDE)\s+(.+)$",
        r"(.+)\s+NO ME ATIENDE$",
    ]
    value = _first_capture(text, patterns) or ""
    generic = {"ESTE PROVEEDOR", "UN PROVEEDOR", "PROVEEDOR"}
    return "" if normalize_text(value) in generic else value


def _score_intents(norm: str, slots: dict[str, Any]) -> dict[str, float]:
    scores = {intent: 0.0 for intent in INTENT_PATTERNS}
    for intent, patterns in INTENT_PATTERNS.items():
        for phrase, weight in patterns:
            if phrase in norm:
                scores[intent] += weight

    if scores[CHAT_INTENT] and sum(value for key, value in scores.items() if key != CHAT_INTENT) >= 3:
        scores[CHAT_INTENT] = 0.0

    if slots.get("amount") is not None:
        scores["presupuesto_mochila"] += 6
    if len(slots.get("order_items", [])) >= 2:
        scores["pedido_optimo"] += 7
    elif len(slots.get("order_items", [])) == 1 and slots.get("amount") is None:
        scores["pedido_optimo"] += 2

    if "CLIENTE" in norm and ("DE DONDE" in norm or "PROVEEDOR" in norm or "ABASTEC" in norm):
        scores["cliente_abastecimiento"] += 5
    if "PROVEEDOR" in norm and any(word in norm for word in ["PIERDO", "PERDER", "RIESGO", "DEPEND"]):
        scores["riesgo_dependencia"] += 6
    if "PROVEEDOR" in norm and any(word in norm for word in ["CONVIENE", "BARATO", "COMPRO", "MEJOR"]):
        scores["proveedor_conveniente"] += 5
    if any(word in norm for word in ["ESE PRODUCTO", "ESTE PRODUCTO", "LO MISMO", "EL ANTERIOR"]):
        scores["buscar_producto"] -= 1

    return scores


def _best_intent(scores: dict[str, float]) -> tuple[str, float]:
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_intent, best = ordered[0]
    second = ordered[1][1] if len(ordered) > 1 else 0.0
    if best < 2:
        return UNKNOWN_INTENT, 0.0
    confidence = best / (best + second + 1.0)
    return best_intent, round(min(confidence, 0.99), 2)


def _static_missing_slots(intent: str, slots: dict[str, Any], norm: str) -> list[str]:
    missing: list[str] = []
    if intent == CHAT_INTENT:
        return missing
    if intent in {"perfil_cliente", "cliente_abastecimiento"} and not slots.get("customer_text"):
        missing.append("customer_text")
    if intent in {"proveedor_conveniente", "venta_cruzada"} and not slots.get("product_text"):
        missing.append("product_text")
    if intent == "pedido_optimo" and not slots.get("order_items"):
        missing.append("order_items")
    if intent == "presupuesto_mochila":
        if slots.get("amount") is None:
            missing.append("amount")
        if not slots.get("order_items") and not slots.get("product_text"):
            missing.append("product_text")
    if intent == "riesgo_dependencia" and any(word in norm for word in ["PIERDO", "PERDER", "SIN"]):
        if not slots.get("supplier_text"):
            missing.append("supplier_text")
    return missing


def _first_capture(text: str, patterns: list[str]) -> str:
    norm = normalize_text(text)
    for pattern in patterns:
        match = re.search(pattern, norm, flags=re.IGNORECASE)
        if match:
            return _cleanup_entity(match.group(1))
    return ""


def _cleanup_entity(value: str) -> str:
    text = str(value or "").strip(" .,:;?¿!¡")
    text = re.sub(r"\s+", " ", text)
    norm = normalize_text(text)
    prefixes = [
        "QUE ME ", "QUE ", "CUAL ES ", "CUALES SON ", "DIME ", "MUESTRA ",
        "PASA SI ", "SI ",
        "POR FAVOR ", "PARA ", "DE ", "DEL ", "EL ", "LA ", "LOS ", "LAS ",
        "AL ", "A LA ", "UN ", "UNA ", "ESTE ", "ESTA ",
    ]
    for prefix in prefixes:
        if norm.startswith(prefix):
            words = text.split()
            drop = len(prefix.split())
            return _cleanup_entity(" ".join(words[drop:]))
    return text


def _remove_money(text: str) -> str:
    text = re.sub(r"(?:S\/|S\.\/)\s*\d+(?:[.,]\d+)?", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\d+(?:[.,]\d+)?\s*SOLES?", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _looks_like_money_context(text: str) -> bool:
    norm = normalize_text(text)
    return norm.startswith(("SOLES", "PRESUPUESTO"))


def _looks_like_measure_unit(text: str) -> bool:
    return normalize_text(text) in {"ML", "L", "LT", "MM", "CM", "M", "GR", "G", "KG"}


def _to_float(value: str) -> float:
    return float(str(value).replace(",", "."))
