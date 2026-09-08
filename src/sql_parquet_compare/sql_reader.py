from __future__ import annotations

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL

from sql_parquet_compare.auth import (
    SQL_COPT_SS_ACCESS_TOKEN,
    is_azure_identity_auth,
    odbc_sql_connection_string,
    sql_access_token_from_cli,
)
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
        trust = cfg.trust_server_certificate or (
            "yes" if encrypt.lower() in {"no", "optional"} else "no"
        )
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
                "TrustServerCertificate": trust,
            },
        )
    raise ValueError(f"Unsupported SQL dialect '{cfg.dialect}'. Use pymssql or pyodbc.")


def create_sql_engine(cfg: SqlConfig) -> Engine:
    if is_azure_identity_auth(cfg.auth):
        return _create_azure_cli_engine(cfg)
    return create_engine(build_sqlalchemy_url(cfg), pool_pre_ping=True)


def connect_azure_sql(cfg: SqlConfig):
    """Open a pyodbc connection using an Azure CLI (or DefaultAzureCredential) access token."""
    try:
        import pyodbc
    except ImportError as exc:
        raise RuntimeError(
            "Azure CLI SQL auth requires pyodbc and ODBC Driver 18. "
            "Install with: pip install -e '.[odbc]'"
        ) from exc

    conn_str = odbc_sql_connection_string(
        host=cfg.host,
        port=int(cfg.port),
        database=cfg.database,
        driver=cfg.odbc_driver,
        encrypt=cfg.encrypt or "yes",
        trust_server_certificate=cfg.trust_server_certificate or None,
    )
    token = sql_access_token_from_cli(cfg.auth, cfg.tenant_id or None)
    return pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token})


def _create_azure_cli_engine(cfg: SqlConfig) -> Engine:
    try:
        import pyodbc  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Azure CLI SQL auth requires pyodbc and ODBC Driver 18. "
            "Install with: pip install -e '.[odbc]'"
        ) from exc
    return create_engine("mssql+pyodbc://", creator=lambda: connect_azure_sql(cfg), pool_pre_ping=True)


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
