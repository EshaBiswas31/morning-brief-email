"""Morning Brief: collect → compute → summarize → format → deliver.

Usage:
    python main.py              # build and send (email by default, see config.yaml)
    python main.py --dry-run    # build and print only (no Telegram)
    python main.py --no-ai      # skip Claude (useful for testing data)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from brief import deliver, market, news, report, summarize

log = logging.getLogger("morning-brief")


def load_dotenv(path: str = ".env") -> None:
    """Tiny .env loader for local runs (GitHub Actions uses Secrets instead)."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and send the morning brief.")
    parser.add_argument("--dry-run", action="store_true", help="print instead of sending")
    parser.add_argument("--no-ai", action="store_true", help="skip the Claude summary")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    load_dotenv()
    cfg = yaml.safe_load(Path(args.config).read_text())
    today = datetime.now(ZoneInfo(cfg.get("timezone", "UTC"))).date()

    # 1. Collect + 2. Compute
    log.info("Fetching prices…")
    overview = market.snapshot(cfg["market_overview"], today)
    macro = market.snapshot(cfg["macro"], today)
    watch = market.watchlist(cfg.get("watchlist", []), cfg["signals"])

    log.info("Fetching news…")
    ncfg = cfg["news"]
    headlines, failed_feeds = news.fetch_headlines(
        ncfg["feeds"], ncfg["max_age_hours"], ncfg["max_headlines"]
    )

    notes: list[str] = []
    if failed_feeds:
        notes.append(f"{len(failed_feeds)} news feed(s) unavailable")
    if any(r.get("stale") for r in overview):
        notes.append("some markets were closed; stale prices show their date")

    # 3. Summarize
    narrative = None
    if not args.no_ai and not os.environ.get("ANTHROPIC_API_KEY"):
        log.info("No ANTHROPIC_API_KEY set: sending the brief without the AI summary")
    elif not args.no_ai:
        payload = {
            "date": str(today),
            "market_overview": overview,
            "macro": macro,
            "watchlist": watch,
            "headlines": [{"title": h["title"], "source": h["source"]} for h in headlines],
            "data_notes": notes,
        }
        try:
            log.info("Asking Claude for the summary…")
            narrative = summarize.write_brief(
                payload, cfg["claude"]["model"], cfg["claude"]["max_tokens"]
            )
        except Exception as exc:
            log.error("Claude summary failed: %s", exc)
            notes.append("AI summary failed today, showing raw headlines")
    if not narrative:
        narrative = report.fallback_summary(watch, headlines)

    # 4. Format
    text = report.assemble(today, report.numbers_section(overview, macro), narrative, notes)
    saved = deliver.save(text, "briefs", str(today))
    log.info("Saved %s", saved)

    # 5. Deliver
    deliver.github_summary(text)  # always visible on the GitHub Actions run page
    if args.dry_run:
        print("\n" + text)
        return 0

    method = cfg.get("delivery", {}).get("method", "email").lower()
    if method == "email":
        deliver.send_email(text, f"☀️ Morning Brief · {today.strftime('%a %d %b %Y')}")
    elif method == "telegram":
        deliver.send_telegram(text)
    elif method == "none":
        log.info("Delivery method is 'none': brief saved and shown on the run page only")
    else:
        raise SystemExit(f"Unknown delivery method in config.yaml: {method!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
