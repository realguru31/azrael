"""
meic.py — the desk's 09:50 MEIC CONDOR DESK ticket (#meic-condor-desk), as pure functions.

What the desk posts at 09:50 (Oct 16, 19, 20, 21 2026 — every ticket so far):
    "Standard 08:30 Grid Holds: Strikes sit strictly beyond both +/-1.0 EM Walls and +/-1.25 EM Fences (<7605P / >7820C)"
    Bear Call Credit Spread (10-Wide): Sell Short Call 7820C · Buy Long Wing 7830C · 5-Pt Defense Trigger 7815
    Bull Put Credit Spread (10-Wide):  Sell Short Put 7605P  · Buy Long Wing 7595P · 5-Pt Defense Trigger 7610
    Regime Mandate (Balanced): SINGLE-SIDED SPREADS OR POST-11:30 RANGE CONDOR (0.75R Size, 1DTE preferred)
    Regime Mandate (Negative): IRON CONDORS BANNED (Negative Gamma). Wide 15-20pt single-sided spreads only.
    5-Point Defense Law: If SPX comes within 5 pts of either short strike, roll out 1 day and 5 pts wider or exit immediately.
So the short strikes ARE the posted ±1.25 EM fence strikes (ROUND((C15 ± 1.25·C12)/5)·5 — the strike grid's fences), the
long wings 10 points further out, the defense triggers 5 points inside each short strike. On gap mornings (C10 active)
the vault moves the fences to the Gap Re-Anchor Engine's C45/C46.

Post-11:30 range condor (Azraël, #live-desk-talk, Oct 8): "A range between the king nodes is confirmed by 11:30 AM when
every 5-minute bar close after the 09:50 gate prints strictly inside the corridor between the Put Node (-0.5 EM) and Call
Node (+0.5 EM). The tape must show two-way rotation back and forth across the cash anchor rather than a one-way directional
drive, keeping the total morning range compressed under roughly 0.5 to 0.6 EM. Any probes toward the nodes must show clear
absorption and wick rejections rather than sustained closes through them. ... your short wings must still sit strictly
beyond the 1.25 EM outer fences."
"""
from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

from core import credit as CR
from core.rules import session_bars
from utils.timeutil import T_GATE_END, T_SHUTDOWN, T_OPEN

MANDATE = {
    1: "DOUBLE-SIDED MEIC IRON CONDOR (Positive Gamma: full 1R size, 0DTE when the overnight inventory is balanced)",
    2: "SINGLE-SIDED SPREADS OR POST-11:30 RANGE CONDOR (0.75R Size, 1DTE preferred)",
    3: "IRON CONDORS BANNED (Negative Gamma). Wide 15-20pt single-sided spreads only.",
}
MANDATE_SOURCE = {1: "credit-spread vault, Positive Gamma protocol (no Positive-Gamma ticket posted yet)",
                  2: "verbatim from the desk's Balanced-Gamma tickets", 3: "verbatim from the desk's Negative-Gamma tickets"}
CIRCUIT_BREAKER = "ZERO CREDIT SPREAD TRADES — spot VIX above 22.0 (hard circuit breaker)."
REGIME_PILL = {1: "POSITIVE GAMMA (PREMIER HARVEST REGIME)", 2: "BALANCED GAMMA (TWO-WAY ROTATIONAL AUCTION)",
               3: "NEGATIVE GAMMA (VOLATILITY EXPANSION)"}


def ticket(plan: Dict, width: float = 10.0, defense: float = 5.0) -> Dict:
    """The 4-leg order ticket exactly as the desk posts it at 09:50."""
    g, sg, gap = plan["grid"], plan["strike_grid"], plan.get("gap") or {}
    c6, reg = float(plan["inputs"]["c6"]), int(plan["regime"])
    if gap.get("active"):
        sc, sp, anchor = float(gap["c45"]), float(gap["c46"]), float(gap["c39"])
        basis = f"GAP RE-ANCHOR FENCES C45/C46 (09:30 OPEN {anchor:,.2f})"
        hold = f"Gap Re-Anchor active: fences moved to the 09:30 open (<{sp:,.0f}P / >{sc:,.0f}C) — do not sell the standard walls into a gap."
    else:
        sc, sp, anchor = float(sg["call_fence"]), float(sg["put_fence"]), float(g["c15"])
        basis = f"STANDARD 08:30 FENCES (ANCHOR {anchor:,.2f})"
        hold = (f"Standard 08:30 Grid Holds: Strikes sit strictly beyond both +/-1.0 EM Walls and +/-1.25 EM Fences "
                f"(<{sp:,.0f}P / >{sc:,.0f}C).")
    proto = CR.regime_protocol(c6)
    allowed = c6 <= 22.0
    cn, pn = (float(gap["c43"]), float(gap["c44"])) if gap.get("active") else (float(sg["call_node"]), float(sg["put_node"]))
    return {
        "short_call": sc, "long_call": sc + width, "short_put": sp, "long_put": sp - width,
        "call_trigger": sc - defense, "put_trigger": sp + defense, "width": width, "defense": defense,
        "anchor": anchor, "cage": sc - sp, "upper_wall": float(sg["upper_wall"]), "lower_wall": float(sg["lower_wall"]),
        "call_node": cn, "put_node": pn,
        "basis": basis, "hold": hold, "gap": bool(gap.get("active")), "regime": reg, "vix": c6,
        "mandate": MANDATE[reg] if allowed else CIRCUIT_BREAKER, "mandate_source": MANDATE_SOURCE[reg] if allowed else "credit-spread vault",
        "regime_pill": REGIME_PILL[reg], "allowed": allowed,
        "condor_now": allowed and reg == 1, "condor_after_1130": allowed and reg == 2, "single_sided_only": reg != 1,
        "size_factor": float(proto["size_factor"]), "expiry_index": {1: 0, 2: 1, 3: 0}[reg],
        "wide_alt": {"call": (sc, sc + 15.0), "put": (sp, sp - 15.0)} if reg == 3 else None,
        "roll_call": (sc + 5.0, sc + 5.0 + width), "roll_put": (sp - 5.0, sp - 5.0 - width),
    }


def defense_status(spot: Optional[float], t: Dict) -> Dict:
    """Distance from spot to each 5-point defense trigger (positive = still safe)."""
    if spot is None:
        return {"spot": None, "call": None, "put": None, "inside": None}
    call_d = t["call_trigger"] - spot
    put_d = spot - t["put_trigger"]
    return {"spot": spot, "inside": t["short_put"] < spot < t["short_call"],
            "call": {"dist": call_d, "hit": spot >= t["call_trigger"], "to_short": t["short_call"] - spot},
            "put": {"dist": put_d, "hit": spot <= t["put_trigger"], "to_short": spot - t["short_put"]}}


def priced(t: Dict, chain: Optional[pd.DataFrame], c19: float) -> Dict:
    """Live mids, credits and Row-29 style contract counts for both wings and the condor (None without a chain)."""
    sf = t["size_factor"]
    call = CR.build_leg("bear_call", t["short_call"], t["width"], chain, c19, sf).as_dict()
    put = CR.build_leg("bull_put", t["short_put"], t["width"], chain, c19, sf).as_dict()
    condor = None
    if call.get("credit") is not None and put.get("credit") is not None:
        from core.workstation import credit_spread_contracts
        cr = round(call["credit"] + put["credit"], 2)
        s = credit_spread_contracts(c19 * sf, t["width"], cr)
        condor = {"credit": cr, "max_loss_per_contract": s["max_loss_per_contract"], "contracts": s["contracts"],
                  "max_gain_per_contract": s["max_gain_per_contract"]}
    return {"call": call, "put": put, "condor": condor, "risk_budget": c19 * sf}


def opening_flow(chain: Optional[pd.DataFrame]) -> Optional[Dict]:
    """Calls vs puts traded so far on this expiry's chain: contracts (Σ volume) and premium (Σ volume × mark × 100).
    The desk prints the 09:30–09:50 window; read at 09:50 this is the same window on the 0DTE chain."""
    need = {"c_volume", "p_volume", "c_mark", "p_mark"}
    if chain is None or chain.empty or not need.issubset(chain.columns):
        return None
    c_ct, p_ct = float(chain["c_volume"].sum()), float(chain["p_volume"].sum())
    c_usd = float((chain["c_volume"] * chain["c_mark"].clip(lower=0)).sum() * 100.0)
    p_usd = float((chain["p_volume"] * chain["p_mark"].clip(lower=0)).sum() * 100.0)
    tot = c_usd + p_usd
    if c_ct + p_ct <= 0:
        return None
    return {"calls_usd": c_usd, "puts_usd": p_usd, "calls_ct": int(c_ct), "puts_ct": int(p_ct), "net_usd": c_usd - p_usd,
            "call_pct": (c_usd / tot * 100.0) if tot > 0 else 50.0}


def range_condor_check(bars5_closed: Optional[pd.DataFrame], t: Dict, em: float, anchor: float, now_min: int) -> Dict:
    """Azraël's post-11:30 range-condor test, measured on CLOSED 5-minute bars after the 09:50 gate."""
    out = {"checks": [], "verdict": "WAITING", "detail": ""}
    bars = session_bars(bars5_closed) if bars5_closed is not None else pd.DataFrame()
    if bars.empty:
        out["detail"] = "no regular-hours bars yet"
        return out
    mins = bars.index.hour * 60 + bars.index.minute
    after = bars[(mins >= T_GATE_END) & (mins + 5 <= T_SHUTDOWN)]
    morning = bars[(mins >= T_OPEN) & (mins + 5 <= T_SHUTDOWN)]
    pn, cn = t["put_node"], t["call_node"]
    checks: List[Dict] = []
    if after.empty:
        out["detail"] = "the test starts with the first close after 09:50"
        return out
    outside = after[(after["close"] <= pn) | (after["close"] >= cn)]
    checks.append({"name": "Every close inside the node corridor", "ok": outside.empty,
                   "note": (f"all {len(after)} closes since 09:50 inside {pn:,.0f}–{cn:,.0f}" if outside.empty else
                            f"{len(outside)} close{'s' if len(outside) != 1 else ''} outside {pn:,.0f}–{cn:,.0f} "
                            f"(first {outside.index[0] + pd.Timedelta(minutes=5):%H:%M} at {float(outside['close'].iloc[0]):,.2f})")})
    side = (after["close"] > anchor).astype(int) - (after["close"] < anchor).astype(int)
    side = side[side != 0]
    crosses = int((side.diff().abs() > 0).sum()) if len(side) > 1 else 0
    checks.append({"name": "Two-way rotation across the anchor", "ok": crosses >= 2, "pending": crosses < 2 and now_min < T_SHUTDOWN,
                   "note": f"{crosses} cross{'es' if crosses != 1 else ''} of the {anchor:,.2f} anchor on 5-minute closes (needs back and forth: ≥ 2)"
                           + (" — still possible before 11:30" if crosses < 2 and now_min < T_SHUTDOWN else "")})
    rng = float(morning["high"].max() - morning["low"].min()) if not morning.empty else 0.0
    frac = rng / em if em else 0.0
    checks.append({"name": "Morning range under ~0.5–0.6 EM", "ok": frac <= 0.6, "warn": 0.5 < frac <= 0.6,
                   "note": f"range {rng:.2f} pts = {frac:.2f} EM" + (" (borderline)" if 0.5 < frac <= 0.6 else "")})
    probes_hi = after[(after["high"] >= cn) & (after["close"] < cn)]
    probes_lo = after[(after["low"] <= pn) & (after["close"] > pn)]
    n_probe = len(probes_hi) + len(probes_lo)
    checks.append({"name": "Node probes absorbed (wick, not close)", "ok": outside.empty,
                   "note": (f"{n_probe} node probe{'s' if n_probe != 1 else ''}, all rejected by the close" if n_probe and outside.empty else
                            "no probe of either node" if not n_probe and outside.empty else "a close went through a node")})
    out["checks"] = checks
    all_ok = all(c["ok"] for c in checks)
    hard_fail = any(not c["ok"] and not c.get("pending") for c in checks)      # a close through a node / range > 0.6 EM cannot be undone
    if now_min < T_SHUTDOWN:
        out["verdict"] = "ON TRACK" if all_ok else "FAILED" if hard_fail else "BUILDING"
        out["detail"] = ("so far every condition holds — verdict at 11:30" if all_ok else
                         "already failed — no range condor today (single-sided only, beyond the fences)" if hard_fail else
                         "no failure yet; the anchor rotation has not printed — verdict at 11:30")
    else:
        out["verdict"] = "CONFIRMED" if all_ok else "NOT CONFIRMED"
        out["detail"] = (f"range confirmed at 11:30 — a condor is allowed, short wings strictly beyond the fences "
                         f"({t['short_put']:,.0f}P / {t['short_call']:,.0f}C)" if all_ok else
                         "range not confirmed — no condor; single-sided only, beyond the fences")
    return out


def payoff_points(t: Dict, credit: Optional[float] = None) -> Dict:
    """Expiration P/L per 1-lot condor in index points (schematic 1.00 credit when no live mids)."""
    cr = credit if (credit is not None and credit > 0) else 1.0
    w = t["width"]
    lo, hi = t["long_put"] - 15.0, t["long_call"] + 15.0
    pts = [(lo, cr - w), (t["long_put"], cr - w), (t["short_put"], cr), (t["short_call"], cr), (t["long_call"], cr - w), (hi, cr - w)]
    return {"points": pts, "credit": cr, "schematic": not (credit is not None and credit > 0), "x_lo": lo, "x_hi": hi,
            "max_gain": cr, "max_loss": w - cr}
