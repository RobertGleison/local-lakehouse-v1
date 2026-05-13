---
status: draft
date: 2026-05-13
owner: Robert Pereira
superseded_by:
tags: [kubernetes, gitops, storage, iceberg, minio, nessie, phase-1]
---
# 0001 — Phase 1: Storage Layer

## Context

This project builds a local data lakehouse on a MacBook (16 GB RAM) using open-source tools. The goal is to learn DataOps, DevOps, and data engineering through hands-on practice.

Phase 1 establishes the foundational storage layer — the substrate everything else depends on. It must answer three questions before any pipeline or query work can begin:

1. **Where do we run services?** — A local Kubernetes cluster is needed so that all subsequent phases (pipelines, query engines, governance) can be deployed the same way they would be in production.
2. **How do we manage cluster state?** — Manual `helm upgrade` commands don't scale and break reproducibility. A GitOps controller is needed from day 1.
3. **Where and how do we store data?** — Parquet files need an S3-compatible object store. Those files also need an ACID-capable table format and a versioned catalog so transforms can branch and merge data like code.

Hardware constraint: 16 GB total RAM with ~5 GB reserved for macOS. The full stack (all 4 phases) must fit in the remaining ~11 GB.

## Decision

Deploy **k3d + Argo CD + MinIO + Apache Iceberg (via Nessie)** as the Phase 1 storage layer.

### k3d — Local Kubernetes

Run K3s inside Docker containers using k3d. A single `cluster.yaml` defines nodes, port mappings, and volume mounts. Bootstrap via `infra/bootstrap.sh` which creates the cluster and installs Argo CD. No other tools are applied manually after that.

### Argo CD — GitOps controller

Argo CD is installed during bootstrap and becomes the only mechanism for applying cluster state. All subsequent phase deployments are declared as Argo CD `Application` manifests under `apps/`. Git is the single source of truth; no `kubectl apply` or `helm upgrade` commands are run post-bootstrap.

### MinIO — Object storage

MinIO provides S3-compatible object storage for all Iceberg Parquet files. Three buckets are created: `bronze`, `silver`, and `gold`, matching the medallion architecture layers. All downstream tools (dlt, DuckDB, Trino, ClickHouse) authenticate via MinIO IAM access keys.

### Apache Iceberg + Nessie — Table format and catalog

Apache Iceberg provides ACID transactions, schema evolution, and time travel on the Parquet files stored in MinIO. Nessie serves as the Iceberg catalog and adds Git-like branching semantics: create a branch, write experimental data, merge only if results are correct. This is a core lakehouse pattern practiced from Phase 1.

### Medallion layers

| Layer | Location | Purpose |
|---|---|---|
| Bronze | `bronze` bucket | Raw, as-ingested data |
| Silver | `silver` bucket | Cleaned, typed, deduplicated |
| Gold | `gold` bucket | Aggregated, business-ready |

### RAM allocation for this phase

| Service | Estimated RAM |
|---|---|
| k3d control plane | ~400 MB |
| Argo CD | ~300 MB |
| MinIO | ~400 MB |
| Nessie | ~300 MB |
| **Phase 1 total** | **~1,400 MB** |

## Alternatives Considered

### Kubernetes runtime: minikube or kind instead of k3d

**minikube** runs a full VM (or a Docker driver that behaves similarly) and ships with more default add-ons. It would consume ~200–400 MB more RAM than k3d for the same workload. k3d uses K3s, a production-grade minimal Kubernetes distribution (~512 MB binary), which is meaningfully lighter on a 16 GB machine.

**kind** (Kubernetes IN Docker) is nearly identical to k3d in approach and weight. k3d was chosen over kind because it has first-class support for multi-node clusters via a single YAML config, simpler port-forwarding semantics for local dev, and broader ecosystem tutorials for lakehouse setups.

**Docker Compose** was considered as a non-Kubernetes option. Rejected because the learning goal explicitly includes Kubernetes and GitOps. Using Compose would mean re-learning everything when moving to a real cluster.

### GitOps: Flux instead of Argo CD

Flux is a CNCF-graduated GitOps operator with a smaller RAM footprint (~100–150 MB vs ~300 MB for Argo CD). It was rejected because Argo CD offers a visual UI that makes it easier to see sync status and debug drift during learning — a meaningful advantage when the goal is understanding GitOps conceptually, not just operationally.

### Object storage: local filesystem or NFS instead of MinIO

Iceberg can write Parquet files to a plain local filesystem. This would eliminate MinIO (~400 MB) but would make the setup non-transferable: every downstream tool (Trino, ClickHouse) expects S3 endpoints. MinIO emulates S3 exactly, so all tool configurations use the same S3 URIs and credentials they would use in a real cloud environment. The learning value of using MinIO over a local path is high; the RAM cost is acceptable.

### Iceberg catalog: Hive Metastore or REST catalog instead of Nessie

**Hive Metastore** is the traditional Iceberg catalog. It requires a relational database (Postgres or MySQL) as its backend, adding ~300–500 MB RAM. It has no branching capability.

**Iceberg REST Catalog** (the spec-compliant reference implementation) is lightweight and stateless, but provides no branching or history — it is just a registry.

**Nessie** was chosen because it implements the Iceberg REST Catalog API (compatible with all Iceberg clients) while adding Git-semantics (branches, tags, commits, merges) on top. The Nessie branching workflow — create branch → transform → merge — is explicitly listed as a learning outcome for this phase and is a differentiating skill in the lakehouse engineering space.

## Consequences

**Positive:**
- All services run on Kubernetes from day 1, matching real production patterns.
- Argo CD enforces GitOps discipline: no manual cluster mutations after bootstrap.
- MinIO S3 compatibility means all tool configurations are portable to AWS S3 or GCS with a credential swap.
- Nessie branching makes data versioning a first-class practice alongside code versioning.
- Phase 1 footprint (~1,400 MB) leaves ~9,600 MB headroom for the remaining three phases and macOS.

**Negative / trade-offs:**
- k3d adds Docker-in-Docker complexity; container-level networking (DNS, service discovery) can be non-obvious to debug during initial setup.
- Argo CD has a steeper initial learning curve than `helm install`. Bootstrap time is longer.
- Nessie stores its commit log in-memory by default (RocksDB backend for persistence is available but not configured in this phase); a pod restart will lose catalog history in the learning environment.

**Follow-up decisions needed:**
- [[0002-phase-2-pipeline-layer]] — Dagster, dlt, DuckDB asset definitions
- [[0003-phase-3-query-layer]] — Trino, ClickHouse, Cloudbeaver
- [[0004-phase-4-governance-observability-layer]] — Keycloak, OpenMetadata, Loki, Prometheus, Grafana
