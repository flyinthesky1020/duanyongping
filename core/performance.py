from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


INITIAL_CAPITAL = 10000.0


@dataclass
class TradingSignal:
    opinion_id: str
    ticker: str
    sentiment: str
    article_date: str
    trade_date: str
    trade_index: int
    summary: str
    source_file: str


def _find_next_trading_index(dates: list[str], target_date: str) -> Optional[int]:
    for idx, date_str in enumerate(dates):
        if date_str >= target_date:
            return idx
    return None


def build_trading_signals(opinions: list[dict], bars: list[dict]) -> list[TradingSignal]:
    if not opinions or not bars:
        return []
    dates = [bar["date"] for bar in bars]
    signals = []
    for op in sorted(opinions, key=lambda item: (item["date"], item.get("id", ""))):
        trade_index = _find_next_trading_index(dates, op["date"])
        if trade_index is None:
            continue
        signals.append(TradingSignal(
            opinion_id=op.get("id", ""),
            ticker=op.get("ticker", ""),
            sentiment=op.get("sentiment", ""),
            article_date=op.get("date", ""),
            trade_date=dates[trade_index],
            trade_index=trade_index,
            summary=op.get("summary", ""),
            source_file=op.get("source_file", ""),
        ))
    return signals


def evaluate_win_rate(signals: list[TradingSignal], bars: list[dict]) -> dict:
    correct = 0
    wrong = 0
    pending = 0
    evaluations = []
    for signal in signals:
        entry_idx = signal.trade_index
        exit_idx = entry_idx + 4
        if exit_idx >= len(bars):
            pending += 1
            continue
        entry_open = float(bars[entry_idx]["open"])
        exit_close = float(bars[exit_idx]["close"])
        success = (
            exit_close > entry_open if signal.sentiment == "bullish"
            else exit_close < entry_open
        )
        if success:
            correct += 1
        else:
            wrong += 1
        evaluations.append({
            "opinion_id": signal.opinion_id,
            "ticker": signal.ticker,
            "sentiment": signal.sentiment,
            "article_date": signal.article_date,
            "trade_date": signal.trade_date,
            "entry_open": entry_open,
            "exit_date": bars[exit_idx]["date"],
            "exit_close": exit_close,
            "correct": success,
            "summary": signal.summary,
            "source_file": signal.source_file,
        })
    total = correct + wrong
    return {
        "correct": correct,
        "wrong": wrong,
        "pending": pending,
        "win_rate": (correct / total) if total else None,
        "evaluations": evaluations,
    }


def evaluate_returns(signals: list[TradingSignal], bars: list[dict]) -> dict:
    if not signals or not bars:
        return {
            "initial_capital": INITIAL_CAPITAL,
            "profit_amount": 0.0,
            "return_rate": None,
            "changes": [],
            "latest_trade_date": bars[-1]["date"] if bars else "",
        }

    changes = []
    equity = INITIAL_CAPITAL
    current_state = "cash"
    current_entry_price = None

    ordered_signals = _collapse_signals_for_returns(signals)

    for signal in ordered_signals:
        if equity <= 0:
            break

        new_state = "long" if signal.sentiment == "bullish" else "short"
        price = float(bars[signal.trade_index]["close"])
        if current_state == "cash":
            current_state = new_state
            current_entry_price = price
            changes.append({
                "trade_date": signal.trade_date,
                "state": new_state,
                "price": price,
                "equity": round(equity, 4),
                "summary": signal.summary,
                "source_file": signal.source_file,
            })
            continue

        if new_state == current_state:
            continue

        segment_return = _calculate_position_return(current_state, current_entry_price, price)
        prev_equity = equity
        equity = max(0.0, equity * (1 + segment_return))
        changes.append({
            "trade_date": signal.trade_date,
            "state": f"{current_state}_to_{new_state}",
            "price": price,
            "segment_return": round(segment_return, 6),
            "segment_profit": round(equity - prev_equity, 4),
            "equity": round(equity, 4),
            "summary": signal.summary,
            "source_file": signal.source_file,
        })
        if equity <= 0:
            current_state = "cash"
            current_entry_price = None
            changes.append({
                "trade_date": signal.trade_date,
                "state": "bankrupt",
                "price": price,
                "equity": 0.0,
                "summary": "capital exhausted",
                "source_file": signal.source_file,
            })
            break
        current_state = new_state
        current_entry_price = price

    if current_state != "cash" and equity > 0:
        latest_close = float(bars[-1]["close"])
        segment_return = _calculate_position_return(current_state, current_entry_price, latest_close)
        prev_equity = equity
        equity = max(0.0, equity * (1 + segment_return))
        changes.append({
            "trade_date": bars[-1]["date"],
            "state": f"{current_state}_to_latest",
            "price": latest_close,
            "segment_return": round(segment_return, 6),
            "segment_profit": round(equity - prev_equity, 4),
            "equity": round(equity, 4),
            "summary": "latest",
            "source_file": "",
        })

    return {
        "initial_capital": INITIAL_CAPITAL,
        "profit_amount": round(equity - INITIAL_CAPITAL, 4),
        "return_rate": (equity - INITIAL_CAPITAL) / INITIAL_CAPITAL,
        "changes": changes,
        "latest_trade_date": bars[-1]["date"],
    }


def _calculate_position_return(position: str, entry_price: float, exit_price: float) -> float:
    if not entry_price:
        return 0.0
    if position == "long":
        return (exit_price - entry_price) / entry_price
    if position == "short":
        # Floor at -100% so the simulation cannot lose more than all capital.
        return max(-1.0, (entry_price - exit_price) / entry_price)
    return 0.0


def _collapse_signals_for_returns(signals: list[TradingSignal]) -> list[TradingSignal]:
    """Keep only the latest opinion per trading day for return simulation.

    This avoids arbitrary same-day flips caused by multiple opinions mapping to the
    same market session, which can otherwise leave the portfolio in the wrong state.
    """
    if not signals:
        return []

    ordered = sorted(
        signals,
        key=lambda s: (
            s.trade_index,
            s.article_date,
            s.opinion_id,
        ),
    )

    collapsed: list[TradingSignal] = []
    for signal in ordered:
        if collapsed and collapsed[-1].trade_index == signal.trade_index:
            collapsed[-1] = signal
        else:
            collapsed.append(signal)
    return collapsed


def compute_stock_statistics(ticker: str, opinions: list[dict], bars: list[dict]) -> dict:
    signals = build_trading_signals(opinions, bars)
    win_rate = evaluate_win_rate(signals, bars)
    returns = evaluate_returns(signals, bars)
    return {
        "ticker": ticker,
        "opinion_count": len(opinions),
        "signal_count": len(signals),
        "signals": [
            {
                "opinion_id": signal.opinion_id,
                "article_date": signal.article_date,
                "trade_date": signal.trade_date,
                "trade_index": signal.trade_index,
                "sentiment": signal.sentiment,
                "summary": signal.summary,
                "source_file": signal.source_file,
            }
            for signal in signals
        ],
        "win_rate": win_rate,
        "returns": returns,
    }
