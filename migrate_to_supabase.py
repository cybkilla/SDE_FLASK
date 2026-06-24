#!/usr/bin/env python3
"""
migrate_to_supabase.py
Importe les utilisateurs (auth/users.yaml) et les watchlists (watchlist/watchlist.json)
dans les tables Supabase. Les entrées déjà présentes sont ignorées (pas d'écrasement).

Usage :
    python migrate_to_supabase.py
"""

import json
import sys
from pathlib import Path

# ── Chargement .env ──────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import os
SUPABASE_URL         = os.getenv("SUPABASE_URL",         "").strip()
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "").strip()

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("❌  SUPABASE_URL et SUPABASE_SERVICE_KEY doivent être renseignés dans .env")
    print("   → Supabase : Project Settings → API → service_role (secret)")
    sys.exit(1)

from supabase import create_client
# La service_role key bypasse le Row Level Security — réservée aux scripts admin
client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
print(f"✓  Connecté à Supabase : {SUPABASE_URL}\n")

# ── Chemins ───────────────────────────────────────────────────────────────────
ROOT          = Path(__file__).parent
USERS_FILE     = ROOT / "auth"      / "users.yaml"
WATCHLIST_FILE = ROOT / "watchlist" / "watchlist.json"
SCORES_FILE    = ROOT / "watchlist" / "last_scores.json"


# ── 1. Utilisateurs ───────────────────────────────────────────────────────────

def migrate_users():
    if not USERS_FILE.exists():
        print(f"⚠️   {USERS_FILE} introuvable — utilisateurs ignorés")
        return

    import yaml
    config = yaml.safe_load(USERS_FILE.read_text()) or {}
    usernames = config.get("credentials", {}).get("usernames", {})

    if not usernames:
        print("⚠️   Aucun utilisateur dans users.yaml")
        return

    print(f"── Utilisateurs ({len(usernames)} trouvés) ────────────────────────")

    # Récupérer les users déjà présents dans Supabase
    existing = {r["username"] for r in client.table("users").select("username").execute().data}

    inserted = skipped = 0
    for username, data in usernames.items():
        if username in existing:
            print(f"   ⏭  {username} — déjà présent, ignoré")
            skipped += 1
            continue
        client.table("users").insert({
            "username": username,
            "name":     data.get("name", username),
            "email":    data.get("email", ""),
            "password": data["password"],
        }).execute()
        print(f"   ✓  {username} ({data.get('name', '')})")
        inserted += 1

    print(f"   → {inserted} importé(s), {skipped} ignoré(s)\n")


# ── 2. Watchlists ─────────────────────────────────────────────────────────────

def migrate_watchlist():
    if not WATCHLIST_FILE.exists():
        print(f"⚠️   {WATCHLIST_FILE} introuvable — watchlists ignorées")
        return

    data = json.loads(WATCHLIST_FILE.read_text())

    total_items = sum(len(v) for v in data.values())
    print(f"── Watchlists ({total_items} entrée(s) pour {len(data)} user(s)) ──")

    # Récupérer les paires (username, ticker) déjà présentes
    existing_rows = client.table("watchlist").select("username,ticker").execute().data
    existing = {(r["username"], r["ticker"]) for r in existing_rows}

    inserted = skipped = 0
    for username, items in data.items():
        for item in items:
            ticker = item["ticker"].upper()
            if (username, ticker) in existing:
                print(f"   ⏭  {username}/{ticker} — déjà présent, ignoré")
                skipped += 1
                continue
            client.table("watchlist").insert({
                "username": username,
                "ticker":   ticker,
                "company":  item.get("company", ""),
                "added_at": item.get("added_at", ""),
            }).execute()
            print(f"   ✓  {username}/{ticker}")
            inserted += 1

    print(f"   → {inserted} importé(s), {skipped} ignoré(s)\n")


# ── 3. Scores ─────────────────────────────────────────────────────────────────

def migrate_scores():
    if not SCORES_FILE.exists():
        print(f"⚠️   {SCORES_FILE} introuvable — scores ignorés")
        return

    data = json.loads(SCORES_FILE.read_text())
    print(f"── Scores ({len(data)} ticker(s)) ──────────────────────────────────")

    existing = {r["ticker"] for r in client.table("scores").select("ticker").execute().data}

    inserted = skipped = 0
    for ticker, entry in data.items():
        ticker = ticker.upper()
        if ticker in existing:
            print(f"   ⏭  {ticker} — déjà présent, ignoré")
            skipped += 1
            continue
        client.table("scores").insert({
            "ticker":  ticker,
            "score":   entry.get("score"),
            "reco":    entry.get("reco", ""),
            "updated": entry.get("updated", ""),
            "prix":    entry.get("prix"),
        }).execute()
        print(f"   ✓  {ticker} — score {entry.get('score')} ({entry.get('reco')})")
        inserted += 1

    print(f"   → {inserted} importé(s), {skipped} ignoré(s)\n")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    migrate_users()
    migrate_watchlist()
    migrate_scores()
    print("Migration terminée ✓")
