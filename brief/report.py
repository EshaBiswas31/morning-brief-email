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


BIAS_ICON = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪️"}


def outlook_section(outlooks: list[dict], track: dict | None) -> str:
    """The forward-looking part: bias, probability, why, and what would prove it wrong."""
    lines = ["📈 OUTLOOK (historical odds, not certainties)"]

    # Overnight US cue always gets its own line: it's the freshest information of the morning
    for o in [o for o in outlooks if o.get("kind") == "global_cue"]:
        lines.append("")
        lines.append(
            f"🌙 {o['name']} today: {BIAS_ICON[o['bias']]} {o['bias'].upper()}"
            + (f" bias, {o['p_up']:.0%} chance up (normal {o['base_p_up']:.0%}) · {o['confidence']} confidence"
               if o["bias"] != "neutral" else f", no clear edge ({o['p_up']:.0%} up vs normal {o['base_p_up']:.0%})")
        )
        lines.append("   Why: " + " · ".join(o["reasons"]))
        lines.append("   History: " + o["evidence"])

    setups = [o for o in outlooks if o.get("kind") != "global_cue"]
    calls = [o for o in setups if "error" not in o and o["bias"] != "neutral"]
    neutral = [o for o in setups if "error" not in o and o["bias"] == "neutral"]
    missing = [o for o in outlooks if "error" in o]

    for o in calls:
        lines.append("")
        lines.append(
            f"{BIAS_ICON[o['bias']]} {o['name']} · {o['horizon_label']}: {o['bias'].upper()} bias, "
            f"{o['p_up']:.0%} chance up (normal {o['base_p_up']:.0%}) · {o['confidence']} confidence"
        )
        lines.append("   Why: " + " · ".join(o["reasons"]))
        lines.append("   History: " + o["evidence"])
        if o.get("wrong_if"):
            lines.append("   Wrong if: " + o["wrong_if"])

    if not calls:
        lines += ["", "No chart setup has a meaningful historical edge this week."]
    if neutral:
        lines += ["", f"⚪️ No clear edge ({neutral[0]['horizon_label']}): "
                  + ", ".join(f"{o['name']} ({o['p_up']:.0%} up)" for o in neutral)]
    if missing:
        lines.append("▫️ Not enough data: " + ", ".join(o["name"] for o in missing))

    if track is not None:
        lines.append("")
        if track.get("graded"):
            lines.append(
                f"🎯 Track record (last {track['window_days']} days): {track['hits']}/{track['graded']} "
                f"calls correct ({track['hit_rate']:.0%}). {track['open']} still open."
            )
        else:
            lines.append(f"🎯 Track record starts once the first calls mature ({track['open']} open).")
    return "\n".join(lines)


def assemble(today: date, numbers: str, narrative: str, notes: list[str], outlook: str = "") -> str:
    header = f"☀️ MORNING BRIEF · {today.strftime('%a %d %b %Y')}"
    parts = [header, "", numbers]
    if outlook:
        parts += ["", outlook]
    parts += ["", narrative]
    if notes:
        parts += ["", "ℹ️ " + " | ".join(notes)]
    parts += ["", "Not investment advice. Data: Yahoo Finance, public RSS feeds."]
    return "\n".join(parts)
