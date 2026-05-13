---
status: draft
date: 2026-05-13
owner: Robert Pereira
superseded_by:
tags: [infrastructure, kubernetes, k3d, argocd, gitops, helm, secrets, phase-1]
---
# 0006 — Infrastructure Layout: k3d, Argo CD, and Helm

## Context

[[0001-phase-1-storage-layer]] established that all services run on k3d and are managed by Argo CD from day 1. What that ADR does not define is the concrete shape of the infrastructure: how the cluster is configured, how Argo CD Applications are structured, how Helm charts are organised, how namespaces are allocated, and how secrets are handled without committing plain credentials to Git.

These decisions affect every phase of the project. A poor namespace strategy or a secret management approach that conflicts with GitOps will cause friction at every subsequent phase. This ADR defines the infrastructure conventions that all phases follow.

## Decision

### 1. k3d cluster topology

The cluster is defined in `infra/cluster.yaml` as a single server node with no dedicated agent nodes. The k3s server node runs both the control plane and workloads. This is the minimum viable topology for a learning environment — it saves ~200–400 MB RAM compared to a server + agent split.

```yaml
# infra/cluster.yaml
apiVersion: k3d.io/v1alpha5
kind: Simple
metadata:
  name: local-datalake
servers: 1
agents: 0
ports:
  - port: 8080:80@loadbalancer    # Argo CD, Grafana, Dagster, Cloudbeaver UIs
  - port: 8443:443@loadbalancer   # HTTPS (Keycloak)
  - port: 9000:9000@loadbalancer  # MinIO API
  - port: 9001:9001@loadbalancer  # MinIO console
volumes:
  - volume: local-datalake-storage:/var/lib/rancher/k3s/storage
    nodeFilters:
      - server:0
options:
  k3s:
    extraArgs:
      - arg: --disable=traefik    # replaced by Argo CD ingress management
        nodeFilters:
          - server:0
```

The local volume mount (`local-datalake-storage`) provides the backing store for all PersistentVolumeClaims — including ClickHouse (see [[0004-phase-3-query-layer]]) and OpenMetadata's Postgres backend.

Bootstrap installs the cluster and Argo CD only:
```bash
# infra/bootstrap.sh
k3d cluster create --config infra/cluster.yaml
helm repo add argo https://argoproj.github.io/argo-helm
helm install argocd argo/argo-cd --namespace argocd --create-namespace
```

After bootstrap, no further `kubectl` or `helm` commands are run. All subsequent state is applied via Argo CD.

### 2. Argo CD Application structure

Each phase is an independent Argo CD `Application` manifest in `apps/`. Phases are activated explicitly by applying their manifest — there is no automatic discovery. This avoids the App of Apps indirection and makes each phase's activation a deliberate, visible action.

```
apps/
├── phase-1-storage.yaml      # MinIO + Nessie
├── phase-2-pipeline.yaml     # Dagster
├── phase-3-query.yaml        # Trino + ClickHouse + Cloudbeaver
└── phase-4-govern.yaml       # Keycloak + OpenMetadata + Grafana stack
```

**Activating a phase:**
```bash
kubectl apply -f apps/phase-1-storage.yaml
```

After that, Argo CD watches the `helm/minio/` and `helm/nessie/` directories in Git and syncs on every push to `main`. No further manual commands needed.

Each Application manifest follows this structure:
```yaml
# apps/phase-1-storage.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: phase-1-storage
  namespace: argocd
spec:
  project: default
  source:
    repoURL: <this-repo>
    targetRevision: main
    path: helm/minio          # points to the local values directory
  destination:
    server: https://kubernetes.default.svc
    namespace: phase-1
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

For services that use an upstream Helm chart (not a local chart), the Application uses a `helm` source type with `repoURL` pointing to the upstream chart registry and `valueFiles` pointing to this repo's values file.

### 3. Namespace strategy

One Kubernetes namespace per phase. Services within a phase share a namespace. Cross-phase communication (e.g. Dagster writing to MinIO in `phase-1`) uses fully qualified service DNS names: `minio.phase-1.svc.cluster.local`.

```
phase-1    MinIO, Nessie
phase-2    Dagster
phase-3    Trino, ClickHouse, Cloudbeaver
phase-4    Keycloak, OpenMetadata, Loki, Prometheus, Grafana
argocd     Argo CD (installed by bootstrap)
```

This maps directly to the rollout structure — tearing down a phase is `kubectl delete namespace phase-N`. It also makes resource usage per phase visible in Grafana (filter by namespace).

### 4. Helm chart organisation

Upstream Helm charts are referenced by URL in the Argo CD Application spec. This repo stores only the `values.yaml` overrides — not the chart files themselves. Charts are fetched by Argo CD at sync time from their canonical registries.

```
helm/
├── minio/
│   └── values.yaml           # overrides for bitnami/minio
├── nessie/
│   └── values.yaml           # overrides for projectnessie/nessie
├── trino/
│   └── values.yaml           # overrides for trino/trino
├── clickhouse/
│   └── values.yaml           # overrides for clickhouse/clickhouse
├── dagster/
│   └── values.yaml           # overrides for dagster/dagster
├── keycloak/
│   └── values.yaml           # overrides for bitnami/keycloak
├── openmetadata/
│   └── values.yaml           # overrides for open-metadata/openmetadata
└── grafana-stack/
    └── values.yaml           # overrides for grafana/loki-stack (Loki + Promtail + Grafana)
```

Values files contain only the keys that differ from the chart defaults: replica counts, resource limits, storage sizes, service types, and environment-specific connection strings. Full chart defaults are not copied.

### 5. Secrets management: Sealed Secrets

Credentials (MinIO access keys, Keycloak admin password, database passwords) must be in Git to satisfy the GitOps "Git is the single source of truth" principle. Plain Kubernetes Secrets (base64-encoded) must never be committed — they are not encrypted, only encoded.

**Sealed Secrets** (Bitnami) encrypts Secret manifests with the cluster's public key. The encrypted `SealedSecret` manifest is safe to commit. The Sealed Secrets controller in the cluster decrypts it with the cluster's private key and creates the real Kubernetes Secret.

```
helm/
└── sealed-secrets/
    └── values.yaml           # Sealed Secrets controller (installed in phase-1)

secrets/
├── phase-1/
│   ├── minio-credentials.yaml      # SealedSecret — safe to commit
│   └── nessie-config.yaml
├── phase-2/
│   └── dagster-secrets.yaml
├── phase-3/
│   ├── trino-config.yaml
│   └── clickhouse-credentials.yaml
└── phase-4/
    ├── keycloak-admin.yaml
    └── openmetadata-config.yaml
```

**Workflow for creating a new secret:**
```bash
# 1. Create the plain Secret manifest (never committed)
kubectl create secret generic minio-credentials \
  --from-literal=access-key=minioadmin \
  --from-literal=secret-key=minioadmin \
  --dry-run=client -o yaml > /tmp/minio-secret.yaml

# 2. Seal it with the cluster's public key
kubeseal --format yaml < /tmp/minio-secret.yaml > secrets/phase-1/minio-credentials.yaml

# 3. Commit the sealed manifest — safe
git add secrets/phase-1/minio-credentials.yaml
git commit -m "feat: add sealed minio credentials"
```

Argo CD syncs the `SealedSecret` to the cluster. The controller creates the real `Secret` automatically.

### 6. Full directory layout

```
local-datalake/
├── infra/
│   ├── cluster.yaml              # k3d cluster definition
│   └── bootstrap.sh              # k3d create + Argo CD install only
├── apps/
│   ├── phase-1-storage.yaml      # Argo CD Application
│   ├── phase-2-pipeline.yaml
│   ├── phase-3-query.yaml
│   └── phase-4-govern.yaml
├── helm/
│   ├── sealed-secrets/values.yaml
│   ├── minio/values.yaml
│   ├── nessie/values.yaml
│   ├── dagster/values.yaml
│   ├── trino/values.yaml
│   ├── clickhouse/values.yaml
│   ├── cloudbeaver/values.yaml   # deployed as a plain Deployment (no Helm chart)
│   ├── keycloak/values.yaml
│   ├── openmetadata/values.yaml
│   └── grafana-stack/values.yaml
├── secrets/
│   ├── phase-1/                  # SealedSecret manifests — safe to commit
│   ├── phase-2/
│   ├── phase-3/
│   └── phase-4/
├── pipelines/                    # see [[0002-phase-2-pipeline-layer]]
│   ├── bronze/
│   ├── silver/
│   └── gold/
├── ADRs/
└── docs/
```

## Alternatives Considered

### Argo CD App of Apps pattern instead of individual Application manifests

The App of Apps pattern uses a single root `Application` that watches the `apps/` directory and auto-creates child Applications for every manifest it finds. It is the idiomatic Argo CD pattern for managing many applications at scale.

It was rejected for this project because:
1. It adds one layer of indirection between Git and the cluster state. Understanding why a service is or is not deployed requires tracing through the root Application → child Application chain.
2. Activating a phase by merging a PR (App of Apps) is less explicit than `kubectl apply -f apps/phase-N.yaml`. For a learning environment, the explicit apply makes the activation step visible and intentional.
3. App of Apps shines when managing 20+ applications across multiple teams. With 4 phases and a single operator, the added complexity is not justified.

### Single namespace instead of per-phase namespaces

A single `datalake` namespace for all services is simpler — no cross-namespace DNS, no namespace-level RBAC configuration. Rejected because:
1. Per-phase namespaces make it possible to tear down a single phase (`kubectl delete namespace phase-3`) without affecting the rest of the stack. This is a common learning operation — "let me rebuild Phase 3 from scratch."
2. Namespace-level resource quotas in Grafana make the RAM budget per phase visible at runtime.
3. Phase isolation prevents accidental service name collisions between phases.

### Local Helm chart copies instead of upstream charts with values overrides

Copying full chart files into the repo (umbrella chart pattern) gives complete control over chart contents and avoids upstream changes breaking the cluster. Rejected because:
1. Helm chart files are large (hundreds of YAML lines). Copying them creates maintenance overhead — upstream security patches must be manually merged.
2. Argo CD's Helm source type with `repoURL` pointing to upstream registries is the standard GitOps pattern. Chart updates are a one-line version bump in the Application spec.
3. The `values.yaml` files in this repo are the only customisation surface needed. Chart internals are upstream concerns.

### SOPS instead of Sealed Secrets

SOPS (Mozilla) encrypts YAML/JSON files with age, PGP, or cloud KMS keys. It is a general-purpose file encryption tool, not Kubernetes-specific. It was considered and rejected because:
1. Sealed Secrets is cluster-bound by design — a secret sealed for one cluster cannot be decrypted by another. This is a safety property: accidentally deploying to the wrong cluster does not expose secrets.
2. Sealed Secrets integrates natively with Argo CD as a CRD — no external decryption step in CI/CD.
3. SOPS requires managing a separate key (age or PGP key) and a decryption step in Argo CD. For a local learning environment, Sealed Secrets is simpler to operate.

### Plain Kubernetes Secrets (not committed) with a setup script

An alternative approach: keep secrets out of Git entirely, managed by a one-time `setup-secrets.sh` script. This avoids encryption tooling but violates the GitOps principle — the cluster cannot be fully rebuilt from Git alone. Rejected on principle: if the cluster is rebuilt (common in a learning environment), secrets must be reapplied manually. With Sealed Secrets, `git clone` + bootstrap + `kubectl apply` is a complete rebuild.

## Consequences

**Positive:**
- The full cluster state is reproducible from `git clone` alone. Sealed Secrets ensures credentials are in Git without security risk.
- Per-phase namespaces align activation, teardown, and observability with the rollout stages.
- Individual Application manifests make each phase's activation explicit — no magic auto-discovery.
- Remote Helm charts with local values keep the repo focused: only customisations live here, not chart boilerplate.
- The k3d volume mount ensures PVC-backed services (ClickHouse, OpenMetadata Postgres) survive cluster restarts.

**Negative / trade-offs:**
- Sealed Secrets introduces a bootstrap dependency: the Sealed Secrets controller must be running before any `SealedSecret` manifest can be synced. It must be installed in Phase 1 alongside MinIO and Nessie.
- If the k3d cluster is destroyed with `k3d cluster delete`, the Sealed Secrets controller's private key is lost. Sealed Secrets cannot be decrypted by a new cluster. The private key must be backed up before cluster deletion: `kubectl get secret -n kube-system sealed-secrets-key -o yaml > sealed-secrets-key-backup.yaml`.
- Cross-phase service communication requires fully qualified DNS names (`service.namespace.svc.cluster.local`), which are longer than single-namespace names. Values files must use these FQDNs for connection strings.
- Cloudbeaver has no official Helm chart. It is deployed as a plain Kubernetes `Deployment` + `Service` manifest under `helm/cloudbeaver/`, managed by Argo CD as a directory-type Application (not a Helm Application).
