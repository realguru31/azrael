"""credit_view.py — #credit-spread-vault: MEIC grid, both fence conventions, live mids, sizing, active defence."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core import credit as CR
from core import workstation as ws
from data import chain as CH
from data import fetcher as F
from views import common as U


def render(cfg, plan0, label0):
    poll = cfg["poll"] if cfg.get("auto", True) else None

    @st.fragment(run_every=poll)
    def live():
        _render(cfg)

    live()


def _render(cfg):
    sess = cfg["session"]
    plan, label = U.get_plan(cfg)
    U.status_bar(plan, label, sess)
    U.refresh_button("credit_refresh")
    if not plan.get("ok"):
        st.error("No plan — feeds unavailable.")
        return
    g, sg, gap, c6, c19 = plan["grid"], plan["strike_grid"], plan["gap"], plan["inputs"]["c6"], plan["sizing"]["c19"]
    proto = CR.regime_protocol(c6)
    st.markdown(f"### Credit Spread Vault — {ws.REGIME_SHORT[plan['regime']]}")
    cls = "ok" if plan["regime"] == 1 else "warn" if plan["regime"] == 2 else "bad"
    st.markdown(f"<span class='tag {cls}'>{proto['structure']}</span> size factor {proto['size_factor']:.2f} · wings {proto['width']:.0f} pts · expiry: {proto['expiry']}",
                unsafe_allow_html=True)
    for n in proto["notes"]:
        st.caption("• " + n)
    if not proto["allowed"]:
        st.error("VIX > 22: zero credit spread trades until volatility normalises.")

    exps = plan["expiries"]
    exp = st.selectbox("Expiry (0DTE · 1DTE · 2DTE …)", exps, format_func=lambda e: f"{e}  ({exps.index(e)}DTE)")
    ch, ch_src = U.chain(exp, "SPX", U.bucket())
    n_sess = exps.index(exp) + 1
    band = plan["beyond"][n_sess - 2] if n_sess >= 2 else None

    a, b = st.columns(2)
    with a:
        st.markdown("**Convention 1 — MEIC blueprint (manual & vault):** one listed strike beyond the rounded Strike Wall, 10-wide")
        m = ws.meic_strikes(g["c13"], g["c17"])
        st.write(f"Bear Call {m['short_call']:,.0f} / {m['long_call']:,.0f} · Bull Put {m['short_put']:,.0f} / {m['long_put']:,.0f} "
                 f"(Strike Walls {m['upper_strike_wall']:,.0f} / {m['lower_strike_wall']:,.0f})")
        st.markdown("**Convention 2 — desk bot fences (±1.25 EM):** short wings strictly beyond")
        st.write(f"short call above {sg['call_fence']:,.0f} (first strike {sg['call_fence'] + 5:,.0f}) · short put below {sg['put_fence']:,.0f} (first strike {sg['put_fence'] - 5:,.0f})")
        if gap["active"]:
            st.markdown(f"**Gap day active (C10):** fences shift to C45 {gap['c45']:,.0f} / C46 {gap['c46']:,.0f} — do not sell the standard walls into a gap.")
        st.caption("Never sell premium between the King Nodes on a two-way day; in Balanced Gamma the desk says spreads are viable after 11:30 once a range between the nodes is confirmed.")
        if band:
            st.caption(f"{n_sess}-session envelope for this expiry: ±{band['em']:.2f} ({band['lo']:,.2f} – {band['hi']:,.2f}); weekly C18 = {g['c18']:.2f}.")
    with b:
        st.markdown(f"**Live pricing and 1R sizing** — {U.chain_note(ch_src)}")
        grid = CR.meic_grid(g["c13"], g["c17"], gap["c45"], gap["c46"], gap["active"], c6, c19, ch)
        f = grid["fences"]
        st.caption(f"Basis for the short strikes: {f['basis']} · minimum credit for one lot inside {proto['size_factor']:.2f}R: ${grid['min_credit_for_one_lot']:.2f}")
        rows = []
        for leg in ("bear_call", "bull_put"):
            L = grid[leg]
            rows.append({"Spread": "Bear Call" if leg == "bear_call" else "Bull Put", "Short": L["short"], "Long": L["long"],
                         "Short mark": L["short_mark"], "Long mark": L["long_mark"], "Credit": L["credit"],
                         "Max loss / ct": L["max_loss_per_contract"], f"Contracts @ {proto['size_factor']:.2f}R": L["contracts_1r"]})
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
        if grid["condor"]:
            c = grid["condor"]
            st.write(f"MEIC condor: credit {c['credit']:.2f} · max loss/contract ${c['max_loss_per_contract']:,.0f} · contracts {c['contracts_1r']} · max gain/contract ${c['max_gain_per_contract']:,.0f}")
        elif proto["single_sided_only"]:
            st.caption("Single-sided only in this regime (or condors banned).")
        st.caption(f"Chain source: {U.chain_note(ch_src)}.")
        if ch is None:
            st.caption("Chain unavailable — strikes shown, no mids.")
        st.markdown("**Manual sizing check**")
        w = st.number_input("Wing width", min_value=5.0, step=5.0, value=float(proto["width"]))
        cr = st.number_input("Credit collected", min_value=0.0, step=0.05, value=1.80)
        s = ws.credit_spread_contracts(c19 * proto["size_factor"], w, cr)
        st.write(f"Max loss per contract ${s['max_loss_per_contract']:,.0f} → INT({c19 * proto['size_factor']:,.0f} / {s['max_loss_per_contract']:,.0f}) = **{s['contracts']} contracts**"
                 + (" — risk exceeds 1R: the account is undercapitalised for these wings, never force size." if s["contracts"] == 0 else ""))

    st.markdown("---")
    st.markdown("**Active defence**")
    spx1, _ = U.bars("SPX", "1", 300, U.bucket())
    spot, _ = F.latest(spx1)
    vix1, _ = U.bars("VIX", "1", 300, U.bucket())
    vnow, _ = F.latest(vix1)
    sc_ = st.number_input("Your short call strike (0 = none)", min_value=0.0, step=5.0, key="def_sc")
    sp_ = st.number_input("Your short put strike (0 = none)", min_value=0.0, step=5.0, key="def_sp")
    if spot:
        for msg in CR.five_point_test(spot, sc_ or None, sp_ or None):
            st.warning(msg)
        flip = CR.regime_flip(c6, vnow)
        if flip:
            st.error(flip)
        st.caption(f"Spot {spot:,.2f} · VIX now {vnow if vnow is None else f'{vnow:.2f}'} (morning C6 {c6:.2f}).")
    if ch is not None:
        stq = CH.straddle(ch, spot or g["c15"])
        if stq:
            st.caption(f"ATM {stq['atm']:,.0f} straddle {stq['straddle']:.2f} (≈ market 1-day EM {stq['implied_em_approx']:.2f} vs C12 {g['c12']:.2f}).")
