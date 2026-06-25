# portfolio/advisor.py — Génération du conseil journalier par ticker
# Logique basée sur les signaux SDE + position de l'utilisateur.
# Pas d'appel LLM : règles transparentes, explicables, sans quota.

from datetime import date, datetime, timezone

_TABLE = "daily_advice"

# Labels lisibles pour chaque action
ACTION_LABELS = {
    "ACHETER":    ("↑ Acheter",    "#1D9E75", "success"),
    "RENFORCER":  ("↗ Renforcer",  "#15803d", "success"),
    "TENIR":      ("◆ Tenir",      "#BA7517", "warning"),
    "SURVEILLER": ("◎ Surveiller", "#5a6a7a", "secondary"),
    "ALLÉGER":    ("↘ Alléger",    "#D85A30", "danger"),
    "VENDRE":     ("↓ Vendre",     "#991b1b", "danger"),
}


# ── Génération du conseil ─────────────────────────────────────────────────────

def generate_advice(summary: dict | None, market: dict, snapshot: dict) -> dict:
    """
    Génère un conseil structuré à partir de la position et de l'analyse SDE.

    summary : résultat de get_portfolio_summary() — None si pas de position
    market  : dict market avec price, rsi, var_1d
    snapshot: dict pipeline avec score_global, recommandation, etc.
    """
    score  = float(snapshot.get("score_global", 50))
    reco   = snapshot.get("recommandation", "NEUTRE")
    rsi    = float(market.get("rsi") or 50)
    prix   = float(market.get("price") or 0)

    # ── Cas 1 : pas de position ───────────────────────────────────────────────
    if summary is None:
        if reco == "ACHETER" and score >= 60:
            return _conseil("ACHETER", None, prix,
                f"Pas de position. Signal SDE haussier ({score:.0f}/100, RSI {rsi:.0f}). "
                f"Opportunité d'entrée autour de {prix:.2f} $.")
        return _conseil("SURVEILLER", None, None,
            f"Pas de position. Signal SDE {reco} ({score:.0f}/100) — "
            f"attendre un signal plus fort avant d'entrer.")

    # ── Cas 2 : position existante ────────────────────────────────────────────
    pnl_pct      = float(summary["pnl_pct"])
    total_shares = float(summary["total_shares"])
    cout_moyen   = float(summary["cout_moyen"])

    # Stop loss automatique
    if pnl_pct <= -20:
        return _conseil("VENDRE", total_shares, prix,
            f"Stop loss atteint : position à {pnl_pct:+.1f}% (coût moyen {cout_moyen:.2f} $). "
            f"Limitation des pertes recommandée.")

    # Prise de bénéfices sur signal vendeur fort
    if pnl_pct >= 15 and reco == "VENDRE":
        alleger = max(1, round(total_shares * 0.5))
        return _conseil("ALLÉGER", alleger, prix,
            f"Plus-value de {pnl_pct:+.1f}% + signal SDE baissier ({score:.0f}/100). "
            f"Sécurisation de la moitié de la position recommandée.")

    # Signal vendeur fort sans plus-value importante
    if reco == "VENDRE" and score <= 38:
        return _conseil("VENDRE", total_shares, prix,
            f"Signal SDE baissier fort ({score:.0f}/100, RSI {rsi:.0f}). "
            f"Sortie de position recommandée (P&L actuelle : {pnl_pct:+.1f}%).")

    # Renforcement sur faiblesse
    if pnl_pct <= -5 and reco == "ACHETER" and rsi <= 42:
        renforcer = max(1, round(total_shares * 0.25))
        return _conseil("RENFORCER", renforcer, prix,
            f"RSI bas ({rsi:.0f}) + signal SDE haussier ({score:.0f}/100). "
            f"Opportunité de renforcement sur faiblesse ({pnl_pct:+.1f}% de latence).")

    # Signal haussier confirmé en territoire positif
    if reco == "ACHETER" and score >= 62 and pnl_pct > 0:
        return _conseil("TENIR", None, None,
            f"Signal SDE haussier ({score:.0f}/100) avec position en positif ({pnl_pct:+.1f}%). "
            f"Maintien recommandé, la tendance reste favorable.")

    # Défaut : tenir
    return _conseil("TENIR", None, None,
        f"Position à {pnl_pct:+.1f}% (coût moyen {cout_moyen:.2f} $). "
        f"Signal SDE {reco} ({score:.0f}/100) — maintien de la position.")


def _conseil(action, quantite, prix_cible, raisonnement) -> dict:
    return {
        "action":             action,
        "quantite_suggeree":  quantite,
        "prix_cible":         round(prix_cible, 4) if prix_cible else None,
        "raisonnement":       raisonnement,
    }


# ── Persistance Supabase ──────────────────────────────────────────────────────

def get_today_advice(username: str, ticker: str) -> dict | None:
    """Retourne le conseil du jour depuis Supabase si déjà généré."""
    try:
        from db import find_one, is_available
        if not is_available():
            return None
        row = find_one(_TABLE, {
            "username":     username,
            "ticker":       ticker.upper(),
            "date_conseil": str(date.today()),
        })
        return row
    except Exception as e:
        print(f"[Advisor] get_today_advice erreur : {e}", flush=True)
        return None


def save_advice(username: str, ticker: str, advice: dict,
                market: dict, snapshot: dict) -> dict:
    """Upsert le conseil du jour dans Supabase. Retourne la ligne."""
    try:
        from db import update_one, is_available
        if not is_available():
            return advice
        row = {
            "action":             advice["action"],
            "quantite_suggeree":  advice.get("quantite_suggeree"),
            "prix_jour":          market.get("price"),
            "prix_cible":         advice.get("prix_cible"),
            "score_sde":          snapshot.get("score_global"),
            "recommandation":     snapshot.get("recommandation"),
            "raisonnement":       advice.get("raisonnement"),
        }
        update_one(
            _TABLE,
            {"username": username, "ticker": ticker.upper(), "date_conseil": str(date.today())},
            {"$set": row},
            upsert=True,
        )
        return {**row, "username": username, "ticker": ticker, "date_conseil": str(date.today())}
    except Exception as e:
        print(f"[Advisor] save_advice erreur : {e}", flush=True)
        return advice


def get_advice_history(username: str, ticker: str, limit: int = 30) -> list:
    """Retourne l'historique des conseils (plus récent en premier)."""
    try:
        from db import _init, _client, is_available
        if not is_available():
            return []
        _init()
        rows = (
            _client.table(_TABLE)
            .select("*")
            .eq("username", username)
            .eq("ticker", ticker.upper())
            .order("date_conseil", desc=True)
            .limit(limit)
            .execute()
            .data or []
        )
        return rows
    except Exception as e:
        print(f"[Advisor] get_advice_history erreur : {e}", flush=True)
        return []


def evaluate_yesterday_advice(username: str, ticker: str, current_price: float):
    """
    Appelé par le scheduler : évalue le conseil d'hier avec le prix actuel.
    Met à jour prix_j1, variation_j1, bon_conseil dans daily_advice.
    """
    from datetime import timedelta
    yesterday = str(date.today() - timedelta(days=1))
    try:
        from db import find_one, update_one, is_available
        if not is_available():
            return

        row = find_one(_TABLE, {
            "username":     username,
            "ticker":       ticker.upper(),
            "date_conseil": yesterday,
        })
        if not row or row.get("evaluated_at"):
            return  # Déjà évalué ou inexistant

        prix_hier    = float(row.get("prix_jour") or 0)
        action       = row.get("action", "")
        variation_j1 = round((current_price - prix_hier) / prix_hier * 100, 2) if prix_hier else 0

        # Le conseil était-il bon ?
        bon = None
        if action in ("ACHETER", "RENFORCER"):
            bon = variation_j1 > 0   # bon si prix a monté
        elif action in ("VENDRE", "ALLÉGER"):
            bon = variation_j1 < 0   # bon si prix a baissé
        elif action == "TENIR":
            bon = abs(variation_j1) < 3  # bon si stable (< 3%)

        update_one(
            _TABLE,
            {"username": username, "ticker": ticker.upper(), "date_conseil": yesterday},
            {"$set": {
                "prix_j1":       round(current_price, 4),
                "variation_j1":  variation_j1,
                "bon_conseil":   bon,
                "evaluated_at":  datetime.now(timezone.utc).isoformat(),
            }},
        )
        emoji = "✓" if bon else "✗" if bon is not None else "?"
        print(f"[Advisor] {ticker} conseil {yesterday} évalué : {emoji} "
              f"({action}, var={variation_j1:+.1f}%)", flush=True)
    except Exception as e:
        print(f"[Advisor] evaluate_yesterday_advice erreur : {e}", flush=True)
