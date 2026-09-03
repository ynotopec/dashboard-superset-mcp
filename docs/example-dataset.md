# Exemple de Dataset RNF

> Jeu de données d'exemple pour tester la création de dashboards via MCP.

## Source

Données RNF (Réseau National de Pharmacovigilance) — jeu de données fictif pour la démo.

## Colonnes

| Colonne | Type | Description |
|---------|------|-------------|
| `id_rnf` | INT | Identifiant unique de la notification |
| `titre_rnf` | VARCHAR | Titre de la notification |
| `type_organisme` | VARCHAR | Type d'établissement (Hôpital, Laboratoire, etc.) |
| `state_juridique` | VARCHAR | Code état juridique |
| `date_declaration` | DATE | Date de déclaration |
| `severite` | VARCHAR | Niveau de sévérité (grave, sérieux, léger) |
| `produit` | VARCHAR | Nom du produit médicamenteux |
| `effets_indésirables` | TEXT | Description des effets indésirables |
| `age_patient` | INT | Âge du patient (si disponible) |
| `sexe` | VARCHAR | Sexe (M/F) |
| `region` | VARCHAR | Région du patient |

## SQL DDL

```sql
CREATE TABLE rnf_donnees (
    id_rnf SERIAL PRIMARY KEY,
    titre_rnf VARCHAR(500) NOT NULL,
    type_organisme VARCHAR(100) NOT NULL,
    state_juridique VARCHAR(50),
    date_declaration DATE NOT NULL,
    severite VARCHAR(50),
    produit VARCHAR(200),
    effets_indésirables TEXT,
    age_patient INT,
    sexe CHAR(1),
    region VARCHAR(100)
);
```

## Fichier CSV d'exemple

```csv
id_rnf,titre_rnf,type_organisme,state_juridique,date_declaration,severite,produit,effets_indésirables,age_patient,sexe,region
1,Notification RNF 001,Hôpital public,761,2025-01-15,grave,Paracétamol,Céphalées persistantes,45,M,Île-de-France
2,Notification RNF 002,Pharmacie ville,513,2025-02-20,sérieux,Ibuprofène,Nausées et vertiges,32,F,Auvergne
3,Notification RNF 003,Laboratoire,651,2025-03-10,grève,Amlodipine,Œdèmes aux membres inférieurs,67,M,Nouvelle-Aquitaine
4,Notification RNF 004,Hôpital privé,711,2025-04-05,léger,Metformine,Hypoglycémie légère,54,F,Occitanie
5,Notification RNF 005,Consultant,731,2025-05-12,sérieux,Omeprazole,Douleurs abdominales,28,F,Bretagne
```

## Comment charger

1. **Via UI Superset** : Data → Datasets → Create dataset → Import CSV
2. **Via SQL** : Coller le DDL ci-dessus + le CSV dans SQL Lab
3. **Via API REST** : POST `/api/v1/database/` puis POST `/api/v1/dataset/`
