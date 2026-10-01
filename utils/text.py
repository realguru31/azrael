"""text.py — plain-text renderers in the desk bot's format (copy into your own notes or a Discord channel)."""
from __future__ import annotations

from typing import Dict, Optional

from core.workstation import REGIME_SHORT, ARCHETYPE_NAME


def f2(x: Optional[float], nd: int = 2) -> str:
    return "—" if x is None else f"{x:,.{nd}f}"


def f0(x: Optional[float]) -> str:
    return "—" if x is None else f"{x:,.0f}"


def pct(x: Optional[float], nd: int = 2) -> str:
    return "—" if x is None else f"{x:+.{nd}f}%"


def strike_grid_post(plan: Dict, session_title: str) -> str:
    g, sg, i = plan["grid"], plan["strike_grid"], plan["inputs"]
    r = plan["regime"]
    el = plan["eligible"]["valid"]
    L = [f"S&P 500 STRIKE GRID (SPX, SPY, SPX500 FEED) | {session_title}", ""]
    L.append(f"SPX anchor {g['c15']:.2f}, VIX {g['c6']:.2f}, EM +/-{g['c12']:.2f}. Regime: {REGIME_SHORT[r]}, "
             f"overnight drift {pct(i.get('c7'))} (SPX500 feed vs cash close). Shelves {g['c16']:.2f} and {g['c14']:.2f} frame the auction; king nodes "
             f"put {sg['put_node']:.0f} and call {sg['call_node']:.0f} sit on them. Structural interpretation: dealer hedging near "
             f"those nodes may pull price back toward {g['c15']:.2f}. Nothing before the 09:50 AM gate; the open has to show which "
             f"shelf holds. Eligible: {', '.join(ARCHETYPE_NAME[a].split(':')[0] for a in el)}.")
    L += ["", "SPX Expected Move Shelves (Workstation)",
          f"+1.0 EM Wall (C13): {g['c13']:.2f}", f"+0.5 EM Shelf (C14): {g['c14']:.2f}", f"Cash Anchor (C15): {g['c15']:.2f}",
          f"-0.5 EM Shelf (C16): {g['c16']:.2f}", f"-1.0 EM Wall (C17): {g['c17']:.2f}",
          "", "SPX Strike Grid (EM levels rounded to 5)",
          f"Call King Node (+0.5 EM): {sg['call_node']:.0f}", f"Put King Node (-0.5 EM): {sg['put_node']:.0f}",
          f"Upper Strike Wall (+1.0 EM): {sg['upper_wall']:.0f}", f"Lower Strike Wall (-1.0 EM): {sg['lower_wall']:.0f}",
          f"Overnight Drift (SPX500 feed): {pct(i.get('c7'))}",
          "", "Credit Spread & Iron Condor Fence (+/-1.25 EM)",
          f"Short Call Fence: strictly above {sg['call_fence']:.0f}", f"Short Put Fence: strictly below {sg['put_fence']:.0f}",
          f"Vega Risk: {'Low vega sensitivity.' if r == 1 else 'Moderate vega sensitivity.' if r == 2 else 'HIGH vega sensitivity — condors banned.'} Fences strictly outside the nodes"]
    if plan.get("spy"):
        s = plan["spy"]
        L += ["", "SPY (dollars, same VIX, own prior close)",
              f"Anchor: {s['anchor']:.2f} | EM: +/-{s['em']:.2f}", f"Shelves: {s['shelf_lo']:.2f} / {s['shelf_hi']:.2f}",
              f"1 EM Band: {s['band_lo']:.2f} to {s['band_hi']:.2f}",
              f"Nodes ($1 strikes): put {s['put_node']:.0f}, call {s['call_node']:.0f}",
              f"Fences: below {s['put_fence']:.0f}, above {s['call_fence']:.0f}"]
    if plan.get("es"):
        e = plan["es"]
        L += ["", f"{e['name']} (points, same VIX)",
              f"Price: {e['anchor']:.2f} | EM: +/-{e['em']:.2f}", f"Shelves: {e['shelf_lo']:.2f} / {e['shelf_hi']:.2f}",
              f"1 EM Band: {e['band_lo']:.2f} to {e['band_hi']:.2f}",
              f"Nodes (5-pt strikes): put {e['put_node']:.0f}, call {e['call_node']:.0f}"]
    if plan.get("beyond"):
        L += ["", "SPX Beyond 0DTE (daily EM x sqrt(sessions))"]
        exps = plan.get("expiries", [])
        for b in plan["beyond"]:
            n = b["sessions"]
            e = exps[n - 1] if n - 1 < len(exps) else ""
            L.append(f"{e} expiry ({n} sessions): +/-{b['em']:.2f} ({b['lo']:.2f} to {b['hi']:.2f})")
        L.append("SPY and the 24-hour feed scale by the same factor.")
    if plan.get("oi_node"):
        o = plan["oi_node"]
        L += ["", f"Live chain (CBOE, delayed): largest combined OI within 1 EM at {o['strike']:.0f} "
                  f"({o['total_oi']:,.0f} = C {o['c_oi']:,.0f} / P {o['p_oi']:,.0f})."]
    L += ["", f"The Vault. Levels anchored to the prior SPX cash close and the VIX {i.get('vix_print', '08:15')} AM ET print. "
              "Strike grid is the workstation's parametric EM model, not a live OI scan."]
    return "\n".join(L)
