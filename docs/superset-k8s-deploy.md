# Installation Superset sur Kubernetes

> Déploiement Helm d'Apache Superset 6.1.0+ sur Kubernetes — single namespace.

## Prérequis

- Cluster Kubernetes fonctionnel
- Helm 3.x
- Ingress controller avec TLS (cert-manager recommandé)
- PersistentVolume (PostgreSQL)
- `kubectl` configuré avec accès au cluster cible

## Déploiement Helm

### 1. Namespace

```bash
kubectl create namespace superset-demo
```

### 2. ConfigMap pour `superset_config.py`

```bash
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: superset-config
  namespace: superset-demo
data:
  superset_config.py: |
    import os
    from dotenv import load_dotenv

    load_dotenv()

    SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_IN_PRODUCTION")

    SQLALCHEMY_DATABASE_URI = (
        f"postgresql+psycopg2://"
        f"{os.getenv('DB_USER', 'superset')}:"
        f"{os.getenv('DB_PASSWORD', '')}@"
        f"{os.getenv('DB_HOST', 'superset-postgresql')}:"
        f"{os.getenv('DB_PORT', '5432')}/"
        f"{os.getenv('DB_NAME', 'superset')}"
    )

    # MCP Server
    MCP_AUTH_ENABLED = False  # DEV ONLY — disable in production
    MCP_DEV_USERNAME = "admin"

    # Redis
    CACHE_CONFIG = {
        "CACHE_TYPE": "RedisCache",
        "CACHE_REDIS_URL": f"redis://:{os.getenv('REDIS_PASSWORD', '')}@superset-redis:6379/0",
    }
    DATA_CACHE_CONFIG = CACHE_CONFIG

    # Celery
    CELERY_CONFIG = {
        "broker_url": f"redis://:{os.getenv('REDIS_PASSWORD', '')}@superset-redis:6379/1",
        "result_backend": f"redis://:{os.getenv('REDIS_PASSWORD', '')}@superset-redis:6379/2",
    }
EOF
```

### 3. Secrets

```bash
kubectl create secret generic superset-secrets \
  --namespace=superset-demo \
  --from-literal=SECRET_KEY="$(openssl rand -base64 32)" \
  --from-literal=DB_PASSWORD="your-secure-password" \
  --from-literal=REDIS_PASSWORD="your-secure-password"
```

### 4. Helm Install

```bash
helm repo add apache-superset https://apache-superset.github.io/helm-charts/
helm repo update

helm install superset apache-superset/superset \
  --namespace=superset-demo \
  --set configMaps.configFrom=superset-config \
  --set secrets.secretsFrom=superset-secrets \
  --set ingress.enabled=true \
  --set ingress.hostname=superset.demo1.ailab.infocepo.com \
  --set ingress.ingressClassName=public \
  --set ingress.tls=true \
  --wait --timeout 300s
```

### 5. Vérification

```bash
kubectl get pods -n superset-demo
# Attendre que tous les pods soient Running

# Tester le endpoint MCP
kubectl port-forward -n superset-demo svc/superset-mcp 5008:5008 &
curl http://localhost:5008/mcp -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":0,"method":"list_tools","params":{}}'

# Vérifier l'UI
kubectl port-forward -n superset-demo svc/superset-webserver 8088:8088 &
# Ouvrir http://localhost:8088
```

### 6. Créer un utilisateur admin initial

```bash
kubectl exec -it -n superset-demo deploy/superset-superset-webserver -- \
  superset fab create-admin \
  --username admin \
  --firstname Admin \
  --lastname User \
  --email admin@example.com \
  --password admin
```

### 7. Initialize database

```bash
kubectl exec -it -n superset-demo deploy/superset-superset-webserver -- \
  superset db upgrade
```

### 8. Load examples (optionnel)

```bash
kubectl exec -it -n superset-demo deploy/superset-superset-webserver -- \
  superset load_examples
```

## Composants

| Composant | Image | Port | Description |
|-----------|-------|------|-------------|
| `superset-webserver` | `apache/superset:6.1.0` | 8088 | Web UI + API REST |
| `superset-worker` | `apache/superset:6.1.0` | - | Celery worker (async queries) |
| `superset-beat` | `apache/superset:6.1.0` | - | Celery beat (cache warming) |
| `superset-redis` | `redis:7-alpine` | 6379 | Cache + broker |
| `superset-postgresql` | `postgres:15` | 5432 | Base de données |
| `superset-mcp` | `apache/superset:6.1.0` | 5008 | MCP Server |

## Nettoyage

```bash
helm uninstall superset -n superset-demo
kubectl delete namespace superset-demo
```
