.PHONY: help install deps cluster seal deploy stop start destroy argocd-password

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Setup ────────────────────────────────────────────────────────────────────

deps: ## Install prerequisites (macOS only)
	brew install k3d kubectl helm kubeseal

# ── Cluster lifecycle ────────────────────────────────────────────────────────

up: cluster seal ## Full bootstrap: create cluster, re-seal secrets, push, and deploy
	git add secrets/minio-credentials.yaml
	git commit -m "chore: re-seal secrets for new cluster"
	git push
	kubectl apply -f apps/

cluster: ## Create k3d cluster + install ArgoCD + Sealed Secrets
	bash infra/bootstrap.sh

stop: ## Pause the cluster (state is preserved)
	k3d cluster stop local-datalake

start: ## Resume a paused cluster
	k3d cluster start local-datalake

destroy: ## Delete the k3d cluster
	k3d cluster delete local-datalake

# ── Secrets ──────────────────────────────────────────────────────────────────

seal: ## Encrypt secrets with kubeseal (run before committing secrets)
	bash secrets/seal.sh

# ── Services ─────────────────────────────────────────────────────────────────

deploy: ## Apply all ArgoCD applications (MinIO, Nessie, Secrets)
	kubectl apply -f apps/

# ── Helpers ──────────────────────────────────────────────────────────────────

argocd-password: ## Print the ArgoCD admin password
	@kubectl get secret argocd-initial-admin-secret -n argocd \
		-o jsonpath="{.data.password}" | base64 -d && echo

argocd-ui: ## Port-forward ArgoCD UI to https://localhost:8080
	kubectl port-forward svc/argocd-server -n argocd 8080:443
