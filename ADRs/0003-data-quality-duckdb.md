---
status: draft
date: 2026-05-13
owner: Robert Pereira
superseded_by:
tags: [data-quality, duckdb, dagster, soda-core, testing, phase-2]
---
# 0003 — Data Quality in DuckDB

## Context

[[0002-phase-2-pipeline-layer]] decided to use DuckDB SQL scripts for Bronze → Silver → Gold transforms instead of dbt. dbt is the most common framework for data quality in SQL-first pipelines — it ships with built-in tests (`not_null`, `unique`, `accepted_values`, `relationships`), a Great Expectations integration, and unit tests (dbt 1.8+). By excluding dbt, this project trades away that testing ecosystem.

This ADR answers: **how do we get equivalent data quality guarantees using the tools already in the stack (DuckDB + Dagster)?**

Two distinct quality concerns must be addressed:

1. **Production data validity** — is the data that landed correct? (Null PKs, domain violations, schema drift, freshness)
2. **Transform correctness** — does the SQL produce the right output? (Silent regressions when transform logic changes)

In production Spark/Delta Lake pipelines, quality checks are never run against the full table on every pipeline run. The pattern is tiered by scope and frequency:

| Tier | When | Scope |
|---|---|---|
| Pre/post-write | Every run | New batch only (today's partition) |
| Aggregate | Daily | Full table or sample |
| Profiling | Weekly | 1–5% statistical sample |

This ADR adopts the same tiering. Checks that scan the full table on every run are an anti-pattern at scale.

## Decision

Use **Soda Core** (`soda-core-duckdb`) for production data validity checks and **pytest + snapshot testing** for transform correctness. No hand-written SQL assertions. No additional orchestration tool.

### Directory structure

SQL transforms and Soda YAML checks are colocated per table — the same way dbt colocates models and `schema.yml` tests. Pytest snapshot tests live in a `tests/` subfolder alongside each transform.

```
pipelines/
├── bronze/
│   └── <table>/
│       ├── <table>.sql          # ingestion or raw transform
│       └── <table>.yml          # Soda checks
├── silver/
│   └── <table>/
│       ├── <table>.sql          # DuckDB Bronze → Silver transform
│       ├── <table>.yml          # Soda checks
│       └── tests/
│           ├── fixture.py       # controlled input rows
│           └── test_<table>.py  # snapshot assertions
└── gold/
    └── <table>/
        ├── <table>.sql          # DuckDB Silver → Gold transform
        ├── <table>.yml          # Soda checks
        └── tests/
            ├── fixture.py
            └── test_<table>.py
```

### Soda Core — production data validity

Soda Core provides a YAML-based check catalogue. No SQL is written by hand — checks reference named expectations from Soda's built-in library.

**Bronze (every run, new batch, blocking):**
```yaml
checks for bronze_customers:
  - row_count > 0
  - missing_count(customer_id) = 0
  - duplicate_count(customer_id) = 0
  - schema:
      fail:
        when required column missing: [customer_id, name, ingested_at]
```

**Silver (every run, new batch, blocking):**
```yaml
checks for silver_customers:
  - missing_count(customer_id) = 0
  - duplicate_count(customer_id) = 0
  - invalid_count(status) = 0:
      valid values: [active, inactive]
  - missing_count(email) < 5%    # warn only — does not block
```

**Gold (daily schedule, full table, warn only):**
```yaml
checks for gold_revenue:
  - row_count > 0
  - min(amount) >= 0
  - freshness(calculated_at) < 25h
  - avg(amount) between 50 and 5000
```

### Dagster integration

A single wrapper function auto-discovers `*.yml` files and wires them as Dagster `@asset_check` — written once, reused by every table. Adding quality checks to a new table only requires creating a `.yml` file; no Python touched.

```python
# pipelines/quality/soda_checks.py
def build_soda_check(asset, yml_path, blocking):
    @asset_check(asset=asset, blocking=blocking)
    def _check(context) -> AssetCheckResult:
        scan = Scan()
        scan.set_data_source_name("duckdb")
        scan.add_configuration_yaml_file("soda/configuration.yml")
        scan.add_sodacl_yaml_file(yml_path)
        scan.add_variables({"date": context.partition_key})
        scan.execute()
        return AssetCheckResult(
            passed=scan.get_error_count() == 0,
            metadata={"errors": scan.get_error_count(), "warnings": scan.get_warning_count()},
        )
    return _check
```

### Severity tiers

| Severity | Dagster behaviour | Use for |
|---|---|---|
| `blocking=True` | Halts downstream assets | Null PKs, schema mismatch, zero-row tables |
| `blocking=False` | Flags in UI, pipeline continues | Optional field nulls, metric anomalies |

### pytest + snapshot — transform unit tests

Transform unit tests validate that the SQL in each `<table>.sql` produces the expected output given controlled input. These are equivalent to **dbt unit tests** (dbt 1.8+) and the **`chispa` golden file pattern** used in Spark pipelines.

Tests run in-memory with DuckDB — no MinIO, no Iceberg, no cluster required.

```python
# pipelines/silver/customers/tests/test_customers.py
import duckdb

def test_deduplicates_on_customer_id(snapshot):
    conn = duckdb.connect()
    conn.execute(open("pipelines/silver/customers/customers.sql").read())
    result = conn.execute("SELECT * FROM silver_customers ORDER BY customer_id").df()
    snapshot.assert_match(result.to_csv(index=False), "silver_customers.csv")
```

- First run: `pytest --snapshot-update` saves the golden `.csv` to Git
- Every subsequent run: compares output against the committed golden file
- Intentional transform change: re-run `--snapshot-update` to approve the new output

### What each layer tests

| Layer | Tool | Catches |
|---|---|---|
| Soda YAML | Runtime, production data | Null PKs, domain violations, freshness, schema drift |
| pytest snapshot | CI, transform logic | Silent regressions when SQL changes |

## Alternatives Considered

### Hand-written SQL assertions via Dagster Asset Checks (original approach)

The first draft of this ADR used `@asset_check` with raw SQL assertions per check:
```python
@asset_check(asset=silver_customers, blocking=True)
def no_null_id(context) -> AssetCheckResult:
    count = duckdb.sql("SELECT COUNT(*) FROM ... WHERE customer_id IS NULL").fetchone()[0]
    return AssetCheckResult(passed=count == 0, metadata={"null_count": count})
```
Rejected because every check requires 8–10 lines of Python boilerplate (vs 1 line in Soda YAML), there is no standard catalogue (every check is SQL written from scratch), and there is no batch scoping built in. Soda Core solves all three problems.

### Great Expectations

GX is the industry standard with 50+ built-in expectations, auto-profiling (scans a table and suggests expectations), and a `dagster-great-expectations` integration. It was considered and rejected because:

1. **Setup complexity**: GX requires a Data Context, Expectation Suites, and Checkpoints — significant overhead for a learning project.
2. **Weight**: ~200 MB runtime vs ~50 MB for Soda Core.
3. **GX v1 API churn**: GX v1 (current) has a significantly different API from v0 — most tutorials are outdated, increasing learning friction.

GX is the right choice for a production environment with a dedicated data quality team. Soda Core achieves the same goals with less configuration.

### Soda Core + Great Expectations hybrid

Using Soda for standard checks and GX for statistical/profiling checks was considered. Rejected: two quality frameworks in the same project doubles the configuration surface without adding new capabilities that matter at this project's scale.

### dbt-duckdb (bring dbt back)

Using `dbt-duckdb` would restore the full dbt test ecosystem. Rejected — see [[0002-phase-2-pipeline-layer]] for the rationale. Running dbt alongside Dagster splits orchestration and contradicts the single-tool-per-concern principle.

## Consequences

**Positive:**
- Soda YAML checks are as concise as dbt `schema.yml` tests — one line per assertion, no Python boilerplate.
- Adding quality checks to a new table requires only a `.yml` file. No Python changes.
- Batch-scoped scanning mirrors production Spark/Delta patterns — checks never scan the full table on every run.
- Blocking checks propagate failures through the Dagster asset graph automatically.
- pytest snapshot tests catch transform regressions in CI with no external services.
- `soda-core-duckdb` + `pytest-snapshot` add ~50 MB to the dependency footprint — negligible.

**Negative / trade-offs:**
- Soda's Dagster integration (`soda-dagster`) is not as mature as `dagster-great-expectations`. The wrapper function is a one-time build but must be maintained.
- No auto-profiling: unlike GX, Soda cannot scan a table and suggest which checks to add. Initial check authorship is manual.
- Snapshot golden files must be updated (`pytest --snapshot-update`) whenever a transform changes intentionally — a small but real maintenance discipline.

**Follow-up decisions needed:**
- [[0004-phase-3-query-layer]] — Trino, ClickHouse, Cloudbeaver
- [[0005-phase-4-governance-observability-layer]] — Keycloak, OpenMetadata, Loki, Prometheus, Grafana
