#!/usr/bin/env bash
# Bootstrap: creates the k3d cluster and installs Argo CD + Sealed Secrets.
# Run once. After this, all state is applied via Argo CD.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "==> Creating k3d cluster..."
k3d cluster create --config "$SCRIPT_DIR/cluster.yaml"

echo "==> Adding Helm repos..."
helm repo add argo https://argoproj.github.io/argo-helm
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

echo "==> Installing Argo CD..."
helm install argocd argo/argo-cd \
  --namespace argocd \
  --create-namespace \
  --wait

echo "==> Installing Sealed Secrets controller..."
# Bootstrapped here (not via Argo CD) so the controller is ready before
# sealing secrets and before applying Argo CD Applications.
helm install sealed-secrets bitnami/sealed-secrets \
  --namespace argocd \
  --wait

echo ""
echo "Bootstrap complete."
echo ""
echo "Next steps:"
echo "  1. Seal secrets:      bash $REPO_ROOT/secrets/phase-1/seal.sh"
echo "  2. Commit sealed secrets and push to GitHub"
echo "  3. Activate phase 1:  kubectl apply -f $REPO_ROOT/apps/phase-1-storage.yaml"
