"""Parse monthly Xueqiu markdown files into structured post JSON files."""
import hashlib
import json
import re
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "@大道无形我有型"
CACHE_DIR = Path(__file__).parent.parent / "cache" / "posts"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Match post header: ## 2020-10-15 14:32 · [原文](https://xueqiu.com/...)
HEADER_RE = re.compile(
    r"^## (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}) · \[原文\]\((https://[^\)]+)\)",
    re.MULTILINE,
)
# Match engagement: 👍 N · 💬 N · 🔁 N
ENGAGE_RE = re.compile(r"👍 (\d+) · 💬 (\d+) · 🔁 (\d+)")


def parse_file(md_path: Path) -> list[dict]:
    """Parse one monthly markdown file and return list of post dicts."""
    text = md_path.read_text(encoding="utf-8")

    # Split on post headers; keep the delimiters
    parts = HEADER_RE.split(text)
    # parts layout: [pre_header, date, time, url, content, date, time, url, content, ...]
    posts = []
    i = 1  # skip pre-header content
    while i + 3 < len(parts):
        date_str = parts[i]
        time_str = parts[i + 1]
        url = parts[i + 2]
        raw_content = parts[i + 3]
        i += 4

        # Extract content before the next separator (---)
        sep_idx = raw_content.find("\n---\n")
        if sep_idx != -1:
            content = raw_content[:sep_idx].strip()
        else:
            content = raw_content.strip()

        # Extract engagement metrics
        engage_match = ENGAGE_RE.search(content)
        likes = comments = reposts = 0
        if engage_match:
            likes = int(engage_match.group(1))
            comments = int(engage_match.group(2))
            reposts = int(engage_match.group(3))
            # Remove engagement line from content
            content = content[: engage_match.start()].strip()

        if not content:
            continue

        posts.append({
            "date": date_str,
            "datetime": f"{date_str} {time_str}",
            "url": url,
            "content": content,
            "likes": likes,
            "comments": comments,
            "reposts": reposts,
            "source_file": md_path.name,
            "content_hash": hashlib.md5(content.encode("utf-8")).hexdigest()[:16],
        })

    return posts


def main():
    md_files = sorted(DATA_DIR.glob("*.md"))
    print(f"Found {len(md_files)} monthly files")
    total_posts = 0
    for md_path in md_files:
        # Extract YYYY-MM from filename
        stem = md_path.stem  # e.g. "2020-10_@大道无形我有型"
        month = stem.split("_")[0]  # "2020-10"
        out_path = CACHE_DIR / f"{month}.json"
        if out_path.exists():
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            print(f"  {month}: {len(existing)} posts (cached, skip)")
            total_posts += len(existing)
            continue
        posts = parse_file(md_path)
        out_path.write_text(json.dumps(posts, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  {month}: {len(posts)} posts")
        total_posts += len(posts)
    print(f"\nTotal: {total_posts} posts written to {CACHE_DIR}")


if __name__ == "__main__":
    main()
