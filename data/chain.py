"""
chain.py — pure calculations on the normalised chain (one row per strike, c_* / p_*). No I/O.

    oi_king_node    Ch.4 definition: the strike with the largest combined call + put open interest within ~1 EM of the
                    close; if two are within the tie band, the one nearer the cash close dominates.
    gex_profile     dealer gamma exposure per strike (call OI × gamma − put OI × gamma) × 100 — the 'air pocket check'
                    of Archetype 4 (minimal concentration between the 0.5 shelf and the 1.0 wall).
    straddle        ATM straddle mark, the market's own 1-day expected move for comparison with C12.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd


def within_em(chain: pd.DataFrame, anchor: float, em: float, mult: float = 1.0) -> pd.DataFrame:
    if chain is None or chain.empty:
        return chain
    return chain[(chain["strike"] >= anchor - mult * em) & (chain["strike"] <= anchor + mult * em)].copy()


def oi_king_node(chain: pd.DataFrame, anchor: float, em: float, tie_band_pct: float = 10.0, top_n: int = 5) -> Optional[Dict]:
    band = within_em(chain, anchor, em)
    if band is None or band.empty or band["total_oi"].max() <= 0:
        return None
    vmax = float(band["total_oi"].max())
    tied = band[band["total_oi"] >= vmax * (1 - tie_band_pct / 100)]
    best = tied.iloc[(tied["strike"] - anchor).abs().argsort()].iloc[0]
    top = band.sort_values("total_oi", ascending=False).head(top_n)
    return {
        "strike": float(best["strike"]), "total_oi": float(best["total_oi"]), "c_oi": float(best["c_oi"]),
        "p_oi": float(best["p_oi"]), "tie_break": bool(len(tied) > 1),
        "top": [{"strike": float(r["strike"]), "total_oi": float(r["total_oi"]), "c_oi": float(r["c_oi"]),
                 "p_oi": float(r["p_oi"]), "volume": float(r.get("total_volume", 0))} for _, r in top.iterrows()],
        "call_max": {"strike": float(band.loc[band["c_oi"].idxmax(), "strike"]), "oi": float(band["c_oi"].max())},
        "put_max": {"strike": float(band.loc[band["p_oi"].idxmax(), "strike"]), "oi": float(band["p_oi"].max())},
    }


def gex_profile(chain: pd.DataFrame, anchor: float, em: float, mult: float = 1.5) -> pd.DataFrame:
    band = within_em(chain, anchor, em, mult)
    if band is None or band.empty:
        return pd.DataFrame(columns=["strike", "call_gex", "put_gex", "net_gex"])
    o = band.copy()
    o["call_gex"] = np.round(o["c_oi"] * o["c_gamma"] * 100, 0)
    o["put_gex"] = -np.round(o["p_oi"] * o["p_gamma"] * 100, 0)
    o["net_gex"] = o["call_gex"] + o["put_gex"]
    return o[["strike", "c_oi", "p_oi", "total_oi", "c_volume", "p_volume", "call_gex", "put_gex", "net_gex"]]


def air_pocket(chain: pd.DataFrame, shelf: float, wall: float) -> Dict[str, float]:
    """Archetype 4 setup requirement: open interest between the 0.5 shelf and the 1.0 wall should be minimal."""
    lo, hi = min(shelf, wall), max(shelf, wall)
    seg = chain[(chain["strike"] > lo) & (chain["strike"] < hi)] if chain is not None else pd.DataFrame()
    total = float(chain["total_oi"].sum()) if chain is not None and not chain.empty else 0.0
    inside = float(seg["total_oi"].sum()) if not seg.empty else 0.0
    return {"oi_between": inside, "share_of_chain": (inside / total * 100) if total else 0.0,
            "max_strike": float(seg.loc[seg["total_oi"].idxmax(), "strike"]) if not seg.empty and seg["total_oi"].max() > 0 else None}


def straddle(chain: pd.DataFrame, spot: float) -> Optional[Dict[str, float]]:
    if chain is None or chain.empty or not spot:
        return None
    atm = float(chain.iloc[(chain["strike"] - spot).abs().argsort()].iloc[0]["strike"])
    row = chain[chain["strike"] == atm].iloc[0]
    c, p = float(row.get("c_mark", 0)), float(row.get("p_mark", 0))
    if c <= 0 or p <= 0:
        return None
    return {"atm": atm, "call": c, "put": p, "straddle": round(c + p, 2), "implied_em_approx": round((c + p) * 0.8, 2)}
