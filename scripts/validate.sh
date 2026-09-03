#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# scripts/validate.sh — Vérification de l'intégrité du projet
# ──────────────────────────────────────────────────────────────────────
# Idempotence : lecture seule, aucun état modifié
# ──────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ERRORS=0
WARNINGS=0

info()  { echo "ℹ️  $*"; }
ok()    { echo "✅ $*"; }
warn()  { echo "⚠️  $*"; WARNINGS=$((WARNINGS + 1)); }
fail()  { echo "❌ $*"; ERRORS=$((ERRORS + 1)); }

echo "🔍 Validation de ${PROJECT_ROOT##*/}..."
echo ""

# ── 1. Git ─────────────────────────────────────────────────────────
if [ -d "$PROJECT_ROOT/.git" ]; then
    ok "Git initialisé"
    if git -C "$PROJECT_ROOT" log --oneline -1 >/dev/null 2>&1; then
        ok "Au moins un commit"
    else
        fail "Aucun commit dans Git"
    fi
else
    fail "Git non initialisé (pas de .git/)"
fi

# ── 2. Fichiers essentiels ─────────────────────────────────────────
REQUIRED_FILES=("VERSION" "README.md" "CHANGELOG.md" "LICENSE" ".gitignore")
for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$PROJECT_ROOT/$file" ]; then
        ok "Fichier présent : $file"
    else
        fail "Fichier manquant : $file"
    fi
done

# ── 3. VERSION ────────────────────────────────────────────────────
if [ -f "$PROJECT_ROOT/VERSION" ]; then
    VERSION=$(cat "$PROJECT_ROOT/VERSION" | tr -d '[:space:]')
    if [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        ok "VERSION valide : $VERSION"
    elif [[ "$VERSION" =~ ^[0-9]+\.[0-9]+$ ]]; then
        warn "VERSION au format mineur : $VERSION"
    else
        fail "VERSION invalide : $VERSION (attendu : MAJOR.MINOR.PATCH)"
    fi
else
    fail "Fichier VERSION manquant"
fi

# ── 4. Structure des répertoires ───────────────────────────────────
for dir in src tests config scripts; do
    if [ -d "$PROJECT_ROOT/$dir" ]; then
        ok "Répertoire présent : $dir/"
    else
        warn "Répertoire manquant : $dir/"
    fi
done

# ── 5. README.md ───────────────────────────────────────────────────
if [ -f "$PROJECT_ROOT/README.md" ]; then
    README_SIZE=$(wc -c < "$PROJECT_ROOT/README.md")
    if [ "$README_SIZE" -lt 50 ]; then
        warn "README.md très court ($README_SIZE octets) — probablement incomplet"
    else
        ok "README.md présent ($README_SIZE octets)"
    fi
else
    fail "README.md manquant"
fi

# ── 6. Conventional Commits ────────────────────────────────────────
if git -C "$PROJECT_ROOT" log --oneline >/dev/null 2>&1; then
    BAD_COMMITS=$(git -C "$PROJECT_ROOT" log --oneline 2>/dev/null | grep -cv "^[0-9a-f]* [a-z]*:.*" || true)
    BAD_COMMITS="${BAD_COMMITS:-0}"
    if [ "$BAD_COMMITS" -gt 0 ]; then
        warn "Certains commits ne suivent pas Conventional Commits (attendu: type: message)"
        git -C "$PROJECT_ROOT" log --oneline | grep -v "^[0-9a-f]* [a-z]*:.*" | sed 's/^/  → /'
    else
        ok "Tous les commits suivent Conventional Commits"
    fi
fi

# ── 7. Résumé ──────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║        Résultat de la validation        ║"
echo "╠══════════════════════════════════════════╣"
printf "║  Erreurs : %-14d  ║\n" "$ERRORS"
printf "║  Warnings: %-14d  ║\n" "$WARNINGS"
if [ "$ERRORS" -eq 0 ] && [ "$WARNINGS" -eq 0 ]; then
    printf "║  Statut : %-13s  ║\n" "✅ OK"
elif [ "$ERRORS" -eq 0 ]; then
    printf "║  Statut : %-13s  ║\n" "⚠️  OK (warnings)"
else
    printf "║  Statut : %-13s  ║\n" "❌ ÉCHEC"
fi
echo "╚══════════════════════════════════════════╝"

if [ "$ERRORS" -gt 0 ]; then
    exit 1
fi
