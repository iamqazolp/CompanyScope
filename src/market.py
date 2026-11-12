from concurrent.futures import ThreadPoolExecutor
import datetime
import email.utils
import hashlib
import re
import threading
from typing import Any
import xml.etree.ElementTree as ET

from edgar import Company, set_identity
from rank_bm25 import BM25Okapi
import requests

from src.config import EDGAR_IDENTITY, FINNHUB_API_KEY, OPENAI_KEY, TIER2_MODEL
from src.db import get_market_cache, set_market_cache
from src.guard import verify_citations

set_identity(EDGAR_IDENTITY)

_yf_lock = threading.Lock()
_yf_session: requests.Session | None = None
_yf_crumb: str | None = None
_yf_crumb_ts: float = 0.0

_UA_HEADER = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
}

_EXCHANGE_TO_TV: dict[str, str] = {
    "NMS": "NASDAQ",
    "NGM": "NASDAQ",
    "NCM": "NASDAQ",
    "NAS": "NASDAQ",
    "NASDAQ": "NASDAQ",
    "NYQ": "NYSE",
    "NYS": "NYSE",
    "NYSE": "NYSE",
    "PCX": "AMEX",
    "ASE": "AMEX",
    "AMX": "AMEX",
    "BTS": "AMEX",
}

_BENCHMARK_INDICES: tuple[tuple[str, str, str], ...] = (
    ("^GSPC", "S&P 500", "SP:SPX"),
    ("^NDX", "Nasdaq 100", "NASDAQ:NDX"),
    ("^DJI", "Dow 30", "DJ:DJI"),
    ("^TNX", "US 10Y Yield", "TVC:US10Y"),
    ("^VIX", "VIX Volatility", "TVC:VIX"),
    ("BTC-USD", "Bitcoin", "COINBASE:BTCUSD"),
)

_TIMEFRAME_PARAMS: dict[str, tuple[str, str, bool]] = {
    "1D": ("1d", "5m", True),
    "5D": ("5d", "15m", True),
    "1M": ("1mo", "1d", False),
    "6M": ("6mo", "1d", False),
    "1Y": ("1y", "1d", False),
    "5Y": ("5y", "1wk", False),
}


def resolve_tradingview_symbol(ticker: str, exchange_code: str = "") -> str:
    """Maps a stock ticker and Yahoo exchange code to a TradingView exchange:symbol identifier."""
    clean = ticker.upper().strip()
    ex = exchange_code.upper().strip()
    if ex in _EXCHANGE_TO_TV:
        return f"{_EXCHANGE_TO_TV[ex]}:{clean}"
    nyse_common = {
        "JPM", "BAC", "WFC", "GS", "MS", "V", "MA", "BRK.B", "BRK-B", "XOM",
        "CVX", "LLY", "UNH", "JNJ", "PG", "KO", "WMT", "HD", "DIS", "CRM",
        "ORCL", "IBM", "UBER", "TSM", "NVO", "BA", "CAT", "GE",
    }
    if clean in nyse_common:
        return f"NYSE:{clean.replace('-', '.')}"
    return f"NASDAQ:{clean}"


def _get_yf_session_and_crumb(force_refresh: bool = False) -> tuple[requests.Session, str]:
    global _yf_session, _yf_crumb, _yf_crumb_ts
    now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
    with _yf_lock:
        if (
            not force_refresh
            and _yf_session is not None
            and _yf_crumb
            and (now_ts - _yf_crumb_ts) < 1800
        ):
            return _yf_session, _yf_crumb

        sess = requests.Session()
        sess.headers.update(_UA_HEADER)
        try:
            sess.get("https://fc.yahoo.com", timeout=5)
            r_crumb = sess.get(
                "https://query2.finance.yahoo.com/v1/test/getcrumb", timeout=5
            )
            if r_crumb.ok and r_crumb.text.strip():
                _yf_session = sess
                _yf_crumb = r_crumb.text.strip()
                _yf_crumb_ts = now_ts
                return sess, _yf_crumb
        except Exception:
            pass

        _yf_session = sess
        _yf_crumb = ""
        _yf_crumb_ts = now_ts
        return sess, ""


def _raw_num(obj: Any) -> float | None:
    if isinstance(obj, (int, float)):
        return float(obj)
    if isinstance(obj, dict) and isinstance(obj.get("raw"), (int, float)):
        return float(obj["raw"])
    return None


def _relative_age(dt: datetime.datetime) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    delta_sec = max(0.0, (now - dt).total_seconds())
    if delta_sec < 3600:
        mins = max(1, int(delta_sec // 60))
        return f"{mins}m ago"
    if delta_sec < 86400:
        hrs = int(delta_sec // 3600)
        return f"{hrs}h ago"
    days = int(delta_sec // 86400)
    return f"{days}d ago"


def _tv_rec_label(mark: float | None) -> str:
    if mark is None:
        return ""
    if mark <= 1.5:
        return "strong_buy"
    if mark <= 2.2:
        return "buy"
    if mark <= 3.2:
        return "hold"
    if mark <= 4.2:
        return "underperform"
    return "sell"


_SECTOR_PEERS: dict[str, list[str]] = {
    "Electronic Technology": ["NVDA", "AVGO", "AMD", "MU", "AAPL"],
    "Technology Services": ["MSFT", "GOOGL", "META", "ORCL", "PLTR"],
    "Finance": ["JPM", "BAC", "GS", "MS", "V"],
    "Health Technology": ["LLY", "ABBV", "JNJ", "MRK", "PFE"],
    "Health Services": ["UNH", "CI", "CVS", "ELV"],
    "Retail Trade": ["AMZN", "WMT", "COST", "HD"],
    "Consumer Durables": ["TSLA", "NKE", "GM", "F"],
    "Consumer Non-Durables": ["PG", "KO", "PEP", "PM"],
    "Consumer Services": ["NFLX", "MCD", "SBUX", "DIS", "BKNG"],
    "Communications": ["TMUS", "VZ", "T", "CMCSA"],
    "Energy Minerals": ["XOM", "CVX", "COP", "EOG"],
    "Producer Manufacturing": ["GE", "CAT", "RTX", "HON", "ETN"],
    "Transportation": ["UBER", "UNP", "UPS", "FDX"],
    "Process Industries": ["LIN", "SHW", "APD", "ECL"],
    "Utilities": ["NEE", "CEG", "SO", "DUK"],
}


def _suggest_sector_peers(clean: str, sector: str = "") -> list[str]:
    pool = _SECTOR_PEERS.get(sector) or ["NVDA", "MSFT", "JPM", "AMZN"]
    peers = [p for p in pool if p != clean]
    return peers[:3]


def _fetch_tradingview_equity_snapshot(clean: str) -> dict[str, Any] | None:
    """Queries TradingView's America Scanner API for live price, multiples, sector, and consensus targets."""
    cols = [
        "name",
        "description",
        "exchange",
        "close",
        "change",
        "change_abs",
        "volume",
        "price_52_week_high",
        "price_52_week_low",
        "market_cap_basic",
        "enterprise_value_fq",
        "price_earnings_ttm",
        "earnings_per_share_forecast_next_fy",
        "enterprise_value_ebitda_ttm",
        "price_book_fq",
        "dividends_yield_current",
        "beta_1_year",
        "price_target_average",
        "price_target_high",
        "price_target_low",
        "recommendation_mark",
        "sector",
    ]
    sym_candidates = [clean]
    if "-" in clean:
        sym_candidates.append(clean.replace("-", "."))
    try:
        r_tv = requests.post(
            "https://scanner.tradingview.com/america/scan",
            json={
                "filter": [
                    {"left": "name", "operation": "in_range", "right": sym_candidates},
                    {
                        "left": "exchange",
                        "operation": "in_range",
                        "right": ["NASDAQ", "NYSE", "AMEX"],
                    },
                    {"left": "is_primary", "operation": "equal", "right": True},
                ],
                "columns": cols,
                "range": [0, 5],
            },
            headers=_UA_HEADER,
            timeout=6,
        )
        if not r_tv.ok:
            return None
        rows = (r_tv.json() or {}).get("data") or []
        if not rows:
            return None
        row = rows[0]
        d = row.get("d") or []
        if len(d) < len(cols):
            return None
        px = _raw_num(d[3])
        if px is None:
            return None
        chg_pct = _raw_num(d[4])
        chg_abs = _raw_num(d[5])
        prev_close = (px - chg_abs) if chg_abs is not None else None
        fwd_eps = _raw_num(d[12])
        fwd_pe = (px / fwd_eps) if (fwd_eps is not None and fwd_eps > 0) else None
        vol_num = _raw_num(d[6])
        return {
            "tv_symbol": str(row.get("s") or ""),
            "short_name": str(d[1] or clean),
            "exchange_code": str(d[2] or ""),
            "price": px,
            "prev_close": prev_close,
            "change": chg_abs,
            "change_pct": round(chg_pct, 2) if chg_pct is not None else None,
            "volume": int(vol_num) if vol_num is not None else None,
            "high_52w": _raw_num(d[7]),
            "low_52w": _raw_num(d[8]),
            "market_cap": _raw_num(d[9]),
            "enterprise_value": _raw_num(d[10]),
            "trailing_pe": _raw_num(d[11]),
            "forward_pe": fwd_pe,
            "ev_to_ebitda": _raw_num(d[13]),
            "price_to_book": _raw_num(d[14]),
            "dividend_yield_pct": _raw_num(d[15]),
            "beta": _raw_num(d[16]),
            "target_mean": _raw_num(d[17]),
            "target_high": _raw_num(d[18]),
            "target_low": _raw_num(d[19]),
            "recommendation": _tv_rec_label(_raw_num(d[20])),
            "sector": str(d[21] or ""),
        }
    except Exception:
        return None


def search_market_tickers(query: str, limit: int = 8) -> list[dict[str, Any]]:
    """
    Live US equity/ADR/ETF autocomplete across 6,000+ NASDAQ/NYSE/AMEX listings via
    TradingView's America Scanner API (matching ticker symbol or company name).
    """
    q_clean = re.sub(r"[^A-Za-z0-9.\- &]", "", (query or "").strip())
    if not q_clean:
        return get_market_movers(limit=limit)

    cache_key = f"search_v1:{q_clean.lower()}:{limit}"
    cached = get_market_cache(cache_key, ttl_seconds=600)
    if isinstance(cached, list) and cached:
        return cached

    q_upper = q_clean.upper()
    cols = [
        "name",
        "description",
        "exchange",
        "close",
        "change",
        "market_cap_basic",
        "sector",
        "type",
    ]
    try:
        r_tv = requests.post(
            "https://scanner.tradingview.com/america/scan",
            json={
                "filter": [
                    {
                        "left": "exchange",
                        "operation": "in_range",
                        "right": ["NASDAQ", "NYSE", "AMEX"],
                    },
                    {"left": "is_primary", "operation": "equal", "right": True},
                ],
                "filter2": {
                    "operator": "or",
                    "operands": [
                        {
                            "operation": {
                                "operator": "or",
                                "operands": [
                                    {
                                        "expression": {
                                            "left": "name",
                                            "operation": "match",
                                            "right": q_clean,
                                        }
                                    },
                                    {
                                        "expression": {
                                            "left": "description",
                                            "operation": "match",
                                            "right": q_clean,
                                        }
                                    },
                                ],
                            }
                        }
                    ],
                },
                "columns": cols,
                "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
                "range": [0, max(16, limit * 2)],
            },
            headers=_UA_HEADER,
            timeout=5,
        )
        if not r_tv.ok:
            return []
        rows = (r_tv.json() or {}).get("data") or []
        scored: list[tuple[tuple[int, float], dict[str, Any]]] = []
        seen: set[str] = set()
        for row in rows:
            d = row.get("d") or []
            if len(d) < len(cols):
                continue
            raw_sym = str(d[0] or "").upper().strip()
            edgar_sym = raw_sym.replace(".", "-")
            if not edgar_sym or len(edgar_sym) > 6 or edgar_sym in seen:
                continue
            px = _raw_num(d[3])
            if px is None:
                continue
            seen.add(edgar_sym)
            chg = _raw_num(d[4])
            mcap = _raw_num(d[5]) or 0.0
            exch = str(d[2] or "")
            tv_sym = str(row.get("s") or f"{exch}:{raw_sym}")
            rank_tier = (
                2
                if edgar_sym == q_upper or raw_sym == q_upper
                else (1 if edgar_sym.startswith(q_upper) else 0)
            )
            scored.append(
                (
                    (rank_tier, mcap),
                    {
                        "ticker": edgar_sym,
                        "company_name": str(d[1] or edgar_sym),
                        "exchange": exch,
                        "tradingview_symbol": tv_sym,
                        "price": round(px, 2),
                        "change_pct": round(chg, 2) if chg is not None else None,
                        "market_cap": mcap if mcap > 0 else None,
                        "sector": str(d[6] or ""),
                    },
                )
            )
        scored.sort(key=lambda item: item[0], reverse=True)
        out = [item[1] for item in scored[:limit]]
        if out:
            set_market_cache(cache_key, out)
        return out
    except Exception:
        return []


def get_market_movers(limit: int = 10) -> list[dict[str, Any]]:
    """
    Returns today's most actively traded US large-cap equities by dollar volume ($ Value.Traded)
    across NASDAQ and NYSE, cached for 3 minutes.
    """
    cache_key = f"movers_v2:{limit}"
    cached = get_market_cache(cache_key, ttl_seconds=180)
    if isinstance(cached, list) and cached:
        return cached

    cols = [
        "name",
        "description",
        "exchange",
        "close",
        "change",
        "market_cap_basic",
        "sector",
        "Value.Traded",
    ]
    try:
        r_tv = requests.post(
            "https://scanner.tradingview.com/america/scan",
            json={
                "filter": [
                    {
                        "left": "exchange",
                        "operation": "in_range",
                        "right": ["NASDAQ", "NYSE"],
                    },
                    {"left": "type", "operation": "equal", "right": "stock"},
                    {"left": "is_primary", "operation": "equal", "right": True},
                    {
                        "left": "market_cap_basic",
                        "operation": "egreater",
                        "right": 20000000000,
                    },
                    {
                        "left": "total_revenue_ttm",
                        "operation": "egreater",
                        "right": 1000000000,
                    },
                ],
                "columns": cols,
                "sort": {"sortBy": "Value.Traded", "sortOrder": "desc"},
                "range": [0, max(limit + 4, 12)],
            },
            headers=_UA_HEADER,
            timeout=5,
        )
        if r_tv.ok:
            rows = (r_tv.json() or {}).get("data") or []
            movers: list[dict[str, Any]] = []
            seen: set[str] = set()
            for row in rows:
                d = row.get("d") or []
                if len(d) < len(cols):
                    continue
                raw_sym = str(d[0] or "").upper().strip()
                edgar_sym = raw_sym.replace(".", "-")
                if not edgar_sym or len(edgar_sym) > 6 or edgar_sym in seen:
                    continue
                px = _raw_num(d[3])
                if px is None:
                    continue
                seen.add(edgar_sym)
                chg = _raw_num(d[4])
                mcap = _raw_num(d[5])
                exch = str(d[2] or "")
                movers.append(
                    {
                        "ticker": edgar_sym,
                        "company_name": str(d[1] or edgar_sym),
                        "exchange": exch,
                        "tradingview_symbol": str(row.get("s") or f"{exch}:{raw_sym}"),
                        "price": round(px, 2),
                        "change_pct": round(chg, 2) if chg is not None else None,
                        "market_cap": mcap,
                        "sector": str(d[6] or ""),
                    }
                )
                if len(movers) >= limit:
                    break
            if movers:
                set_market_cache(cache_key, movers)
                return movers
    except Exception:
        pass

    fallback_syms = ["NVDA", "MSFT", "JPM", "LLY", "AMZN", "PLTR", "AVGO", "COST"]
    return [
        {
            "ticker": s,
            "company_name": s,
            "exchange": "",
            "tradingview_symbol": resolve_tradingview_symbol(s),
            "price": None,
            "change_pct": None,
            "market_cap": None,
            "sector": "",
        }
        for s in fallback_syms[:limit]
    ]


def get_live_market_data(ticker: str) -> dict[str, Any]:
    """
    Fetches live spot price, 1D change, 52-week range, Market Cap, Enterprise Value,
    Trailing/Forward P/E, EV/EBITDA, and Wall Street consensus target price.
    Primary: TradingView Scanner API; Fallback: Yahoo Finance v8/v10.
    Cached for 5 minutes in market_cache.
    """
    clean = ticker.upper().strip()
    cache_key = f"quote_v3:{clean}"
    cached = get_market_cache(cache_key, ttl_seconds=300)
    if isinstance(cached, dict) and cached.get("price") is not None:
        return cached

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    price: float | None = None
    prev_close: float | None = None
    change: float | None = None
    change_pct: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    volume: int | None = None
    exchange_code = ""
    tv_symbol_override = ""
    currency = "USD"
    short_name = clean
    sector = ""
    market_cap: float | None = None
    enterprise_value: float | None = None
    trailing_pe: float | None = None
    forward_pe: float | None = None
    ev_to_ebitda: float | None = None
    price_to_book: float | None = None
    dividend_yield_pct: float | None = None
    beta: float | None = None
    target_mean: float | None = None
    target_high: float | None = None
    target_low: float | None = None
    recommendation = ""
    analyst_count: int | None = None
    source_label = "TradingView Live Scanner & Multiples"

    # 1. Primary: TradingView America Scanner API (zero-key, low-latency, cloud-safe)
    tv_snap = _fetch_tradingview_equity_snapshot(clean)
    if tv_snap is not None:
        tv_symbol_override = tv_snap["tv_symbol"]
        short_name = tv_snap["short_name"]
        exchange_code = tv_snap["exchange_code"]
        sector = tv_snap.get("sector") or ""
        price = tv_snap["price"]
        prev_close = tv_snap["prev_close"]
        change = tv_snap["change"]
        change_pct = tv_snap["change_pct"]
        volume = tv_snap["volume"]
        high_52w = tv_snap["high_52w"]
        low_52w = tv_snap["low_52w"]
        market_cap = tv_snap["market_cap"]
        enterprise_value = tv_snap["enterprise_value"]
        trailing_pe = tv_snap["trailing_pe"]
        forward_pe = tv_snap["forward_pe"]
        ev_to_ebitda = tv_snap["ev_to_ebitda"]
        price_to_book = tv_snap["price_to_book"]
        dividend_yield_pct = tv_snap["dividend_yield_pct"]
        beta = tv_snap["beta"]
        target_mean = tv_snap["target_mean"]
        target_high = tv_snap["target_high"]
        target_low = tv_snap["target_low"]
        recommendation = tv_snap["recommendation"]

    # 2. Fallback: Yahoo v8 chart + v10 quoteSummary if TradingView had no match
    if price is None:
        source_label = "Yahoo Finance Live Quote & Multiples"
        try:
            r_v8 = requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{clean}",
                params={"range": "5d", "interval": "1d"},
                headers=_UA_HEADER,
                timeout=7,
            )
            if r_v8.ok:
                res_list = ((r_v8.json() or {}).get("chart") or {}).get("result") or []
                if res_list:
                    res0 = res_list[0]
                    meta = res0.get("meta") or {}
                    price = _raw_num(meta.get("regularMarketPrice"))
                    high_52w = _raw_num(meta.get("fiftyTwoWeekHigh"))
                    low_52w = _raw_num(meta.get("fiftyTwoWeekLow"))
                    vol_raw = _raw_num(meta.get("regularMarketVolume"))
                    volume = int(vol_raw) if vol_raw is not None else None
                    exchange_code = str(meta.get("exchangeName") or "")
                    currency = str(meta.get("currency") or "USD")
                    short_name = str(
                        meta.get("shortName") or meta.get("longName") or clean
                    )

                    quotes = ((res0.get("indicators") or {}).get("quote") or [{}])[0]
                    closes = [
                        float(c)
                        for c in (quotes.get("close") or [])
                        if isinstance(c, (int, float))
                    ]
                    if len(closes) >= 2:
                        prev_close = closes[-2]
                    elif meta.get("chartPreviousClose") is not None:
                        prev_close = _raw_num(meta.get("chartPreviousClose"))
        except Exception:
            pass

        for attempt in range(2):
            sess, crumb = _get_yf_session_and_crumb(force_refresh=(attempt == 1))
            if not crumb:
                break
            try:
                r_qs = sess.get(
                    f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{clean}",
                    params={
                        "modules": "price,summaryDetail,defaultKeyStatistics,financialData",
                        "crumb": crumb,
                    },
                    timeout=7,
                )
                if r_qs.status_code in (401, 403) and attempt == 0:
                    continue
                if r_qs.ok:
                    qs_list = (
                        (r_qs.json() or {}).get("quoteSummary") or {}
                    ).get("result") or []
                    if qs_list:
                        qs = qs_list[0]
                        p_mod = qs.get("price") or {}
                        sd_mod = qs.get("summaryDetail") or {}
                        ks_mod = qs.get("defaultKeyStatistics") or {}
                        fd_mod = qs.get("financialData") or {}

                        if price is None:
                            price = _raw_num(p_mod.get("regularMarketPrice"))
                        if prev_close is None:
                            prev_close = _raw_num(
                                p_mod.get("regularMarketPreviousClose")
                            )
                        if p_mod.get("shortName"):
                            short_name = str(p_mod["shortName"])
                        if p_mod.get("exchangeName") and not exchange_code:
                            exchange_code = str(p_mod["exchangeName"])

                        market_cap = _raw_num(p_mod.get("marketCap")) or _raw_num(
                            sd_mod.get("marketCap")
                        )
                        enterprise_value = _raw_num(ks_mod.get("enterpriseValue"))
                        trailing_pe = _raw_num(sd_mod.get("trailingPE"))
                        forward_pe = _raw_num(sd_mod.get("forwardPE")) or _raw_num(
                            ks_mod.get("forwardPE")
                        )
                        ev_to_ebitda = _raw_num(ks_mod.get("enterpriseToEbitda"))
                        price_to_book = _raw_num(ks_mod.get("priceToBook"))
                        dy_raw = _raw_num(sd_mod.get("dividendYield"))
                        dividend_yield_pct = (
                            dy_raw * 100.0 if dy_raw is not None else None
                        )
                        beta = _raw_num(sd_mod.get("beta")) or _raw_num(
                            ks_mod.get("beta")
                        )
                        target_mean = _raw_num(fd_mod.get("targetMeanPrice"))
                        target_high = _raw_num(fd_mod.get("targetHighPrice"))
                        target_low = _raw_num(fd_mod.get("targetLowPrice"))
                        recommendation = str(fd_mod.get("recommendationKey") or "")
                        ac = _raw_num(fd_mod.get("numberOfAnalystOpinions"))
                        analyst_count = int(ac) if ac is not None else None
                    break
            except Exception:
                break

    if (change is None or change_pct is None) and price is not None and prev_close and prev_close > 0:
        change = round(price - prev_close, 4)
        change_pct = round(((price - prev_close) / prev_close) * 100.0, 2)

    tv_symbol = tv_symbol_override or resolve_tradingview_symbol(clean, exchange_code)

    metrics: dict[str, dict[str, Any]] = {}
    if price is not None:
        metrics["SpotPrice"] = {"value": round(price, 2), "unit": currency}
    if change_pct is not None:
        metrics["DailyChangePct"] = {"value": change_pct, "unit": "%"}
    if market_cap is not None:
        metrics["MarketCap"] = {"value": round(market_cap, 2), "unit": currency}
    if enterprise_value is not None:
        metrics["EnterpriseValue"] = {
            "value": round(enterprise_value, 2),
            "unit": currency,
        }
    if trailing_pe is not None:
        metrics["TrailingPE"] = {"value": round(trailing_pe, 2), "unit": "x"}
    if forward_pe is not None:
        metrics["ForwardPE"] = {"value": round(forward_pe, 2), "unit": "x"}
    if ev_to_ebitda is not None:
        metrics["EVToEBITDA"] = {"value": round(ev_to_ebitda, 2), "unit": "x"}
    if high_52w is not None:
        metrics["FiftyTwoWeekHigh"] = {"value": round(high_52w, 2), "unit": currency}
    if low_52w is not None:
        metrics["FiftyTwoWeekLow"] = {"value": round(low_52w, 2), "unit": currency}
    if target_mean is not None:
        metrics["AnalystTargetPrice"] = {
            "value": round(target_mean, 2),
            "unit": currency,
        }

    payload: dict[str, Any] = {
        "ticker": clean,
        "company_name": short_name,
        "exchange": exchange_code,
        "sector": sector,
        "suggested_peers": _suggest_sector_peers(clean, sector),
        "tradingview_symbol": tv_symbol,
        "currency": currency,
        "as_of": now_iso,
        "price": round(price, 2) if price is not None else None,
        "previous_close": round(prev_close, 2) if prev_close is not None else None,
        "change": round(change, 2) if change is not None else None,
        "change_pct": change_pct,
        "volume": volume,
        "fifty_two_week_high": round(high_52w, 2) if high_52w is not None else None,
        "fifty_two_week_low": round(low_52w, 2) if low_52w is not None else None,
        "market_cap": market_cap,
        "enterprise_value": enterprise_value,
        "trailing_pe": round(trailing_pe, 2) if trailing_pe is not None else None,
        "forward_pe": round(forward_pe, 2) if forward_pe is not None else None,
        "ev_to_ebitda": round(ev_to_ebitda, 2) if ev_to_ebitda is not None else None,
        "price_to_book": round(price_to_book, 2) if price_to_book is not None else None,
        "dividend_yield": (
            round(dividend_yield_pct, 2) if dividend_yield_pct is not None else None
        ),
        "beta": round(beta, 2) if beta is not None else None,
        "analyst_target_mean": (
            round(target_mean, 2) if target_mean is not None else None
        ),
        "analyst_target_high": (
            round(target_high, 2) if target_high is not None else None
        ),
        "analyst_target_low": round(target_low, 2) if target_low is not None else None,
        "recommendation": recommendation,
        "analyst_count": analyst_count,
        "metrics": metrics,
        "source": source_label,
    }

    if price is not None:
        set_market_cache(cache_key, payload)
    return payload


def _parse_money_float(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    cleaned = str(val).replace("$", "").replace(",", "").strip()
    if not cleaned or cleaned.upper() == "N/A":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _fetch_nasdaq_ohlcv(clean: str, tf: str) -> list[dict[str, Any]]:
    """Fetches reliable intraday (1D) or historical OHLCV (5D/1M/6M/1Y/5Y) from Nasdaq's public API."""
    nh = {
        "User-Agent": _UA_HEADER["User-Agent"],
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.nasdaq.com",
        "Referer": "https://www.nasdaq.com/",
    }
    sym = clean.replace(".", "-")

    if tf == "1D":
        for asset_cls in ("stocks", "etf"):
            try:
                r_i = requests.get(
                    f"https://api.nasdaq.com/api/quote/{sym}/chart",
                    params={"assetclass": asset_cls},
                    headers=nh,
                    timeout=7,
                )
                if not r_i.ok:
                    continue
                pts = ((r_i.json() or {}).get("data") or {}).get("chart") or []
                if not pts:
                    continue
                buckets: dict[int, dict[str, Any]] = {}
                for pt in pts:
                    x_ms = pt.get("x")
                    y_px = _parse_money_float(pt.get("y"))
                    if not isinstance(x_ms, (int, float)) or y_px is None:
                        continue
                    slot = int((int(x_ms) // 1000 // 300) * 300)
                    if slot not in buckets:
                        buckets[slot] = {
                            "time": slot,
                            "open": round(y_px, 2),
                            "high": round(y_px, 2),
                            "low": round(y_px, 2),
                            "close": round(y_px, 2),
                            "volume": 0,
                        }
                    else:
                        b = buckets[slot]
                        b["high"] = round(max(float(b["high"]), y_px), 2)
                        b["low"] = round(min(float(b["low"]), y_px), 2)
                        b["close"] = round(y_px, 2)
                if buckets:
                    return [buckets[k] for k in sorted(buckets.keys())]
            except Exception:
                continue
        return []

    lookback_days = {
        "5D": 10,
        "1M": 35,
        "6M": 186,
        "1Y": 370,
        "5Y": 1830,
    }.get(tf, 186)
    today = datetime.datetime.now(datetime.timezone.utc).date()
    from_date = (today - datetime.timedelta(days=lookback_days)).isoformat()
    to_date = today.isoformat()

    daily_bars: list[dict[str, Any]] = []
    for asset_cls in ("stocks", "etf"):
        try:
            r_h = requests.get(
                f"https://api.nasdaq.com/api/quote/{sym}/historical",
                params={
                    "assetclass": asset_cls,
                    "fromdate": from_date,
                    "todate": to_date,
                    "limit": "1500",
                },
                headers=nh,
                timeout=8,
            )
            if not r_h.ok:
                continue
            rows = (
                (((r_h.json() or {}).get("data") or {}).get("tradesTable") or {}).get(
                    "rows"
                )
                or []
            )
            if not rows:
                continue
            for row in rows:
                raw_d = str(row.get("date") or "").strip()
                try:
                    dt_d = datetime.datetime.strptime(raw_d, "%m/%d/%Y").date()
                except ValueError:
                    continue
                o_v = _parse_money_float(row.get("open"))
                h_v = _parse_money_float(row.get("high"))
                l_v = _parse_money_float(row.get("low"))
                c_v = _parse_money_float(row.get("close"))
                vol_v = _parse_money_float(row.get("volume")) or 0.0
                if o_v is None or h_v is None or l_v is None or c_v is None:
                    continue
                daily_bars.append(
                    {
                        "time": dt_d.isoformat(),
                        "open": round(o_v, 2),
                        "high": round(h_v, 2),
                        "low": round(l_v, 2),
                        "close": round(c_v, 2),
                        "volume": int(vol_v),
                    }
                )
            if daily_bars:
                break
        except Exception:
            continue

    daily_bars.sort(key=lambda bar: str(bar["time"]))
    if tf == "5D" and len(daily_bars) > 5:
        return daily_bars[-5:]
    if tf == "5Y" and len(daily_bars) > 60:
        weekly: dict[str, dict[str, Any]] = {}
        for bar in daily_bars:
            d_obj = datetime.date.fromisoformat(str(bar["time"]))
            monday = (d_obj - datetime.timedelta(days=d_obj.weekday())).isoformat()
            if monday not in weekly:
                weekly[monday] = dict(bar, time=monday)
            else:
                wb = weekly[monday]
                wb["high"] = round(max(float(wb["high"]), float(bar["high"])), 2)
                wb["low"] = round(min(float(wb["low"]), float(bar["low"])), 2)
                wb["close"] = bar["close"]
                wb["volume"] = int(wb["volume"]) + int(bar["volume"])
        return [weekly[k] for k in sorted(weekly.keys())]
    return daily_bars


def get_ohlcv_chart_data(ticker: str, timeframe: str = "6M") -> dict[str, Any]:
    """
    Fetches OHLCV candlestick & volume series formatted for TradingView lightweight-charts,
    alongside the live quote & valuation snapshot.
    """
    clean = ticker.upper().strip()
    tf = timeframe.upper().strip()
    if tf not in _TIMEFRAME_PARAMS:
        tf = "6M"

    yf_range, yf_interval, is_intraday = _TIMEFRAME_PARAMS[tf]
    ttl = 120 if is_intraday else 600
    cache_key = f"ohlcv_v2:{clean}:{tf}"
    cached = get_market_cache(cache_key, ttl_seconds=ttl)
    if isinstance(cached, dict) and cached.get("candles"):
        cached["quote"] = get_live_market_data(clean)
        return cached

    # 1. Primary: Nasdaq public intraday/historical OHLCV API (zero-key, cloud-safe)
    candles: list[dict[str, Any]] = _fetch_nasdaq_ohlcv(clean, tf)

    # 2. Fallback: Yahoo Finance v8 chart API
    if not candles:
        try:
            r = requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{clean}",
                params={"range": yf_range, "interval": yf_interval},
                headers=_UA_HEADER,
                timeout=8,
            )
            if r.ok:
                res_list = ((r.json() or {}).get("chart") or {}).get("result") or []
                if res_list:
                    res0 = res_list[0]
                    timestamps = res0.get("timestamp") or []
                    q0 = ((res0.get("indicators") or {}).get("quote") or [{}])[0]
                    opens = q0.get("open") or []
                    highs = q0.get("high") or []
                    lows = q0.get("low") or []
                    closes = q0.get("close") or []
                    vols = q0.get("volume") or []

                    seen_times: set[int | str] = set()
                    for idx, ts in enumerate(timestamps):
                        if ts is None or idx >= len(closes):
                            continue
                        o = opens[idx] if idx < len(opens) else None
                        h = highs[idx] if idx < len(highs) else None
                        low_v = lows[idx] if idx < len(lows) else None
                        c = closes[idx] if idx < len(closes) else None
                        v = vols[idx] if idx < len(vols) else 0
                        if o is None or h is None or low_v is None or c is None:
                            continue

                        t_key: int | str
                        if is_intraday:
                            t_key = int(ts)
                        else:
                            t_key = datetime.datetime.fromtimestamp(
                                int(ts), tz=datetime.timezone.utc
                            ).strftime("%Y-%m-%d")

                        if t_key in seen_times:
                            continue
                        seen_times.add(t_key)
                        candles.append(
                            {
                                "time": t_key,
                                "open": round(float(o), 2),
                                "high": round(float(h), 2),
                                "low": round(float(low_v), 2),
                                "close": round(float(c), 2),
                                "volume": int(v or 0),
                            }
                        )
        except Exception:
            pass

    candles.sort(key=lambda bar: bar["time"])
    actual_intraday = bool(candles and isinstance(candles[0]["time"], int))
    period_change_pct: float | None = None
    if len(candles) >= 2 and candles[0]["open"] > 0:
        start_px = float(candles[0]["open"])
        end_px = float(candles[-1]["close"])
        period_change_pct = round(((end_px - start_px) / start_px) * 100.0, 2)

    quote = get_live_market_data(clean)
    out = {
        "ticker": clean,
        "timeframe": tf,
        "is_intraday": actual_intraday,
        "tradingview_symbol": quote.get(
            "tradingview_symbol", resolve_tradingview_symbol(clean)
        ),
        "period_change_pct": period_change_pct,
        "candles": candles,
        "quote": quote,
    }
    if candles:
        set_market_cache(cache_key, out)
    return out


def get_insider_and_events(ticker: str, limit: int = 8) -> list[dict[str, Any]]:
    """
    Fetches live SEC Form 4 executive/director insider stock trades and recent Form 8-K
    material corporate events directly from SEC EDGAR via edgartools.
    Returns Citation-Guard-compatible chunks with verbatim transaction & event records.
    """
    clean = ticker.upper().strip()
    cache_key = f"insider_events_v1:{clean}:{limit}"
    cached = get_market_cache(cache_key, ttl_seconds=1800)
    if isinstance(cached, list) and cached:
        return cached

    items: list[dict[str, Any]] = []
    edgar_search_url = (
        f"https://www.sec.gov/edgar/browse/?CIK={clean}"
    )

    try:
        comp = Company(clean)
        # 1. Recent SEC Form 4 Insider Transactions
        f4_filings = comp.get_filings(form="4")
        for idx in range(min(6, len(f4_filings))):
            try:
                filing = f4_filings[idx]
                f_date = str(filing.filing_date)
                f_year = int(f_date[:4]) if len(f_date) >= 4 else datetime.datetime.now().year
                acc_short = str(getattr(filing, "accession_no", idx)).replace("-", "")[-6:]
                doc_url = str(getattr(filing, "homepage_url", "") or edgar_search_url)

                f4_obj = filing.obj()
                if f4_obj is None or not hasattr(f4_obj, "get_ownership_summary"):
                    continue
                summary = f4_obj.get_ownership_summary()
                insider = str(getattr(summary, "insider_name", "Executive/Director")).strip()
                position = str(getattr(summary, "position", "Officer/Director")).strip()
                txs = getattr(summary, "transactions", None) or []
                if not txs:
                    continue

                tx_descriptions: list[str] = []
                for tx in txs[:3]:
                    code = str(getattr(tx, "code", "")).upper()
                    tx_type = str(getattr(tx, "transaction_type", "")).lower()
                    shares = getattr(tx, "shares", 0)
                    px = getattr(tx, "price_per_share", None)
                    val = getattr(tx, "value", None)
                    code_label = (
                        "Open-Market Purchase (Code P)"
                        if code == "P"
                        else "Open-Market Sale (Code S)"
                        if code == "S"
                        else f"{tx_type.title() or 'Transaction'} (Code {code or 'N/A'})"
                    )
                    px_part = f" at ${float(px):,.2f}/sh" if isinstance(px, (int, float)) and px > 0 else ""
                    val_part = f" (${float(val):,.0f} total)" if isinstance(val, (int, float)) and val > 0 else ""
                    tx_descriptions.append(
                        f"{code_label} of {int(float(shares or 0)):,} shares{px_part}{val_part}"
                    )

                rem = getattr(summary, "remaining_shares", None)
                rem_part = (
                    f" Remaining direct holdings: {int(rem):,} shares."
                    if rem is not None
                    else ""
                )
                chunk_text = (
                    f"[SEC Form 4 Insider Filing | Filed {f_date}] {insider} ({position}) "
                    f"reported: {'; '.join(tx_descriptions)}.{rem_part}"
                )
                items.append(
                    {
                        "chunk_id": f"{clean}_{f_year}_FORM4_{acc_short}_{idx}",
                        "chunk_text": chunk_text,
                        "ticker": clean,
                        "year": f_year,
                        "section": f"SEC Form 4 ({f_date})",
                        "source_type": "insider_filing",
                        "url": doc_url,
                    }
                )
            except Exception:
                continue

        # 2. Recent Form 8-K Material Event Filings
        f8_filings = comp.get_filings(form="8-K")
        for idx in range(min(4, len(f8_filings))):
            try:
                f8 = f8_filings[idx]
                f_date = str(f8.filing_date)
                f_year = int(f_date[:4]) if len(f_date) >= 4 else datetime.datetime.now().year
                acc_short = str(getattr(f8, "accession_no", idx)).replace("-", "")[-6:]
                doc_url = str(getattr(f8, "homepage_url", "") or edgar_search_url)
                raw_text = " ".join((f8.text() or "")[:1600].split())
                if not raw_text:
                    continue
                chunk_text = (
                    f"[SEC Form 8-K Material Event | Filed {f_date}] {raw_text[:650]}"
                )
                items.append(
                    {
                        "chunk_id": f"{clean}_{f_year}_8KEVENT_{acc_short}_{idx}",
                        "chunk_text": chunk_text,
                        "ticker": clean,
                        "year": f_year,
                        "section": f"SEC Form 8-K ({f_date})",
                        "source_type": "sec_8k_event",
                        "url": doc_url,
                    }
                )
                if len(items) >= limit:
                    break
            except Exception:
                continue
    except Exception:
        pass

    out = items[:limit]
    if out:
        set_market_cache(cache_key, out)
    return out


def fetch_fresh_news_and_sentiment(
    ticker: str,
    query: str | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """
    Aggregates live 24h-7d financial news (Google News RSS, Finnhub, Yahoo Finance)
    alongside fresh Reddit discussions (t=month across r/stocks, r/investing, r/wallstreetbets,
    r/SecurityAnalysis), ranked by BM25 relevance and recency.
    """
    clean = ticker.upper().strip()
    q_clean = (query or "").strip()
    cache_key = (
        f"fresh_news_v1:{clean}:"
        + hashlib.sha1(f"{q_clean}:{limit}".encode()).hexdigest()[:10]
    )
    cached = get_market_cache(cache_key, ttl_seconds=600)
    if isinstance(cached, list) and cached:
        return cached

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    current_year = now_utc.year
    candidates: list[tuple[float, dict[str, Any]]] = []
    seen_titles: set[str] = set()

    def _add_candidate(
        title: str,
        body: str,
        section: str,
        source_type: str,
        url: str,
        cid_suffix: str,
        pub_dt: datetime.datetime | None,
    ) -> None:
        norm_t = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
        if not norm_t or norm_t in seen_titles:
            return
        seen_titles.add(norm_t)
        dt = pub_dt or now_utc
        age_label = _relative_age(dt)
        recency_hours = max(1.0, (now_utc - dt).total_seconds() / 3600.0)
        recency_bonus = 1.0 / (1.0 + (recency_hours / 24.0))

        text = f"[{section} · {age_label}] {body}"
        candidates.append(
            (
                recency_bonus,
                {
                    "chunk_id": f"{clean}_{dt.year}_{cid_suffix}",
                    "chunk_text": text,
                    "ticker": clean,
                    "year": dt.year,
                    "section": section,
                    "published_at": dt.isoformat(),
                    "age": age_label,
                    "source_type": source_type,
                    "url": url,
                },
            )
        )

    # 1. Google News 7-Day RSS (Fresh multi-publisher stream)
    try:
        gn_query = (
            f"{clean} stock {q_clean} when:7d".strip()
            if q_clean
            else f"{clean} stock earnings market when:7d"
        )
        r_gn = requests.get(
            "https://news.google.com/rss/search",
            params={"q": gn_query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
            headers=_UA_HEADER,
            timeout=7,
        )
        if r_gn.ok and r_gn.text:
            root = ET.fromstring(r_gn.text)
            for idx, item_el in enumerate(root.findall(".//item")[:10]):
                raw_title = " ".join((item_el.findtext("title") or "").split())
                if not raw_title:
                    continue
                src_el = item_el.find("source")
                publisher = (
                    (src_el.text or "").strip()
                    if src_el is not None and src_el.text
                    else "Financial News"
                )
                link = (item_el.findtext("link") or "").strip()
                pub_raw = (item_el.findtext("pubDate") or "").strip()
                pub_dt: datetime.datetime | None = None
                if pub_raw:
                    try:
                        parsed_dt = email.utils.parsedate_to_datetime(pub_raw)
                        pub_dt = (
                            parsed_dt.astimezone(datetime.timezone.utc)
                            if parsed_dt.tzinfo
                            else parsed_dt.replace(tzinfo=datetime.timezone.utc)
                        )
                    except Exception:
                        pub_dt = None
                _add_candidate(
                    title=raw_title,
                    body=f"Headline: {raw_title}",
                    section=f"News ({publisher})",
                    source_type="financial_news",
                    url=link,
                    cid_suffix=f"GNEWS_{idx}",
                    pub_dt=pub_dt,
                )
    except Exception:
        pass

    # 2. Optional Finnhub Company News (last 14 days)
    if FINNHUB_API_KEY:
        try:
            date_to = now_utc.date().isoformat()
            date_from = (now_utc.date() - datetime.timedelta(days=14)).isoformat()
            r_fh = requests.get(
                "https://finnhub.io/api/v1/company-news",
                params={
                    "symbol": clean,
                    "from": date_from,
                    "to": date_to,
                    "token": FINNHUB_API_KEY,
                },
                timeout=7,
            )
            if r_fh.ok and isinstance(r_fh.json(), list):
                for idx, art in enumerate(r_fh.json()[:6]):
                    hl = " ".join(str(art.get("headline") or "").split())
                    summ = " ".join(str(art.get("summary") or "").split())[:320]
                    src = str(art.get("source") or "Finnhub")
                    url = str(art.get("url") or "")
                    dt_val = art.get("datetime")
                    p_dt = (
                        datetime.datetime.fromtimestamp(
                            float(dt_val), tz=datetime.timezone.utc
                        )
                        if dt_val
                        else None
                    )
                    body = f"Headline: {hl}. Summary: {summ}" if summ else f"Headline: {hl}"
                    _add_candidate(
                        title=hl,
                        body=body,
                        section=f"News ({src})",
                        source_type="financial_news",
                        url=url,
                        cid_suffix=f"FHNEWS_{idx}",
                        pub_dt=p_dt,
                    )
        except Exception:
            pass

    # 3. Yahoo Finance Search News
    try:
        yf_term = f"{clean} {q_clean}".strip()
        r_yf = requests.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": yf_term, "newsCount": "8", "quotesCount": "0"},
            headers=_UA_HEADER,
            timeout=7,
        )
        if r_yf.ok:
            for idx, art in enumerate((r_yf.json() or {}).get("news") or []):
                hl = " ".join(str(art.get("title") or "").split())
                pub = str(art.get("publisher") or "Yahoo Finance")
                link = str(art.get("link") or "")
                pt = art.get("providerPublishTime")
                p_dt = (
                    datetime.datetime.fromtimestamp(
                        float(pt), tz=datetime.timezone.utc
                    )
                    if pt
                    else None
                )
                uid = str(art.get("uuid") or idx)[:8]
                _add_candidate(
                    title=hl,
                    body=f"Headline: {hl}",
                    section=f"News ({pub})",
                    source_type="financial_news",
                    url=link,
                    cid_suffix=f"NEWS_{uid}",
                    pub_dt=p_dt,
                )
    except Exception:
        pass

    # 4. Fresh Reddit Retail & Institutional Investor Pulse (t=month instead of stale t=year)
    try:
        red_headers = {
            "User-Agent": "python:companyscope:v0.3.0 (by /u/companyscope_research)"
        }
        red_term = f"{clean} {q_clean}".strip()
        r_red = requests.get(
            "https://www.reddit.com/r/stocks+investing+wallstreetbets+SecurityAnalysis/search.json",
            params={
                "q": red_term,
                "restrict_sr": "on",
                "sort": "relevance",
                "t": "month",
                "limit": "6",
            },
            headers=red_headers,
            timeout=7,
        )
        if r_red.ok:
            children = ((r_red.json() or {}).get("data") or {}).get("children") or []
            for idx, child in enumerate(children):
                post = (child or {}).get("data") or {}
                title = " ".join(str(post.get("title") or "").split())
                selftext = " ".join(str(post.get("selftext") or "").split())[:420]
                if not title:
                    continue
                sub = str(post.get("subreddit_name_prefixed") or "r/stocks")
                score = int(post.get("score") or 0)
                n_com = int(post.get("num_comments") or 0)
                c_utc = post.get("created_utc")
                p_dt = (
                    datetime.datetime.fromtimestamp(
                        float(c_utc), tz=datetime.timezone.utc
                    )
                    if c_utc
                    else datetime.datetime(current_year, 1, 1, tzinfo=datetime.timezone.utc)
                )
                pid = str(post.get("id") or idx)
                permalink = str(post.get("permalink") or "")
                post_url = f"https://www.reddit.com{permalink}" if permalink else ""
                body = (
                    f"Score: {score} | Comments: {n_com} | Title: {title}. "
                    f"Excerpt: {selftext or title}"
                )
                _add_candidate(
                    title=title,
                    body=body,
                    section=f"Reddit ({sub})",
                    source_type="social_sentiment",
                    url=post_url,
                    cid_suffix=f"REDDIT_{pid}",
                    pub_dt=p_dt,
                )
    except Exception:
        pass

    if not candidates:
        return []

    if q_clean and len(candidates) > 1:
        tok_q = re.findall(r"[a-z0-9]+", q_clean.lower())
        corpus = [
            re.findall(r"[a-z0-9]+", item["chunk_text"].lower()) or ["empty"]
            for _, item in candidates
        ]
        if tok_q:
            bm25 = BM25Okapi(corpus)
            scores = bm25.get_scores(tok_q)
            ranked = sorted(
                [
                    (float(bm_s) + rec_b, item)
                    for bm_s, (rec_b, item) in zip(scores, candidates)
                ],
                key=lambda x: x[0],
                reverse=True,
            )
            out = [it for _, it in ranked[:limit]]
            set_market_cache(cache_key, out)
            return out

    candidates.sort(key=lambda x: x[0], reverse=True)
    out = [it for _, it in candidates[:limit]]
    set_market_cache(cache_key, out)
    return out


def _fetch_single_benchmark(sym: str, label: str, tv_sym: str) -> dict[str, Any]:
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
            params={"range": "5d", "interval": "1d"},
            headers=_UA_HEADER,
            timeout=6,
        )
        if r.ok:
            res_list = ((r.json() or {}).get("chart") or {}).get("result") or []
            if res_list:
                res0 = res_list[0]
                meta = res0.get("meta") or {}
                px = _raw_num(meta.get("regularMarketPrice"))
                q0 = ((res0.get("indicators") or {}).get("quote") or [{}])[0]
                closes = [
                    float(c)
                    for c in (q0.get("close") or [])
                    if isinstance(c, (int, float))
                ]
                prev = (
                    closes[-2]
                    if len(closes) >= 2
                    else _raw_num(meta.get("chartPreviousClose"))
                )
                chg_pct = (
                    round(((px - prev) / prev) * 100.0, 2)
                    if px is not None and prev and prev > 0
                    else None
                )
                return {
                    "symbol": sym,
                    "label": label,
                    "tradingview_symbol": tv_sym,
                    "price": round(px, 2) if px is not None else None,
                    "change_pct": chg_pct,
                }
    except Exception:
        pass
    return {
        "symbol": sym,
        "label": label,
        "tradingview_symbol": tv_sym,
        "price": None,
        "change_pct": None,
    }


def _fetch_macro_market_headlines(limit: int = 8) -> list[dict[str, Any]]:
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    headlines: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        r_gn = requests.get(
            "https://news.google.com/rss/search",
            params={
                "q": "(S&P 500 OR Nasdaq OR Federal Reserve OR Treasury yields OR tech earnings) when:2d",
                "hl": "en-US",
                "gl": "US",
                "ceid": "US:en",
            },
            headers=_UA_HEADER,
            timeout=7,
        )
        if r_gn.ok and r_gn.text:
            root = ET.fromstring(r_gn.text)
            for idx, item_el in enumerate(root.findall(".//item")[:12]):
                raw_title = " ".join((item_el.findtext("title") or "").split())
                norm = re.sub(r"[^a-z0-9]+", " ", raw_title.lower()).strip()
                if not raw_title or norm in seen:
                    continue
                seen.add(norm)
                src_el = item_el.find("source")
                publisher = (
                    (src_el.text or "").strip()
                    if src_el is not None and src_el.text
                    else "Market News"
                )
                link = (item_el.findtext("link") or "").strip()
                pub_raw = (item_el.findtext("pubDate") or "").strip()
                pub_dt = now_utc
                if pub_raw:
                    try:
                        p = email.utils.parsedate_to_datetime(pub_raw)
                        pub_dt = (
                            p.astimezone(datetime.timezone.utc)
                            if p.tzinfo
                            else p.replace(tzinfo=datetime.timezone.utc)
                        )
                    except Exception:
                        pub_dt = now_utc
                age = _relative_age(pub_dt)
                headlines.append(
                    {
                        "chunk_id": f"MARKET_{pub_dt.year}_HEADLINE_{idx}",
                        "title": raw_title,
                        "publisher": publisher,
                        "age": age,
                        "published_at": pub_dt.isoformat(),
                        "url": link,
                        "ticker": "MARKET",
                        "year": pub_dt.year,
                        "section": f"Market News ({publisher})",
                        "chunk_text": f"[{publisher} · {age}] Headline: {raw_title}",
                    }
                )
                if len(headlines) >= limit:
                    break
    except Exception:
        pass
    return headlines


def _fetch_all_benchmarks() -> list[dict[str, Any]]:
    """Fetches all 6 cross-asset benchmarks in one TradingView Global Scan POST, falling back to Yahoo v8."""
    tv_syms = [tv for _, _, tv in _BENCHMARK_INDICES]
    tv_map: dict[str, tuple[float | None, float | None]] = {}
    try:
        r_tv = requests.post(
            "https://scanner.tradingview.com/global/scan",
            json={
                "symbols": {"tickers": tv_syms},
                "columns": ["close", "change"],
            },
            headers=_UA_HEADER,
            timeout=6,
        )
        if r_tv.ok:
            for item in (r_tv.json() or {}).get("data") or []:
                s_key = str(item.get("s") or "")
                d_vals = item.get("d") or []
                if len(d_vals) >= 2:
                    px = _raw_num(d_vals[0])
                    chg = _raw_num(d_vals[1])
                    tv_map[s_key] = (
                        round(px, 2) if px is not None else None,
                        round(chg, 2) if chg is not None else None,
                    )
    except Exception:
        pass

    if any(px is not None for px, _ in tv_map.values()):
        out: list[dict[str, Any]] = []
        for sym, lbl, tv in _BENCHMARK_INDICES:
            px, chg = tv_map.get(tv, (None, None))
            if px is not None:
                out.append(
                    {
                        "symbol": sym,
                        "label": lbl,
                        "tradingview_symbol": tv,
                        "price": px,
                        "change_pct": chg,
                    }
                )
            else:
                out.append(_fetch_single_benchmark(sym, lbl, tv))
        return out

    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = [
            pool.submit(_fetch_single_benchmark, sym, lbl, tv)
            for sym, lbl, tv in _BENCHMARK_INDICES
        ]
        return [f.result() for f in futs]


def get_market_pulse_and_recap(force_refresh: bool = False) -> dict[str, Any]:
    """
    Returns live cross-asset benchmark quotes (S&P 500, Nasdaq 100, Dow 30, 10Y Yield, VIX, BTC)
    plus a 0-quota Citation-Guard-verified AI Market News Recap cached for 30 minutes.
    """
    recap_cache_key = "global_market_recap_v2"
    bench_cache_key = "global_benchmarks_v2"
    if not force_refresh:
        cached = get_market_cache(recap_cache_key, ttl_seconds=1800)
        if isinstance(cached, dict) and cached.get("recap_markdown"):
            idx_cached = get_market_cache(bench_cache_key, ttl_seconds=180)
            if isinstance(idx_cached, list) and any(
                b.get("price") is not None for b in idx_cached
            ):
                cached["benchmarks"] = idx_cached
            else:
                fresh_bench = _fetch_all_benchmarks()
                if any(b.get("price") is not None for b in fresh_bench):
                    set_market_cache(bench_cache_key, fresh_bench)
                    cached["benchmarks"] = fresh_bench
            return cached

    benchmarks = _fetch_all_benchmarks()
    if any(b.get("price") is not None for b in benchmarks):
        set_market_cache(bench_cache_key, benchmarks)
    headlines = _fetch_macro_market_headlines(limit=8)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Deterministic verified fallback summary
    bench_parts = [
        f"**{b['label']}** `{b['price']:,.2f}` (`{b['change_pct']:+.2f}%`)"
        for b in benchmarks
        if b.get("price") is not None and b.get("change_pct") is not None
    ]
    fallback_bullets = []
    if bench_parts:
        fallback_bullets.append(
            "- **Cross-Asset Tape:** " + " · ".join(bench_parts[:5])
        )
    for h in headlines[:3]:
        fallback_bullets.append(
            f"- **{h['publisher']} ({h['age']}):** *\"{h['title']}\"* "
        )
    fallback_md = "\n".join(fallback_bullets) or "Live market headlines are updating."
    fallback_cits = [
        {
            "type": "sentiment",
            "ticker": "MARKET",
            "year": h["year"],
            "section": h["section"],
            "chunk_id": h["chunk_id"],
            "quote": h["title"],
            "source_context": h["chunk_text"],
            "source_url": h["url"],
        }
        for h in headlines[:3]
    ]

    recap_md = fallback_md
    verified_cits: list[dict[str, Any]] = fallback_cits
    recap_model = "deterministic-feed"

    if OPENAI_KEY and headlines:
        try:
            from src.agent import _call_llm, _extract_json

            prompt_chunks = "\n".join(
                f"- chunk_id={h['chunk_id']} | section={h['section']} | chunk_text={h['chunk_text']}"
                for h in headlines[:6]
            )
            bench_text = ", ".join(
                f"{b['label']}: {b['price']} ({b['change_pct']:+.2f}%)"
                for b in benchmarks
                if b.get("price") is not None and b.get("change_pct") is not None
            )
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are the CompanyScope Morning Market Strategist. "
                        "Synthesize the live benchmark moves and top headlines into 3 concise executive Markdown bullet points. "
                        "Every cited headline quote in `citations` MUST be an exact verbatim substring from `chunk_text`. "
                        "Output ONLY valid JSON: "
                        '{"answer": "- **Macro & Indices:** ...\\n- **Key Catalyst:** ...\\n- **Sector Watch:** ...", '
                        '"citations": [{"type": "sentiment", "ticker": "MARKET", "year": 2026, "section": "...", "chunk_id": "...", "quote": "..."}], '
                        '"needs_clarification": ""}'
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Live Benchmarks: {bench_text}\n\n"
                        f"Breaking 24h-48h Headlines:\n{prompt_chunks}"
                    ),
                },
            ]
            msg, used_m = _call_llm(
                messages=messages,
                use_tools=False,
                model=TIER2_MODEL,
                obs_name="daily_market_news_recap",
            )
            parsed = _extract_json(msg.get("content") or "{}")
            checked = verify_citations(parsed, {"recap_news": headlines})
            cand_ans = str(checked.get("answer") or "").strip()
            if (
                cand_ans
                and "couldn't fully verify" not in cand_ans.lower()
                and checked.get("citations")
            ):
                recap_md = cand_ans
                verified_cits = checked["citations"]
                recap_model = used_m
        except Exception:
            pass

    payload = {
        "as_of": now_iso,
        "model": recap_model,
        "benchmarks": benchmarks,
        "recap_markdown": recap_md,
        "citations": verified_cits,
        "headlines": [
            {
                "title": h["title"],
                "publisher": h["publisher"],
                "age": h["age"],
                "url": h["url"],
            }
            for h in headlines[:6]
        ],
    }
    set_market_cache(recap_cache_key, payload)
    return payload
