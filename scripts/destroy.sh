#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# scripts/destroy.sh — Cleanup idempotent
# ──────────────────────────────────────────────────────────────────────
# Idempotence : ne supprime JAMAIS .git/ ni les fichiers essentiels
# Peut être relancé indéfiniment sans effet secondaire
# ──────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🗑️  Cleanup de ${PROJECT_ROOT##*/}..."
echo "ℹ️  Garde : .git/, src/, tests/, config/, scripts/"
echo ""

# ── 1. Build artifacts ──────────────────────────────────────────────
echo "📦 Suppression des build artifacts..."
for pattern in "__pycache__" "*.pyc" "*.pyo" "*.pyd" ".Python" "venv/" ".venv/" "env/" "*.egg-info/" "dist/" "build/" "*.egg"; do
    find "$PROJECT_ROOT" -maxdepth 3 -name "$pattern" -exec rm -rf {} + 2>/dev/null || true
done
echo "  ✅ Cleaned build artifacts"

# ── 2. Node artifacts ───────────────────────────────────────────────
echo "📦 Suppression de node_modules..."
if [ -d "$PROJECT_ROOT/node_modules" ]; then
    rm -rf "$PROJECT_ROOT/node_modules"
    find "$PROJECT_ROOT" -name "package-lock.json" -delete 2>/dev/null || true
    find "$PROJECT_ROOT" -name "yarn.lock" -delete 2>/dev/null || true
    echo "  ✅ Cleaned node_modules"
else
    echo "  ℹ️  node_modules non trouvé"
fi

# ── 3. Rust artifacts ───────────────────────────────────────────────
echo "📦 Suppression de Cargo.lock / target..."
if [ -d "$PROJECT_ROOT/target" ]; then
    rm -rf "$PROJECT_ROOT/target"
    echo "  ✅ Cleaned target/"
else
    echo "  ℹ️  target/ non trouvé"
fi

# ── 4. IDE / OS files ───────────────────────────────────────────────
echo "📦 Suppression des fichiers IDE/OS..."
find "$PROJECT_ROOT" -name ".DS_Store" -delete 2>/dev/null || true
find "$PROJECT_ROOT" -name "Thumbs.db" -delete 2>/dev/null || true
find "$PROJECT_ROOT" -name "*.swp" -delete 2>/dev/null || true
find "$PROJECT_ROOT" -name "*.swo" -delete 2>/dev/null || true
find "$PROJECT_ROOT" -name "*~" -delete 2>/dev/null || true
echo "  ✅ Cleaned IDE/OS files"

# ── 5. Temp files ───────────────────────────────────────────────────
echo "📦 Suppression des fichiers temporaires..."
for pattern in "tmp/" "temp/" "tempfile*" "tmpfile*" "*.tmp"; do
    find "$PROJECT_ROOT" -maxdepth 2 -name "$pattern" -exec rm -rf {} + 2>/dev/null || true
done
echo "  ✅ Cleaned temp files"

# ── 6. Backup files (version.sh) ────────────────────────────────────
echo "📦 Suppression des backups..."
rm -f "$PROJECT_ROOT/VERSION.bak" 2>/dev/null || true
rm -f "$PROJECT_ROOT/VERSION.tmp" 2>/dev/null || true
echo "  ✅ Cleaned backups"

echo ""
echo "🎉 Cleanup terminé (fichiers essentiels préservés)"
