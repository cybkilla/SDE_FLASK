# Scheduler SDE — Mise en place sur GitHub Actions

## Ce que fait le scheduler

Toutes les heures, GitHub Actions :
1. Récupère les prix et scores actuels de chaque ticker suivi dans les watchlists
2. Compare avec le dernier état connu (`last_scores.json`)
3. Envoie un email d'alerte si la variation dépasse ±5 % ou si la recommandation change
4. Met à jour `last_scores.json` avec les nouveaux prix et scores (commit automatique)

---

## Étapes de mise en place

### 1. Créer le fichier workflow

Créer `.github/workflows/scheduler.yml` à la racine du repo :

```yaml
name: SDE Scheduler

on:
  schedule:
    - cron: "0 * * * *"   # toutes les heures (minute 0)
  workflow_dispatch:        # déclenchement manuel depuis l'onglet Actions

permissions:
  contents: write           # permet au bot de committer last_scores.json

jobs:
  run-scheduler:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install dependencies
        run: pip install -r stockengine/requirements-scheduler.txt

      - name: Run scheduler (one pass)
        env:
          GROQ_API_KEY:  ${{ secrets.GROQ_API_KEY }}
          NEWS_API_KEY:  ${{ secrets.NEWS_API_KEY }}
          SMTP_PASSWORD: ${{ secrets.SMTP_PASSWORD }}
        run: |
          cd stockengine
          python alerts/scheduler.py --once

      - name: Commit last_scores.json
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add stockengine/watchlist/last_scores.json
          git diff --staged --quiet || git commit -m "chore: scheduler update scores [skip ci]"
          git push
```

> `[skip ci]` dans le message de commit empêche ce commit de déclencher un nouveau run.

---

### 2. Créer `requirements-scheduler.txt`

Un fichier de dépendances allégé (sans `torch` / `transformers` qui pèsent ~2 Go et sont inutiles pour le scheduler) :

```
yfinance>=1.0.0
pandas==2.2.2
numpy==1.26.4
newsapi-python==0.2.7
feedparser==6.0.11
requests==2.32.3
beautifulsoup4==4.12.3
lxml==5.2.2
vaderSentiment==3.3.2
streamlit-authenticator>=0.4.2
bcrypt>=4.1.0
PyYAML>=6.0
groq>=0.9.0
```

---

### 3. Ajouter le mode `--once`

GitHub Actions a besoin que le script se termine. Sans `--once`, il tourne en boucle infinie :

```python
if "--once" in sys.argv:
    check_all()
else:
    while True:
        check_all()
        time.sleep(CHECK_INTERVAL_MIN * 60)
```

---

### 4. Activer les permissions d'écriture sur le repo

Dans GitHub :  
**Settings → Actions → General → Workflow permissions**  
→ Cocher **"Read and write permissions"** → Save

Sans ça, le `git push` du bot échoue avec une erreur 403.

---

### 5. Ajouter les secrets

Dans GitHub :  
**Settings → Secrets and variables → Actions → New repository secret**

| Nom | Valeur |
|---|---|
| `GROQ_API_KEY` | Clé Groq (console.groq.com) |
| `NEWS_API_KEY` | Clé NewsAPI (newsapi.org) |
| `SMTP_PASSWORD` | App Password Gmail 16 caractères (pas le mot de passe Google) |

> Les valeurs ne sont pas lisibles après enregistrement — c'est normal.

---

## Lancer manuellement et vérifier

### Déclencher un run

1. Aller sur GitHub → onglet **Actions**
2. Cliquer sur **"SDE Scheduler"** dans la liste à gauche
3. Cliquer sur **"Run workflow"** (bouton gris à droite) → **"Run workflow"**
4. Le run apparaît dans la liste en quelques secondes

### Lire les logs

Cliquer sur le run → **"run-scheduler"** → chaque étape est dépliable.

La sortie attendue dans **"Run scheduler (one pass)"** :

```
[Scheduler] Mode one-shot (--once)
[Scheduler] Vérification de 4 utilisateur(s)…
  [LLM] Groq — OK
  → Alerte GOOG pour admin (ACHETER→ACHETER, var_tracked=+2.1%)
  ✗ Erreur SPCX : Ticker 'SPCX' : aucune clôture disponible.
```

### Vérifier que `last_scores.json` a été mis à jour

**Option 1 — Dans GitHub**  
Onglet **Code** → `stockengine/watchlist/last_scores.json`  
→ Le champ `"updated"` de chaque ticker doit correspondre à l'heure du run.

**Option 2 — Dans les logs Actions**  
Étape **"Commit last_scores.json"** :
- `[main abc1234] chore: scheduler update scores [skip ci]` → fichier mis à jour ✅
- `nothing to commit` → prix inchangés depuis le dernier run (normal en dehors des heures de marché) ✅

**Option 3 — Historique des commits**  
Onglet **Code** → icône horloge (commits) → chercher les commits `chore: scheduler update scores`.

---

## Dépannage rapide

| Symptôme | Cause | Solution |
|---|---|---|
| `has no attribute 'Search'` | yfinance trop vieux | `yfinance>=1.0.0` dans requirements |
| `Expecting value: line 1 column 1` | Même cause | Idem |
| `ModuleNotFoundError: pipeline` | Path Python incorrect | `sys.path.insert` en tête de `scheduler.py` |
| `535 Auth Error` SMTP | Mauvais App Password | Regénérer sur myaccount.google.com |
| `403` sur le git push | Permissions insuffisantes | Settings → Actions → Read and write permissions |
| Pas d'email reçu | Aucun seuil dépassé | Modifier `last_scores.json` avec un vieux prix pour forcer l'alerte |
