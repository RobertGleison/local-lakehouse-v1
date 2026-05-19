# Local Datalake

A local Kubernetes-based datalake for learning purposes. Runs entirely on your laptop using k3d (k3s in Docker), with GitOps managed by ArgoCD.

## Architecture

```
┌─────────────────────────────────────────┐
│              k3d Cluster                │
│                                         │
│  ┌──────────┐       ┌────────────────┐  │
│  │  MinIO   │       │    Nessie      │  │
│  │ (storage)│       │  (data catalog)│  │
│  └──────────┘       └────────────────┘  │
│                                         │
│  ┌──────────────────────────────────┐   │
│  │            ArgoCD                │   │
│  │  (watches GitHub, syncs cluster) │   │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

| Service | Role | Port |
|---------|------|------|
| MinIO | S3-compatible object storage (Bronze/Silver/Gold buckets) | 9000 (API), 9001 (UI) |
| Nessie | Git-like catalog for Iceberg table versioning | 19120 |
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

# 2. Seal your secrets
bash secrets/seal.sh

# 3. Commit and push sealed secrets to GitHub
git add secrets/phase-1/ && git commit -m "feat: add sealed secrets" && git push

# 4. Deploy all services via ArgoCD
kubectl apply -f apps/
```

ArgoCD will pull from GitHub and deploy MinIO and Nessie automatically.

## Accessing services

**ArgoCD UI:**
```bash
kubectl port-forward svc/argocd-server -n argocd 8080:443
# Open https://localhost:8080
# Username: admin
# Password:
kubectl get secret argocd-initial-admin-secret -n argocd -o jsonpath="{.data.password}" | base64 -d
```

**MinIO UI:** `http://localhost:9001`

**MinIO S3 API:** `http://localhost:9000`

**Nessie API:** `http://localhost:19120`

## Project structure

```
apps/               ArgoCD Application manifests (one per service)
infra/              Cluster setup (k3d config, bootstrap script)
secrets/            Secret management (seal.sh + sealed secret manifests)
services/           One directory per service
  <service>/
    application/    Helm chart (Chart.yaml, values.yaml, templates/)
    infrastructure/ Terragrunt placeholder (N/A locally, used in cloud envs)
```

## Adding a new service

Use the `/new-service` skill in Claude Code — it scaffolds the full structure automatically.

## License

MIT
