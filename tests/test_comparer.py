from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pandas as pd

from sql_parquet_compare.comparer import compare_frames
from sql_parquet_compare.config import CompareDefaults, TableMapping


def _defaults(**kwargs) -> CompareDefaults:
    return CompareDefaults(**kwargs)


def _mapping(**kwargs) -> TableMapping:
    values = {"name": "customers", "keys": ["customer_id"]}
    values.update(kwargs)
    return TableMapping(**values)


def _sql_customers() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Customer_Id": [1, 2],
            "Name": ["Ada", "Alan"],
            "Amount": [10.5, 3.0],
            "Is_Active": [True, False],
            "Created_At": [datetime(2024, 1, 1, 10, 0, 0), datetime(2024, 1, 2, 11, 0, 0)],
        }
    )


def test_like_for_like_match_ignores_column_case_and_order():
    sql_df = _sql_customers()
    parquet_df = pd.DataFrame(
        {
            "created_at": [datetime(2024, 1, 1, 10, 0, 0), datetime(2024, 1, 2, 11, 0, 0)],
            "is_active": [1, 0],
            "amount": [Decimal("10.500000"), Decimal("3.000000")],
            "name": ["Ada", "Alan"],
            "customer_id": [1, 2],
        }
    )
    result = compare_frames(
        sql_df,
        parquet_df,
        _mapping(bool_columns=["is_active"]),
        _defaults(),
    )
    assert result.passed, result.message


def test_value_mismatch_reports_key_and_column():
    sql_df = _sql_customers()
    parquet_df = _sql_customers().copy()
    parquet_df.loc[parquet_df["Customer_Id"] == 2, "Name"] = "Turing"
    result = compare_frames(sql_df, parquet_df, _mapping(), _defaults())
    assert not result.passed
    assert result.value_mismatches
    mismatch = result.value_mismatches[0]
    assert mismatch.column == "name"
    assert mismatch.keys == {"customer_id": 2}
    assert mismatch.sql == "Alan"
    assert mismatch.parquet == "Turing"


def test_missing_row_in_parquet():
    sql_df = _sql_customers()
    parquet_df = _sql_customers().iloc[[0]]
    result = compare_frames(sql_df, parquet_df, _mapping(), _defaults())
    assert not result.passed
    assert result.row_count_sql == 2
    assert result.row_count_parquet == 1
    assert result.missing_in_parquet == [{"customer_id": 2}]


def test_schema_mismatch_extra_column():
    sql_df = _sql_customers()
    parquet_df = _sql_customers().copy()
    parquet_df["extra"] = ["x", "y"]
    result = compare_frames(sql_df, parquet_df, _mapping(), _defaults())
    assert not result.passed
    assert result.extra_columns_parquet == ["extra"]


def test_nulls_match_and_null_vs_value_fails():
    sql_df = pd.DataFrame({"id": [1, 2], "notes": [None, "ok"]})
    parquet_df = pd.DataFrame({"id": [1, 2], "notes": [pd.NA, "ok"]})
    result = compare_frames(sql_df, parquet_df, _mapping(name="notes", keys=["id"]), _defaults())
    assert result.passed, result.message

    parquet_df = pd.DataFrame({"id": [1, 2], "notes": ["missing", "ok"]})
    result = compare_frames(sql_df, parquet_df, _mapping(name="notes", keys=["id"]), _defaults())
    assert not result.passed
    assert result.value_mismatches[0].column == "notes"


def test_string_strip_and_date_normalization():
    sql_df = pd.DataFrame(
        {
            "id": [1],
            "name": ["  Ada  "],
            "order_date": [date(2024, 3, 1)],
        }
    )
    parquet_df = pd.DataFrame(
        {
            "id": [1],
            "name": ["Ada"],
            "order_date": [datetime(2024, 3, 1, 0, 0, 0)],
        }
    )
    result = compare_frames(sql_df, parquet_df, _mapping(name="orders", keys=["id"]), _defaults())
    assert result.passed, result.message


def test_decimal_quantization_and_float_like_values():
    sql_df = pd.DataFrame({"id": [1], "amount": [Decimal("19.99001")]})
    parquet_df = pd.DataFrame({"id": [1], "amount": [19.99]})
    result = compare_frames(
        sql_df,
        parquet_df,
        _mapping(name="orders", keys=["id"], decimal_places=4),
        _defaults(decimal_places=4),
    )
    assert result.passed, result.message


def test_duplicate_keys_fail():
    sql_df = pd.DataFrame({"id": [1, 1], "name": ["a", "b"]})
    parquet_df = pd.DataFrame({"id": [1], "name": ["a"]})
    result = compare_frames(sql_df, parquet_df, _mapping(name="dup", keys=["id"]), _defaults())
    assert not result.passed
    assert result.duplicate_keys_sql == 1


def test_positional_compare_without_keys():
    sql_df = pd.DataFrame({"name": ["b", "a"], "qty": [2, 1]})
    parquet_df = pd.DataFrame({"name": ["a", "b"], "qty": [1, 2]})
    result = compare_frames(sql_df, parquet_df, _mapping(name="sorted", keys=[]), _defaults())
    assert result.passed, result.message


def test_exclude_columns():
    sql_df = _sql_customers()
    parquet_df = _sql_customers().copy()
    parquet_df["Name"] = ["changed", "changed"]
    result = compare_frames(
        sql_df,
        parquet_df,
        _mapping(exclude_columns=["name"]),
        _defaults(),
    )
    assert result.passed, result.message
