from __future__ import annotations

import struct
from types import SimpleNamespace

import pytest

from sql_parquet_compare.auth import (
    LOGIN_HELP,
    SQL_AAD_SCOPE,
    STORAGE_AAD_SCOPE,
    azure_credential,
    get_token,
    is_azure_identity_auth,
    odbc_sql_connection_string,
    sql_access_token_struct,
)
from sql_parquet_compare.config import SqlConfig, StorageConfig, load_config
from sql_parquet_compare.parquet_reader import _blob_service


def test_azure_cli_modes():
    assert is_azure_identity_auth("azure_cli")
    assert is_azure_identity_auth("az")
    assert is_azure_identity_auth("azure_default")
    assert not is_azure_identity_auth("sql")
    assert not is_azure_identity_auth("connection_string")


def test_sql_access_token_struct_is_utf16le_with_length_prefix():
    packed = sql_access_token_struct("abc")
    length = struct.unpack_from("<I", packed)[0]
    token_bytes = packed[4:]
    assert length == len(token_bytes)
    assert token_bytes == "abc".encode("utf-16-le")


def test_odbc_connection_string_for_azure_sql():
    conn = odbc_sql_connection_string(
        host="myserver.database.windows.net",
        port=1433,
        database="appdb",
        driver="ODBC Driver 18 for SQL Server",
        encrypt="yes",
    )
    assert "SERVER=tcp:myserver.database.windows.net,1433" in conn
    assert "DATABASE=appdb" in conn
    assert "Encrypt=yes" in conn
    assert "TrustServerCertificate=no" in conn


def test_get_token_uses_azure_cli_credential(monkeypatch):
    seen = {}

    class FakeCredential:
        def get_token(self, scope):
            seen["scope"] = scope
            return SimpleNamespace(token="cli-token")

    monkeypatch.setattr("sql_parquet_compare.auth.AzureCliCredential", lambda **kwargs: FakeCredential())
    token = get_token("azure_cli", SQL_AAD_SCOPE)
    assert token == "cli-token"
    assert seen["scope"] == SQL_AAD_SCOPE
    assert isinstance(azure_credential("azure_cli"), FakeCredential)


def test_get_token_explains_missing_az_login(monkeypatch):
    from azure.identity import CredentialUnavailableError

    class FakeCredential:
        def get_token(self, scope):
            raise CredentialUnavailableError("az not logged in")

    monkeypatch.setattr("sql_parquet_compare.auth.AzureCliCredential", lambda **kwargs: FakeCredential())
    with pytest.raises(RuntimeError, match="az login"):
        get_token("azure_cli", STORAGE_AAD_SCOPE)
    assert "az login" in LOGIN_HELP


def test_config_loads_azure_cli_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("SQL_AUTH", "azure_cli")
    monkeypatch.setenv("STORAGE_AUTH", "azure_cli")
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT", "myaccount")
    monkeypatch.setenv("AZURE_TENANT_ID", "tenant-1")
    config_path = tmp_path / "tables.yaml"
    config_path.write_text(
        """
sql:
  auth: ${SQL_AUTH}
  host: myserver.database.windows.net
  database: appdb
  tenant_id: ${AZURE_TENANT_ID}
storage:
  auth: ${STORAGE_AUTH}
  account_name: ${AZURE_STORAGE_ACCOUNT}
  tenant_id: ${AZURE_TENANT_ID}
  container: parquet
tables:
  - name: customers
    sql: dbo.customers
    parquet: customers.parquet
    keys: [id]
""".strip(),
        encoding="utf-8",
    )
    config = load_config(config_path)
    assert config.sql.auth == "azure_cli"
    assert config.sql.tenant_id == "tenant-1"
    assert config.storage.auth == "azure_cli"
    assert config.storage.blob_account_url() == "https://myaccount.blob.core.windows.net"


def test_storage_azure_cli_ignores_connection_string(monkeypatch):
    created = {}

    class FakeClient:
        def __init__(self, account_url, credential):
            created["url"] = account_url
            created["credential"] = credential

    monkeypatch.setattr("sql_parquet_compare.parquet_reader.BlobServiceClient", FakeClient)
    monkeypatch.setattr(
        "sql_parquet_compare.parquet_reader._cli_credential",
        lambda mode, tenant_id: f"cred:{mode}:{tenant_id}",
    )
    client = _blob_service(
        StorageConfig(
            auth="azure_cli",
            account_name="lake",
            connection_string="UseDevelopmentStorage=true",
            tenant_id="t1",
        )
    )
    assert isinstance(client, FakeClient)
    assert created["url"] == "https://lake.blob.core.windows.net"
    assert created["credential"] == "cred:azure_cli:t1"


def test_azure_cli_sql_connect_passes_access_token(monkeypatch):
    seen = {}

    class FakeToken:
        token = "aad-token"

    monkeypatch.setattr(
        "sql_parquet_compare.auth.AzureCliCredential",
        lambda **kwargs: SimpleNamespace(get_token=lambda scope: FakeToken()),
    )

    def fake_connect(conn_str, attrs_before=None):
        seen["conn_str"] = conn_str
        seen["attrs"] = attrs_before
        return SimpleNamespace()

    fake_pyodbc = SimpleNamespace(connect=fake_connect)
    monkeypatch.setitem(__import__("sys").modules, "pyodbc", fake_pyodbc)

    from sql_parquet_compare.sql_reader import connect_azure_sql

    connect_azure_sql(
        SqlConfig(
            auth="azure_cli",
            host="myserver.database.windows.net",
            port=1433,
            database="appdb",
            encrypt="yes",
            odbc_driver="ODBC Driver 18 for SQL Server",
        )
    )
    assert "myserver.database.windows.net" in seen["conn_str"]
    assert 1256 in seen["attrs"]
    packed = seen["attrs"][1256]
    assert packed[4:] == "aad-token".encode("utf-16-le")
