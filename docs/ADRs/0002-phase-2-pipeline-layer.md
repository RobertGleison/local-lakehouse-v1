---
status: draft
date: 2026-05-13
owner: Robert Pereira
superseded_by:
tags: [pipeline, ingestion, transforms, dagster, dlt, duckdb, phase-2]
---
# 0002 — Phase 2: Pipeline Layer

## Context

With the storage layer from [[0001-phase-1-storage-layer]] in place (k3d, Argo CD, MinIO, Nessie + Iceberg), Phase 2 activates the data movement layer. Three capabilities are needed:

1. **Ingestion** — pull data from external sources (REST APIs, databases, files) and land it as Bronze Iceberg tables in MinIO.
2. **Transforms** — clean and reshape Bronze → Silver (typed, deduplicated) and Silver → Gold (aggregated, business-ready) using SQL.
3. **Orchestration** — schedule, execute, monitor, and retry the above as a dependency graph with visible lineage.

Hardware constraint remains 16 GB total RAM. Phase 2 must add minimal overhead since Phases 3 and 4 still need to fit. The tool choices must also reinforce the learning goals: understanding medallion architecture patterns and asset-oriented pipeline design, not just running pipelines.

## Decision

Deploy **Dagster** as the orchestrator, with **dlt** (data load tool) and **DuckDB** running as Dagster job steps.

### Dagster — Orchestration and asset graph

Dagster models data pipelines as **software-defined assets**: each Iceberg table (Bronze, Silver, Gold) is a first-class asset with explicit upstream dependencies. The Dagster UI renders the full Bronze → Silver → Gold lineage graph, making the medallion architecture visible and debuggable.

Dagster runs as a Kubernetes deployment managed by Argo CD via `apps/phase-2-pipeline.yaml`. Pipelines are defined under `pipelines/assets/` and executed as Dagster runs. The Dagster scheduler handles recurring ingestion; the UI handles ad-hoc runs and reruns of failed assets.

### dlt — Ingestion (Bronze layer)

dlt (data load tool) is a Python-native library for ingesting data from REST APIs, databases, and files. It handles pagination, schema inference, incremental loading, and writes directly to Iceberg tables in MinIO via the Iceberg destination. A dlt pipeline is defined in `pipelines/ingestion/` and called as a Dagster `@asset`.

dlt runs in-process inside the Dagster pod — no separate deployment.

### DuckDB — Transforms (Silver and Gold layers)

DuckDB runs in-process (embedded) inside Dagster job steps. SQL transform scripts in `pipelines/transforms/` are executed by DuckDB reading from and writing to Iceberg tables via the PyIceberg + MinIO integration.

- **Bronze → Silver**: clean, type-cast, deduplicate raw data
- **Silver → Gold**: joins, aggregations, KPI calculations

DuckDB is single-threaded and in-process, which keeps RAM usage low and eliminates any distributed coordination overhead.

### Asset dependency model

```
dlt ingestion asset  →  Bronze Iceberg table
                              │
                    DuckDB transform asset
                              │
                         Silver Iceberg table
                              │
                    DuckDB transform asset
                              │
                         Gold Iceberg table
```

Each arrow is an explicit Dagster asset dependency. Dagster materialises assets in order and propagates failures upstream.

### RAM allocation for this phase (incremental over Phase 1)

| Service | Estimated RAM |
|---|---|
| Dagster (webserver + daemon + code server) | ~500 MB |
| dlt (in-process, per run) | ~50–100 MB |
| DuckDB (in-process, per run) | ~100–200 MB |
| **Phase 2 incremental** | **~500 MB idle / ~800 MB running** |

## Alternatives Considered

### Orchestration: Apache Airflow instead of Dagster

Airflow is the most widely deployed open-source orchestrator. It models pipelines as DAGs of operators. It was rejected for three reasons:

1. **RAM**: A minimal Airflow deployment (webserver, scheduler, worker, Postgres, Redis) consumes ~1,200–1,500 MB — roughly 3× Dagster's footprint on a RAM-constrained machine.
2. **Model**: Airflow DAGs describe task execution flow, not data assets. There is no native concept of a "table" as a first-class object, so lineage must be bolted on. Dagster's asset model makes the Bronze/Silver/Gold layers first-class entities.
3. **Learning goal alignment**: The goal is to learn medallion architecture patterns. Dagster's asset graph teaches those patterns directly; Airflow teaches task scheduling, which is a different skill.

### Orchestration: Prefect instead of Dagster

Prefect 2 is lighter than Airflow and has a cleaner Python API. It was not chosen because it does not have a native asset model — pipelines are flows and tasks, not assets with lineage. For a lakehouse learning environment where understanding data lineage is a primary goal, Dagster's asset-first model is the better fit.

### Ingestion: Airbyte instead of dlt

Airbyte is a full ingestion platform with 300+ connectors, a web UI, and a dedicated server. It was rejected because:

1. It adds ~1,500–2,000 MB RAM for its platform services (server, worker, db, temporal).
2. It is a separate deployment concern from the pipeline layer — harder to version alongside dlt pipeline code.
3. dlt connectors are plain Python functions; Airbyte connectors are Docker images. For a learning environment where reading and understanding the ingestion code is a goal, dlt is more transparent.

### Ingestion: Singer/Meltano instead of dlt

Meltano/Singer uses tap/target pairs (separate processes) and JSONL over stdin/stdout. It was considered and rejected in favour of dlt because dlt has first-class Iceberg support as a destination and runs as a Python library (no subprocess coordination needed). Singer taps writing to Iceberg require a custom target.

### Transforms: Apache Spark instead of DuckDB

Spark is the canonical distributed transform engine for large-scale lakehouse environments. It was explicitly excluded from the project because:

1. **RAM**: A local Spark deployment (driver + executor) requires ~3,000–4,000 MB minimum.
2. **Complexity**: Spark introduces a JVM runtime, a separate cluster manager, and distributed execution semantics that are unnecessary at a single-machine scale.
3. **Learning goal**: DuckDB teaches the same medallion transform patterns (Bronze → Silver → Gold SQL) with 1/20th the RAM. The SQL skills transfer directly to Spark; the operational overhead does not.

### Transforms: dbt instead of DuckDB SQL scripts

dbt is a SQL-first transform framework with built-in testing, documentation, and lineage. It was considered and excluded because at this project's scale, raw DuckDB SQL scripts in `pipelines/transforms/` serve the same purpose. Introducing dbt would add another tool to the learning surface without adding new architectural concepts — the medallion patterns are already taught by the layer structure itself.

## Consequences

**Positive:**
- Dagster asset graph makes Bronze → Silver → Gold lineage visible in the UI from the first pipeline run.
- dlt's incremental loading handles pagination and state automatically, reducing ingestion boilerplate.
- DuckDB in-process execution means no extra pods, no network overhead, and fast SQL iteration.
- The entire Phase 2 stack adds only ~500 MB idle RAM, well within budget.
- All pipeline code lives under `pipelines/` and is version-controlled alongside infrastructure.

**Negative / trade-offs:**
- DuckDB is single-node only; transforms that need to join very large datasets may hit memory limits at scale. Acceptable for a local learning environment.
- dlt's Iceberg destination is newer than its warehouse destinations; edge cases in schema evolution may require workarounds.
- Dagster has more concepts to learn upfront (assets, jobs, sensors, schedules, resources) compared to simple cron + scripts. This complexity pays off as the pipeline grows but adds initial friction.

**Follow-up decisions needed:**
- [[0003-phase-3-query-layer]] — Trino, ClickHouse, Cloudbeaver
- [[0004-phase-4-governance-observability-layer]] — Keycloak, OpenMetadata, Loki, Prometheus, Grafana
