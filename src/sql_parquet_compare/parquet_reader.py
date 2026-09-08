from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient, ContainerClient

from sql_parquet_compare.auth import (
    LOGIN_HELP,
    STORAGE_AAD_SCOPE,
    azure_credential,
    is_azure_identity_auth,
)
from sql_parquet_compare.config import StorageConfig


def read_parquet(storage: StorageConfig, relative_path: str) -> pd.DataFrame:
    if not relative_path:
        raise ValueError("Parquet path is empty")
    if storage.backend == "local":
        return _read_local(storage.local_root, relative_path)
    if storage.backend in {"azure", "blob", "adls"}:
        return _read_azure(storage, relative_path)
    raise ValueError(f"Unsupported storage backend '{storage.backend}'")


def _read_local(root: str, relative_path: str) -> pd.DataFrame:
    base = Path(root)
    target = base / relative_path
    if target.is_file():
        return pd.read_parquet(target)
    if target.is_dir():
        files = sorted(target.glob("**/*.parquet"))
        if not files:
            raise FileNotFoundError(f"No parquet files under {target}")
        return pd.concat([pd.read_parquet(path) for path in files], ignore_index=True)
    files = sorted(base.glob(relative_path))
    parquet_files = [path for path in files if path.suffix == ".parquet"]
    if not parquet_files:
        raise FileNotFoundError(f"No parquet files matching {base / relative_path}")
    return pd.concat([pd.read_parquet(path) for path in parquet_files], ignore_index=True)


def _read_azure(storage: StorageConfig, relative_path: str) -> pd.DataFrame:
    container = _container_client(storage)
    prefix = relative_path.lstrip("/").replace("\\", "/")
    blobs = [
        blob.name
        for blob in container.list_blobs(name_starts_with=prefix.rstrip("/") if prefix.endswith("/") else prefix)
        if blob.name.endswith(".parquet")
    ]
    if not blobs and not prefix.endswith("/"):
        blobs = [
            blob.name
            for blob in container.list_blobs(name_starts_with=prefix)
            if blob.name.endswith(".parquet") and (
                blob.name == prefix or blob.name.startswith(prefix.rstrip("/") + "/")
            )
        ]
    if not blobs:
        raise FileNotFoundError(
            f"No parquet blobs in container '{storage.container}' with prefix '{relative_path}'"
        )
    frames = []
    for name in sorted(blobs):
        payload = container.download_blob(name).readall()
        frames.append(pd.read_parquet(BytesIO(payload)))
    return pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]


def write_parquet_azure(storage: StorageConfig, relative_path: str, frame: pd.DataFrame) -> None:
    container = _container_client(storage)
    try:
        container.create_container()
    except ResourceExistsError:
        pass
    buffer = BytesIO()
    frame.to_parquet(buffer, index=False)
    blob_path = relative_path.lstrip("/").replace("\\", "/")
    if blob_path.endswith("/"):
        blob_path = blob_path + "data.parquet"
    container.upload_blob(name=blob_path, data=buffer.getvalue(), overwrite=True)


def _container_client(storage: StorageConfig) -> ContainerClient:
    service = _blob_service(storage)
    return service.get_container_client(storage.container)


def _blob_service(storage: StorageConfig) -> BlobServiceClient:
    if is_azure_identity_auth(storage.auth):
        account_url = storage.blob_account_url()
        if not account_url:
            raise ValueError(
                "Azure CLI storage auth needs AZURE_STORAGE_ACCOUNT_URL or AZURE_STORAGE_ACCOUNT"
            )
        return BlobServiceClient(
            account_url=account_url,
            credential=_cli_credential(storage.auth, storage.tenant_id or None),
        )
    if storage.connection_string:
        conn = storage.connection_string
        if _is_azurite(conn):
            conn = "UseDevelopmentStorage=true"
        return BlobServiceClient.from_connection_string(conn)
    if storage.blob_account_url():
        return BlobServiceClient(
            account_url=storage.blob_account_url(),
            credential=_cli_credential("azure_cli", storage.tenant_id or None),
        )
    raise ValueError(
        "Azure storage needs STORAGE_AUTH=azure_cli with an account URL, or AZURE_STORAGE_CONNECTION_STRING"
    )


def _cli_credential(mode: str, tenant_id: str | None):
    from azure.identity import CredentialUnavailableError

    credential = azure_credential(mode, tenant_id)
    try:
        credential.get_token(STORAGE_AAD_SCOPE)
    except CredentialUnavailableError as exc:
        raise RuntimeError(LOGIN_HELP) from exc
    return credential


def _is_azurite(connection_string: str) -> bool:
    lowered = connection_string.lower()
    return (
        "usedevelopmentstorage=true" in lowered
        or "127.0.0.1" in lowered
        or "localhost" in lowered
        or "devstoreaccount1" in lowered
    )
