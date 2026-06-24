# data/market.py — OHLCV via Twelve Data + quote/fondamentaux via Finnhub
import re
import pandas as pd
from utils.indicators import add_indicators
from config import HISTORY_DAYS, FINNHUB_API_KEY, TWELVE_DATA_API_KEY

# ── Finnhub client (singleton) ────────────────────────────
_fh_client = None


def _fh():
    global _fh_client
    if _fh_client is None:
        if not FINNHUB_API_KEY:
            raise RuntimeError(
                "FINNHUB_API_KEY absent — ajoutez-la dans .env et sur Render"
            )
        import finnhub
        _fh_client = finnhub.Client(api_key=FINNHUB_API_KEY)
    return _fh_client


# ── Helpers ───────────────────────────────────────────────
def _safe(val, default=None):
    if val is None:
        return default
    try:
        return default if pd.isna(val) else val
    except Exception:
        return val


def _period_to_days(period: str) -> int:
    m = re.match(r"(\d+)(d|w|mo|m|y)", period.lower())
    if not m:
        return 90
    n, unit = int(m.group(1)), m.group(2)
    return n * {"d": 1, "w": 7, "mo": 30, "m": 30, "y": 365}.get(unit, 1)


# ── Twelve Data : OHLCV historique (NASDAQ / NYSE) ───────
def _get_candles(ticker: str, days: int) -> pd.DataFrame:
    """Récupère l'historique OHLCV depuis Twelve Data (marchés US)."""
    if not TWELVE_DATA_API_KEY:
        raise RuntimeError(
            "TWELVE_DATA_API_KEY absent — ajoutez-la dans .env et sur Render"
        )
    from twelvedata import TDClient
    td = TDClient(apikey=TWELVE_DATA_API_KEY)

    params = {"symbol": ticker, "interval": "1day", "outputsize": min(days, 5000), "order": "ASC"}

    try:
        ts = td.time_series(**params).as_pandas()
    except Exception as e:
        print(f"[Market] Twelve Data erreur ({ticker}): {e}")
        return pd.DataFrame()

    if ts is None or ts.empty:
        return pd.DataFrame()

    ts.index = pd.to_datetime(ts.index)
    ts.index.name = "Date"
    ts = ts.rename(columns={
        "open": "Open", "high": "High",
        "low":  "Low",  "close": "Close", "volume": "Volume",
    })
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col in ts.columns:
            ts[col] = pd.to_numeric(ts[col], errors="coerce")

    cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in ts.columns]
    return ts[cols].dropna(subset=["Close"]).sort_index()


# ── Finnhub : quote temps réel ────────────────────────────
def _get_quote(symbol: str) -> dict:
    try:
        return _fh().quote(symbol) or {}
    except Exception:
        return {}


# ── Finnhub : profil entreprise ───────────────────────────
def _get_profile(symbol: str) -> dict:
    try:
        return _fh().company_profile2(symbol=symbol) or {}
    except Exception:
        return {}


# ── Finnhub : fondamentaux ────────────────────────────────
def _get_metrics(symbol: str) -> dict:
    try:
        data = _fh().company_basic_financials(symbol, "all") or {}
        return data.get("metric", {})
    except Exception:
        return {}


# ── Finnhub : dirigeants ──────────────────────────────────
def _get_executives(symbol: str) -> tuple:
    try:
        data    = _fh().company_executives(symbol) or {}
        persons = data.get("executive", []) or []

        def _find(role: str) -> str:
            return next(
                (p.get("name", "N/A") for p in persons
                 if role in p.get("title", "").upper()),
                "N/A",
            )

        return _find("CEO"), _find("CFO")
    except Exception:
        return "N/A", "N/A"


# ── Fonction principale ───────────────────────────────────
def get_market_data(ticker: str) -> dict:
    """
    Collecte les données marché :
      - Historique OHLCV : Twelve Data  (fonctionne sur cloud, plan gratuit)
      - Quote temps réel : Finnhub quote (60 req/min, plan gratuit)
      - Profil + fondamentaux : Finnhub  (plan gratuit)
    Interface retour identique à l'ancienne version yfinance.
    """
    ticker = ticker.upper().strip()

    # ── 1. Historique OHLCV (Twelve Data) ───────────────
    days = _period_to_days(HISTORY_DAYS)
    hist = _get_candles(ticker, days)

    # Fallback sur 30 j si l'historique complet est vide
    if hist.empty and days > 30:
        hist = _get_candles(ticker, 30)

    if hist.empty:
        raise ValueError(
            f"Ticker '{ticker}' introuvable ou sans données — vérifiez le symbole."
        )

    # ── 2. Indicateurs techniques (Pandas) ──────────────
    hist        = hist.rename_axis("Date").pipe(add_indicators)
    hist_closed = hist.dropna(subset=["Close"])
    if hist_closed.empty:
        raise ValueError(f"Ticker '{ticker}' : aucune clôture disponible.")

    hist_closed = hist_closed.copy()
    close       = hist_closed["Close"]
    hist_closed["Ret_1d"]    = close.pct_change(1)  * 100
    hist_closed["Ret_5d"]    = close.pct_change(5)  * 100
    hist_closed["Ret_30d"]   = close.pct_change(30) * 100
    hist_closed["Vol_ratio"] = (
        hist_closed["Volume"] / hist_closed["Volume"].rolling(20).mean()
    ).round(2)
    hist = hist_closed
    last = hist.iloc[-1]

    def _ind(col, default, digits=2):
        try:
            v = float(last[col])
            return round(v, digits) if not pd.isna(v) else default
        except Exception:
            return default

    # ── 3. Quote temps réel (Finnhub) ───────────────────
    fh_sym = ticker
    quote      = _get_quote(fh_sym)
    live_price = _safe(quote.get("c")) or round(float(last["Close"]), 2)
    prev_close = _safe(quote.get("pc"))

    if live_price and prev_close:
        var_1d = round((live_price - prev_close) / prev_close * 100, 2)
    else:
        var_1d = _ind("Ret_1d", 0.0)

    live_price = round(float(live_price), 2)

    # ── 4. Profil entreprise (Finnhub) ──────────────────
    profile = _get_profile(fh_sym)

    # ── 5. Fondamentaux (Finnhub) ────────────────────────
    metrics = _get_metrics(fh_sym)

    pe = _safe(
        metrics.get("peBasicExclExtraTTM")
        or metrics.get("peTTM")
        or metrics.get("peExclExtraTTM")
    )
    eps = _safe(
        metrics.get("epsBasicExclExtraTTM")
        or metrics.get("epsNormalizedAnnual")
    )
    de = _safe(
        metrics.get("totalDebt/totalEquityAnnual")
        or metrics.get("longTermDebt/equityAnnual")
    )
    rev_growth = _safe(metrics.get("revenueGrowthTTMYoy"))
    div_yield  = _safe(
        metrics.get("dividendYieldIndicatedAnnual")
        or metrics.get("dividendYield5Y")
    )
    mktcap_m   = (
        metrics.get("marketCapitalization")
        or profile.get("marketCapitalization")
    )
    market_cap = _safe(mktcap_m and mktcap_m * 1_000_000)

    # ── 6. Dirigeants (Finnhub) ──────────────────────────
    ceo_name, cfo_name = _get_executives(fh_sym)

    return {
        # Identification
        "ticker":         ticker,
        "company_name":   profile.get("name") or ticker,
        "sector":         profile.get("finnhubIndustry") or "N/A",
        "industry":       profile.get("finnhubIndustry") or "N/A",
        "currency":       profile.get("currency") or "USD",

        # Prix
        "price":          live_price,
        "prev_close":     round(float(prev_close), 2) if prev_close else None,
        "pre_market":     None,
        "post_market":    None,
        "var_1d":         var_1d,
        "var_5d":         _ind("Ret_5d",  0.0),
        "var_30d":        _ind("Ret_30d", 0.0),

        # Indicateurs techniques
        "rsi":            _ind("RSI",      50.0, digits=1),
        "ma20":           _ind("MA20",     live_price),
        "ma50":           _ind("MA50",     live_price),
        "macd":           _ind("MACD",     0.0, digits=4),
        "macd_signal":    _ind("MACD_sig", 0.0, digits=4),
        "bb_upper":       _ind("BB_upper", round(live_price * 1.05, 2)),
        "bb_lower":       _ind("BB_lower", round(live_price * 0.95, 2)),
        "vol_ratio":      _ind("Vol_ratio", 1.0),

        # Fondamentaux
        "pe_ratio":       pe,
        "eps":            eps,
        "debt_equity":    de,
        "revenue_growth": rev_growth,
        "market_cap":     market_cap,
        "dividend_yield": div_yield,

        # Dirigeants
        "ceo_name":       ceo_name,
        "cfo_name":       cfo_name,
        "officers":       [],

        # DataFrame complet (graphiques + scoring)
        "history":        hist,
    }
