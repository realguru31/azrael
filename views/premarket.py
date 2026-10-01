"""premarket.py — Tab 1 of the workstation, automated, plus the desk bot's #premarket-math strike grid."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core import workstation as ws
from data import chain as CH
from utils import charts as C
from utils.text import strike_grid_post
from utils.timeutil import fmt_session_title
from views import common as U


def _row(cell, label, value, note=""):
    st.markdown(f"<div class='lvl'><div class='name'><b>{cell}</b> · {label}</div><div class='val'>{value}</div></div>"
                + (f"<div class='small'>{note}</div>" if note else ""), unsafe_allow_html=True)


def render(cfg, plan, label):
    sess = cfg["session"]
    U.status_bar(plan, label, sess)
    if not plan.get("ok"):
        st.error("No plan — feeds unavailable. Use the sidebar overrides for C5/C6.")
        return
    i, g, sg, sz, gap = plan["inputs"], plan["grid"], plan["strike_grid"], plan["sizing"], plan["gap"]

    st.markdown("### Premarket Calculator (Tab 1)")
    a, b = st.columns(2)
    with a:
        st.markdown("**Input parameters**")
        _row("C5", "SPX Previous Cash Close", f"{i['c5']:,.2f}", plan["notes"].get("c5", ""))
        _row("C6", "CBOE Volatility Index ($VIX)", f"{i['c6']:.2f}", plan["notes"].get("c6", ""))
        _row("C7", "Overnight Drift (%) — sheet cell '/ES Overnight Drift', fed by the SPX500 price feed", f"{i['c7']:+.2f}" if i.get("c7") is not None else "—", plan["notes"].get("c7", ""))
        _row("C8", "Total Account Size ($)", f"{i['c8']:,.0f}")
        _row("C9", "Max Risk Per Trade (%) [1R Default: 1.0%]", f"{i['c9']:.2f}")
        _row("C10", "Today's 9:30 AM Cash Open (Leave Blank on Normal Days)", f"{i['c10']:,.2f}" if i.get("c10") else "blank")
        st.markdown("**Expected move & risk outputs**")
        _row("C12", "1-Day Expected Move (Points)", f"{g['c12']:.2f}", f"{plan['sanity']['em_pct']:.3f} % of the index · rule of thumb VIX×0.063 % = {plan['sanity']['rule_of_thumb']:.3f} % · walls symmetric: {plan['sanity']['symmetric_walls']}")
        _row("C13", "+1.0 Upper Expected Move Wall", f"{g['c13']:,.2f}")
        _row("C14", "+0.5 Upper Expected Move Boundary", f"{g['c14']:,.2f}")
        _row("C15", "Cash Close Anchor (Equilibrium)", f"{g['c15']:,.2f}")
        _row("C16", "-0.5 Lower Expected Move Boundary", f"{g['c16']:,.2f}")
        _row("C17", "-1.0 Lower Expected Move Wall", f"{g['c17']:,.2f}")
        _row("C18", "5-Day Weekly Expected Move (Points)", f"{g['c18']:.2f}")
        _row("C19", "Max 1R Dollar Risk Per Trade ($)", f"{sz['c19']:,.2f}")
    with b:
        st.markdown("**Regime & execution protocol**")
        _row("C22", "Gamma Regime", ws.REGIME_NAME[plan["regime"]], plan["c22"])
        _row("C23", "Overnight Inventory Bias", ws.inventory_bias_key(i.get("c7")).upper(), plan["c23"])
        _row("C24", "Daily Execution Protocol", "", plan["c24"])
        st.caption(plan["character"])
        st.markdown("**Position sizing & contract calculator**")
        _row("C27", "Structural Stop Distance (SPX Points)", f"{sz['c27']:.2f}")
        _row("C28", "Option Contract Delta", f"{sz['c28']:.2f}")
        _row("C29", "MAX RECOMMENDED CONTRACTS", f"{sz['c29']}", "0 → stop too wide for 1R: tighter structural stop, higher delta, or stand aside. Never shrink 1R." if sz["c29"] == 0 else f"0DTE operational limit with the 15–20 % gamma-convexity buffer: {sz['zero_dte_limit']}")
        _row("C30", "Dollar Risk per Contract", f"${sz['c30']:,.2f}")
        _row("C31", "Notional Position Size", f"${sz['c31']:,.2f}")
        lad = ws.sizing_ladder(sz["c19"], sz["c27"], sz["c28"])
        st.caption("Sizing ladder — " + " · ".join(f"{k}: {v.c29} contract{'s' if v.c29 != 1 else ''}" for k, v in lad.items())
                   + ". 0.5R is the C24 fade limit in Positive Gamma; 0.75R the Balanced credit protocol; XSP/SPY use one-tenth of the stop distance.")
        st.markdown("**Gap Re-Anchor Engine (C10 required)**")
        _row("C37", "Opening Drift (%)", f"{gap['c37']:+.2f}" if gap.get("c37") is not None else "")
        _row("C38", "Re-Anchor Status", "", gap["c38"])
        _row("C39", "Intraday Execution Anchor", f"{gap['c39']:,.2f}")
        _row("C40", "Intraday Expected Move (Points)", f"{gap['c40']:.2f}")
        _row("C41", "+0.5 Intraday Shelf (Upper Resistance)", f"{gap['c41']:,.2f}")
        _row("C42", "-0.5 Intraday Shelf (Lower Support)", f"{gap['c42']:,.2f}")
        _row("C43", "Intraday Call King Node", f"{gap['c43']:,.0f}")
        _row("C44", "Intraday Put King Node", f"{gap['c44']:,.0f}")
        _row("C45", "Intraday Credit Spread Call Fence", f"{gap['c45']:,.0f}")
        _row("C46", "Intraday Credit Spread Put Fence", f"{gap['c46']:,.0f}")
        st.caption("Sheet nodes C43/C44 use 0.52 × EM; the desk bot's strike grid uses 0.5 × EM — they coincide except when the two offsets round to different 5-point strikes.")

    # ── 08:33 cross-check against the desk bot
    st.markdown("---")
    st.markdown("### 08:33 cross-check against the desk bot (#premarket-math)")
    x1, x2, x3 = st.columns(3)
    with x1:
        bot13 = st.number_input("Desk bot C13 (+1.0 wall)", min_value=0.0, step=0.01, key="bot_c13")
    with x2:
        bot17 = st.number_input("Desk bot C17 (−1.0 wall)", min_value=0.0, step=0.01, key="bot_c17")
    with x3:
        botvix = st.number_input("Desk bot VIX (optional)", min_value=0.0, step=0.01, key="bot_vix")
    if bot13 and bot17:
        d13, d17 = abs(bot13 - g["c13"]), abs(bot17 - g["c17"])
        ok = d13 <= 2 and d17 <= 2
        st.markdown(f"<span class='tag {'ok' if ok else 'bad'}'>{'MATCH within 2 points' if ok else 'DIVERGENT'}</span> "
                    f"C13 differs by {d13:.2f}, C17 by {d17:.2f}." + ("" if ok else " Recheck C5, then align C6 to the bot's VIX (sidebar override). "
                    "A 0.5 VIX discrepancy shifts the EM by 2–3 points."), unsafe_allow_html=True)
        if botvix and abs(botvix - i["c6"]) >= 0.5:
            st.warning(f"VIX discrepancy {abs(botvix - i['c6']):.2f} ≥ 0.5 — update C6 to the desk bot's reading.")

    # ── the desk bot's STRIKE GRID
    st.markdown("---")
    st.markdown("### Strike grid — the desk bot's #premarket-math post, reproduced")
    left, right = st.columns([0.5, 0.5])
    with left:
        st.code(strike_grid_post(plan, fmt_session_title(sess)), language=None)
    with right:
        exp = plan["expiries"][0]
        ch = U.chain(exp, "SPX", U.bucket())
        prof = CH.gex_profile(ch, g["c15"], g["c12"], 1.6) if ch is not None else None
        st.plotly_chart(C.node_map({"C13": g["c13"], "C14": g["c14"], "C15": g["c15"], "C16": g["c16"], "C17": g["c17"]}, sg, prof,
                                   title="NODE MAP · parametric grid" + (" over live CBOE open interest" if prof is not None else " (model shape, no chain)")),
                        use_container_width=True, key="node_map")
        if plan.get("oi_node"):
            o = plan["oi_node"]
            st.markdown(f"**Book definition (Ch.4) from the live chain:** largest combined OI within 1 EM at **{o['strike']:,.0f}** "
                        f"({o['total_oi']:,.0f} = C {o['c_oi']:,.0f} / P {o['p_oi']:,.0f}){' — tie broken toward the close' if o['tie_break'] else ''}. "
                        f"Max call OI {o['call_max']['strike']:,.0f}, max put OI {o['put_max']['strike']:,.0f}.")
            top = pd.DataFrame(o["top"]).rename(columns={"strike": "Strike", "total_oi": "Total OI", "c_oi": "Call OI", "p_oi": "Put OI", "volume": "Volume"})
            st.dataframe(top.style.format({"Strike": "{:,.0f}", "Total OI": "{:,.0f}", "Call OI": "{:,.0f}", "Put OI": "{:,.0f}", "Volume": "{:,.0f}"}),
                         use_container_width=True, hide_index=True)
            ap = plan.get("air_pocket") or {}
            if ap.get("up") and ap.get("down"):
                st.caption(f"Air-pocket check (Archetype 4): OI between C14 and C13 = {ap['up']['oi_between']:,.0f} ({ap['up']['share_of_chain']:.1f} % of the chain); "
                           f"between C16 and C17 = {ap['down']['oi_between']:,.0f} ({ap['down']['share_of_chain']:.1f} %).")
        else:
            st.caption("Chain unavailable — the node map shows the model shape only.")
        if plan.get("vol_node"):
            v = plan["vol_node"]
            st.markdown(f"**Volume node (today's 0DTE flow, live proxy):** largest combined volume within 1 EM at **{v['strike']:,.0f}** "
                        f"({v['total_volume']:,.0f} = C {v['c_volume']:,.0f} / P {v['p_volume']:,.0f}; {v['chain_volume']:,.0f} contracts traded within 1 EM so far).")
        st.caption(f"Chain source: {U.chain_note()} · expiry {exp}")
        if prof is not None and not prof.empty:
            st.plotly_chart(C.gex_chart(prof, {"C13": g["c13"], "C14": g["c14"], "C15": g["c15"], "C16": g["c16"], "C17": g["c17"]}, None),
                            use_container_width=True, key="gex")

    # ── micro desk + stop clusters
    st.markdown("---")
    m1, m2 = st.columns(2)
    with m1:
        st.markdown("**Micro Desk Protocol (accounts under $25k)**")
        mi = plan.get("micro", {})
        if mi:
            x = mi["XSP"]
            st.write(f"XSP (1/10th of SPX, identical settlement): anchor {x['C15']:.2f} · shelves {x['C16']:.2f} / {x['C14']:.2f} · walls {x['C17']:.2f} / {x['C13']:.2f} · "
                     f"nodes {x['put_node']:.1f} / {x['call_node']:.1f} · fences {x['put_fence']:.1f} / {x['call_fence']:.1f}")
            s10 = mi["SPY_div10"]
            st.write(f"SPY by division (KB): anchor {s10['C15']:.2f} · shelves {s10['C16']:.2f} / {s10['C14']:.2f} · walls {s10['C17']:.2f} / {s10['C13']:.2f}")
            if plan.get("spy"):
                s = plan["spy"]
                st.write(f"SPY on its own prior close (desk bot): anchor {s['anchor']:.2f} · shelves {s['shelf_lo']:.2f} / {s['shelf_hi']:.2f} · nodes {s['put_node']:.0f} / {s['call_node']:.0f}")
    with m2:
        st.markdown("**08:45 stop-cluster candidates**")
        sc = plan.get("stop_clusters", {})
        def _v(k):
            v = sc.get(k)
            return f"{v:,.2f}" if v is not None else "—"
        st.write(f"Pre-market high / low (SPX500 feed, 18:00–09:30): {_v('pre_market_high')} / {_v('pre_market_low')}")
        st.write(f"Prior session high / low: {_v('prior_session_high')} / {_v('prior_session_low')}")
        st.write("Round hundreds inside the envelope: " + (", ".join(f"{h:,}" for h in sc.get("round_hundreds", [])) or "none"))
        if plan.get("es"):
            e = plan["es"]
            st.caption(f"{e['name']}: {e['anchor']:,.2f} · EM ±{e['em']:.2f} · shelves {e['shelf_lo']:,.2f} / {e['shelf_hi']:,.2f} · nodes {e['put_node']:,.0f} / {e['call_node']:,.0f}")
