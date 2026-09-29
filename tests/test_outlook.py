"""Tests for the outlook engine and scorecard, using synthetic prices with known answers."""
from datetime import date

import numpy as np
import pandas as pd

from brief import outlook, report, scorecard


def _frame(closes, end="2026-09-28"):
    idx = pd.bdate_range(end=end, periods=len(closes))
    return pd.DataFrame({"Close": np.asarray(closes, dtype=float), "Volume": 1_000_000}, index=idx)


def _random_walk(n=1300, seed=0, drift=0.0003):
    rng = np.random.default_rng(seed)
    return 1000 * np.exp((rng.normal(drift, 0.012, n)).cumsum())


def test_setup_outlook_structure_and_base_rate():
    o = outlook.setup_outlook(_frame(_random_walk()), "Test", horizon=5, min_samples=30)
    assert "error" not in o
    assert o["bias"] in {"bullish", "bearish", "neutral"}
    assert 0 <= o["p_up"] <= 1 and 0 <= o["base_p_up"] <= 1
    assert o["n_similar"] >= 30
    assert len(o["reasons"]) == 3 and "RSI" in o["reasons"][1]
    assert o["confidence"] in {"low", "moderate", "none"}


def test_base_rate_matches_manual_count():
    closes = _random_walk(seed=3)
    f = outlook.features(pd.Series(closes, index=pd.bdate_range(end="2026-09-28", periods=len(closes))), 5)
    o = outlook.setup_outlook(_frame(closes), "Test", horizon=5, min_samples=30)
    hist = f.dropna(subset=["fwd", "trend", "rsi_zone", "move"])
    today = f.iloc[-1]
    mask = np.ones(len(hist), dtype=bool)
    for col in o["setup_used"]:
        mask &= (hist[col] == today[col]).to_numpy()
    assert mask.sum() == o["n_similar"]
    assert round(float((hist[mask]["fwd"] > 0).mean()), 3) == o["p_up"]
    # the forward return of today is unknown and must never be used
    assert pd.isna(f["fwd"].iloc[-1])


def test_short_history_is_reported_not_crashed():
    o = outlook.setup_outlook(_frame(_random_walk(n=150)), "Short")
    assert o.get("error") == "not enough history"


def test_global_cue_alignment():
    # Build a world where Nifty always follows the previous US session's direction.
    rng = np.random.default_rng(1)
    days = pd.bdate_range(end="2026-09-28", periods=800)
    us_ret = rng.normal(0, 0.01, len(days))
    spx = 4000 * np.exp(np.cumsum(us_ret))
    nifty_ret = np.r_[0, np.sign(us_ret[:-1]) * 0.005]      # Nifty day t follows US day t-1
    nifty = 20000 * np.exp(np.cumsum(nifty_ret))
    nifty_df = pd.DataFrame({"Close": nifty[:-1]}, index=days[:-1])   # US has one newer session
    spx_df = pd.DataFrame({"Close": spx}, index=days)
    cue = outlook.global_cue(nifty_df, spx_df, min_samples=30)
    assert "error" not in cue
    expected_up = us_ret[-1] > 0
    assert cue["p_up"] == (1.0 if expected_up else 0.0)
    assert cue["bias"] == ("bullish" if expected_up else "bearish")


def test_global_cue_needs_fresh_us_session():
    # Same calendar date is fine (US closes after India), but an older US date is stale,
    # e.g. a US holiday: there is no new overnight information.
    days = pd.bdate_range(end="2026-09-28", periods=300)
    nifty = pd.DataFrame({"Close": np.linspace(100, 120, 300)}, index=days)
    us_stale = nifty.iloc[:-1]
    assert "error" in outlook.global_cue(nifty, us_stale)


def test_scorecard_grades_hits_and_misses():
    book = scorecard.load("does/not/exist.csv")
    calls = [
        {"ticker": "A", "name": "A", "kind": "setup", "horizon": 2, "bias": "bullish", "confidence": "low",
         "p_up": 0.6, "as_of": "2026-09-21", "entry_close": 100.0},
        {"ticker": "B", "name": "B", "kind": "setup", "horizon": 2, "bias": "bearish", "confidence": "low",
         "p_up": 0.4, "as_of": "2026-09-21", "entry_close": 100.0},
        {"ticker": "C", "name": "C", "kind": "setup", "horizon": 2, "bias": "neutral", "confidence": "none",
         "p_up": 0.5, "as_of": "2026-09-21", "entry_close": 100.0},
        {"ticker": "D", "name": "D", "kind": "setup", "horizon": 10, "bias": "bullish", "confidence": "low",
         "p_up": 0.6, "as_of": "2026-09-21", "entry_close": 100.0},
    ]
    book = scorecard.add(book, calls, date(2026, 9, 22))
    book = scorecard.add(book, calls, date(2026, 9, 22))  # same-day re-run: no duplicates
    assert len(book) == 4

    idx = pd.bdate_range("2026-09-21", periods=6)
    closes = {
        "A": pd.Series([100, 101, 103, 104, 104, 105], index=idx),  # bullish, went up -> hit
        "B": pd.Series([100, 101, 102, 104, 104, 105], index=idx),  # bearish, went up -> miss
        "D": pd.Series([100, 101, 102, 104, 104, 105], index=idx),  # horizon not reached -> open
    }
    book = scorecard.grade(book, closes)
    status = dict(zip(book["ticker"], book["status"]))
    assert status == {"A": "hit", "B": "miss", "C": "unscored", "D": "open"}
    a = book[book["ticker"] == "A"].iloc[0]
    assert a["exit_date"] == "2026-09-23" and a["return_pct"] == 3.0

    s = scorecard.summary(book, date(2026, 9, 28))
    assert s["graded"] == 2 and s["hits"] == 1 and s["open"] == 1


def test_scorecard_round_trip(tmp_path):
    book = scorecard.add(scorecard.load(tmp_path / "p.csv"), [
        {"ticker": "A", "name": "A", "kind": "setup", "horizon": 5, "bias": "bullish", "confidence": "low",
         "p_up": 0.6, "as_of": "2026-09-25", "entry_close": 100.0}], date(2026, 9, 28))
    scorecard.save(book, tmp_path / "p.csv")
    again = scorecard.load(tmp_path / "p.csv")
    assert again.iloc[0]["made_on"] == "2026-09-28" and again.iloc[0]["status"] == "open"


def test_outlook_section_renders():
    o = outlook.setup_outlook(_frame(_random_walk(seed=5)), "Test")
    text = report.outlook_section([o, {"name": "X", "error": "no data"}], {"graded": 0, "open": 3})
    assert text.startswith("📈 OUTLOOK")
    assert "Not enough data: X" in text
    assert "Track record starts" in text
