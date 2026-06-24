# SDE — Configuration Supabase

Supabase remplace MongoDB Atlas comme backend de persistance.  
Il expose une API REST sur HTTPS (port 443), ce qui évite les problèmes TLS
rencontrés avec pymongo sur Render.

---

## Création du projet

1. [supabase.com](https://supabase.com) → **New project**
2. Nom : `sde` — région : **Frankfurt (eu-central-1)**
3. Attendre ~1 min que le projet soit prêt

---

## Schéma SQL

**SQL Editor → New query** — exécuter une seule fois :

```sql
CREATE TABLE users (
  username TEXT PRIMARY KEY,
  name     TEXT NOT NULL,
  email    TEXT DEFAULT '',
  password TEXT NOT NULL
);

CREATE TABLE watchlist (
  id       SERIAL PRIMARY KEY,
  username TEXT NOT NULL,
  ticker   TEXT NOT NULL,
  company  TEXT DEFAULT '',
  added_at TEXT DEFAULT '',
  UNIQUE(username, ticker)
);

CREATE TABLE scores (
  ticker  TEXT PRIMARY KEY,
  score   FLOAT,
  reco    TEXT,
  updated TEXT,
  prix    FLOAT
);
```

---

## Récupérer les clés

**Project Settings → API** :

| Variable | Source Supabase |
|---|---|
| `SUPABASE_URL` | Project URL |
| `SUPABASE_KEY` | `anon` / `public` key |
| `SUPABASE_SERVICE_KEY` | `service_role` key (migration uniquement) |

> La `service_role` key bypasse le Row Level Security — ne jamais l'exposer côté client ni dans l'app Flask. Elle sert uniquement au script de migration en local.

---

## Variables d'environnement

### Local (`.env`)
```env
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJhbGci...
# Pour la migration uniquement :
SUPABASE_SERVICE_KEY=eyJhbGci...
```

### Render (Production)
Render → Service → **Environment** → ajouter :
- `SUPABASE_URL`
- `SUPABASE_KEY`

(`SUPABASE_SERVICE_KEY` n'est pas nécessaire sur Render)

---

## Migration des données locales

Importe `auth/users.yaml`, `watchlist/watchlist.json` et `watchlist/last_scores.json`
dans Supabase. Idempotent : les entrées existantes sont ignorées.

```bash
# Renseigner SUPABASE_URL, SUPABASE_KEY et SUPABASE_SERVICE_KEY dans .env
python migrate_to_supabase.py
```

Sortie attendue :
```
✓  Connecté à Supabase : https://xxxxx.supabase.co

── Utilisateurs (4 trouvés) ────────────────────────
   ✓  admin (Admin)
   ✓  cyb1 (vladimir.andriana)
   ✓  cybkilla (Vlad Andriana)
   ✓  vlad (Vlad)
   → 4 importé(s), 0 ignoré(s)

── Watchlists (4 entrée(s) pour 2 user(s)) ──
   ✓  admin/GOOG
   ✓  admin/TMC
   ...
   → 4 importé(s), 0 ignoré(s)

── Scores (4 ticker(s)) ────────────────────────────
   ✓  GOOG — score 66.1 (ACHETER)
   ...
   → 4 importé(s), 0 ignoré(s)

Migration terminée ✓
```

---

## Architecture de la couche DB (`db.py`)

`db.py` expose une interface générique utilisée par `auth.py` et `watchlist/watchlist.py` :

| Fonction | Description |
|---|---|
| `is_available()` | Retourne `True` si Supabase est configuré |
| `find_one(table, filter)` | Équivalent SELECT … LIMIT 1 |
| `find(table, filter)` | Équivalent SELECT … |
| `insert_one(table, doc)` | Équivalent INSERT |
| `update_one(table, filter, update, upsert)` | Équivalent UPDATE ou UPSERT |
| `delete_one(table, filter)` | Équivalent DELETE |
| `count_documents(table, filter)` | Équivalent COUNT |

Si `SUPABASE_URL` ou `SUPABASE_KEY` est absent, toutes les fonctions retournent `None` / `[]` / `0`
et le code appelant bascule automatiquement sur le fallback YAML/JSON local.

---

## Fallback local (sans Supabase)

| Données | Fichier local |
|---|---|
| Utilisateurs | `auth/users.yaml` |
| Watchlist | `watchlist/watchlist.json` |
| Scores | `watchlist/last_scores.json` |

Le fallback est actif automatiquement quand les variables Supabase sont absentes du `.env`.
Utile pour le développement local sans connexion internet ou sans compte Supabase.
