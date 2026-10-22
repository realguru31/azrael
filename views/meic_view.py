"""meic_view.py — #meic-condor-desk: the desk's 09:50 MEIC CONDOR DESK ticket, live.

Strikes, wings and defense triggers exactly as the desk posts them (core/meic.py), priced on the live chain (Barchart;
CBOE only as the flagged fallback), the payoff cage with the live SPX print, the 5-Point Defense Law and regime-flip
monitor (the sidebar watcher alerts on both from 09:50 to the close), the opening options flow, and Azraël's post-11:30
range-condor test for Balanced Gamma days."""
from __future__ import annotations

import json
import os

import streamlit as st

from core import meic as MC
from data import storage as S
from utils.timeutil import T_GATE_END, T_SHUTDOWN, fmt_hm
from views import cards as K
from views import common as U
from views import live as LV


def render(cfg, plan0, label0):
    poll = cfg["poll"] if cfg.get("auto", True) else None

    @st.fragment(run_every=poll)
    def live():
        _render(cfg)

    live()


def _flow_path(sess_iso: str) -> str:
    return os.path.join(S.STORE, "session", f"meic_flow_{sess_iso}.json")


def _opening_flow(s):
    """The desk prints calls vs puts traded 09:30–09:50. Read at 09:50–09:55 the 0DTE chain's day volume IS that window;
    the first such read is frozen for the day. Opened later, the page shows the cumulative flow and says so."""
    sess_iso = s.sess.isoformat()
    path = _flow_path(sess_iso)
    stored = None
    try:
        if os.path.exists(path):
            with open(path) as f:
                stored = json.load(f)
    except Exception:
        stored = None
    if stored and stored.get("flow"):
        return stored["flow"], f"09:30–09:50 window · 0DTE chain read at {stored['at']} ET · Σ volume × mark"
    if not s.today:
        return None, "not recorded for this session (the page was not open between 09:50 and 09:55)"
    if s.m < T_GATE_END:
        return None, "prints at 09:50 — calls vs puts traded during the 20-minute discovery gate"
    flow = MC.opening_flow(s.chain)
    if flow is None:
        return None, "no live chain — " + (s.chain_src or {}).get("note", "unavailable")
    if s.m <= T_GATE_END + 5 and (s.chain_src or {}).get("src") == "barchart":
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                json.dump({"flow": flow, "at": s.now.strftime("%H:%M")}, f)
        except Exception:
            pass
        return flow, f"09:30–09:50 window · 0DTE chain read at {s.now:%H:%M} ET · Σ volume × mark"
    return flow, f"cumulative since 09:30, read {s.now:%H:%M} ET (the page was not open at 09:50) · 0DTE chain · Σ volume × mark"


def _render(cfg):
    sess = cfg["session"]
    s = LV.snapshot(cfg)
    U.status_bar(s.plan, s.label, sess)
    U.refresh_button("meic_refresh")
    if not s.ok:
        st.error(s.error)
        return
    plan, t = s.plan, s.ticket
    past = sess < s.now.date()
    live = past or (s.today and s.m >= T_GATE_END)
    exps = plan["expiries"]
    idx = min(t["expiry_index"], len(exps) - 1)
    c1, c2 = st.columns([0.42, 0.58])
    with c1:
        exp = st.selectbox("Price the ticket on expiry", exps, index=idx, key="meic_expiry",
                           format_func=lambda e: f"{e}  ({exps.index(e)}DTE)" + ("  · desk preference" if exps.index(e) == t["expiry_index"] else ""))
    chain, src = U.chain(exp, "SPX", U.bucket())
    with c2:
        st.markdown(f"<div style='margin-top:30px'><span class='tag {'ok' if (src or {}).get('src') == 'barchart' else 'bad'}'>CHAIN</span> "
                    f"<span class='small'>{K.esc((src or {}).get('note', 'unavailable'))}</span></div>", unsafe_allow_html=True)
    priced = MC.priced(t, chain, plan["sizing"]["c19"])
    credit = priced["condor"]["credit"] if priced.get("condor") else None
    pay = MC.payoff_points(t, credit)
    spot = s.last if s.today else None
    dfn = MC.defense_status(spot, t)
    flow, flow_label = _opening_flow(s)
    st.markdown(K.meic_card(s, t, pay, priced, dfn, flow, flow_label, live), unsafe_allow_html=True)
    rc = None
    if t["regime"] == 2 and (past or (s.today and s.m >= T_GATE_END + 5)):   # nothing to test before the first close after 09:50
        now_min = 24 * 60 if past else s.m
        rc = MC.range_condor_check(s.day5_closed, t, s.lv["em"], t["anchor"], now_min)
        if not rc.get("checks"):
            rc = None
    st.markdown(K.meic_rules_card(t, dfn, s.vix_now if s.today else None, rc, live and s.today), unsafe_allow_html=True)
    if not live:
        st.caption(f"The desk posts this ticket at 09:50 ET, after the Discovery Gate. Strikes come from the {('locked 08:30' if s.locked else 'provisional')} "
                   f"map and do not move intraday; defense alerts start at 09:50.")
    if s.today and s.m >= T_SHUTDOWN and t["regime"] == 2 and rc is not None:
        st.caption(f"After 11:30 the desk allows a range condor only if the test above says CONFIRMED (checked at {fmt_hm(T_SHUTDOWN)}).")
    with st.expander("Desk source (09:50 ticket format) and how the strikes are derived", expanded=False):
        st.markdown(
            "- **Short strikes** = the ±1.25 EM fences of the 08:30 map, `ROUND((C15 ± 1.25 × C12) / 5) × 5` — the same numbers the "
            "08:30 post prints as *MEIC Condor Fences* (`<put`P / `>call`C). The desk's tickets sell exactly those strikes "
            "(Oct 16: 7840C/7645P · Oct 19: 7770C/7545P · Oct 20: 7805C/7575P · Oct 21: 7820C/7605P).\n"
            "- **Long wings** 10 points further out · **5-Pt Defense Triggers** 5 points inside each short strike.\n"
            "- **Gap mornings (C10 active):** the fences move to the Gap Re-Anchor Engine's C45/C46.\n"
            "- **Regime mandate:** Balanced and Negative texts are the desk's own; Positive comes from the credit-spread vault (no Positive ticket posted yet).\n"
            "- The *Credit spread vault* page keeps the manual's wall-based blueprint for comparison.")
