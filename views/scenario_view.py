"""scenario_view.py — the 08:45 If/Then map (generated in the desk's format) and the 09:15 trade card."""
from __future__ import annotations

import streamlit as st

from core import scenario as SC
from core import workstation as ws
from data import storage as S
from utils.timeutil import T_CARD_DEADLINE, fmt_session_title, minutes_of, now_et
from views import common as U

INSTRUMENT = {
    "Archetype 1: Half EM Fade": "ATM or 1–2 strikes ITM SPXW, 0DTE/1DTE, delta 0.55–0.70 — 1DTE preferred when the stop is wide",
    "Archetype 2: King Node Reversal": "0DTE or 1DTE SPXW in the reversal direction, delta 0.55–0.65",
    "Archetype 3: 3-Ticker Alignment": "0DTE SPXW at 0.55–0.65 delta in the break direction — no OTM lottery strikes",
    "Archetype 4: EM Boundary Runner": "0DTE SPXW at 0.55–0.65 delta; reduce size 15–20 % for gamma convexity",
    "Credit Spread: Bull Put": "10-wide (15–20 in Negative Gamma), short strike beyond the put fence; size by (width − credit) × 100",
    "Credit Spread: Bear Call": "10-wide (15–20 in Negative Gamma), short strike beyond the call fence; size by (width − credit) × 100",
    "Iron Condor (MEIC)": "10-wide both sides outside the 1.0 walls; 0DTE clear Positive Gamma, 1–2DTE Balanced; max loss = C19",
}


def render(cfg, plan, label):
    sess = cfg["session"]
    U.status_bar(plan, label, sess)
    if not plan.get("ok"):
        st.error("No plan — feeds unavailable.")
        return
    g = ws.StandardGrid(**plan["grid"])
    sg = ws.StrikeGrid(**plan["strike_grid"])
    m = SC.scenario_map(fmt_session_title(sess), g, sg, plan["inputs"].get("c7"), plan.get("spy"), plan.get("es"),
                        cfg.get("macro", ""), plan.get("oi_node"))
    left, right = st.columns([0.55, 0.45])
    with left:
        st.markdown("### Tactical execution map (generated from the locked math)")
        st.code(SC.scenario_text(m), language=None)
        st.caption("Generated in the desk's A/B/C format from today's C5–C7. Read it against the real #daily-scenarios post: "
                   "when both point to the same regime and side, conviction is high; when they diverge, reduce size or wait.")
    with right:
        st.markdown("### Trade card — post before 09:25")
        now_m = minutes_of(now_et())
        cards = S.load_cards()
        existing = cards.get(sess.isoformat())
        locked = bool(existing and existing.get("locked"))
        if locked:
            st.markdown(f"<span class='tag ok'>LOCKED {existing.get('posted_at', '')}</span> {existing['text']}", unsafe_allow_html=True)
            if st.button("Unlock card (log the reason in the journal notes)"):
                existing["locked"] = False
                S.save_card(sess.isoformat(), existing)
                st.rerun()
            return
        options = ["Watch Day"] + ws.JOURNAL_SETUP_TYPES
        default_idx = 0
        fav = m["favored"].split(" (")[0]
        for k, o in enumerate(options):
            if o.startswith(fav.split(":")[0]) and fav != "Watch Day":
                default_idx = k
        arche = st.selectbox("Setup Archetype", options, index=default_idx if existing is None else options.index(existing["archetype"]) if existing["archetype"] in options else 0)
        if arche == "Watch Day":
            st.info("Watch Day. No qualifying setup identified for current regime. — capital preservation is an active position.")
            if st.button("Post Watch Day", type="primary", use_container_width=True):
                card = SC.TradeCard(sess.isoformat(), "Watch Day", "—", "—", "—", plan["sizing"]["c19"], 0, "—", "",
                                    now_et().strftime("%H:%M ET"), locked=True)
                d = card.as_dict(); d["text"] = card.text(); S.save_card(sess.isoformat(), d)
                st.success("Watch Day posted."); st.rerun()
            return
        lv = plan["grid"]
        sug_trig = {"Archetype 1: Half EM Fade": f"−0.5 shelf C16 {lv['c16']:,.2f} (or C14 {lv['c14']:,.2f}) within 3–5 pts, two closes hold, third bar reverses on volume",
                    "Archetype 2: King Node Reversal": f"put node {sg.put_node:,.0f} / call node {sg.call_node:,.0f} after a 15+ pt displacement, wick rejection bar",
                    "Archetype 3: 3-Ticker Alignment": f"5-min close ≥ {0.05 * lv['c12']:.2f} pts outside a ≤ {0.2 * lv['c12']:.2f}-pt 20-minute box, SPY and QQQ confirming",
                    "Archetype 4: EM Boundary Runner": f"two 5-min closes beyond C14 {lv['c14']:,.2f} or C16 {lv['c16']:,.2f}, next bar holds, enter on the following open",
                    "Credit Spread: Bull Put": f"short put strictly below fence {sg.put_fence:,.0f}",
                    "Credit Spread: Bear Call": f"short call strictly above fence {sg.call_fence:,.0f}",
                    "Iron Condor (MEIC)": f"shorts beyond {sg.put_fence:,.0f}P / {sg.call_fence:,.0f}C"}
        sug_inv = {"Archetype 1: Half EM Fade": f"5-min close more than 8 pts beyond the shelf ({lv['c16'] - 8:,.2f} / {lv['c14'] + 8:,.2f})",
                   "Archetype 2: King Node Reversal": f"5-min close 5 pts through the node ({sg.put_node - 5:,.0f} / {sg.call_node + 5:,.0f}) or two closes beyond it",
                   "Archetype 3: 3-Ticker Alignment": "5-min close back inside the broken box",
                   "Archetype 4: EM Boundary Runner": "5-min close back inside the 0.5 shelf",
                   "Credit Spread: Bull Put": "5-point test on the short strike → roll out 1 day / 5 wider, else take the loss",
                   "Credit Spread: Bear Call": "5-point test on the short strike → roll out 1 day / 5 wider, else take the loss",
                   "Iron Condor (MEIC)": "5-point test either side; regime flip to Negative Gamma → close at market"}
        direction = st.selectbox("Direction", ["Long calls", "Long puts", "Bull Put", "Bear Call", "Iron Condor"],
                                 index=["Long calls", "Long puts", "Bull Put", "Bear Call", "Iron Condor"].index(existing["direction"]) if existing and existing.get("direction") in ["Long calls", "Long puts", "Bull Put", "Bear Call", "Iron Condor"] else 0)
        trig = st.text_input("Trigger Level", value=existing["trigger_level"] if existing else sug_trig.get(arche, ""))
        inv = st.text_input("Invalidation Level (structural stop)", value=existing["invalidation_level"] if existing else sug_inv.get(arche, ""))
        risk_choice = st.selectbox("Planned risk", ["1R", "0.75R", "0.5R"], help="C24 in Positive Gamma: 'Fade with 0.5R limit'. Balanced credit protocol: 0.75R.")
        lad = ws.sizing_ladder(plan["sizing"]["c19"], cfg["c27"], cfg["c28"])
        sz = lad[risk_choice]
        st.caption(f"1R cap ${plan['sizing']['c19']:,.2f} · at {risk_choice}: {sz.c29} contract{'s' if sz.c29 != 1 else ''} (stop {cfg['c27']:.1f} pts · Δ {cfg['c28']:.2f} · ${sz.c30:,.0f}/contract) · "
                   f"0DTE buffered {sz.zero_dte_limit}. {INSTRUMENT.get(arche, '')}")
        notes = st.text_area("Notes (regime, map alignment, macro)", value=existing["notes"] if existing else
                             f"VIX {plan['inputs']['c6']:.2f}, {ws.REGIME_SHORT[plan['regime']]}, overnight drift {plan['inputs'].get('c7') if plan['inputs'].get('c7') is not None else '—'}. {cfg.get('macro', '')}".strip(), height=90)
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Save draft", use_container_width=True):
                card = SC.TradeCard(sess.isoformat(), arche, direction, trig, inv, plan["sizing"]["c19"] * {"1R": 1, "0.75R": .75, "0.5R": .5}[risk_choice],
                                    sz.c29, INSTRUMENT.get(arche, ""), notes, now_et().strftime("%H:%M ET"), locked=False)
                d = card.as_dict(); d["text"] = card.text(); S.save_card(sess.isoformat(), d); st.success("Draft saved."); st.rerun()
        with c2:
            late = now_m >= T_CARD_DEADLINE and sess == now_et().date()
            if st.button("Post & lock card" + (" (after 09:25 — late)" if late else ""), type="primary", use_container_width=True):
                card = SC.TradeCard(sess.isoformat(), arche, direction, trig, inv, plan["sizing"]["c19"] * {"1R": 1, "0.75R": .75, "0.5R": .5}[risk_choice],
                                    sz.c29, INSTRUMENT.get(arche, ""), notes + (" [posted after the 09:25 deadline]" if late else ""),
                                    now_et().strftime("%H:%M ET"), locked=True)
                d = card.as_dict(); d["text"] = card.text(); S.save_card(sess.isoformat(), d); st.success("Card posted and locked."); st.rerun()
        if existing:
            st.caption(f"Draft: {existing['text']}")
