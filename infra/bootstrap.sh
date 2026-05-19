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
helm repo add sealed-secrets https://bitnami-labs.github.io/sealed-secrets
helm repo update

echo "==> Installing Argo CD..."
helm install argocd argo/argo-cd \
  --namespace argocd \
  --create-namespace \
  --wait

echo "==> Installing Sealed Secrets controller..."
# Bootstrapped here (not via Argo CD) so the controller is ready before
# sealing secrets and before applying Argo CD Applications.
helm install sealed-secrets sealed-secrets/sealed-secrets \
  --namespace kube-system \
  --create-namespace \
  --wait

echo ""
echo "Bootstrap complete."
echo ""
echo "Next steps:"
echo "  1. Seal secrets:      bash $REPO_ROOT/secrets/seal.sh"
echo "  2. Commit sealed secrets and push to GitHub"
echo "  3. Activate services: kubectl apply -f $REPO_ROOT/apps/"
