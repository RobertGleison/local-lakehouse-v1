---
name: new-service
description: Scaffold a new service deployment for the local datalake. Use when adding a new service, deploying a new component, creating a new Helm chart, or onboarding a new tool to the datalake (e.g. "add Spark", "deploy Trino", "new service").
argument-hint: "[service-name]"
allowed-tools: Read, Write, Bash, Glob
---

# Add a New Service to the Datalake

Scaffold the Helm chart and ArgoCD application for a new service following the project's established pattern.

## Folder structure

Every service follows this layout:

```
services/
  <service>/
    application/          ← Helm chart (owns the Kubernetes resources)
      Chart.yaml          ← chart metadata (name, version, description)
      values.yaml         ← all tuneable config (image, ports, resources, etc.)
      templates/          ← Helm renders ALL files here automatically
        deployment.yaml
        service.yaml
        pvc.yaml          ← only if the service needs persistent storage
    infrastructure/
      terragrunt.hcl      ← placeholder for local dev; real Terragrunt config for cloud envs

argocd/appsets/
  <service>.yaml          ← ArgoCD Application — points ArgoCD at the Helm chart
```

## File responsibilities

| File | Purpose |
|------|---------|
| `Chart.yaml` | Helm chart metadata. Required. Never references templates. |
| `values.yaml` | All config knobs. Templates read from here via `{{ .Values.xxx }}`. |
| `templates/*.yaml` | The actual Kubernetes resources (Deployment, Service, PVC, etc.). |
| `infrastructure/terragrunt.hcl` | Cloud infra (S3, IAM, DNS). Empty locally — k3s handles storage via PVC. |
| `argocd/appsets/<service>.yaml` | ArgoCD Application. Tells ArgoCD where the chart lives and where to deploy it. |

## Step 1: Create the Helm chart

Create `services/<service>/application/Chart.yaml`:
```yaml
apiVersion: v2
name: <service>
description: <one-line description of what this service does in the datalake>
type: application
version: 0.1.0
appVersion: "latest"
```

## Step 2: Define values

Create `services/<service>/application/values.yaml` with all configurable fields:
- `image.repository` and `image.tag`
- `replicaCount`
- `resources.requests` and `resources.limits`
- `service.port`
- `persistence` block if the service needs a PVC

## Step 3: Write templates

Create `services/<service>/application/templates/` with the required Kubernetes resources.

**Always include:**
- `deployment.yaml` — use `{{ .Values.image.repository }}:{{ .Values.image.tag }}`, `{{ .Release.Namespace }}`, `{{- toYaml .Values.resources | nindent 12 }}`
- `service.yaml` — selector must match `app: <service>` label on the pod

**Include only if needed:**
- `pvc.yaml` — if the service needs persistent storage (use `{{ .Values.persistence.storageClassName }}` and `{{ .Values.persistence.size }}`)
- `<init-job>.yaml` — if the service needs one-time setup after start (e.g. bucket creation)

Use `{{ .Release.Namespace }}` instead of hardcoding the namespace in every template.

## Step 4: Add the infrastructure placeholder

Create `services/<service>/infrastructure/terragrunt.hcl` with a comment explaining it's N/A for local dev. See `services/minio/infrastructure/terragrunt.hcl` as a reference.

## Step 5: Create the ArgoCD Application

Create `argocd/appsets/<service>.yaml`:
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: <service>
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "1"  # increase if this service depends on others
spec:
  project: default
  source:
    repoURL: https://github.com/RobertGleison/local-datalake
    path: services/<service>/application   # ArgoCD auto-detects Helm from Chart.yaml
    targetRevision: main
  destination:
    server: https://kubernetes.default.svc
    namespace: phase-1
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

## Step 6: Activate

If the cluster is running:
```bash
kubectl apply -f argocd/appsets/<service>.yaml
```

ArgoCD will pull the chart from git and deploy it. For secrets the service depends on, use wave `"0"` in a separate `argocd/appsets/<service>-secrets.yaml` and ensure they deploy first.

## Sync waves

| Wave | Purpose |
|------|---------|
| `"0"` | Secrets (SealedSecrets — must exist before pods start) |
| `"1"` | Services (MinIO, Nessie, Spark, etc.) |
| `"2"` | Services that depend on wave 1 (e.g. a query engine that needs the catalog) |

## Reference implementations

See `services/minio/` and `services/nessie/` for complete working examples of this pattern.
