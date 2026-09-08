from __future__ import annotations

from sql_parquet_compare.config import load_config
from sql_parquet_compare.sql_reader import split_table_name


def test_env_expansion_and_table_mapping(tmp_path, monkeypatch):
    monkeypatch.setenv("SQL_HOST", "sql.example")
    monkeypatch.setenv("SQL_PASSWORD", "secret")
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
    config_path = tmp_path / "tables.yaml"
    config_path.write_text(
        """
sql:
  host: ${SQL_HOST}
  password: ${SQL_PASSWORD}
  database: ${SQL_DATABASE:-CompareTest}
storage:
  connection_string: ${AZURE_STORAGE_CONNECTION_STRING}
  container: parquet
tables:
  - name: customers
    sql: dbo.customers
    parquet: customers/customers.parquet
    keys: [customer_id]
    bool_columns: [is_active]
""".strip(),
        encoding="utf-8",
    )
    config = load_config(config_path)
    assert config.sql.host == "sql.example"
    assert config.sql.password == "secret"
    assert config.sql.database == "CompareTest"
    assert config.tables[0].bool_columns == ["is_active"]


def test_split_table_name():
    assert split_table_name("dbo.customers") == ("dbo", "customers")
    assert split_table_name("[sales].[Order Details]") == ("sales", "Order Details")
    assert split_table_name("customers") == ("dbo", "customers")
