"""LLM Pass 1: Extract philosophy quotes from all monthly post files.

Usage:
    python pipeline/extract_philosophies.py
"""
import hashlib
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.philosophy_extractor import extract_philosophy_quotes

POSTS_DIR = Path(__file__).parent.parent / "cache" / "posts"
OUT_DIR = Path(__file__).parent.parent / "cache" / "philosophy_quotes"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = Path(__file__).parent.parent / "config.json"

BATCH_SIZE = 8

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"config.json not found at {CONFIG_FILE}. Create it first.")
    cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    return cfg


def batch_hash(posts: list[dict]) -> str:
    combined = "|".join(p.get("content_hash", p["content"][:32]) for p in posts)
    return hashlib.md5(combined.encode()).hexdigest()[:16]


def process_batch(posts: list[dict], config: dict, month: str, batch_idx: int) -> list[dict]:
    key = batch_hash(posts)
    cache_path = OUT_DIR / f"{month}_{batch_idx:03d}_{key}.json"
    if cache_path.exists():
        logging.info("  [%s batch %d] cache hit", month, batch_idx)
        return json.loads(cache_path.read_text(encoding="utf-8"))

    for attempt in range(3):
        try:
            records = extract_philosophy_quotes(posts, config)
            cache_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
            logging.info("  [%s batch %d] extracted %d records", month, batch_idx, len(records))
            return records
        except Exception as exc:
            logging.error("  [%s batch %d] attempt %d failed: %s", month, batch_idx, attempt + 1, exc)
            if attempt < 2:
                time.sleep(2 ** attempt)
    return []


def process_month_file(post_file: Path, config: dict) -> list[dict]:
    month = post_file.stem  # "2020-10"
    posts = json.loads(post_file.read_text(encoding="utf-8"))
    if not posts:
        return []

    # Split into batches
    batches = [posts[i:i + BATCH_SIZE] for i in range(0, len(posts), BATCH_SIZE)]
    all_records = []
    for idx, batch in enumerate(batches):
        records = process_batch(batch, config, month, idx)
        all_records.extend(records)
    logging.info("[%s] total %d philosophy quotes", month, len(all_records))
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

    print(f"\nDone. Total philosophy quotes extracted: {len(all_records)}")
    print(f"Output files in: {OUT_DIR}")


if __name__ == "__main__":
    main()
