"""Technical indicators and signal detection.

Pure pandas, no network calls, so it is easy to test (see tests/).
The LLM never computes these numbers; this module does.
"""
from __future__ import annotations

import pandas as pd


def pct_change(close: pd.Series, periods: int = 1) -> float | None:
    """% change between the last close and the close `periods` bars earlier."""
    close = close.dropna()
    if len(close) <= periods:
        return None
    return round((close.iloc[-1] / close.iloc[-1 - periods] - 1) * 100, 2)


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index using Wilder's smoothing."""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = gain / loss
    out = 100 - 100 / (1 + rs)
    # All gains and no losses means RSI = 100; no movement at all means neutral 50
    out = out.where(loss != 0, 100.0)
    return out.where(~((gain == 0) & (loss == 0)), 50.0)


def analyze_stock(df: pd.DataFrame, cfg: dict) -> dict:
    """Compute metrics and human-readable signals for one stock.

    df needs 'Close' and 'Volume' columns, ideally ~1 year of daily bars.
    cfg is the `signals` section of config.yaml.
    """
    df = df.dropna(subset=["Close"])
    close, volume = df["Close"], df["Volume"]
    last = float(close.iloc[-1])

    chg_1d = pct_change(close, 1)
    chg_5d = pct_change(close, 5)
    rsi_series = rsi(close)
    rsi_now = float(rsi_series.iloc[-1]) if rsi_series.notna().any() else None

    sma50 = close.rolling(50).mean()
    high_52w = float(close.tail(252).max())
    low_52w = float(close.tail(252).min())

    avg_vol_20 = volume.iloc[-21:-1].mean() if len(volume) > 21 else None
    vol_ratio = (
        round(float(volume.iloc[-1] / avg_vol_20), 2)
        if avg_vol_20 and avg_vol_20 > 0
        else None
    )

    signals: list[str] = []

    if chg_1d is not None and abs(chg_1d) >= cfg["big_move_pct"]:
        signals.append(f"big move: {chg_1d:+.2f}% yesterday")

    if rsi_now is not None:
        if rsi_now >= cfg["rsi_overbought"]:
            signals.append(f"RSI {rsi_now:.0f} (overbought)")
        elif rsi_now <= cfg["rsi_oversold"]:
            signals.append(f"RSI {rsi_now:.0f} (oversold)")

    if sma50.notna().sum() >= 2:
        prev_above = close.iloc[-2] > sma50.iloc[-2]
        now_above = close.iloc[-1] > sma50.iloc[-1]
        if now_above and not prev_above:
            signals.append("crossed ABOVE 50-day average")
        elif prev_above and not now_above:
            signals.append("crossed BELOW 50-day average")

    near = cfg["near_52w_pct"] / 100
    if last >= high_52w:
        signals.append("at 52-week high")
    elif last >= high_52w * (1 - near):
        signals.append("near 52-week high")
    if last <= low_52w:
        signals.append("at 52-week low")
    elif last <= low_52w * (1 + near):
        signals.append("near 52-week low")

    if vol_ratio is not None and vol_ratio >= cfg["volume_spike_x"]:
        signals.append(f"volume {vol_ratio}x the 20-day average")

    return {
        "close": round(last, 2),
        "chg_1d_pct": chg_1d,
        "chg_5d_pct": chg_5d,
        "rsi14": round(rsi_now, 1) if rsi_now is not None else None,
        "above_50dma": bool(close.iloc[-1] > sma50.iloc[-1]) if pd.notna(sma50.iloc[-1]) else None,
        "high_52w": round(high_52w, 2),
        "low_52w": round(low_52w, 2),
        "volume_vs_20d": vol_ratio,
        "last_date": str(close.index[-1].date()),
        "signals": signals,
        "notable": bool(signals),
    }
