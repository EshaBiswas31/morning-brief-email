"""Tests for the pure logic. Run with: pytest -q"""
from datetime import date

import numpy as np
import pandas as pd

from brief import report
from brief.deliver import build_email, split_message
from brief.indicators import analyze_stock, pct_change, rsi
from brief.news import dedupe

SIGNAL_CFG = {
    "big_move_pct": 3.0,
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    "volume_spike_x": 2.0,
    "near_52w_pct": 2.0,
}


def _frame(closes, volumes=None):
    idx = pd.bdate_range(end="2026-09-25", periods=len(closes))
    volumes = volumes if volumes is not None else [1_000_000] * len(closes)
    return pd.DataFrame({"Close": closes, "Volume": volumes}, index=idx)


def test_pct_change():
    assert pct_change(pd.Series([100.0, 110.0])) == 10.0
    assert pct_change(pd.Series([100.0])) is None


def test_rsi_extremes():
    up = pd.Series(np.arange(1, 40, dtype=float))
    down = pd.Series(np.arange(40, 1, -1, dtype=float))
    assert rsi(up).iloc[-1] == 100
    assert rsi(down).iloc[-1] < 5
    assert rsi(pd.Series([100.0] * 30)).iloc[-1] == 50  # no movement = neutral


def test_quiet_stock_has_no_signals():
    # Gentle wobble around 100 inside a 90–110 yearly range: nothing should fire
    closes = list(100 + 0.5 * np.sin(np.arange(260) * 0.7))
    closes[20], closes[21] = 90.0, 110.0
    result = analyze_stock(_frame(closes), SIGNAL_CFG)
    assert result["notable"] is False, result["signals"]


def test_big_move_and_volume_spike():
    closes = [100.0] * 259 + [106.0]
    volumes = [1_000_000] * 259 + [3_000_000]
    result = analyze_stock(_frame(closes, volumes), SIGNAL_CFG)
    joined = " ".join(result["signals"])
    assert "big move" in joined
    assert "volume 3.0x" in joined
    assert "52-week high" in joined
    assert result["notable"] is True


def test_dedupe_removes_near_duplicates():
    items = [
        {"title": "Sensex jumps 500 points as banks rally", "source": "A"},
        {"title": "Sensex jumps 500 points as banks rally!", "source": "B"},
        {"title": "RBI keeps repo rate unchanged", "source": "C"},
    ]
    assert [i["source"] for i in dedupe(items)] == ["A", "C"]


def test_split_message_respects_limit():
    text = "\n".join(f"line {i} " + "x" * 50 for i in range(200))
    chunks = split_message(text, limit=1000)
    assert all(len(c) <= 1000 for c in chunks)
    assert "".join(c.replace("\n", "") for c in chunks) == text.replace("\n", "")


def test_report_handles_missing_data():
    overview = [
        {"name": "Nifty 50", "close": 25000.5, "chg_pct": 0.42, "last_date": "2026-09-25", "stale": False},
        {"name": "Hang Seng", "error": "unavailable"},
    ]
    text = report.numbers_section(overview, [])
    assert "Nifty 50: 25,000.50 (+0.42%)" in text
    assert "Hang Seng: unavailable" in text
    full = report.assemble(date(2026, 9, 28), text, "summary", ["1 news feed(s) unavailable"])
    assert full.startswith("☀️ MORNING BRIEF · Mon 28 Sep 2026")


def test_email_has_text_and_html_versions():
    text = "☀️ MORNING BRIEF\n🟢▲ Nifty 50: 25,000.50 (+0.42%)\nTata & Sons <note>"
    msg = build_email(text, "Brief", "me@gmail.com", ["me@gmail.com", "you@x.com"])
    assert msg["To"] == "me@gmail.com, you@x.com"
    plain = msg.get_body(("plain",)).get_content()
    rich = msg.get_body(("html",)).get_content()
    assert "Nifty 50: 25,000.50" in plain
    assert "<br>" in rich and "Tata &amp; Sons &lt;note&gt;" in rich
