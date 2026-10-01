"""
fetcher.py — every network call lives here. Nothing in here imports streamlit or the core modules.

Sources (from the streamlit-options-dashboard skill):
    tvDatafeed  live SPX / SPY / QQQ / VIX / ES bars (anonymous works for index data; optional login via secrets)
    CBOE        delayed (~15 min) SPX and SPY option chains with open interest, volume, IV and greeks — free
    Barchart    optional live chain if minted WAF cookies exist (store/session/cookies.json) — never required

Design rules
    • Spot never comes from the chain vendor.
    • Fetchers return None / empty on failure; callers fall back. The UI shows which source served the data.
    • The 08:15 VIX print and the 08:20 /ES price are read off the feeds' own 1-minute bars, so they are exact
      regardless of when the app was opened.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import date, datetime, time as dtime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

SYMBOLS = {
    "SPX": [("SP", "SPX"), ("CBOE", "SPX"), ("TVC", "SPX")],
    "VIX": [("CBOE", "VIX"), ("TVC", "VIX")],
    "ES": [("CME_MINI", "ES1!"), ("CME_MINI", "ESZ2026"), ("OANDA", "SPX500USD"), ("FOREXCOM", "SPX500")],
    "SPY": [("AMEX", "SPY"), ("NYSE", "SPY"), ("BATS", "SPY")],
    "QQQ": [("NASDAQ", "QQQ"), ("BATS", "QQQ")],
}
CBOE_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{sym}.json"
_OCC = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

_cboe_cache: Dict[str, Dict] = {}
_CBOE_TTL = 120
_tv = None
_tv_failed_at = 0.0

DEMO = os.environ.get("AZRAEL_DEMO", "0") == "1"


# ═════════════════════════════ tvDatafeed ═════════════════════════════
def _tv_client(username: Optional[str] = None, password: Optional[str] = None):
    """One TvDatafeed per process. Anonymous unless credentials are given (secrets)."""
    global _tv, _tv_failed_at
    if _tv is not None:
        return _tv
    if time.time() - _tv_failed_at < 60:
        return None
    try:
        from tvDatafeed import TvDatafeed  # type: ignore
        _tv = TvDatafeed(username, password) if username and password else TvDatafeed()
        return _tv
    except Exception as e:                 # ImportError or login failure
        logger.warning("tvDatafeed unavailable: %s", e)
        _tv_failed_at = time.time()
        return None


def _interval(name: str):
    from tvDatafeed import Interval  # type: ignore
    return {"1": Interval.in_1_minute, "5": Interval.in_5_minute, "15": Interval.in_15_minute,
            "60": Interval.in_1_hour, "D": Interval.in_daily}[name]


def _to_et(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    df = df.copy()
    df.index = idx.tz_convert(ET)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def get_bars(key: str, interval: str = "5", n_bars: int = 400, creds: Optional[Tuple[str, str]] = None,
             extended: bool = True) -> Tuple[Optional[pd.DataFrame], str]:
    """Bars for a logical symbol key ('SPX','VIX','ES','SPY','QQQ'), ET-indexed. Returns (df, 'EXCHANGE:SYMBOL')."""
    if DEMO:
        return demo_bars(key, interval, n_bars), "demo"
    tv = _tv_client(*(creds or (None, None)))
    if tv is None:
        return None, ""
    for exch, sym in SYMBOLS[key]:
        try:
            df = tv.get_hist(symbol=sym, exchange=exch, interval=_interval(interval), n_bars=n_bars, extended_session=extended)
            if df is not None and len(df) >= 2:
                df = df.rename(columns={c: c.lower() for c in df.columns})
                return _to_et(df[["open", "high", "low", "close", "volume"]]), f"{exch}:{sym}"
        except Exception as e:
            logger.info("tv %s:%s %s failed: %s", exch, sym, interval, e)
            continue
    return None, ""


def daily(key: str, n: int = 6, creds=None) -> Tuple[Optional[pd.DataFrame], str]:
    return get_bars(key, "D", n, creds, extended=False)


def prior_close(key: str, session: date, creds=None) -> Tuple[Optional[float], Optional[date], str]:
    """Official close of the last completed session before `session` from the daily bars."""
    df, src = daily(key, 8, creds)
    if df is None or df.empty:
        return None, None, src
    dts = [d.date() for d in df.index]
    for i in range(len(dts) - 1, -1, -1):
        if dts[i] < session:
            return float(df["close"].iloc[i]), dts[i], src
    return None, None, src


def print_at(df: Optional[pd.DataFrame], session: date, hh: int, mm: int) -> Tuple[Optional[float], str]:
    """Close of the 1-minute bar stamped hh:mm (the 'print'), else the last bar before it that day."""
    if df is None or df.empty:
        return None, "no bars"
    day = df[df.index.date == session]
    if day.empty:
        return None, "no bars for the session"
    t = dtime(hh, mm)
    exact = day[day.index.time == t]
    if not exact.empty:
        return float(exact["close"].iloc[-1]), f"{hh:02d}:{mm:02d} ET print"
    before = day[day.index.time < t]
    if not before.empty:
        return float(before["close"].iloc[-1]), f"last print before {hh:02d}:{mm:02d} ({before.index[-1].strftime('%H:%M')})"
    return None, f"no print before {hh:02d}:{mm:02d} yet"


def latest(df: Optional[pd.DataFrame]) -> Tuple[Optional[float], Optional[str]]:
    if df is None or df.empty:
        return None, None
    return float(df["close"].iloc[-1]), df.index[-1].strftime("%m-%d %H:%M")


def session_slice(df: Optional[pd.DataFrame], session: date) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    return df[df.index.date == session].copy()


def overnight_range(es: Optional[pd.DataFrame], session: date) -> Tuple[Optional[float], Optional[float]]:
    """/ES 18:00 (prior evening) to 09:30 range — the pre-market high/low of the 08:45 map."""
    if es is None or es.empty:
        return None, None
    prev = session - timedelta(days=1)
    start = datetime.combine(prev, dtime(18, 0), tzinfo=ET)
    end = datetime.combine(session, dtime(9, 30), tzinfo=ET)
    w = es[(es.index >= start) & (es.index < end)]
    if w.empty:
        return None, None
    return float(w["high"].max()), float(w["low"].min())


# ═════════════════════════════ CBOE chain ═════════════════════════════
def cboe_raw(underlying: str = "SPX", force: bool = False) -> Optional[Dict]:
    """Full delayed chain (all expiries) for '_SPX' or 'SPY'. Cached per process."""
    if DEMO:
        return None
    key = "_" + underlying if underlying in ("SPX", "VIX", "NDX", "RUT", "XSP") else underlying
    now = time.time()
    c = _cboe_cache.get(key)
    if c and not force and now - c["ts"] < _CBOE_TTL:
        return c["raw"]
    try:
        r = requests.get(CBOE_URL.format(sym=key), timeout=30, headers={"accept": "application/json", "user-agent": _UA})
        r.raise_for_status()
        data = r.json().get("data")
        if not data or "options" not in data:
            return c["raw"] if c else None
        _cboe_cache[key] = {"ts": now, "raw": data}
        return data
    except Exception as e:
        logger.warning("CBOE %s failed: %s", key, e)
        return c["raw"] if c else None


def cboe_expiries(underlying: str = "SPX") -> List[str]:
    raw = cboe_raw(underlying)
    if not raw:
        return []
    exps = set()
    for o in raw["options"]:
        m = _OCC.match(o.get("option", ""))
        if m:
            y = m.group(2)
            exps.add(f"20{y[:2]}-{y[2:4]}-{y[4:6]}")
    return sorted(exps)


def _f(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def cboe_chain(expiry: str, underlying: str = "SPX") -> Optional[pd.DataFrame]:
    """One row per strike for one expiry, normalised schema (c_* / p_*). SPX and SPXW roots aggregated:
    OI and volume summed, prices and greeks OI-weighted."""
    raw = cboe_raw(underlying)
    if not raw:
        return None
    rows = []
    for o in raw["options"]:
        m = _OCC.match(o.get("option", ""))
        if not m:
            continue
        root, ymd, cp, strike = m.groups()
        if f"20{ymd[:2]}-{ymd[2:4]}-{ymd[4:6]}" != expiry:
            continue
        bid, ask, last = _f(o.get("bid")), _f(o.get("ask")), _f(o.get("last_trade_price"))
        rows.append({
            "strike": int(strike) / 1000.0, "type": "c" if cp == "C" else "p", "root": root,
            "oi": int(_f(o.get("open_interest"))), "volume": int(_f(o.get("volume"))),
            "iv": _f(o.get("iv")), "delta": _f(o.get("delta")), "gamma": _f(o.get("gamma")),
            "vega": _f(o.get("vega")), "theta": _f(o.get("theta")), "bid": bid, "ask": ask, "last": last,
            "mark": round((bid + ask) / 2, 2) if (bid > 0 and ask > 0) else last,
        })
    if not rows:
        return None
    df = pd.DataFrame(rows)
    out = []
    for strike, g in df.groupby("strike"):
        row = {"strike": float(strike)}
        for side in ("c", "p"):
            s = g[g["type"] == side]
            if s.empty:
                for f in ("oi", "volume", "iv", "delta", "gamma", "vega", "theta", "bid", "ask", "last", "mark"):
                    row[f"{side}_{f}"] = 0.0
                continue
            w = s["oi"].astype(float).values
            ws = w.sum()
            row[f"{side}_oi"] = int(s["oi"].sum())
            row[f"{side}_volume"] = int(s["volume"].sum())
            for f in ("iv", "delta", "gamma", "vega", "theta", "bid", "ask", "last", "mark"):
                v = s[f].astype(float).values
                row[f"{side}_{f}"] = float(np.average(v, weights=w)) if ws > 0 else float(v.mean())
        out.append(row)
    res = pd.DataFrame(out).sort_values("strike").reset_index(drop=True)
    res["total_oi"] = res["c_oi"] + res["p_oi"]
    res["total_volume"] = res["c_volume"] + res["p_volume"]
    return res


def cboe_underlying(underlying: str = "SPX") -> Dict[str, Optional[float]]:
    raw = cboe_raw(underlying)
    if not raw:
        return {}
    return {"close": _f(raw.get("close")) or None, "prev_day_close": _f(raw.get("prev_day_close")) or None,
            "current_price": _f(raw.get("current_price")) or None}


# ═════════════════════════════ demo data (offline) ═════════════════════════════
def demo_bars(key: str, interval: str, n: int) -> pd.DataFrame:
    """Deterministic synthetic bars so the app renders with no network (AZRAEL_DEMO=1)."""
    rng = np.random.default_rng({"SPX": 1, "VIX": 2, "ES": 3, "SPY": 4, "QQQ": 5}[key])
    base = {"SPX": 7670.84, "VIX": 16.11, "ES": 7731.5, "SPY": 764.2, "QQQ": 742.0}[key]
    vol = {"SPX": 0.9, "VIX": 0.03, "ES": 0.9, "SPY": 0.09, "QQQ": 0.1}[key]
    end = datetime.now(ET).replace(second=0, microsecond=0)
    step = {"1": 1, "5": 5, "15": 15, "60": 60, "D": 1440}[interval]
    idx = pd.date_range(end=end, periods=n, freq=f"{step}min")
    if interval == "D":
        idx = pd.date_range(end=end.date(), periods=n, freq="B", tz=ET)
    close = base + np.cumsum(rng.normal(0, vol, n))
    high = close + np.abs(rng.normal(0, vol, n))
    low = close - np.abs(rng.normal(0, vol, n))
    opn = np.r_[close[0], close[:-1]]
    volm = rng.integers(500, 5000, n)
    df = pd.DataFrame({"open": opn, "high": high, "low": low, "close": close, "volume": volm}, index=idx)
    if key == "VIX":
        df["volume"] = 0
    return df
