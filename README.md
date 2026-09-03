# Dashboard Superset MCP

> Automatisation de dashboards Apache Superset via le serveur MCP natif (6.1.0+).

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    AI Agent / CLI                        │
│  (Hermes, Claude, GPT, ou script personnalisé)           │
└──────────────────────┬───────────────────────────────────┘
                       │ MCP JSON-RPC 2.0 (Streamable HTTP)
                       ▼
┌──────────────────────────────────────────────────────────┐
│              MCP Orchestrator (cette lib)                 │
│  ┌────────────────────────────────────────────────────┐  │
│  │  SequentialLayer                                    │  │
│  │  - Sémaphore: 1 opération à la fois                  │  │
│  │  - Verify-before-retry: état vérifié avant retry     │  │
│  │  - Idempotence: noms déterministes                   │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────┐  │
│  │  MCP Client                                         │  │
│  │  - JSON-RPC 2.0 over HTTP                          │  │
│  │  - JWT auth via Superset                          │  │
│  │  - Retry avec backoff (max 3)                       │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│              Superset MCP Server (6.1.0+)                 │
│  `superset mcp run --host 0.0.0.1 --port 5008`           │
│                                                          │
│  Outils disponibles:                                     │
│  ├─ generate_chart                                       │
│  ├─ generate_dashboard                                   │
│  ├─ add_chart_to_existing_dashboard                      │
│  ├─ create_virtual_dataset                               │
│  ├─ get_chart_info / list_charts                         │
│  ├─ get_dashboard_info / list_dashboards                 │
│  └─ ... (20 outils au total)                             │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│              Superset Instance                            │
│  PostgreSQL + Redis + Web UI                             │
└──────────────────────────────────────────────────────────┘
```

## Workflow

```
1. Vérifier datasource existante
2. Créer dataset (si nécessaire) → verify
3. Créer charts séquentiellement → verify chaque chart
4. Créer dashboard → attach charts
5. Publier le dashboard
6. Vérifier le résultat final
```

## Quick Start

```bash
# Installation
pip install -e .

# Configuration (fichier .env ou variables d'environnement)
export SUPERSET_BASE_URL=https://superset.example.com
export SUPERSET_USERNAME=admin
export SUPERSET_PASSWORD=admin
export MCP_HOST=127.0.0.1
export MCP_PORT=5008

# Lancer la CLI
python -m dashboard_superset_mcp create-dashboard \
    --name "My Dashboard" \
    --charts my_chart_1 my_chart_2
```

## Déploiement Superset

```bash
# Superset 6.1.0+ avec MCP natif
docker run -d \
  --name superset \
  -e SUPERSET_CONFIG_PATH=/app/superset_config.py \
  -p 8088:8088 \
  -p 5008:5008 \
  apache/superset:6.1.0

# MCP serveur (processus séparé)
superset mcp run --host 0.0.0.0 --port 5008
```

## Conventions

- Branches: `<type>/<kebab-description>#<ticket>`
- Commits: Conventional Commits
- Fichiers: kebab-case
- Version: Semantic Versioning (MAJOR.MINOR.PATCH)
