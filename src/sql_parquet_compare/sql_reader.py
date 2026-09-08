from __future__ import annotations

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL

from sql_parquet_compare.config import SqlConfig


def build_sqlalchemy_url(cfg: SqlConfig) -> URL | str:
    if cfg.odbc_connect:
        return URL.create("mssql+pyodbc", query={"odbc_connect": cfg.odbc_connect})

    dialect = cfg.dialect.lower()
    if dialect in {"pymssql", "mssql+pymssql"}:
        return URL.create(
            "mssql+pymssql",
            username=cfg.username,
            password=cfg.password,
            host=cfg.host,
            port=int(cfg.port),
            database=cfg.database,
        )
    if dialect in {"pyodbc", "mssql+pyodbc", "odbc"}:
        encrypt = cfg.encrypt or "yes"
        return URL.create(
            "mssql+pyodbc",
            username=cfg.username,
            password=cfg.password,
            host=cfg.host,
            port=int(cfg.port),
            database=cfg.database,
            query={
                "driver": cfg.odbc_driver,
                "Encrypt": encrypt,
                "TrustServerCertificate": "yes" if encrypt.lower() in {"no", "optional"} else "no",
            },
        )
    raise ValueError(f"Unsupported SQL dialect '{cfg.dialect}'. Use pymssql or pyodbc.")


def create_sql_engine(cfg: SqlConfig) -> Engine:
    return create_engine(build_sqlalchemy_url(cfg), pool_pre_ping=True)


def split_table_name(name: str, default_schema: str = "dbo") -> tuple[str, str]:
    cleaned = name.replace("[", "").replace("]", "").strip()
    if "." in cleaned:
        schema, table = cleaned.split(".", 1)
        return schema, table
    return default_schema, cleaned


def read_sql_table(engine, mapping, default_schema: str = "dbo") -> pd.DataFrame:
    query = mapping.sql_query or _select_star(mapping.sql or mapping.name, default_schema)
    return pd.read_sql_query(query, engine)


def _select_star(qualified: str, default_schema: str) -> str:
    schema, table = split_table_name(qualified, default_schema)
    return f"SELECT * FROM [{schema}].[{table}]"
