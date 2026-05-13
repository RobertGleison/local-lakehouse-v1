---
status: draft
date: 2026-05-13
owner: Robert Pereira
superseded_by:
tags: [data-quality, duckdb, dagster, testing, phase-2]
---
# 0003 — Data Quality in DuckDB

## Context

[[0002-phase-2-pipeline-layer]] decided to use DuckDB SQL scripts for Bronze → Silver → Gold transforms instead of dbt. dbt is the most common framework for data quality in SQL-first pipelines — it ships with built-in tests (`not_null`, `unique`, `accepted_values`, `relationships`), a Great Expectations integration (`dbt-expectations`), and unit tests (dbt 1.8+). By excluding dbt, this project trades away that testing ecosystem.

This ADR answers: **how do we get equivalent data quality guarantees using the tools already in the stack (DuckDB + Dagster)?**

The quality surface spans three layers and three concerns:

| Layer | What to validate |
|---|---|
| Bronze | Schema conformance, row count > 0, no duplicate primary keys from source |
| Silver | Not-null on business keys, referential integrity, value domain checks |
| Gold | Business rule assertions (e.g. metrics are non-negative, totals are internally consistent) |

The quality checks must be visible alongside pipeline runs — a failure should block downstream assets, not silently pass.

## Decision

Implement data quality using **Dagster Asset Checks** for runtime validation and **pytest + DuckDB in-memory** for unit-level transform testing. No additional framework is introduced.

### Layer 1: Dagster Asset Checks (runtime, per-asset)

Dagster 1.5+ ships `@asset_check` — a first-class decorator that attaches a named check to any asset. Checks appear in the Dagster UI's asset graph, run automatically after materialisation, and block downstream assets on failure when configured with `blocking=True`.

Each Iceberg table asset gets one or more checks defined in the same file as the asset. Checks query the table via DuckDB using PyIceberg to read the Parquet files.

**dbt test equivalents:**

| dbt test | Dagster Asset Check equivalent |
|---|---|
| `not_null` | `SELECT COUNT(*) FROM t WHERE col IS NULL` → fail if > 0 |
| `unique` | `SELECT COUNT(*) - COUNT(DISTINCT col) FROM t` → fail if > 0 |
| `accepted_values` | `SELECT COUNT(*) FROM t WHERE col NOT IN ('a','b','c')` → fail if > 0 |
| `relationships` | JOIN to parent table, count unmatched FKs → fail if > 0 |
| `dbt-expectations: expect_column_values_to_be_between` | `SELECT COUNT(*) FROM t WHERE col < min OR col > max` → fail if > 0 |
| `dbt-expectations: expect_table_row_count_to_be_between` | `SELECT COUNT(*) FROM t` → fail if outside bounds |
| Custom test | Any SQL assertion returning a violation count |

**Example — Silver layer customer asset check:**

```python
from dagster import asset_check, AssetCheckResult, AssetCheckSeverity

@asset_check(asset=silver_customers, blocking=True)
def silver_customers_no_null_id(context) -> AssetCheckResult:
    count = duckdb.sql(
        "SELECT COUNT(*) FROM iceberg_scan('s3://silver/customers') WHERE customer_id IS NULL"
    ).fetchone()[0]
    return AssetCheckResult(
        passed=count == 0,
        severity=AssetCheckSeverity.ERROR,
        metadata={"null_id_count": count},
    )

@asset_check(asset=silver_customers, blocking=True)
def silver_customers_unique_id(context) -> AssetCheckResult:
    result = duckdb.sql("""
        SELECT COUNT(*) - COUNT(DISTINCT customer_id)
        FROM iceberg_scan('s3://silver/customers')
    """).fetchone()[0]
    return AssetCheckResult(passed=result == 0, metadata={"duplicate_count": result})
```

Checks are grouped under `pipelines/assets/<layer>_checks.py`. The Dagster UI shows each check by name, its pass/fail status, and the metadata (violation counts) per run.

### Layer 2: pytest + DuckDB in-memory (unit, per-transform)

The Bronze → Silver and Silver → Gold SQL scripts in `pipelines/transforms/` are pure SQL. They can be unit-tested by:

1. Loading a small fixture dataset into an in-memory DuckDB database
2. Executing the transform SQL against it
3. Asserting the output shape, types, and values with standard pytest assertions

This is equivalent to dbt's unit tests (introduced in dbt 1.8).

```python
# tests/transforms/test_silver_customers.py
import duckdb
import pytest

@pytest.fixture
def db():
    conn = duckdb.connect()
    conn.execute("""
        CREATE TABLE bronze_customers AS
        SELECT * FROM (VALUES
            (1, 'Alice', NULL),
            (2, 'Bob', 'bob@example.com'),
            (2, 'Bob_dup', 'dup@example.com')   -- duplicate id
        ) t(customer_id, name, email)
    """)
    return conn

def test_silver_deduplicates_on_customer_id(db):
    db.execute(open("pipelines/transforms/silver_customers.sql").read())
    count = db.execute("SELECT COUNT(*) FROM silver_customers").fetchone()[0]
    assert count == 2  # duplicate removed

def test_silver_drops_null_email_rows(db):
    db.execute(open("pipelines/transforms/silver_customers.sql").read())
    nulls = db.execute(
        "SELECT COUNT(*) FROM silver_customers WHERE email IS NULL"
    ).fetchone()[0]
    assert nulls == 0
```

Tests live under `tests/transforms/` and run via `pytest` as part of CI. They run in milliseconds — no cluster, no MinIO, no Iceberg required.

### Where each check type lives

```
pipelines/
├── assets/
│   ├── bronze_assets.py       # @asset definitions
│   ├── bronze_checks.py       # @asset_check: schema, row count, no-dup PK
│   ├── silver_assets.py
│   ├── silver_checks.py       # @asset_check: not_null, unique, domain values
│   ├── gold_assets.py
│   └── gold_checks.py         # @asset_check: business rule assertions
└── transforms/
    ├── silver_customers.sql
    └── gold_revenue.sql
tests/
└── transforms/
    ├── test_silver_customers.py
    └── test_gold_revenue.py
```

### Severity tiers

Not all checks should block the pipeline. Dagster Asset Checks support two severities:

| Severity | Behaviour | Use for |
|---|---|---|
| `ERROR` + `blocking=True` | Blocks downstream assets | Null PKs, negative revenue, zero-row tables |
| `WARN` | Flags in UI, does not block | Unexpected nulls on optional fields, row count deviations |

## Alternatives Considered

### Great Expectations (standalone)

Great Expectations (GX) is the industry-standard data quality framework. It has a DuckDB backend via its SQLAlchemy connector and supports 50+ built-in expectations. It was considered and rejected for this project because:

1. **Operational complexity**: GX requires a Data Context, a Data Source, Expectation Suites, and Checkpoints — all persisted as JSON or YAML config files. This is significant setup overhead for a learning project.
2. **No Dagster UI integration**: GX produces its own HTML reports. Failures must be surfaced to Dagster via a custom sensor or op, adding glue code. Dagster Asset Checks integrate natively.
3. **RAM**: A GX Checkpoint run loads the full GX runtime (~200–300 MB). Dagster Asset Checks run as lightweight Python functions with no additional runtime.

GX would be the right choice for a production lakehouse with a dedicated data quality team. At this project's scale, the complexity is not justified.

### Soda Core

Soda Core is a lighter alternative to GX with a YAML-based check syntax and a DuckDB scanner. It addresses GX's complexity problem but introduces a new tool that is not otherwise present in the stack. Since Dagster Asset Checks can express all the same checks as SQL, adding Soda Core would duplicate functionality. Rejected on the same grounds: no native Dagster UI integration, extra dependency, no new capabilities.

### dbt-duckdb (bring dbt back)

The `dbt-duckdb` adapter allows dbt to run against DuckDB as its warehouse. This would restore the full dbt testing ecosystem (`not_null`, `unique`, `dbt-expectations`, unit tests). It was considered and rejected because:

1. ADR [[0002-phase-2-pipeline-layer]] excluded dbt specifically to avoid adding a new tool surface when DuckDB SQL scripts cover the same transform patterns.
2. Running dbt alongside Dagster creates a split orchestration model: Dagster orchestrates assets, dbt orchestrates transforms. The integration is possible (dagster-dbt) but adds a layer of indirection that complicates the learning environment.
3. Dagster Asset Checks + pytest cover all the test categories dbt provides. The added complexity of dbt is not justified by a quality gap.

If the project grows in scope (e.g., multiple data sources, a team of analysts writing transforms), revisiting dbt-duckdb would be warranted.

### Pandera (DataFrame validation)

Pandera validates pandas/Polars DataFrames against a schema at the Python level. It is well-suited for ingestion validation (validating a DataFrame before writing to Bronze) but does not cover SQL transform correctness or table-level assertions. It is not rejected — it may be used within dlt pipeline steps to validate incoming API payloads before landing them. But it is not the primary data quality mechanism.

## Consequences

**Positive:**
- Dagster Asset Checks are visible in the asset graph UI — the same place engineers already watch pipeline runs. No separate quality dashboard needed.
- `blocking=True` propagates failures through the dependency graph automatically. A bad Bronze table will not silently produce a corrupt Gold table.
- pytest + DuckDB in-memory transform tests run in milliseconds, require no external services, and can run in CI on every push.
- No new runtime dependencies: DuckDB and Dagster are already in the stack.
- The SQL assertion pattern is identical to what analysts already write. No new framework to learn.

**Negative / trade-offs:**
- Dagster Asset Checks require more Python boilerplate than dbt's YAML test syntax. A `not_null` check that is one line in `schema.yml` is 8–10 lines of Python here.
- There is no auto-generated documentation for checks comparable to dbt's docs site.
- pytest transform tests must be maintained alongside the SQL scripts — a refactor of `silver_customers.sql` requires updating the corresponding test fixtures. This coupling is intentional but requires discipline.
- Great Expectations' richer expectation library (statistical distributions, column correlations) is not available without adding GX.

**Follow-up decisions needed:**
- [[0004-phase-3-query-layer]] — Trino, ClickHouse, Cloudbeaver
- [[0005-phase-4-governance-observability-layer]] — Keycloak, OpenMetadata, Loki, Prometheus, Grafana
