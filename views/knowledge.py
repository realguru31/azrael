"""knowledge.py — the desk's rules on one page, for the moment you need them (execution focus, no theory)."""
from __future__ import annotations

import streamlit as st

from views import common as U

LAWS = """
**The 4 non-negotiable desk laws**
1. **ONE structured setup per session.** Target hit or 1R stop hit = the day is over. Screens off before the 11:30 theta grind.
2. **Hard 1R account risk cap.** Never more than 1 % of capital on a trade. Size is reverse-engineered from the structural invalidation. Moving a stop mid-trade is grounds for desk suspension.
3. **The 20-minute opening discovery rule.** Zero executions 09:30–09:50. Market makers widen spreads up to 300 % clearing overnight imbalances.
4. **Zero 'signal call' culture.** Run the 08:30 math, choose your archetype, log your plan, execute independently.
"""

SOP = """
| ET | Action |
|---|---|
| 08:30 | Workstation calibration: C5 close, C6 VIX, C7 /ES drift, C8 capital, C9 1.0 %. Note C22 regime, C23 inventory bias. |
| 08:33 | Cross-verify C13/C17 with the desk bot within 2 points; if divergent, align C6. |
| 08:40 | Mark the coordinates: blue walls C13/C17 · orange shelves C14/C16 · grey anchor C15 (purple C41–C46 on gap days). |
| 08:45 | Macro catalyst sweep (CPI, PPI, NFP, FOMC — widen stops or stand aside) and the If/Then map: favoured side, trap zones, King Nodes. |
| 09:15 | Post the trade card before 09:25: Archetype · Trigger · Invalidation · 1R cap. No setup = post Watch Day. |
| 09:25 | Set the 25-minute timer for 09:50. Hands off order entry. |
| 09:30–09:50 | Discovery gate. Classify the open: acceptance or trap. |
| 09:31 | Gap protocol (outlier opens only): open outside ±1.0 EM or drift ≥ 0.75 % → enter the cash open in C10; C38 re-anchors; trade C41/C42, nodes C43/C44, fences C45/C46. |
| 09:50 | The test: holding the side of the open where the move started = acceptance (A3/A4); reversed back through the open = trap (A1/A2). |
| 09:51–10:15 | Primary execution window (SOP). MEIC entries once opening volatility has cleared. |
| by 11:05 | A qualifying 5-minute bar must have closed; otherwise no trade today. Flat by 11:30. |
| 11:30 | Desk shutdown. Dead zone: no new positions. |
| 16:15 | Settlement audit against the 08:30 map; log Tab 2; post the broker card, wins and losses both. |
"""

ARCH = """
**Regime filter (C6):** Positive < 15.0 → A1 & A2 valid, A3 & A4 banned · Balanced 15.0–18.5 → A2 & A3 valid, A4 banned · Negative > 18.5 → A3 & A4 valid, A1 banned. The 09:50 test decides between the two: acceptance → A3/A4, trap → A1/A2. A King Node on a ±0.5 shelf merges A1 and A2 into one maximum-edge setup.

**A1 · Half-EM mean-reversion fade (Positive).** Probe within 3–5 pts of C14/C16 after 09:50 → two consecutive 5-minute closes at/near the shelf without continuation → third candle reverses toward the anchor on expanding volume → enter on that close. Stop: a 5-minute close > 8 pts beyond the shelf (a wick is not a stop). Target: C15 within 3 pts, exit 100 %; secondary the opposite 0.5 shelf only if momentum confirms — never the 1.0 wall in Positive Gamma. ATM or 1–2 strikes ITM, delta 0.55–0.70, 1DTE when the stop is wide. Gap days: shelves C41/C42, target C39.

**A2 · King Node absorption reversal (all regimes, best in Balanced).** Displacement of 15–25+ pts from the node, first retest holds within 2–3 pts → a 5-minute candle with a rejection wick (close > 50 % off the extreme) → enter on the open of the follow-through candle. Mechanical desk version: fall ≥ 15 into the put node, bar closes back above it with a lower wick over half its range → long; target half the fall back; out on a 5-minute close 5 pts through or two closes beyond. Mirror at the call node. Delta 0.55–0.65.

**A3 · 3-ticker alignment breakout (VIX ≥ 15).** SPX, SPY and QQQ all close a 5-minute bar outside their last 20-minute box; SPX box ≤ 0.20 EM wide, close ≥ 0.05 EM outside, > 8 pts of room to the next EM level; trade toward that level. Out on a close back inside the box; if any ticker fails to hold on the next candle, exit. 0DTE at 0.55–0.65 delta, no OTM lottery strikes.

**A4 · 1.0-EM boundary runner (Negative only).** Two consecutive 5-minute closes beyond the 0.5 shelf (the first on above-average volume), the next candle does not snap back → enter on the open of the second candle following acceptance. Stop: a close back inside the shelf. Target: the 1.0 wall on first contact, exit 100 % — reversals at the wall are violent. Air-pocket check: minimal OI between the shelf and the wall. Size down 15–20 % for gamma convexity. Never take counter-trend fades in Negative Gamma.
"""

REGIMES = """
| Regime | Dealer flow | Tape | Desk stance |
|---|---|---|---|
| Positive Gamma (VIX < 15) | long gamma: sell rallies, buy dips | moves capped, breakouts fail, ±29-pt half shelves at VIX 12 | fade the shelves back to the anchor (A1); never buy breakout calls above C14 |
| Balanced Gamma (15–18.5) | book evenly split | boundary → anchor → opposite boundary rotations | King Node absorption (A2) or wait for 3-ticker alignment (A3); full 1R, stop 8–10 pts past the boundary |
| Negative Gamma (> 18.5) | short gamma: chase price | candles extend, gaps widen, air pockets | ride momentum to the 1.0 wall (A4); counter-trend fades forbidden; VIX 20–25 → EM 97–121 pts |
"""

CREDIT = """
**MEIC** — 10-wide Iron Condor sold strictly outside the 1.0 walls: bear call short 3–5 pts above C13, bull put short 3–5 pts below C17 (blueprint: 7,747 → 7,750/7,760; 7,601 → 7,595/7,585). Expiry 0DTE on clear Positive-Gamma days with balanced inventory, 1DTE for Balanced or macro mornings, 2DTE only in clear Positive Gamma with balanced C23. Gap days: shorts strictly beyond C45/C46 (1.25 × EM). Desk bot: short wings strictly beyond the ±1.25 EM fences, never between the King Nodes on a two-way day; in Balanced Gamma spreads are viable after 11:30 once a range between the nodes is confirmed.

**Sizing** — max loss per contract = (width − credit) × 100; contracts = INT(C19 ÷ max loss). $25k / $250 with a $1.80 credit on a 10-wide = $820 max loss = 0 contracts: the account is undercapitalised for those wings, never force size.

**Regime protocol** — Positive: double-sided MEIC, full 1R. Balanced: single-sided aligned with the morning bias, extra 3–5 pt buffer, size −25 %. Negative: condors banned, directional only, 15–20 wide, size −50 %; VIX > 22 = zero trades.

**Defence** — within 5 pts of a short strike: roll the tested wing out 1 day and 5 wider for a credit or scratch, else take the loss. C22 flips to Negative during the session: close the entire condor at market.
"""

RISK = """
| Account | Risk per trade | 10 losing days | Status |
|---|---|---|---|
| $25,000 | 1 % ($250) | $2,500 (10 %) | recoverable within a week |
| $25,000 | 2 % ($500) | $5,000 (20 %) | significant drawdown |
| $25,000 | 5 % ($1,250) | $12,500 (50 %) | account crisis |
| $25,000 | 10 % ($2,500) | destroyed | no recovery path |

**Sizing** C29 = INT(C19 ÷ (C27 × C28 × 100)); $250 ÷ (8 × 0.55 × 100) = 0 → tighter structural stop, higher delta, or stand aside. 0DTE: treat C29 × 0.8 as the operational limit (gamma convexity). Micro desk (< $25k): XSP = SPX ÷ 10 with identical settlement; SPY = levels ÷ 10.

**Discipline score** = sessions with ≤ 1 trade ÷ total sessions × 100. 90+ = disciplined desk operator; < 80 = your off-plan sessions are your worst. 95 % discipline with a 52 % win rate beats 80 % discipline with 60 %.
"""

CASES = """
| Case | Regime | Setup | Trade |
|---|---|---|---|
| Aug 5 2024 | volatility shock, VIX 38→65, /ES −3.2 % | opening trap reclaim | 160-pt gap-down absorbed by 09:50; 5,200 calls at 09:50 on the 5,195 reclaim, stop 5,185, target the −0.5 floor 5,281.6 → +3.2R by 11:15 |
| Aug 21 2026 | Positive, VIX 15.13 | A1 | dip to 7,638 at the −0.5 shelf, two candles hold, 10:20 reversal on volume; 7,645 calls $7.80, stop close < 7,629, target the anchor 7,674 → sold $15.50, +1.8R |
| Jul 11 2024 | Balanced → Negative, CPI day | A3 | acceptance down through the open; SPX 5,630, SPY 561.50, QQQ 498 break together at 10:05; 5,620 puts, stop close > 5,634, target −1.0 wall 5,588.3 → +2.4R |
| Mar 15 2024 | Balanced, quad witching | A2 | 45,000 contracts at 5,150; 22-pt drop to 5,128 on the −0.5 floor, 12-pt hammer at 09:50; 5,140 calls at 10:00, stop 5,123, target the node → +2.1R, pinned all day |
| Apr 12 2024 | Negative, VIX > 17 | A4 | −0.5 floor 5,174 sliced by 09:45, two closes below 5,170; 5,160 puts on the second candle's open at 10:00, stop close > 5,176, −1.0 wall 5,150.2 first contact → +2.5R by 10:40 |
"""


def render(cfg, plan, label):
    U.status_bar(plan, label, cfg["session"])
    st.markdown("### Desk knowledge — the rules, not the theory")
    t = st.tabs(["Laws & SOP", "Archetypes", "Regimes", "Credit spreads", "Risk & discipline", "Case studies"])
    with t[0]:
        st.markdown(LAWS); st.markdown(SOP)
    with t[1]:
        st.markdown(ARCH)
    with t[2]:
        st.markdown(REGIMES)
        st.caption("C24 protocols: Positive — wait 20 min, identify the EM boundary probe, fade with a 0.5R limit, target the anchor, exit by 3 PM. "
                   "Balanced — watch the dominant strike, enter on rotation confirmation, target the opposite 0.5 EM, trail the stop. "
                   "Negative — identify the air-pocket direction, momentum entry post 09:50, stop below the EM boundary, target the 1.0 wall.")
    with t[3]:
        st.markdown(CREDIT)
    with t[4]:
        st.markdown(RISK)
    with t[5]:
        st.markdown(CASES)
