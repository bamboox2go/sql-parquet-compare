from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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
    args = parser.parse_args(argv)

    env_path = Path(args.env) if args.env and Path(args.env).exists() else None
    config = load_config(args.config, env_file=env_path)
    results = run_comparisons(config, table_names=args.tables, fail_fast=args.fail_fast)

    if args.json:
        print(json.dumps([_result_to_dict(item) for item in results], indent=2))
    else:
        for item in results:
            print(item.message)

    return 0 if all(item.passed for item in results) else 1


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
