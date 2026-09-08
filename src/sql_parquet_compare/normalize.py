from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

import pandas as pd

_QUANTUM = {
    0: Decimal("1"),
    1: Decimal("0.1"),
    2: Decimal("0.01"),
    3: Decimal("0.001"),
    4: Decimal("0.0001"),
    5: Decimal("0.00001"),
    6: Decimal("0.000001"),
    7: Decimal("0.0000001"),
    8: Decimal("0.00000001"),
}


_ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2})?")


def normalize_frame(
    frame: pd.DataFrame,
    *,
    strip_strings: bool = True,
    case_sensitive_columns: bool = False,
    decimal_places: int = 6,
    datetime_unit: str = "us",
    columns: list[str] | None = None,
    exclude_columns: list[str] | None = None,
    bool_columns: list[str] | None = None,
) -> pd.DataFrame:
    """Align SQL and Parquet frames so like-for-like comparison is type-stable."""
    out = frame.copy()
    out.columns = [_normalize_name(col, case_sensitive_columns) for col in out.columns]

    selected = [_normalize_name(col, case_sensitive_columns) for col in columns] if columns else list(out.columns)
    excluded = {_normalize_name(col, case_sensitive_columns) for col in (exclude_columns or [])}
    bool_names = {_normalize_name(col, case_sensitive_columns) for col in (bool_columns or [])}
    keep = [col for col in selected if col in out.columns and col not in excluded]
    out = out.loc[:, keep]

    for column in out.columns:
        if column in bool_names:
            out[column] = out[column].map(_to_bool, na_action="ignore").astype("boolean")
            continue
        out[column] = _normalize_series(
            out[column],
            strip_strings=strip_strings,
            decimal_places=decimal_places,
            datetime_unit=datetime_unit,
        )
    return out.reset_index(drop=True)


def _normalize_name(name: object, case_sensitive: bool) -> str:
    text = str(name).strip()
    return text if case_sensitive else text.lower()


def _normalize_series(
    series: pd.Series,
    *,
    strip_strings: bool,
    decimal_places: int,
    datetime_unit: str,
) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        converted = pd.to_datetime(series, utc=True, errors="coerce")
        if getattr(converted.dt, "tz", None) is not None:
            converted = converted.dt.tz_convert("UTC").dt.tz_localize(None)
        return converted.astype(f"datetime64[{datetime_unit}]")

    if _looks_dates(series):
        converted = pd.to_datetime(series, utc=True, errors="coerce")
        if getattr(converted.dt, "tz", None) is not None:
            converted = converted.dt.tz_convert("UTC").dt.tz_localize(None)
        return converted.astype(f"datetime64[{datetime_unit}]")

    if pd.api.types.is_bool_dtype(series) or str(series.dtype) in {"boolean", "bool"}:
        return series.astype("boolean")

    if pd.api.types.is_integer_dtype(series):
        return series.astype("Int64")

    if pd.api.types.is_float_dtype(series) or _looks_decimal(series):
        return series.map(lambda value: _to_decimal(value, decimal_places), na_action="ignore").astype("object")

    if pd.api.types.is_string_dtype(series) or series.dtype == object:
        as_string = series.astype("string")
        if strip_strings:
            as_string = as_string.str.strip()
        sample = series.dropna().head(20)
        if not sample.empty and _looks_datetime_strings(sample):
            converted = pd.to_datetime(series, utc=True, errors="coerce")
            if getattr(converted.dt, "tz", None) is not None:
                converted = converted.dt.tz_convert("UTC").dt.tz_localize(None)
            return converted.astype(f"datetime64[{datetime_unit}]")
        return as_string

    return series


def _looks_dates(series: pd.Series) -> bool:
    sample = series.dropna().head(20).tolist()
    return bool(sample) and all(isinstance(value, (date, datetime, pd.Timestamp)) for value in sample)


def _to_bool(value: object) -> bool | pd.NA:
    if value is None or (not isinstance(value, (bytes, bytearray)) and pd.isna(value)):
        return pd.NA
    if isinstance(value, (bytes, bytearray)):
        return value != b"\x00" and value != bytes([0])
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "t", "yes"}:
            return True
        if lowered in {"0", "false", "f", "no", ""}:
            return False
    return bool(value)


def _looks_decimal(series: pd.Series) -> bool:
    sample = series.dropna().head(20).tolist()
    return bool(sample) and all(isinstance(value, Decimal) for value in sample)


def _looks_datetime_strings(sample: pd.Series) -> bool:
    values = [str(value) for value in sample.tolist()]
    return bool(values) and all(_ISO_DATETIME.match(value) for value in values)


def _to_decimal(value: object, places: int) -> Decimal | pd.NA:
    if value is None or (isinstance(value, float) and pd.isna(value)) or pd.isna(value):
        return pd.NA
    try:
        decimal = value if isinstance(value, Decimal) else Decimal(str(value))
        quantum = _QUANTUM.get(places, Decimal("1").scaleb(-places))
        return decimal.quantize(quantum, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return pd.NA
