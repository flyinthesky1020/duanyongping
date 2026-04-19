"""Flask app for 段永平投资思想可视化平台."""
import json
from collections import defaultdict
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, render_template, request

from core.stock_data import compute_date_range, fetch_ohlc_with_meta
from core.performance import compute_stock_statistics

app = Flask(__name__)

BASE = Path(__file__).parent
INDEX_DIR = BASE / "cache" / "index"
CACHE_DIR = BASE / "cache"
SNAPSHOT_DIR = CACHE_DIR / "snapshots"
SNAPSHOT_STOCK_DETAIL_DIR = SNAPSHOT_DIR / "stock_detail"
SNAPSHOT_STOCK_OHLC_DIR = SNAPSHOT_DIR / "stock_ohlc"
TIMELINE_SNAPSHOT_PATH = INDEX_DIR / "timeline.json"
DEPLOY_SNAPSHOT_DIR = BASE / "deploy_snapshot" / "current"
DEPLOY_INDEX_DIR = DEPLOY_SNAPSHOT_DIR / "index"
DEPLOY_STOCK_DETAIL_DIR = DEPLOY_SNAPSHOT_DIR / "stock_detail"
DEPLOY_STOCK_OHLC_DIR = DEPLOY_SNAPSHOT_DIR / "stock_ohlc"
STOCK_ALIASES = {
    "9992.HK": "09992.HK",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _stocks_summary(stocks_data: dict) -> dict:
    """Return stocks index without full opinions lists (for /api/stocks)."""
    if not stocks_data:
        return {"stocks": []}
    summary_stocks = []
    for s in stocks_data.get("stocks", []):
        summary_stocks.append({
            "name": s["name"],
            "ticker": s["ticker"],
            "market": s["market"],
            "philosophies": s.get("philosophies", []),
            "opinion_count": s["opinion_count"],
            "bullish_count": s["bullish_count"],
            "bearish_count": s["bearish_count"],
            # Include first 3 opinions as preview
            "preview_opinions": s.get("opinions", [])[:3],
        })
    return {"stocks": summary_stocks}


def _canonical_ticker(ticker: str) -> str:
    return STOCK_ALIASES.get(ticker, ticker)


def _snapshot_name(ticker: str) -> str:
    return _canonical_ticker(ticker).replace("/", "_")


def _snapshot_path(snapshot_dir: Path, ticker: str) -> Path:
    return snapshot_dir / f"{_snapshot_name(ticker)}.json"


def _load_snapshot(snapshot_dir: Path, ticker: str):
    return _load_json(_snapshot_path(snapshot_dir, ticker))


def _has_deploy_snapshot() -> bool:
    return DEPLOY_SNAPSHOT_DIR.exists()


def _filter_bars_by_range(bars: list[dict], start: str = "", end: str = "") -> list[dict]:
    if not start and not end:
        return bars
    filtered = []
    for bar in bars:
        bar_date = bar.get("date", "")
        if start and bar_date < start:
            continue
        if end and bar_date > end:
            continue
        filtered.append(bar)
    return filtered


def _load_raw_stock_opinions(ticker: str) -> list[dict]:
    canonical = _canonical_ticker(ticker)
    opinions = []
    for path in sorted((CACHE_DIR / "stock_opinions").glob("*.json")):
        items = _load_json(path) or []
        for opinion in items:
            if _canonical_ticker(opinion.get("ticker", "")) == canonical:
                normalized = dict(opinion)
                normalized["ticker"] = canonical
                opinions.append(normalized)
    opinions.sort(key=lambda item: (item.get("date", ""), item.get("id", ""), item.get("url", "")))
    return opinions


def _find_stock_group(stocks_data: dict, ticker: str) -> list[dict]:
    target = _canonical_ticker(ticker)
    matched = []
    for stock in stocks_data.get("stocks", []):
        if _canonical_ticker(stock.get("ticker", "")) == target:
            matched.append(stock)
    return matched


def _merge_stock_group(stocks: list[dict], requested_ticker: str) -> Optional[dict]:
    if not stocks:
        return None

    base = max(stocks, key=lambda item: len(item.get("opinions", [])))
    seen = set()
    merged_opinions = _load_raw_stock_opinions(requested_ticker)
    if not merged_opinions:
        for stock in stocks:
            for opinion in stock.get("opinions", []):
                dedupe_key = (
                    opinion.get("id") or "",
                    opinion.get("date") or "",
                    opinion.get("url") or "",
                    opinion.get("summary") or "",
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                merged_opinions.append(opinion)

    merged_opinions.sort(key=lambda item: (item.get("date", ""), item.get("id", ""), item.get("url", "")))

    bullish_count = sum(1 for opinion in merged_opinions if opinion.get("sentiment") == "bullish")
    bearish_count = sum(1 for opinion in merged_opinions if opinion.get("sentiment") == "bearish")
    philosophies = sorted({
        phi
        for stock in stocks
        for phi in stock.get("philosophies", [])
    })

    return {
        "name": base.get("name", requested_ticker),
        "ticker": _canonical_ticker(requested_ticker),
        "market": base.get("market", ""),
        "philosophies": philosophies,
        "opinion_count": len(merged_opinions),
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "preview_opinions": merged_opinions[:3],
        "opinions": merged_opinions,
    }


def _load_yearly_timeline() -> dict:
    philosophy_index = _load_json(INDEX_DIR / "philosophies.json") or {"philosophies": []}
    stocks_index = _load_json(INDEX_DIR / "stocks.json") or {"stocks": []}

    philosophy_meta = {
        item["key"]: {
            "title": item["title"],
            "tagline": item.get("tagline", ""),
        }
        for item in philosophy_index.get("philosophies", [])
    }
    stock_meta = {
        item["ticker"]: {
            "name": item["name"],
            "market": item.get("market", ""),
        }
        for item in stocks_index.get("stocks", [])
    }
    stock_aliases = {
        "9992.HK": "09992.HK",
    }

    years: dict[str, dict] = {}

    def ensure_year(year: str) -> dict:
        if year not in years:
            years[year] = {
                "year": year,
                "post_count": 0,
                "philosophy_quote_count": 0,
                "stock_opinion_count": 0,
                "monthly_posts": defaultdict(lambda: {"count": 0, "posts": []}),
                "philosophies": defaultdict(lambda: {"count": 0, "quotes": []}),
                "stocks": defaultdict(lambda: {
                    "count": 0,
                    "bullish_count": 0,
                    "bearish_count": 0,
                    "quotes": [],
                }),
                "moments": [],
            }
        return years[year]

    for post_file in sorted((CACHE_DIR / "posts").glob("*.json")):
        posts = _load_json(post_file) or []
        year, month = post_file.stem.split("-", 1)
        year_bucket = ensure_year(year)
        year_bucket["post_count"] += len(posts)
        month_bucket = year_bucket["monthly_posts"][month]
        month_bucket["count"] += len(posts)
        for post in posts:
            if len(month_bucket["posts"]) >= 2:
                break
            month_bucket["posts"].append({
                "date": post.get("date", ""),
                "datetime": post.get("datetime", ""),
                "text": post.get("content", ""),
                "url": post.get("url", ""),
            })

    for quote_file in sorted((CACHE_DIR / "philosophy_quotes").glob("*.json")):
        quotes = _load_json(quote_file) or []
        if not quotes:
            continue
        year = quote_file.name[:4]
        year_bucket = ensure_year(year)
        year_bucket["philosophy_quote_count"] += len(quotes)
        for quote in quotes:
            key = quote.get("philosophy_key", "")
            if not key:
                continue
            item = year_bucket["philosophies"][key]
            item["count"] += 1
            if len(item["quotes"]) < 3:
                item["quotes"].append({
                    "date": quote.get("post_date", ""),
                    "text": quote.get("quote", ""),
                    "url": quote.get("post_url", ""),
                    "quality_score": quote.get("quality_score", 0),
                })

    for opinion_file in sorted((CACHE_DIR / "stock_opinions").glob("*.json")):
        opinions = _load_json(opinion_file) or []
        if not opinions:
            continue
        year = opinion_file.name[:4]
        year_bucket = ensure_year(year)
        year_bucket["stock_opinion_count"] += len(opinions)
        for op in opinions:
            raw_ticker = op.get("ticker", "")
            ticker = stock_aliases.get(raw_ticker, raw_ticker)
            if not ticker:
                continue
            meta = stock_meta.get(ticker)
            # Skip malformed or unresolved tickers like "IH" that do not map to the stock index.
            if meta is None:
                continue
            item = year_bucket["stocks"][ticker]
            item["count"] += 1
            if op.get("sentiment") == "bullish":
                item["bullish_count"] += 1
            elif op.get("sentiment") == "bearish":
                item["bearish_count"] += 1
            if len(item["quotes"]) < 3:
                item["quotes"].append({
                    "date": op.get("date", ""),
                    "summary": op.get("summary", ""),
                    "quote": op.get("quote", ""),
                    "sentiment": op.get("sentiment", ""),
                    "url": op.get("url", ""),
                })

    timeline = []
    for year in sorted(years.keys()):
        bucket = years[year]

        top_philosophies = sorted(
            bucket["philosophies"].items(),
            key=lambda item: item[1]["count"],
            reverse=True,
        )[:4]
        top_stocks = sorted(
            bucket["stocks"].items(),
            key=lambda item: item[1]["count"],
            reverse=True,
        )[:5]

        moments = []
        for key, info in top_philosophies[:2]:
            meta = philosophy_meta.get(key, {})
            quote = info["quotes"][0] if info["quotes"] else {}
            moments.append({
                "type": "philosophy",
                "title": meta.get("title", key),
                "meta": f"{info['count']}条理念语录",
                "text": quote.get("text", ""),
                "date": quote.get("date", ""),
                "url": quote.get("url", ""),
            })
        for ticker, info in top_stocks[:2]:
            meta = stock_meta.get(ticker, {})
            quote = info["quotes"][0] if info["quotes"] else {}
            moments.append({
                "type": "stock",
                "title": meta.get("name", ticker),
                "meta": f"{ticker} · {info['count']}条观点",
                "text": quote.get("quote", "") or quote.get("summary", ""),
                "date": quote.get("date", ""),
                "url": quote.get("url", ""),
                "sentiment": quote.get("sentiment", ""),
            })

        timeline.append({
            "year": year,
            "post_count": bucket["post_count"],
            "philosophy_quote_count": bucket["philosophy_quote_count"],
            "stock_opinion_count": bucket["stock_opinion_count"],
            "monthly_posts": [
                {
                    "month": month,
                    "count": info["count"],
                    "posts": info["posts"],
                }
                for month, info in sorted(bucket["monthly_posts"].items(), key=lambda item: item[0])
            ],
            "top_philosophies": [
                {
                    "key": key,
                    "title": philosophy_meta.get(key, {}).get("title", key),
                    "tagline": philosophy_meta.get(key, {}).get("tagline", ""),
                    "count": info["count"],
                    "quotes": info["quotes"],
                }
                for key, info in top_philosophies
            ],
            "top_stocks": [
                {
                    "ticker": ticker,
                    "name": stock_meta.get(ticker, {}).get("name", ticker),
                    "market": stock_meta.get(ticker, {}).get("market", ""),
                    "count": info["count"],
                    "bullish_count": info["bullish_count"],
                    "bearish_count": info["bearish_count"],
                    "quotes": info["quotes"],
                }
                for ticker, info in top_stocks
            ],
            "moments": moments,
        })

    return {"timeline": timeline}


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/philosophies")
def get_philosophies():
    data = _load_json(DEPLOY_INDEX_DIR / "philosophies.json") or _load_json(INDEX_DIR / "philosophies.json")
    if data is None:
        return jsonify({"error": "Index not built. Run pipeline/build_index.py first."}), 503
    return jsonify(data)


@app.route("/api/stocks")
def get_stocks_summary():
    data = _load_json(DEPLOY_INDEX_DIR / "stocks.json") or _load_json(INDEX_DIR / "stocks.json")
    if data is None:
        return jsonify({"error": "Index not built. Run pipeline/build_index.py first."}), 503
    return jsonify(_stocks_summary(data))


@app.route("/api/stocks/<path:ticker>")
def get_stock_detail(ticker):
    snapshot = (
        _load_snapshot(DEPLOY_STOCK_DETAIL_DIR, ticker)
        or _load_snapshot(SNAPSHOT_STOCK_DETAIL_DIR, ticker)
    )
    if snapshot is not None:
        return jsonify(snapshot)
    data = _load_json(DEPLOY_INDEX_DIR / "stocks.json") or _load_json(INDEX_DIR / "stocks.json")
    if data is None:
        return jsonify({"error": "Index not built"}), 503
    merged = _merge_stock_group(_find_stock_group(data, ticker), ticker)
    if merged is not None:
        return jsonify(merged)
    return jsonify({"error": f"Stock {ticker} not found"}), 404


@app.route("/api/wordcloud")
def get_wordcloud():
    data = _load_json(DEPLOY_INDEX_DIR / "wordcloud.json") or _load_json(INDEX_DIR / "wordcloud.json")
    if data is None:
        return jsonify({"error": "Index not built. Run pipeline/build_index.py first."}), 503
    return jsonify(data)


@app.route("/api/timeline")
def get_timeline():
    snapshot = _load_json(DEPLOY_INDEX_DIR / "timeline.json") or _load_json(TIMELINE_SNAPSHOT_PATH)
    if snapshot is not None:
        return jsonify(snapshot)
    return jsonify(_load_yearly_timeline())


# ── Stock OHLC (copied from check_finance) ────────────────────────────────────

@app.route("/api/stock/<path:ticker>")
def get_stock_ohlc(ticker):
    market = request.args.get("market", "UNKNOWN")
    start = request.args.get("start", "")
    end = request.args.get("end", "")
    force_refresh = request.args.get("force", "") in ("1", "true", "yes")
    snapshot = (
        _load_snapshot(DEPLOY_STOCK_OHLC_DIR, ticker)
        or _load_snapshot(SNAPSHOT_STOCK_OHLC_DIR, ticker)
    )
    if snapshot is not None:
        bars = _filter_bars_by_range(snapshot.get("bars", []), start, end)
        return jsonify({
            "ticker": snapshot.get("ticker", _canonical_ticker(ticker)),
            "bars": bars,
            "source": "snapshot",
            "error": snapshot.get("error", ""),
        })
    if _has_deploy_snapshot():
        return jsonify({
            "ticker": _canonical_ticker(ticker),
            "bars": [],
            "source": "snapshot",
            "error": "Snapshot missing for this stock",
        })
    if not start or not end:
        return jsonify({"error": "start and end query params required"}), 400
    payload = fetch_ohlc_with_meta(ticker, market, start, end, force_refresh=force_refresh)
    return jsonify(payload)


@app.route("/api/stats/stock/<path:ticker>", methods=["POST"])
def get_stock_stats(ticker):
    data_req = request.json or {}
    market = data_req.get("market", "UNKNOWN")
    force_refresh = bool(data_req.get("force_refresh"))
    opinions_override = data_req.get("opinions")
    start_override = data_req.get("start")
    end_override = data_req.get("end")

    stocks_data = _load_json(DEPLOY_INDEX_DIR / "stocks.json") or _load_json(INDEX_DIR / "stocks.json")
    if not stocks_data:
        return jsonify({"error": "Index not built"}), 503

    opinions = []
    if isinstance(opinions_override, list) and opinions_override:
        opinions = opinions_override
    else:
        merged_stock = _merge_stock_group(_find_stock_group(stocks_data, ticker), ticker)
        if merged_stock is not None:
            opinions = merged_stock.get("opinions", [])

    if not opinions:
        return jsonify({"error": "No opinions found for this stock"}), 404

    start, end = compute_date_range(opinions)
    if start_override:
        start = start_override
    if end_override:
        end = end_override
    snapshot = (
        _load_snapshot(DEPLOY_STOCK_OHLC_DIR, ticker)
        or _load_snapshot(SNAPSHOT_STOCK_OHLC_DIR, ticker)
    )
    if snapshot is not None:
        stock_payload = {
            "ticker": snapshot.get("ticker", _canonical_ticker(ticker)),
            "bars": _filter_bars_by_range(snapshot.get("bars", []), start, end),
            "source": "snapshot",
            "error": snapshot.get("error", ""),
        }
    elif _has_deploy_snapshot():
        stock_payload = {
            "ticker": _canonical_ticker(ticker),
            "bars": [],
            "source": "snapshot",
            "error": "Snapshot missing for this stock",
        }
    else:
        stock_payload = fetch_ohlc_with_meta(ticker, market, start, end, force_refresh=force_refresh)
    if not stock_payload["bars"]:
        return jsonify({
            "ticker": ticker,
            "market": market,
            "error": stock_payload.get("error", "No stock data"),
            "stats": None,
        })

    stats = compute_stock_statistics(ticker, opinions, stock_payload["bars"])
    return jsonify({
        "ticker": ticker,
        "market": market,
        "source": stock_payload.get("source", ""),
        "error": stock_payload.get("error", ""),
        "stats": stats,
    })


if __name__ == "__main__":
    app.run(debug=True, port=5001)
