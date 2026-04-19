"""Build the three master index files from cached extraction results.

Usage:
    python pipeline/build_index.py

Outputs:
    cache/index/philosophies.json
    cache/index/stocks.json
    cache/index/wordcloud.json
"""
import json
import sys
import uuid
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.philosophy_extractor import PHILOSOPHIES

BASE = Path(__file__).parent.parent
PHIL_QUOTES_DIR = BASE / "cache" / "philosophy_quotes"
STOCK_OPINIONS_DIR = BASE / "cache" / "stock_opinions"
INDEX_DIR = BASE / "cache" / "index"
INDEX_DIR.mkdir(parents=True, exist_ok=True)


# ── Philosophy descriptions ───────────────────────────────────────────────────

PHILOSOPHY_DESCRIPTIONS = {
    "stop_doing": (
        "段永平认为，成功的关键不仅是做正确的事，更重要的是停止做错误的事。"
        "他将Stop Doing List视为比To Do List更重要的清单。"
        "一旦认识到某件事是错的，就应该立刻停止，无论已付出多少沉没成本。"
    ),
    "integrity": (
        "本分是段永平商业哲学的核心——做正确的事，对所有利益相关者诚实守信。"
        "短期利益永远不值得以牺牲长期声誉为代价。好的企业文化建立在本分之上。"
    ),
    "business_model": (
        "好的商业模式具备定价权、护城河和持续的高ROE。"
        "段永平寻找那些客户愿意为之溢价买单、竞争对手难以复制的生意。"
        "差异化是商业模式的核心，同质化竞争终将走向价格战。"
    ),
    "corporate_culture": (
        "企业文化是公司最持久的竞争优势。段永平特别重视管理层的价值观——"
        "不说谎、不欺骗、以客户为中心。文化腐化的公司，再好的产品也只是暂时的。"
    ),
    "long_termism": (
        "段永平持股的时间框架是十年以上。短期价格波动在长期看来几乎没有意义。"
        "他认为，如果找到了真正好的公司，最大的错误是卖得太早。"
        "\"不要试图预测市场，要预测公司的长期价值。\""
    ),
    "circle_of_competence": (
        "只投资自己真正理解的生意。段永平反复强调，看不懂的公司无论多诱人都不碰。"
        "理解意味着能够预测这门生意十年后还会存在，并且大概率会更好。"
    ),
    "patience": (
        "等待是投资者最重要的美德之一。段永平相信，好价格总会出现，"
        "问题是你是否有足够的耐心等待，以及是否有足够的胆量在恐慌时买入。"
        "什么都不做，也是一种正确的选择。"
    ),
    "cash_flow": (
        "公司的内在价值是其未来自由现金流的折现总和。"
        "段永平特别警惕账面利润高但现金流差的公司——那往往意味着利润质量存疑。"
        "真正的好生意，现金流应该持续且可预测。"
    ),
}


def load_all_philosophy_quotes() -> list[dict]:
    records = []
    for f in PHIL_QUOTES_DIR.glob("*.json"):
        try:
            items = json.loads(f.read_text(encoding="utf-8"))
            records.extend(items)
        except Exception as exc:
            print(f"  Warning: failed to read {f.name}: {exc}")
    return records


def load_all_stock_opinions() -> list[dict]:
    records = []
    for f in STOCK_OPINIONS_DIR.glob("*.json"):
        try:
            items = json.loads(f.read_text(encoding="utf-8"))
            records.extend(items)
        except Exception as exc:
            print(f"  Warning: failed to read {f.name}: {exc}")
    # Ensure each has an id and url field
    for r in records:
        if not r.get("id"):
            r["id"] = str(uuid.uuid4())
        r.setdefault("url", "")
    return records


def build_philosophies_index(quotes: list[dict], stock_opinions: list[dict]) -> dict:
    # Group quotes by philosophy key
    by_key = defaultdict(list)
    for q in quotes:
        by_key[q["philosophy_key"]].append(q)

    # Build stock→philosophy mapping from quotes' mentioned_stocks
    stock_to_philosophies = defaultdict(set)
    for q in quotes:
        for stock_name in q.get("mentioned_stocks", []):
            # Try to find ticker from stock opinions
            ticker = _name_to_ticker(stock_name, stock_opinions)
            if ticker:
                stock_to_philosophies[ticker].add(q["philosophy_key"])

    philosophies = []
    for p in PHILOSOPHIES:
        key = p["key"]
        raw_quotes = by_key.get(key, [])
        # Sort by quality_score desc, then date desc
        raw_quotes.sort(key=lambda x: (-x.get("quality_score", 0), x.get("post_date", "")))
        # Deduplicate by quote text similarity (first 50 chars)
        seen_prefixes = set()
        deduped = []
        for q in raw_quotes:
            prefix = q["quote"][:50]
            if prefix not in seen_prefixes:
                seen_prefixes.add(prefix)
                deduped.append(q)

        top_quotes = deduped[:8]

        # Stocks mentioned in this philosophy's quotes
        phi_stocks = set()
        for q in raw_quotes:
            for stock_name in q.get("mentioned_stocks", []):
                ticker = _name_to_ticker(stock_name, stock_opinions)
                if ticker and ticker != "UNKNOWN":
                    phi_stocks.add(ticker)

        philosophies.append({
            "key": key,
            "title": p["title"],
            "tagline": p["tagline"],
            "description": PHILOSOPHY_DESCRIPTIONS.get(key, ""),
            "quote_count": len(raw_quotes),
            "top_quotes": [
                {
                    "text": q["quote"],
                    "date": q.get("post_date", ""),
                    "url": q.get("post_url", ""),
                    "quality_score": q.get("quality_score", 3),
                }
                for q in top_quotes
            ],
            "stocks": sorted(phi_stocks),
        })

    return {"philosophies": philosophies}


def _name_to_ticker(name: str, opinions: list[dict]) -> str:
    """Look up ticker by stock name from opinions list."""
    name_lower = name.lower().strip()
    for op in opinions:
        stock = (op.get("stock") or "").lower()
        ticker = op.get("ticker", "")
        if not ticker or ticker == "UNKNOWN":
            continue
        # Match by name containment
        if name_lower in stock or stock in name_lower:
            return ticker
        # Common aliases
        aliases = {
            "苹果": "AAPL", "apple": "AAPL",
            "茅台": "600519.SH", "贵州茅台": "600519.SH",
            "腾讯": "0700.HK", "tencent": "0700.HK",
            "谷歌": "GOOG", "google": "GOOG", "alphabet": "GOOG",
            "亚马逊": "AMZN", "amazon": "AMZN",
            "微软": "MSFT", "microsoft": "MSFT",
            "伯克希尔": "BRK-B", "berkshire": "BRK-B",
            "网易": "NTES", "格力": "000651.SZ",
            "平安": "601318.SH", "中国平安": "601318.SH",
        }
        if name_lower in aliases:
            return aliases[name_lower]
    return ""


def build_stocks_index(opinions: list[dict], phil_index: dict) -> dict:
    # Build philosophy mapping: ticker → set of philosophy keys
    ticker_to_philosophies = defaultdict(set)
    for phi in phil_index["philosophies"]:
        for ticker in phi["stocks"]:
            ticker_to_philosophies[ticker].add(phi["key"])

    # Group opinions by ticker
    by_ticker = defaultdict(list)
    for op in opinions:
        ticker = op.get("ticker", "UNKNOWN")
        if not ticker or ticker == "UNKNOWN":
            continue
        by_ticker[ticker].append(op)

    stocks = []
    for ticker, ops in by_ticker.items():
        # Get stock name from first opinion
        name = ops[0].get("stock", ticker)
        market = ops[0].get("market", "UNKNOWN")
        # Sort opinions by date
        ops.sort(key=lambda x: x.get("date", ""))
        bullish = sum(1 for o in ops if o.get("sentiment") == "bullish")
        bearish = sum(1 for o in ops if o.get("sentiment") == "bearish")

        opinion_records = []
        for op in ops:
            opinion_records.append({
                "id": op.get("id", str(uuid.uuid4())),
                "date": op.get("date", ""),
                "sentiment": op.get("sentiment", ""),
                "summary": op.get("summary", ""),
                "quote": op.get("quote", ""),
                "url": op.get("url", ""),
            })

        stocks.append({
            "name": name,
            "ticker": ticker,
            "market": market,
            "philosophies": sorted(ticker_to_philosophies.get(ticker, set())),
            "opinions": opinion_records,
            "opinion_count": len(ops),
            "bullish_count": bullish,
            "bearish_count": bearish,
        })

    # Sort by opinion_count descending
    stocks.sort(key=lambda x: -x["opinion_count"])
    return {"stocks": stocks}


def build_wordcloud_index(phil_index: dict, stocks_index: dict) -> dict:
    words = []

    # Philosophy concept words
    philosophy_weights = {
        "long_termism": 95,
        "business_model": 90,
        "stop_doing": 88,
        "integrity": 85,
        "corporate_culture": 82,
        "cash_flow": 80,
        "circle_of_competence": 78,
        "patience": 75,
    }
    for phi in phil_index["philosophies"]:
        key = phi["key"]
        words.append({
            "text": phi["title"],
            "weight": philosophy_weights.get(key, 70) + phi["quote_count"] // 5,
            "type": "concept",
            "target": f"philosophy:{key}",
        })

    # Stock words — weight by opinion count (max 85)
    max_count = max((s["opinion_count"] for s in stocks_index["stocks"]), default=1)
    for stock in stocks_index["stocks"][:60]:  # Top 60 stocks
        count = stock["opinion_count"]
        weight = max(20, min(85, int(20 + 65 * count / max_count)))
        words.append({
            "text": stock["name"],
            "weight": weight,
            "type": "stock",
            "target": f"stock:{stock['ticker']}",
        })

    # Additional concept words
    extra_concepts = [
        ("本分", 88, "concept", "philosophy:integrity"),
        ("护城河", 75, "concept", "philosophy:business_model"),
        ("定价权", 72, "concept", "philosophy:business_model"),
        ("现金流", 78, "concept", "philosophy:cash_flow"),
        ("能力圈", 73, "concept", "philosophy:circle_of_competence"),
        ("安全边际", 70, "concept", "philosophy:patience"),
        ("ROE", 68, "concept", "philosophy:business_model"),
        ("市场先生", 65, "concept", "philosophy:patience"),
        ("巴菲特", 72, "concept", "philosophy:long_termism"),
        ("DCF", 62, "concept", "philosophy:cash_flow"),
        ("永续经营", 65, "concept", "philosophy:long_termism"),
        ("逆向投资", 60, "concept", "philosophy:patience"),
        ("商业模式", 75, "concept", "philosophy:business_model"),
        ("企业文化", 72, "concept", "philosophy:corporate_culture"),
    ]
    for text, weight, wtype, target in extra_concepts:
        words.append({"text": text, "weight": weight, "type": wtype, "target": target})

    return {"words": words}


def main():
    print("Loading philosophy quotes...")
    quotes = load_all_philosophy_quotes()
    print(f"  {len(quotes)} quotes loaded")

    print("Loading stock opinions...")
    opinions = load_all_stock_opinions()
    print(f"  {len(opinions)} opinions loaded")

    print("Building philosophies index...")
    phil_index = build_philosophies_index(quotes, opinions)
    out = INDEX_DIR / "philosophies.json"
    out.write_text(json.dumps(phil_index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Saved {out} ({len(phil_index['philosophies'])} philosophies)")

    print("Building stocks index...")
    stocks_index = build_stocks_index(opinions, phil_index)
    out = INDEX_DIR / "stocks.json"
    out.write_text(json.dumps(stocks_index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Saved {out} ({len(stocks_index['stocks'])} stocks)")

    print("Building wordcloud index...")
    wc_index = build_wordcloud_index(phil_index, stocks_index)
    out = INDEX_DIR / "wordcloud.json"
    out.write_text(json.dumps(wc_index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Saved {out} ({len(wc_index['words'])} words)")

    print("\nAll indices built successfully.")


if __name__ == "__main__":
    main()
