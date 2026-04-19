"""Build local deploy snapshots so production serves only local JSON data.

Usage:
    python3 scripts/build_deploy_snapshot.py
    python3 scripts/build_deploy_snapshot.py --force-refresh
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import (
    INDEX_DIR,
    STOCK_ALIASES,
    DEPLOY_SNAPSHOT_DIR,
    DEPLOY_INDEX_DIR,
    DEPLOY_STOCK_DETAIL_DIR,
    DEPLOY_STOCK_OHLC_DIR,
    _canonical_ticker,
    _find_stock_group,
    _load_json,
    _load_yearly_timeline,
    _merge_stock_group,
)
from core.stock_data import compute_date_range, fetch_ohlc_with_meta


def _ensure_dirs() -> None:
    if DEPLOY_SNAPSHOT_DIR.exists():
        shutil.rmtree(DEPLOY_SNAPSHOT_DIR)
    DEPLOY_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    DEPLOY_STOCK_DETAIL_DIR.mkdir(parents=True, exist_ok=True)
    DEPLOY_STOCK_OHLC_DIR.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _detail_snapshot_path(ticker: str) -> Path:
    return DEPLOY_STOCK_DETAIL_DIR / f"{_canonical_ticker(ticker)}.json"


def _ohlc_snapshot_path(ticker: str) -> Path:
    return DEPLOY_STOCK_OHLC_DIR / f"{_canonical_ticker(ticker)}.json"


def build_snapshot(force_refresh: bool = False) -> dict:
    _ensure_dirs()
    stocks_index = _load_json(INDEX_DIR / "stocks.json") or {"stocks": []}
    philosophies_index = _load_json(INDEX_DIR / "philosophies.json") or {"philosophies": []}
    wordcloud_index = _load_json(INDEX_DIR / "wordcloud.json") or {"words": []}

    _write_json(DEPLOY_INDEX_DIR / "stocks.json", stocks_index)
    _write_json(DEPLOY_INDEX_DIR / "philosophies.json", philosophies_index)
    _write_json(DEPLOY_INDEX_DIR / "wordcloud.json", wordcloud_index)

    unique_tickers = []
    seen = set()
    for stock in stocks_index.get("stocks", []):
        ticker = _canonical_ticker(stock.get("ticker", ""))
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        unique_tickers.append(ticker)

    success = []
    failed = []

    for idx, ticker in enumerate(unique_tickers, start=1):
        groups = _find_stock_group(stocks_index, ticker)
        merged = _merge_stock_group(groups, ticker)
        if merged is None:
            failed.append({"ticker": ticker, "error": "stock not found in index"})
            continue

        _write_json(_detail_snapshot_path(ticker), merged)

        opinions = merged.get("opinions", [])
        market = merged.get("market", "")
        start, end = compute_date_range(opinions)
        payload = fetch_ohlc_with_meta(
            ticker,
            market,
            start,
            end,
            force_refresh=force_refresh,
        )
        if payload.get("bars"):
            snapshot_payload = {
                "ticker": payload.get("ticker", ticker),
                "market": market,
                "start": start,
                "end": end,
                "bars": payload.get("bars", []),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            _write_json(_ohlc_snapshot_path(ticker), snapshot_payload)
            success.append({
                "ticker": ticker,
                "market": market,
                "bar_count": len(snapshot_payload["bars"]),
                "progress": f"{idx}/{len(unique_tickers)}",
            })
            print(f"[{idx}/{len(unique_tickers)}] OK   {ticker} {market} {len(snapshot_payload['bars'])} bars")
        else:
            error = payload.get("error", "unknown error")
            _write_json(_ohlc_snapshot_path(ticker), {
                "ticker": ticker,
                "market": market,
                "start": start,
                "end": end,
                "bars": [],
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "error": error,
            })
            failed.append({"ticker": ticker, "market": market, "error": error})
            print(f"[{idx}/{len(unique_tickers)}] FAIL {ticker} {market} {error}")

    _write_json(DEPLOY_INDEX_DIR / "timeline.json", _load_yearly_timeline())

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stock_count": len(unique_tickers),
        "success_count": len(success),
        "failure_count": len(failed),
        "success": success,
        "failed": failed,
        "aliases": STOCK_ALIASES,
    }
    _write_json(DEPLOY_SNAPSHOT_DIR / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Refresh OHLC from providers instead of reusing existing range cache.",
    )
    args = parser.parse_args()

    manifest = build_snapshot(force_refresh=args.force_refresh)
    print(
        f"Done. Success: {manifest['success_count']}, "
        f"Failed: {manifest['failure_count']}, "
        f"Manifest: {DEPLOY_SNAPSHOT_DIR / 'manifest.json'}"
    )


if __name__ == "__main__":
    main()
