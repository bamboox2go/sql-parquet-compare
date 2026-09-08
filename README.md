# SQL Server vs Parquet like-for-like tests

Python test project that reads SQL Server tables and compares them with Parquet files in Azure Storage (or the local Azurite emulator).

Comparison is **like-for-like**: same columns, same row keys, same values after type normalisation (nulls, decimals, datetimes, BIT vs 0/1, string trim, case-insensitive column names).

Cloud connections use the **current Azure CLI session** (`az login`) via `AzureCliCredential`. No SQL password or storage account key is required for that path.

## Layout

```
config/tables.yaml          # table → parquet mapping
src/sql_parquet_compare/    # readers, normaliser, comparer, CLI
tests/                      # unit tests (no Docker)
tests/integration/          # live SQL Server + Azurite
scripts/seed_local.py       # sample tables + parquet
docker-compose.yml          # SQL Server + Azurite
```

## Setup

```bash
cd ~/Projects/sql-parquet-compare
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

## Azure CLI login (SQL + storage)

```bash
az login
az account set --subscription <subscription-id-or-name>
az account show
```

The signed-in identity must be:

- an Entra ID user on the SQL server / Azure SQL database (`CREATE USER [<upn>] FROM EXTERNAL PROVIDER` plus read permission)
- granted Blob Data access on the storage account (typically **Storage Blob Data Reader**)

Install ODBC Driver 18 and the Python extra:

```bash
pip install -e ".[odbc]"
```

Point `.env` at Azure:

```bash
SQL_AUTH=azure_cli
SQL_DIALECT=pyodbc
SQL_HOST=<server>.database.windows.net
SQL_PORT=1433
SQL_DATABASE=<database>
SQL_ENCRYPT=yes

STORAGE_AUTH=azure_cli
AZURE_STORAGE_ACCOUNT=<account>
AZURE_STORAGE_ACCOUNT_URL=https://<account>.blob.core.windows.net
AZURE_STORAGE_CONNECTION_STRING=
AZURE_STORAGE_CONTAINER=parquet
```

Confirm tokens, then compare:

```bash
sql-parquet-compare --check-auth -c config/tables.yaml
sql-parquet-compare -c config/tables.yaml
```

`--check-auth` asks Azure CLI for a SQL token (`https://database.windows.net/.default`) and a storage token (`https://storage.azure.com/.default`) using the active `az login` account.

`SQL_AUTH=azure_default` / `STORAGE_AUTH=azure_default` uses `DefaultAzureCredential` instead (CLI, managed identity, environment, VS Code, etc.).

## Local Docker (password + Azurite)

Used by integration tests. This path does not use Azure CLI.

```bash
docker compose up -d
python scripts/wait_for_services.py
python scripts/seed_local.py
pytest
```

`.env` defaults:

```bash
SQL_AUTH=sql
STORAGE_AUTH=connection_string
AZURE_STORAGE_CONNECTION_STRING=UseDevelopmentStorage=true
```

## Run tests

```bash
pytest tests --ignore=tests/integration
pytest
```

Integration tests skip automatically if Docker services are not running.

## Compare tables

```bash
sql-parquet-compare -c config/tables.yaml
sql-parquet-compare -c config/tables.yaml --table customers --json
```

Exit code `0` means every mapped table matched. `1` means at least one mismatch.

Map tables in `config/tables.yaml`:

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
