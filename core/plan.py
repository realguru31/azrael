"""
plan.py — builds the session plan the way the desk bot does, from feeds, and freezes it at 08:30.

    C5  SPX previous cash close      official close of the prior session (daily bar)
    C6  VIX                          the 08:15 ET 1-minute print (desk bot); 08:30 per the sheet — configurable
    C7  /ES overnight drift %        /ES 08:20 ET price vs the prior /ES daily settle, in percent
    C10 09:30 cash open              filled at 09:31 on gap days (auto from the 09:30 SPX bar, or typed)
    SPY block                        SPY prior close, same VIX      /ES block   08:20 price, same VIX

Lock tiers: (1) store/baseline/<session>.json written by CI at 08:31 ET or by the app at the lock,
(2) a lock taken by this app instance after 08:30, (3) provisional live values before 08:30.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, Optional, Tuple

import pandas as pd

from core import workstation as ws
from data import fetcher as F
from data import chain as CH
from data import storage as S
from utils.timeutil import (ET, T_MATH, minutes_of, now_et, session_date, upcoming_expiries, trading_days_between,
                            is_trading_day, prev_trading_day)


def build_plan(session: date, vix_print: str = "08:15", es_print: str = "08:20", c8: float = 25000.0, c9: float = 1.0,
               c27: float = 8.0, c28: float = 0.55, overrides: Optional[Dict] = None, creds=None,
               c10: Optional[float] = None) -> Dict:
    """Everything the workstation and the strike grid need, from live feeds. JSON-serialisable."""
    overrides = overrides or {}
    vh, vm = (int(x) for x in vix_print.split(":"))
    eh, em_ = (int(x) for x in es_print.split(":"))
    notes = {}

    # C5 — SPX prior cash close
    c5, c5_date, spx_src = F.prior_close("SPX", session, creds)
    if overrides.get("c5"):
        c5, notes["c5"] = float(overrides["c5"]), "manual override"
    elif c5 is None:
        u = F.cboe_underlying("SPX")
        c5 = u.get("prev_day_close") if u else None
        notes["c5"] = "CBOE prev_day_close (tvDatafeed unavailable)"
    else:
        notes["c5"] = f"{spx_src} daily close {c5_date}"

    # C6 — VIX print
    vix1, vix_src = F.get_bars("VIX", "1", 1400, creds)
    c6, c6_note = F.print_at(vix1, session, vh, vm)
    vix_live, vix_live_t = F.latest(vix1)
    if overrides.get("c6"):
        c6, c6_note = float(overrides["c6"]), "manual override"
    elif c6 is None:
        c6, c6_note = vix_live, f"latest VIX ({vix_live_t}) — {vix_print} print not available yet"
    notes["c6"] = f"{vix_src} {c6_note}" if c6_note else vix_src

    # C7 — /ES drift: 08:20 price vs prior settle
    es1, es_src = F.get_bars("ES", "1", 1400, creds)
    es_print_px, es_note = F.print_at(es1, session, eh, em_)
    es_live, es_live_t = F.latest(es1)
    es_settle, es_settle_date, _ = F.futures_settle("ES", session, creds)
    if es_settle is None:
        es_settle, es_settle_date, _ = F.prior_close("ES", session, creds)
    if es_print_px is None:
        es_print_px, es_note = es_live, f"latest /ES ({es_live_t})"
    c7 = None
    if overrides.get("c7") not in (None, ""):
        c7, notes["c7"] = float(overrides["c7"]), "manual override"
    elif es_print_px and es_settle:
        c7 = (es_print_px / es_settle - 1) * 100
        notes["c7"] = f"{es_src} {es_note} {es_print_px:.2f} vs settle {es_settle:.2f} ({es_settle_date})"
    else:
        notes["c7"] = "unavailable"
    on_hi, on_lo = F.overnight_range(es1, session)
    px1, px_src = F.get_bars("PROXY", "1", 1400, creds)
    px_hi, px_lo = F.overnight_range(px1, session)
    # convert the /ES overnight range to SPX points with the prior-16:00 basis (ES at the prior cash close minus C5)
    prev_sess = prev_trading_day(session)
    es_1600_prev, _ = F.print_at(es1, prev_sess, 16, 0)
    basis = (es_1600_prev - c5) if (es_1600_prev and c5) else (es_settle - c5 if (es_settle and c5) else None)
    pm_hi = (on_hi - basis) if (on_hi is not None and basis is not None) else None
    pm_lo = (on_lo - basis) if (on_lo is not None and basis is not None) else None
    # proxy (Capital.com SPX500 CFD) basis at the prior 16:00 — usually a few points; used to shift the proxy line onto SPX
    px_1600_prev, _ = F.print_at(px1, prev_sess, 16, 0)
    proxy_basis = (px_1600_prev - c5) if (px_1600_prev and c5) else 0.0
    if px_hi is not None and px_lo is not None:
        pm_hi, pm_lo = px_hi - proxy_basis, px_lo - proxy_basis
    # prior session high / low (SPX daily bar)
    spx_d, _ = F.daily("SPX", 8, creds)
    prev_hi = prev_lo = None
    if spx_d is not None and not spx_d.empty:
        d = spx_d[[x.date() < session for x in spx_d.index]]
        if not d.empty:
            prev_hi, prev_lo = float(d["high"].iloc[-1]), float(d["low"].iloc[-1])

    if c5 is None or c6 is None:
        return {"ok": False, "session": session.isoformat(), "notes": notes, "error": "missing C5 or C6"}

    g = ws.standard_grid(c5, c6)
    sg = ws.strike_grid(g.c15, g.c12)
    sizing = ws.sizing(ws.max_1r(c8, c9), c27, c28)
    gap = ws.gap_engine(c5, c6, g.c13, g.c17, c10)
    ladder = ws.beyond_0dte(g.c15, g.c12, [2, 3, 4, 5])
    exps = upcoming_expiries(session, 5)

    # SPY / ES proxies (the bot's 'Same Map on SPY and /ES')
    spy_c5, _, spy_src = F.prior_close("SPY", session, creds)
    spy_grid = ws.proxy_grid("SPY", spy_c5, c6, 1.0).as_dict() if spy_c5 else None
    es_grid = ws.proxy_grid("/ES", es_print_px, c6, 5.0).as_dict() if es_print_px else None

    # Live chain (CBOE, delayed) — the book's OI King Node and the air-pocket check
    chain = F.cboe_chain(session.isoformat(), "SPX")
    oi_node = CH.oi_king_node(chain, g.c15, g.c12) if chain is not None else None
    air_up = CH.air_pocket(chain, g.c14, g.c13) if chain is not None else None
    air_dn = CH.air_pocket(chain, g.c16, g.c17) if chain is not None else None

    return {
        "ok": True, "session": session.isoformat(), "built_at": now_et().strftime("%Y-%m-%d %H:%M:%S ET"),
        "inputs": {"c5": c5, "c6": c6, "c7": c7, "c8": c8, "c9": c9, "c10": gap.c10, "c27": c27, "c28": c28,
                   "vix_print": vix_print, "es_print": es_print, "es_print_px": es_print_px, "es_settle": es_settle,
                   "vix_live": vix_live, "es_live": es_live, "on_high": on_hi, "on_low": on_lo, "spy_c5": spy_c5,
                   "es_basis": basis, "pm_high_spx": pm_hi, "pm_low_spx": pm_lo, "prev_high": prev_hi, "prev_low": prev_lo,
                   "proxy_basis": proxy_basis, "proxy_src": px_src},
        "stop_clusters": {"pre_market_high": pm_hi, "pre_market_low": pm_lo, "prior_session_high": prev_hi,
                          "prior_session_low": prev_lo,
                          "round_hundreds": [h for h in range(int(g.c17 // 100 + 1) * 100, int(g.c13 // 100) * 100 + 1, 100)]},
        "micro": ws.micro_desk(g, sg),
        "notes": notes,
        "grid": g.as_dict(), "levels": g.levels, "regime": ws.regime_code(c6),
        "c22": ws.c22(c6), "c23": ws.c23(c7), "c24": ws.c24(c6), "character": ws.regime_character(c6),
        "eligible": ws.eligible_archetypes(c6), "sizing": sizing.as_dict(), "gap": gap.as_dict(),
        "strike_grid": sg.as_dict(), "beyond": ladder, "expiries": [e.isoformat() for e in exps],
        "spy": spy_grid, "es": es_grid, "oi_node": oi_node, "air_pocket": {"up": air_up, "down": air_dn},
        "sources": {"spx": spx_src, "vix": vix_src, "es": es_src, "spy": spy_src,
                    "chain": "CBOE delayed" if chain is not None else "unavailable"},
        "sanity": ws.sanity_check(g),
    }


def rebuild_from_inputs(plan: Dict, c8: float, c9: float, c27: float, c28: float, c10: Optional[float]) -> Dict:
    """Re-derive the outputs from locked C5/C6/C7 when the user changes C8/C9/C27/C28 or enters C10 — the
    locked inputs never change."""
    i = plan["inputs"]
    g = ws.standard_grid(i["c5"], i["c6"])
    gap = ws.gap_engine(i["c5"], i["c6"], g.c13, g.c17, c10)
    p = dict(plan)
    p["inputs"] = {**i, "c8": c8, "c9": c9, "c27": c27, "c28": c28, "c10": gap.c10}
    p["sizing"] = ws.sizing(ws.max_1r(c8, c9), c27, c28).as_dict()
    p["gap"] = gap.as_dict()
    return p


def lock_status(session: date, plan: Dict) -> Tuple[str, Dict]:
    """Apply the tiers. Returns (tier_label, plan_to_show)."""
    key = session.isoformat()
    saved = S.load_baseline(key)
    if saved and saved.get("ok"):
        return f"LOCKED {saved.get('locked_at', '08:30')} · {saved.get('lock_source', 'file')}", saved
    now = now_et()
    if session == now.date() and minutes_of(now) >= T_MATH and plan.get("ok"):
        plan = dict(plan)
        plan["locked_at"] = now.strftime("%H:%M ET")
        plan["lock_source"] = "app lock (first load after 08:30)"
        S.save_baseline(key, plan)
        return f"LOCKED {plan['locked_at']} · app", plan
    return "PROVISIONAL · locks at 08:30 ET", plan


def unlock(session: date) -> None:
    p = S.baseline_path(session.isoformat())
    import os
    if os.path.exists(p):
        os.remove(p)
