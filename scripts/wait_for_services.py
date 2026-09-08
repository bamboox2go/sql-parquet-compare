#!/usr/bin/env python3
"""Wait until local SQL Server and Azurite accept connections."""

from __future__ import annotations

import argparse
import socket
import sys
import time


def port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for(host: str, port: int, label: str, attempts: int, delay: float) -> None:
    for attempt in range(1, attempts + 1):
        if port_open(host, port):
            print(f"{label} is up on {host}:{port}")
            return
        print(f"waiting for {label} ({attempt}/{attempts})")
        time.sleep(delay)
    raise SystemExit(f"{label} did not become ready on {host}:{port}")


def wait_for_sql(host: str, port: int, user: str, password: str, attempts: int, delay: float) -> None:
    try:
        import pymssql
    except ImportError as exc:
        raise SystemExit("pymssql is required. Install with: pip install -e '.[dev]'") from exc

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            conn = pymssql.connect(
                server=host,
                port=port,
                user=user,
                password=password,
                login_timeout=5,
            )
            conn.close()
            print(f"SQL Server accepted login on {host}:{port}")
            return
        except Exception as exc:  # noqa: BLE001 - wait loop
            last_error = exc
            print(f"waiting for SQL login ({attempt}/{attempts}): {exc}")
            time.sleep(delay)
    raise SystemExit(f"SQL Server did not accept login: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sql-host", default="127.0.0.1")
    parser.add_argument("--sql-port", type=int, default=14333)
    parser.add_argument("--sql-user", default="sa")
    parser.add_argument("--sql-password", default="SqlParquet_1")
    parser.add_argument("--azurite-host", default="127.0.0.1")
    parser.add_argument("--azurite-port", type=int, default=10000)
    parser.add_argument("--attempts", type=int, default=40)
    parser.add_argument("--delay", type=float, default=2.0)
    args = parser.parse_args()

    wait_for(args.azurite_host, args.azurite_port, "Azurite", args.attempts, args.delay)
    wait_for(args.sql_host, args.sql_port, "SQL Server port", args.attempts, args.delay)
    wait_for_sql(args.sql_host, args.sql_port, args.sql_user, args.sql_password, args.attempts, args.delay)
    return 0


if __name__ == "__main__":
    sys.exit(main())
