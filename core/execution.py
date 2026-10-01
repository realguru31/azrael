"""
execution.py — the TRADE OPPORTUNITY banner. Pure logic: plan + today's bars + scanner state -> what to do right now,
in order-ticket language, with the desk's state machine:

    PREMARKET  provisional map, locks 08:30         LOCKED     plan locked, nothing until the 09:50 gate
    GATE       09:30–09:50 no trades                 WATCHING   waiting for a qualifying 5-minute close
    ARMED      price is at a trigger zone            TRIGGERED / ACTIVE   the one setup, live R
    DONE       target, stop or 11:30 flat            STAND_DOWN no qualifying bar closed by 11:05 — Watch Day
    SHUTDOWN   11:30–16:00 dead zone                 SETTLE     16:00+, run the audit
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

import pandas as pd

from core import credit as CR
from core import workstation as ws
from core.rules import session_bars
from utils.timeutil import (T_MATH, T_OPEN, T_GATE_END, T_PRIMARY_END, T_LAST_QUALIFYING, T_SHUTDOWN, T_CLOSE, fmt_hm)

ARM_DISTANCE = 10.0     # points from a trigger level at which a play is 'armed'


@dataclass
class Play:
    archetype: int
    side: str                 # "LONG CALLS" | "LONG PUTS"
    title: str
    condition: str
    entry: str
    stop: str
    target: str
    status: str               # "watch" | "armed" | "blocked"
    status_text: str
    distance: Optional[float] = None

    def as_dict(self):
        return asdict(self)


@dataclass
class Banner:
    state: str
    tone: str                 # neutral | wait | go | active | done | bad
    headline: str
    sub: str
    plays: List[Play]
    credit: str
    notes: List[str] = field(default_factory=list)

    def as_dict(self):
        d = asdict(self); d["plays"] = [p.as_dict() for p in self.plays]; return d


def _f(x: Optional[float]) -> str:
    return "—" if x is None else f"{x:,.2f}"


def _box(bars: pd.DataFrame, n: int = 4):
    done = bars.iloc[:-1] if len(bars) > 1 else bars          # completed bars only
    b = done.tail(n)
    if len(b) < n:
        return None
    return float(b["low"].min()), float(b["high"].max())


def plays_for(plan: Dict, lv: Dict[str, float], bars: pd.DataFrame, last: Optional[float], sizing: Dict) -> List[Play]:
    """The concrete directional plays the regime allows today, with live arming."""
    reg, el = plan["regime"], plan["eligible"]["valid"]
    em = lv["em"]
    c13, c14, c15, c16, c17 = lv["C13"], lv["C14"], lv["C15"], lv["C16"], lv["C17"]
    pn, cn = lv["put_node"], lv["call_node"]
    rb = session_bars(bars) if bars is not None else pd.DataFrame()
    sess_hi = float(rb["high"].max()) if not rb.empty else None
    sess_lo = float(rb["low"].min()) if not rb.empty else None
    n_ct = sizing.get("c29", 0)
    size_txt = f"{n_ct} contract{'s' if n_ct != 1 else ''} at Δ {sizing.get('c28', 0.55):.2f} ({sizing.get('c27', 8):.0f}-pt stop)" if n_ct else "0 contracts at this stop — tighter structural stop or stand aside"
    out: List[Play] = []

    def arm(dist: Optional[float], blocked: str = "") -> (str, str):
        if blocked:
            return "blocked", blocked
        if dist is None:
            return "watch", "waiting for bars"
        if abs(dist) <= ARM_DISTANCE:
            return "armed", f"price {dist:+.2f} pts from the trigger level — ARMED, wait for the qualifying 5-minute close"
        return "watch", f"price {dist:+.2f} pts from the trigger level"

    # Archetype 2 — every regime (favoured in Balanced)
    if 2 in el or reg == 3:
        fall = (sess_hi - pn) if sess_hi is not None else None
        st, tx = arm((last - pn) if last is not None else None)
        if fall is not None and fall < 15:
            tx += f" · displacement so far {fall:.1f} pts (needs ≥ 15 from the session high)"
        elif fall is not None:
            tx += f" · displacement {fall:.1f} pts OK → target ≈ {pn + fall / 2:,.2f}"
        out.append(Play(2, "LONG CALLS", f"King-node fade at the put node {pn:,.0f}",
                        f"SPX falls ≥ 15 pts into {pn:,.0f} after 09:50 and a 5-minute bar closes back above it with a lower wick over half its range",
                        "the close of that bar", f"5-minute close below {pn - 5:,.0f}, or two closes below {pn:,.0f}",
                        "half the fall back (then the next shelf)", st, tx, (last - pn) if last is not None else None))
        rise = (cn - sess_lo) if sess_lo is not None else None
        st, tx = arm((cn - last) if last is not None else None)
        if rise is not None and rise < 15:
            tx += f" · displacement so far {rise:.1f} pts (needs ≥ 15 from the session low)"
        elif rise is not None:
            tx += f" · displacement {rise:.1f} pts OK → target ≈ {cn - rise / 2:,.2f}"
        out.append(Play(2, "LONG PUTS", f"King-node fade at the call node {cn:,.0f}",
                        f"SPX rises ≥ 15 pts into {cn:,.0f} after 09:50 and a 5-minute bar closes back below it with an upper wick over half its range",
                        "the close of that bar", f"5-minute close above {cn + 5:,.0f}, or two closes above {cn:,.0f}",
                        "half the rise back (then the next shelf)", st, tx, (cn - last) if last is not None else None))
    # Archetype 1 — Positive only
    if 1 in el:
        st, tx = arm((last - c16) if last is not None else None)
        out.append(Play(1, "LONG CALLS", f"Half-EM fade at the −0.5 shelf {c16:,.2f}",
                        "probe within 3–5 pts of the shelf, two consecutive 5-minute closes hold, the third reverses toward the anchor on higher volume",
                        "the close of the reversal bar", f"5-minute close below {c16 - 8:,.2f}", f"anchor {c15:,.2f} (exit within 3 pts, 100 %)", st, tx))
        st, tx = arm((c14 - last) if last is not None else None)
        out.append(Play(1, "LONG PUTS", f"Half-EM fade at the +0.5 shelf {c14:,.2f}",
                        "probe within 3–5 pts of the shelf, two consecutive 5-minute closes hold, the third reverses toward the anchor on higher volume",
                        "the close of the reversal bar", f"5-minute close above {c14 + 8:,.2f}", f"anchor {c15:,.2f} (exit within 3 pts, 100 %)", st, tx))
    # Archetype 3 — Balanced / Negative
    if 3 in el:
        box = _box(rb) if not rb.empty else None
        if box:
            lo, hi = box
            w = hi - lo
            ok = w <= 0.2 * em
            ups = sorted(x for x in (c13, c14, c15, c16, c17) if x > hi + 0.05 * em)
            dns = sorted((x for x in (c13, c14, c15, c16, c17) if x < lo - 0.05 * em), reverse=True)
            tgt_up = ups[0] if ups else None
            tgt_dn = dns[0] if dns else None
            cond_txt = (f"current 20-minute box {lo:,.2f}–{hi:,.2f} ({w:.2f} pts{' OK' if ok else ' — too wide, needs ≤ ' + f'{0.2 * em:.2f}'}). "
                        f"Break: 5-minute close ≥ {hi + 0.05 * em:,.2f} (long) or ≤ {lo - 0.05 * em:,.2f} (short), SPY and QQQ outside their own boxes on the same bar")
            st, tx = arm(min(abs(last - hi), abs(last - lo)) if last is not None else None, "" if ok else "box too wide for the rule")
            out.append(Play(3, "LONG CALLS / LONG PUTS", "3-ticker breakout of the 20-minute box", cond_txt, "the close of the breakout bar",
                            "5-minute close back inside the box (long: below the box high; short: above the box low)",
                            f"next EM level: up {_f(tgt_up)} / down {_f(tgt_dn)} (needs > 8 pts of room)", st, tx))
        else:
            out.append(Play(3, "LONG CALLS / LONG PUTS", "3-ticker breakout of the 20-minute box",
                            f"all three close outside their last 20-minute box; SPX box ≤ {0.2 * em:.2f} pts, close ≥ {0.05 * em:.2f} outside, > 8 pts room to the next level",
                            "the close of the breakout bar", "5-minute close back inside the box", "the next EM level", "watch", "waiting for four completed bars"))
    # Archetype 4 — Negative only
    if 4 in el:
        st, tx = arm((c14 - last) if last is not None else None)
        out.append(Play(4, "LONG CALLS", f"1.0-EM runner through the +0.5 shelf {c14:,.2f}",
                        "two consecutive 5-minute closes above the shelf (the first on above-average volume), the next bar does not snap back",
                        "the open of the second candle following acceptance", f"5-minute close back below {c14:,.2f}", f"+1.0 wall {c13:,.2f} on first contact, 100 %", st, tx))
        st, tx = arm((last - c16) if last is not None else None)
        out.append(Play(4, "LONG PUTS", f"1.0-EM runner through the −0.5 shelf {c16:,.2f}",
                        "two consecutive 5-minute closes below the shelf (the first on above-average volume), the next bar does not snap back",
                        "the open of the second candle following acceptance", f"5-minute close back above {c16:,.2f}", f"−1.0 wall {c17:,.2f} on first contact, 100 %", st, tx))
    for p in out:
        p.entry = p.entry + f" · {size_txt}"
    return out


def credit_line(plan: Dict, chain: Optional[pd.DataFrame]) -> str:
    g, sg, gap, c6, c19 = plan["grid"], plan["strike_grid"], plan["gap"], plan["inputs"]["c6"], plan["sizing"]["c19"]
    grid = CR.meic_grid(g["c13"], g["c17"], gap["c45"], gap["c46"], gap["active"], c6, c19, chain)
    proto = grid["protocol"]
    if not proto["allowed"]:
        return f"CREDIT SPREADS: NONE — VIX {c6:.2f} > 22 circuit breaker."
    bc, bp = grid["bear_call"], grid["bull_put"]
    def leg(L, name):
        s = f"{name} {L['short']:,.0f}/{L['long']:,.0f}"
        if L.get("credit") is not None:
            s += f" credit ≈ {L['credit']:.2f} → {L['contracts_1r']} ct"
        return s
    fence_txt = f"fences {sg['put_fence']:,.0f}P / {sg['call_fence']:,.0f}C" + (f" · gap fences C45/C46 {gap['c45']:,.0f}/{gap['c46']:,.0f}" if gap["active"] else "")
    if plan["regime"] == 1:
        head = "MEIC IRON CONDOR (premier regime, full 1R): "
        body = leg(bc, "bear call") + " + " + leg(bp, "bull put")
        if grid.get("condor"):
            body += f" · condor credit ≈ {grid['condor']['credit']:.2f}, {grid['condor']['contracts_1r']} ct"
        tail = " · 0DTE if the overnight inventory is balanced."
    elif plan["regime"] == 2:
        head = "SINGLE-SIDED CREDIT SPREAD (0.75R, side = morning bias): "
        body = leg(bc, "bear call") + " or " + leg(bp, "bull put")
        tail = " · viable after 11:30 once price confirms a range between the nodes; never between the nodes on a two-way day."
    else:
        head = "DIRECTIONAL SPREAD ONLY (condors banned, 0.5R, 15–20 wide): "
        body = leg(bc, "bear call") + " or " + leg(bp, "bull put")
        tail = " · do not sell unhedged gamma on an out-of-bounds gap."
    from data import fetcher as _F
    return head + body + f" · {fence_txt}" + tail + (f" (mids: {_F.chain_source()['note']})" if chain is not None else " (no chain mids)")


def banner(plan: Dict, lv: Dict[str, float], bars: pd.DataFrame, last: Optional[float], now_min: int, gate, live: Optional[Dict],
           chain: Optional[pd.DataFrame], locked: bool) -> Banner:
    sizing = plan["sizing"]
    plays = plays_for(plan, lv, bars, last, sizing)
    if now_min < T_GATE_END:                      # nothing can be taken before 09:50 — show distances, never 'armed'
        for p in plays:
            if p.status == "armed":
                p.status, p.status_text = "watch", p.status_text.replace(" — ARMED, wait for the qualifying 5-minute close", " (arms after the 09:50 gate)")
    cred = credit_line(plan, chain)
    notes: List[str] = []
    c7 = plan["inputs"].get("c7")
    if c7 is not None and abs(c7) >= 0.75 and not plan["gap"]["active"]:
        notes.append(f"GAP DAY LIKELY (/ES {c7:+.2f} %): never fade the open; at 09:31 enter the 09:30 cash open in C10 and trade the re-anchored brackets.")
    if plan["gap"]["active"]:
        notes.append(f"RE-ANCHOR ACTIVE: plays use C41 {lv['C14']:,.2f} / C42 {lv['C16']:,.2f}, nodes C43 {lv['call_node']:,.0f} / C44 {lv['put_node']:,.0f}, fences C45/C46.")
    reg_name = ws.REGIME_SHORT[plan["regime"]]
    fav = {1: "Archetype 1 (Half-EM fade)", 2: "Archetype 2 (King Node absorption)", 3: "Archetype 4 (1.0-EM runner)"}[plan["regime"]]

    if now_min < T_MATH and not locked:
        return Banner("PREMARKET", "neutral", "PRE-MARKET — provisional map", f"{reg_name}. Locks at 08:30 (in {T_MATH - now_min} min). Favoured: {fav}.",
                      plays, cred, notes)
    if now_min < T_OPEN:
        return Banner("LOCKED", "wait", "PLAN LOCKED — nothing until the 09:50 gate",
                      f"{reg_name}. Favoured: {fav}. Post the card before 09:25; set the timer at 09:25.", plays, cred, notes)
    if now_min < T_GATE_END:
        g = f" · initial move {'UP' if gate.direction > 0 else 'DOWN'} from the open {gate.open_print:,.2f}" if gate and gate.open_print else ""
        return Banner("GATE", "bad", f"DISCOVERY GATE — NO TRADES · verdict at 09:50 (in {T_GATE_END - now_min} min)",
                      f"{reg_name}{g}. Acceptance → momentum plays; trap → fades.", plays, cred, notes)
    chosen = live.get("chosen") if live else None
    if chosen is not None:
        r = chosen
        n_ct = sizing.get("c29", 0)
        base = (f"ARCHETYPE {r.archetype} {('LONG CALLS' if r.side == 'long' else 'LONG PUTS')} · triggered {r.trigger_time} at {r.entry:,.2f} · "
                f"stop {r.stop:,.2f} (5-minute close) · target {r.target:,.2f} · risk {r.risk_pts:.2f} pts = 1R · {n_ct} contracts")
        if r.resolution in (None, "open"):
            pnl = (last - r.entry) if (last is not None and r.side == "long") else (r.entry - last) if last is not None else None
            rr = (pnl / r.risk_pts) if (pnl is not None and r.risk_pts) else None
            return Banner("ACTIVE", "active", "TRADE ACTIVE — manage, don't add", base + (f" · now {pnl:+.2f} pts ({rr:+.2f}R)" if pnl is not None else ""),
                          [], cred, notes + [r.trigger_text])
        return Banner("DONE", "done", f"DAY DONE — {r.resolution.upper()} at {r.exit_price:,.2f} ({r.r_multiple:+.2f}R)",
                      base + ". One setup taken; the desk is closed for you. Log the journal row at 16:15.", [], cred, notes + [r.resolution_text])
    if now_min >= T_CLOSE:
        return Banner("SETTLE", "neutral", "SETTLEMENT — run the 16:15 audit", "No trade today. Log Watch Day in the journal (1-Trade Rule: Yes).", [], cred, notes)
    if now_min >= T_SHUTDOWN:
        return Banner("SHUTDOWN", "neutral", "DESK CLOSED — dead zone, no new positions", "Watch Day. Screens off.", [], cred, notes)
    if now_min >= T_LAST_QUALIFYING:
        return Banner("STAND_DOWN", "neutral", "STAND DOWN — no qualifying bar closed by 11:05", "Watch Day: capital intact, discipline score intact. Flat by 11:30.", [], cred, notes)
    armed = [p for p in plays if p.status == "armed"]
    gtxt = ""
    if gate and gate.status in ("acceptance", "trap"):
        gtxt = (" 09:50 said ACCEPTANCE → momentum plays first (A3/A4)." if gate.status == "acceptance" else " 09:50 said TRAP → the fades first (A1/A2).")
    if armed:
        a = armed[0]
        return Banner("ARMED", "go", f"ARMED — {a.side}: {a.title}", f"{a.status_text}. Primary window closes 10:15; last qualifying bar 11:05.{gtxt}",
                      plays, cred, notes)
    win = f"primary window until {fmt_hm(T_PRIMARY_END)}" if now_min < T_PRIMARY_END else f"last qualifying bar closes {fmt_hm(T_LAST_QUALIFYING)}"
    return Banner("WATCHING", "wait", "WAITING FOR A QUALIFYING 5-MINUTE CLOSE", f"{reg_name} · {win}.{gtxt}", plays, cred, notes)
