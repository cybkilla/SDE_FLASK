# SDE — Stock Decision Engine (Flask)

Application web d'aide à la décision boursière. Analyse n'importe quelle action cotée en combinant signaux techniques, données fondamentales, analyse médiatique et synthèse par IA.

## Fonctionnalités

### Analyse
- **Score global** (0–100) avec jauge visuelle et décomposition en 3 composantes pondérées
- **Recommandation** ACHETER / NEUTRE / VENDRE avec niveau de confiance
- **Signaux techniques** : RSI, MACD, moyennes mobiles (MA20/MA50), volume ratio
- **Données fondamentales** : P/E, EPS, dette/capitalisation, croissance CA
- **Analyse médiatique** : sentiment NLP (VADER) sur presse et flux RSS
- **Activité insiders** : transactions des dirigeants
- **Risque dirigeants** : détection d'événements (scandales, départs, rachats)
- **Zones de trading** : entrée, objectif cible, stop-loss, ratio R/R
- **Synthèse IA** : résumé généré par LLaMA 3.3 70B via Groq (fallback Python)
- **Graphiques** : cours + volume (matplotlib), RSI, chandeliers Plotly interactifs
- **Figures chartistes** : détection de 12 patterns avec explication contextuelle

### Portfolio & Conseil
- **Positions** : enregistrement des lots d'achat par ticker (DCA supporté), P&L en temps réel
- **Conseil du jour** : recommandation journalière rule-based (sans LLM) combinant score SDE, RSI, P&L de la position et pattern chandelier détecté
- **Historique des conseils** : évaluation automatique J+1 (bon/mauvais conseil), taux de fiabilité

### Plateforme
- **Watchlist** personnelle (AJAX, sans rechargement de page)
- **Cache 3 niveaux** : mémoire 15 min → snapshot Supabase 24h → pipeline complet
- **Prix live** : superposition du prix Finnhub en temps réel sur les analyses en cache
- **Authentification** : inscription / connexion / sessions persistantes (Flask-Login + bcrypt)
- **Alertes email** : notification sur variation de cours ou changement de recommandation (Resend HTTP)
- **Scheduler deux vitesses** : prix live toutes les 30 min (Finnhub léger) + pipeline complet 1×/jour
- **Interface responsive** : navbar intégrée, mobile-first

## Stack technique

| Couche | Technologie |
|---|---|
| Framework web | Flask 3 + Blueprints |
| Auth | Flask-Login, Flask-WTF (CSRF), bcrypt |
| Base de données | Supabase (PostgreSQL) via REST HTTPS |
| Données marché | yfinance (primaire) · Finnhub (quote live + fallback) · Twelve Data (fallback historique) |
| NLP / Sentiment | VADER |
| LLM | Groq API (LLaMA 3.3 70B) + fallback Python |
| Graphiques | matplotlib (PNG base64), Plotly (JSON → JS) |
| Actualités | NewsAPI, feedparser (RSS) |
| Email | Resend (HTTP API — fonctionne sur Render) |
| Scheduler | cron-job.org → `POST /scheduler/run` toutes les 30 min |
| Serveur prod | gunicorn (`workers=1`, `max_requests=200`) |
| Déploiement cloud | Render free tier — `https://sde-flask.onrender.com` |

## Installation

### Prérequis

- Python 3.10+
- pip

### 1. Cloner et installer

```bash
git clone https://github.com/cybkilla/SDE_FLASK.git
cd SDE_FLASK
pip install -r requirements.txt
```

### 2. Configurer les variables d'environnement

```bash
cp .env.example .env
# Éditer .env avec vos clés
```

Variables requises dans `.env` :

```env
FLASK_SECRET_KEY=une_cle_aleatoire_longue

# Données marché
FINNHUB_API_KEY=votre_cle_finnhub
TWELVE_DATA_API_KEY=votre_cle_twelvedata

# Actualités
NEWS_API_KEY=votre_cle_newsapi

# LLM (optionnel — fallback Python si absent)
GROQ_API_KEY=votre_cle_groq

# Supabase (obligatoire en production)
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGci...   # service_role — bypass RLS, server-side uniquement
SUPABASE_KEY=eyJhbGci...           # anon/public — fallback si SERVICE_KEY absent

# Email alertes
RESEND_API_KEY=re_xxxxxxxxxxxx
RESEND_FROM=SDE StockDecisionEngine <onboarding@resend.dev>

# Scheduler
CRON_SECRET=un_token_aleatoire_long
```

Sources des clés :
- **Finnhub** : [finnhub.io](https://finnhub.io) — 60 req/min gratuit
- **Twelve Data** : [twelvedata.com](https://twelvedata.com) — 800 req/jour gratuit
- **NewsAPI** : [newsapi.org](https://newsapi.org) — 100 req/jour gratuit
- **Groq** : [console.groq.com](https://console.groq.com) — gratuit
- **Supabase** : [supabase.com](https://supabase.com) — voir `doc/SUPABASE.md` pour le schéma SQL
- **Resend** : [resend.com](https://resend.com) — 3 000 emails/mois gratuit
- **CRON_SECRET** : `python -c "import secrets; print(secrets.token_hex(24))"`

### 3. Lancer en développement

```bash
python run_flask.py
```

Ouvrir [http://localhost:5000](http://localhost:5000)

### 4. Lancer en production (gunicorn)

```bash
gunicorn --config gunicorn.conf.py "run_flask:app"
```

## Scheduler & Alertes

Le scheduler vérifie toutes les watchlists via [cron-job.org](https://cron-job.org).

| Endpoint | Rôle |
|---|---|
| `POST /scheduler/run` | Déclenche le scheduler (thread background, répond 202) |
| `GET /scheduler/test-email?to=...` | Envoie un email de test Resend |

Protégés par le header `X-Cron-Secret` (ou paramètre `?secret=CRON_SECRET`).

**Architecture deux vitesses :**
- **Chemin rapide** (toutes les 30 min) : `get_live_price()` Finnhub + snapshot Supabase
- **Chemin complet** (1×/jour) : pipeline complet si snapshot > 24h (renouvelle NewsAPI, Groq…)

**Configuration cron-job.org :**
- URL : `https://sde-flask.onrender.com/scheduler/run`
- Méthode : POST
- Header : `X-Cron-Secret: CRON_SECRET`
- Intervalle : toutes les 30 minutes

## Structure du projet

```
sde_flask/
├── run_flask.py              # Point d'entrée Flask
├── config.py                 # Paramètres centralisés (charge .env)
├── pipeline.py               # Orchestrateur de l'analyse complète
├── snapshot.py               # Cache Supabase 24h (sérialisation/désérialisation)
├── cache.py                  # Cache in-memory 15 min
├── db.py                     # Couche persistance Supabase (service_role key)
├── flask_app/
│   ├── __init__.py           # Factory create_app()
│   ├── blueprints/
│   │   ├── auth.py           # Routes /auth/login, /register, /logout
│   │   ├── stock.py          # Routes /, /analyze/<ticker>, /api/search, /watchlist
│   │   ├── portfolio.py      # Routes /portfolio/positions, /portfolio/advice
│   │   └── cron.py           # Route /scheduler/run (protégée par CRON_SECRET)
│   ├── static/
│   │   ├── css/sde.css       # Design system (Dashboard Financier)
│   │   └── js/
│   │       ├── search.js     # Autocomplete navbar
│   │       └── watchlist.js  # AJAX watchlist (modal Bootstrap)
│   └── templates/
│       ├── base.html         # Layout : navbar, modal watchlist, scripts
│       ├── home.html         # Page d'accueil
│       ├── analysis.html     # Page d'analyse + section Ma position
│       └── auth/
├── analysis/
│   ├── scoring.py            # Score global pondéré (technique + fondamental + médiatique)
│   ├── candle_patterns.py    # Détection de 12 figures chartistes
│   ├── sentiment.py          # NLP VADER
│   ├── media_score.py        # Score médiatique agrégé
│   ├── executive_risk.py     # Risque dirigeants
│   └── llm_explain.py        # Appels Groq / fallback Python
├── data/
│   ├── market.py             # get_market_data() + get_live_price() (Finnhub → yfinance fallback)
│   ├── news.py               # NewsAPI + feedparser RSS
│   └── insider.py            # Transactions insiders
├── portfolio/
│   ├── positions.py          # get_portfolio_summary(), add_position(), delete_position()
│   └── advisor.py            # generate_advice() — conseil rule-based (SDE + RSI + P&L + chandelier)
├── alerts/
│   ├── scheduler.py          # Architecture deux vitesses (Finnhub live + snapshot + pipeline)
│   └── mailer.py             # Envoi alertes via Resend
├── watchlist/
│   └── watchlist.py          # get_watchlist(), add/remove, get_last_score()
├── ui/
│   └── charts.py             # Génération graphiques (matplotlib + Plotly)
├── gunicorn.conf.py          # workers=1, max_requests=200 (Render free tier 512MB)
└── .env.example
```

## Supabase — Tables

Voir `doc/SUPABASE.md` pour le schéma SQL complet et les politiques RLS.

| Table | Rôle |
|---|---|
| `users` | Comptes utilisateurs |
| `watchlist` | Tickers suivis par utilisateur |
| `scores` | Dernier score/reco connu par ticker |
| `ticker_snapshots` | Résultats pipeline sérialisés (cache 24h) |
| `positions` | Lots d'achat par utilisateur et ticker |
| `daily_advice` | Conseils journaliers + évaluation J+1 |

## Sécurité

- Clés API uniquement via `os.getenv()` — jamais en dur dans le code
- `.env` dans `.gitignore` — seul `.env.example` est versionné
- `FLASK_SECRET_KEY` et `SUPABASE_SERVICE_KEY` obligatoires via variables d'environnement
- RLS activé sur toutes les tables Supabase ; `SUPABASE_SERVICE_KEY` (service_role) uniquement côté serveur
- Protection CSRF sur tous les formulaires et requêtes AJAX (Flask-WTF + header `X-CSRFToken`)
- Sessions HTTP-only, SameSite=Lax

## Avertissement

SDE est un outil d'aide à la décision. Les informations fournies ne constituent pas un conseil financier. Investir comporte des risques de perte en capital.
