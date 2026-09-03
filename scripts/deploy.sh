#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# deploy.sh — One-command deploy of Superset on K8s
# Inspired by: ynotopec/superset-k8s
# Usage: ./scripts/deploy.sh [namespace] [version]
# Prerequisite: copy config/.env.example to config/.env and edit
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Paths ─────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${SCRIPT_DIR}/config/.env"
MANIFEST_DIR="${SCRIPT_DIR}/k8s"
VERSION_FILE="${SCRIPT_DIR}/VERSION"

# ── Defaults ──────────────────────────────────────────────────────
NAMESPACE="${2:-demo1}"
SUPERSET_VERSION="${3:-6.1.0}"
DOMAIN="${DOMAIN:-local.lan}"
SUPERSET_PASSWORD="${SUPERSET_PASSWORD:-changeme}"
SUPERSET_SECRET_KEY="${SUPERSET_SECRET_KEY:-changeme_superset_secret_key}"
SUPERSET_ADMIN_USER="${SUPERSET_ADMIN_USER:-admin}"
SUPERSET_ADMIN_PASSWORD="${SUPERSET_ADMIN_PASSWORD:-admin}"
SUPERSET_HOST="superset.${NAMESPACE}.${DOMAIN}"

# ── Load .env if present ─────────────────────────────────────────
if [ -f "${ENV_FILE}" ]; then
  set -a
  # shellcheck disable=SC1091
  . "${ENV_FILE}"
  set +a
  # Override with .env values (take precedence over defaults)
  NAMESPACE="${NAMESPACE:-$NAMESPACE}"
  SUPERSET_PASSWORD="${SUPERSET_PASSWORD:-$SUPERSET_PASSWORD}"
  SUPERSET_SECRET_KEY="${SUPERSET_SECRET_KEY:-$SUPERSET_SECRET_KEY}"
  SUPERSET_ADMIN_USER="${SUPERSET_ADMIN_USER:-$SUPERSET_ADMIN_USER}"
  SUPERSET_ADMIN_PASSWORD="${SUPERSET_ADMIN_PASSWORD:-$SUPERSET_ADMIN_PASSWORD}"
  DOMAIN="${DOMAIN:-$DOMAIN}"
  SUPERSET_HOST="superset.${NAMESPACE}.${DOMAIN}"
else
  echo "[WARN] No .env found — using defaults. Copy config/.env.example and edit first."
fi

# ── Safety check ──────────────────────────────────────────────────
if [ "${SUPERSET_PASSWORD}" = "changeme" ] && [ "${SUPERSET_SECRET_KEY}" = "changeme_superset_secret_key" ]; then
  echo "[WARN] Using default passwords! Edit .env before production use."
fi

# ── Validate ──────────────────────────────────────────────────────
if ! command -v kubectl &> /dev/null; then
  echo "[ERROR] kubectl not found. Install it first."
  exit 1
fi

if ! kubectl cluster-info &> /dev/null; then
  echo "[ERROR] Cannot connect to cluster. Check your kubeconfig."
  exit 1
fi

echo "============================================================"
echo "  Deploying Superset v${SUPERSET_VERSION} to namespace ${NAMESPACE}"
echo "  Host: ${SUPERSET_HOST}"
echo "  Image: apache/superset:${SUPERSET_VERSION}"
echo "============================================================"

# ── 0. Namespace ──────────────────────────────────────────────────
echo "[1/7] Creating namespace '${NAMESPACE}'..."
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

# ── 1. Secrets ────────────────────────────────────────────────────
echo "[2/7] Applying secrets..."
sed \
  -e "s|__NAMESPACE__|${NAMESPACE}|g" \
  -e "s|__SUPERSET_PASSWORD__|${SUPERSET_PASSWORD}|g" \
  -e "s|__SUPERSET_SECRET_KEY__|${SUPERSET_SECRET_KEY}|g" \
  -e "s|__SUPERSET_ADMIN_USER__|${SUPERSET_ADMIN_USER}|g" \
  -e "s|__SUPERSET_ADMIN_PASSWORD__|${SUPERSET_ADMIN_PASSWORD}|g" \
  "${MANIFEST_DIR}/02-secrets.yml" | kubectl apply -f -

# ── 2. ConfigMap ─────────────────────────────────────────────────
echo "[3/7] Applying ConfigMap..."
sed \
  -e "s|__NAMESPACE__|${NAMESPACE}|g" \
  "${MANIFEST_DIR}/08-configmap.yml" | kubectl apply -f -

# ── 3. PVC ────────────────────────────────────────────────────────
echo "[4/7] Applying PVC..."
sed \
  -e "s|__NAMESPACE__|${NAMESPACE}|g" \
  "${MANIFEST_DIR}/08-pvc-init.yml" | kubectl apply -f -

# ── 4. Postgres ───────────────────────────────────────────────────
echo "[5/7] Deploying PostgreSQL..."
sed \
  -e "s|__NAMESPACE__|${NAMESPACE}|g" \
  -e "s|__SUPERSET_PASSWORD__|${SUPERSET_PASSWORD}|g" \
  "${MANIFEST_DIR}/03-postgres.yml" | kubectl apply -f -

# ── 5. Redis ──────────────────────────────────────────────────────
echo "[6/7] Deploying Redis..."
sed \
  -e "s|__NAMESPACE__|${NAMESPACE}|g" \
  "${MANIFEST_DIR}/05-redis.yml" | kubectl apply -f -

# ── 6. Wait for PostgreSQL ───────────────────────────────────────
echo "[6.5] Waiting for PostgreSQL ready..."
kubectl wait --for=condition=ready pod -l app=superset-postgres -n "${NAMESPACE}" --timeout=120s || {
  echo "[WARN] PostgreSQL not ready after 120s, continuing anyway..."
}

# ── 7. Init Job (migrations + admin) ─────────────────────────────
echo "[7/7] Running init job (migrations + admin user)..."
sed \
  -e "s|__NAMESPACE__|${NAMESPACE}|g" \
  -e "s|__SUPERSET_PASSWORD__|${SUPERSET_PASSWORD}|g" \
  -e "s|__SUPERSET_ADMIN_USER__|${SUPERSET_ADMIN_USER}|g" \
  -e "s|__SUPERSET_ADMIN_PASSWORD__|${SUPERSET_ADMIN_PASSWORD}|g" \
  "${MANIFEST_DIR}/08-pvc-init.yml" | kubectl apply -f -

kubectl wait --for=condition=complete job/superset-init -n "${NAMESPACE}" --timeout=300s

# ── 8. Deploy webserver + worker + mcp (shared config applied) ──
echo "[8/7] Deploying webserver, worker, MCP..."
for f in "${MANIFEST_DIR}"/04-webserver.yml "${MANIFEST_DIR}"/06-worker.yml "${MANIFEST_DIR}"/07-mcp.yml; do
  sed \
    -e "s|__NAMESPACE__|${NAMESPACE}|g" \
    -e "s|__SUPERSET_HOST__|${SUPERSET_HOST}|g" \
    "$f" | kubectl apply -f -
done

# ── 9. Verify ────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  Verifying deployment..."
echo "============================================================"
sleep 5

echo ""
echo "--- Pods ---"
kubectl get pods -n "${NAMESPACE}" -l app=superset 2>/dev/null || true

echo ""
echo "--- Services ---"
kubectl get svc -n "${NAMESPACE}" 2>/dev/null || true

echo ""
echo "--- Jobs ---"
kubectl get jobs -n "${NAMESPACE}" 2>/dev/null || true

echo ""
echo "============================================================"
echo "  Deployed successfully!"
echo "============================================================"
echo "  Ingress:  https://${SUPERSET_HOST}"
echo "  Port-fwd: kubectl port-forward svc/superset-webserver 8088:8088 -n ${NAMESPACE}"
echo "  MCP:      kubectl port-forward svc/superset-mcp 5008:5008 -n ${NAMESPACE}"
echo ""
echo "  Admin: ${SUPERSET_ADMIN_USER} / ${SUPERSET_ADMIN_PASSWORD}"
echo "  Database: ${SUPERSET_PASSWORD}"
echo "============================================================"
