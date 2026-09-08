from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

_ENV_PATTERN = re.compile(r"\$\{([^}:]+)(?::-([^}]*))?\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def _expand_env_value(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        braced, default, bare = match.group(1), match.group(2), match.group(3)
        key = braced or bare
        if key in os.environ:
            return os.environ[key]
        if default is not None:
            return default
        return ""

    return _ENV_PATTERN.sub(repl, value)


def _expand(obj: Any) -> Any:
    if isinstance(obj, str):
        return _expand_env_value(obj)
    if isinstance(obj, list):
        return [_expand(item) for item in obj]
    if isinstance(obj, dict):
        return {key: _expand(value) for key, value in obj.items()}
    return obj


@dataclass
class SqlConfig:
    dialect: str = "pymssql"
    auth: str = "sql"
    host: str = "127.0.0.1"
    port: int = 1433
    database: str = "CompareTest"
    username: str = "sa"
    password: str = ""
    encrypt: str = "no"
    trust_server_certificate: str = ""
    odbc_driver: str = "ODBC Driver 18 for SQL Server"
    odbc_connect: str | None = None
    tenant_id: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SqlConfig:
        data = data or {}
        port = data.get("port", cls.port)
        return cls(
            dialect=str(data.get("dialect", cls.dialect)),
            auth=str(data.get("auth", cls.auth) or cls.auth).lower(),
            host=str(data.get("host", cls.host)),
            port=int(port) if str(port) else cls.port,
            database=str(data.get("database", cls.database)),
            username=str(data.get("username", cls.username)),
            password=str(data.get("password", cls.password)),
            encrypt=str(data.get("encrypt", cls.encrypt)),
            trust_server_certificate=str(data.get("trust_server_certificate", "") or ""),
            odbc_driver=str(data.get("odbc_driver", cls.odbc_driver)),
            odbc_connect=data.get("odbc_connect"),
            tenant_id=str(data.get("tenant_id", "") or ""),
        )


@dataclass
class StorageConfig:
    backend: str = "azure"
    auth: str = "connection_string"
    connection_string: str = ""
    account_url: str = ""
    account_name: str = ""
    container: str = "parquet"
    local_root: str = ""
    tenant_id: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> StorageConfig:
        data = data or {}
        return cls(
            backend=str(data.get("backend", cls.backend)).lower(),
            auth=str(data.get("auth", cls.auth) or cls.auth).lower(),
            connection_string=str(data.get("connection_string", "") or ""),
            account_url=str(data.get("account_url", "") or ""),
            account_name=str(data.get("account_name", "") or ""),
            container=str(data.get("container", cls.container)),
            local_root=str(data.get("local_root", "") or ""),
            tenant_id=str(data.get("tenant_id", "") or ""),
        )

    def blob_account_url(self) -> str:
        if self.account_url:
            return self.account_url.rstrip("/")
        if self.account_name:
            return f"https://{self.account_name}.blob.core.windows.net"
        return ""


@dataclass
class TableMapping:
    name: str
    sql: str | None = None
    sql_query: str | None = None
    parquet: str = ""
    keys: list[str] = field(default_factory=list)
    columns: list[str] | None = None
    exclude_columns: list[str] = field(default_factory=list)
    bool_columns: list[str] = field(default_factory=list)
    float_atol: float | None = None
    float_rtol: float | None = None
    decimal_places: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], defaults: dict[str, Any]) -> TableMapping:
        if not data.get("name"):
            raise ValueError("Each table mapping needs a name")
        return cls(
            name=str(data["name"]),
            sql=data.get("sql"),
            sql_query=data.get("sql_query"),
            parquet=str(data.get("parquet", "")),
            keys=list(data.get("keys") or []),
            columns=list(data["columns"]) if data.get("columns") else None,
            exclude_columns=list(data.get("exclude_columns") or []),
            bool_columns=list(data.get("bool_columns") or []),
            float_atol=_maybe_float(data.get("float_atol", defaults.get("float_atol"))),
            float_rtol=_maybe_float(data.get("float_rtol", defaults.get("float_rtol"))),
            decimal_places=_maybe_int(data.get("decimal_places", defaults.get("decimal_places"))),
        )


@dataclass
class CompareDefaults:
    float_atol: float = 1e-6
    float_rtol: float = 1e-9
    decimal_places: int = 6
    datetime_unit: str = "us"
    strip_strings: bool = True
    case_sensitive_columns: bool = False
    max_mismatches: int = 50

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CompareDefaults:
        data = data or {}
        return cls(
            float_atol=float(data.get("float_atol", cls.float_atol)),
            float_rtol=float(data.get("float_rtol", cls.float_rtol)),
            decimal_places=int(data.get("decimal_places", cls.decimal_places)),
            datetime_unit=str(data.get("datetime_unit", cls.datetime_unit)),
            strip_strings=bool(data.get("strip_strings", cls.strip_strings)),
            case_sensitive_columns=bool(data.get("case_sensitive_columns", cls.case_sensitive_columns)),
            max_mismatches=int(data.get("max_mismatches", cls.max_mismatches)),
        )


@dataclass
class AppConfig:
    sql: SqlConfig
    storage: StorageConfig
    defaults: CompareDefaults
    tables: list[TableMapping]

    def table(self, name: str) -> TableMapping:
        for mapping in self.tables:
            if mapping.name == name:
                return mapping
        known = ", ".join(m.name for m in self.tables) or "(none)"
        raise KeyError(f"Unknown table '{name}'. Known: {known}")


def _maybe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _maybe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def load_config(path: str | Path, env_file: str | Path | None = None) -> AppConfig:
    """Load YAML config, expanding ${VAR} and ${VAR:-default} from the environment."""
    if env_file:
        load_dotenv(env_file, override=False)
    else:
        load_dotenv(override=False)

    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    raw = _expand(raw)
    defaults = CompareDefaults.from_dict(raw.get("defaults"))
    tables = [TableMapping.from_dict(item, raw.get("defaults") or {}) for item in raw.get("tables") or []]
    return AppConfig(
        sql=SqlConfig.from_dict(raw.get("sql")),
        storage=StorageConfig.from_dict(raw.get("storage")),
        defaults=defaults,
        tables=tables,
    )
