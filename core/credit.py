"""
credit.py — the Systematic Credit Spread framework (#credit-spread-vault), as pure functions.

    MEIC (standard day): bear call short 3–5 pts above C13, bull put short 3–5 pts below C17, 10-wide wings.
    Gap day (C10 active): short call strictly above C45, short put strictly below C46 (1.25 × EM fences).
    Desk bot: 'Short wings must sit strictly beyond <put fence>P / <call fence>C. Never sell premium between King Nodes.'
    Regime protocol: Positive = double-sided MEIC, full 1R · Balanced = single-sided preferred, extra 3–5 buffer,
    size −25 % · Negative = condors banned, directional only, 15–20 wide, size −50 %, VIX > 22 = zero trades.
    Sizing: max loss per contract = (width − credit) × 100; contracts = INT(C19 / max loss).
    Defence: 5-point test (roll out 1 day, 5 wider, or take the loss) · regime flip to Negative = close at market.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

import pandas as pd

from core.workstation import credit_spread_contracts, regime_code


@dataclass
class SpreadLeg:
    kind: str            # "bear_call" | "bull_put"
    short: float
    long: float
    width: float
    short_mark: Optional[float] = None
    long_mark: Optional[float] = None
    credit: Optional[float] = None
    max_loss_per_contract: Optional[float] = None
    contracts_1r: Optional[int] = None
    prob_note: str = ""

    def as_dict(self):
        return asdict(self)


def regime_protocol(c6: float) -> Dict[str, object]:
    r = regime_code(c6)
    if r == 1:
        return {"regime": r, "structure": "Double-sided MEIC Iron Condor (premier harvest regime)", "allowed": True,
                "single_sided_only": False, "size_factor": 1.00, "buffer_extra": 0.0, "width": 10.0,
                "expiry": "0DTE on clear Positive-Gamma days with balanced overnight inventory; 1DTE if the open is ambiguous",
                "notes": ["Full 1R allocation.", "Short strikes 3–5 pts outside C13/C17 (C45/C46 on gap days)."]}
    if r == 2:
        return {"regime": r, "structure": "Single-sided credit spread preferred (Bull Put OR Bear Call)", "allowed": True,
                "single_sided_only": True, "size_factor": 0.75, "buffer_extra": 3.0, "width": 10.0,
                "expiry": "1DTE preferred (insulates against the opening 20-minute whipsaw); 2DTE when ambiguity is high",
                "notes": ["Align the side with the morning auction bias from the scenario map.",
                          "Extra 3–5 pt buffer beyond the 1.0 walls; condor size −25 % (0.75R).",
                          "Desk bot: credit spreads viable after 11:30 once price has confirmed a range between the King Nodes."]}
    if c6 > 22:
        return {"regime": r, "structure": "NO CREDIT SPREAD TRADES (VIX > 22 circuit breaker)", "allowed": False,
                "single_sided_only": True, "size_factor": 0.0, "buffer_extra": 0.0, "width": 15.0,
                "expiry": "—", "notes": ["Hard circuit breaker: zero credit spread trades until volatility normalises."]}
    return {"regime": r, "structure": "Directional credit spreads only — Iron Condors BANNED", "allowed": True,
            "single_sided_only": True, "size_factor": 0.50, "buffer_extra": 0.0, "width": 15.0,
            "expiry": "Far OTM, 15–20 point wings; size −50 %",
            "notes": ["Bull Put below C17 if bullish, Bear Call above C13 if bearish.",
                      "Out-of-bounds gap days carry extreme vega expansion risk — do not sell unhedged gamma."]}


def fences(c13: float, c17: float, c45: float, c46: float, gap_active: bool, buffer_pts: float = 3.0,
           extra: float = 0.0, step: float = 5.0) -> Dict[str, float]:
    """Where the short strikes may sit. Standard day: first listed strike at/beyond (wall ± buffer ± extra).
    Gap day: strictly beyond the C45/C46 fences."""
    if gap_active:
        return {"short_call_min": c45 + step, "short_put_max": c46 - step, "basis": "gap fences C45/C46 (strictly beyond)"}
    from core.workstation import round_to_strike
    n_extra = math.ceil(extra / step) * step if extra > 0 else 0.0          # Balanced: one more strike out
    sc_wall = round_to_strike(c13, step) + step + n_extra                  # manual / MEIC blueprint
    sp_wall = round_to_strike(c17, step) - step - n_extra
    sc = max(sc_wall, c45 + step)                                          # desk bot: strictly beyond the ±1.25 EM fence
    sp = min(sp_wall, c46 - step)
    return {"short_call_min": sc, "short_put_max": sp, "wall_call": sc_wall, "wall_put": sp_wall,
            "basis": f"strictly beyond the ±1.25 EM fences ({c46:,.0f}P / {c45:,.0f}C); the manual's wall-based strikes would be "
                     f"{sp_wall:,.0f} / {sc_wall:,.0f}"}


def _mark_at(chain: pd.DataFrame, strike: float, side: str) -> Optional[float]:
    if chain is None or chain.empty:
        return None
    row = chain[chain["strike"] == strike]
    if row.empty:
        return None
    col = "c_mark" if side == "call" else "p_mark"
    v = float(row.iloc[0][col]) if col in row else None
    return v if v and v > 0 else None


def build_leg(kind: str, short: float, width: float, chain: Optional[pd.DataFrame], c19: float,
              size_factor: float = 1.0) -> SpreadLeg:
    side = "call" if kind == "bear_call" else "put"
    long = short + width if kind == "bear_call" else short - width
    leg = SpreadLeg(kind=kind, short=short, long=long, width=width)
    leg.short_mark, leg.long_mark = _mark_at(chain, short, side), _mark_at(chain, long, side)
    if leg.short_mark is not None and leg.long_mark is not None:
        leg.credit = round(max(leg.short_mark - leg.long_mark, 0.0), 2)
        s = credit_spread_contracts(c19 * size_factor, width, leg.credit)
        leg.max_loss_per_contract, leg.contracts_1r = s["max_loss_per_contract"], s["contracts"]
    return leg


def meic_grid(c13: float, c17: float, c45: float, c46: float, gap_active: bool, c6: float, c19: float,
              chain: Optional[pd.DataFrame], buffer_pts: float = 3.0, step: float = 5.0) -> Dict[str, object]:
    proto = regime_protocol(c6)
    f = fences(c13, c17, c45, c46, gap_active, buffer_pts, proto["buffer_extra"], step)
    width = float(proto["width"])
    call_leg = build_leg("bear_call", f["short_call_min"], width, chain, c19, proto["size_factor"])
    put_leg = build_leg("bull_put", f["short_put_max"], width, chain, c19, proto["size_factor"])
    condor_credit = (call_leg.credit or 0) + (put_leg.credit or 0) if (call_leg.credit is not None and put_leg.credit is not None) else None
    condor = None
    if condor_credit is not None and proto["allowed"] and not proto["single_sided_only"]:
        s = credit_spread_contracts(c19 * proto["size_factor"], width, condor_credit)
        condor = {"credit": round(condor_credit, 2), "max_loss_per_contract": s["max_loss_per_contract"],
                  "contracts_1r": s["contracts"], "max_gain_per_contract": s["max_gain_per_contract"]}
    return {"protocol": proto, "fences": f, "bear_call": call_leg.as_dict(), "bull_put": put_leg.as_dict(), "condor": condor,
            "min_credit_for_one_lot": round(max(0.0, width - c19 * proto["size_factor"] / 100.0), 2)}


def five_point_test(spot: float, short_call: Optional[float], short_put: Optional[float]) -> List[str]:
    """Active defence: within 5 points of either short strike -> roll the tested wing out 1 day and 5 wider, or take the loss."""
    msgs = []
    if short_call is not None and short_call - spot <= 5:
        msgs.append(f"5-POINT TEST on the short call {short_call:.0f}: spot {spot:.2f} is {short_call - spot:.2f} pts away. "
                    f"Roll out 1 day / 5 wider for a credit or scratch — otherwise take the loss.")
    if short_put is not None and spot - short_put <= 5:
        msgs.append(f"5-POINT TEST on the short put {short_put:.0f}: spot {spot:.2f} is {spot - short_put:.2f} pts away. "
                    f"Roll out 1 day / 5 wider for a credit or scratch — otherwise take the loss.")
    return msgs


def regime_flip(c6_morning: float, vix_now: Optional[float]) -> Optional[str]:
    if vix_now is None:
        return None
    if regime_code(c6_morning) != 3 and regime_code(vix_now) == 3:
        return (f"REGIME FLIP: VIX {vix_now:.2f} is above 18.5 (morning C6 {c6_morning:.2f}). Close the entire Iron Condor at "
                f"market — the volatility-dampening premise has evaporated.")
    return None
