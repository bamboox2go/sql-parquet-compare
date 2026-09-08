from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

import pandas as pd

from sql_parquet_compare.config import CompareDefaults, TableMapping
from sql_parquet_compare.normalize import normalize_frame


@dataclass
class ValueMismatch:
    keys: dict[str, object]
    column: str
    sql: object
    parquet: object


@dataclass
class CompareResult:
    table: str
    passed: bool
    row_count_sql: int
    row_count_parquet: int
    extra_columns_sql: list[str] = field(default_factory=list)
    extra_columns_parquet: list[str] = field(default_factory=list)
    missing_in_parquet: list[dict[str, object]] = field(default_factory=list)
    missing_in_sql: list[dict[str, object]] = field(default_factory=list)
    duplicate_keys_sql: int = 0
    duplicate_keys_parquet: int = 0
    value_mismatches: list[ValueMismatch] = field(default_factory=list)
    truncated: bool = False
    message: str = ""

    def assertion_message(self) -> str:
        return self.message or ("like-for-like match" if self.passed else "mismatch")


def compare_frames(
    sql_df: pd.DataFrame,
    parquet_df: pd.DataFrame,
    mapping: TableMapping,
    defaults: CompareDefaults,
) -> CompareResult:
    sql_norm = normalize_frame(
        sql_df,
        strip_strings=defaults.strip_strings,
        case_sensitive_columns=defaults.case_sensitive_columns,
        decimal_places=mapping.decimal_places or defaults.decimal_places,
        datetime_unit=defaults.datetime_unit,
        columns=mapping.columns,
        exclude_columns=mapping.exclude_columns,
        bool_columns=mapping.bool_columns,
    )
    pq_norm = normalize_frame(
        parquet_df,
        strip_strings=defaults.strip_strings,
        case_sensitive_columns=defaults.case_sensitive_columns,
        decimal_places=mapping.decimal_places or defaults.decimal_places,
        datetime_unit=defaults.datetime_unit,
        columns=mapping.columns,
        exclude_columns=mapping.exclude_columns,
        bool_columns=mapping.bool_columns,
    )

    keys = [_name(col, defaults.case_sensitive_columns) for col in mapping.keys]
    extra_sql = sorted(set(sql_norm.columns) - set(pq_norm.columns))
    extra_pq = sorted(set(pq_norm.columns) - set(sql_norm.columns))
    shared = [col for col in sql_norm.columns if col in pq_norm.columns]

    result = CompareResult(
        table=mapping.name,
        passed=False,
        row_count_sql=len(sql_norm),
        row_count_parquet=len(pq_norm),
        extra_columns_sql=extra_sql,
        extra_columns_parquet=extra_pq,
    )

    if extra_sql or extra_pq:
        result.message = _format_result(result)
        return result

    sql_shared = sql_norm.loc[:, shared]
    pq_shared = pq_norm.loc[:, shared]
    atol = mapping.float_atol if mapping.float_atol is not None else defaults.float_atol
    rtol = mapping.float_rtol if mapping.float_rtol is not None else defaults.float_rtol
    cap = defaults.max_mismatches

    if keys:
        missing = [col for col in keys if col not in shared]
        if missing:
            result.message = f"Key columns not present after normalize: {missing}"
            return result
        result.duplicate_keys_sql = int(sql_shared.duplicated(keys).sum())
        result.duplicate_keys_parquet = int(pq_shared.duplicated(keys).sum())
        if result.duplicate_keys_sql or result.duplicate_keys_parquet:
            result.message = _format_result(result)
            return result
        _compare_on_keys(sql_shared, pq_shared, keys, shared, atol, rtol, cap, result)
    else:
        _compare_positional(sql_shared, pq_shared, shared, atol, rtol, cap, result)

    result.passed = (
        result.row_count_sql == result.row_count_parquet
        and not result.extra_columns_sql
        and not result.extra_columns_parquet
        and not result.missing_in_parquet
        and not result.missing_in_sql
        and not result.value_mismatches
        and not result.duplicate_keys_sql
        and not result.duplicate_keys_parquet
    )
    result.message = _format_result(result)
    return result


def _compare_on_keys(
    sql_df: pd.DataFrame,
    pq_df: pd.DataFrame,
    keys: list[str],
    shared: list[str],
    atol: float,
    rtol: float,
    cap: int,
    result: CompareResult,
) -> None:
    merged = sql_df.merge(pq_df, on=keys, how="outer", suffixes=("_sql", "_pq"), indicator=True)
    left_only = merged[merged["_merge"] == "left_only"]
    right_only = merged[merged["_merge"] == "right_only"]
    both = merged[merged["_merge"] == "both"]

    result.missing_in_parquet = _rows_as_dicts(left_only, keys, cap)
    result.missing_in_sql = _rows_as_dicts(right_only, keys, cap)
    if len(left_only) > cap or len(right_only) > cap:
        result.truncated = True

    value_cols = [col for col in shared if col not in keys]
    mismatches: list[ValueMismatch] = []
    for _, row in both.iterrows():
        if len(mismatches) >= cap:
            result.truncated = True
            break
        key_values = {col: _jsonable(row[col]) for col in keys}
        for column in value_cols:
            sql_value = row[f"{column}_sql"]
            pq_value = row[f"{column}_pq"]
            if not _values_equal(sql_value, pq_value, atol, rtol):
                mismatches.append(
                    ValueMismatch(
                        keys=key_values,
                        column=column,
                        sql=_jsonable(sql_value),
                        parquet=_jsonable(pq_value),
                    )
                )
                if len(mismatches) >= cap:
                    result.truncated = True
                    break
    result.value_mismatches = mismatches


def _compare_positional(
    sql_df: pd.DataFrame,
    pq_df: pd.DataFrame,
    shared: list[str],
    atol: float,
    rtol: float,
    cap: int,
    result: CompareResult,
) -> None:
    sql_sorted = sql_df.sort_values(by=shared, kind="mergesort").reset_index(drop=True)
    pq_sorted = pq_df.sort_values(by=shared, kind="mergesort").reset_index(drop=True)
    if len(sql_sorted) != len(pq_sorted):
        result.message = _format_result(result)
        return

    mismatches: list[ValueMismatch] = []
    for index in range(len(sql_sorted)):
        if len(mismatches) >= cap:
            result.truncated = True
            break
        for column in shared:
            sql_value = sql_sorted.at[index, column]
            pq_value = pq_sorted.at[index, column]
            if not _values_equal(sql_value, pq_value, atol, rtol):
                mismatches.append(
                    ValueMismatch(
                        keys={"_row": index},
                        column=column,
                        sql=_jsonable(sql_value),
                        parquet=_jsonable(pq_value),
                    )
                )
                if len(mismatches) >= cap:
                    result.truncated = True
                    break
    result.value_mismatches = mismatches


def _values_equal(left: object, right: object, atol: float, rtol: float) -> bool:
    left_na = _is_na(left)
    right_na = _is_na(right)
    if left_na and right_na:
        return True
    if left_na or right_na:
        return False
    if isinstance(left, Decimal) or isinstance(right, Decimal):
        try:
            return Decimal(str(left)) == Decimal(str(right))
        except Exception:
            return False
    if isinstance(left, (float, int)) and isinstance(right, (float, int)):
        return abs(float(left) - float(right)) <= atol + rtol * abs(float(right))
    if isinstance(left, pd.Timestamp) or isinstance(right, pd.Timestamp):
        return pd.Timestamp(left) == pd.Timestamp(right)
    return left == right


def _is_na(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (ValueError, TypeError):
        return False


def _rows_as_dicts(frame: pd.DataFrame, keys: list[str], cap: int) -> list[dict[str, object]]:
    if frame.empty:
        return []
    return [{col: _jsonable(row[col]) for col in keys} for _, row in frame.head(cap).iterrows()]


def _jsonable(value: object) -> object:
    if _is_na(value):
        return None
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            return str(value)
    return value


def _name(column: str, case_sensitive: bool) -> str:
    return column if case_sensitive else column.strip().lower()


def _format_result(result: CompareResult) -> str:
    if result.passed:
        return (
            f"{result.table}: PASS like-for-like "
            f"({result.row_count_sql} rows, {result.row_count_sql and 'matched' or 'empty'})"
        )
    parts = [f"{result.table}: FAIL"]
    if result.row_count_sql != result.row_count_parquet:
        parts.append(f"row count sql={result.row_count_sql} parquet={result.row_count_parquet}")
    if result.extra_columns_sql:
        parts.append(f"extra SQL columns={result.extra_columns_sql}")
    if result.extra_columns_parquet:
        parts.append(f"extra Parquet columns={result.extra_columns_parquet}")
    if result.duplicate_keys_sql or result.duplicate_keys_parquet:
        parts.append(
            f"duplicate keys sql={result.duplicate_keys_sql} parquet={result.duplicate_keys_parquet}"
        )
    if result.missing_in_parquet:
        parts.append(f"missing in parquet={len(result.missing_in_parquet)}")
    if result.missing_in_sql:
        parts.append(f"missing in sql={len(result.missing_in_sql)}")
    if result.value_mismatches:
        sample = result.value_mismatches[0]
        parts.append(
            f"value mismatches={len(result.value_mismatches)} "
            f"e.g. {sample.keys} {sample.column}: sql={sample.sql!r} parquet={sample.parquet!r}"
        )
    if result.truncated:
        parts.append("(truncated)")
    return "; ".join(parts)
