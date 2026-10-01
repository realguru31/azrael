"""desk.py — the session cockpit. Open it at 08:30 and the day is on one screen."""
from __future__ import annotations

from datetime import date

import streamlit as st

from core import rules as R
from core import workstation as ws
from data import fetcher as F
from utils import charts as C
from utils.timeutil import T_GATE_END, T_OPEN, T_SHUTDOWN, is_trading_day, minutes_of, now_et
from views import common as U


def render(cfg, plan, label):
    sess: date = cfg["session"]
    U.status_bar(plan, label, sess)
    U.phase_banner()
    if not plan.get("ok"):
        st.error(f"Feeds did not return C5/C6 for {sess}: {plan.get('notes')}. Use the overrides in the sidebar or try again.")
        return

    spx5, spx_src = U.bars("SPX", "5", 400, U.bucket())
    spy5, _ = U.bars("SPY", "5", 400, U.bucket())
    qqq5, _ = U.bars("QQQ", "5", 400, U.bucket())
    day = F.session_slice(spx5, sess)
    day_spy, day_qqq = F.session_slice(spy5, sess), F.session_slice(qqq5, sess)
    m = minutes_of(now_et())

    # ── gap-day protocol at 09:31: auto-fill C10 from the 09:30 cash open when the triggers fire
    gap = plan["gap"]
    open_px = U.spx_open_print(sess) if (sess == now_et().date() and m >= T_OPEN + 1) else None
    with st.container():
        c1, c2 = st.columns([0.62, 0.38])
        with c2:
            st.markdown("**Levels (SPX points)**")
            U.level_table(plan, gap=True)
            st.markdown("**Gap protocol (Step 1.5)**")
            drift_flag = plan["inputs"].get("c7") is not None and abs(plan["inputs"]["c7"]) >= 0.75
            if open_px:
                auto_trigger = open_px > plan["grid"]["c13"] or open_px < plan["grid"]["c17"] or abs((open_px - plan["grid"]["c5"]) / plan["grid"]["c5"] * 100) >= 0.75
                st.caption(f"09:30 cash open {open_px:,.2f} · {'RE-ANCHOR conditions met' if auto_trigger else 'inside the envelope, drift below 0.75 %'}")
                if auto_trigger and not st.session_state.get("c10_value"):
                    if st.button("Enter the 09:30 open in C10 (activate the Gap Re-Anchor Engine)", use_container_width=True):
                        st.session_state["c10_value"] = open_px
                        st.rerun()
            elif drift_flag:
                st.caption(f"/ES drift {plan['inputs']['c7']:+.2f} % ≥ 0.75 %: probable gap day — enter the 09:30 cash open in C10 at 09:31.")
            c10 = st.number_input("C10  Today's 09:30 cash open (blank on normal days = 0)", min_value=0.0, step=0.01,
                                  value=float(st.session_state.get("c10_value") or 0.0), key="c10_widget")
            if (c10 or None) != st.session_state.get("c10_value"):
                st.session_state["c10_value"] = c10 or None
                st.rerun()
            st.markdown(f"<span class='tag {'warn' if gap['active'] else ''}'>{gap['c38']}</span>", unsafe_allow_html=True)
        with c1:
            lv = R.rule_levels(plan)
            levels = {k: lv[k] for k in ("C13", "C14", "C15", "C16", "C17")}
            nodes = {"call_node": lv["call_node"], "put_node": lv["put_node"]}
            fences = {"call_fence": plan["strike_grid"]["call_fence"], "put_fence": plan["strike_grid"]["put_fence"]}
            gapl = {"c39": gap["c39"], "c41": gap["c41"], "c42": gap["c42"]} if gap["active"] else None
            extra = []
            sc = plan.get("stop_clusters", {})
            for nm, k in (("pre-mkt high", "pre_market_high"), ("pre-mkt low", "pre_market_low"),
                          ("prior high", "prior_session_high"), ("prior low", "prior_session_low")):
                if sc.get(k):
                    extra.append({"y": sc[k], "name": nm, "color": "#7a8794", "dash": "dot"})
            last, _ = F.latest(day)
            std_levels = {"C13": plan["grid"]["c13"], "C14": plan["grid"]["c14"], "C15": plan["grid"]["c15"],
                          "C16": plan["grid"]["c16"], "C17": plan["grid"]["c17"]}
            pre_open = day.empty or m < T_OPEN
            overnight = U.es_overnight_spx(plan, sess) if cfg.get("overnight", True) else None
            if last is None and overnight is not None and not overnight.empty:
                last = float(overnight["close"].iloc[-1])
            fig = C.session_chart(day, sess, std_levels,
                                  {"call_node": plan["strike_grid"]["call_node"], "put_node": plan["strike_grid"]["put_node"]},
                                  fences, gapl, spot=last, extra_lines=extra, height=540,
                                  title=f"SPX cash · 5-minute · {spx_src or 'no feed'}" + (" · provisional map" if not label.startswith("LOCKED") else ""),
                                  candles=cfg.get("candles", False), overnight=overnight,
                                  show_premarket=pre_open and overnight is not None)
            st.plotly_chart(fig, use_container_width=True, key="desk_chart")
            if gap["active"]:
                st.caption("Gap Re-Anchor active: the scanner below uses C41/C42 as shelves, C43/C44 as King Nodes, C45/C46 as the 1.0 targets. "
                           "Standard levels stay on the chart as the macro envelope and gap-fill targets.")

    # ── the 09:50 test and the live scanner
    st.markdown("---")
    g1, g2 = st.columns([0.4, 0.6])
    with g1:
        st.markdown("**The 09:50 test**")
        gt = R.gate_test(day) if not day.empty else None
        if gt is None:
            st.info("Waiting for the 09:30 open.")
        else:
            cls = {"acceptance": "ok", "trap": "warn", "unconfirmed": "", "pending": ""}[gt.status]
            st.markdown(f"<span class='tag {cls}'>{gt.status.upper()}</span> {gt.detail}", unsafe_allow_html=True)
            gb = day[(day.index.hour * 60 + day.index.minute) < T_GATE_END]
            if not gb.empty:
                st.caption(f"Gate range 09:30–09:50: high {gb['high'].max():,.2f} · low {gb['low'].min():,.2f} · open print {gt.open_print:,.2f}. "
                           "Use the gate's high and low after 09:50 to confirm a fade or an acceptance.")
        el = plan["eligible"]
        st.markdown("**Eligible today** " + " ".join(f"<span class='tag ok'>{ws.ARCHETYPE_NAME[a]}</span>" for a in el["valid"])
                    + " " + " ".join(f"<span class='tag bad'>{ws.ARCHETYPE_NAME[a].split(':')[0]} banned</span>" for a in el["banned"]),
                    unsafe_allow_html=True)
        st.caption(el["note"])
    with g2:
        st.markdown("**Live scanner — mechanical rules on today's 5-minute bars**")
        if day.empty:
            st.info("No regular-hours bars yet.")
        else:
            lv = R.rule_levels(plan)
            grid = {k: lv[k] for k in ("C13", "C14", "C15", "C16", "C17")}
            ls = R.live_status(day, day_spy, day_qqq, grid, lv["em"], lv["put_node"], lv["call_node"], plan["inputs"]["c6"])
            ch = ls["chosen"]
            if ch is not None:
                st.markdown(f"<span class='tag ok'>QUALIFYING BAR</span> **Archetype {ch.archetype} {ch.side}** at {ch.trigger_time} — entry {ch.entry:,.2f}, "
                            f"stop {ch.stop:,.2f}, target {ch.target:,.2f}, planned risk {ch.risk_pts:.2f} pts = 1R.", unsafe_allow_html=True)
                st.caption(ch.trigger_text)
                if ch.resolution not in (None, "open"):
                    st.caption(ch.resolution_text)
            else:
                if m >= T_SHUTDOWN:
                    st.markdown("<span class='tag'>STAND DOWN</span> No qualifying bar closed by 11:05 — no trade today. Capital intact; the session is a Watch Day.",
                                unsafe_allow_html=True)
                elif m >= T_GATE_END:
                    st.markdown("<span class='tag'>NO QUALIFYING BAR YET</span>", unsafe_allow_html=True)
                else:
                    st.markdown("<span class='tag bad'>GATE OPEN — NO TRADES</span>", unsafe_allow_html=True)
            pr = ls.get("proximity", {})
            if pr:
                st.caption(f"Last {pr['last']:,.2f} ({pr['last_time']}) · to put node {pr['put_node']:+.2f} · to call node {pr['call_node']:+.2f} · "
                           f"to C16 {pr['C16']:+.2f} · to C14 {pr['C14']:+.2f} · to C17 {pr['C17']:+.2f} · to C13 {pr['C13']:+.2f}")
            with st.expander("Also checked", expanded=False):
                for line in ls["also_checked"]:
                    st.write("• " + line)

    # ── the day's card
    st.markdown("---")
    from data import storage as S
    card = S.load_cards().get(sess.isoformat())
    if card:
        st.markdown(f"**Trade card ({'locked' if card.get('locked') else 'draft'}, posted {card.get('posted_at', '')})** — " + card.get("text", ""))
    else:
        st.caption("No trade card yet for this session. Write it on the Scenario & Card page before 09:25 — or post Watch Day.")
    st.caption(f"Sources: SPX {plan['sources'].get('spx')} · VIX {plan['sources'].get('vix')} · /ES {plan['sources'].get('es')} · "
               f"chain {plan['sources'].get('chain')} · C6 {plan['notes'].get('c6', '')} · C7 {plan['notes'].get('c7', '')}")
