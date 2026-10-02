"""
rules.py — the desk's mechanical archetype rules on 5-minute bars, exactly as the desk bot states them
in its Tactical Execution Maps and 04:15 Rules Replay (Sep 29 / Sep 30 2026 posts), with the manual's
definitions (Ch.3, Ch.4) where the bot leaves something implicit.

All functions are pure: bars in (ET-indexed DataFrames with open/high/low/close/volume), results out.
Everything is measured on the index, not on option fills — same convention as the desk audit.

Bar convention: a row's index is the bar OPEN time; the bar closes 5 minutes later. "A bar closing after
09:50" therefore means bars stamped 09:45 or later closing at 09:50 or later — the bot's replay took the
09:50 gate as the first bar whose close time is >= 09:50.

Mechanical definitions
    Gate (09:50 test)     open print = 09:30 bar open. Initial move = side of the larger excursion in the first
                          10 minutes (09:30 and 09:35 bars). At the 09:45 bar's close (09:50): two consecutive
                          closes on the initial side = ACCEPTANCE; last close on the opposite side = TRAP.
    A2 King Node          SPX falls >= 15 pts into the put node and a bar closes back above it with a lower wick
                          over half its range -> long; target = half the fall back; stop = 5-min close below
                          node - 5, or two closes below the node. Mirror at the call node.
    A3 3-ticker breakout  all three close a 5-min bar outside their last 20-minute box (prior 4 bars); the SPX box
                          is no wider than 0.20 EM; SPX closes >= 0.05 EM outside; > 8 pts of room to the next EM
                          level; trade toward that level; out on a close back inside the box.
    A1 Half-EM fade       (Positive only) probe within 5 pts of C14/C16, two consecutive closes at/near the shelf
                          without continuation (no close > 8 beyond), third bar reverses toward the anchor on
                          volume above the prior two bars; entry on that close; stop = close > 8 beyond the shelf;
                          target = anchor within 3 pts.
    A4 1.0-EM runner      (Negative only) two consecutive closes beyond the 0.5 shelf, the first on above-average
                          volume; entry on the open of the next bar; stop = close back inside the shelf;
                          target = the 1.0 wall on first contact.
    Stand down            no qualifying bar closed by 11:05 -> no trade; open trades are flat at 11:30.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from utils.timeutil import T_GATE_END, T_LAST_QUALIFYING, T_SHUTDOWN, T_OPEN

GATE_END = time(9, 50)
LAST_QUALIFYING = time(11, 5)
SHUTDOWN = time(11, 30)


# ── helpers ───────────────────────────────────────────────────────────────────
def _minutes(ts: pd.Timestamp) -> int:
    return ts.hour * 60 + ts.minute


def session_bars(df: pd.DataFrame, start_min: int = T_OPEN, end_min: int = 16 * 60) -> pd.DataFrame:
    """Regular-hours bars of one session (index in ET)."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    mins = df.index.hour * 60 + df.index.minute
    return df[(mins >= start_min) & (mins < end_min)].copy()


def bar_close_time(ts: pd.Timestamp, bar_minutes: int = 5) -> pd.Timestamp:
    return ts + pd.Timedelta(minutes=bar_minutes)


# ── 09:50 gate test ───────────────────────────────────────────────────────────
@dataclass
class GateResult:
    status: str                 # "pending" | "acceptance" | "trap" | "unconfirmed"
    direction: int              # +1 up, -1 down, 0
    open_print: Optional[float]
    close_0950: Optional[float]
    detail: str

    def as_dict(self):
        return asdict(self)


def gate_test(spx5: pd.DataFrame) -> GateResult:
    bars = session_bars(spx5)
    if bars.empty:
        return GateResult("pending", 0, None, None, "No regular-hours bars yet.")
    open_print = float(bars.iloc[0]["open"])
    first10 = bars[(bars.index.hour * 60 + bars.index.minute) < T_OPEN + 10]
    if first10.empty:
        return GateResult("pending", 0, open_print, None, "Waiting for the first bars.")
    up_exc = float(first10["high"].max()) - open_print
    dn_exc = open_print - float(first10["low"].min())
    direction = 1 if up_exc >= dn_exc else -1
    gate_bars = bars[(bars.index.hour * 60 + bars.index.minute) <= T_GATE_END - 5]      # bars closing by 09:50
    if len(gate_bars) < 4:
        return GateResult("pending", direction, open_print, None,
                          f"Initial move {'up' if direction > 0 else 'down'} ({max(up_exc, dn_exc):.1f} pts). Verdict at 09:50.")
    last_two = gate_bars["close"].iloc[-2:].tolist()
    c = last_two[-1]
    sides = [1 if x > open_print else -1 if x < open_print else 0 for x in last_two]
    if all(s == direction for s in sides):
        return GateResult("acceptance", direction, open_print, c,
                          f"Opening acceptance {'UP' if direction > 0 else 'DOWN'}: two 5-minute closes holding "
                          f"{'above' if direction > 0 else 'below'} the open {open_print:.2f}. Momentum active — look for "
                          f"Archetype 3 (Breakout) or Archetype 4 (Runner) if the regime permits.")
    if sides[-1] == -direction:
        return GateResult("trap", direction, open_print, c,
                          f"Opening trap: the first move {'up' if direction > 0 else 'down'} reversed back through the open "
                          f"{open_print:.2f}. Rejection active — look for Archetype 1 (Fade) or Archetype 2 (King Node) if the "
                          f"regime permits.")
    return GateResult("unconfirmed", direction, open_print, c,
                      "Unconfirmed: no two-close hold and no reversal through the open. Wait for absorption at a shelf.")


# ── replay data classes ───────────────────────────────────────────────────────
@dataclass
class Replay:
    archetype: int
    qualified: bool
    side: Optional[str] = None                 # "long" | "short"
    trigger_time: Optional[str] = None
    entry: Optional[float] = None
    stop: Optional[float] = None
    target: Optional[float] = None
    risk_pts: Optional[float] = None
    resolution: Optional[str] = None           # "target" | "stopped" | "flat_1130" | "open"
    exit_time: Optional[str] = None
    exit_price: Optional[float] = None
    pnl_pts: Optional[float] = None
    r_multiple: Optional[float] = None
    best_excursion: Optional[float] = None
    trigger_text: str = ""
    invalidation_text: str = ""
    resolution_text: str = ""
    not_qualified_reason: str = ""
    extra: Dict = field(default_factory=dict)

    def as_dict(self):
        return asdict(self)


def _resolve(bars_after: pd.DataFrame, side: str, entry: float, stop: float, target: float,
             stop_mode: str = "close", two_close_level: Optional[float] = None) -> Tuple[str, Optional[pd.Timestamp], float, float]:
    """Walk forward bar by bar. Target = first touch (high/low). Stop = 5-minute close through the stop level
    (or two consecutive closes through `two_close_level`). Flat at the 11:30 bar close if still open.
    Returns (resolution, exit_time, exit_price, best_excursion_pts)."""
    best = 0.0
    consecutive = 0
    for ts, r in bars_after.iterrows():
        t = ts.time()
        if side == "long":
            best = max(best, float(r["high"]) - entry)
            if float(r["high"]) >= target:
                return "target", ts, target, best
            if float(r["close"]) <= stop:
                return "stopped", ts, float(r["close"]), best
            if two_close_level is not None:
                consecutive = consecutive + 1 if float(r["close"]) < two_close_level else 0
                if consecutive >= 2:
                    return "stopped", ts, float(r["close"]), best
        else:
            best = max(best, entry - float(r["low"]))
            if float(r["low"]) <= target:
                return "target", ts, target, best
            if float(r["close"]) >= stop:
                return "stopped", ts, float(r["close"]), best
            if two_close_level is not None:
                consecutive = consecutive + 1 if float(r["close"]) > two_close_level else 0
                if consecutive >= 2:
                    return "stopped", ts, float(r["close"]), best
        if t >= time(11, 25):                       # the 11:25 bar closes at 11:30 -> flat by 11:30
            return "flat_1130", ts, float(r["close"]), best
    return "open", None, float(bars_after["close"].iloc[-1]) if len(bars_after) else entry, best


def _finish(rp: Replay, bars_after: pd.DataFrame, two_close_level: Optional[float] = None) -> Replay:
    res, ts, px, best = _resolve(bars_after, rp.side, rp.entry, rp.stop, rp.target, two_close_level=two_close_level)
    rp.resolution, rp.exit_price, rp.best_excursion = res, px, round(best, 2)
    rp.exit_time = ts.strftime("%H:%M") if ts is not None else None
    rp.pnl_pts = round((px - rp.entry) if rp.side == "long" else (rp.entry - px), 2)
    rp.r_multiple = round(rp.pnl_pts / rp.risk_pts, 2) if rp.risk_pts else None
    exit_close = bar_close_time(ts).strftime("%H:%M") if ts is not None else "—"
    if res == "target":
        rp.resolution_text = (f"Target: the {rp.exit_time} bar reached {rp.target:.2f}, +{rp.pnl_pts:.2f} pts "
                              f"(+{rp.r_multiple:.2f}R on the index). Best excursion {rp.best_excursion:.2f} pts.")
    elif res == "stopped":
        over = abs(rp.r_multiple) - 1 if rp.r_multiple is not None else 0
        rp.resolution_text = (f"Stopped: the {rp.exit_time} bar closed at {px:.2f}, {rp.pnl_pts:+.2f} pts "
                              f"({rp.r_multiple:+.2f}R on the index). The stop is a 5-minute close, so the exit "
                              f"{'overshot' if over > 0 else 'landed within'} the planned 1R by {abs(over):.2f}R. "
                              f"Best excursion before the exit: {rp.best_excursion:.2f} pts in favor.")
    elif res == "flat_1130":
        rp.resolution_text = (f"Flat at the 11:30 desk shutdown: closed at {px:.2f}, {rp.pnl_pts:+.2f} pts "
                              f"({rp.r_multiple:+.2f}R). Best excursion {rp.best_excursion:.2f} pts.")
    else:
        rp.resolution_text = (f"Still open at the last bar ({px:.2f}, {rp.pnl_pts:+.2f} pts, {rp.r_multiple:+.2f}R). "
                              f"Best excursion {rp.best_excursion:.2f} pts.")
    return rp


def _after(bars: pd.DataFrame, ts: pd.Timestamp) -> pd.DataFrame:
    return bars[bars.index > ts]


def _window(bars: pd.DataFrame) -> pd.DataFrame:
    """Bars that can qualify: close time >= 09:50 and close time <= 11:05 ('no qualifying bar closed by 11:05'),
    i.e. open times 09:45 … 11:00."""
    mins = bars.index.hour * 60 + bars.index.minute
    return bars[(mins + 5 >= T_GATE_END) & (mins + 5 <= T_LAST_QUALIFYING)]


def _touch_window(bars: pd.DataFrame) -> pd.DataFrame:
    """The desk reports node touches over 09:50 to 11:30 ('SPX never reached it from 09:50 to 11:30')."""
    mins = bars.index.hour * 60 + bars.index.minute
    return bars[(mins + 5 >= T_GATE_END) & (mins < T_SHUTDOWN)]


# ── Archetype 2 — King Node absorption ────────────────────────────────────────
def replay_a2(spx5: pd.DataFrame, put_node: float, call_node: float, min_fall: float = 15.0,
              stop_pts: float = 5.0) -> Replay:
    bars = session_bars(spx5)
    if bars.empty:
        return Replay(2, False, not_qualified_reason="no session bars")
    win = _window(bars)
    reasons = []
    for ts, r in win.iterrows():
        prior = bars[bars.index < ts]
        # put node: fall into the node, close back above it, lower wick > half the range
        if float(r["low"]) <= put_node and float(r["close"]) > put_node and len(prior):
            fall = float(prior["high"].max()) - put_node
            rng = float(r["high"]) - float(r["low"])
            wick = min(float(r["open"]), float(r["close"])) - float(r["low"])
            if fall >= min_fall and rng > 0 and wick > 0.5 * rng:
                entry = float(r["close"])
                rp = Replay(2, True, "long", ts.strftime("%H:%M"), entry, put_node - stop_pts,
                            put_node + 0.5 * fall, round(entry - (put_node - stop_pts), 2),
                            trigger_text=(f"SPX fell {fall:.2f} pts into the put node {put_node:.0f}; the {ts:%H:%M} bar "
                                          f"(low {r['low']:.2f}) closed back above it at {entry:.2f} with a lower wick of "
                                          f"{wick:.2f} pts on a {rng:.2f}-pt range. Long calls; target half the fall back "
                                          f"({put_node + 0.5 * fall:.2f})."),
                            invalidation_text=(f"A 5-minute close below {put_node - stop_pts:.0f} (node − {stop_pts:.0f}) or two "
                                               f"closes below {put_node:.0f}. Planned risk {entry - (put_node - stop_pts):.2f} pts = 1R."))
                return _finish(rp, _after(bars, ts), two_close_level=put_node)
            reasons.append(f"{ts:%H:%M} touched the put node but fall {fall:.1f} pts / wick {wick:.1f} of {rng:.1f} did not qualify")
        # call node mirror
        if float(r["high"]) >= call_node and float(r["close"]) < call_node and len(prior):
            rise = call_node - float(prior["low"].min())
            rng = float(r["high"]) - float(r["low"])
            wick = float(r["high"]) - max(float(r["open"]), float(r["close"]))
            if rise >= min_fall and rng > 0 and wick > 0.5 * rng:
                entry = float(r["close"])
                rp = Replay(2, True, "short", ts.strftime("%H:%M"), entry, call_node + stop_pts,
                            call_node - 0.5 * rise, round((call_node + stop_pts) - entry, 2),
                            trigger_text=(f"SPX rose {rise:.2f} pts into the call node {call_node:.0f}; the {ts:%H:%M} bar "
                                          f"(high {r['high']:.2f}) closed back below it at {entry:.2f} with an upper wick of "
                                          f"{wick:.2f} pts on a {rng:.2f}-pt range. Long puts; target half the rise back "
                                          f"({call_node - 0.5 * rise:.2f})."),
                            invalidation_text=(f"A 5-minute close above {call_node + stop_pts:.0f} (node + {stop_pts:.0f}) or two "
                                               f"closes above {call_node:.0f}. Planned risk {(call_node + stop_pts) - entry:.2f} pts = 1R."))
                return _finish(rp, _after(bars, ts), two_close_level=call_node)
            reasons.append(f"{ts:%H:%M} touched the call node but rise {rise:.1f} pts / wick {wick:.1f} of {rng:.1f} did not qualify")
    tw = _touch_window(bars)
    why = []
    if tw.empty:
        return Replay(2, False, not_qualified_reason="no bars between 09:50 and 11:30")
    lo, hi = float(tw["low"].min()), float(tw["high"].max())
    # put node
    if lo > put_node:
        why.append(f"Archetype 2 at the put node {put_node:.0f} did not qualify: SPX never reached it from 09:50 to 11:30; "
                   f"the window low was {lo:.2f}, {lo - put_node:.2f} pts above it")
    else:
        touch = tw[tw["low"] <= put_node]
        b = touch.loc[touch["close"].idxmax()]          # the touch that came closest to closing back above the node
        why.append(f"Archetype 2 at the put node {put_node:.0f} did not qualify: the best touch was the {b.name:%H:%M} bar "
                   f"(low {float(b['low']):.2f}, close {float(b['close']):.2f}); "
                   + ("it did not close back above " + f"{put_node:.0f}" if float(b["close"]) <= put_node
                      else "the fall into the node or the rejection wick did not meet the rule"))
    # call node
    if hi < call_node:
        why.append(f"Archetype 2 at the call node {call_node:.0f} did not qualify: SPX never reached it from 09:50 to 11:30; "
                   f"the window high was {hi:.2f}, {call_node - hi:.2f} pts below it")
    else:
        touch = tw[tw["high"] >= call_node]
        b = touch.loc[touch["close"].idxmin()]          # the touch that came closest to closing back below the node
        why.append(f"Archetype 2 at the call node {call_node:.0f} did not qualify: the best touch was the {b.name:%H:%M} bar "
                   f"(high {float(b['high']):.2f}, close {float(b['close']):.2f}); "
                   + ("it did not close back below " + f"{call_node:.0f}" if float(b["close"]) >= call_node
                      else "the rise into the node or the rejection wick did not meet the rule"))
    return Replay(2, False, not_qualified_reason=". ".join(why))


# ── Archetype 3 — 3-ticker alignment breakout ─────────────────────────────────
def replay_a3(spx5: pd.DataFrame, spy5: Optional[pd.DataFrame], qqq5: Optional[pd.DataFrame], em: float,
              levels: List[float], room_pts: float = 8.0, box_bars: int = 4, require_all: bool = True) -> Replay:
    bars = session_bars(spx5)
    if bars.empty:
        return Replay(3, False, not_qualified_reason="no session bars")
    if require_all and ((spy5 is None or spy5.empty) or (qqq5 is None or qqq5.empty)):
        return Replay(3, False, not_qualified_reason="SPY and/or QQQ 5-minute bars unavailable — the 3-ticker alignment cannot be confirmed")
    spy = session_bars(spy5) if spy5 is not None else None
    qqq = session_bars(qqq5) if qqq5 is not None else None
    max_box = 0.20 * em
    min_out = 0.05 * em
    win = _window(bars)
    near_misses = []
    for ts, r in win.iterrows():
        prior = bars[bars.index < ts].tail(box_bars)
        if len(prior) < box_bars:
            continue
        box_hi, box_lo = float(prior["high"].max()), float(prior["low"].min())
        width = box_hi - box_lo
        c = float(r["close"])
        side = "long" if c > box_hi else "short" if c < box_lo else None
        if side is None:
            continue
        outside = (c - box_hi) if side == "long" else (box_lo - c)
        if width > max_box:
            near_misses.append(f"{ts:%H:%M} broke {side} but the box was {width:.2f} pts wide (limit {max_box:.2f})")
            continue
        if outside < min_out:
            near_misses.append(f"{ts:%H:%M} closed only {outside:.2f} pts outside the box (needs {min_out:.2f})")
            continue
        # other tickers must close outside their own box on the same bar, same direction
        def _confirms(df):
            if df is None or df.empty or ts not in df.index:
                return None, None
            p = df[df.index < ts].tail(box_bars)
            if len(p) < box_bars:
                return None, None
            bh, bl = float(p["high"].max()), float(p["low"].min())
            cc = float(df.loc[ts, "close"])
            return (cc > bh if side == "long" else cc < bl), (bh if side == "long" else bl)
        spy_ok, spy_edge = _confirms(spy)
        qqq_ok, qqq_edge = _confirms(qqq)
        if spy_ok is False or qqq_ok is False:
            near_misses.append(f"{ts:%H:%M} SPX broke {side} but "
                               f"{'SPY' if spy_ok is False else 'QQQ'} did not close outside its own box")
            continue
        if require_all and (spy_ok is None or qqq_ok is None):
            near_misses.append(f"{ts:%H:%M} SPX broke {side} but SPY/QQQ had no bar at that time")
            continue
        # room to the next EM level in the direction of the break
        ups = sorted([l for l in levels if l > c])
        dns = sorted([l for l in levels if l < c], reverse=True)
        nxt = ups[0] if side == "long" and ups else dns[0] if side == "short" and dns else None
        if nxt is None:
            near_misses.append(f"{ts:%H:%M} no EM level beyond the break")
            continue
        room = (nxt - c) if side == "long" else (c - nxt)
        if room <= room_pts:
            near_misses.append(f"{ts:%H:%M} only {room:.2f} pts of room to {nxt:.2f} (needs > {room_pts:.0f})")
            continue
        stop = box_hi if side == "long" else box_lo
        risk = abs(c - stop)
        conf = []
        if spy_ok:
            conf.append(f"SPY {float(spy.loc[ts, 'close']):.2f} closed {'above' if side == 'long' else 'below'} its box {'high' if side == 'long' else 'low'} ({spy_edge:.2f})")
        if qqq_ok:
            conf.append(f"QQQ {float(qqq.loc[ts, 'close']):.2f} closed {'above' if side == 'long' else 'below'} its box {'high' if side == 'long' else 'low'} ({qqq_edge:.2f})")
        if spy_ok is None and qqq_ok is None:
            conf.append("SPY/QQQ bars unavailable — SPX-only confirmation")
        box_start = prior.index[0].strftime("%H:%M")
        box_end = prior.index[-1].strftime("%H:%M")
        rp = Replay(3, True, side, ts.strftime("%H:%M"), c, stop, nxt, round(risk, 2),
                    trigger_text=(f"SPX closed the {ts:%H:%M} bar at {c:.2f}, {outside:.2f} pts {'above' if side == 'long' else 'below'} "
                                  f"its {box_start} to {box_end} box ({box_lo:.2f} to {box_hi:.2f}, {width:.2f} pts wide); "
                                  + "; ".join(conf) + f" on the same bar. Next EM level {nxt:.2f}, {room:.2f} pts of room."),
                    invalidation_text=(f"A 5-minute close back inside the box, {'below' if side == 'long' else 'above'} "
                                       f"{stop:.2f}. Planned risk {risk:.2f} pts = 1R."),
                    extra={"box_lo": box_lo, "box_hi": box_hi, "width": width})
        return _finish(rp, _after(bars, ts))
    return Replay(3, False, not_qualified_reason="; ".join(near_misses[:3]) or "no 3-ticker box break closed between 09:50 and 11:05")


# ── Archetype 1 — Half-EM mean-reversion fade ─────────────────────────────────
def replay_a1(spx5: pd.DataFrame, c14: float, c15: float, c16: float, probe_pts: float = 5.0,
              stop_beyond: float = 8.0, target_within: float = 3.0) -> Replay:
    bars = session_bars(spx5)
    if bars.empty:
        return Replay(1, False, not_qualified_reason="no session bars")
    win = _window(bars)
    idx = list(bars.index)
    reasons = []
    for ts in win.index:
        i = idx.index(ts)
        if i < 2:
            continue
        b0, b1, b2 = bars.iloc[i - 2], bars.iloc[i - 1], bars.iloc[i]     # two shelf bars, then the reversal bar
        # lower shelf C16: probe within probe_pts (or through), two closes near the shelf without continuation
        near_lo = (min(float(b0["low"]), float(b1["low"])) <= c16 + probe_pts
                   and all(abs(float(b["close"]) - c16) <= probe_pts for b in (b0, b1))
                   and all(float(b["close"]) >= c16 - stop_beyond for b in (b0, b1)))
        if near_lo and float(b2["close"]) > float(b1["close"]) and float(b2["close"]) > float(b2["open"]) \
                and float(b2["volume"]) > max(float(b0["volume"]), float(b1["volume"])):
            entry = float(b2["close"])
            rp = Replay(1, True, "long", ts.strftime("%H:%M"), entry, c16 - stop_beyond, c15 - target_within,
                        round(entry - (c16 - stop_beyond), 2),
                        trigger_text=(f"SPX probed the −0.5 shelf {c16:.2f} ({b0.name:%H:%M} low {min(float(b0['low']), float(b1['low'])):.2f}); "
                                      f"the {b0.name:%H:%M} and {b1.name:%H:%M} bars closed at/near the shelf without continuation; "
                                      f"the {ts:%H:%M} bar reversed toward the anchor, closing {entry:.2f} on volume "
                                      f"{float(b2['volume']):,.0f} > prior two. Long calls; target anchor {c15:.2f} within {target_within:.0f}."),
                        invalidation_text=f"A 5-minute close more than {stop_beyond:.0f} pts below the shelf (below {c16 - stop_beyond:.2f}). "
                                          f"Planned risk {entry - (c16 - stop_beyond):.2f} pts = 1R.")
            return _finish(rp, _after(bars, ts))
        near_hi = (max(float(b0["high"]), float(b1["high"])) >= c14 - probe_pts
                   and all(abs(float(b["close"]) - c14) <= probe_pts for b in (b0, b1))
                   and all(float(b["close"]) <= c14 + stop_beyond for b in (b0, b1)))
        if near_hi and float(b2["close"]) < float(b1["close"]) and float(b2["close"]) < float(b2["open"]) \
                and float(b2["volume"]) > max(float(b0["volume"]), float(b1["volume"])):
            entry = float(b2["close"])
            rp = Replay(1, True, "short", ts.strftime("%H:%M"), entry, c14 + stop_beyond, c15 + target_within,
                        round((c14 + stop_beyond) - entry, 2),
                        trigger_text=(f"SPX probed the +0.5 shelf {c14:.2f} ({b0.name:%H:%M} high {max(float(b0['high']), float(b1['high'])):.2f}); "
                                      f"the {b0.name:%H:%M} and {b1.name:%H:%M} bars closed at/near the shelf without continuation; "
                                      f"the {ts:%H:%M} bar reversed toward the anchor, closing {entry:.2f} on volume "
                                      f"{float(b2['volume']):,.0f} > prior two. Long puts; target anchor {c15:.2f} within {target_within:.0f}."),
                        invalidation_text=f"A 5-minute close more than {stop_beyond:.0f} pts above the shelf (above {c14 + stop_beyond:.2f}). "
                                          f"Planned risk {(c14 + stop_beyond) - entry:.2f} pts = 1R.")
            return _finish(rp, _after(bars, ts))
    lo, hi = (float(win["low"].min()), float(win["high"].max())) if len(win) else (float("nan"), float("nan"))
    if not len(win) or (lo > c16 + probe_pts and hi < c14 - probe_pts):
        reasons.append(f"neither shelf was probed within {probe_pts:.0f} pts (window {lo:.2f}–{hi:.2f}; shelves {c16:.2f}/{c14:.2f})")
    else:
        reasons.append("a shelf was probed but no two-close consolidation plus higher-volume reversal bar followed")
    return Replay(1, False, not_qualified_reason="; ".join(reasons))


# ── Archetype 4 — 1.0-EM boundary runner ──────────────────────────────────────
def replay_a4(spx5: pd.DataFrame, c13: float, c14: float, c16: float, c17: float) -> Replay:
    bars = session_bars(spx5)
    if bars.empty:
        return Replay(4, False, not_qualified_reason="no session bars")
    win = _window(bars)
    idx = list(bars.index)
    for ts in win.index:
        i = idx.index(ts)
        if i < 1 or i + 2 >= len(idx):
            continue
        # b1, b2 = the two consecutive closes beyond the shelf (acceptance confirmed at b2's close);
        # b3 = the next candle, which must not snap back inside; entry on the open of b4, the second candle following
        b1, b2, b3, b4 = bars.iloc[i - 1], bars.iloc[i], bars.iloc[i + 1], bars.iloc[i + 2]
        avg_vol = float(bars.iloc[:i]["volume"].mean()) if i > 0 else 0.0
        for side, shelf, wall in (("long", c14, c13), ("short", c16, c17)):
            beyond = (lambda x: x > shelf) if side == "long" else (lambda x: x < shelf)
            if beyond(float(b1["close"])) and beyond(float(b2["close"])) and float(b1["volume"]) >= avg_vol \
                    and beyond(float(b3["close"])):
                entry = float(b4["open"])
                risk = abs(entry - shelf)
                rp = Replay(4, True, side, b4.name.strftime("%H:%M"), entry, shelf, wall, round(risk, 2),
                            trigger_text=(f"Two consecutive 5-minute closes {'above' if side == 'long' else 'below'} the "
                                          f"{'+' if side == 'long' else '−'}0.5 shelf {shelf:.2f} ({b1.name:%H:%M} {float(b1['close']):.2f} on volume "
                                          f"{float(b1['volume']):,.0f} vs session average {avg_vol:,.0f}; {b2.name:%H:%M} {float(b2['close']):.2f}); "
                                          f"the {b3.name:%H:%M} bar did not snap back inside ({float(b3['close']):.2f}); entered on the open of the "
                                          f"second candle following acceptance ({b4.name:%H:%M}) at {entry:.2f}. Target the 1.0 wall {wall:.2f} on first contact."),
                            invalidation_text=f"A 5-minute close back inside the shelf ({'below' if side == 'long' else 'above'} {shelf:.2f}). "
                                              f"Planned risk {risk:.2f} pts = 1R.")
                return _finish(rp, _after(bars, b4.name))
    return Replay(4, False, not_qualified_reason="no two consecutive closes beyond a 0.5 shelf between 09:50 and 11:05")


# ── the level set the rules use: standard, or re-anchored on gap days ────────
def rule_levels(plan: Dict) -> Dict[str, float]:
    """Standard day: C13–C17 shelves/walls and the strike-grid King Nodes. Gap day (C10 active, Step 1.5 / Ch.1):
    shelves C41/C42, anchor C39, King Nodes C43/C44, and the 1.0 targets become the fences C45/C46
    ('on gap-extended days, target outer credit fences C45/C46')."""
    g, sg, gap = plan["grid"], plan["strike_grid"], plan.get("gap") or {}
    if gap.get("active"):
        return {"mode": "gap", "C13": gap["c45"], "C14": gap["c41"], "C15": gap["c39"], "C16": gap["c42"], "C17": gap["c46"],
                "put_node": gap["c44"], "call_node": gap["c43"], "em": gap["c40"]}
    return {"mode": "standard", "C13": g["c13"], "C14": g["c14"], "C15": g["c15"], "C16": g["c16"], "C17": g["c17"],
            "put_node": sg["put_node"], "call_node": sg["call_node"], "em": g["c12"]}


# ── the whole replay, regime-gated ───────────────────────────────────────────
def rules_replay(spx5: pd.DataFrame, spy5: Optional[pd.DataFrame], qqq5: Optional[pd.DataFrame], grid: Dict[str, float],
                 em: float, put_node: float, call_node: float, c6: float) -> Dict:
    """Runs every archetype the regime allows, returns the qualifying trade (earliest trigger) plus the 'also checked' list.
    `grid` may be the standard set or the gap-day set from rule_levels()."""
    from core.workstation import eligible_archetypes
    el = eligible_archetypes(c6)
    levels = [grid["C17"], grid["C16"], grid["C15"], grid["C14"], grid["C13"]]
    results: Dict[int, Replay] = {}
    for a in (1, 2, 3, 4):
        if a not in el["valid"] and not (a == 2):          # A2 is checked in every regime (Ch.4: all regimes)
            continue
        if a == 1:
            results[1] = replay_a1(spx5, grid["C14"], grid["C15"], grid["C16"])
        elif a == 2:
            results[2] = replay_a2(spx5, put_node, call_node)
        elif a == 3:
            results[3] = replay_a3(spx5, spy5, qqq5, em, levels)
        else:
            results[4] = replay_a4(spx5, grid["C13"], grid["C14"], grid["C16"], grid["C17"])
    qualified = [r for r in results.values() if r.qualified]
    chosen = min(qualified, key=lambda r: r.trigger_time) if qualified else None
    also = []
    for a in (1, 2, 3, 4):
        if a in results:
            r = results[a]
            if chosen is not None and r is chosen:
                continue
            if r.qualified:
                also.append(f"Archetype {a} also qualified later ({r.trigger_time}) — one setup per session, the earlier trigger stands.")
            elif a == 2:
                also.append(r.not_qualified_reason + ".")
            else:
                also.append(f"Archetype {a} did not qualify: {r.not_qualified_reason}.")
        else:
            need = {1: "needs VIX under 15", 3: "needs VIX at or above 15", 4: "needs VIX above 18.5"}[a]
            also.append(f"Not eligible at VIX {c6:.2f}: Archetype {a} ({need}).")
    return {"chosen": chosen, "results": results, "also_checked": also, "eligible": el}


# ── live scanner: what qualifies right now on the current bars ───────────────
def live_status(spx5: pd.DataFrame, spy5, qqq5, grid: Dict[str, float], em: float, put_node: float, call_node: float,
                c6: float) -> Dict:
    """Same machinery as the replay, run on today's bars so far; also reports proximity to the trigger zones."""
    out = rules_replay(spx5, spy5, qqq5, grid, em, put_node, call_node, c6)
    bars = session_bars(spx5)
    if bars.empty:
        out["proximity"] = {}
        return out
    last = float(bars["close"].iloc[-1])
    out["proximity"] = {
        "put_node": round(last - put_node, 2), "call_node": round(call_node - last, 2),
        "C16": round(last - grid["C16"], 2), "C14": round(grid["C14"] - last, 2),
        "C17": round(last - grid["C17"], 2), "C13": round(grid["C13"] - last, 2),
        "last": last, "last_time": bars.index[-1].strftime("%H:%M"),
    }
    return out
