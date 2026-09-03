#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# undeploy.sh — Clean up all Superset resources in namespace
# Usage: ./scripts/undeploy.sh [namespace]
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

NAMESPACE="${1:-demo1}"

echo "============================================================"
echo "  Undeploying Superset from namespace '${NAMESPACE}'"
echo "============================================================"

echo "[1/5] Deleting MCP server..."
kubectl delete deployment superset-mcp -n "${NAMESPACE}" --ignore-not-found=true
kubectl delete service superset-mcp -n "${NAMESPACE}" --ignore-not-found=true

echo "[2/5] Deleting worker and webserver..."
kubectl delete deployment superset-worker -n "${NAMESPACE}" --ignore-not-found=true
kubectl delete deployment superset-webserver -n "${NAMESPACE}" --ignore-not-found=true
kubectl delete service superset-webserver -n "${NAMESPACE}" --ignore-not-found=true

echo "[3/5] Deleting init job..."
kubectl delete job superset-init -n "${NAMESPACE}" --ignore-not-found=true

echo "[4/5] Deleting postgres and redis..."
kubectl delete deployment superset-postgres -n "${NAMESPACE}" --ignore-not-found=true
kubectl delete service superset-postgres -n "${NAMESPACE}" --ignore-not-found=true
kubectl delete pvc superset-postgres-data -n "${NAMESPACE}" --ignore-not-found=true
kubectl delete deployment superset-redis -n "${NAMESPACE}" --ignore-not-found=true
kubectl delete service superset-redis -n "${NAMESPACE}" --ignore-not-found=true
kubectl delete pvc superset-home-pvc -n "${NAMESPACE}" --ignore-not-found=true

echo "[5/5] Deleting secrets and config..."
kubectl delete secret superset-secrets -n "${NAMESPACE}" --ignore-not-found=true
kubectl delete configmap superset-config -n "${NAMESPACE}" --ignore-not-found=true

echo ""
echo "============================================================"
echo "  Superset cleaned up from namespace '${NAMESPACE}'"
echo "  (PVC data preserved — delete manually if needed)"
echo "============================================================"
