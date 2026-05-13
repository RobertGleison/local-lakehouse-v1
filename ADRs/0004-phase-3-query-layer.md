---
status: draft
date: 2026-05-13
owner: Robert Pereira
superseded_by:
tags: [query, trino, clickhouse, cloudbeaver, iceberg, olap, phase-3]
---
# 0004 — Phase 3: Query Layer

## Context

Phases 1–2 established storage (MinIO + Iceberg + Nessie) and pipelines (Dagster + dlt + DuckDB). At the end of Phase 2, Bronze, Silver, and Gold Iceberg tables exist in MinIO and can be read by DuckDB inside Dagster jobs. But there is no way for a human analyst to query them interactively, and no engine optimised for the fast aggregation queries that characterise BI and analytical workloads.

Phase 3 adds three capabilities:

1. **Federated SQL** — query all three Iceberg layers (Bronze, Silver, Gold) with standard SQL from any client, without moving data.
2. **OLAP acceleration** — sub-second aggregation queries on the Gold layer for dashboards and ad-hoc analysis.
3. **Interactive SQL editor** — a web UI for writing and running queries without a local client install.

Hardware constraint: Trino and ClickHouse are the heaviest services in the stack. This phase adds ~2,600 MB of RAM. Both services must be scalable to 0 replicas via Argo CD when not actively querying to keep the always-on footprint within budget.

## Decision

Deploy **Trino** (federated SQL), **ClickHouse** (OLAP), and **Cloudbeaver** (SQL editor) as the Phase 3 query layer.

### Trino — Federated query engine

Trino connects to Nessie as its Iceberg catalog and can query all three layers (Bronze, Silver, Gold) with standard SQL. It runs as a single-node deployment — no coordinator/worker split needed at this scale. Trino is the "open-source Athena" pattern: data stays in MinIO, Trino reads Parquet files directly at query time.

The Nessie connector exposes all Iceberg tables across the catalog. Analysts can run cross-layer joins (e.g. Bronze vs Gold reconciliation) in a single query without ETL.

Trino is scaled to 0 replicas in Argo CD when idle. Startup takes ~30 seconds, acceptable for a learning environment.

**RAM:** ~1,500 MB (single-node, JVM heap set to 1 GB via `config.properties`).

### ClickHouse — OLAP engine

ClickHouse ingests the Gold Iceberg layer (via a scheduled Dagster asset) and stores it in its native columnar format for sub-second aggregation queries. It is optimised for `GROUP BY`, `COUNT`, `SUM`, and window functions on large result sets — queries that Trino can answer but slowly due to Parquet scan overhead.

ClickHouse is the dedicated analytics engine. It does not replace Trino — Trino remains the federated query layer. ClickHouse handles the "fast dashboard" use case.

ClickHouse is also scaled to 0 replicas when idle.

**RAM:** ~800 MB.

### Cloudbeaver — SQL editor

Cloudbeaver is a web-based SQL client that connects to both Trino (via JDBC) and ClickHouse (via its native connector). It provides a browser UI for writing queries, browsing schemas, and exporting results — no local SQL client install needed.

**RAM:** ~300 MB.

### Data flow for this phase

```
MinIO (Iceberg tables)
        │
        ▼ Trino reads Parquet via Nessie catalog
   Trino ──────────────────────────────► Cloudbeaver (SQL editor)
        │
        │ Dagster asset: Gold → ClickHouse load
        ▼
   ClickHouse ──────────────────────────► Cloudbeaver (SQL editor)
```

### RAM allocation for this phase (incremental over Phase 2)

| Service | Estimated RAM |
|---|---|
| Trino (single-node, 1 GB heap) | ~1,500 MB |
| ClickHouse | ~800 MB |
| Cloudbeaver | ~300 MB |
| **Phase 3 incremental (active)** | **~2,600 MB** |
| **Phase 3 incremental (idle, scaled to 0)** | **~0 MB** |

## Alternatives Considered

### Federated query: Presto instead of Trino

Presto and Trino are forks of the same original Facebook Presto codebase. They have near-identical SQL dialects and configuration. Presto is maintained by the Presto Foundation (Meta, Uber, Alibaba); Trino is maintained by Trino Software Foundation (the original Presto creators). Trino was chosen because it has faster release cadence, better Iceberg and Nessie connector support, and more active community documentation for the lakehouse use case. Running both would be redundant — they solve the same problem identically.

### Federated query: Spark SQL instead of Trino

Spark SQL can query Iceberg tables via the Iceberg Spark connector and Nessie catalog. It was rejected because Spark was explicitly excluded from the stack in [[0001-phase-1-storage-layer]] due to RAM cost (~3,000–4,000 MB for a local Spark deployment). Trino achieves the same federated query capability at ~1,500 MB.

### Federated query: DuckDB (extend Phase 2 tool) instead of Trino

DuckDB can read Iceberg tables directly via `iceberg_scan()` and could serve as the interactive query engine. It was considered and rejected for the query layer role because:

1. DuckDB is in-process — it runs embedded inside a Python process. It has no persistent server, no JDBC/ODBC endpoint, and no multi-user access. Cloudbeaver cannot connect to it.
2. DuckDB is already used for transforms in Phase 2. Separating transform execution (DuckDB) from interactive query (Trino) keeps responsibilities clear.
3. Trino teaches the "query engine as a service" pattern used in production lakehouses (Athena, Starburst). DuckDB does not.

### OLAP: StarRocks instead of ClickHouse

StarRocks is a high-performance OLAP engine with native Iceberg support — it can query Iceberg tables directly without a separate load step. It was explicitly excluded from the project because it is redundant with ClickHouse for this use case. Both are columnar OLAP engines with similar query performance. ClickHouse has a larger community, more tutorials, and broader ecosystem integrations. StarRocks' native Iceberg support is compelling but not a differentiating factor at this learning scale.

### OLAP: Apache Druid instead of ClickHouse

Druid is a real-time OLAP engine designed for event streams and time-series data. It requires a full cluster (broker, coordinator, historical, middleManager, router) consuming ~3,000–4,000 MB minimum. Rejected on RAM grounds alone — ClickHouse achieves comparable aggregation performance at ~800 MB in a single-node deployment.

### SQL editor: Apache Superset instead of Cloudbeaver

Superset is a full BI platform with dashboards, charts, and a SQL editor. It was explicitly excluded from the project because its dashboard capabilities overlap with Grafana (Phase 4) and its SQL editor is not meaningfully better than Cloudbeaver for the learning use case. Superset adds ~600–800 MB RAM for its own stack (Flask app + Celery worker + Redis + Postgres). Cloudbeaver covers the SQL editor need at ~300 MB.

### SQL editor: Metabase instead of Cloudbeaver

Metabase is a lightweight BI tool with a question-based interface and a SQL editor. It was not chosen because it adds a Postgres database as a backend (~200 MB extra) and its primary UX is the "question builder" — a visual query interface that abstracts SQL. The learning goal for Phase 3 is writing SQL directly against Trino and ClickHouse, not building visual dashboards.

## Consequences

**Positive:**
- Trino gives analysts SQL access to all three Iceberg layers without moving data — the core "open lakehouse" query pattern.
- Cross-layer queries (e.g. joining Bronze raw rows to Gold aggregates for reconciliation) are possible in a single Trino SQL statement.
- ClickHouse provides sub-second OLAP on Gold data — the performance gap between "batch query" and "dashboard query" becomes concrete and learnable.
- Both Trino and ClickHouse can be scaled to 0 replicas, reducing always-on RAM pressure to ~300 MB (Cloudbeaver only) when the query layer is idle.
- Cloudbeaver connects to both engines in the same UI — no tool-switching between Trino and ClickHouse queries.

**Negative / trade-offs:**
- Trino's JVM startup time (~30 seconds from 0 replicas) means the first query after scaling up has noticeable latency.
- The Gold → ClickHouse load is a separate Dagster asset — ClickHouse is not directly reading from Iceberg. This means ClickHouse data lags behind Gold Iceberg by one pipeline run. Acceptable for a learning environment.
- Trino single-node has no fault tolerance. A pod restart drops all running queries. Acceptable for a learning environment.
- Phase 3 is the most RAM-intensive phase. Running Trino + ClickHouse simultaneously pushes active RAM usage to ~4,100 MB above Phase 2 baseline. Scaling both to 0 when not querying is essential.

**Follow-up decisions needed:**
- [[0005-phase-4-governance-observability-layer]] — Keycloak, OpenMetadata, Loki, Prometheus, Grafana
