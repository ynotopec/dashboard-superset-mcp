# Prompt de Création de Dashboard

> Comment utiliser les outils MCP de Superset pour créer des dashboards.

## Workflow MCP Officiel (Superset 6.1.0+)

D'après la documentation officielle et DeepWiki :

### Étapes recommandées

1. **list_datasets** — Découvrir les datasets disponibles
2. **list_databases** — Vérifier les bases connectées
3. **create_virtual_dataset** (optionnel) — Créer un dataset SQL personnalisé
4. **list_charts** — Vérifier les charts existants
5. **generate_chart** — Créer les charts (séquentiellement!)
6. **generate_dashboard** — Créer le dashboard et assembler les charts
7. **get_dashboard_info** — Valider le résultat

## Exemple de Prompt

```
Créer un dashboard "Suivi RNF" avec 4 charts:

1. BigNumber: nombre total de notifications RNF
2. Bar chart: répartition par type d'organisme
3. Pie chart: répartition par niveau de sévérité
4. Table: dernières notifications avec date, produit, severity

DataSource: table rnf_donnees dans la base rnf_postgres
```

## Ce que fait le prompt

Le MCP server traduit cela en:

```python
# 1. Découvrir
list_datasets()       # → trouve rnf_donnees (id=32)
list_databases()      # → trouve rnf_postgres (id=3)

# 2. Créer charts (séquentiellement!)
generate_chart({
    "name": "Total RNF",
    "viz_type": "big_number",
    "datasource_id": 32,
    "metrics": ["COUNT(*)"],
    "datasource_type": "table"
})
# → retourne: {"id": 138, "slice_name": "Total RNF", ...}

generate_chart({
    "name": "Par Type d'Organisme",
    "viz_type": "bar",
    "datasource_id": 32,
    "metrics": ["COUNT(*)"],
    "groupby": ["type_organisme"],
    "datasource_type": "table"
})
# → retourne: {"id": 135, "slice_name": "Par Type d'Organisme", ...}

generate_chart({
    "name": "Par Sévérité",
    "viz_type": "pie",
    "datasource_id": 32,
    "metrics": ["COUNT(*)"],
    "groupby": ["severite"],
    "datasource_type": "table"
})
# → retourne: {"id": 136, "slice_name": "Par Sévérité", ...}

generate_chart({
    "name": "Dernières Notifications",
    "viz_type": "table",
    "datasource_id": 32,
    "metrics": ["COUNT(*)"],
    "groupby": ["date_declaration", "produit", "severite"],
    "datasource_type": "table"
})
# → retourne: {"id": 137, "slice_name": "Dernières Notifications", ...}

# 3. Créer dashboard
generate_dashboard({
    "title": "Suivi RNF",
    "charts": [
        {"chart_id": 138},  # BigNumber (top-left)
        {"chart_id": 137},  # Table (top-right)
        {"chart_id": 136},  # Pie (bottom-left)
        {"chart_id": 135},  # Bar (bottom-right)
    ]
})
# → retourne: {"dashboard_id": "uuid-56", "title": "Suifié RNF", "charts": [...]}

# 4. Valider
get_dashboard_info("uuid-56")
# → retourne: dashboard complet avec 4 charts
```

## Attention: Séquentialité Obligatoire

⚠️ **Ne PAS appeler plusieurs `generate_chart` en parallèle.**

Bug Superset 6.1.0 (#42567, #42622): les appels concurrents partagent une session SQLAlchemy, causant:
- `DetachedInstanceError` après 2 appels concurrents
- Création en base malgré retour d'erreur au client
- Doublons si retry naïf

**Bon usage:**
```
generate_chart #1 → wait → verify → generate_chart #2 → wait → verify → generate_chart #3 → ...
```

## Outils MCP Disponibles

| Outil | Description |
|-------|-------------|
| `list_datasets` | Lister les datasets |
| `list_databases` | Lister les bases de données |
| `create_virtual_dataset` | Créer un dataset à partir de SQL |
| `generate_chart` | Créer un chart (séquentiel!) |
| `get_chart_info` | Info sur un chart |
| `list_charts` | Lister les charts |
| `generate_dashboard` | Créer un dashboard avec charts |
| `add_chart_to_existing_dashboard` | Ajouter un chart à un dashboard existant |
| `get_dashboard_info` | Info sur un dashboard |
| `list_dashboards` | Lister les dashboards |
| `execute_sql` | Exécuter une requête SQL |
| `list_tools` | Découvrir tous les outils |

## Source

- [Docs Superset MCP](https://superset.apache.org/admin-docs/configuration/mcp-server/)
- [DeepWiki MCP Tools](https://deepwiki.com/apache/superset/4.6.2-mcp-tools-and-resources)
- [Superset GitHub MCP Service](https://github.com/apache/superset/tree/master/superset/mcp_service)
