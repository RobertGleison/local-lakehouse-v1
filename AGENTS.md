# AGENTS.md — Local Datalake

Local Kubernetes datalake (k3d) managed via ArgoCD GitOps. Services are upstream Helm chart wrappers under `infra/<name>/application/`.

## Cluster Lifecycle

```bash
make deps       # Install k3d, kubectl, helm, kubeseal (macOS)
make up         # Bootstrap cluster + reseal secrets + commit + push + deploy
make destroy    # Delete the k3d cluster
make stop       # Pause (state preserved)
make start      # Resume
```

`make up` = `make cluster` (`scripts/bootstrap.sh`) → `make seal` → git commit/push → `kubectl apply -f argocd/appsets/`.

## Local Verification (no cluster needed)

```bash
uv run yamllint .                                   # Lint all YAML
uv run pytest core/tests/ -v                        # Validate services.json registry
uv run python3 -m json.tool argocd/appsets/services.json > /dev/null  # Validate JSON
```

CI also runs gitleaks on push/PR. Python 3.12+, managed via `uv`. Dev deps: pytest, yamllint.

## Secrets

Never commit plaintext credentials. Workflow:
1. Edit credentials in `scripts/seal.sh` (keep them there, do NOT commit plaintext elsewhere)
2. Run `make seal` — encrypts into `infra/minio/application/templates/minio-credentials.yaml` and `infra/grafana/application/templates/grafana-admin.yaml`
3. Commit the sealed manifests and push — ArgoCD deploys them

Credentials stored in seal.sh: MinIO `minioadmin`/`minioadmin123`, Grafana `admin`/`admin`.
SealedSecrets use `namespace-wide` scope, decrypted by the controller in `kube-system`.

## ArgoCD Sync Waves (from `argocd/appsets/services.json`)

| Wave | Services |
|------|----------|
| 1 | minio, nessie |
| 2 | dagster |
| 3 | clickhouse, cloudbeaver, trino |
| 5 | prometheus, loki |
| 6 | promtail, grafana |

Add a new service: create `infra/<name>/application/` (Chart.yaml, values.yaml, templates/), then register it in `argocd/appsets/services.json` with the correct wave.

## Key Files

| File | Purpose |
|------|---------|
| `scripts/bootstrap.sh` | k3d cluster + ArgoCD + Sealed Secrets install |
| `scripts/seal.sh` | Encrypt raw credentials → SealedSecret manifests |
| `infra/cluster.yaml` | k3d cluster topology (1 server + 1 agent + port maps + volume) |
| `argocd/appsets/local-lakehouse.yaml` | Single ApplicationSet, matrix-generated from `services.json` + `clusters/*.json` |
| `argocd/appsets/services.json` | Service registry: name, Helm chart path, sync wave |
| `argocd/projects/infrastructure.yaml` | AppProject defining source/destination permissions |

## Conventions

- Commits: `feat:`, `fix:`, `chore:`, `docs:`
- ADRs in `docs/ADRs/` numbered sequentially (use `/adr` skill to scaffold)
- `.gitignore` excludes `*.unsealed.yaml`, `main.py`, `.venv`, `.superpowers/`, `docs/superpowers/`
- yamllint ignores `infra/*/application/templates/` (SealedSecret blobs)
- Service Helm charts are **local** (no upstream dependency) or **umbrella** wrapping a vendored `.tgz` in `charts/`
