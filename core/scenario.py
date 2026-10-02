"""
scenario.py — writes the 08:45 Tactical Execution Map (A / B / C) and the 09:15 trade card in the desk's format.

The map's wording and numbers follow the Sep 29 / Sep 30 2026 desk posts: A = King Node absorption with the
mechanical wick rule (or the Half-EM fade in Positive Gamma), B = 3-ticker breakout with the box limits
(0.20 EM wide, 0.05 EM outside, > 8 pts room) or the runner in Negative Gamma, C = stand down / gate.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

from core.workstation import (ARCHETYPE_NAME, REGIME_SHORT, eligible_archetypes, inventory_bias_key, regime_code,
                              StandardGrid, StrikeGrid)


def scenario_map(session_title: str, g: StandardGrid, sg: StrikeGrid, c7: Optional[float], spy: Optional[Dict] = None,
                 es: Optional[Dict] = None, macro_note: str = "", oi_node: Optional[Dict] = None) -> Dict[str, object]:
    r = regime_code(g.c6)
    el = eligible_archetypes(g.c6)
    bias = inventory_bias_key(c7)
    em = g.c12
    levels = [g.c17, g.c16, g.c15, g.c14, g.c13]
    box_max, out_min = 0.20 * em, 0.05 * em
    drift_txt = f"{c7:+.2f}%" if c7 is not None else "n/a"      # overnight drift from the SPX500 price feed

    # ── A ─────────────────────────────────────────────────────────────────────
    if r == 1:
        A = (f"A. Half-EM fade (Archetype 1). IF price probes the −0.5 shelf {g.c16:.2f} after 09:50 AM, two 5-minute bars close "
             f"at/near it without continuation and the third reverses on higher volume, THEN long calls toward the anchor "
             f"{g.c15:.2f} (exit within 3 pts). Out on a 5-minute close below {g.c16 - 8:.2f}. Mirror at the +0.5 shelf "
             f"{g.c14:.2f} with puts, stop above {g.c14 + 8:.2f}. Never hold for the 1.0 wall in Positive Gamma.")
    else:
        A = (f"A. King node absorption (Archetype 2). If SPX falls 15 pts or more into the put node {sg.put_node:.0f} after 09:50 AM "
             f"and the bar closes back above {sg.put_node:.0f} with a lower wick over half its range, long calls; target half the "
             f"fall back. Out on a 5-minute close below {sg.put_node - 5:.0f} or two closes below {sg.put_node:.0f}. "
             f"Mirror at the call node {sg.call_node:.0f} with puts.")
    # ── B ─────────────────────────────────────────────────────────────────────
    if r == 3:
        B = (f"B. 1.0-EM runner (Archetype 4). If two consecutive 5-minute bars close beyond the +0.5 shelf {g.c14:.2f} (or below "
             f"{g.c16:.2f}), the first on above-average volume, enter on the open of the next bar toward the 1.0 wall "
             f"{g.c13:.2f} / {g.c17:.2f} and exit 100 % on first contact. Out on a close back inside the shelf. "
             f"3-ticker breakout (Archetype 3) also eligible with the box rules below.")
    else:
        B = (f"B. 3-ticker breakout (Archetype 3). If SPX, SPY and QQQ all close a 5-minute bar outside their last 20-minute box "
             f"after 09:50 AM, the SPX box is no wider than {box_max:.2f} pts, SPX closes at least {out_min:.2f} pts outside it and "
             f"has more than 8 pts of room to the next EM level ({', '.join(f'{x:.2f}' for x in levels)}), trade toward that "
             f"level. Out on a close back inside the box.")
        if r == 1:
            # the desk's own low-VIX maps (Sep 22/23, VIX 14.31) still post a shelf-break continuation as Scenario B
            B = (f"B. Shelf break / breakout continuation. Acceptance beyond a shelf transfers local control: IF price accepts above "
                 f"the Call King Node {sg.call_node:.0f} post-gate, THEN long calls targeting the Upper Strike Wall {sg.upper_wall:.0f}, "
                 f"stop back under {sg.call_node:.0f}. IF price accepts below the Put King Node {sg.put_node:.0f}, THEN long puts targeting "
                 f"the Lower Strike Wall {sg.lower_wall:.0f}, stop back above {sg.put_node:.0f}. King Nodes are triggers, never targets. "
                 f"(The archetype filter bans Archetypes 3 and 4 in Positive Gamma — treat B as a discretionary continuation, half size, "
                 f"and only on acceptance, never on the spike.)")
    C = ("C. Stand down. No entries 09:30 to 09:50 AM. No qualifying bar closed by 11:05 AM means no trade today. "
         "One setup, 1R planned risk, flat by 11:30 AM.")

    gap_day = c7 is not None and abs(c7) >= 0.75
    favored = 3 if gap_day else {1: 1, 2: 2, 3: 4}[r]
    favored_label = "Archetype 3 (Breakout / Gap Momentum)" if gap_day else ARCHETYPE_NAME[favored]
    read = {
        1: (f"Positive Gamma dampens extension: fade the shelves {g.c16:.2f} / {g.c14:.2f} back toward {g.c15:.2f}. "
            f"Nothing before the 09:50 gate; opening probes through shelves are liquidity sweeps, not intent."),
        2: (f"Balanced Gamma reads as a two-way auction, so the regime favors Scenario A, fading a push into the put node "
            f"{sg.put_node:.0f} or the call node {sg.call_node:.0f} once the bar closes back inside. Scenario B only if the "
            f"3-ticker breakout qualifies."),
        3: (f"Negative Gamma: dealers chase price. Ride acceptance beyond a 0.5 shelf into the 1.0 wall; counter-trend fades "
            f"are banned. Strict stop at the shelf."),
    }[r]
    if bias == "short":
        read += f" Overnight drift {drift_txt}: dealers carried short delta — do not short the opening spike; let it exhaust."
    elif bias == "long":
        read += f" Overnight drift {drift_txt}: long-inventory absorption risk — the pre-market high is the first fade candidate."
    else:
        read += f" Overnight drift {drift_txt}: balanced open, standard protocol."
    if c7 is not None and abs(c7) >= 0.75:
        read += (" Large opening imbalance: never fade the open at this drift. If the 09:30 cash open prints outside "
                 f"{g.c17:.2f}–{g.c13:.2f} or the drift stays ≥ 0.75 %, enter the open in C10 at 09:31 — the map re-anchors.")
    if macro_note:
        read += f" Macro: {macro_note}."
    read += " I stand down if no qualifying bar closes by 11:05 AM, or after the one setup is taken."

    vol = {
        1: (f"VIX at {g.c6:.2f} — low-IV environment. Premium decays cleanly. IC and credit spreads viable provided short wings "
            f"sit strictly beyond {sg.put_fence:.0f}P / {sg.call_fence:.0f}C. Avoid tight 5-point wings intraday."),
        2: (f"VIX at {g.c6:.2f}: moderate IV, two-way auction. Credit spreads are viable after 11:30 AM if price has confirmed "
            f"a range between the king nodes. Short wings sit strictly beyond {sg.put_fence:.0f}P / {sg.call_fence:.0f}C. "
            f"Never sell premium between the nodes on a two-way day."),
        3: (f"VIX at {g.c6:.2f}: expansion regime. Iron Condors banned; directional credit spreads only, 15–20 wide, half size"
            + (". VIX > 22: zero credit spread trades." if g.c6 > 22 else ".")),
    }[r]

    out = {
        "title": f"TACTICAL EXECUTION MAP | {session_title}",
        "header": (f"SPX 0DTE. {REGIME_SHORT[r]}, EM +/-{em:.2f}, VIX {g.c6:.2f}, anchor {g.c15:.2f}, overnight drift {drift_txt} (SPX500 feed)."),
        "A": A, "B": B, "C": C, "desk_read": read,
        "eligible": f"{', '.join(ARCHETYPE_NAME[a].split(':')[0] for a in el['valid'])} (VIX {g.c6:.2f})",
        "favored": favored_label,
        "execution_guidance": ("Current Regime: Large Opening Imbalance. Rule: Never fade the open when drift is "
                               f"{c7:+.2f}%. Let 09:50 AM confirm absorption before entering.") if gap_day else "",
        "gate": "Hands off 09:30 to 09:50 AM", "risk": "1 Setup / 1R Planned Risk", "vol": vol,
        "proxies": [],
    }
    if oi_node:
        out["oi_note"] = (f"Live chain: largest combined open interest within 1 EM sits at {oi_node['strike']:.0f} "
                          f"({oi_node['total_oi']:,.0f} contracts). The parametric nodes above are the workstation model; the OI "
                          f"strike is the book's Ch.4 definition — when they coincide with a 0.5 shelf, Archetypes 1 & 2 merge.")
    if spy:
        out["proxies"].append(f"SPY: put node {spy['put_node']:.0f}, call node {spy['call_node']:.0f}, shelves {spy['shelf_lo']:.2f} / {spy['shelf_hi']:.2f}")
    if es:
        out["proxies"].append(f"{es['name']}: put node {es['put_node']:.0f}, call node {es['call_node']:.0f}, shelves {es['shelf_lo']:.2f} / {es['shelf_hi']:.2f}")
    return out


def scenario_text(m: Dict[str, object]) -> str:
    L = [m["title"], "", m["header"], "", m["A"], "", m["B"], "", m["C"], "", f"Desk read: {m['desk_read']}", "",
         f"Eligible Archetypes (VIX-gated): {m['eligible']}", f"Favored Archetype: {m['favored']}",
         f"Discovery Gate (All Archetypes): {m['gate']}", f"Directional Risk Model: {m['risk']}"]
    if m.get("execution_guidance"):
        L += ["", "Execution Guidance", "• " + m["execution_guidance"]]
    if m.get("proxies"):
        L += ["", "Same Map on SPY and the 24-hour SPX500 feed"] + list(m["proxies"])
    L += ["", f"Vol Regime & Credit Spread Viability: {m['vol']}"]
    if m.get("oi_note"):
        L += ["", m["oi_note"]]
    L += ["", "The Vault. Levels from the 08:30 AM map. Post your structured trade card in #pre-bell-plans."]
    return "\n".join(L)


@dataclass
class TradeCard:
    session: str
    archetype: str                 # ARCHETYPE_NAME value, credit spread type, or "Watch Day"
    direction: str                 # "Long calls" | "Long puts" | "Bull Put" | "Bear Call" | "Iron Condor" | "—"
    trigger_level: str
    invalidation_level: str
    one_r_cap: float
    contracts: int
    instrument: str
    notes: str
    posted_at: str
    locked: bool = False

    def as_dict(self):
        return asdict(self)

    def text(self) -> str:
        if self.archetype == "Watch Day":
            return f"Watch Day. No qualifying setup identified for current regime. ({self.session}, posted {self.posted_at})"
        return (f"{self.archetype} | Trigger: {self.trigger_level} | Invalidation: {self.invalidation_level} | "
                f"1R cap: ${self.one_r_cap:,.2f} ({self.contracts} contract{'s' if self.contracts != 1 else ''}, {self.instrument}). "
                f"{self.notes}".strip())
