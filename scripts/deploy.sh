#!/usr/bin/env bash
set -euo pipefail

# ── Config ──────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${SCRIPT_DIR}/config/.env"

if [ -f "${ENV_FILE}" ]; then
  set -a; source "${ENV_FILE}"; set +a
else
  NAMESPACE="${NAMESPACE:-demo1}"
  DOMAIN="${DOMAIN:-local.lan}"
  SUPERSET_PASSWORD="${SUPERSET_PASSWORD:-changeme}"
  SUPERSET_SECRET_KEY="${SUPERSET_SECRET_KEY:-changeme_superset_secret_key}"
  SUPERSET_ADMIN_USER="${SUPERSET_ADMIN_USER:-admin}"
  SUPERSET_ADMIN_PASSWORD="${SUPERSET_ADMIN_PASSWORD:-admin}"
  IMAGE="${IMAGE:-apache/superset:6.1.0}"
  export NAMESPACE DOMAIN SUPERSET_PASSWORD SUPERSET_SECRET_KEY
  export SUPERSET_ADMIN_USER SUPERSET_ADMIN_PASSWORD IMAGE
  SUPERSET_HOST="superset.${NAMESPACE}.${DOMAIN}"
  echo "[WARN] No .env found — using defaults."
fi

SUPERSET_HOST="superset.${NAMESPACE}.${DOMAIN}"
echo "=== Deploying Superset to namespace ${NAMESPACE} ==="
echo "  Image:     ${IMAGE}"
echo "  Host:      ${SUPERSET_HOST}"
echo "  Admin:     ${SUPERSET_ADMIN_USER}"

# ── 1. Remove old resources (stateless) ─────────────────────────────
echo "[1/6] Cleaning old resources..."
for name in superset-webserver superset-worker superset-ingress superset-svc superset-env superset-config; do
  kubectl delete -n "${NAMESPACE}" $name 2>/dev/null || true
done
kubectl delete -n "${NAMESPACE}" job superset-init 2>/dev/null || true

# ── 2. Apply manifest with substitution ─────────────────────────────
echo "[2/6] Applying manifests (substitution)..."
sed \
  -e "s|__NAMESPACE__|${NAMESPACE}|g" \
  -e "s|__SUPERSET_PASSWORD__|${SUPERSET_PASSWORD}|g" \
  -e "s|__SUPERSET_SECRET_KEY__|${SUPERSET_SECRET_KEY}|g" \
  -e "s|__SUPERSET_ADMIN_USER__|${SUPERSET_ADMIN_USER}|g" \
  -e "s|__SUPERSET_ADMIN_PASSWORD__|${SUPERSET_ADMIN_PASSWORD}|g" \
  -e "s|__SUPERSET_HOST__|${SUPERSET_HOST}|g" \
  -e "s|__IMAGE__|${IMAGE}|g" \
  "${SCRIPT_DIR}/manifests/superset-all.yaml" | kubectl apply -f -

# ── 3. Wait for init ────────────────────────────────────────────────
echo "[3/6] Waiting for pods to be ready (timeout 300s)..."
kubectl wait --for=condition=ready pod -l app=superset-webserver -n "${NAMESPACE}" --timeout=300s 2>/dev/null || true

# ── 4. Check status ─────────────────────────────────────────────────
echo "[4/6] Status:"
kubectl get pods -n "${NAMESPACE}" -l app=superset -o wide

# ── 5. Verify webserver ─────────────────────────────────────────────
echo "[5/6] Verifying webserver health..."
sleep 10
POD=$(kubectl get pods -n "${NAMESPACE}" -l app=superset-webserver -o jsonpath='{.items[0].metadata.name}')
if [ -n "$POD" ]; then
  kubectl exec "$POD" -n "${NAMESPACE}" -- curl -sf http://localhost:8088/health || echo "[WARN] Health check not ready yet"
else
  echo "[WARN] No webserver pod found"
fi

# ── 6. Summary ──────────────────────────────────────────────────────
echo "[6/6] Done."
echo ""
echo "=== Access Superset ==="
echo "  Ingress:  https://${SUPERSET_HOST}"
echo "  Port-fwd: kubectl port-forward svc/superset-svc 8088:8088 -n ${NAMESPACE}"
echo "  Admin:    ${SUPERSET_ADMIN_USER} / ${SUPERSET_ADMIN_PASSWORD}"
echo "  MCP:      http://localhost:5008 (port-fwd to superset-webserver)"
