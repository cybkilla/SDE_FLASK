# data/market.py — données marché via Finnhub (fonctionne sur cloud)
import re
import time
import pandas as pd
from utils.indicators import add_indicators
from config import HISTORY_DAYS, FINNHUB_API_KEY

# ── Client Finnhub (singleton) ────────────────────────────
_fh_client = None


def _client():
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


def _ticker_candidates(ticker: str) -> list:
    """Variantes Finnhub à essayer pour un ticker au format yfinance (ex. MC.PA → MC)."""
    candidates = [ticker.upper()]
    if "." in ticker:
        candidates.append(ticker.upper().split(".")[0])
    return candidates


# ── Fetchers Finnhub ──────────────────────────────────────
def _get_candles(fh, symbol: str, days: int) -> pd.DataFrame:
    to_ts   = int(time.time())
    from_ts = to_ts - days * 86_400
    try:
        data = fh.stock_candles(symbol, "D", from_ts, to_ts)
    except Exception:
        return pd.DataFrame()
    if data.get("s") != "ok" or not data.get("c"):
        return pd.DataFrame()
    df = pd.DataFrame(
        {
            "Open":   data["o"],
            "High":   data["h"],
            "Low":    data["l"],
            "Close":  data["c"],
            "Volume": data["v"],
        },
        index=pd.to_datetime(data["t"], unit="s", utc=True).tz_convert(None),
    )
    df.index.name = "Date"
    df.index = df.index.normalize()
    return df.sort_index()


def _get_quote(fh, symbol: str) -> dict:
    try:
        return fh.quote(symbol) or {}
    except Exception:
        return {}


def _get_profile(fh, symbol: str) -> dict:
    try:
        return fh.company_profile2(symbol=symbol) or {}
    except Exception:
        return {}


def _get_metrics(fh, symbol: str) -> dict:
    try:
        data = fh.company_basic_financials(symbol, "all") or {}
        return data.get("metric", {})
    except Exception:
        return {}


def _get_executives(fh, symbol: str) -> tuple:
    try:
        data    = fh.company_executives(symbol) or {}
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
    Collecte les données marché via Finnhub.
    Interface identique à l'ancienne version yfinance :
    retourne un dict avec 'history' DataFrame + scalaires.
    """
    ticker = ticker.upper().strip()
    fh     = _client()

    # ── 1. Historique des cours ──────────────────────────
    days = _period_to_days(HISTORY_DAYS)
    hist = pd.DataFrame()
    fh_symbol = ticker

    for symbol in _ticker_candidates(ticker):
        for d in (days, 30, 5):
            hist = _get_candles(fh, symbol, d)
            if not hist.empty:
                fh_symbol = symbol
                break
        if not hist.empty:
            break

    if hist.empty:
        raise ValueError(
            f"Ticker '{ticker}' introuvable sur Finnhub — vérifiez le symbole."
        )

    # ── 2. Indicateurs techniques ────────────────────────
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

    # ── 3. Prix temps réel ───────────────────────────────
    quote      = _get_quote(fh, fh_symbol)
    live_price = _safe(quote.get("c")) or round(float(last["Close"]), 2)
    prev_close = _safe(quote.get("pc"))

    if live_price and prev_close:
        var_1d = round((live_price - prev_close) / prev_close * 100, 2)
    else:
        var_1d = _ind("Ret_1d", 0.0)

    live_price = round(float(live_price), 2)

    # ── 4. Profil entreprise ─────────────────────────────
    profile = _get_profile(fh, fh_symbol)

    # ── 5. Fondamentaux ──────────────────────────────────
    metrics = _get_metrics(fh, fh_symbol)

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
    mktcap_m   = metrics.get("marketCapitalization") or profile.get("marketCapitalization")
    market_cap = _safe(mktcap_m and mktcap_m * 1_000_000)

    # ── 6. Dirigeants ────────────────────────────────────
    ceo_name, cfo_name = _get_executives(fh, fh_symbol)

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

        # DataFrame complet (graphiques)
        "history":        hist,
    }
