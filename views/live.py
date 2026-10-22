"""live.py — one live snapshot of the desk per poll, shared by the Desk page, the MEIC tab and the sidebar alert watcher,
so every page sees the same state and the alerts never depend on which page is open.

Rules input = what is final when the feed was read (core/live.py): closed 5-minute bars (+ the forming bar's open for S4),
closed 1-minute bars for the Scenario Book send rule. The live price and the ARMED heads-up use the forming bar."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, Optional

import pandas as pd
import streamlit as st

from core import execution as X
from core import live as L
from core import meic as MC
from core import rules as R
from core import workstation as ws
from data import fetcher as F
from utils.timeutil import minutes_of, now_et
from views import common as U


@dataclass
class Snap:
    ok: bool
    sess: date
    now: datetime
    m: int
    today: bool
    plan: Dict
    label: str
    locked: bool = False
    error: str = ""
    px1: Optional[pd.DataFrame] = None
    px_src: str = ""
    five: bool = False
    shift: int = 5
    last: Optional[float] = None
    last_t: Optional[str] = None
    day5: Optional[pd.DataFrame] = None            # all regular-session 5-min bars incl. the forming one
    day5_closed: Optional[pd.DataFrame] = None
    day5_known: Optional[pd.DataFrame] = None
    spy: Optional[pd.DataFrame] = None
    qqq: Optional[pd.DataFrame] = None
    lv: Dict = field(default_factory=dict)
    grid: Dict = field(default_factory=dict)
    gate: object = None
    live_s: Optional[Dict] = None
    banner: Optional[X.Banner] = None
    score: object = None
    chain: Optional[pd.DataFrame] = None
    chain_src: Dict = field(default_factory=dict)
    vix_now: Optional[float] = None
    bar: Dict = field(default_factory=dict)
    ticket: Optional[Dict] = None
    three: Optional[Dict] = None
    fetched_at: Optional[datetime] = None


def size_text(plan: Dict) -> str:
    sz = plan["sizing"]
    n = sz.get("c29", 0)
    if n:
        return f"{n} SPX contract{'s' if n != 1 else ''} at Δ {sz.get('c28', 0.55):.2f} (Row 29)"
    xsp = ws.sizing(sz.get("c19", 0.0), max(sz.get("c27", 8.0) / 10.0, 0.01), sz.get("c28", 0.55)).c29
    return f"0 SPX at this stop → {xsp} XSP (or {xsp} SPY), Micro Desk"


def _key(cfg: Dict, now: datetime):
    return (U.bucket(), now.strftime("%H:%M"), cfg["session"].isoformat(), cfg.get("rules_feed"), cfg.get("price_symbol"),
            str(cfg.get("interval")), json.dumps(cfg.get("overrides", {}), sort_keys=True), cfg.get("c10"), cfg["c8"], cfg["c9"],
            cfg["c27"], cfg["c28"], cfg["vix_print"], cfg["es_print"], cfg.get("cboe", None))


def snapshot(cfg: Dict) -> Snap:
    now = now_et()
    key = _key(cfg, now)
    memo = st.session_state.get("_az_snap")
    if not isinstance(memo, dict):
        memo = st.session_state["_az_snap"] = {}
    if key in memo:
        return memo[key]
    s = _build(cfg, now)
    if len(memo) >= 4:                                  # one entry per session per poll-minute is all that is ever reused
        memo.clear()
    memo[key] = s
    return s


def _build(cfg: Dict, now: datetime) -> Snap:
    sess: date = cfg["session"]
    m = minutes_of(now)
    plan, label = U.get_plan(cfg)
    snap = Snap(ok=bool(plan.get("ok")), sess=sess, now=now, m=m, today=(sess == now.date()), plan=plan, label=label)
    if not plan.get("ok"):
        snap.error = f"Feeds did not return C5/C6 for {sess}: {plan.get('notes')}. Use the overrides in the sidebar or try again."
        return snap
    snap.locked = label.startswith("LOCKED")
    five = str(cfg.get("interval", "1-minute")).startswith("5")
    days_back = max(0, (now.date() - sess).days)
    n_bars = min(2000, 400 + days_back * 300) if five else min(5000, 1400 + days_back * 1440)   # a 24-hour feed prints ~1,400 1-min bars a day
    snap.px1, snap.px_src = U.price_bars(cfg["price_symbol"], "5" if five else "1", n_bars, U.bucket())
    snap.five, snap.shift = five, (0 if five else 5)        # on the 1-minute view the 5-minute bar's close is 5 minutes after its stamp
    if cfg.get("rules_feed", "").startswith("Price"):
        spx5, _ = U.price_bars(cfg["price_symbol"], "5", 400, U.bucket())
    else:
        spx5, _ = U.bars("SPX", "5", 400, U.bucket())
    spy5, _ = U.bars("SPY", "5", 400, U.bucket())
    qqq5, _ = U.bars("QQQ", "5", 400, U.bucket())
    snap.fetched_at = L.fetched_at(spx5, now)
    day5 = F.session_slice(spx5, sess)
    day_spy, day_qqq = F.session_slice(spy5, sess), F.session_slice(qqq5, sess)
    fa_spy, fa_qqq = L.fetched_at(spy5, now), L.fetched_at(qqq5, now)
    snap.day5, snap.spy, snap.qqq = day5, day_spy, day_qqq
    snap.day5_closed = L.closed(day5, 5, snap.fetched_at)
    snap.day5_known = L.known(day5, 5, snap.fetched_at)
    spy_closed, qqq_closed = L.closed(day_spy, 5, fa_spy), L.closed(day_qqq, 5, fa_qqq)
    spy_known, qqq_known = L.known(day_spy, 5, fa_spy), L.known(day_qqq, 5, fa_qqq)
    snap.last, snap.last_t = F.latest(snap.px1)
    lv = R.rule_levels(plan)
    snap.lv = lv
    snap.grid = {k: lv[k] for k in ("C13", "C14", "C15", "C16", "C17")}
    snap.gate = R.gate_test(snap.day5_closed) if not snap.day5_closed.empty else None
    snap.live_s = (R.live_status(snap.day5_known, spy_known, qqq_known, snap.grid, lv["em"], lv["put_node"], lv["call_node"],
                                 plan["inputs"]["c6"]) if not snap.day5_known.empty else None)
    snap.chain, snap.chain_src = U.chain(plan["expiries"][0], "SPX", U.bucket())
    b = X.banner(plan, lv, day5, snap.last, m, snap.gate, snap.live_s, snap.chain, snap.locked, snap.chain_src,
                 session_ahead=(sess > now.date()), past_session=(sess < now.date()), closed_bars=snap.day5_closed)
    vix1, _ = U.bars("VIX", "1", 300, U.bucket())
    snap.vix_now = F.latest(F.session_slice(vix1, sess))[0] if vix1 is not None else None
    if b.state in ("ACTIVE", "DONE") and snap.live_s and snap.live_s.get("chosen") is not None:
        from core import scoring as SCR
        spx1, _ = U.bars("SPX", "1", 800, U.bucket())
        spx1_closed = L.closed(F.session_slice(spx1, sess), 1, L.fetched_at(spx1, now))
        snap.score = SCR.score_idea(snap.live_s["chosen"], plan, lv, snap.day5_known, spy_known, qqq_known, snap.gate,
                                    snap.vix_now, spx1_closed, m)
        b.score = snap.score.as_dict()
    snap.banner = b
    snap.bar = L.bar_clock(now, 5)
    snap.ticket = MC.ticket(plan)
    if 3 in plan["eligible"]["valid"]:
        snap.three = L.three_ticker(day5, snap.day5_closed, day_spy, spy_closed, day_qqq, qqq_closed, lv["em"])
    return snap
