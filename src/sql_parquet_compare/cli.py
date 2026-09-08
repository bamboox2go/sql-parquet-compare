from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sql_parquet_compare.auth import LOGIN_HELP, STORAGE_AAD_SCOPE, SQL_AAD_SCOPE, get_token, is_azure_identity_auth
from sql_parquet_compare.comparer import CompareResult, compare_frames
from sql_parquet_compare.config import AppConfig, load_config
from sql_parquet_compare.parquet_reader import read_parquet
from sql_parquet_compare.sql_reader import create_sql_engine, read_sql_table


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare SQL Server tables to Parquet files in Azure Storage (like-for-like)."
    )
    parser.add_argument("-c", "--config", default="config/tables.yaml", help="YAML table mapping")
    parser.add_argument("--env", default=".env", help="dotenv file (optional)")
    parser.add_argument("--table", action="append", dest="tables", help="Limit to one or more table names")
    parser.add_argument("--json", action="store_true", help="Print JSON results")
    parser.add_argument("--fail-fast", action="store_true", help="Stop on the first mismatch")
    parser.add_argument(
        "--check-auth",
        action="store_true",
        help="Verify Azure CLI tokens for SQL and Storage, then exit",
    )
    args = parser.parse_args(argv)

    env_path = Path(args.env) if args.env and Path(args.env).exists() else None
    config = load_config(args.config, env_file=env_path)

    if args.check_auth:
        return check_auth(config)

    results = run_comparisons(config, table_names=args.tables, fail_fast=args.fail_fast)

    if args.json:
        print(json.dumps([_result_to_dict(item) for item in results], indent=2))
    else:
        for item in results:
            print(item.message)

    return 0 if all(item.passed for item in results) else 1


def check_auth(config: AppConfig) -> int:
    ok = True
    if is_azure_identity_auth(config.sql.auth):
        try:
            get_token(config.sql.auth, SQL_AAD_SCOPE, config.sql.tenant_id or None)
            print(f"SQL Azure CLI token: OK ({config.sql.host}/{config.sql.database})")
        except Exception as exc:
            ok = False
            print(f"SQL Azure CLI token: FAIL\n{exc}", file=sys.stderr)
    else:
        print(f"SQL auth: {config.sql.auth} (username/password, not Azure CLI)")

    if is_azure_identity_auth(config.storage.auth):
        try:
            get_token(config.storage.auth, STORAGE_AAD_SCOPE, config.storage.tenant_id or None)
            print(f"Storage Azure CLI token: OK ({config.storage.blob_account_url() or config.storage.account_name})")
        except Exception as exc:
            ok = False
            print(f"Storage Azure CLI token: FAIL\n{exc}", file=sys.stderr)
    else:
        print(f"Storage auth: {config.storage.auth} (connection string / Azurite, not Azure CLI)")

    if not ok:
        print(LOGIN_HELP, file=sys.stderr)
        return 1
    return 0


def run_comparisons(
    config: AppConfig,
    table_names: list[str] | None = None,
    fail_fast: bool = False,
) -> list[CompareResult]:
    mappings = config.tables
    if table_names:
        mappings = [config.table(name) for name in table_names]
    if not mappings:
        raise SystemExit("No tables configured")

    if is_azure_identity_auth(config.sql.auth) or is_azure_identity_auth(config.storage.auth):
        print(
            f"Auth: SQL={config.sql.auth} Storage={config.storage.auth} "
            "(using current `az login` session)",
            file=sys.stderr,
        )

    engine = create_sql_engine(config.sql)
    results: list[CompareResult] = []
    with engine.connect() as _:
        pass
    for mapping in mappings:
        sql_df = read_sql_table(engine, mapping)
        parquet_df = read_parquet(config.storage, mapping.parquet)
        result = compare_frames(sql_df, parquet_df, mapping, config.defaults)
        results.append(result)
        if fail_fast and not result.passed:
            break
    return results


def _result_to_dict(result: CompareResult) -> dict:
    return {
        "table": result.table,
        "passed": result.passed,
        "row_count_sql": result.row_count_sql,
        "row_count_parquet": result.row_count_parquet,
        "extra_columns_sql": result.extra_columns_sql,
        "extra_columns_parquet": result.extra_columns_parquet,
        "missing_in_parquet": result.missing_in_parquet,
        "missing_in_sql": result.missing_in_sql,
        "duplicate_keys_sql": result.duplicate_keys_sql,
        "duplicate_keys_parquet": result.duplicate_keys_parquet,
        "value_mismatches": [
            {"keys": item.keys, "column": item.column, "sql": item.sql, "parquet": item.parquet}
            for item in result.value_mismatches
        ],
        "truncated": result.truncated,
        "message": result.message,
    }


if __name__ == "__main__":
    sys.exit(main())
