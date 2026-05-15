#!/usr/bin/env bash
# Generates and seals MinIO and Nessie secrets for phase-1.
# Prerequisites: cluster running, sealed-secrets controller ready, kubeseal installed.
# Run: bash secrets/phase-1/seal.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Ensuring phase-1 namespace exists..."
kubectl create namespace phase-1 --dry-run=client -o yaml | kubectl apply -f -

echo "==> Sealing minio-credentials..."
kubectl create secret generic minio-credentials \
  --namespace phase-1 \
  --from-literal=root-user=minioadmin \
  --from-literal=root-password=minioadmin123 \
  --dry-run=client -o yaml \
| kubeseal --scope namespace-wide --format yaml \
  > "$SCRIPT_DIR/minio-credentials.yaml"

echo ""
echo "Sealed secrets written to secrets/phase-1/"
echo ""
echo "Next: commit and push, then activate phase 1:"
echo "  git add secrets/phase-1/minio-credentials.yaml"
echo "  git commit -m 'feat: add sealed phase-1 secrets'"
echo "  git push"
echo "  kubectl apply -f apps/phase-1-storage.yaml"
