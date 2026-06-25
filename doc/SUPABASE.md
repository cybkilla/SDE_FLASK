# SDE — Configuration Supabase

Supabase est le backend de persistance principal. Il expose une API REST sur HTTPS (port 443), compatible avec Render et tout environnement cloud.

---

## Création du projet

1. [supabase.com](https://supabase.com) → **New project**
2. Nom : `sde` — région : **Frankfurt (eu-central-1)**
3. Attendre ~1 min que le projet soit prêt

---

## Schéma SQL

**SQL Editor → New query** — exécuter une seule fois :

```sql
-- Comptes utilisateurs
CREATE TABLE users (
  username TEXT PRIMARY KEY,
  name     TEXT NOT NULL,
  email    TEXT DEFAULT '',
  password TEXT NOT NULL
);

-- Tickers suivis par utilisateur
CREATE TABLE watchlist (
  id       SERIAL PRIMARY KEY,
  username TEXT NOT NULL,
  ticker   TEXT NOT NULL,
  company  TEXT DEFAULT '',
  added_at TEXT DEFAULT '',
  UNIQUE(username, ticker)
);

-- Dernier score/reco connu par ticker (scheduler)
CREATE TABLE scores (
  ticker  TEXT PRIMARY KEY,
  score   FLOAT,
  reco    TEXT,
  updated TEXT,
  prix    FLOAT
);

-- Cache pipeline sérialisé (TTL 24h)
CREATE TABLE ticker_snapshots (
  ticker     TEXT PRIMARY KEY,
  payload    JSONB NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Lots d'achat par utilisateur (supporte le DCA)
CREATE TABLE positions (
  id         SERIAL PRIMARY KEY,
  username   TEXT NOT NULL,
  ticker     TEXT NOT NULL,
  company    TEXT DEFAULT '',
  date_achat DATE NOT NULL,
  prix_achat FLOAT NOT NULL,
  quantite   FLOAT NOT NULL,
  currency   TEXT DEFAULT 'USD',
  notes      TEXT DEFAULT '',
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Conseils journaliers + évaluation J+1
CREATE TABLE daily_advice (
  id                SERIAL PRIMARY KEY,
  username          TEXT NOT NULL,
  ticker            TEXT NOT NULL,
  date_conseil      DATE NOT NULL,
  action            TEXT NOT NULL,        -- ACHETER / RENFORCER / TENIR / SURVEILLER / ALLÉGER / VENDRE
  quantite_suggeree FLOAT,
  prix_jour         FLOAT,
  prix_cible        FLOAT,
  score_sde         FLOAT,
  recommandation    TEXT,
  raisonnement      TEXT,
  prix_j1           FLOAT,               -- prix le lendemain (évaluation scheduler)
  variation_j1      FLOAT,               -- variation % entre prix_jour et prix_j1
  bon_conseil       BOOLEAN,             -- TRUE si le conseil était pertinent
  evaluated_at      TIMESTAMPTZ,
  UNIQUE(username, ticker, date_conseil)
);
```

---

## Activer RLS (Row Level Security)

RLS doit être activé sur **toutes les tables**. L'app utilise la `service_role` key côté serveur, qui bypasse RLS — l'activation empêche tout accès direct non autorisé via la clé anon.

```sql
ALTER TABLE users           ENABLE ROW LEVEL SECURITY;
ALTER TABLE watchlist       ENABLE ROW LEVEL SECURITY;
ALTER TABLE scores          ENABLE ROW LEVEL SECURITY;
ALTER TABLE ticker_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE positions       ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_advice    ENABLE ROW LEVEL SECURITY;
```

Aucune policy supplémentaire n'est nécessaire : l'app accède toujours via `service_role` (bypass RLS).

---

## Récupérer les clés

**Project Settings → API** :

| Variable | Source Supabase | Usage |
|---|---|---|
| `SUPABASE_URL` | Project URL | Toutes les requêtes |
| `SUPABASE_SERVICE_KEY` | `service_role` key | **Production** — bypass RLS, server-side uniquement |
| `SUPABASE_KEY` | `anon` / `public` key | Fallback dev local si SERVICE_KEY absent |

> `SUPABASE_SERVICE_KEY` est la clé principale utilisée par l'app en production.  
> Ne jamais l'exposer côté client ni dans le code source.

---

## Variables d'environnement

### Local (`.env`)
```env
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGci...   # service_role — obligatoire
SUPABASE_KEY=eyJhbGci...           # anon — fallback optionnel
```

### Render (Production)
Render → Service → **Environment** → ajouter :
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`

---

## Architecture de la couche DB (`db.py`)

`db.py` expose une interface générique utilisée par tous les modules :

| Fonction | Description |
|---|---|
| `is_available()` | `True` si Supabase est configuré |
| `find_one(table, filter)` | SELECT … LIMIT 1 |
| `find(table, filter)` | SELECT … |
| `insert_one(table, doc)` | INSERT |
| `update_one(table, filter, update, upsert)` | UPDATE ou UPSERT |
| `delete_one(table, filter)` | DELETE |
| `count_documents(table, filter)` | COUNT |

`db.py` utilise `SUPABASE_SERVICE_KEY` en priorité (bypass RLS).  
Si absent, bascule sur `SUPABASE_KEY` (anon).  
Si les deux sont absents, toutes les fonctions retournent `None` / `[]` / `0`.

---

## Cache snapshot (`snapshot.py`)

Le module `snapshot.py` sérialise le résultat complet du pipeline dans `ticker_snapshots` :

- **TTL** : 24h (configurable via `MAX_AGE_HOURS`)
- **Sérialisation** : DataFrames → listes de dicts, numpy → scalaires Python natifs
- **Désérialisation** : reconstruction des DataFrames avec DatetimeIndex

Flux d'une requête d'analyse :
```
1. Cache mémoire (15 min)       → hit → réponse immédiate
2. ticker_snapshots (< 24h)     → hit → prix superposé via get_live_price()
3. Pipeline complet              → calcul → sauvegardé en mémoire + Supabase
```

---

## Migration des données locales

Script one-shot pour importer `auth/users.yaml`, `watchlist/watchlist.json` et `watchlist/last_scores.json` dans Supabase. Idempotent.

```bash
python migrate_to_supabase.py
```

---

## Fallback local (dev sans Supabase)

| Données | Fichier local |
|---|---|
| Utilisateurs | `auth/users.yaml` |
| Watchlist | `watchlist/watchlist.json` |
| Scores | `watchlist/last_scores.json` |

Le fallback est actif automatiquement quand les variables Supabase sont absentes du `.env`.
