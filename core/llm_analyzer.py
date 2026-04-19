"""Extract stock opinions from parsed documents using a configurable LLM provider."""
import json
import logging
import re
import uuid
from typing import Generator

SYSTEM_PROMPT = """You are an information extraction system. Extract explicit current stock stance statements from the provided document.

Rules:
1. Perform neutral extraction only. Do not provide financial advice, recommendations, predictions, or analysis beyond what is explicitly stated in the source text.
2. Only extract statements where the source text clearly expresses a positive/bullish stance (看多/利好/买入/做多/上涨) or a negative/bearish stance (看空/利空/卖出/做空/下跌).
3. Do NOT extract historical-only commentary. If the text is only describing the author's past view, past trade, past judgment, or historical attribution about a company, and does not clearly express the author's current stance in the document date context, return nothing for that company.
4. If the same document on the same date contains conflicting statements about the same company, compare them and output only ONE final stance for that company. Choose the more confident/current/final stance, and do not output both bullish and bearish records for the same stock from the same document date.
5. Return a JSON array. If no such statements are found, return [].
6. Each output item must represent the author's actionable or current stance as of the document date, not a recap of an old viewpoint unless the text explicitly reaffirms that viewpoint in the present.
7. Normalize tickers:
   - China A-shares: "600519.SH" (Shanghai 6xxxxx→.SH) or "000001.SZ" (Shenzhen 0/3xxxxx→.SZ)
   - HK stocks: "0700.HK" (4-digit zero-padded + .HK)
   - US stocks: "AAPL", "TSLA" (standard uppercase ticker)
   - Uncertain: set market to "UNKNOWN", ticker to best guess
8. "summary" ≤20 chars (Chinese or English) — a short neutral label for the extracted statement.
9. "quote" ≤200 chars verbatim excerpt from text supporting this extracted statement.
10. "date" is the document date provided in the user message.
11. Historical trades or closed positions must not by themselves produce a stance. Examples that should usually be ignored unless the text explicitly states a current present-tense stance: "曾买入", "之前买过", "过去看好", "历史上看空", "69买入，104已卖出", "当时看多", "之前判断", "此前观点".
12. If the text says a stock was bought in the past and later sold, that historical path should NOT be converted into a current bullish signal. Only extract a current bearish signal if the text explicitly expresses a present negative stance now, such as "现在不看好", "我不愿意买单", "继续看空", "目前卖出/回避", "现在认为高估".

Return ONLY valid JSON array, no markdown fences, no explanations.

Schema:
{"stock":"<name>","ticker":"<ticker>","market":"CN_A|HK|US|UNKNOWN","date":"YYYY-MM-DD","sentiment":"bullish|bearish","summary":"≤20chars","quote":"≤200chars"}"""


def _normalize_ticker_value(value: str) -> str:
    return str(value or "").strip().upper()


def _is_historical_only(opinion: dict) -> bool:
    text = " ".join([
        str(opinion.get("summary", "") or ""),
        str(opinion.get("quote", "") or ""),
    ]).lower()
    historical_markers = [
        "曾经", "之前", "过去", "当时", "那时", "历史上", "以前", "old view",
        "previously", "historical", "in the past", "过去买入", "此前买入", "曾买入",
        "已卖出", "卖出后", "当年", "曾看好", "曾看空", "买入后卖出", "此前观点",
        "之前判断", "过去判断", "曾经判断", "当时判断", "之前买过", "过去买过",
    ]
    current_markers = [
        "现在", "目前", "依然", "继续", "仍然", "长期看好", "长期看空",
        "继续看好", "继续看空", "维持看好", "维持看空", "依旧看好", "依旧看空",
        "依然看好", "依然看空", "现价买入", "当前买入", "继续买入", "继续卖出",
        "继续加仓", "继续减仓", "继续持有", "维持持有", "不看好", "不愿意买单",
        "回避", "高估", "低估", "买单", "看错", "静待花开",
    ]
    has_historical = any(marker in text for marker in historical_markers)
    has_current = any(marker in text for marker in current_markers)
    return has_historical and not has_current


def _is_closed_trade_without_current_stance(opinion: dict) -> bool:
    text = " ".join([
        str(opinion.get("summary", "") or ""),
        str(opinion.get("quote", "") or ""),
    ])
    has_buy = any(marker in text for marker in ["买入", "买过", "建仓", "加仓"])
    has_sell = any(marker in text for marker in ["卖出", "清仓", "止盈", "减仓"])
    current_negative_markers = [
        "现在不看好", "目前不看好", "继续看空", "依然看空", "不愿意买单",
        "不愿意", "不买单", "回避", "高估", "不值得", "不买", "看空",
    ]
    current_positive_markers = [
        "现在看好", "目前看好", "继续看好", "依然看好", "长期看好",
        "继续买入", "继续持有", "低估", "静待花开",
    ]
    has_current_negative = any(marker in text for marker in current_negative_markers)
    has_current_positive = any(marker in text for marker in current_positive_markers)
    return has_buy and has_sell and not has_current_negative and not has_current_positive


def _dedupe_conflicting_opinions(records: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for record in records:
        key = (
            record.get("source_file", ""),
            record.get("date", ""),
            _normalize_ticker_value(record.get("ticker", "")) or record.get("stock", ""),
        )
        grouped.setdefault(key, []).append(record)

    deduped = []
    confidence_markers = ["现在", "目前", "依然", "继续", "维持", "明确", "长期", "就是", "坚定"]
    for _, items in grouped.items():
        if len(items) == 1:
            deduped.extend(items)
            continue

        def score(item: dict) -> tuple[int, int, int]:
            text = f"{item.get('summary', '')} {item.get('quote', '')}"
            confidence_score = sum(1 for marker in confidence_markers if marker in text)
            quote_len = len(item.get("quote", "") or "")
            summary_len = len(item.get("summary", "") or "")
            return (confidence_score, quote_len, summary_len)

        best = max(items, key=score)
        deduped.append(best)

    return deduped


def _strip_code_fences(text: str) -> str:
    text = re.sub(r'^\s*```json?\s*\n?', '', text.strip())
    text = re.sub(r'\n?\s*```\s*$', '', text)
    return text.strip()


def _extract_json_payload(text: str) -> str:
    cleaned = _strip_code_fences(text)
    if not cleaned:
        raise ValueError("LLM returned empty content; no JSON to parse.")
    if cleaned[0] in "[{":
        return cleaned

    for opener, closer in (("[", "]"), ("{", "}")):
        start = cleaned.find(opener)
        end = cleaned.rfind(closer)
        if start != -1 and end != -1 and end > start:
            return cleaned[start:end + 1]
    return cleaned


def _call_llm(content: str, date: str, config: dict) -> list:
    """Call the configured LLM and return a list of raw opinion dicts. Raises on error."""
    api_key = config.get("api_key", "")
    model = config.get("model", "")
    base_url = (config.get("base_url") or "").strip()
    if not api_key:
        raise ValueError("API key is not configured. Please set it in Settings.")
    if not model:
        raise ValueError("Model is not configured. Please set it in Settings.")

    provider = config.get("provider", "anthropic")
    user_msg = f"Document date: {date}\n\n---\n{content}\n---\n\nExtract all stock opinions as JSON array."
    raw = ""
    if provider == "anthropic":
        import anthropic
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = anthropic.Anthropic(**client_kwargs)
        msg = client.messages.create(
            model=model,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}]
        )
        raw = msg.content[0].text
    elif provider in ("openai", "openai_compatible"):
        import openai
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = openai.OpenAI(**client_kwargs)
        request_kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
        }
        try:
            resp = client.chat.completions.create(
                **request_kwargs
            )
        except Exception as exc:
            message = str(exc)
            lowered = message.lower()
            if "content_filter" in lowered or "high risk" in lowered:
                raise ValueError(
                    "当前模型供应商拦截了这次请求，判定为高风险金融内容。"
                    "请尝试更换模型、切换供应商，或缩小单次分析内容。"
                ) from exc
            raise
        message = resp.choices[0].message
        raw = message.content or ""
        if not raw:
            reasoning = getattr(message, "reasoning_content", "") or ""
            finish_reason = resp.choices[0].finish_reason
            if reasoning and finish_reason == "length":
                raise ValueError(
                    "LLM exhausted the provider's output budget in reasoning before producing final content. "
                    "Please retry later or switch to a model/provider with a larger effective output budget."
                )
    else:
        raise ValueError(
            f"Unknown API type: {provider!r}. Use 'anthropic', 'openai', or 'openai_compatible'."
        )

    cleaned = _extract_json_payload(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        snippet = cleaned[:240].replace("\n", " ")
        raise ValueError(f"LLM returned non-JSON content: {snippet}") from exc
    if isinstance(parsed, dict):
        parsed = [parsed]
    return parsed if isinstance(parsed, list) else []


def analyze_one_document(doc: dict, config: dict) -> list[dict]:
    """Analyze one parsed document and return normalized opinion records."""
    raw_opinions = _call_llm(doc["content"], doc["date"], config)
    records = []
    for op in raw_opinions:
        sentiment = op.get("sentiment", "")
        if sentiment not in ("bullish", "bearish"):
            logging.warning("Skipping opinion with invalid sentiment %r: %s", sentiment, op)
            continue
        record = {
            "id": str(uuid.uuid4()),
            "stock": op.get("stock", ""),
            "ticker": op.get("ticker", "UNKNOWN"),
            "market": op.get("market", "UNKNOWN"),
            "date": op.get("date", doc["date"]),
            "sentiment": sentiment,
            "summary": op.get("summary", "")[:20],
            "quote": op.get("quote", "")[:200],
            "source_file": doc["file_path"],
            "source_type": doc["source_type"],
            "chunk_index": doc.get("chunk_index", 0),
        }
        if _is_historical_only(record):
            logging.info("Skipping historical-only opinion: %s", record)
            continue
        if _is_closed_trade_without_current_stance(record):
            logging.info("Skipping closed-trade historical opinion: %s", record)
            continue
        records.append(record)
    return _dedupe_conflicting_opinions(records)


def analyze_documents(docs: list, config: dict) -> Generator:
    """
    Yields SSE-ready dicts:
      {"type": "progress", "done": int, "total": int, "current_file": str}
      {"type": "opinion", "record": OpinionRecord}
      {"type": "done", "total_opinions": int}
      {"type": "error", "message": str}
    """
    total = len(docs)
    total_opinions = 0
    for i, doc in enumerate(docs):
        yield {"type": "progress", "done": i, "total": total,
               "current_file": doc["file_path"]}
        try:
            records = analyze_one_document(doc, config)
        except Exception as e:
            logging.error("LLM call failed for %s: %s", doc["file_path"], e)
            yield {"type": "error", "message": str(e)}
            records = []

        for record in records:
            total_opinions += 1
            yield {"type": "opinion", "record": record}

    yield {"type": "done", "total_opinions": total_opinions}
