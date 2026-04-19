"""LLM Pass 2: Extract stock opinions from all monthly post files.

Usage:
    python pipeline/extract_stock_opinions.py
"""
import hashlib
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.llm_analyzer import analyze_one_document

POSTS_DIR = Path(__file__).parent.parent / "cache" / "posts"
OUT_DIR = Path(__file__).parent.parent / "cache" / "stock_opinions"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = Path(__file__).parent.parent / "config.json"

# Each "document" for llm_analyzer is one month's posts concatenated
# (same pattern as check_finance: one doc = one file chunk)
BATCH_SIZE = 10

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"config.json not found at {CONFIG_FILE}")
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


def posts_to_doc(posts: list[dict], batch_idx: int, month: str) -> dict:
    """Convert a batch of posts into a doc dict compatible with llm_analyzer."""
    # Concatenate posts, preserving URL in content so build_index can match them
    lines = []
    for p in posts:
        lines.append(f"[{p['date']} {p['url']}]")
        lines.append(p["content"][:600])
        lines.append("")
    content = "\n".join(lines)
    return {
        "content": content,
        "date": posts[0]["date"] if posts else month + "-01",
        "file_path": f"{month}_batch{batch_idx:03d}",
        "source_type": "xueqiu",
        "chunk_index": batch_idx,
        "content_hash": hashlib.md5(content.encode()).hexdigest()[:16],
        # Store original posts for URL lookup
        "_posts": posts,
    }


def process_batch(doc: dict, config: dict, cache_key: str) -> list[dict]:
    cache_path = OUT_DIR / f"{cache_key}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    for attempt in range(3):
        try:
            records = analyze_one_document(doc, config)
            # Enrich each record with URL by matching quote text against original posts
            posts = doc.get("_posts", [])
            for record in records:
                record["url"] = _find_post_url(record.get("quote", ""), posts)
            # Remove internal field
            cache_path.write_text(
                json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logging.info("  [%s] %d opinions", cache_key, len(records))
            return records
        except Exception as exc:
            logging.error("  [%s] attempt %d failed: %s", cache_key, attempt + 1, exc)
            if attempt < 2:
                time.sleep(2 ** attempt)
    return []


def _find_post_url(quote: str, posts: list[dict]) -> str:
    """Find the Xueqiu URL of the post containing this quote (substring match)."""
    if not quote:
        return ""
    # Try progressively shorter substrings for robustness
    for length in (80, 40, 20):
        fragment = quote[:length].strip()
        if not fragment:
            continue
        for post in posts:
            if fragment in post.get("content", ""):
                return post.get("url", "")
    return ""


def process_month_file(post_file: Path, config: dict) -> list[dict]:
    month = post_file.stem
    posts = json.loads(post_file.read_text(encoding="utf-8"))
    if not posts:
        return []

    batches = [posts[i:i + BATCH_SIZE] for i in range(0, len(posts), BATCH_SIZE)]
    all_records = []
    for idx, batch in enumerate(batches):
        doc = posts_to_doc(batch, idx, month)
        cache_key = f"{month}_{idx:03d}_{doc['content_hash']}"
        records = process_batch(doc, config, cache_key)
        all_records.extend(records)

    logging.info("[%s] total %d stock opinions", month, len(all_records))
    return all_records


def main():
    config = load_config()
    post_files = sorted(POSTS_DIR.glob("*.json"))
    if not post_files:
        print("No post files found. Run pipeline/parse_xueqiu.py first.")
        sys.exit(1)

    workers = config.get("concurrent_workers", 10)
    print(f"Processing {len(post_files)} monthly files with {workers} workers...")
    all_records = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_month_file, f, config): f for f in post_files}
        for future in as_completed(futures):
            f = futures[future]
            try:
                records = future.result()
                all_records.extend(records)
            except Exception as exc:
                logging.error("Failed processing %s: %s", f.name, exc)

    print(f"\nDone. Total stock opinions extracted: {len(all_records)}")


if __name__ == "__main__":
    main()
