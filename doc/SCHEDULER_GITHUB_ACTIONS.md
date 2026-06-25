# SDE — Scheduler & Alertes

> **Note** : SDE utilise désormais **cron-job.org** + **Render** (pas GitHub Actions). Ce document décrit l'architecture actuelle, suivie d'une annexe sur l'ancienne approche GitHub Actions (conservée à titre de référence).

---

## Architecture actuelle — cron-job.org + Render

### Ce que fait le scheduler

Toutes les 30 minutes, cron-job.org déclenche `POST /scheduler/run` sur Render. Flask démarre un thread background qui :

1. Lit toutes les watchlists (via Supabase)
2. Récupère le prix live via Finnhub
3. Compare avec le dernier état connu (snapshot Supabase)
4. Si snapshot > 24h → pipeline complet (NewsAPI, Groq, yfinance 90j)
5. Envoie un email Resend si variation ≥ ±5 % ou changement de recommandation

### Architecture deux vitesses

| Chemin | Déclencheur | Coût |
|---|---|---|
| **Rapide** (toutes les 30 min) | `get_live_price()` Finnhub + snapshot Supabase | Léger — 1 appel Finnhub par ticker |
| **Complet** (1×/jour) | Snapshot > 24h | Lourd — pipeline complet (NewsAPI, Groq, yfinance) |

### Configuration cron-job.org

1. Créer un compte sur [cron-job.org](https://cron-job.org)
2. **New cronjob** :
   - URL : `https://sde-flask.onrender.com/scheduler/run`
   - Méthode : `POST`
   - Header : `X-Cron-Secret: <valeur de CRON_SECRET>`
   - Intervalle : toutes les 30 minutes

### Variables d'environnement requises (Render)

```env
CRON_SECRET=un_token_aleatoire_long
RESEND_API_KEY=re_xxxxxxxxxxxx
RESEND_FROM=SDE StockDecisionEngine <onboarding@resend.dev>
FINNHUB_API_KEY=votre_cle_finnhub
```

### Endpoints scheduler

| Route | Protection | Rôle |
|---|---|---|
| `POST /scheduler/run` | Header `X-Cron-Secret` | Déclenche le scheduler (répond 202 immédiatement, thread background) |
| `GET /scheduler/test-email?to=email` | Header ou `?secret=` | Envoie un email de test Resend |

### Tester manuellement

```bash
curl -X POST https://sde-flask.onrender.com/scheduler/run \
     -H "X-Cron-Secret: VOTRE_CRON_SECRET"
# → {"status": "started", "message": "Scheduler lancé en background"}
```

---

## Email via Resend

Resend est une API HTTP qui fonctionne sur Render (pas besoin de SMTP/socket, qui est souvent bloqué en cloud).

- 3 000 emails/mois gratuit
- Sans domaine propre : `RESEND_FROM=SDE StockDecisionEngine <onboarding@resend.dev>`
- Avec domaine vérifié : `RESEND_FROM=SDE <noreply@mondomaine.com>`

Conditions d'alerte dans `alerts/scheduler.py` :
- Variation de prix ≥ ±5 % depuis le dernier check
- Changement de recommandation (ACHETER / NEUTRE / VENDRE)

---

## Annexe — Ancienne architecture GitHub Actions (Streamlit, obsolète)

> Gardé à titre de référence pour l'historique du projet. L'approche GitHub Actions était utilisée avec la version Streamlit et a été remplacée par cron-job.org lors de la migration vers Flask + Render.

**Différences principales :**
- GitHub Actions utilisait `streamlit-authenticator` + fichiers JSON locaux
- L'email était via SMTP Gmail (App Password)
- Le scheduler commitait `last_scores.json` dans le repo (`[skip ci]`)
- Fréquence : 1×/heure (pas 30 min)

**Ancienne configuration `.github/workflows/scheduler.yml` :**

```yaml
name: SDE Scheduler (obsolète)
on:
  schedule:
    - cron: "0 * * * *"
  workflow_dispatch:
jobs:
  run-scheduler:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11", cache: pip }
      - run: pip install -r stockengine/requirements-scheduler.txt
      - env:
          GROQ_API_KEY:  ${{ secrets.GROQ_API_KEY }}
          NEWS_API_KEY:  ${{ secrets.NEWS_API_KEY }}
          SMTP_PASSWORD: ${{ secrets.SMTP_PASSWORD }}
        run: cd stockengine && python alerts/scheduler.py --once
      - run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add stockengine/watchlist/last_scores.json
          git diff --staged --quiet || git commit -m "chore: scheduler update scores [skip ci]"
          git push
```

**Secrets GitHub requis (obsolète) :**

| Nom | Valeur |
|---|---|
| `GROQ_API_KEY` | Clé Groq |
| `NEWS_API_KEY` | Clé NewsAPI |
| `SMTP_PASSWORD` | App Password Gmail 16 caractères |
