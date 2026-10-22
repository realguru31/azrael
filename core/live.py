"""
live.py — what the live desk may and may not look at, as pure functions.

The rules are written on 5-minute CLOSES ("a 5-minute close outside the box", "stops are 5-minute closes"). tvDatafeed
returns the bar that is still forming as the last row, so feeding the raw series to the engine lets a half-built bar
"trigger", "stop" or vanish on the next poll — the flicker behind the false ACTIVE / DONE alerts. The live engine
therefore only ever sees bars that had closed when the feed was read; the forming bar is used for the live price and
for "armed" (heads-up) status only. The settlement audit runs on complete sessions and is unaffected.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Optional

import pandas as pd

from utils.timeutil import ET


def fetched_at(df: Optional[pd.DataFrame], default: Optional[datetime] = None) -> Optional[datetime]:
    """When the feed was read (stamped by the cached loaders in views/common.py), as an ET datetime."""
    if df is not None and getattr(df, "attrs", None):
        t = df.attrs.get("fetched_at")
        if t:
            return datetime.fromtimestamp(float(t), ET)
    return default


def closed(df: Optional[pd.DataFrame], minutes: int, asof: Optional[datetime]) -> pd.DataFrame:
    """Bars whose close time (open + interval) is at or before `asof`. A row is stamped at its bar OPEN."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    if asof is None:
        return df
    cut = pd.Timestamp(asof).tz_convert(ET) - pd.Timedelta(minutes=minutes)
    return df[df.index <= cut]


def known(df: Optional[pd.DataFrame], minutes: int, asof: Optional[datetime]) -> pd.DataFrame:
    """Everything that is final at `asof`: the closed bars, plus the forming bar reduced to its OPEN (open = high = low =
    close, volume 0). The open is the only final value of a forming bar — S4 enters 'on the open of the second candle
    following acceptance', so the live engine must see it the moment that candle starts. A zero-range stub can neither
    close outside a box, nor print a wick, nor reverse on volume, so nothing else can fire on it."""
    done = closed(df, minutes, asof)
    if df is None or df.empty or asof is None or len(done) == len(df):
        return done
    last = df.iloc[-1]
    o = float(last["open"])
    stub = pd.DataFrame({"open": [o], "high": [o], "low": [o], "close": [o], "volume": [0.0]}, index=df.index[-1:])
    return pd.concat([done, stub])


def bar_clock(now: datetime, minutes: int = 5) -> Dict[str, object]:
    """The 5-minute bar forming at `now`: its open, its close and the seconds left."""
    now = now.astimezone(ET)
    start = now.replace(second=0, microsecond=0) - timedelta(minutes=now.minute % minutes)
    end = start + timedelta(minutes=minutes)
    left = max(0, int((end - now).total_seconds()))
    return {"open": start, "close": end, "secs_left": left, "label": f"{start:%H:%M} bar closes {end:%H:%M}",
            "countdown": f"{left // 60}:{left % 60:02d}"}


def box(closed_bars: Optional[pd.DataFrame], n: int = 4) -> Optional[Dict[str, float]]:
    """The rolling 20-minute box = the last n CLOSED bars (the box the next close is measured against)."""
    if closed_bars is None or len(closed_bars) < n:
        return None
    b = closed_bars.tail(n)
    return {"lo": float(b["low"].min()), "hi": float(b["high"].max()), "start": b.index[0].strftime("%H:%M"),
            "end": b.index[-1].strftime("%H:%M")}


def ticker_vs_box(all_bars: Optional[pd.DataFrame], closed_bars: Optional[pd.DataFrame], n: int = 4) -> Optional[Dict]:
    """Where a ticker's live price sits against its own 20-minute box (display only — the rule needs the CLOSE)."""
    bx = box(closed_bars, n)
    if bx is None or all_bars is None or all_bars.empty:
        return None
    px = float(all_bars["close"].iloc[-1])
    side = "above" if px > bx["hi"] else "below" if px < bx["lo"] else "inside"
    edge = bx["hi"] if px >= (bx["hi"] + bx["lo"]) / 2 else bx["lo"]
    return {**bx, "px": px, "side": side, "edge": edge, "margin_pct": abs(px - edge) / edge * 100.0 if edge else 0.0}


def three_ticker(spx_all, spx_closed, spy_all, spy_closed, qqq_all, qqq_closed, em: float) -> Dict[str, Optional[Dict]]:
    """Live 3-ticker alignment for the S3 card: each ticker against its own box, plus the SPX break threshold."""
    out = {"SPX": ticker_vs_box(spx_all, spx_closed), "SPY": ticker_vs_box(spy_all, spy_closed),
           "QQQ": ticker_vs_box(qqq_all, qqq_closed)}
    s = out["SPX"]
    if s:
        s["width"] = s["hi"] - s["lo"]
        s["max_width"] = 0.20 * em
        s["min_out"] = 0.05 * em
        s["up_trigger"] = s["hi"] + 0.05 * em
        s["dn_trigger"] = s["lo"] - 0.05 * em
    return out
