"""Fetch prices from Yahoo Finance (via yfinance) in one batch per group."""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from .indicators import analyze_stock, pct_change

log = logging.getLogger(__name__)

STALE_AFTER_DAYS = 4  # older than this = holiday/data problem, flagged in the brief


def _download(tickers: list[str], period: str) -> pd.DataFrame:
    import yfinance as yf  # imported here so tests don't need it

    return yf.download(
        tickers,
        period=period,
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        progress=False,
        threads=True,
    )


def _frame_for(data: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Pull one ticker's OHLCV out of yfinance's multi-ticker frame."""
    if isinstance(data.columns, pd.MultiIndex):
        if ticker in data.columns.get_level_values(0):
            return data[ticker]
        return data.xs(ticker, axis=1, level=1)
    return data


def snapshot(named: dict[str, str], today: date) -> list[dict]:
    """Last close and 1-day % change for a {name: ticker} mapping."""
    rows: list[dict] = []
    try:
        data = _download(list(named.values()), "10d")
    except Exception as exc:  # network down, Yahoo change, etc.
        log.error("Price download failed: %s", exc)
        return [{"name": n, "ticker": t, "error": "unavailable"} for n, t in named.items()]

    for name, ticker in named.items():
        try:
            close = _frame_for(data, ticker)["Close"].dropna()
            if close.empty:
                raise ValueError("no data")
            last_date = close.index[-1].date()
            rows.append({
                "name": name,
                "ticker": ticker,
                "close": round(float(close.iloc[-1]), 2),
                "chg_pct": pct_change(close, 1),
                "last_date": str(last_date),
                "stale": (today - last_date).days > STALE_AFTER_DAYS,
            })
        except Exception as exc:
            log.warning("No data for %s (%s): %s", name, ticker, exc)
            rows.append({"name": name, "ticker": ticker, "error": "unavailable"})
    return rows


def watchlist(tickers: list[str], signal_cfg: dict) -> list[dict]:
    """1 year of history per stock so we can compute 50-DMA, RSI, 52-week range."""
    if not tickers:
        return []
    try:
        data = _download(tickers, "1y")
    except Exception as exc:
        log.error("Watchlist download failed: %s", exc)
        return [{"ticker": t, "error": "unavailable"} for t in tickers]

    rows: list[dict] = []
    for ticker in tickers:
        try:
            df = _frame_for(data, ticker)
            rows.append({"ticker": ticker, **analyze_stock(df, signal_cfg)})
        except Exception as exc:
            log.warning("Could not analyze %s: %s", ticker, exc)
            rows.append({"ticker": ticker, "error": "unavailable"})
    return rows
