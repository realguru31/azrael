"""
scoring.py — the desk's live-idea layer from THE SCENARIO BOOK (pinned in #live-trade-ideas), laid over the book trade.

The book gives the skeleton: ten checks (Regime, Open, Trigger, Structure, SPY and QQQ, Volume, VIX, Reward, Reach, Path)
scored 1 / 0.5 / 0, "meeting a rule at its bare minimum scores 0", under 4.0 nothing is sent, maximum 9.5, and the send
rules by score. It does NOT publish what earns 1 vs 0.5 on each check — the definitions below are the app's, written to
be strict and visible, and they reproduce the two posted scores we have (S3 on Oct 2 and Oct 6: both 4.0) under the
volume / VIX values recorded for those days. Treat every check's note as the thing to compare with the desk.

Send rules (verbatim from the book):
  7.5 or higher: at the bar close. 6 to 7: can wait up to 2 bars, 4 to 5.5 up to 4 bars, for a 1-minute close 0.25R in
  its direction. A waiting idea is dropped if the invalidation prints or price runs 0.5R past the trigger close.
  Nothing is sent after the 11:05 close.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import time
from typing import Dict, List, Optional, Tuple

import pandas as pd

from utils.timeutil import T_LAST_QUALIFYING

PAGE_VIX = {1: (0.0, 15.0), 2: (15.0, 18.5), 3: (15.0, 99.0), 4: (18.5, 99.0)}
MAX_SCORE = 9.5


@dataclass
class Check:
    name: str
    value: float          # 1, 0.5 or 0
    note: str


@dataclass
class Scored:
    score: float
    checks: List[Check]
    send_rule: str        # "at close" | "wait 2 bars" | "wait 4 bars" | "not sent"
    status: str           # NOT_SENT | SENT | WAITING | DROPPED | EXPIRED | CUTOFF
    status_text: str
    sent_time: Optional[str] = None
    sent_price: Optional[float] = None
    r_pts: float = 0.0

    def as_dict(self):
        d = asdict(self); d["checks"] = [asdict(c) for c in self.checks]; return d


def _v(x: Optional[float]) -> float:
    return 0.0 if x is None else float(x)


def ten_checks(r, plan: Dict, lv: Dict[str, float], bars5: pd.DataFrame, spy5: Optional[pd.DataFrame], qqq5: Optional[pd.DataFrame],
               gate, vix_now: Optional[float]) -> List[Check]:
    """r = the qualifying Replay (book trade). Each check: 1 / 0.5 / 0 with a one-line note."""
    em = lv["em"]
    c6 = plan["inputs"]["c6"]
    long = r.side == "long"
    sign = 1.0 if long else -1.0
    out: List[Check] = []

    # 1 Regime — how far inside the page's VIX range the 08:15 print sat (an edge reading is a bare minimum = 0)
    lo, hi = PAGE_VIX.get(r.archetype, (0.0, 99.0))
    inside = min(c6 - lo, (hi - c6) if hi < 99 else 99.0)
    val = 1.0 if inside >= 2.0 else 0.5 if inside >= 1.0 else 0.0
    out.append(Check("Regime", val, f"VIX {c6:.2f} is {inside:.2f} inside the page's range [{lo:g}, {hi if hi < 99 else '∞'})"))

    # 2 Open — the 09:50 verdict relative to the trade's direction
    if gate is None or gate.status not in ("acceptance", "trap"):
        out.append(Check("Open", 0.0, "no 09:50 verdict"))
    else:
        aligned = (gate.status == "acceptance" and ((gate.direction > 0) == long)) or (gate.status == "trap" and ((gate.direction > 0) != long))
        out.append(Check("Open", 0.5 if aligned else 0.0, f"09:50 {gate.status} {'with' if aligned else 'against'} the trade's direction"))

    # 3 Trigger — margin over the minimum trigger distance
    m = r.trigger_text or ""
    try:
        dist = float(m.split(" pts ")[0].split()[-1])            # "SPX closed the 10:50 bar at 7738.45, 4.13 pts below…"
    except Exception:
        dist = None
    if r.archetype == 3 and dist is not None:
        mn = 0.05 * em
        ratio = dist / mn if mn else 0.0
        val = 1.0 if ratio >= 2.0 else 0.5 if ratio >= 1.5 else 0.0
        out.append(Check("Trigger", val, f"close {dist:.2f} pts outside the box vs minimum {mn:.2f} ({ratio:.2f}×)"))
    else:
        out.append(Check("Trigger", 0.0, "trigger met at the written minimum"))

    # 4 Structure — quality of the structure the page is built on (S3: box width vs the 0.2 EM maximum)
    if r.archetype == 3 and "box (" in m:
        try:
            seg = m.split("box (")[1].split(")")[0].split(",")[0]          # "7742.58 to 7754.67"
            a, b = [float(x) for x in seg.split(" to ")]
            width = abs(b - a); mx = 0.2 * em; frac = width / mx if mx else 1.0
            val = 1.0 if frac <= 0.5 else 0.5 if frac <= 0.75 else 0.0
            out.append(Check("Structure", val, f"box {width:.2f} pts wide = {frac:.2f} of the 0.2 EM maximum ({mx:.2f})"))
        except Exception:
            out.append(Check("Structure", 0.0, "box width unavailable"))
    else:
        out.append(Check("Structure", 0.5, "structure met with margin not measured for this page"))

    # 5 SPY and QQQ — margin of their own breaks (S3) or alignment (other pages)
    if r.archetype == 3:
        try:
            spy_part = m.split("SPY ")[1].split(";")[0]          # "770.94 closed below its box low (771.30)"
            qqq_part = m.split("QQQ ")[1].split(" on the same bar")[0]
            def margin(part):
                px = float(part.split()[0]); lvl = float(part.split("(")[1].split(")")[0])
                return abs(px - lvl) / lvl * 100.0
            ms_, mq_ = margin(spy_part), margin(qqq_part)
            both = min(ms_, mq_)
            val = 1.0 if both >= 0.10 else 0.5 if both >= 0.05 else 0.0
            out.append(Check("SPY and QQQ", val, f"SPY {ms_:.3f} % and QQQ {mq_:.3f} % beyond their own boxes (weaker {both:.3f} %)"))
        except Exception:
            out.append(Check("SPY and QQQ", 0.5, "both confirmed; margins unavailable"))
    else:
        out.append(Check("SPY and QQQ", 0.5, "not a three-ticker page"))

    # 6 Volume — the trigger bar vs the four bars before it (SPY volume; the index prints none)
    vol_val, vol_note = 0.0, "no volume feed"
    src = spy5 if (spy5 is not None and not spy5.empty) else bars5
    try:
        hh, mm = map(int, r.trigger_time.split(":"))
        tb = src[(src.index.hour == hh) & (src.index.minute == mm)]
        if not tb.empty:
            i = src.index.get_loc(tb.index[0])
            prev = src.iloc[max(0, i - 4):i]["volume"]
            if len(prev) >= 2 and prev.mean() > 0 and float(tb["volume"].iloc[0]) > 0:
                ratio = float(tb["volume"].iloc[0]) / float(prev.mean())
                vol_val = 1.0 if ratio >= 1.5 else 0.5 if ratio >= 1.2 else 0.0
                vol_note = f"trigger-bar volume {ratio:.2f}× the prior four bars"
    except Exception:
        pass
    out.append(Check("Volume", vol_val, vol_note))

    # 7 VIX — the move in VIX since 08:15, with the trade (puts want VIX up, calls want VIX down)
    if vix_now is None:
        out.append(Check("VIX", 0.0, "VIX now unavailable"))
    else:
        d = vix_now - c6
        helps = (-d) if long else d
        val = 1.0 if helps >= 0.30 else 0.5 if helps >= 0.10 else 0.0
        out.append(Check("VIX", val, f"VIX {vix_now:.2f} vs 08:15 {c6:.2f} ({d:+.2f}) — {'with' if helps > 0 else 'against'} the trade"))

    # 8 Reward — room to the target in R (the minimum is 8 pts of room)
    risk = max(r.risk_pts, 1e-9)
    room = abs(r.target - r.entry)
    rr = room / risk
    val = 1.0 if rr >= 4.0 else 0.5 if rr >= 2.5 else 0.0
    out.append(Check("Reward", val, f"{room:.2f} pts to the target = {rr:.2f}R"))

    # 9 Reach — how much of the expected move the target asks for
    frac = room / em if em else 1.0
    val = 1.0 if frac <= 0.30 else 0.5 if frac <= 0.50 else 0.0
    out.append(Check("Reach", val, f"target {frac:.2f} EM from the entry"))

    # 10 Path — mapped levels between the entry and the target
    levels = {"+0.5 shelf": lv["C14"], "−0.5 shelf": lv["C16"], "call node": lv["call_node"], "put node": lv["put_node"],
              "+1.0 wall": lv["C13"], "−1.0 wall": lv["C17"], "anchor": lv["C15"]}
    sc = plan.get("stop_clusters", {}) or {}
    minor = {"pre-mkt high": sc.get("pre_market_high"), "pre-mkt low": sc.get("pre_market_low"),
             "prior high": sc.get("prior_session_high"), "prior low": sc.get("prior_session_low")}
    lo_, hi_ = min(r.entry, r.target), max(r.entry, r.target)
    tol = 0.5
    majors = [k for k, v in levels.items() if v is not None and lo_ + tol < v < hi_ - tol]
    minors = [k for k, v in minor.items() if v is not None and lo_ + tol < v < hi_ - tol]
    val = 0.0 if majors else 0.5 if minors else 1.0
    out.append(Check("Path", val, "clear to the target" if not (majors or minors) else "in the way: " + ", ".join(majors + minors)))
    return out


def send_rule_for(score: float) -> Tuple[str, int]:
    if score < 4.0:
        return "not sent", 0
    if score >= 7.5:
        return "at close", 0
    if score >= 6.0:
        return "wait 2 bars", 2
    return "wait 4 bars", 4


def live_status(r, score: float, spx1: Optional[pd.DataFrame], now_min: int) -> Tuple[str, str, Optional[str], Optional[float]]:
    """Walk the 1-minute index closes after the trigger bar closed. Returns (status, text, sent_time, sent_price)."""
    rule, max_bars = send_rule_for(score)
    risk = max(r.risk_pts, 1e-9)
    long = r.side == "long"
    sign = 1.0 if long else -1.0
    hh, mm = map(int, r.trigger_time.split(":"))
    bar_close_min = hh * 60 + mm + 5
    if rule == "not sent":
        return "NOT_SENT", f"score {score:.1f} < 4.0 — not sent", None, None
    if bar_close_min > T_LAST_QUALIFYING:
        return "CUTOFF", "after the 11:05 close — nothing is sent", None, None
    if rule == "at close":
        return "SENT", f"score {score:.1f} ≥ 7.5 — sent at the bar close {r.entry:,.2f}", f"{(bar_close_min // 60):02d}:{(bar_close_min % 60):02d}", r.entry
    deadline = bar_close_min + 5 * max_bars
    if spx1 is None or spx1.empty:
        return "WAITING", f"score {score:.1f} — waiting up to {max_bars} bars for a 1-min close 0.25R ({0.25 * risk:.2f} pts) in its direction", None, None
    mins = spx1.index.hour * 60 + spx1.index.minute
    after = spx1[(mins >= bar_close_min) & (mins <= min(deadline, T_LAST_QUALIFYING + 25))]
    for ts, row in after.iterrows():
        c = float(row["close"]); moved = sign * (c - r.entry)
        inval = (c <= r.stop) if long else (c >= r.stop)
        if inval:
            return "DROPPED", f"dropped — the {ts:%H:%M} close {c:,.2f} printed the invalidation while waiting", None, None
        if moved > 0.5 * risk:
            return "DROPPED", f"dropped — the {ts:%H:%M} close {c:,.2f} ran {moved:.2f} pts past the trigger close, more than 0.5R ({0.5 * risk:.2f})", None, None
        if moved >= 0.25 * risk:
            m_ = ts.hour * 60 + ts.minute
            if m_ > T_LAST_QUALIFYING:
                return "CUTOFF", f"confirmed at {ts:%H:%M} but after the 11:05 close — nothing is sent", None, None
            return "SENT", f"score {score:.1f} — sent {ts:%H:%M} at {c:,.2f} after a 1-min close 0.25R in its direction", f"{ts:%H:%M}", c
    if now_min > deadline:
        return "EXPIRED", f"dropped — no 1-min close 0.25R in its direction within {max_bars} bars", None, None
    left = max(0, (deadline - now_min) // 5 + (1 if (deadline - now_min) % 5 else 0))
    return "WAITING", f"score {score:.1f} — waiting, {left} bar{'s' if left != 1 else ''} left for a 1-min close 0.25R ({0.25 * risk:.2f} pts) in its direction", None, None


def score_idea(r, plan: Dict, lv: Dict[str, float], bars5: pd.DataFrame, spy5, qqq5, gate, vix_now: Optional[float],
               spx1: Optional[pd.DataFrame], now_min: int) -> Scored:
    checks = ten_checks(r, plan, lv, bars5, spy5, qqq5, gate, vix_now)
    score = min(MAX_SCORE, round(sum(c.value for c in checks) * 2) / 2)
    rule, _ = send_rule_for(score)
    status, text, st_t, st_p = live_status(r, score, spx1, now_min)
    return Scored(score, checks, rule, status, text, st_t, st_p, r.risk_pts)
