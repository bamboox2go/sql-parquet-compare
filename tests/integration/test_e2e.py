from __future__ import annotations

import socket
from pathlib import Path

import pytest

from sql_parquet_compare.comparer import compare_frames
from sql_parquet_compare.config import load_config
from sql_parquet_compare.parquet_reader import read_parquet
from sql_parquet_compare.sql_reader import create_sql_engine, read_sql_table

ROOT = Path(__file__).resolve().parents[2]


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _services_up() -> bool:
    env = ROOT / ".env"
    config_path = ROOT / "config" / "tables.yaml"
    if not config_path.exists():
        return False
    try:
        config = load_config(config_path, env_file=env if env.exists() else ROOT / ".env.example")
        return _port_open(config.sql.host, int(config.sql.port)) and _port_open("127.0.0.1", 10000)
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _services_up(),
    reason="Start local services with: docker compose up -d && python scripts/seed_local.py",
)


@pytest.fixture(scope="module")
def app_config():
    env = ROOT / ".env"
    return load_config(ROOT / "config" / "tables.yaml", env_file=env if env.exists() else ROOT / ".env.example")


@pytest.fixture(scope="module")
def engine(app_config):
    return create_sql_engine(app_config.sql)


@pytest.mark.integration
@pytest.mark.parametrize("table_name", ["customers", "orders", "order_lines"])
def test_sql_matches_parquet_like_for_like(app_config, engine, table_name):
    mapping = app_config.table(table_name)
    sql_df = read_sql_table(engine, mapping)
    parquet_df = read_parquet(app_config.storage, mapping.parquet)
    result = compare_frames(sql_df, parquet_df, mapping, app_config.defaults)
    assert result.passed, result.message


@pytest.mark.integration
def test_detects_parquet_drift(app_config, engine):
    mapping = app_config.table("customers")
    sql_df = read_sql_table(engine, mapping)
    parquet_df = read_parquet(app_config.storage, mapping.parquet)
    drifted = parquet_df.copy()
    name_col = "name" if "name" in drifted.columns else "Name"
    drifted.loc[drifted.index[0], name_col] = "NOT-THE-SAME"
    result = compare_frames(sql_df, drifted, mapping, app_config.defaults)
    assert not result.passed
    assert result.value_mismatches
