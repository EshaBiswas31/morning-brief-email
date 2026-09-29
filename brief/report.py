"""Build the final message text. Numbers come from code, never from the LLM."""
from __future__ import annotations

from datetime import date


def _fmt_number(x: float) -> str:
    return f"{x:,.2f}"


def _line(row: dict) -> str:
    if "error" in row or row.get("chg_pct") is None:
        return f"▫️ {row['name']}: unavailable"
    chg = row["chg_pct"]
    arrow = "🟢▲" if chg > 0 else "🔴▼" if chg < 0 else "⚪️•"
    stale = f"  (as of {row['last_date']})" if row.get("stale") else ""
    return f"{arrow} {row['name']}: {_fmt_number(row['close'])} ({chg:+.2f}%){stale}"


def numbers_section(overview: list[dict], macro: list[dict]) -> str:
    lines = ["📊 MARKETS (last close, 1-day change)"]
    lines += [_line(r) for r in overview]
    lines += ["", "🌐 MACRO"]
    lines += [_line(r) for r in macro]
    return "\n".join(lines)


def fallback_summary(watch: list[dict], headlines: list[dict]) -> str:
    """Used when Claude is unavailable, so the brief still goes out."""
    lines = ["📰 LATEST HEADLINES"]
    lines += [f"• {h['title']} ({h['source']})" for h in headlines[:7]]
    notable = [w for w in watch if w.get("notable")]
    lines += ["", "⭐ WATCHLIST"]
    if notable:
        lines += [f"• {w['ticker']}: {'; '.join(w['signals'])}" for w in notable]
    else:
        lines.append("All quiet on your watchlist.")
    return "\n".join(lines)


def assemble(today: date, numbers: str, narrative: str, notes: list[str]) -> str:
    header = f"☀️ MORNING BRIEF · {today.strftime('%a %d %b %Y')}"
    parts = [header, "", numbers, "", narrative]
    if notes:
        parts += ["", "ℹ️ " + " | ".join(notes)]
    parts += ["", "Not investment advice. Data: Yahoo Finance, public RSS feeds."]
    return "\n".join(parts)
