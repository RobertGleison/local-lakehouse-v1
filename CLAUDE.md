# CLAUDE.md — Local Datalake

## Project Overview

Local Kubernetes datalake running entirely on a laptop via k3d (k3s in Docker). GitOps-managed by ArgoCD — the cluster always converges to what's in this repo.

**Phases:**
- **Phase 1 (complete):** Storage layer — k3d + ArgoCD + MinIO + Nessie
- **Phase 2 (complete):** Pipeline layer — Dagster + Celery
- **Phase 3 (complete):** Query layer — Trino + ClickHouse + CloudBeaver
- **Phase 4 (complete):** Observability — Prometheus + Loki + Promtail + Grafana

---

## Cluster Lifecycle

```bash
make deps       # Install prerequisites (k3d, kubectl, helm, kubeseal) — macOS only
make up         # Full bootstrap: cluster + seal secrets + push + deploy
make destroy    # Delete the k3d cluster entirely
```

`make up` calls `make cluster` (runs `infra/bootstrap.sh`), then `make seal`, commits the re-sealed secrets, pushes, and applies ArgoCD apps.

---

## Secret Management

Secrets are never committed in plaintext. The workflow is:

1. Edit credentials in `secrets/seal.sh` (do not commit plaintext)
2. Run `make seal` → outputs `secrets/minio-credentials.yaml` (SealedSecret)
3. Commit and push the sealed file — ArgoCD applies it automatically

The SealedSecret is scoped to the `local-datalake` namespace and can only be decrypted by the Sealed Secrets controller in the cluster.

---

## ArgoCD Sync Waves

Services deploy in dependency order:

| Wave | Services | Why |
|------|----------|-----|
| 0 | Sealed Secrets | Credentials must exist before anything else |
| 1 | MinIO | Storage layer — everything else depends on it |
| 2 | Nessie | Catalog depends on MinIO |
| 3 | Trino, ClickHouse, CloudBeaver | Query layer depends on Nessie + MinIO |
| 4 | Dagster | Orchestration depends on query layer |
| 5 | Prometheus, Loki | Metrics/logs collection before dashboards |
| 6 | Promtail, Grafana | Shippers and dashboards come last |

Set `argocd.argoproj.io/sync-wave` annotation in `argocd/appsets/<service>.yaml` to control ordering.

---

## Service Structure Convention

Every service lives under `services/<name>/`:

```
services/<name>/
  application/          Helm chart (Chart.yaml, values.yaml, templates/ or charts/*.tgz)
  infrastructure/       Terragrunt placeholder — unused locally, for cloud deployments
```

ArgoCD Application manifests live in `argocd/appsets/<name>.yaml` and point to `services/<name>/application`.

---

## Available Skills

| Skill | When to use |
|-------|-------------|
| `/new-service` | Scaffold a new service (Helm chart + ArgoCD Application) |
| `/adr` | Create an Architecture Decision Record in `docs/ADRs/` |

---

## Port Mappings

| Service | URL | Notes |
|---------|-----|-------|
| ArgoCD UI | https://localhost:8080 | `make argocd-ui` + `make argocd-password` |
| MinIO UI | http://localhost:9001 | minioadmin / minioadmin123 |
| MinIO API | http://localhost:9000 | S3-compatible endpoint |
| Nessie API | http://localhost:19120 | Iceberg REST catalog |
| Trino | http://localhost:8080 | Distributed SQL |
| ClickHouse | http://localhost:8123 | OLAP HTTP interface |
| CloudBeaver | http://localhost:8978 | Web SQL client |
| Dagster UI | http://localhost:3000 | `kubectl port-forward svc/dagster-dagster-webserver 3000:80 -n local-datalake` |
| Grafana | http://localhost:3000 | `kubectl port-forward svc/grafana 3000:80 -n local-datalake` |
| Loki | http://localhost:3100 | Log aggregation API |

---

## Common Operations

```bash
make deploy          # Re-apply all ArgoCD apps (after adding a new argocd/appsets/*.yaml)
make argocd-ui       # Port-forward ArgoCD to https://localhost:8080
make argocd-password # Print the ArgoCD admin password
make seal            # Re-encrypt secrets (after rotating credentials)
```

---

## Conventions

- **Commits:** Follow conventional commits (`feat:`, `fix:`, `chore:`, `docs:`). Use the `promptly-skills:commit` skill.
- **PRs:** Use the `promptly-skills:pr-writer` skill.
- **ADRs:** One ADR per significant architectural decision. Numbered sequentially under `docs/ADRs/`.
- **No CI/CD pipelines** — ArgoCD is the sole deployment mechanism; everything flows through GitOps.

---

## Key Files

| File | Purpose |
|------|---------|
| `infra/bootstrap.sh` | One-time cluster setup (k3d + ArgoCD + Sealed Secrets) |
| `infra/cluster.yaml` | k3d cluster config (nodes, port mappings, volumes) |
| `secrets/seal.sh` | Encrypts raw credentials into SealedSecret manifests |
| `argocd/appsets/*.yaml` | ArgoCD Application manifests — one per service |
| `Makefile` | All common operations; run `make help` for a summary |
