"""Forward-looking outlook built on historical base rates.

The question this module answers, for each stock or index:
    "The last time the chart looked like it does today, what happened next?"

Method (deliberately simple and explainable):
1. Describe today's setup with three labels: trend, RSI zone, and yesterday's move.
2. Find every past day (about 5 years) with the same setup.
3. Measure how often price was higher N sessions later, and by how much.
4. Compare with the "normal" rate on any day. The difference is the edge.
If too few past matches exist, fall back to a simpler setup (fewer labels).

Nothing here is a certainty. Outputs are probabilities with the evidence attached,
plus a price level that would invalidate the view.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import rsi

RSI_BINS = [-np.inf, 30, 45, 55, 70, np.inf]
RSI_LABELS = ["oversold", "weak", "neutral", "strong", "overbought"]
MOVE_BINS = [-np.inf, -1.5, -0.5, 0.5, 1.5, np.inf]
MOVE_LABELS = ["sharp drop", "down", "flat", "up", "sharp rise"]

# Most specific first. We use the first one with enough historical matches.
SETUP_LEVELS = [("trend", "rsi_zone", "move"), ("trend", "rsi_zone"), ("trend", "move"), ("trend",)]


def _clean(close: pd.Series) -> pd.Series:
    close = close.dropna().astype(float)
    if getattr(close.index, "tz", None) is not None:
        close.index = close.index.tz_localize(None)
    return close


def features(close: pd.Series, horizon: int) -> pd.DataFrame:
    """One row per day: setup labels plus the forward return we want to predict."""
    close = _clean(close)
    ret1 = close.pct_change()
    vol60 = ret1.rolling(60).std()
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    r = rsi(close)

    trend = pd.Series(
        np.select(
            [(close > sma50) & (sma50 > sma200), (close < sma50) & (sma50 < sma200)],
            ["uptrend", "downtrend"],
            "mixed",
        ),
        index=close.index,
    ).where(sma200.notna())

    f = pd.DataFrame(index=close.index)
    f["close"] = close
    f["ret1"] = ret1
    f["z"] = ret1 / vol60
    f["sma50"] = sma50
    f["sma200"] = sma200
    f["rsi"] = r
    f["trend"] = trend
    f["rsi_zone"] = pd.cut(r, RSI_BINS, labels=RSI_LABELS).astype(object)
    f["move"] = pd.cut(f["z"], MOVE_BINS, labels=MOVE_LABELS).astype(object)
    f["fwd"] = close.shift(-horizon) / close - 1
    return f


def _bias(p_up: float, base: float, n: int) -> tuple[str, str]:
    """Turn a probability into a bias label and an honest confidence level."""
    edge = p_up - base
    if p_up >= 0.55 and edge >= 0.05:
        bias = "bullish"
    elif p_up <= 0.45 and edge <= -0.05:
        bias = "bearish"
    else:
        return "neutral", "none"
    # Never "high": market base rates are noisy and overlapping windows inflate n.
    confidence = "moderate" if (n >= 60 and abs(edge) >= 0.08) else "low"
    return bias, confidence


def _fmt(x: float) -> str:
    return f"{x:,.2f}"


def setup_outlook(df: pd.DataFrame, name: str, horizon: int = 5, min_samples: int = 30) -> dict:
    """Outlook for one instrument over the next `horizon` sessions."""
    f = features(df["Close"], horizon)
    today = f.iloc[-1]
    if pd.isna(today["trend"]) or pd.isna(today["rsi_zone"]) or pd.isna(today["move"]):
        return {"name": name, "error": "not enough history"}

    hist = f.dropna(subset=["fwd", "trend", "rsi_zone", "move"])
    if len(hist) < min_samples:
        return {"name": name, "error": "not enough history"}
    base_p_up = float((hist["fwd"] > 0).mean())

    match, used = None, None
    for level in SETUP_LEVELS:
        mask = np.ones(len(hist), dtype=bool)
        for col in level:
            mask &= (hist[col] == today[col]).to_numpy()
        if mask.sum() >= min_samples:
            match, used = hist[mask], level
            break
    if match is None:  # even "trend" alone is too rare
        match, used = hist, ()

    n = len(match)
    p_up = float((match["fwd"] > 0).mean())
    avg = float(match["fwd"].mean() * 100)
    bias, confidence = _bias(p_up, base_p_up, n)

    # Evidence, in plain words
    close, s50, s200 = today["close"], today["sma50"], today["sma200"]
    trend_txt = {
        "uptrend": f"Uptrend: above 50-DMA ({_fmt(s50)}), and 50-DMA above 200-DMA ({_fmt(s200)})",
        "downtrend": f"Downtrend: below 50-DMA ({_fmt(s50)}), and 50-DMA below 200-DMA ({_fmt(s200)})",
        "mixed": f"Mixed trend: 50-DMA {_fmt(s50)}, 200-DMA {_fmt(s200)}",
    }[today["trend"]]
    reasons = [
        trend_txt,
        f"RSI {today['rsi']:.0f} ({today['rsi_zone']})",
        f"Last session {today['ret1'] * 100:+.2f}% ({abs(today['z']):.1f}x a normal day's move, {today['move']})",
    ]
    setup_desc = " + ".join(str(today[c]) for c in used) if used else "any day"
    evidence = (
        f"{n} past sessions with the same setup ({setup_desc}): higher {horizon} sessions later "
        f"{p_up:.0%} of the time, avg {avg:+.2f}% (normal: {base_p_up:.0%})"
    )

    last10 = f["close"].tail(10)
    if bias == "bullish":
        wrong_if = f"closes below {_fmt(last10.min())} (10-day low)"
    elif bias == "bearish":
        wrong_if = f"closes above {_fmt(last10.max())} (10-day high)"
    else:
        wrong_if = f"no edge; watch for a break above {_fmt(last10.max())} or below {_fmt(last10.min())}"

    return {
        "name": name,
        "kind": "setup",
        "horizon": horizon,
        "horizon_label": f"next {horizon} sessions",
        "bias": bias,
        "confidence": confidence,
        "p_up": round(p_up, 3),
        "base_p_up": round(base_p_up, 3),
        "edge_pct_points": round((p_up - base_p_up) * 100, 1),
        "avg_return_pct": round(avg, 2),
        "n_similar": n,
        "setup_used": list(used),
        "reasons": reasons,
        "evidence": evidence,
        "wrong_if": wrong_if,
        "as_of": str(f.index[-1].date()),
        "entry_close": round(float(close), 2),
    }


US_BINS = [-np.inf, -1.0, 0.0, 1.0, np.inf]
US_LABELS = ["fell more than 1%", "fell 0-1%", "rose 0-1%", "rose more than 1%"]


def global_cue(target: pd.DataFrame, driver: pd.DataFrame, target_name: str = "Nifty 50",
               driver_name: str = "S&P 500", min_samples: int = 30) -> dict:
    """How the target (e.g. Nifty) did in the session after the driver (e.g. S&P 500) moved.

    US markets close after Indian markets, so last night's S&P move is genuinely new
    information for today's Nifty session.
    """
    t = _clean(target["Close"])
    d = _clean(driver["Close"])
    t_df = pd.DataFrame({"date": t.index, "t_ret": t.pct_change().to_numpy()})
    d_df = pd.DataFrame({"date": d.index, "d_ret": d.pct_change().to_numpy() * 100, "d_date": d.index})

    # For each target session, the most recent driver session strictly before it
    merged = pd.merge_asof(t_df.sort_values("date"), d_df.sort_values("date"),
                           on="date", allow_exact_matches=False).dropna()
    merged["bucket"] = pd.cut(merged["d_ret"], US_BINS, labels=US_LABELS).astype(object)

    last_t, last_d = t.index[-1], d.index[-1]
    if last_d < last_t:
        return {"name": target_name, "error": f"no new {driver_name} session since {target_name}'s last close"}
    today_move = float(d.pct_change().iloc[-1] * 100)
    bucket = pd.cut(pd.Series([today_move]), US_BINS, labels=US_LABELS).astype(object).iloc[0]

    match = merged[merged["bucket"] == bucket]
    if len(match) < min_samples:
        return {"name": target_name, "error": "not enough history"}
    base = float((merged["t_ret"] > 0).mean())
    p_up = float((match["t_ret"] > 0).mean())
    avg = float(match["t_ret"].mean() * 100)
    bias, confidence = _bias(p_up, base, len(match))

    return {
        "name": target_name,
        "kind": "global_cue",
        "horizon": 1,
        "horizon_label": "today's session",
        "bias": bias,
        "confidence": confidence,
        "p_up": round(p_up, 3),
        "base_p_up": round(base, 3),
        "edge_pct_points": round((p_up - base) * 100, 1),
        "avg_return_pct": round(avg, 2),
        "n_similar": len(match),
        "reasons": [f"{driver_name} {today_move:+.2f}% overnight ({bucket})"],
        "evidence": (
            f"After {len(match)} past US sessions where the {driver_name} {bucket}, {target_name} closed "
            f"higher next session {p_up:.0%} of the time, avg {avg:+.2f}% (normal: {base:.0%})"
        ),
        "wrong_if": "",
        "as_of": str(last_t.date()),
        "entry_close": round(float(t.iloc[-1]), 2),
    }
