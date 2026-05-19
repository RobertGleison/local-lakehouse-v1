# Contributing

## Adding a new service

Each service lives under `services/<service>/` and follows this structure:

```
services/<service>/
  application/
    Chart.yaml          # Helm chart metadata
    values.yaml         # all configurable values
    templates/
      deployment.yaml
      service.yaml
      pvc.yaml          # only if persistent storage is needed
  infrastructure/
    terragrunt.hcl      # placeholder locally; real Terragrunt config for cloud
```

And an ArgoCD Application at `apps/<service>.yaml` pointing to `services/<service>/application`.

Use the `/new-service` skill in Claude Code to scaffold this automatically.

## Sync waves

Services deploy in order via ArgoCD sync waves:

| Wave | What goes here |
|------|---------------|
| `0` | Secrets (must exist before pods start) |
| `1` | Core services (MinIO, Nessie, etc.) |
| `2` | Services that depend on wave 1 |

## Secrets

Never commit raw secrets. Use `secrets/seal.sh` to encrypt them with Sealed Secrets before committing.

## GitOps flow

1. Make changes locally
2. Push to `main`
3. ArgoCD detects the change and syncs the cluster automatically

Manual sync: `kubectl apply -f apps/<service>.yaml`
