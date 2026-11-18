"""
workstation.py — AZRAEL_OPTIONS_SPX_Premarket_Workstation.xlsx, Tab 1, cell for cell.

Every formula below is copied from the workbook (openpyxl, data_only=False). Where the desk bot in
#premarket-math uses a different convention than the sheet (King Nodes at 0.5 EM vs the sheet's 0.52),
both are provided and named for what they are. Nothing in here does I/O.

Sheet formulas
    C12 = C5*(C6/100)*SQRT(1/252)          C13 = C5+C12        C14 = C5+(C12/2)     C15 = C5
    C16 = C5-(C12/2)                       C17 = C5-C12        C18 = C5*(C6/100)*SQRT(5/252)
    C19 = C8*(C9/100)
    C22 = IF(C6<15, POSITIVE…, IF(C6<=18.5, BALANCED…, NEGATIVE…))
    C23 = IF(C7<-0.5, SHORT…, IF(C7>0.5, LONG…, BALANCED…))
    C24 = IF(C6<15, PROTOCOL…, IF(C6<=18.5, PROTOCOL…, PROTOCOL…))
    C29 = INT(C19/(C27*C28*100))           C30 = C27*C28*100   C31 = C29*C30
    C37 = IF(ISBLANK(C10),"",(C10-C5)/C5*100)
    C38 = IF(ISBLANK(C10),"STANDARD MODE (Prior Close Anchor)",
             IF(OR(C10>C13,C10<C17,ABS((C10-C5)/C5*100)>=0.75),"RE-ANCHOR ACTIVE: …","STANDARD MODE (Gap below threshold…)"))
    C39 = IF(ISBLANK(C10),C5,IF(OR(C10>C13,C10<C17,ABS((C10-C5)/C5*100)>=0.75),C10,C5))
    C40 = C39*(C6/100)*SQRT(1/252)          C41 = C39+(C40/2)   C42 = C39-(C40/2)
    C43 = ROUND((C39+(C40*0.52))/5,0)*5    C44 = ROUND((C39-(C40*0.52))/5,0)*5
    C45 = ROUND((C39+(C40*1.25))/5,0)*5    C46 = ROUND((C39-(C40*1.25))/5,0)*5
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Tuple, Dict, List, Optional

SQRT_1_252 = math.sqrt(1 / 252)
SQRT_5_252 = math.sqrt(5 / 252)

# ── exact text cells ──────────────────────────────────────────────────────────
C22_TEXT = {
    1: "POSITIVE GAMMA: Dealer Dampening Active. Fades Favored. Mean Reversion at Half EM Boundaries.",
    2: "BALANCED GAMMA: Two Way Auction. Strike Balance Dominant. Wait for EM Boundary Touch.",
    3: "NEGATIVE GAMMA: Volatility Expansion Active. Air Pockets Open. Momentum with EM Wall Runners.",
}
C23_TEXT = {
    "short": "SHORT INVENTORY SKEW: Opening Squeeze Risk. Do NOT fade first 20 min lows.",
    "long": "LONG INVENTORY SKEW: Opening Absorption Risk. Do NOT chase first 20 min highs.",
    "balanced": "BALANCED OVERNIGHT INVENTORY: Neutral Open Expected. Wait for Direction.",
}
C24_TEXT = {
    1: "PROTOCOL: Wait 20 min. Identify EM boundary probe. Fade with 0.5R limit. Target anchor close. Exit by 3 PM.",
    2: "PROTOCOL: Wait 20 min. Watch dominant strike. Enter on rotation confirmation. Target opposite 0.5 EM. Trail stop.",
    3: "PROTOCOL: Wait 20 min. Identify air pocket direction. Momentum entry post 9:50. Stop below EM boundary. Target 1.0 EM wall.",
}
REGIME_NAME = {1: "POSITIVE GAMMA", 2: "BALANCED GAMMA", 3: "NEGATIVE GAMMA"}
REGIME_SHORT = {1: "Positive Gamma (Dealer Dampening)", 2: "Balanced Gamma (Two-Way Auction)",
                3: "Negative Gamma (Volatility Expansion)"}

C38_STANDARD_BLANK = "STANDARD MODE (Prior Close Anchor)"
C38_ACTIVE = "RE-ANCHOR ACTIVE: Intraday brackets shifted to opening print."
C38_STANDARD_BELOW = "STANDARD MODE (Gap below threshold. Prior close anchor holds.)"

# Trade Journal Tab 2 — data validation lists, verbatim
JOURNAL_SETUP_TYPES = [
    "Archetype 1: Half EM Fade", "Archetype 2: King Node Reversal", "Archetype 3: 3-Ticker Alignment",
    "Archetype 4: EM Boundary Runner", "Credit Spread: Bull Put", "Credit Spread: Bear Call", "Iron Condor (MEIC)",
]
JOURNAL_CHANNELS = ["#member-wins-and-receipts", "#daily-math-receipts", "Logged Manually"]
JOURNAL_COLUMNS = ["Date", "Setup Type", "Strike & Expiry", "Entry Time", "Invalidation Level (Stop)", "Exit Price",
                   "PnL ($)", "PnL (%)", "R-Multiple", "1-Trade Rule?", "Discord Channel Logged", "Microstructure Notes"]


def excel_round(x: float, digits: int = 0) -> float:
    """Excel ROUND: half away from zero (Python's round() is banker's rounding)."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return float("nan")
    q = 10 ** digits
    return math.floor(abs(x) * q + 0.5) / q * (1 if x >= 0 else -1)


def round_to_strike(x: float, step: float = 5.0) -> float:
    """ROUND(x/step,0)*step — the sheet's strike rounding."""
    return excel_round(x / step, 0) * step


# ── C12–C19 ───────────────────────────────────────────────────────────────────
def daily_em(c5: float, c6: float) -> float:
    return c5 * (c6 / 100.0) * SQRT_1_252


def weekly_em(c5: float, c6: float) -> float:
    return c5 * (c6 / 100.0) * SQRT_5_252


def max_1r(c8: float, c9: float) -> float:
    return c8 * (c9 / 100.0)


@dataclass
class StandardGrid:
    c5: float
    c6: float
    c12: float
    c13: float
    c14: float
    c15: float
    c16: float
    c17: float
    c18: float

    def as_dict(self) -> Dict[str, float]:
        return asdict(self)

    @property
    def levels(self) -> Dict[str, float]:
        return {"C13": self.c13, "C14": self.c14, "C15": self.c15, "C16": self.c16, "C17": self.c17}

    @property
    def em_pct(self) -> float:
        return self.c12 / self.c5 * 100.0 if self.c5 else float("nan")


def standard_grid(c5: float, c6: float) -> StandardGrid:
    em = daily_em(c5, c6)
    return StandardGrid(c5=c5, c6=c6, c12=em, c13=c5 + em, c14=c5 + em / 2, c15=c5, c16=c5 - em / 2,
                        c17=c5 - em, c18=weekly_em(c5, c6))


# ── C22–C24 ───────────────────────────────────────────────────────────────────
def regime_code(c6: float) -> int:
    """1 Positive (<15) · 2 Balanced (15–18.5 inclusive) · 3 Negative (>18.5) — the sheet's IF ladder."""
    if c6 < 15:
        return 1
    if c6 <= 18.5:
        return 2
    return 3


def c22(c6: float) -> str:
    return C22_TEXT[regime_code(c6)]


def inventory_bias_key(c7: Optional[float]) -> str:
    if c7 is None or (isinstance(c7, float) and math.isnan(c7)):
        return "balanced"
    if c7 < -0.5:
        return "short"
    if c7 > 0.5:
        return "long"
    return "balanced"


def c23(c7: Optional[float]) -> str:
    return C23_TEXT[inventory_bias_key(c7)]


def c24(c6: float) -> str:
    return C24_TEXT[regime_code(c6)]


def regime_character(c6: float) -> str:
    """Ch.1 VIX table and the Discord regime graphic."""
    if c6 < 15:
        return "Tight chop, fade setups dominate (half-EM shelves ≈ ±29 pts at VIX 12)"
    if c6 <= 18.5:
        return "Two-way rotation between boundaries, anchor is the session magnet"
    if c6 <= 22:
        return "Expanding range, directional bias, air pockets open — ride momentum to the 1.0 wall"
    return "Deep negative gamma: 200-pt+ intraday potential, strict directional discipline"


# ── archetype gate (Discord #the-4-archetypes, Step 1) ────────────────────────
ARCHETYPE_NAME = {
    1: "Archetype 1: Half EM Fade", 2: "Archetype 2: King Node Reversal",
    3: "Archetype 3: 3-Ticker Alignment", 4: "Archetype 4: EM Boundary Runner",
}
ARCHETYPE_LONG = {
    1: "Half Expected-Move Mean-Reversion Fade", 2: "King Node Absorption Reversal",
    3: "3-Ticker Alignment Breakout", 4: "1.0 Expected-Move Boundary Runner",
}


DAY_NAME = {1: "Calm day", 2: "Normal day", 3: "Fast day"}


def eligible_archetypes(c6: float) -> Dict[str, List[int]]:
    """The desk's November rules (#the-4-setups, pinned 2026-11-17): the VIX band decides which TWO setups run.
    Calm (VIX < 15): S1 shelf fade + S2 rejection · Normal (15–18.5): S2 rejection + S3 three-ticker break ·
    Fast (> 18.5): S3 three-ticker break + S4 shelf break runner. S2 is only allowed with VIX 18.5 or under."""
    r = regime_code(c6)
    if r == 1:
        return {"valid": [1, 2], "banned": [3, 4], "note": "Calm day (VIX under 15): S1 shelf fade and S2 rejection. Fades toward the middle."}
    if r == 2:
        return {"valid": [2, 3], "banned": [1, 4], "note": "Normal day (VIX 15 to 18.5): S2 rejection and S3 three-ticker break."}
    return {"valid": [3, 4], "banned": [1, 2], "note": "Fast day (VIX above 18.5): S3 three-ticker break and S4 shelf break runner. "
            "Breaks beyond the shelves tend to run — the desk never fades a move today."}


# ── C27–C31 and the credit-spread sizing formula ──────────────────────────────
@dataclass
class Sizing:
    c19: float
    c27: float
    c28: float
    c29: int
    c30: float
    c31: float
    zero_dte_limit: int

    def as_dict(self):
        return asdict(self)


def sizing(c19: float, c27: float, c28: float, zero_dte_buffer_pct: float = 20.0) -> Sizing:
    c30 = round(c27 * c28 * 100.0, 6)                             # 8 × 0.55 × 100 is 440 exactly, not 440.00000000000006
    c29 = int(c19 / c30 + 1e-9) if c30 > 0 else 0                 # INT() truncates; epsilon guards float noise
    c31 = c29 * c30
    zero = int(c19 * (1 - zero_dte_buffer_pct / 100.0) / c30 + 1e-9) if c30 > 0 else 0   # Ch.5: 15–20 % premium buffer
    return Sizing(c19=c19, c27=c27, c28=c28, c29=c29, c30=c30, c31=c31, zero_dte_limit=zero)


def credit_spread_contracts(c19: float, width: float, credit: float) -> Dict[str, float]:
    """Credit Spread Vault: Max Loss per Contract = (Wing Width − Credit) × 100; contracts = INT(C19 / max loss)."""
    max_loss = round(max(width - credit, 0.0) * 100.0, 6)
    n = int(c19 / max_loss + 1e-9) if max_loss > 0 else 0
    return {"max_loss_per_contract": max_loss, "contracts": n, "max_gain_per_contract": credit * 100.0}


# ── Gap Re-Anchor Engine C37–C46 ──────────────────────────────────────────────
@dataclass
class GapEngine:
    c10: Optional[float]
    c37: Optional[float]
    c38: str
    active: bool
    c39: float
    c40: float
    c41: float
    c42: float
    c43: float
    c44: float
    c45: float
    c46: float

    def as_dict(self):
        return asdict(self)


def gap_engine(c5: float, c6: float, c13: float, c17: float, c10: Optional[float]) -> GapEngine:
    blank = c10 is None or (isinstance(c10, float) and (math.isnan(c10) or c10 <= 0))
    if blank:
        c37, c38, c39, active = None, C38_STANDARD_BLANK, c5, False
    else:
        drift = (c10 - c5) / c5 * 100.0
        c37 = drift
        active = (c10 > c13) or (c10 < c17) or (abs(drift) >= 0.75)
        c38 = C38_ACTIVE if active else C38_STANDARD_BELOW
        c39 = c10 if active else c5
    c40 = c39 * (c6 / 100.0) * SQRT_1_252
    return GapEngine(
        c10=None if blank else c10, c37=c37, c38=c38, active=active, c39=c39, c40=c40,
        c41=c39 + c40 / 2, c42=c39 - c40 / 2,
        c43=round_to_strike(c39 + c40 * 0.52), c44=round_to_strike(c39 - c40 * 0.52),
        c45=round_to_strike(c39 + c40 * 1.25), c46=round_to_strike(c39 - c40 * 1.25),
    )


# ── the desk bot's STRIKE GRID (#premarket-math) ───────────────────────────────
@dataclass
class StrikeGrid:
    """'SPX Strike Grid (EM levels rounded to 5)' — the bot's parametric model, not an OI scan."""
    anchor: float
    em: float
    call_node: float      # (+0.5 EM) rounded to strike
    put_node: float       # (−0.5 EM)
    upper_wall: float     # (+1.0 EM)
    lower_wall: float     # (−1.0 EM)
    call_fence: float     # (+1.25 EM) short call strictly above
    put_fence: float      # (−1.25 EM) short put strictly below
    step: float

    def as_dict(self):
        return asdict(self)


def fence_levels(anchor: float, em: float, step: float = 5.0) -> Tuple[float, float]:
    """#credit-spreads (2026-11-17): strikes sit 'past the wall by 5 pts, or at the 1.25× fence, whichever is farther'.
    Verified against the 8:30 posts of Nov 17 (7550 / 7285) and Nov 18 (7480 / 7200)."""
    call_f = max(round_to_strike(anchor + em, step) + step, round_to_strike(anchor + 1.25 * em, step))
    put_f = min(round_to_strike(anchor - em, step) - step, round_to_strike(anchor - 1.25 * em, step))
    return call_f, put_f


def strike_grid(anchor: float, em: float, step: float = 5.0) -> StrikeGrid:
    """King Nodes = the shelves rounded to the nearest 5-pt strike ('S2 levels'; the desk: 'they are not option data').
    Walls rounded. Fences per fence_levels()."""
    cf, pf = fence_levels(anchor, em, step)
    return StrikeGrid(
        anchor=anchor, em=em, step=step,
        call_node=round_to_strike(anchor + 0.5 * em, step), put_node=round_to_strike(anchor - 0.5 * em, step),
        upper_wall=round_to_strike(anchor + em, step), lower_wall=round_to_strike(anchor - em, step),
        call_fence=cf, put_fence=pf,
    )


@dataclass
class ProxyGrid:
    """SPY (dollars, same VIX, own prior close) and /ES (points, 08:20 AM ET price) blocks of the bot post."""
    name: str
    anchor: float
    em: float
    shelf_lo: float
    shelf_hi: float
    band_lo: float
    band_hi: float
    put_node: float
    call_node: float
    put_fence: float
    call_fence: float
    step: float

    def as_dict(self):
        return asdict(self)


def proxy_grid(name: str, anchor: float, c6: float, step: float) -> ProxyGrid:
    em = daily_em(anchor, c6)
    g = strike_grid(anchor, em, step)
    return ProxyGrid(name=name, anchor=anchor, em=em, shelf_lo=anchor - em / 2, shelf_hi=anchor + em / 2,
                     band_lo=anchor - em, band_hi=anchor + em, put_node=g.put_node, call_node=g.call_node,
                     put_fence=g.put_fence, call_fence=g.call_fence, step=step)


def beyond_0dte(anchor: float, em: float, sessions: List[int], round_em: bool = True) -> List[Dict[str, float]]:
    """'SPX Beyond 0DTE (daily EM x sqrt(sessions))'. The desk bot multiplies the EM it prints (2 decimals), so
    round_em=True reproduces its numbers; 5 sessions equals C18 to within a cent or two."""
    out = []
    base = round(em, 2) if round_em else em
    for n in sessions:
        e = base * math.sqrt(n)
        out.append({"sessions": n, "em": e, "lo": anchor - e, "hi": anchor + e})
    return out


def ac1_stop_levels(c14: float, c16: float, pts: float = 8.0) -> Dict[str, float]:
    """Archetype 1 structural stop: a 5-minute close more than 8 pts beyond the 0.5 shelf."""
    return {"above_c14": c14 + pts, "below_c16": c16 - pts}


def meic_strikes(c13: float, c17: float, step: float = 5.0, width: float = 10.0) -> Dict[str, float]:
    """MEIC standard day (Credit Spread Vault blueprint): 'Upper Wall 7,747 -> Bear Call 7,750/7,760; Lower Wall 7,601 ->
    Bull Put 7,595/7,585'. That is one listed strike beyond the rounded Strike Wall (±1.0 EM rounded to 5), 10-wide wings —
    the 'short strike 3 to 5 points beyond the wall' of the manual, resolved onto the 5-point SPX grid."""
    sc = round_to_strike(c13, step) + step
    sp = round_to_strike(c17, step) - step
    return {"short_call": sc, "long_call": sc + width, "short_put": sp, "long_put": sp - width,
            "upper_strike_wall": round_to_strike(c13, step), "lower_strike_wall": round_to_strike(c17, step)}


def desk_gap_levels(open_px: float, c6: float) -> Dict[str, float]:
    """#reading-the-levels (2026-11-17): on a gap morning 'the same formula with today's open as the middle'. Verified on
    Nov 9: close 7376.86, open 7443.53, VIX ≈ 23.45 → new upper shelf 7498.51. The live tickets use these levels; the 08:30
    levels stay on the chart as gap-fill targets."""
    em = open_px * (c6 / 100.0) * math.sqrt(1.0 / 252.0)
    g = {"middle": open_px, "em": em, "C13": open_px + em, "C14": open_px + 0.5 * em, "C15": open_px, "C16": open_px - 0.5 * em, "C17": open_px - em}
    g["call_node"], g["put_node"] = round_to_strike(g["C14"]), round_to_strike(g["C16"])
    g["call_fence"], g["put_fence"] = fence_levels(open_px, em)
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in g.items()}


def if_it_breaks(g: StandardGrid, gex: Optional[Dict] = None) -> str:
    """The 8:30 post's 'If it breaks' line: room from each shelf to the next level, with any GEX level on the way."""
    def on_way(lo: float, hi: float) -> str:
        if not gex:
            return ""
        hits = [f"{k} {v:,.0f}" for k, v in (("put wall", gex.get("put_wall")), ("call wall", gex.get("call_wall")), ("flip", gex.get("flip")))
                if v and lo < v < hi]
        return f" ({', '.join(hits)} on the way)" if hits else ""
    down = f"below {g.c16:,.2f}, the next level is {g.c17:,.2f}, {g.c16 - g.c17:,.0f} pts lower{on_way(g.c17, g.c16)}"
    up = f"Above {g.c14:,.2f}, the next level is {g.c13:,.2f}, {g.c13 - g.c14:,.0f} pts higher{on_way(g.c14, g.c13)}"
    return f"If it breaks: {down}. {up}."


SIZE_ACCOUNTS = (50_000, 100_000, 250_000, 500_000)


def size_table(risk_pts: float, pct: float = 0.01, b_grade: bool = False) -> Dict[str, str]:
    """The ticket's SIZE line: stop in SPX points × $100 per SPX contract, a tenth per XSP, at 1 % of the account (B-grade: half)."""
    out = {}
    per_spx = risk_pts * 100.0; per_xsp = per_spx / 10.0
    for acct in SIZE_ACCOUNTS:
        budget = acct * pct * (0.5 if b_grade else 1.0)
        n_spx = int(budget // per_spx) if per_spx else 0
        n_xsp = int(budget // per_xsp) if per_xsp else 0
        out[f"${acct // 1000}k"] = f"{n_spx} SPX" if n_spx >= 1 else f"{n_xsp} XSP"
    return out


def micro_desk(grid: StandardGrid, sg: "StrikeGrid") -> Dict[str, Dict[str, float]]:
    """Discord 'Micro Desk Protocol' for accounts under $25k: XSP trades at exactly 1/10th of SPX with identical cash
    settlement; for SPY 'divide all workstation SPX levels by 10 (e.g., SPX 5,850 = SPY 585.00)'. (The desk bot's own
    SPY block instead re-anchors on SPY's prior close — both are shown in the app.)"""
    def tenth(x: float) -> float:
        return round(x / 10.0, 2)
    lv = {k: tenth(v) for k, v in grid.levels.items()}
    return {"XSP": {**lv, "em": tenth(grid.c12), "put_node": tenth(sg.put_node), "call_node": tenth(sg.call_node),
                    "put_fence": tenth(sg.put_fence), "call_fence": tenth(sg.call_fence)},
            "SPY_div10": dict(lv)}


def sizing_ladder(c19: float, c27: float, c28: float) -> Dict[str, Sizing]:
    """C29 at 1R, at 0.75R (Balanced credit protocol) and at 0.5R ('Fade with 0.5R limit', C24 Positive Gamma);
    XSP/SPY use one-tenth of the SPX stop distance."""
    return {"1R": sizing(c19, c27, c28), "0.75R": sizing(c19 * 0.75, c27, c28), "0.5R": sizing(c19 * 0.5, c27, c28),
            "XSP 1R": sizing(c19, c27 / 10.0, c28), "SPY 1R": sizing(c19, c27 / 10.0, c28)}


def sanity_check(grid: StandardGrid) -> Dict[str, object]:
    """Ch.3 08:33 sanity check: VIX 15 ≈ 0.95 %, VIX 12 ≈ 0.75 %, VIX 20 ≈ 1.25 % of the index."""
    pct = grid.em_pct
    expected = grid.c6 * SQRT_1_252            # = C6 × 0.06299 %
    ok = abs(pct - expected) < 1e-9
    sym = abs((grid.c13 - grid.c15) - (grid.c15 - grid.c17)) < 1e-9
    return {"em_pct": pct, "rule_of_thumb": expected, "passes": ok and sym, "symmetric_walls": sym}
