"""Keep score: log every call, grade it once its horizon has passed.

Predictions without a track record are just opinions. This file is saved in the
repository (data/predictions.csv), so the history builds up day after day.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

COLUMNS = [
    "made_on", "ticker", "name", "kind", "horizon", "bias", "confidence", "p_up",
    "entry_date", "entry_close", "status", "exit_date", "exit_close", "return_pct",
]


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Consistent column types, whether the table is new, loaded from CSV, or appended to."""
    df = df.reindex(columns=COLUMNS).copy()
    for col in ("p_up", "entry_close", "exit_close", "return_pct"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")
    df["horizon"] = pd.to_numeric(df["horizon"], errors="coerce")
    for col in ("made_on", "ticker", "name", "kind", "bias", "confidence", "entry_date", "status", "exit_date"):
        df[col] = df[col].astype(object).where(df[col].notna(), None)
    return df


def load(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return _normalize(pd.DataFrame(columns=COLUMNS))
    return _normalize(pd.read_csv(p, dtype=str))


def save(df: pd.DataFrame, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    df[COLUMNS].to_csv(p, index=False)


def add(df: pd.DataFrame, outlooks: list[dict], made_on: date) -> pd.DataFrame:
    """Append today's calls. Re-running on the same day doesn't duplicate them."""
    rows = []
    for o in outlooks:
        if "error" in o:
            continue
        key = (str(made_on), o["ticker"], o["kind"])
        if ((df["made_on"] == key[0]) & (df["ticker"] == key[1]) & (df["kind"] == key[2])).any():
            continue
        rows.append({
            "made_on": str(made_on), "ticker": o["ticker"], "name": o["name"], "kind": o["kind"],
            "horizon": o["horizon"], "bias": o["bias"], "confidence": o["confidence"],
            "p_up": o["p_up"], "entry_date": o["as_of"], "entry_close": o["entry_close"],
            "status": "unscored" if o["bias"] == "neutral" else "open",
            "exit_date": None, "exit_close": None, "return_pct": None,
        })
    if not rows:
        return df
    new = _normalize(pd.DataFrame(rows, columns=COLUMNS))
    return new if df.empty else _normalize(pd.concat([df, new], ignore_index=True))


def grade(df: pd.DataFrame, closes: dict[str, pd.Series]) -> pd.DataFrame:
    """Close out open calls whose horizon has passed, using actual closing prices."""
    df = df.copy()
    for i, row in df[df["status"] == "open"].iterrows():
        series = closes.get(row["ticker"])
        if series is None:
            continue
        s = series.dropna()
        if getattr(s.index, "tz", None) is not None:
            s.index = s.index.tz_localize(None)
        after = s[s.index > pd.Timestamp(row["entry_date"])]
        h = int(row["horizon"])
        if len(after) < h:
            continue  # not matured yet
        exit_close = float(after.iloc[h - 1])
        ret = (exit_close / float(row["entry_close"]) - 1) * 100
        correct = ret > 0 if row["bias"] == "bullish" else ret < 0
        df.at[i, "status"] = "hit" if correct else "miss"
        df.at[i, "exit_date"] = str(after.index[h - 1].date())
        df.at[i, "exit_close"] = round(exit_close, 2)
        df.at[i, "return_pct"] = round(ret, 2)
    return df


def summary(df: pd.DataFrame, today: date, days: int = 60) -> dict:
    """Hit rate of graded calls whose outcome landed in the last `days` days."""
    graded = df[df["status"].isin(["hit", "miss"])].copy()
    if graded.empty:
        return {"graded": 0, "open": int((df["status"] == "open").sum())}
    graded = graded[pd.to_datetime(graded["exit_date"]) >= pd.Timestamp(today - timedelta(days=days))]
    hits = int((graded["status"] == "hit").sum())
    return {
        "graded": len(graded),
        "hits": hits,
        "hit_rate": round(hits / len(graded), 3) if len(graded) else None,
        "open": int((df["status"] == "open").sum()),
        "window_days": days,
    }
