from __future__ import annotations

from datetime import datetime

import pandas as pd

from sql_parquet_compare.normalize import normalize_frame


def test_column_names_are_lowercased_and_strings_stripped():
    frame = pd.DataFrame({" Customer_ID ": [1], "Name": ["  Ada  "]})
    out = normalize_frame(frame)
    assert list(out.columns) == ["customer_id", "name"]
    assert out.loc[0, "name"] == "Ada"


def test_bool_columns_accept_ints_and_bytes():
    frame = pd.DataFrame({"id": [1, 2], "is_active": [1, b"\x00"]})
    out = normalize_frame(frame, bool_columns=["is_active"])
    assert bool(out.loc[0, "is_active"]) is True
    assert bool(out.loc[1, "is_active"]) is False


def test_datetime_timezone_normalized_to_naive_utc():
    frame = pd.DataFrame(
        {
                "ts": pd.to_datetime(
                    ["2024-01-01T10:00:00+00:00", "2024-01-01T12:00:00+02:00"],
                    utc=True,
                ),
        }
    )
    out = normalize_frame(frame)
    assert out.loc[0, "ts"] == pd.Timestamp("2024-01-01 10:00:00")
    assert out.loc[1, "ts"] == pd.Timestamp("2024-01-01 10:00:00")


def test_python_datetime_objects_are_normalized():
    frame = pd.DataFrame({"created_at": [datetime(2024, 1, 15, 9, 30, 0)]})
    out = normalize_frame(frame)
    assert out.loc[0, "created_at"] == pd.Timestamp("2024-01-15 09:30:00")
