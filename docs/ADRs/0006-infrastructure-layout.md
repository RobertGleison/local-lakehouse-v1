---
status: draft
date: 2026-05-13
owner: Robert Pereira
superseded_by:
tags: [infrastructure, kubernetes, k3d, argocd, gitops, helm, secrets, pvcs, phase-1]
---
# 0006 — Infrastructure Layout: k3d, Argo CD, and Helm

## Context

[[0001-phase-1-storage-layer]] established that all services run on k3d and are managed by Argo CD from day 1. What that ADR does not define is the concrete shape of the infrastructure: how the cluster is configured, how Argo CD Applications are structured, how Helm charts are organised, how namespaces are allocated, how secrets are handled without committing plain credentials to Git, and which services need persistent storage.

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

The local volume mount (`local-datalake-storage`) maps k3s's PVC storage path to the Mac's local filesystem. This means PVC data survives both pod restarts and full `k3d cluster delete` + recreate cycles — the data lives on the Mac, not inside the Docker container.

Bootstrap installs the cluster and Argo CD only:
```bash
# infra/bootstrap.sh
k3d cluster create --config infra/cluster.yaml
helm repo add argo https://argoproj.github.io/argo-helm
helm install argocd argo/argo-cd --namespace argocd --create-namespace
```

After bootstrap, no further `kubectl` or `helm` commands are run. All subsequent state is applied via Argo CD.

### 2. How services are deployed: Git → Argo CD → Kubernetes objects

Every service follows the same deployment flow:

```
Git push to main
      │
      ▼ Argo CD detects drift
Argo CD runs helm template (or applies YAML directory)
      │
      ▼ Kubernetes objects created in the target namespace
  Deployment      ← stateless services (Trino, Dagster webserver, Cloudbeaver)
  StatefulSet     ← stateful services (MinIO, ClickHouse, Keycloak, Postgres)
  Job / CronJob   ← one-off or scheduled workloads (Dagster pipeline runs)
  Service         ← internal ClusterIP or LoadBalancer for exposed UIs
  Ingress         ← path-based routing through k3d's load balancer
  PVC             ← persistent storage claim (see section 4)
  Secret          ← decrypted by Sealed Secrets controller (see section 5)
```

Stateless services (`Deployment`) have no local state — they can be deleted and recreated freely. Stateful services (`StatefulSet`) are backed by a PVC; the pod can be restarted or rescheduled without data loss as long as the PVC exists.

### 3. Argo CD Application types

Three types of Argo CD Applications are used depending on whether a service has an upstream Helm chart:

```yaml
# Type 1 — upstream Helm chart + local values.yaml (most services)
# The chart is fetched from the upstream registry at sync time.
# This repo stores only the values overrides.
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: minio
  namespace: argocd
spec:
  sources:
    - repoURL: https://charts.bitnami.com/bitnami
      chart: minio
      targetRevision: 14.x
      helm:
        valueFiles:
          - $values/helm/minio/values.yaml
    - repoURL: <this-repo>       # second source: provides the values file
      targetRevision: main
      ref: values
  destination:
    server: https://kubernetes.default.svc
    namespace: phase-1
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

```yaml
# Type 2 — local YAML manifests directory (Cloudbeaver — no upstream Helm chart)
spec:
  source:
    repoURL: <this-repo>
    path: helm/cloudbeaver       # directory of plain Deployment + Service YAML
    targetRevision: main
```

```yaml
# Type 3 — local umbrella chart (Grafana stack: Loki + Prometheus + Grafana together)
spec:
  source:
    repoURL: <this-repo>
    path: helm/grafana-stack     # Chart.yaml with sub-chart dependencies
    targetRevision: main
```

Each phase has one Application manifest in `apps/`. Phases are activated explicitly:
```bash
kubectl apply -f apps/phase-1-storage.yaml
```

After that single command, Argo CD takes over and syncs the phase on every push to `main`.

### 4. Persistent Volumes

k3s ships with a built-in `local-path` storage class that provisions PVCs automatically from the node's local filesystem — no external storage driver needed. Combined with the k3d volume mount in `cluster.yaml`, PVC data persists on the Mac's disk and survives cluster recreation.

PVC declarations live in each service's `values.yaml`. Only services with durable data need PVCs:

| Service | Needs PVC | Storage class | Size | Reason |
|---|---|---|---|---|
| MinIO | Yes | `local-path` | 20 Gi | All Iceberg Parquet files (Bronze/Silver/Gold) |
| ClickHouse | Yes | `local-path` | 10 Gi | Columnar data; must survive scale-to-zero |
| OpenMetadata Postgres | Yes | `local-path` | 5 Gi | Table catalog and lineage metadata |
| Nessie | Yes | `local-path` | 2 Gi | RocksDB catalog history |
| Prometheus | Yes | `local-path` | 5 Gi | 15-day metrics retention |
| Keycloak Postgres | Yes | `local-path` | 2 Gi | User/role/client data |
| Dagster | No | — | — | Stateless; run history in a shared Postgres |
| Trino | No | — | — | Stateless query engine |
| Loki | No | — | — | Stores logs in MinIO, not locally |
| Cloudbeaver | No | — | — | Stateless web client |

PVC example in `values.yaml`:
```yaml
# helm/clickhouse/values.yaml
persistence:
  enabled: true
  storageClass: local-path
  size: 10Gi
```

### 5. Secrets: Sealed Secrets

Credentials (MinIO access keys, Keycloak admin password, database passwords) must be in Git to satisfy the GitOps principle. Plain Kubernetes Secrets must never be committed — they are base64-encoded, not encrypted.

**Sealed Secrets** (Bitnami) encrypts Secret manifests with the cluster's public key. The encrypted `SealedSecret` is safe to commit. The Sealed Secrets controller decrypts it and creates the real Kubernetes `Secret` at sync time.

**Flow from Git to pod:**

```
secrets/phase-1/minio-credentials.yaml   ← SealedSecret in Git (encrypted)
      │
      ▼ Argo CD syncs to cluster
SealedSecret object in cluster
      │
      ▼ Sealed Secrets controller decrypts with cluster private key
Kubernetes Secret object  (minio-credentials)
      │
      ▼ Pod references by name — never by value
env:
  - name: MINIO_ROOT_USER
    valueFrom:
      secretKeyRef:
        name: minio-credentials
        key: access-key
```

The `values.yaml` file references the Secret name only — never the credential value:
```yaml
# helm/minio/values.yaml
auth:
  existingSecret: minio-credentials    # name of the K8s Secret
```

**Workflow for creating a new secret:**
```bash
# 1. Generate the plain Secret (never committed)
kubectl create secret generic minio-credentials \
  --from-literal=access-key=minioadmin \
  --from-literal=secret-key=minioadmin \
  --dry-run=client -o yaml > /tmp/minio-secret.yaml

# 2. Encrypt with the cluster's public key
kubeseal --format yaml < /tmp/minio-secret.yaml \
  > secrets/phase-1/minio-credentials.yaml

# 3. Commit — safe
git add secrets/phase-1/minio-credentials.yaml
git commit -m "feat: add sealed minio credentials"
```

**Secrets by phase:**
```
secrets/
├── phase-1/
│   ├── minio-credentials.yaml         # MinIO root access key
│   └── nessie-config.yaml             # Nessie storage backend config
├── phase-2/
│   └── dagster-postgres.yaml          # Dagster run history DB password
├── phase-3/
│   ├── trino-config.yaml              # Trino MinIO connector credentials
│   └── clickhouse-credentials.yaml   # ClickHouse admin password
└── phase-4/
    ├── keycloak-admin.yaml            # Keycloak bootstrap admin password
    └── openmetadata-config.yaml       # OpenMetadata DB + JWT secrets
```

### 6. Namespace strategy

One Kubernetes namespace per phase. Cross-phase communication uses fully qualified DNS: `<service>.<namespace>.svc.cluster.local`.

```
argocd     Argo CD + Sealed Secrets controller
phase-1    MinIO, Nessie
phase-2    Dagster
phase-3    Trino, ClickHouse, Cloudbeaver
phase-4    Keycloak, OpenMetadata, Loki, Prometheus, Grafana
```

Tearing down a phase: `kubectl delete namespace phase-N` — removes all pods and services for that phase without touching others. PVC data is preserved (PVCs are namespace-scoped but the underlying volume on the Mac's disk remains).

### 7. Helm chart organisation

This repo stores only `values.yaml` overrides. Upstream chart files are not copied.

```
helm/
├── sealed-secrets/values.yaml     # Bitnami Sealed Secrets controller
├── minio/values.yaml              # bitnami/minio overrides
├── nessie/values.yaml             # projectnessie/nessie overrides
├── dagster/values.yaml            # dagster/dagster overrides
├── trino/values.yaml              # trino/trino overrides
├── clickhouse/values.yaml         # clickhouse/clickhouse overrides
├── cloudbeaver/
│   ├── deployment.yaml            # plain Deployment (no upstream chart)
│   └── service.yaml               # plain Service
├── keycloak/values.yaml           # bitnami/keycloak overrides
├── openmetadata/values.yaml       # open-metadata/openmetadata overrides
└── grafana-stack/
    ├── Chart.yaml                 # umbrella chart declaring sub-chart deps
    └── values.yaml                # overrides for Loki + Prometheus + Grafana
```

### 8. Full directory layout

```
local-datalake/
├── infra/
│   ├── cluster.yaml
│   └── bootstrap.sh
├── apps/
│   ├── phase-1-storage.yaml
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
│   ├── cloudbeaver/
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   ├── keycloak/values.yaml
│   ├── openmetadata/values.yaml
│   └── grafana-stack/
│       ├── Chart.yaml
│       └── values.yaml
├── secrets/
│   ├── phase-1/
│   ├── phase-2/
│   ├── phase-3/
│   └── phase-4/
├── pipelines/
│   ├── bronze/
│   ├── silver/
│   └── gold/
├── ADRs/
└── docs/
```

## Alternatives Considered

### Argo CD App of Apps pattern instead of individual Application manifests

The App of Apps pattern uses a single root `Application` that watches the `apps/` directory and auto-creates child Applications for every manifest it finds. It is the idiomatic Argo CD pattern for managing many applications at scale.

Rejected because:
1. It adds one layer of indirection — understanding why a service is not deployed requires tracing root Application → child Application.
2. Activating a phase via `kubectl apply -f apps/phase-N.yaml` is more explicit than a PR merge that auto-triggers discovery. In a learning environment, explicit activation is preferable.
3. App of Apps shines with 20+ applications across multiple teams. With 4 phases and a single operator, the complexity is not justified.

### Single namespace instead of per-phase namespaces

Simpler — no cross-namespace DNS. Rejected because:
1. `kubectl delete namespace phase-3` is the cleanest way to rebuild a single phase during learning.
2. Per-namespace resource usage is visible in Grafana without label filtering.
3. Service name collisions between phases are prevented at the namespace boundary.

### Local Helm chart copies (umbrella chart pattern)

Full chart files in this repo gives complete control but creates maintenance overhead — upstream security patches must be manually merged. Rejected: `values.yaml` overrides are the only customisation surface needed. Chart internals are upstream concerns.

### SOPS instead of Sealed Secrets

SOPS encrypts files with age/PGP/KMS. Rejected because Sealed Secrets is cluster-bound by design (a secret sealed for one cluster cannot be decrypted by another — a safety property), integrates natively with Argo CD as a CRD, and requires no external key management step.

### Plain Kubernetes Secrets not committed to Git

Keeps secrets out of Git via a one-time `setup-secrets.sh` script. Rejected: violates GitOps — the cluster cannot be fully rebuilt from Git alone. With Sealed Secrets, `git clone` + bootstrap + phase activation is a complete, repeatable rebuild.

## Consequences

**Positive:**
- Full cluster state — including secrets — is reproducible from `git clone` alone.
- The k3d volume mount means PVC data (MinIO, ClickHouse, Postgres) persists across cluster restarts and deletions.
- Per-phase namespaces align teardown and observability with the rollout stages.
- Individual Application manifests make each phase's activation a deliberate action.
- Remote Helm charts with local values keep the repo lean — only overrides, not chart boilerplate.
- `local-path` storage class requires no external storage driver — zero additional configuration for PVCs.

**Negative / trade-offs:**
- Sealed Secrets controller must be running before any `SealedSecret` can be synced. It is the first dependency installed in Phase 1.
- The Sealed Secrets private key lives in the cluster. If the cluster is deleted without backing up the key, all sealed secrets must be re-sealed against the new cluster's key: `kubectl get secret -n kube-system sealed-secrets-key -o yaml > sealed-secrets-key-backup.yaml`.
- Cross-phase service DNS (`minio.phase-1.svc.cluster.local`) is verbose. All `values.yaml` connection strings must use FQDNs — not short names.
- Cloudbeaver has no upstream Helm chart. Its `helm/cloudbeaver/` directory contains hand-maintained Kubernetes manifests that must be updated manually when upgrading Cloudbeaver.
- Dagster and Keycloak both need a Postgres database. Two separate Postgres `StatefulSet` deployments are required — one per service — adding ~400 MB RAM and two additional PVCs.
