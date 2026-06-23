import re
import unicodedata
from difflib import SequenceMatcher


def strip_accents(value: str) -> str:
    text = str(value)
    return "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = strip_accents(str(value)).upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_column_name(value: str) -> str:
    text = normalize_text(value).lower()
    return text.replace(" ", "_")


def similarity(a: object, b: object) -> float:
    left = normalize_text(a)
    right = normalize_text(b)
    if not left or not right:
        return 0.0
    try:
        from rapidfuzz import fuzz

        return float(fuzz.token_set_ratio(left, right)) / 100.0
    except Exception:
        return SequenceMatcher(None, left, right).ratio()

