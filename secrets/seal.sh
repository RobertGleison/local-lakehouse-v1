#!/usr/bin/env bash
# Generates and seals MinIO and Nessie secrets for local-datalake.
# Prerequisites: cluster running, sealed-secrets controller ready, kubeseal installed.
# Run: bash secrets/local-datalake/seal.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Ensuring local-datalake namespace exists..."
kubectl create namespace local-datalake --dry-run=client -o yaml | kubectl apply -f -

echo "==> Sealing minio-credentials..."
kubectl create secret generic minio-credentials \
  --namespace local-datalake \
  --from-literal=root-user=minioadmin \
  --from-literal=root-password=minioadmin123 \
  --dry-run=client -o yaml \
| kubeseal \
  --controller-name sealed-secrets \
  --controller-namespace kube-system \
  --scope namespace-wide \
  --format yaml \
  > "$SCRIPT_DIR/minio-credentials.yaml"

echo "==> Sealing grafana-admin..."
kubectl create secret generic grafana-admin \
  --namespace local-datalake \
  --from-literal=admin-user=admin \
  --from-literal=admin-password=admin \
  --dry-run=client -o yaml \
| kubeseal \
  --controller-name sealed-secrets \
  --controller-namespace kube-system \
  --scope namespace-wide \
  --format yaml \
  > "$SCRIPT_DIR/grafana-admin.yaml"

echo ""
echo "Sealed secrets written to secrets/"
echo ""
echo "Next: commit and push, then deploy:"
echo "  git add secrets/minio-credentials.yaml"
echo "  git commit -m 'feat: add sealed local-datalake secrets'"
echo "  git push"
echo "  kubectl apply -f apps/"
