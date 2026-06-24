# SDE — Grille d'évaluation PPL 2026

> Récap technique par critère. 

---

## 01 Conception du projet

| Sous-critère | Ce qui est fait dans SDE |
|---|---|
| **Ambition & Originalité** | Moteur d'analyse boursière multi-source : scoring composite technique + fondamental + sentiment + risque dirigeants + LLM, avec système d'alertes email automatisées. |
| **Fonctionnalités** | Recherche de ticker, analyse complète, watchlist multi-utilisateurs, alertes email conditionnelles, explication IA générée. |
| **Description des processus** | `pipeline.py::run(ticker)` orchestre la collecte → calcul des sous-scores → score global → recommandation → explication LLM. |
| **Modélisation du Workflow** | Voir `ARCHITECTURE.md` : 5 modules d'analyse indépendants agrégés par `scoring.py`, résultat consommé par `app.py` et `scheduler.py`. |

---

## 02 Structure logique de l'application

| Sous-critère | Ce qui est fait dans SDE |
|---|---|
| **Architecture** | Découpage MVC-like : `data/` (collecte), `analysis/` (calcul), `ui/` (rendu), `alerts/` (notifications), `auth/` (session), `utils/` (helpers). |
| **Modules externes** | `yfinance`, `newsapi-python`, `feedparser`, `vaderSentiment`, `groq`, `streamlit-authenticator`, `plotly`. |
| **Système de classes** | `ui/gauge.py` et `ui/charts.py` : figures Plotly encapsulées. `auth/auth.py` : wrapper `streamlit-authenticator`. |
| **Gestion des données** | Données temps réel via yfinance/NewsAPI ; état persistant en JSON (`watchlist.json`, `last_scores.json`) ; config centralisée dans `config.py`. |
| **Local / Serveur** | Dev local (Streamlit), scheduler cloud via **GitHub Actions** (cron horaire, commit automatique de `last_scores.json`). |

---

## 03 Programmation Python

| Sous-critère | Ce qui est fait dans SDE |
|---|---|
| **Organisation des fichiers** | Un fichier = une responsabilité (`market.py`, `news.py`, `sentiment.py`, `scoring.py`…). Imports relatifs propres grâce au `sys.path.insert`. |
| **Fonctions & variables** | Nommage explicite (`get_sector_news`, `save_last_score`, `build_prompt`). Constantes dans `config.py` (`ALERT_VAR_THRESHOLD`, `LLM_MAX_TOKENS`). |
| **Classes, méthodes, héritage** | Pas de hiérarchie lourde (volontaire) ; classes légères dans `ui/`. Utilisation de dataclasses implicites via dict typés. |
| **Bibliothèques Standard** | `pathlib`, `json`, `smtplib`, `email.mime`, `sys`, `time`, `os`, `re`, `datetime`. |
| **Modules Built-In** | `typing` (hints), `functools` (cache), `collections`. |
| **Organisation & Extensibilité** | `pipeline.py` expose une API unique `run(ticker)` ; ajouter un nouveau sous-score = créer un module + l'intégrer dans `scoring.py` sans toucher à l'UI. |

---

## 04 Analyse du code utilisé

| Sous-critère | Ce qui est fait dans SDE |
|---|---|
| **Justification du design** | `ARCHITECTURE.md` : choix VADER vs FinBERT (GPU optionnel), Groq vs Ollama (fallback local), scoring pondéré 40/35/25. |
| **Maîtrise du code** | Gestion index Pandas (`_col()` helper pour colonnes absentes), alignement `.fillna()`, fallback LLM gracieux, `variation_tracked` vs `var_1d` yfinance. |

---

## 05 Interfaces utilisateur — Streamlit

| Sous-critère | Ce qui est fait dans SDE |
|---|---|
| **Librairies** | Streamlit 1.57, `streamlit-authenticator` v0.4.2, Plotly 6, CSS inline custom (ciblage `data-testid`). |
| **Fonctionnalités** | Login/logout sidebar, recherche de ticker avec autocomplétion, jauge score animée, graphiques OHLCV + RSI + MA, expander actualités par type (ticker/secteur), gestion watchlist. |
| **Usabilité** | Recommandation colorée (vert/orange/rouge), jauge 0-100, actualités filtrées par type, bouton "Se connecter" aligné à droite dans sidebar. |

---

## 06 Modules externes

| Sous-critère | Ce qui est fait dans SDE |
|---|---|
| **Librairies externes** | `yfinance`, `vaderSentiment`, `feedparser`, `newsapi-python`, `transformers` (FinBERT optionnel), `groq`, `bcrypt`, `PyYAML`. |
| **Connexion APIs distantes** | **NewsAPI** (articles financiers), **Yahoo Finance** via yfinance (cours, fondamentaux, insider), **Groq API** (LLM llama-3.3-70b pour explication IA). |
| **Maps / GPS / Audio / Vidéo** | Non applicable pour ce projet. |

---

## 07 Flask — REST API

| Sous-critère | Ce qui est fait dans SDE |
|---|---|
| **Routes** | SDE utilise **Streamlit** (pas Flask). L'UI et la logique métier sont couplées dans `app.py` via callbacks Streamlit. |
| **Authentification** | `streamlit-authenticator` : hash bcrypt des mots de passe dans `users.yaml`, cookie de session signé (clé dans `config.py`). |
| **SGBD** | Pas de base SQL ; persistance légère en JSON (adapté au volume). Extension possible vers SQLite/Firebase. |
| **Modélisation des données** | Structures dict typées : `WatchlistItem`, résultat `run()` (score, reco, market, news, explication). |

---

## 07bis Traitement des données — NumPy & Pandas

| Sous-critère | Ce qui est fait dans SDE |
|---|---|
| **Collection des données** | `data/market.py` : DataFrame yfinance (OHLCV, 90j). `data/news.py` : DataFrame d'articles (titre, source, sentiment, type). |
| **Visualisation** | `ui/charts.py` : chandelier Plotly, RSI, moyennes mobiles 20/50j. `ui/gauge.py` : jauge score composite. |
| **Test accessibilité APIs** | `test_market.py`, `test_news.py`, `test_media.py` : vérifient que les sources retournent des données valides. |
| **Modules externes** | `pandas 2.2`, `numpy 1.26`, `plotly 6`. |

---

## 09 Techniques de Développement — DevOps

| Sous-critère | Ce qui est fait dans SDE |
|---|---|
| **GIT** | Repo GitHub avec historique de commits ; `.github/workflows/` versionné ; `[skip ci]` sur commits automatiques. |
| **Docker** | Pas encore de Dockerfile dans SDE. _(À ajouter : `FROM python:3.11-slim`, `COPY requirements.txt`, `CMD streamlit run app.py`)_. |
| **Déploiement** | **GitHub Actions** (`scheduler.yml`) : cron horaire, exécution `scheduler.py --once`, commit automatique `last_scores.json`. |
| **Testing** | `test_full.py` (pipeline complet), `test_market.py`, `test_news.py`, `test_media.py`, `test_signals/`. |

---

## 10 Fonctionnalités du projet

| Sous-critère | Ce qui est fait dans SDE |
|---|---|
| **Proof of work** | Score composite 0-100 → recommandation ACHETER / NEUTRE / VENDRE avec explication LLM en 3 phrases. |
| **Usages incrémentables** | Ajout de tickers watchlist à la volée, multi-utilisateurs (`users.yaml`), seuils configurables dans `config.py`. |
| **Formulaires / interfaces avancées** | Formulaire login sidebar, recherche ticker avec autocomplétion, gestion watchlist (ajout/suppression). |
| **Options de développement à venir** | FinBERT GPU pour sentiment plus précis, vue portfolio agrégée, scoring sectoriel avancé, Dockerfile + déploiement cloud. |
| **Exploitation commerciale** | Outil d'aide à la décision pour investisseurs particuliers ; base pour un SaaS de screener boursier personnalisé. |

---

## Points forts à mettre en avant

- Pipeline entièrement **découplé** : chaque source d'analyse est indépendante et testable seule.
- **Alertes automatisées** sans infrastructure payante (GitHub Actions gratuit).
- **Fallback LLM** : Groq cloud → Ollama local si quota épuisé.
- Gestion robuste des **cas limites** : tickers sans données, colonnes absentes dans yfinance, index Pandas mal alignés.

## Lacunes à mentionner honnêtement

- Pas de Dockerfile (Streamlit se déploie facilement mais non containerisé).
- Pas de base SQL (JSON suffisant au prototype, limite à grande échelle).
- Pas de tests unitaires sur `analysis/scoring.py` (couverture partielle).
