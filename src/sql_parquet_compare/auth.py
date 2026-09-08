from __future__ import annotations

import struct

from azure.identity import AzureCliCredential, CredentialUnavailableError, DefaultAzureCredential

SQL_AAD_SCOPE = "https://database.windows.net/.default"
STORAGE_AAD_SCOPE = "https://storage.azure.com/.default"
SQL_COPT_SS_ACCESS_TOKEN = 1256

_CLI_MODES = {"azure_cli", "az", "cli", "aad"}
_DEFAULT_MODES = {"azure", "azure_default", "default"}

LOGIN_HELP = (
    "Azure CLI is not logged in or cannot issue a token. Run:\n"
    "  az login\n"
    "  az account set --subscription <subscription-id-or-name>\n"
    "Then retry. The signed-in identity needs access to the SQL server and storage account."
)


def is_azure_cli_auth(mode: str | None) -> bool:
    return (mode or "").strip().lower() in _CLI_MODES


def is_azure_identity_auth(mode: str | None) -> bool:
    return is_azure_cli_auth(mode) or (mode or "").strip().lower() in _DEFAULT_MODES


def azure_credential(mode: str, tenant_id: str | None = None):
    """Return AzureCliCredential for az login, or DefaultAzureCredential for the full chain."""
    tenant = (tenant_id or "").strip() or None
    if is_azure_cli_auth(mode):
        return AzureCliCredential(tenant_id=tenant) if tenant else AzureCliCredential()
    if (mode or "").strip().lower() in _DEFAULT_MODES:
        kwargs: dict = {"exclude_interactive_browser_credential": True}
        if tenant:
            kwargs["tenant_id"] = tenant
        return DefaultAzureCredential(**kwargs)
    raise ValueError(f"Unsupported Azure auth mode '{mode}'. Use azure_cli or azure_default.")


def get_token(mode: str, scope: str, tenant_id: str | None = None) -> str:
    try:
        return azure_credential(mode, tenant_id).get_token(scope).token
    except CredentialUnavailableError as exc:
        raise RuntimeError(LOGIN_HELP) from exc


def sql_access_token_struct(token: str) -> bytes:
    """Pack an Entra access token for ODBC SQL_COPT_SS_ACCESS_TOKEN."""
    token_bytes = token.encode("utf-16-le")
    return struct.pack("<I", len(token_bytes)) + token_bytes


def sql_access_token_from_cli(mode: str, tenant_id: str | None = None) -> bytes:
    return sql_access_token_struct(get_token(mode, SQL_AAD_SCOPE, tenant_id))


def odbc_sql_connection_string(
    host: str,
    port: int,
    database: str,
    driver: str,
    encrypt: str = "yes",
    trust_server_certificate: str | None = None,
) -> str:
    encrypt_value = (encrypt or "yes").strip() or "yes"
    if trust_server_certificate:
        trust = trust_server_certificate
    else:
        trust = "yes" if encrypt_value.lower() in {"no", "optional"} else "no"
    return (
        f"DRIVER={{{driver}}};"
        f"SERVER=tcp:{host},{int(port)};"
        f"DATABASE={database};"
        f"Encrypt={encrypt_value};"
        f"TrustServerCertificate={trust};"
    )
