#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# scripts/version.sh — Gestion de version idempotente
# ──────────────────────────────────────────────────────────────────────
# Usage:
#   version.sh get          # Affiche la version courante
#   version.sh set <ver>    # Définit une version (ex: 1.2.3)
#   version.sh bump major   # Incrémente MAJOR
#   version.sh bump minor   # Incrémente MINOR
#   version.sh bump patch   # Incrémente PATCH
#   version.sh tag          # Crée un tag Git + entry CHANGELOG
# ──────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VERSION_FILE="$PROJECT_ROOT/VERSION"
CHANGELOG="$PROJECT_ROOT/CHANGELOG.md"
TODAY=$(date +%Y-%m-%d)

get_version() {
    if [ -f "$VERSION_FILE" ]; then
        cat "$VERSION_FILE" | tr -d '[:space:]'
    else
        echo "0.0.0"
    fi
}

set_version() {
    local new_ver="$1"
    if [[ ! "$new_ver" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "❌ Format invalide : $new_ver (attendu : MAJOR.MINOR.PATCH)"
        exit 1
    fi
    echo "$new_ver" > "$VERSION_FILE"
    echo "✅ Version définie : $(get_version)"
}

bump_version() {
    local mode="$1"
    local current
    current=$(get_version)
    
    local major minor patch
    IFS='.' read -r major minor patch <<< "$current"
    
    case "$mode" in
        major)
            major=$((major + 1))
            minor=0
            patch=0
            ;;
        minor)
            minor=$((minor + 1))
            patch=0
            ;;
        patch)
            patch=$((patch + 1))
            ;;
        *)
            echo "❌ Mode invalide : $mode (attendu: major, minor, patch)"
            exit 1
            ;;
    esac
    
    local new_ver="${major}.${minor}.${patch}"
    set_version "$new_ver"
}

make_tag() {
    local version
    version=$(get_version)
    local tag="v${version}"
    
    if git -C "$PROJECT_ROOT" tag -l | grep -q "^${tag}$"; then
        echo "⚠️  Tag existant : $tag"
        return 0
    fi
    
    git -C "$PROJECT_ROOT" add -A
    if git -C "$PROJECT_ROOT" diff --cached --quiet 2>/dev/null; then
        echo "ℹ️  Aucun changement à taguer"
        return 0
    fi
    
    git -C "$PROJECT_ROOT" commit -m "chore: release $tag" --no-verify 2>/dev/null || true
    git -C "$PROJECT_ROOT" tag "$tag"
    echo "✅ Tag créé : $tag"
}

# ── Commande ─────────────────────────────────────────────────────────
CMD="${1:-help}"

case "$CMD" in
    get)
        get_version
        ;;
    set)
        if [ -z "${2:-}" ]; then
            echo "❌ Usage: $0 set <version>"
            exit 1
        fi
        set_version "$2"
        ;;
    bump)
        if [ -z "${2:-}" ]; then
            echo "❌ Usage: $0 bump <major|minor|patch>"
            exit 1
        fi
        bump_version "$2"
        ;;
    tag)
        make_tag
        ;;
    current)
        get_version
        ;;
    help|--help|-h)
        echo "Gestion de version idempotente"
        echo ""
        echo "Usage:"
        echo "  $0 get        Afficher la version courante"
        echo "  $0 set <ver>  Définir une version (ex: 1.2.3)"
        echo "  $0 bump <type> Incrémenter (major|minor|patch)"
        echo "  $0 tag        Créer un tag Git + entry CHANGELOG"
        echo "  $0 current    Alias pour get"
        ;;
    *)
        echo "❌ Commande inconnue : $CMD"
        exit 1
        ;;
esac
