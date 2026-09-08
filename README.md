# SQL Server vs Parquet like-for-like tests

Python test project that reads SQL Server tables and compares them with Parquet files in Azure Storage (or the local Azurite emulator).

Comparison is **like-for-like**: same columns, same row keys, same values after type normalisation (nulls, decimals, datetimes, BIT vs 0/1, string trim, case-insensitive column names).

## Layout

```
config/tables.yaml          # table → parquet mapping
src/sql_parquet_compare/    # readers, normaliser, comparer, CLI
tests/                      # unit tests (no Docker)
tests/integration/          # live SQL Server + Azurite
scripts/seed_local.py       # sample tables + parquet
docker-compose.yml          # SQL Edge + Azurite
```

## Setup

```bash
cd ~/Projects/sql-parquet-compare
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Start the local stack and seed matching SQL + Parquet data:

```bash
docker compose up -d
python scripts/wait_for_services.py
python scripts/seed_local.py
```

## Run tests

```bash
# unit tests only
pytest tests --ignore=tests/integration

# everything, including SQL Server + Azurite
pytest
```

Integration tests skip automatically if Docker services are not running.

## Compare tables

```bash
sql-parquet-compare -c config/tables.yaml
sql-parquet-compare -c config/tables.yaml --table customers --json
```

Exit code `0` means every mapped table matched. `1` means at least one mismatch.

## Point at real SQL Server and a storage account

Edit `.env`:

```bash
SQL_DIALECT=pyodbc
SQL_HOST=<server>.database.windows.net
SQL_PORT=1433
SQL_DATABASE=<db>
SQL_USERNAME=<user>
SQL_PASSWORD=<password>
SQL_ENCRYPT=yes

# connection string, or leave empty and set AZURE_STORAGE_ACCOUNT_URL for Azure AD
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net
AZURE_STORAGE_CONTAINER=parquet
```

Install the ODBC extra for Azure SQL / encrypted SQL Server:

```bash
pip install -e ".[odbc]"
```

You also need [ODBC Driver 18 for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server).

Then map tables in `config/tables.yaml`:

```yaml
tables:
  - name: customers
    sql: dbo.customers
    parquet: bronze/customers/          # all .parquet blobs under this prefix
    keys: [customer_id]
    bool_columns: [is_active]
    exclude_columns: [loaded_at]        # optional
    # sql_query: SELECT * FROM dbo.customers WHERE is_active = 1
```

`parquet` can be a single blob (`customers/customers.parquet`) or a prefix ending in `/` for a folder of parts.

## What “like-for-like” checks

- Column sets (after optional include/exclude)
- Row counts
- Missing/extra keys
- Duplicate keys
- Cell values, with:
  - null equals null
  - decimals quantized (default 6 places; set `decimal_places` per table)
  - datetimes compared in UTC at microsecond precision
  - strings stripped
  - BIT / parquet 0-1 via `bool_columns`

## Intel Mac / full SQL Server image

`docker-compose.yml` uses SQL Server 2022 (`linux/amd64`). That image runs under emulation on Apple Silicon and natively on Intel.
