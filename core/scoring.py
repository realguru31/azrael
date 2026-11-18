"""
scoring.py — the desk's live-idea score, out of 10, with the per-check definitions the desk now publishes on every ticket.

Calibrated against the rubrics printed in #live-trade-ideas (Oct 8, 16, 19, 20, 21, 23, 26; Nov 6, 9, 10 — 11 blocks).
Each check is 1 / 0.5 / 0. A ticket needs 4.0; a B-grade setup (posted after 10:45 if nothing qualified) needs 3.0.
Reward and Reach are measured again at the send price/time. Send rules (Scenario Book): ≥ 7.5 at the bar close; 6–7 wait
≤ 2 bars; 4–5.5 wait ≤ 4 bars for a 1-minute close 0.25R in its direction; dropped if the invalidation prints or price runs
0.5R past the trigger close; nothing sent after the 11:05 close.

Published examples and the thresholds they pin (pts = SPX points, EM = the day's expected move):
  Regime   distance inside the day's VIX band: 0.09→0, 0.39→0, 0.57→½, 0.71→½, 1.16→1, 1.28→1 …  ⇒ ≥1.0 → 1 · ≥0.5 → ½
  Open     |open − anchor| in EM: 0.02→1, 0.13→1, 0.14→1, 0.17→½, 0.30→½, 0.48→½, 0.61→0          ⇒ ≤0.15 → 1 · ≤0.50 → ½
  Trigger  S3 close outside the box / S4 second close past the shelf, in EM: 0.066→0, 0.077→0, 0.081→½, 0.097→½, 0.121→1, 0.134→1
           ⇒ ≥0.12 → 1 · ≥0.08 → ½
  Structure S3 box width in EM: 0.113→½, 0.123→0, 0.143→0 ⇒ ≤0.10 → 1 · ≤0.12 → ½ ; S4 second close beyond the first, in EM:
           −0.029→0, 0.022→½, 0.056→1, 0.066→1 ⇒ ≥0.05 → 1 · >0 → ½
  SPY and QQQ weaker of the two moves with the idea: 0.039→0, 0.061→½, 0.072→½, 0.092→½, 0.120→1 ; any against → 0
           ⇒ ≥0.10 % → 1 · ≥0.05 % → ½
  Volume   SPY bar volume ÷ its 10-session median for that bar: 1.30→0, 1.38→0, 1.57→½, 1.75→½ ⇒ ≥2.0× → 1 · ≥1.5× → ½
  VIX      VIX move with the idea over 3 bars: 0.08→0, 0.10→½, 0.15→½, 0.41→1 ⇒ ≥0.25 → 1 · ≥0.10 → ½ (VIXY % proxy when VIX bars are missing)
  Reward   target distance in R: 1.08→0, 1.67→0, 2.23→½, 2.87→½, 3.12→1 ⇒ ≥3R → 1 · ≥2R → ½
  Reach    target distance ÷ pts left to 11:30 (= EM × √(minutes left ÷ 390)): 0.38→1, 0.64→1, 0.78→½, 0.95→½, 1.26→0 ⇒ ≤0.70 → 1 · ≤1.0 → ½
  Path     no mapped level before the target → 1 (a level within one strike of the entry or the target is that level, not an obstacle)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

import pandas as pd

from utils.timeutil import T_LAST_QUALIFYING, T_SHUTDOWN

MAX_SCORE = 10.0
FLOOR_A = 4.0
FLOOR_B = 3.0


@dataclass
class Check:
    name: str
    value: float
    note: str


@dataclass
class Scored:
    score: float
    checks: List[Check]
    send_rule: str
    status: str            # NOT_SENT | SENT | WAITING | DROPPED | EXPIRED | CUTOFF
    status_text: str
    sent_time: Optional[str] = None
    sent_price: Optional[float] = None
    r_pts: float = 0.0
    grade: str = "A"       # "A" ≥ 4.0 · "B" 3.0–3.5 (half size, own risk) · "none"

    def as_dict(self):
        d = asdict(self); d["checks"] = [asdict(c) for c in self.checks]; return d


def _band(c6: float) -> Tuple[str, float]:
    """The day's VIX band and how far inside it the 08:15 print sits (min distance to the band's edges)."""
    if c6 < 15:
        return "under 15", 15.0 - c6
    if c6 <= 18.5:
        return "15 to 18.5", min(c6 - 15.0, 18.5 - c6)
    return "above 18.5", c6 - 18.5


def _bar_at(df: Optional[pd.DataFrame], hh: int, mm: int):
    if df is None or df.empty:
        return None
    b = df[(df.index.hour == hh) & (df.index.minute == mm)]
    return b.iloc[0] if not b.empty else None


def ten_checks(r, plan: Dict, lv: Dict[str, float], bars5: pd.DataFrame, spy5, qqq5, gate, vix5: Optional[pd.DataFrame],
               spy_hist5: Optional[pd.DataFrame] = None, at_price: Optional[float] = None, at_min: Optional[int] = None) -> List[Check]:
    """r = the qualifying Replay. at_price/at_min = the send price and minute (Reward and Reach are re-measured there)."""
    em = lv["em"]; c6 = plan["inputs"]["c6"]; anchor = lv["C15"]
    long = r.side == "long"; sign = 1.0 if long else -1.0
    out: List[Check] = []
    hh, mm = map(int, r.trigger_time.split(":"))
    trig_min = hh * 60 + mm
    px = at_price if at_price is not None else r.entry
    now_min = at_min if at_min is not None else trig_min + 5
    m = r.trigger_text or ""

    # 1 Regime
    band, inside = _band(c6)
    v = 1.0 if inside >= 1.0 else 0.5 if inside >= 0.5 else 0.0
    out.append(Check("Regime", v, f"VIX {c6:.2f} is {inside:.2f} inside the {band} band"))

    # 2 Open — how far the 09:30 open printed from the anchor, in EM
    open_px = plan.get("open_print") or (float(bars5["open"].iloc[0]) if bars5 is not None and not bars5.empty else None)
    if open_px is None:
        out.append(Check("Open", 0.0, "open print unavailable"))
    else:
        d = abs(open_px - anchor); fe = d / em if em else 9.0
        v = 1.0 if fe <= 0.15 else 0.5 if fe <= 0.50 else 0.0
        out.append(Check("Open", v, f"opened {d:.2f} pts {'above' if open_px >= anchor else 'below'} anchor ({fe:.2f} EM)"))

    # 3 Trigger / 4 Structure
    if r.archetype == 3:
        try:
            dist = float(m.split(" pts ")[0].split()[-1]); seg = m.split("box (")[1].split(")")[0].split(",")[0]
            a, b = [float(x) for x in seg.split(" to ")]; width = abs(b - a)
        except Exception:
            dist, width = None, None
        if dist is not None:
            fe = dist / em
            out.append(Check("Trigger", 1.0 if fe >= 0.12 else 0.5 if fe >= 0.08 else 0.0, f"closed {fe:.3f} EM outside box"))
        else:
            out.append(Check("Trigger", 0.0, "trigger distance unavailable"))
        if width is not None:
            fw = width / em
            out.append(Check("Structure", 1.0 if fw <= 0.10 else 0.5 if fw <= 0.12 else 0.0, f"box {width:.2f} pts wide ({fw:.3f} EM)"))
        else:
            out.append(Check("Structure", 0.0, "box width unavailable"))
    elif r.archetype == 4:
        try:
            c1 = float(m.split("(")[1].split(" ")[1].rstrip(",")); c2 = float(m.split(", ")[1].split(" ")[1].rstrip(");"))
            shelf = r.stop
            past2 = abs(c2 - shelf) / em; beyond = sign * (c2 - c1) / em
        except Exception:
            past2, beyond = None, None
        out.append(Check("Trigger", (1.0 if past2 >= 0.12 else 0.5 if past2 >= 0.08 else 0.0) if past2 is not None else 0.0,
                         f"second close {past2:.3f} EM past shelf" if past2 is not None else "unavailable"))
        out.append(Check("Structure", (1.0 if beyond >= 0.05 else 0.5 if beyond > 0 else 0.0) if beyond is not None else 0.0,
                         f"second close {beyond:+.3f} EM beyond first" if beyond is not None else "unavailable"))
    else:
        out.append(Check("Trigger", 0.0, "met at the written minimum (S1/S2 margins not published by the desk)"))
        out.append(Check("Structure", 0.5, "structure met; margin not measured for this page"))

    # 5 SPY and QQQ — move with the idea on the trigger bar (%), weaker of the two
    def _mv(df):
        b = _bar_at(df, hh, mm)
        if b is None:
            return None
        return sign * (float(b["close"]) - float(b["open"])) / float(b["open"]) * 100.0
    ms_, mq_ = _mv(spy5), _mv(qqq5)
    if ms_ is None or mq_ is None:
        out.append(Check("SPY and QQQ", 0.0, "SPY/QQQ bars unavailable"))
    else:
        weaker = min(ms_, mq_)
        v = 0.0 if weaker <= 0 else 1.0 if weaker >= 0.10 else 0.5 if weaker >= 0.05 else 0.0
        out.append(Check("SPY and QQQ", v, f"SPY {ms_:+.3f}%, QQQ {mq_:+.3f}% with idea"))

    # 6 Volume — SPY trigger-bar volume vs its 10-session median for that bar
    v, note = 0.0, "SPY volume history unavailable"
    src = spy_hist5 if spy_hist5 is not None else spy5
    if src is not None and not src.empty:
        same = src[(src.index.hour == hh) & (src.index.minute == mm)]
        same = same[same.index.date != same.index.date[-1]] if len(same) > 1 else same.iloc[0:0]
        tb = _bar_at(spy5, hh, mm)
        if tb is not None and len(same) >= 3 and float(same["volume"].median()) > 0:
            ratio = float(tb["volume"]) / float(same["volume"].median())
            v = 1.0 if ratio >= 2.0 else 0.5 if ratio >= 1.5 else 0.0
            note = f"SPY volume {ratio:.2f}x 10-session median"
    out.append(Check("Volume", v, note))

    # 7 VIX — move with the idea over the 3 bars into the trigger close
    v, note = 0.0, "VIX bars unavailable"
    if vix5 is not None and not vix5.empty:
        mins = vix5.index.hour * 60 + vix5.index.minute
        w = vix5[(mins <= trig_min) & (mins >= trig_min - 15)]
        if len(w) >= 2:
            d = float(w["close"].iloc[-1]) - float(w["close"].iloc[0])
            helps = d if not long else -d
            v = 1.0 if helps >= 0.25 else 0.5 if helps >= 0.10 else 0.0
            note = f"VIX moved {d:+.2f} {'with' if helps > 0 else 'against'} idea over 3 bars"
    out.append(Check("VIX", v, note))

    # 8 Reward — target distance in R at the send price
    risk = max(r.risk_pts, 1e-9)
    room = abs(r.target - px); rr = room / risk
    out.append(Check("Reward", 1.0 if rr >= 3.0 else 0.5 if rr >= 2.0 else 0.0, f"target {room:.2f} pts away = {rr:.2f}R"))

    # 9 Reach — target distance ÷ the move the day still prices to 11:30 (EM × √(minutes left ÷ 390))
    left_min = max(T_SHUTDOWN - now_min, 1)
    left_pts = em * math.sqrt(left_min / 390.0)
    ratio = room / left_pts if left_pts else 9.0
    out.append(Check("Reach", 1.0 if ratio <= 0.70 else 0.5 if ratio <= 1.0 else 0.0, f"{room:.2f} of {left_pts:.2f} pts left to 11:30 ({ratio:.2f})"))

    # 10 Path — mapped levels between the send price and the target (a level within one strike of either is that level)
    levels = {"+0.5 shelf": lv["C14"], "−0.5 shelf": lv["C16"], "call S2 level": lv["call_node"], "put S2 level": lv["put_node"],
              "+1.0 wall": lv["C13"], "−1.0 wall": lv["C17"], "middle": lv["C15"]}
    for k, val in (plan.get("gex_levels") or {}).items():
        if val:
            levels[k] = val
    lo_, hi_ = min(px, r.target), max(px, r.target)
    tol = 5.0
    inway = [k for k, val in levels.items() if val is not None and lo_ + tol < val < hi_ - tol]
    out.append(Check("Path", 0.0 if inway else 1.0, "no mapped level before the target" if not inway else "in the way: " + ", ".join(inway)))
    return out


def send_rule_for(score: float) -> Tuple[str, int]:
    if score < FLOOR_A:
        return "not sent", 0
    if score >= 7.5:
        return "at close", 0
    if score >= 6.0:
        return "wait 2 bars", 2
    return "wait 4 bars", 4


def live_status(r, score: float, spx1: Optional[pd.DataFrame], now_min: int) -> Tuple[str, str, Optional[str], Optional[float]]:
    """1-minute index closes after the trigger bar closed → sent / waiting / dropped, in the desk's words."""
    from datetime import timedelta as _td
    rule, max_bars = send_rule_for(score)
    risk = max(r.risk_pts, 1e-9); long = r.side == "long"; sign = 1.0 if long else -1.0
    hh, mm = map(int, r.trigger_time.split(":")); bar_close_min = hh * 60 + mm + 5
    if rule == "not sent":
        return "NOT_SENT", f"score {score:.1f} < {FLOOR_A:.1f} — not sent", None, None
    if bar_close_min > T_LAST_QUALIFYING:
        return "CUTOFF", "after the 11:05 close — nothing is sent", None, None
    if rule == "at close":
        return "SENT", f"score {score:.1f} ≥ 7.5 — sent at the bar close {r.entry:,.2f}", f"{bar_close_min // 60:02d}:{bar_close_min % 60:02d}", r.entry
    deadline = bar_close_min + 5 * max_bars
    if spx1 is None or spx1.empty:
        return "WAITING", f"score {score:.1f} — waiting up to {max_bars} bars for a 1-min close 0.25R ({0.25 * risk:.2f} pts) in its direction", None, None
    mins = spx1.index.hour * 60 + spx1.index.minute
    after = spx1[(mins >= bar_close_min) & (mins <= min(deadline, T_LAST_QUALIFYING + 25))]
    for ts0, row in after.iterrows():
        ts = ts0 + _td(minutes=1); c = float(row["close"]); moved = sign * (c - r.entry)
        inval = (c <= r.stop) if long else (c >= r.stop)
        if inval:
            return "DROPPED", f"dropped — the {ts:%H:%M} close {c:,.2f} printed the invalidation while waiting", None, None
        if moved > 0.5 * risk:
            return "DROPPED", f"dropped — the {ts:%H:%M} close {c:,.2f} ran {moved:.2f} pts past the trigger close, more than 0.5R ({0.5 * risk:.2f})", None, None
        if moved >= 0.25 * risk:
            if ts.hour * 60 + ts.minute > T_LAST_QUALIFYING:
                return "CUTOFF", f"confirmed at {ts:%H:%M} but after the 11:05 close — nothing is sent", None, None
            return "SENT", f"scored {score:.1f} at the trigger close and confirmed +0.25R at {ts:%H:%M} ({c:,.2f})", f"{ts:%H:%M}", c
    if now_min > deadline:
        return "EXPIRED", f"dropped — no 1-min close 0.25R in its direction within {max_bars} bars", None, None
    left = max(0, -(-(deadline - now_min) // 5))
    return "WAITING", f"score {score:.1f} — waiting, {left} bar{'s' if left != 1 else ''} left for a 1-min close 0.25R ({0.25 * risk:.2f} pts) in its direction", None, None


def score_idea(r, plan: Dict, lv: Dict[str, float], bars5: pd.DataFrame, spy5, qqq5, gate, vix5: Optional[pd.DataFrame],
               spx1: Optional[pd.DataFrame], now_min: int, spy_hist5: Optional[pd.DataFrame] = None) -> Scored:
    checks = ten_checks(r, plan, lv, bars5, spy5, qqq5, gate, vix5, spy_hist5)
    score = min(MAX_SCORE, round(sum(c.value for c in checks) * 2) / 2)
    rule, _ = send_rule_for(score)
    status, text, st_t, st_p = live_status(r, score, spx1, now_min)
    if status == "SENT" and st_p is not None and st_t:
        # Reward and Reach are measured again at the send price
        hh, mm = map(int, st_t.split(":"))
        checks = ten_checks(r, plan, lv, bars5, spy5, qqq5, gate, vix5, spy_hist5, at_price=st_p, at_min=hh * 60 + mm)
        score = min(MAX_SCORE, round(sum(c.value for c in checks) * 2) / 2)
    grade = "A" if score >= FLOOR_A else "B" if score >= FLOOR_B else "none"
    return Scored(score, checks, rule, status, text, st_t, st_p, r.risk_pts, grade)
