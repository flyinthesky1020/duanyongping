"""Extract philosophy quotes from Xueqiu posts using LLM."""
import json
import logging
import re

PHILOSOPHIES = [
    {"key": "stop_doing", "title": "停止做错误的事", "tagline": "比知道该做什么更重要的，是知道不该做什么"},
    {"key": "integrity", "title": "本分", "tagline": "做正确的事，长期声誉远比短期利益重要"},
    {"key": "business_model", "title": "好的商业模式", "tagline": "有定价权、有护城河、ROE持续高的生意"},
    {"key": "corporate_culture", "title": "企业文化", "tagline": "管理层的价值观决定公司的长期命运"},
    {"key": "long_termism", "title": "长期主义", "tagline": "持股如持业，以十年为单位思考"},
    {"key": "circle_of_competence", "title": "不懂不投", "tagline": "只在自己真正理解的领域内做决策"},
    {"key": "patience", "title": "等待与耐心", "tagline": "等待好价格出现，什么都不做也是一种选择"},
    {"key": "cash_flow", "title": "现金流思维", "tagline": "公司价值是未来现金流的折现，而非账面利润"},
]

PHILOSOPHY_KEYS = [p["key"] for p in PHILOSOPHIES]

SYSTEM_PROMPT = """你是分析段永平（大道无形我有型）投资理念的专家。
从以下雪球帖子中，提取能体现以下8种投资理念的代表性语录。

理念分类（使用这些精确的key）：
- "stop_doing": 停止做错误的事 / 不做错误的事 / Stop Doing List（关于什么事不应该做）
- "integrity": 本分（做正确的事，声誉、诚信、长期大于短期）
- "business_model": 好的商业模式（定价权、护城河、ROE、差异化、生意壁垒）
- "corporate_culture": 企业文化（管理层价值观、公司文化、人的因素）
- "long_termism": 长期主义（长期持有、以十年为单位、忽略短期波动）
- "circle_of_competence": 不懂不投（能力圈、只投理解的生意）
- "patience": 等待与耐心（等待好价格、不作为也是选择、市场先生）
- "cash_flow": 现金流思维（现金流折现、自由现金流、净现金流 vs 净利润）

规则：
1. 只提取段永平本人的观点，不要提取他引用他人的话
2. 每条语录必须是对该理念的清晰表达，而非模糊提及
3. quality_score: 1-5，5分表示对该理念最具代表性的精彩论述
4. quote: 原文摘录，≤300字，尽量完整保留原意
5. mentioned_stocks: 语录中明确提到的公司名称（如提到的话），否则为空数组
6. 如无相关语录，返回空数组 []

返回格式：仅返回JSON数组，不含代码框或解释。

Schema:
{"philosophy_key":"<key>","quote":"<原文≤300字>","post_url":"<url>","post_date":"<YYYY-MM-DD>","mentioned_stocks":["<公司名>"],"quality_score":<1-5>}"""


def _strip_code_fences(text: str) -> str:
    text = re.sub(r'^\s*```json?\s*\n?', '', text.strip())
    text = re.sub(r'\n?\s*```\s*$', '', text)
    return text.strip()


def _extract_json_payload(text: str) -> str:
    cleaned = _strip_code_fences(text)
    if not cleaned:
        raise ValueError("LLM returned empty content")
    if cleaned[0] in "[{":
        return cleaned
    for opener, closer in (("[", "]"), ("{", "}")):
        start = cleaned.find(opener)
        end = cleaned.rfind(closer)
        if start != -1 and end != -1 and end > start:
            return cleaned[start:end + 1]
    return cleaned


def _call_llm(batch_text: str, config: dict) -> list:
    api_key = config.get("api_key", "")
    model = config.get("model", "")
    base_url = (config.get("base_url") or "").strip()
    if not api_key:
        raise ValueError("API key is not configured")
    if not model:
        raise ValueError("Model is not configured")

    provider = config.get("provider", "anthropic")
    raw = ""
    if provider == "anthropic":
        import anthropic
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = anthropic.Anthropic(**client_kwargs)
        msg = client.messages.create(
            model=model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": batch_text}],
        )
        raw = msg.content[0].text
    elif provider in ("openai", "openai_compatible"):
        import openai
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = openai.OpenAI(**client_kwargs)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": batch_text},
            ],
        )
        raw = resp.choices[0].message.content or ""
    else:
        raise ValueError(f"Unknown provider: {provider!r}")

    cleaned = _extract_json_payload(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        snippet = cleaned[:240].replace("\n", " ")
        raise ValueError(f"LLM returned non-JSON: {snippet}") from exc
    if isinstance(parsed, dict):
        parsed = [parsed]
    return parsed if isinstance(parsed, list) else []


def extract_philosophy_quotes(posts: list[dict], config: dict) -> list[dict]:
    """Given a batch of post dicts, return philosophy quote records."""
    # Format posts for LLM
    lines = []
    for p in posts:
        lines.append(f"[{p['date']} | {p['url']}]")
        lines.append(p["content"][:800])
        lines.append("")
    batch_text = "\n".join(lines)

    raw_items = _call_llm(batch_text, config)
    records = []
    for item in raw_items:
        key = item.get("philosophy_key", "")
        if key not in PHILOSOPHY_KEYS:
            logging.warning("Unknown philosophy key %r, skipping", key)
            continue
        quote = (item.get("quote") or "")[:300]
        if not quote:
            continue
        score = item.get("quality_score", 3)
        try:
            score = max(1, min(5, int(score)))
        except (TypeError, ValueError):
            score = 3
        records.append({
            "philosophy_key": key,
            "quote": quote,
            "post_url": item.get("post_url", ""),
            "post_date": item.get("post_date", ""),
            "mentioned_stocks": [s for s in (item.get("mentioned_stocks") or []) if s],
            "quality_score": score,
        })
    return records
