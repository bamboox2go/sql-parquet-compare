#!/usr/bin/env python3
"""Create sample SQL Server tables and matching Parquet blobs in Azurite."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pandas as pd
import pymssql
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sql_parquet_compare.config import load_config
from sql_parquet_compare.parquet_reader import write_parquet_azure
from sql_parquet_compare.sample_data import CUSTOMERS, DDL, ORDER_LINES, ORDERS


def _ensure_env() -> Path:
    env_path = ROOT / ".env"
    example = ROOT / ".env.example"
    if not env_path.exists() and example.exists():
        shutil.copy(example, env_path)
        print(f"created {env_path} from .env.example")
    return env_path


def _connect_master(host: str, port: int, user: str, password: str):
    return pymssql.connect(
        server=host,
        port=port,
        user=user,
        password=password,
        database="master",
        autocommit=True,
        login_timeout=10,
    )


def seed_sql(host: str, port: int, user: str, password: str, database: str) -> None:
    conn = _connect_master(host, port, user, password)
    cursor = conn.cursor()
    cursor.execute(
        f"IF DB_ID('{database}') IS NULL CREATE DATABASE [{database}];"
    )
    cursor.close()
    conn.close()

    conn = pymssql.connect(
        server=host,
        port=port,
        user=user,
        password=password,
        database=database,
        autocommit=True,
        login_timeout=10,
    )
    cursor = conn.cursor()
    for statement in DDL:
        cursor.execute(statement)

    cursor.executemany(
        "INSERT INTO dbo.customers (customer_id, name, email, created_at, is_active) "
        "VALUES (%s, %s, %s, %s, %s)",
        [
            (row["customer_id"], row["name"], row["email"], row["created_at"], int(row["is_active"]))
            for row in CUSTOMERS
        ],
    )
    cursor.executemany(
        "INSERT INTO dbo.orders (order_id, customer_id, amount, order_date, notes) "
        "VALUES (%s, %s, %s, %s, %s)",
        [
            (row["order_id"], row["customer_id"], row["amount"], row["order_date"], row["notes"])
            for row in ORDERS
        ],
    )
    cursor.executemany(
        "INSERT INTO dbo.order_lines (order_id, line_no, sku, qty, unit_price) "
        "VALUES (%s, %s, %s, %s, %s)",
        [
            (row["order_id"], row["line_no"], row["sku"], row["qty"], row["unit_price"])
            for row in ORDER_LINES
        ],
    )
    cursor.close()
    conn.close()
    print(f"seeded SQL database {database}")


def seed_parquet(config) -> None:
    write_parquet_azure(config.storage, "customers/customers.parquet", pd.DataFrame(CUSTOMERS))
    write_parquet_azure(config.storage, "orders/part-000.parquet", pd.DataFrame(ORDERS))
    write_parquet_azure(config.storage, "order_lines/order_lines.parquet", pd.DataFrame(ORDER_LINES))
    print(f"seeded parquet container '{config.storage.container}'")


def main() -> int:
    env_path = _ensure_env()
    load_dotenv(env_path, override=False)
    config = load_config(ROOT / "config" / "tables.yaml", env_file=env_path)
    seed_sql(
        host=config.sql.host,
        port=int(config.sql.port),
        user=config.sql.username,
        password=config.sql.password,
        database=config.sql.database,
    )
    seed_parquet(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
