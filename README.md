# Local Datalake

A local Kubernetes-based datalake for learning purposes. Runs entirely on your laptop using k3d (k3s in Docker), with GitOps managed by ArgoCD.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                       k3d Cluster                        │
│                                                          │
│  Storage & Catalog          Query & Processing           │
│  ┌──────────┐  ┌─────────┐  ┌───────┐  ┌────────────┐  │
│  │  MinIO   │  │ Nessie  │  │ Trino │  │ ClickHouse │  │
│  │ (S3)     │  │(catalog)│  │       │  │            │  │
│  └──────────┘  └─────────┘  └───────┘  └────────────┘  │
│                                                          │
│  Orchestration              Observability                │
│  ┌──────────┐  ┌─────────┐  ┌────────┐  ┌──────────┐   │
│  │ Dagster  │  │CloudBvr │  │Grafana │  │Prometheus│   │
│  │(pipeline)│  │(SQL UI) │  │(dash.) │  │(metrics) │   │
│  └──────────┘  └─────────┘  └────────┘  └──────────┘   │
│                                                          │
│  ┌──────────┐  ┌─────────┐                              │
│  │   Loki   │  │Promtail │                              │
│  │  (logs)  │  │(shipper)│                              │
│  └──────────┘  └─────────┘                              │
│                                                          │
│  ┌──────────────────────────────────────┐               │
│  │               ArgoCD                 │               │
│  │   (watches GitHub, syncs cluster)    │               │
│  └──────────────────────────────────────┘               │
└──────────────────────────────────────────────────────────┘
```

| Service | Role | Port |
|---------|------|------|
| MinIO | S3-compatible object storage (Bronze/Silver/Gold + Loki buckets) | 9000 (API), 9001 (UI) |
| Nessie | Git-like catalog for Iceberg table versioning | 19120 |
| Trino | Distributed SQL query engine over Iceberg tables | 8080 |
| ClickHouse | Columnar OLAP database for fast analytics | 8123 |
| Dagster | Pipeline orchestration with Celery workers | 3000 |
| CloudBeaver | Web-based SQL client for Trino/ClickHouse | 8978 |
| Prometheus | Metrics collection (MinIO, Dagster, Trino, ClickHouse, cluster) | — |
| Loki | Log aggregation backed by MinIO S3 | 3100 |
| Promtail | DaemonSet log shipper — collects all pod logs and sends to Loki | — |
| Grafana | Dashboards for metrics and logs (pre-wired to Prometheus + Loki) | 3000 |
| ArgoCD | GitOps controller — syncs the cluster to this repo | 8080 |

## Prerequisites

Make sure Docker is installed and running, then install the rest with Homebrew:

```bash
brew install k3d       # creates k3s clusters in Docker
brew install kubectl   # Kubernetes CLI
brew install helm      # Kubernetes package manager
brew install kubeseal  # encrypts secrets before committing
```

## Quickstart

```bash
# 1. Bootstrap the cluster (run once)
bash infra/bootstrap.sh

# 2. Seal your secrets (requires cluster + sealed-secrets controller running)
bash secrets/seal.sh

# 3. Commit and push sealed secrets to GitHub
git add secrets/*.yaml && git commit -m "feat: add sealed secrets" && git push

# 4. Deploy all services via ArgoCD
kubectl apply -f apps/
```

ArgoCD pulls from GitHub and deploys all services in sync-wave order (storage → catalog → query → orchestration → observability).

## Accessing services

**ArgoCD UI:**
```bash
kubectl port-forward svc/argocd-server -n argocd 8080:443
# Open https://localhost:8080  |  Username: admin
kubectl get secret argocd-initial-admin-secret -n argocd -o jsonpath="{.data.password}" | base64 -d
```

**MinIO UI:** `http://localhost:9001` (minioadmin / minioadmin123)

**Grafana:** `http://localhost:3000` (admin / admin — via sealed secret)
```bash
kubectl port-forward svc/grafana 3000:80 -n local-datalake
```

**Dagster UI:**
```bash
kubectl port-forward svc/dagster-dagster-webserver 3000:80 -n local-datalake
```

**Trino:** `http://localhost:8080`

**ClickHouse:** `http://localhost:8123`

**CloudBeaver:** `http://localhost:8978`

**Nessie API:** `http://localhost:19120`

## Deployment sync-waves

Services deploy in order via ArgoCD sync-waves:

| Wave | Services |
|------|---------|
| 0 | Sealed secrets |
| 1 | MinIO |
| 2 | Nessie |
| 3 | Trino, ClickHouse, CloudBeaver |
| 4 | Dagster |
| 5 | Prometheus, Loki |
| 6 | Promtail, Grafana |

## Project structure

```
apps/               ArgoCD Application manifests (one per service)
infra/              Cluster setup (k3d config, bootstrap script)
secrets/            Secret management (seal.sh + sealed secret manifests)
services/           One directory per service
  <service>/
    application/    Helm chart (Chart.yaml, values.yaml, templates/)
    infrastructure/ Terragrunt placeholder (N/A locally, used in cloud envs)
docs/               Architecture Decision Records and implementation plans
```

## Grafana dashboards

Six dashboards are pre-provisioned at startup:

| Dashboard | What it shows |
|-----------|--------------|
| Kubernetes Cluster | Node CPU/memory, pod counts |
| Node Exporter | Disk, network, system metrics |
| MinIO | Request rate, storage usage, errors |
| Loki Logs | Log volume and streams by namespace |
| Trino | Query counts and JVM metrics |
| Kubernetes Namespaces | Per-namespace resource usage |

## Adding a new service

Use the `/new-service` skill in Claude Code — it scaffolds the full structure automatically.

## License

MIT
