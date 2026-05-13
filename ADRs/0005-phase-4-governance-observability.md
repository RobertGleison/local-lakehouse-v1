---
status: draft
date: 2026-05-13
owner: Robert Pereira
superseded_by:
tags: [governance, observability, keycloak, openmetadata, loki, prometheus, grafana, iam, phase-4]
---
# 0005 — Phase 4: Governance & Observability

## Context

Phases 1–3 deliver a functioning data lakehouse: data flows from external sources through Bronze/Silver/Gold Iceberg tables, can be queried interactively via Trino and ClickHouse, and has quality checks at each layer. What is missing:

1. **Identity and access** — every service (Argo CD, Grafana, Dagster UI, Cloudbeaver, OpenMetadata) has its own login. There is no single identity, no central access control, and no audit trail.
2. **Data governance** — there is no catalog of what tables exist, what their schemas are, where the data came from, or how columns relate across layers. Discovering the lakehouse requires reading code.
3. **Observability** — there are no dashboards for pipeline health, query latency, or cluster resource pressure. Debugging a failed pipeline means reading pod logs directly from kubectl.

Phase 4 addresses all three with a minimal set of tools that each have one clear responsibility. These services are optional at runtime — the lakehouse continues to function if Phase 4 is scaled down. They add operational maturity, not core data flow.

Hardware constraint: Phase 4 must fit in the remaining headroom after Phases 1–3. With Trino and ClickHouse scaled to 0, the always-on Phase 4 footprint (~1,800 MB) is acceptable. Running the full stack simultaneously requires careful replica management.

## Decision

Deploy **Keycloak** (IAM/SSO), **OpenMetadata** (data governance catalog), **Loki** (log aggregation), **Prometheus** (metrics), and **Grafana** (dashboards) as the Phase 4 governance and observability layer.

### Keycloak — Identity and access management

Keycloak provides OIDC/OAuth2 SSO for all web UIs in the stack. A single Keycloak realm defines users and roles. Each service is registered as an OIDC client. After Phase 4 is active, all UIs (Argo CD, Grafana, Dagster, OpenMetadata, Cloudbeaver) accept the same username and password via Keycloak's login page.

Service-to-service authentication (MinIO, DuckDB, Trino, ClickHouse accessing storage) uses MinIO IAM access keys and Kubernetes service accounts — not Keycloak. Keycloak is scoped to **human logins only**.

| Access type | Tool |
|---|---|
| Human logins (web UIs) | Keycloak OIDC |
| Service-to-service (S3 storage) | MinIO IAM access keys |
| Kubernetes workloads | k3s RBAC + service accounts |

**RAM:** ~500 MB.

### OpenMetadata — Data governance catalog

OpenMetadata connects to Trino as a metadata source and auto-discovers all Iceberg tables across Bronze, Silver, and Gold layers. It builds a searchable catalog with schema definitions, column descriptions, sample data, and end-to-end lineage (dlt ingestion → DuckDB transform → Gold table).

OpenMetadata replaces the need to read `pipelines/` source code to understand what tables exist and how they were produced. It also integrates with the Dagster pipeline runs to show which asset materialisation produced which table version.

**RAM:** ~700 MB.

### Loki — Log aggregation

Loki collects logs from all pods via Promtail (a log shipping agent deployed as a DaemonSet). Logs are indexed by Kubernetes labels (pod name, namespace, container) and stored in MinIO — reusing the existing object store rather than adding a new one.

Loki is queried through Grafana using LogQL. A single Grafana panel gives full-text log search across all pods — the same experience as CloudWatch Logs or Datadog Log Management, but local.

**RAM:** ~150 MB (Loki) + ~50 MB (Promtail DaemonSet).

### Prometheus — Metrics

Prometheus scrapes metrics endpoints from all services that expose them: Dagster, Trino, ClickHouse, MinIO, and the k3s node exporter (CPU, RAM, disk per pod). Metrics are retained locally for 15 days — sufficient for a learning environment.

**RAM:** ~200 MB.

### Grafana — Dashboards

Grafana connects to both Prometheus (metrics) and Loki (logs) as data sources. Six dashboards are provisioned:

| Dashboard | Source | What it shows |
|---|---|---|
| Pipeline health | Prometheus + Dagster | Asset run success/failure rate, duration per asset |
| Query latency | Trino metrics | P50/P95 query duration |
| OLAP latency | ClickHouse metrics | Query response times |
| Cluster pressure | Prometheus node exporter | CPU/RAM per pod, alert threshold at 80% |
| Storage growth | MinIO metrics | Bucket sizes for Bronze/Silver/Gold over time |
| Error logs | Loki | Full-text log search across all pods |

Grafana is also a Keycloak OIDC client — the same login used everywhere else.

**RAM:** ~200 MB (Grafana) — shared Grafana stack with Loki + Prometheus totals ~600 MB.

### RAM allocation for this phase (incremental over Phase 3)

| Service | Estimated RAM |
|---|---|
| Keycloak | ~500 MB |
| OpenMetadata | ~700 MB |
| Loki + Promtail | ~200 MB |
| Prometheus | ~200 MB |
| Grafana | ~200 MB |
| **Phase 4 incremental** | **~1,800 MB** |

**Full stack (all phases active, Trino + ClickHouse at 1 replica):**

| Phase | RAM |
|---|---|
| Phase 1 (k3d + Argo CD + MinIO + Nessie) | ~1,400 MB |
| Phase 2 (Dagster + dlt + DuckDB) | ~500 MB idle |
| Phase 3 (Trino + ClickHouse + Cloudbeaver) | ~2,600 MB |
| Phase 4 (Keycloak + OpenMetadata + Grafana stack) | ~1,800 MB |
| **Total** | **~6,300 MB** |
| macOS overhead | ~5,000 MB |
| **Headroom on 16 GB** | **~4,700 MB ✓** |

## Alternatives Considered

### IAM: Dex instead of Keycloak

Dex is a lightweight OIDC identity provider (~100 MB) that federates to upstream identity sources (GitHub, LDAP, SAML). It is simpler to configure than Keycloak for pure OIDC federation. It was rejected because:

1. Dex does not manage users itself — it requires an upstream provider (GitHub, LDAP). In a local learning environment with no upstream provider, Dex has no user store to work with.
2. Keycloak is a full-featured IAM platform: user management, roles, groups, client scopes, audit logs. Learning to configure Keycloak is a transferable skill for production deployments. Dex is a proxy, not a platform.

### Data governance: DataHub instead of OpenMetadata

DataHub (maintained by LinkedIn) is a widely deployed enterprise data catalog with strong lineage and search capabilities. It was explicitly excluded from the project because:

1. DataHub's full deployment (GMS, MCE consumer, MAE consumer, frontend, Elasticsearch, Kafka, MySQL) consumes ~4,000–5,000 MB — over twice the total Phase 4 RAM budget.
2. OpenMetadata achieves the same core capabilities (table discovery, lineage, column-level metadata, Trino connector) in a single-service deployment at ~700 MB.
3. OpenMetadata's architecture is simpler to understand for a learning environment — one service, one database, one API.

### Data governance: Amundsen instead of OpenMetadata

Amundsen (maintained by Lyft) is a data discovery tool focused on table search and popularity scoring. It does not have native Iceberg/Trino lineage support and requires Elasticsearch + Neo4j as backends, adding ~800–1,200 MB. Rejected in favour of OpenMetadata's lighter footprint and better Trino integration.

### Log aggregation: ELK stack instead of Loki

Elasticsearch + Logstash + Kibana (ELK) is the most widely deployed log aggregation stack. It was rejected because:

1. **RAM**: A minimal ELK deployment consumes ~2,000–3,000 MB. Loki + Promtail achieves the same log search at ~200 MB by storing logs in MinIO (object storage) rather than an inverted index.
2. **Architecture fit**: Loki reuses MinIO as its storage backend — no new storage system introduced. ELK adds Elasticsearch as a new stateful service with its own operational overhead.
3. Loki's LogQL is similar to PromQL, so learning both Prometheus and Loki in Grafana reinforces the same query mental model.

### Metrics: InfluxDB instead of Prometheus

InfluxDB is a purpose-built time-series database with a push-based metrics model. Prometheus uses a pull-based scrape model. Prometheus was chosen because every service in this stack (Dagster, Trino, ClickHouse, MinIO) already exposes a `/metrics` endpoint in Prometheus format — no agent or exporter configuration needed beyond standard scrape configs. InfluxDB would require a separate push agent on each service.

### Dashboards: Kibana instead of Grafana

Kibana is the native dashboard tool for the ELK stack. Since ELK was rejected in favour of Loki, Kibana is not applicable. Grafana natively supports both Prometheus and Loki as data sources — it is the single dashboard surface for both metrics and logs.

## Consequences

**Positive:**
- Keycloak SSO eliminates per-service password management. One identity, one login for all UIs.
- OpenMetadata auto-discovery means the full table catalog (Bronze/Silver/Gold, all schemas, lineage) is always up to date without manual documentation.
- Loki log aggregation in Grafana gives the same debugging experience as cloud-native log tools (CloudWatch, Datadog) — search by pod name, filter by time range, full-text search — all from the same UI as metrics dashboards.
- Storing Loki logs in MinIO reuses existing infrastructure — no new storage system.
- Phase 4 services are optional. Scaling them to 0 has no impact on data flow or query capability.

**Negative / trade-offs:**
- Keycloak is the most complex configuration task in the entire project. Each OIDC client requires a client ID, secret, redirect URIs, and role mappings. Misconfiguration locks users out of services.
- OpenMetadata requires a Postgres database as its backend metadata store — an additional stateful service (~200 MB, not counted in the RAM budget above). This is the only service in the stack that introduces a new database dependency.
- Loki's LogQL is powerful but has a learning curve distinct from SQL. Full-text log search requires understanding label selectors and log pipeline filters.
- The Grafana stack (Loki + Prometheus + Grafana) is deployed as a single Helm chart (`grafana-stack`) to simplify configuration. Upgrading individual components requires upgrading the whole chart.
