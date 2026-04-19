"""Fetch OHLC candlestick data for global stocks via yfinance (US/HK) and AKShare (China A-shares)."""
import json
import hashlib
import logging
import time
from datetime import date, timedelta
from pathlib import Path
import pandas as pd

CACHE_DIR = Path(__file__).parent.parent / "cache" / "ohlc"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_VERSION = "v3-adjusted-us-qfq"


def _cache_path(ticker: str, start: str, end: str) -> Path:
    key = hashlib.md5(f"{CACHE_VERSION}:{ticker}:{start}:{end}".encode()).hexdigest()[:12]
    return CACHE_DIR / f"{key}.json"


def _load_cache(ticker: str, start: str, end: str):
    p = _cache_path(ticker, start, end)
    if p.exists():
        return json.loads(p.read_text())
    return None


def _save_cache(ticker: str, start: str, end: str, bars: list):
    _cache_path(ticker, start, end).write_text(json.dumps(bars))


def _fetch_yfinance(ticker: str, start: str, end: str) -> list:
    import yfinance as yf
    last_exc = None
    df = pd.DataFrame()
    for attempt in range(2):
        try:
            t = yf.Ticker(ticker)
            # Use adjusted OHLC so US split events do not render as fake price crashes.
            df = t.history(start=start, end=end, auto_adjust=True)
            if not df.empty:
                break
        except Exception as exc:
            last_exc = exc
            message = str(exc)
            if "Too Many Requests" not in message and "Rate limited" not in message:
                raise
            time.sleep(1.5 * (attempt + 1))

    if df.empty:
        try:
            # download() is often more stable than Ticker.history() under light throttling.
            df = yf.download(
                ticker,
                start=start,
                end=end,
                auto_adjust=True,
                progress=False,
                threads=False,
            )
        except Exception as exc:
            last_exc = exc

    if df is None or df.empty:
        if last_exc is not None:
            raise last_exc
        return []

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    bars = []
    for idx, row in df.iterrows():
        bars.append({
            "date": str(idx.date()),
            "open": round(float(row.Open), 4),
            "high": round(float(row.High), 4),
            "low": round(float(row.Low), 4),
            "close": round(float(row.Close), 4),
            "volume": int(row.Volume)
        })
    return bars


def _filter_df_by_date(df, start: str, end: str):
    if df is None or getattr(df, "empty", True):
        return df
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    if "date" in df.columns:
        series = pd.to_datetime(df["date"])
        return df[(series >= start_ts) & (series <= end_ts)]
    if "日期" in df.columns:
        series = pd.to_datetime(df["日期"])
        return df[(series >= start_ts) & (series <= end_ts)]
    if getattr(df.index, "dtype", None) is not None:
        idx = pd.to_datetime(df.index)
        return df[(idx >= start_ts) & (idx <= end_ts)]
    return df


def _fetch_us_akshare(ticker: str, start: str, end: str) -> list:
    import akshare as ak
    last_exc = None
    df = pd.DataFrame()
    for attempt in range(3):
        try:
            # Use forward-adjusted prices so splits do not appear as fake crashes.
            df = ak.stock_us_daily(symbol=ticker, adjust="qfq")
            if df is not None and not df.empty:
                break
        except Exception as exc:
            last_exc = exc
            if "unexpected EOF while parsing" not in str(exc):
                raise
            time.sleep(0.8 * (attempt + 1))

    if df is None or df.empty:
        if last_exc is not None:
            raise last_exc
        return []

    df = _filter_df_by_date(df, start, end)
    bars = []
    for _, row in df.iterrows():
        bars.append({
            "date": str(pd.to_datetime(row["date"]).date()),
            "open": round(float(row["open"]), 4),
            "high": round(float(row["high"]), 4),
            "low": round(float(row["low"]), 4),
            "close": round(float(row["close"]), 4),
            "volume": int(float(row["volume"])),
        })
    return bars


def _fetch_hk_akshare(ticker: str, start: str, end: str) -> list:
    import akshare as ak
    code = ticker.split(".")[0].zfill(5)
    df = ak.stock_hk_daily(symbol=code, adjust="")
    df = _filter_df_by_date(df, start, end)
    bars = []
    for _, row in df.iterrows():
        bars.append({
            "date": str(pd.to_datetime(row["date"]).date()),
            "open": round(float(row["open"]), 4),
            "high": round(float(row["high"]), 4),
            "low": round(float(row["low"]), 4),
            "close": round(float(row["close"]), 4),
            "volume": int(float(row["volume"])),
        })
    return bars


def _fetch_akshare(ticker: str, start: str, end: str) -> list:
    import akshare as ak
    code = ticker.split(".")[0]
    df = ak.stock_zh_a_hist(
        symbol=code,
        period="daily",
        start_date=start.replace("-", ""),
        end_date=end.replace("-", ""),
        adjust=""
    )
    bars = []
    for _, row in df.iterrows():
        bars.append({
            "date": str(row["日期"])[:10],
            "open": round(float(row["开盘"]), 4),
            "high": round(float(row["最高"]), 4),
            "low": round(float(row["最低"]), 4),
            "close": round(float(row["收盘"]), 4),
            "volume": int(row["成交量"])
        })
    return bars


def _normalize_cn_symbol(ticker: str) -> str:
    code, suffix = ticker.split(".", 1)
    market = suffix.upper()
    prefix = "sh" if market == "SH" else "sz"
    return prefix + code


def _fetch_cn_akshare_daily(ticker: str, start: str, end: str) -> list:
    import akshare as ak
    symbol = _normalize_cn_symbol(ticker)
    df = ak.stock_zh_a_daily(symbol=symbol, start_date=start.replace("-", ""), end_date=end.replace("-", ""), adjust="")
    bars = []
    for _, row in df.iterrows():
        bars.append({
            "date": str(pd.to_datetime(row["date"]).date()),
            "open": round(float(row["open"]), 4),
            "high": round(float(row["high"]), 4),
            "low": round(float(row["low"]), 4),
            "close": round(float(row["close"]), 4),
            "volume": int(float(row["volume"])),
        })
    return bars


def _fetch_cn_akshare_tx(ticker: str, start: str, end: str) -> list:
    import akshare as ak
    symbol = _normalize_cn_symbol(ticker)
    df = ak.stock_zh_a_hist_tx(symbol=symbol, start_date=start.replace("-", ""), end_date=end.replace("-", ""), adjust="")
    bars = []
    for _, row in df.iterrows():
        bars.append({
            "date": str(pd.to_datetime(row["date"]).date()),
            "open": round(float(row["open"]), 4),
            "high": round(float(row["high"]), 4),
            "low": round(float(row["low"]), 4),
            "close": round(float(row["close"]), 4),
            "volume": int(float(row.get("amount", 0))),
        })
    return bars


def _normalize_ticker(ticker: str, market: str) -> str:
    """Ensure HK tickers are normalized for downstream providers."""
    if market == "HK" and "." in ticker:
        code, suffix = ticker.split(".", 1)
        return code.zfill(4) + "." + suffix
    return ticker


def fetch_ohlc_with_meta(
    ticker: str,
    market: str,
    start: str,
    end: str,
    force_refresh: bool = False,
) -> dict:
    ticker = _normalize_ticker(ticker, market)
    cached = None if force_refresh else _load_cache(ticker, start, end)
    if cached is not None:
        return {"ticker": ticker, "bars": cached, "source": "cache", "error": ""}

    bars = []
    errors = []
    source = ""
    fetchers = []
    if market == "CN_A":
        fetchers = [
            ("akshare_cn_daily", _fetch_cn_akshare_daily),
            ("akshare_cn_tx", _fetch_cn_akshare_tx),
            ("akshare_cn_hist", _fetch_akshare),
        ]
    elif market == "HK":
        fetchers = [
            ("akshare_hk_daily", _fetch_hk_akshare),
            ("yfinance", _fetch_yfinance),
        ]
    elif market == "US":
        fetchers = [
            ("yfinance", _fetch_yfinance),
            ("akshare_us_daily", _fetch_us_akshare),
        ]
    else:
        fetchers = [
            ("yfinance", _fetch_yfinance),
            ("akshare_us_daily", _fetch_us_akshare),
        ]

    for source_name, fetcher in fetchers:
        try:
            bars = fetcher(ticker, start, end)
            if bars:
                source = source_name
                break
            errors.append(f"{source_name}: empty result")
        except Exception as exc:
            logging.warning("Stock fetch via %s failed for %s: %s", source_name, ticker, exc)
            errors.append(f"{source_name}: {exc}")

    if bars:  # Only cache non-empty results
        _save_cache(ticker, start, end, bars)
        return {"ticker": ticker, "bars": bars, "source": source, "error": ""}
    error_message = "; ".join(errors[:3]) or "No data returned from providers"
    logging.error("Stock fetch error for %s: %s", ticker, error_message)
    return {"ticker": ticker, "bars": [], "source": "", "error": error_message}


def fetch_ohlc(ticker: str, market: str, start: str, end: str) -> list:
    return fetch_ohlc_with_meta(ticker, market, start, end)["bars"]


def compute_date_range(opinions: list) -> tuple[str, str]:
    """Return (start, end) covering 10 days before earliest opinion to today."""
    if not opinions:
        return (str(date.today()), str(date.today()))
    earliest = min(op["date"] for op in opinions)
    start = (date.fromisoformat(earliest) - timedelta(days=10)).isoformat()
    end = date.today().isoformat()
    return start, end
