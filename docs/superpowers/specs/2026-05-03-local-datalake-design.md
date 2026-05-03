# Local Open-Source Datalake — Design Spec

**Date:** 2026-05-03  
**Goal:** Build a local data lakehouse with open-source tools to learn DataOps, DevOps, and data engineering.  
**Primary learning goals:** Lakehouse architecture + Platform Engineering  
**Hardware:** MacOS, 16 GB RAM  

---

## 1. Tool Stack

| Layer | Tool | Purpose |
|---|---|---|
| Kubernetes | k3d (K3s in Docker) | Local cluster — all services run as pods |
| GitOps | Argo CD | Syncs all Helm charts from Git to the cluster |
| Blob storage | MinIO | S3-compatible object storage — holds all Iceberg Parquet files |
| Table format | Apache Iceberg | ACID tables with schema evolution and time travel |
| Catalog | Nessie | Git-like versioning for the Iceberg catalog (branch, merge, tag) |
| Ingestion | dlt | Python-native data load tool — REST, SQL, filesystem connectors |
| Transforms | DuckDB | In-process SQL: Bronze → Silver → Gold (replaces Spark) |
| Orchestration | Dagster | Asset-oriented pipeline orchestration with lineage UI |
| Federated query | Trino (single-node) | "Open-source Athena" — SQL across all Iceberg layers via Nessie |
| OLAP | ClickHouse | Fast aggregations on Gold layer data |
| SQL editor | Cloudbeaver | Web-based SQL client — connects to Trino and ClickHouse |
| IAM | Keycloak | OIDC/OAuth2 SSO — single login for all web UIs |
| Data governance | OpenMetadata | Catalog, lineage, data quality — auto-discovers Iceberg + Trino |
| Logs | Loki | Log aggregation from all pods |
| Metrics | Prometheus | Metrics scraping from all pods |
| Dashboards | Grafana | Observability dashboards for pipeline health, queries, cluster |

**Tools explicitly excluded:**
- Spark — replaced by DuckDB (teaches same medallion patterns, 1/20th the RAM)
- Presto — redundant with Trino (they are forks of the same project)
- StarRocks — redundant with ClickHouse
- Apache Superset — not needed; Cloudbeaver covers SQL editor, Trino CLI for scripting

---

## 2. Deployment Strategy

**Approach: Layered k3d — phased rollout on Kubernetes**

Everything runs on k3d from day 1, managed by Argo CD. The stack is activated in 4 independent phases. Each phase is a standalone learning module. Phases 3 and 4 services can be scaled to 0 replicas when idle to save RAM.

---

## 3. Medallion Architecture (Data Flow)

```
External sources (APIs / databases / files)
        │
        ▼ dlt ingestion
┌───────────────────────────────────────┐
│  BRONZE — raw, as-is                  │
│  Iceberg tables in MinIO / Nessie     │
└───────────────────────────────────────┘
        │ DuckDB transform (clean, type, deduplicate)
        ▼
┌───────────────────────────────────────┐
│  SILVER — cleaned, normalised         │
│  Iceberg tables in MinIO / Nessie     │
└───────────────────────────────────────┘
        │ DuckDB transform (joins, aggregations, KPIs)
        ▼
┌───────────────────────────────────────┐
│  GOLD — business-ready                │
│  Iceberg tables in MinIO / Nessie     │
│  (loaded into ClickHouse in Phase 3)  │
└───────────────────────────────────────┘
        │
        ▼ Query consumers
  Trino (federated SQL across all layers)
  ClickHouse (OLAP on Gold)
  Cloudbeaver (web SQL editor)
```

**Nessie branching workflow:** Create a Nessie branch, run experimental transforms, merge only if results look correct. Same Git workflow applied to data — a core lakehouse pattern.

Each pipeline stage is a **Dagster asset**. The Bronze, Silver, and Gold tables are assets with explicit upstream dependencies. Dagster's asset graph makes the Bronze → Silver → Gold lineage visible in the UI.

---

## 4. Repository Structure

```
local-datalake/
├── infra/
│   ├── cluster.yaml          # k3d cluster config (nodes, ports, volumes)
│   └── bootstrap.sh          # creates k3d cluster + installs Argo CD only (phases applied separately)
├── apps/
│   ├── phase-1-storage.yaml  # Argo CD Application: MinIO + Nessie
│   ├── phase-2-pipeline.yaml # Argo CD Application: Dagster
│   ├── phase-3-query.yaml    # Argo CD Application: Trino + ClickHouse + Cloudbeaver
│   └── phase-4-govern.yaml   # Argo CD Application: Keycloak + OpenMetadata + Loki + Grafana
├── helm/
│   ├── minio/                # values.yaml overrides
│   ├── nessie/
│   ├── trino/
│   ├── clickhouse/
│   ├── dagster/
│   ├── keycloak/
│   ├── openmetadata/
│   └── grafana-stack/        # Loki + Prometheus + Grafana together
├── pipelines/
│   ├── ingestion/            # dlt sources + destinations
│   ├── transforms/           # DuckDB SQL scripts per layer
│   └── assets/               # Dagster asset definitions
└── docs/
    └── superpowers/specs/
```

---

## 5. GitOps Workflow

Every infrastructure change follows the same flow:

1. Edit a file under `helm/<service>/values.yaml`
2. `git push` to `main`
3. Argo CD detects drift between Git state and cluster state
4. Argo CD syncs the Helm release — pods updated

No `kubectl apply` or `helm upgrade` commands are run manually after bootstrap. Git is the single source of truth.

---

## 6. Phased Rollout

### Phase 1 — Storage Layer
**Services:** k3d, Argo CD, MinIO, Nessie  
**Learning outcomes:**
- Bootstrap a local Kubernetes cluster with k3d
- Deploy services via Argo CD (GitOps day 1)
- Create MinIO buckets for Bronze / Silver / Gold
- Register the Nessie catalog and create an Iceberg table
- Practice Nessie branching: create branch → write data → merge

### Phase 2 — Pipeline Layer
**Services:** Dagster (+ dlt and DuckDB run as Dagster jobs)  
**Learning outcomes:**
- Write a dlt pipeline that ingests a real API into a Bronze Iceberg table
- Write DuckDB SQL transforms for Silver (clean) and Gold (aggregate)
- Define Dagster assets for each medallion layer
- Schedule and monitor a full pipeline run in the Dagster UI

### Phase 3 — Query Layer
**Services:** Trino, ClickHouse, Cloudbeaver  
**Learning outcomes:**
- Point Trino at Nessie to query all 3 Iceberg layers with SQL
- Load Gold layer into ClickHouse for sub-second OLAP queries
- Use Cloudbeaver to run interactive queries against Trino and ClickHouse
- Scale Trino/ClickHouse to 0 replicas in Argo CD when idle

### Phase 4 — Governance & Observability Layer
**Services:** Keycloak, OpenMetadata, Loki, Prometheus, Grafana  
**Learning outcomes:**
- Configure Keycloak OIDC for Argo CD, Grafana, Dagster, OpenMetadata, Cloudbeaver
- Connect OpenMetadata to Trino — auto-discover all Iceberg tables and lineage
- Build Grafana dashboards: pipeline health, query latency, cluster resource pressure
- Set up Loki log search across all pods

---

## 7. IAM Design

| Access type | Tool | Scope |
|---|---|---|
| Human logins (web UIs) | Keycloak (OIDC) | Argo CD, Grafana, Dagster UI, OpenMetadata, Cloudbeaver |
| Service-to-service (storage) | MinIO IAM (S3 access keys) | dlt, DuckDB, Trino, ClickHouse reading from MinIO |
| Kubernetes RBAC | k3s built-in | Pod service accounts, namespace isolation |

---

## 8. Observability Design

**Grafana dashboards (6 panels minimum):**

| Dashboard | Source | What it shows |
|---|---|---|
| Pipeline health | Prometheus + Dagster | Asset run success/failure rate, duration |
| Query latency | Trino metrics | P50/P95 query duration |
| OLAP latency | ClickHouse metrics | Query response times |
| Cluster pressure | Prometheus (node exporter) | CPU/RAM per pod, alert at 80% |
| Storage growth | MinIO metrics | Bucket sizes per Bronze/Silver/Gold |
| Error logs | Loki | Full-text log search across all pods |

---

## 9. RAM Budget (Phase 4 — full stack)

| Service(s) | Estimated RAM |
|---|---|
| k3d control plane + Argo CD | ~700 MB |
| MinIO + Nessie | ~700 MB |
| Dagster | ~500 MB |
| Trino (single-node, minimal heap) | ~1,500 MB |
| ClickHouse | ~800 MB |
| Cloudbeaver | ~300 MB |
| Keycloak | ~500 MB |
| OpenMetadata | ~700 MB |
| Loki + Prometheus + Grafana | ~600 MB |
| **Total data stack** | **~6,300 MB** |
| macOS overhead | ~5,000 MB |
| **Headroom on 16 GB** | **~4,700 MB ✓** |

Trino and ClickHouse can be scaled to 0 replicas via Argo CD when not actively querying, reducing the always-on footprint to ~3,500 MB.

---

## 10. Out of Scope

- Spark (replaced by DuckDB for local learning)
- dbt (DuckDB SQL scripts in `pipelines/transforms/` serve the same purpose at this scale)
- Apache Airflow (replaced by Dagster)
- DataHub (replaced by OpenMetadata — lighter, simpler setup)
- Production hardening (TLS, external secrets, multi-node clusters)
