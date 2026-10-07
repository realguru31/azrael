"""
audit.py — the 04:15 PM Settlement Audit & Rules Replay, in the desk's own format (#daily-math-receipts).

    The cash session settled at X (official daily close).
    Session Volatility Audit (locked to the 08:30 AM map posted in #premarket-math):
        Cash Anchor · VIX Input (08:15 AM ET print) · 1-Sigma Expected Move · King Nodes · Fences ·
        Session Range (low bar to high bar, pts = x EM) · Settlement Verification
    SPY and /ES Against Their Own Morning Bands
    Rules Replay (5-minute bars, hindsight, measured on the index, not a fill)
    Also checked · Microstructure Lesson

Plus the four questions of the manual's settlement review (Ch.6) and the 20-session statistics.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional

import pandas as pd

from core.rules import rules_replay, session_bars


@dataclass
class SessionAudit:
    session: str
    settlement: Optional[float]
    anchor: float
    vix: float
    vix_print_time: str
    em: float
    c13: float
    c14: float
    c15: float
    c16: float
    c17: float
    put_node: float
    call_node: float
    put_fence: float
    call_fence: float
    session_low: Optional[float] = None
    session_low_time: Optional[str] = None
    session_high: Optional[float] = None
    session_high_time: Optional[str] = None
    range_pts: Optional[float] = None
    range_em: Optional[float] = None
    inside_1sigma: Optional[bool] = None
    inside_half: Optional[bool] = None
    walls_tested: Optional[bool] = None
    wall_tested_side: Optional[str] = None
    half_shelves_held: Optional[bool] = None
    king_node_touched: Optional[str] = None
    stops_run: List[str] = field(default_factory=list)
    nearest_miss: str = ""
    score_line: str = ""
    provisional: bool = False
    last_print: Optional[float] = None
    last_print_time: str = ""
    settle_zone: str = ""
    regime: int = 2
    replay: Optional[Dict] = None
    also_checked: List[str] = field(default_factory=list)
    lesson: str = ""
    proxies: List[Dict] = field(default_factory=list)

    def as_dict(self):
        return asdict(self)


def zone_text(s: float, c5: float, em: float) -> str:
    if s > c5 + em:
        return "ABOVE C13: +1.0 wall broken"
    if s > c5 + em / 2:
        return "between C14 and C13"
    if s >= c5:
        return "between C15 and C14"
    if s >= c5 - em / 2:
        return "between C16 and C15"
    if s >= c5 - em:
        return "between C17 and C16"
    return "BELOW C17: −1.0 wall broken"


def build_audit(session: str, spx5: pd.DataFrame, spy5, qqq5, settlement: Optional[float], anchor: float, vix: float,
                vix_print_time: str, grid: Dict[str, float], em: float, put_node: float, call_node: float,
                put_fence: float, call_fence: float, c6: float, proxies: Optional[List[Dict]] = None,
                stop_clusters: Optional[Dict] = None) -> SessionAudit:
    a = SessionAudit(session=session, settlement=settlement, anchor=anchor, vix=vix, vix_print_time=vix_print_time,
                     em=em, c13=grid["C13"], c14=grid["C14"], c15=grid["C15"], c16=grid["C16"], c17=grid["C17"],
                     put_node=put_node, call_node=call_node, put_fence=put_fence, call_fence=call_fence)
    from core.workstation import regime_code
    a.regime = regime_code(c6)
    bars = session_bars(spx5)
    if not bars.empty:
        lo_i, hi_i = bars["low"].idxmin(), bars["high"].idxmax()
        a.session_low, a.session_low_time = float(bars.loc[lo_i, "low"]), lo_i.strftime("%H:%M")
        a.session_high, a.session_high_time = float(bars.loc[hi_i, "high"]), hi_i.strftime("%H:%M")
        a.range_pts = round(a.session_high - a.session_low, 2)
        a.range_em = round(a.range_pts / em, 2) if em else None
        a.walls_tested = bool(a.session_high >= grid["C13"] or a.session_low <= grid["C17"])
        a.wall_tested_side = ("+1.0" if a.session_high >= grid["C13"] else "") + ("−1.0" if a.session_low <= grid["C17"] else "")
        a.half_shelves_held = bool(a.session_high < grid["C14"] + 8 and a.session_low > grid["C16"] - 8)
        touched = []
        if a.session_low <= put_node <= a.session_high:
            touched.append(f"put node {put_node:.0f}")
        if a.session_low <= call_node <= a.session_high:
            touched.append(f"call node {call_node:.0f}")
        a.king_node_touched = ", ".join(touched) if touched else "neither node was traded through"
        # Ch.6 fourth question: where did the stops get run relative to the levels flagged at 08:45?
        sc = stop_clusters or {}
        for name, lvl in (("pre-market high", sc.get("pre_market_high")), ("pre-market low", sc.get("pre_market_low")),
                          ("prior session high", sc.get("prior_session_high")), ("prior session low", sc.get("prior_session_low"))):
            if lvl is None:
                continue
            if "high" in name and a.session_high > lvl:
                a.stops_run.append(f"{name} {lvl:.2f} taken out (session high {a.session_high:.2f} at {a.session_high_time})")
            if "low" in name and a.session_low < lvl:
                a.stops_run.append(f"{name} {lvl:.2f} taken out (session low {a.session_low:.2f} at {a.session_low_time})")
        for h in sc.get("round_hundreds", []) or []:
            if a.session_low <= h <= a.session_high:
                a.stops_run.append(f"round hundred {h:.0f} traded through")
        if settlement is None:
            # session not settled yet: keep the settlement empty and say so (the replay below is still final after 11:30)
            a.provisional = True
            a.last_print = float(bars["close"].iloc[-1])
            a.last_print_time = bars.index[-1].strftime("%H:%M")
    if a.settlement is not None:
        a.inside_1sigma = bool(grid["C17"] <= a.settlement <= grid["C13"])
        a.inside_half = bool(grid["C16"] <= a.settlement <= grid["C14"])
        a.settle_zone = zone_text(a.settlement, grid["C15"], em)
    rr = rules_replay(spx5, spy5, qqq5, grid, em, put_node, call_node, c6)
    a.replay = rr["chosen"].as_dict() if rr["chosen"] is not None else None
    a.also_checked = rr["also_checked"]
    a.proxies = proxies or []
    if a.replay is None and spx5 is not None and not spx5.empty:
        # the closest the tape came to any written trigger — the desk's lesson on a Watch Day
        from core.rules import _touch_window
        tw = _touch_window(session_bars(spx5))
        cands = []
        if not tw.empty:
            lo_, hi_ = float(tw["low"].min()), float(tw["high"].max())
            if lo_ > put_node:
                cands.append((lo_ - put_node, f"the window low of {lo_:.2f} sat {lo_ - put_node:.2f} pts above the {put_node:.0f} put node"))
            if hi_ < call_node:
                cands.append((call_node - hi_, f"the window high of {hi_:.2f} sat {call_node - hi_:.2f} pts below the {call_node:.0f} call node"))
            if lo_ > grid["C16"]:
                cands.append((lo_ - grid["C16"], f"the window low of {lo_:.2f} held {lo_ - grid['C16']:.2f} pts above the −0.5 shelf {grid['C16']:.2f}"))
            if hi_ < grid["C14"]:
                cands.append((grid["C14"] - hi_, f"the window high of {hi_:.2f} held {grid['C14'] - hi_:.2f} pts below the +0.5 shelf {grid['C14']:.2f}"))
        if cands:
            cands.sort(key=lambda c: c[0])
            a.nearest_miss = cands[0][1]
    a.lesson = microstructure_lesson(a)
    return a


def microstructure_lesson(a: SessionAudit) -> str:
    from core.workstation import REGIME_SHORT
    reg = REGIME_SHORT.get(a.regime, "")
    if a.score_line:
        L.append(f"Live idea (app scoring, Scenario Book): {a.score_line}")
    if a.replay is None and a.nearest_miss:
        return (f"{a.nearest_miss[0].upper()}{a.nearest_miss[1:]}, and in a {reg.lower()} inside the expected move, only an actual tag of the "
                f"written level makes the setup live. Not trading was the trade.")
    parts = [f"In a {reg} regime (structural interpretation),"]
    if a.range_em is not None:
        parts.append(f"the session used {a.range_em:.2f} EM of range ({a.range_pts:.2f} pts)")
    if a.inside_1sigma is not None:
        parts.append("and settled inside the 1-sigma envelope." if a.inside_1sigma else "and settled OUTSIDE the 1-sigma envelope.")
    if a.replay:
        r = a.replay
        if r["resolution"] == "target":
            parts.append(f"The {r['trigger_time']} Archetype {r['archetype']} trigger reached its target for +{r['r_multiple']:.2f}R.")
        elif r["resolution"] == "stopped":
            over = abs(r["r_multiple"]) - 1 if r["r_multiple"] is not None else 0
            parts.append(f"The {r['trigger_time']} Archetype {r['archetype']} trigger ran {r['best_excursion']:.2f} pts before the "
                         f"stop, and the close-based stop gave up {max(over, 0):.2f}R beyond plan.")
        else:
            parts.append(f"The {r['trigger_time']} Archetype {r['archetype']} trigger was flat at 11:30 for {r['r_multiple']:+.2f}R.")
    else:
        parts.append("No archetype qualified between 09:50 and 11:05 — the disciplined outcome was a Watch Day.")
    return " ".join(parts)


def audit_text(a: SessionAudit) -> str:
    """Discord-style plain text of the audit, mirroring the desk bot post."""
    L = []
    L.append(f"04:15 PM SETTLEMENT AUDIT & RULES REPLAY | {a.session}")
    L.append("")
    if a.settlement is not None:
        L.append(f"The cash session settled at {a.settlement:.2f} (official daily close).")
    elif a.provisional:
        L.append(f"LIVE — session not settled. Last 5-minute print {a.last_print:.2f} at {a.last_print_time} ET; the settlement block fills at 16:00.")
    L.append("Session Volatility Audit (locked to the 08:30 AM map):")
    L.append(f"Cash Anchor (prior close): {a.anchor:.2f}")
    L.append(f"VIX Input: {a.vix:.2f} ({a.vix_print_time} ET print)")
    L.append(f"1-Sigma Expected Move: +/-{a.em:.2f} pts ({a.c17:.2f} to {a.c13:.2f})")
    L.append(f"King Nodes: put {a.put_node:.0f}, call {a.call_node:.0f}. Fences: <{a.put_fence:.0f} / >{a.call_fence:.0f}")
    if a.range_pts is not None:
        L.append(f"Session Range: {a.session_low:.2f} ({a.session_low_time} bar) to {a.session_high:.2f} ({a.session_high_time} bar), "
                 f"{a.range_pts:.2f} pts = {a.range_em:.2f} EM")
    if a.inside_1sigma is not None:
        L.append(f"Settlement Verification: {'Inside' if a.inside_1sigma else 'OUTSIDE'} 1-Sigma Expected Move ({a.settle_zone})")
    if a.king_node_touched:
        L.append(f"King Node gravity: {a.king_node_touched}")
    if a.stops_run:
        L.append("Stops run vs the 08:45 map: " + "; ".join(a.stops_run))
    if a.proxies:
        L.append("")
        L.append("SPY and the 24-hour SPX500 feed Against Their Own Morning Bands:")
        for p in a.proxies:
            if p.get("settle") is not None:
                L.append(f"{p['name']}: settled {p['settle']:.2f}, band {p['band_lo']:.2f} to {p['band_hi']:.2f} "
                         f"(+/-{p['em']:.2f}): {'inside' if p['band_lo'] <= p['settle'] <= p['band_hi'] else 'OUTSIDE'} its 1-sigma band")
    L.append("")
    L.append("Rules Replay (5-minute bars, hindsight, measured on the index, not a fill):")
    if a.replay:
        r = a.replay
        from core.workstation import ARCHETYPE_LONG
        L.append(f"Setup Archetype: Archetype {r['archetype']} ({ARCHETYPE_LONG[r['archetype']]}), "
                 f"{'long (calls)' if r['side'] == 'long' else 'short (puts)'}")
        L.append(f"Execution Trigger: {r['trigger_text']}")
        L.append("Contract Structure: SPXW 0DTE, 0.55 to 0.65 delta (SPY 0DTE and /ES options map to the same levels)")
        L.append(f"Structural Invalidation: {r['invalidation_text']}")
        L.append(f"Trade Resolution: {r['resolution_text']}")
    else:
        L.append("No archetype produced a qualifying 5-minute close between 09:50 and 11:05 — stand down (Watch Day).")
    if a.also_checked:
        L.append("Also checked: " + " ".join(a.also_checked))
    L.append("")
    L.append(f"Microstructure Lesson: {a.lesson}")
    L.append("")
    L.append("(Log your verified session P&L in Tab 2 of your Workstation and post execution cards in #member-wins-and-receipts)")
    return "\n".join(L)


def history_stats(audits: List[Dict]) -> Dict:
    """Over 20 sessions the loop compounds: hold rates of the walls and shelves, by regime."""
    if not audits:
        return {"n": 0}
    df = pd.DataFrame(audits)
    out = {"n": len(df)}
    if "inside_1sigma" in df:
        out["inside_1sigma_pct"] = round(df["inside_1sigma"].fillna(False).mean() * 100, 1)
    if "inside_half" in df:
        out["inside_half_pct"] = round(df["inside_half"].fillna(False).mean() * 100, 1)
    if "walls_tested" in df:
        out["walls_tested_pct"] = round(df["walls_tested"].fillna(False).mean() * 100, 1)
    if "regime" in df and "inside_1sigma" in df:
        by = df.groupby("regime")["inside_1sigma"].agg(["mean", "count"])
        out["by_regime"] = {int(k): {"held_pct": round(v["mean"] * 100, 1), "n": int(v["count"])} for k, v in by.iterrows()}
    rs = [a["replay"]["r_multiple"] for a in audits if a.get("replay") and a["replay"].get("r_multiple") is not None]
    if rs:
        out["replay_trades"] = len(rs)
        out["replay_avg_r"] = round(sum(rs) / len(rs), 2)
        out["replay_win_pct"] = round(sum(1 for r in rs if r > 0) / len(rs) * 100, 1)
    return out
