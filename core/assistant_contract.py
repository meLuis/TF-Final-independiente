"""Contrato de salida uniforme del asistente comercial.

Cada motor de seccion (core/assistant/engine_*.py) devuelve un AssistantResponse
con la misma forma, de modo que la capa de presentacion (assistant_ui.py) pueda
renderizar cualquier respuesta sin conocer el algoritmo que la produjo.

Este modulo es deliberadamente independiente de Streamlit (solo dataclasses,
typing y pandas): la logica vive en core/, la pintura vive fuera. Cuando llegue
la caja de texto + router, este contrato no cambia: el router solo elige que
engine_* llamar y reusa el mismo render.

El par "baseline del curso vs algoritmo investigado" vive DENTRO del contrato
(dos AlgoVariant), no en la pagina, para que la narrativa de sustentacion sea
uniforme en las 10 secciones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class AlgoVariant:
    """Una de las dos caras de la comparacion (baseline o investigado)."""

    name: str                                   # "BFS clasico", "Min-cost flow"...
    role: str = "investigado"                   # "baseline" | "investigado"
    table: pd.DataFrame | None = None           # resultado tabular de esta variante
    metrics: dict[str, Any] = field(default_factory=dict)  # {expanded_nodes, cost...}
    summary: str = ""                           # 1 linea legible


@dataclass
class AssistantResponse:
    """Respuesta uniforme de cualquier seccion del asistente."""

    intent: str                                 # id de la seccion / intencion
    answer: str = ""                            # respuesta natural breve (markdown)
    entities: dict[str, Any] = field(default_factory=dict)   # entidades resueltas
    table: pd.DataFrame | None = None           # tabla principal a mostrar
    algorithm: str = ""                         # nombre del algoritmo investigado
    baseline: AlgoVariant | None = None         # cara "antes" (curso)
    investigated: AlgoVariant | None = None     # cara "ahora" (investigado)
    evidence: list[str] = field(default_factory=list)        # grafos/archivos usados
    technical: dict[str, Any] = field(default_factory=dict)  # detalle para sustentacion
    extra_tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    @classmethod
    def fail(cls, intent: str, message: str) -> "AssistantResponse":
        """Atajo para una respuesta de error renderizable."""
        return cls(intent=intent, error=message)

    @property
    def ok(self) -> bool:
        return self.error is None
