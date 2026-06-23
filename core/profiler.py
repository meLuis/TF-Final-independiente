from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import pandas as pd


@dataclass
class ColumnProfile:
    column: str
    dtype: str
    null_rate: float
    unique_count: int
    sample_values: list[str]
    parseable_as_number: float
    parseable_as_date: float
    min_value: float | None
    max_value: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _numeric_series(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype(str)
        .str.replace(r"[^\d,\.\-]", "", regex=True)
        .str.replace(",", ".", regex=False)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def _date_series(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip()
    date_like = text.str.contains(
        r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4})|(?:\d{4}[/-]\d{1,2}[/-]\d{1,2})",
        regex=True,
        na=False,
    )
    parsed = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    if date_like.any():
        parsed.loc[date_like] = pd.to_datetime(
            text.loc[date_like],
            errors="coerce",
            dayfirst=True,
        )
    return parsed


def profile_dataframe(df: pd.DataFrame, sample_size: int = 5) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    total = max(len(df), 1)

    for column in df.columns:
        series = df[column]
        non_null = series.dropna()
        sample_values = [str(v)[:120] for v in non_null.head(sample_size).tolist()]

        numeric = _numeric_series(series)
        parsed_dates = _date_series(series)

        numeric_ratio = float(numeric.notna().sum() / total)
        date_ratio = float(parsed_dates.notna().sum() / total)

        min_value = None
        max_value = None
        if numeric.notna().any():
            min_value = float(numeric.min())
            max_value = float(numeric.max())

        profile = ColumnProfile(
            column=str(column),
            dtype=str(series.dtype),
            null_rate=float(series.isna().sum() / total),
            unique_count=int(series.nunique(dropna=True)),
            sample_values=sample_values,
            parseable_as_number=round(numeric_ratio, 4),
            parseable_as_date=round(date_ratio, 4),
            min_value=min_value,
            max_value=max_value,
        )
        profiles[str(column)] = profile.to_dict()

    return profiles


def profile_files(dataframes: dict[str, pd.DataFrame]) -> dict[str, dict[str, dict[str, Any]]]:
    return {name: profile_dataframe(df) for name, df in dataframes.items()}
