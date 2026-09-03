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

## Déploiement Kubernetes

```bash
# 1. Copier et éditer la config
cp config/.env.example config/.env
# Éditer .env : passwords, namespace, domain

# 2. Déployer en une commande
chmod +x scripts/deploy.sh
./scripts/deploy.sh [namespace] [version]

# Exemple : ./scripts/deploy.sh demo1 6.1.0

# 3. Vérifier
kubectl get pods -n demo1
kubectl port-forward svc/superset-webserver 8088:8088 -n demo1
kubectl port-forward svc/superset-mcp 5008:5008 -n demo1

# 4. Nettoyer (sans supprimer les PVC)
./scripts/undeploy.sh demo1
```

### Déploiement Helm (alternatif)

```bash
# Via chart Helm officiel avec overrides personnalisés
helm install superset bitnami/superset \
  -f k8s/superset-helm-values.yaml \
  -n superset \
  --create-namespace
```

### Docker Compose (local/dev)

```bash
# Variante simple sans K8s
docker-compose up -d
```

### Fix important

L'image officielle `apache/superset:6.1.0` a un bug connu :
le dashboard affiche une chargement infini au clic. La correction
est incluse automatiquement via `lifecycle.postStart` dans les
manifests K8s, mais pour un build local :

```bash
docker build -f k8s/Dockerfile.superset-fix -t superset:6.1.0-fix .
```

## Conventions

- Branches: `<type>/<kebab-description>#<ticket>`
- Commits: Conventional Commits
- Fichiers: kebab-case
- Version: Semantic Versioning (MAJOR.MINOR.PATCH)
