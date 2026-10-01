"""desk.py — the session cockpit, built for the moment of execution: the banner says what to do, the chart shows
where price is against the map, everything else folds away."""
from __future__ import annotations

from datetime import date, time as dtime, datetime, timedelta

import streamlit as st
import streamlit.components.v1 as components

from core import execution as X
from core import rules as R
from core import workstation as ws
from data import fetcher as F
from utils import charts as C
from utils import lwchart as LW
from utils.timeutil import ET, T_OPEN, minutes_of, now_et
from views import common as U

TONE = {"neutral": ("#263653", "#e0e0e0"), "wait": ("#3d2d12", "#ffd27a"), "go": ("#123d2e", "#7ee2b5"),
        "active": ("#1b3a5c", "#8ec5ff"), "done": ("#2a2f3a", "#e0e0e0"), "bad": ("#3d1a1a", "#ff9d9d")}


def _banner(b: X.Banner):
    bg, fg = TONE.get(b.tone, TONE["neutral"])
    plays_html = ""
    for p in b.plays:
        badge = {"armed": "ok", "watch": "", "blocked": "bad"}[p.status]
        plays_html += (f"<div style='margin:8px 0 0 0;padding:8px 10px;border-radius:5px;background:rgba(0,0,0,0.18);'>"
                       f"<span class='tag {badge}'>{p.status.upper()}</span> <b>{p.side}</b> — {p.title}"
                       f"<div class='small' style='margin-top:4px'>Condition: {p.condition}</div>"
                       f"<div class='small'>Entry: {p.entry} · Stop: {p.stop} · Target: {p.target}</div>"
                       f"<div class='small'>{p.status_text}</div></div>")
    notes = "".join(f"<div class='small' style='margin-top:6px'>▲ {n}</div>" for n in b.notes)
    st.markdown(
        f"<div style='padding:14px 16px;border-radius:8px;background:{bg};border-left:8px solid {fg};margin:6px 0 10px 0;'>"
        f"<div style='font-size:0.78rem;letter-spacing:0.08em;color:{fg};'>TRADE OPPORTUNITY · {b.state.replace('_', ' ')}</div>"
        f"<div style='font-size:1.35rem;font-weight:600;color:{fg};margin:2px 0;'>{b.headline}</div>"
        f"<div style='color:var(--text);font-size:0.95rem;'>{b.sub}</div>"
        f"{plays_html}"
        f"<div style='margin-top:10px;padding-top:8px;border-top:1px solid rgba(255,255,255,0.12);color:var(--text);font-size:0.9rem;'>"
        f"<b>CREDIT</b> · {b.credit}</div>{notes}</div>", unsafe_allow_html=True)


def render(cfg, plan, label):
    sess: date = cfg["session"]
    U.status_bar(plan, label, sess)
    if not plan.get("ok"):
        st.error(f"Feeds did not return C5/C6 for {sess}: {plan.get('notes')}. Use the overrides in the sidebar or try again.")
        return
    now = now_et()
    m = minutes_of(now)
    locked = label.startswith("LOCKED")

    # ── data
    px1, px_src = U.price_bars(cfg["price_symbol"], "1", 1400, U.bucket())        # the price feed: Capital.com SPX500
    if cfg.get("rules_feed", "").startswith("Price"):
        spx5, _ = U.price_bars(cfg["price_symbol"], "5", 400, U.bucket())
    else:
        spx5, _ = U.bars("SPX", "5", 400, U.bucket())
    spx1, spx_src = px1, px_src
    spy5, _ = U.bars("SPY", "5", 400, U.bucket())
    qqq5, _ = U.bars("QQQ", "5", 400, U.bucket())
    day1 = px1 if px1 is not None else F.session_slice(spx1, sess)
    day5 = F.session_slice(spx5, sess)
    day_spy, day_qqq = F.session_slice(spy5, sess), F.session_slice(qqq5, sess)
    proxy, proxy_src = None, ""                                                   # the price feed itself trades 24 h — no hand-off
    last_spx, last_t = F.latest(day1)
    last = last_spx
    lv = R.rule_levels(plan)
    grid = {k: lv[k] for k in ("C13", "C14", "C15", "C16", "C17")}
    gate = R.gate_test(day5) if not day5.empty else None
    live = R.live_status(day5, day_spy, day_qqq, grid, lv["em"], lv["put_node"], lv["call_node"], plan["inputs"]["c6"]) if not day5.empty else None
    chain = U.chain(plan["expiries"][0], "SPX", U.bucket())

    # ── 1. the banner
    _banner(X.banner(plan, lv, day5, last, m, gate, live, chain, locked))

    # ── 2. the chart
    sg, gap = plan["strike_grid"], plan["gap"]
    levels = [
        {"price": grid["C13"], "color": "#3d8bff", "style": 1, "title": "+1.0 wall C13"},
        {"price": grid["C14"], "color": "#ff9d2e", "style": 2, "title": "+0.5 shelf C14"},
        {"price": grid["C15"], "color": "#a7b1bd", "style": 0, "title": "anchor C15", "width": 2},
        {"price": grid["C16"], "color": "#ff9d2e", "style": 2, "title": "−0.5 shelf C16"},
        {"price": grid["C17"], "color": "#3d8bff", "style": 1, "title": "−1.0 wall C17"},
        {"price": lv["call_node"], "color": "#b06cff", "style": 1, "title": "Call King Node", "width": 2},
        {"price": lv["put_node"], "color": "#b06cff", "style": 1, "title": "Put King Node", "width": 2},
        {"price": sg["call_fence"], "color": "#e3b600", "style": 4, "title": "call fence"},
        {"price": sg["put_fence"], "color": "#e3b600", "style": 4, "title": "put fence"},
    ]
    if plan.get("oi_node"):
        levels.append({"price": plan["oi_node"]["strike"], "color": "#22d3ee", "style": 2, "title": f"OI King Node (book) {plan['oi_node']['total_oi']:,.0f} OI"})
    if plan.get("vol_node") and plan["vol_node"]["total_volume"] > 0:
        levels.append({"price": plan["vol_node"]["strike"], "color": "#67e8f9", "style": 4, "title": f"Volume node {plan['vol_node']['total_volume']:,.0f}"})
    sc = plan.get("stop_clusters", {})
    for nm, k in (("pre-mkt high", "pre_market_high"), ("pre-mkt low", "pre_market_low"), ("prior high", "prior_session_high"), ("prior low", "prior_session_low")):
        if sc.get(k):
            levels.append({"price": sc[k], "color": "#7a8794", "style": 4, "title": nm})
    if gap["active"]:
        for k, nm in (("c39", "gap anchor C39"), ("c41", "+0.5 intraday C41"), ("c42", "−0.5 intraday C42")):
            levels.append({"price": gap[k], "color": "#c084fc", "style": 3, "title": nm})
    f_dt, t_dt = U.chart_window(sess)
    markers = [(datetime.combine(sess, dtime(h, mi), tzinfo=ET), txt) for h, mi, txt in
               ((9, 30, "09:30 open"), (9, 50, "09:50 gate"), (10, 15, "10:15"), (11, 5, "11:05 last bar"), (11, 30, "11:30 shutdown"), (16, 0, "16:00 settle"))]
    f_dt0, t_dt0 = U.chart_window(sess)
    vis = day1[(day1.index >= f_dt0) & (day1.index <= t_dt0)] if day1 is not None and not day1.empty else day1
    ys = [l["price"] for l in levels] + ([float(vis["low"].min()), float(vis["high"].max())] if vis is not None and not vis.empty else [])
    em = plan["grid"]["c12"]
    title = f"{px_src or cfg['price_symbol']} · 1-minute · rules on {'the price feed' if cfg.get('rules_feed', '').startswith('Price') else 'SPX cash (SP:SPX)'}" + ("" if locked else " · PROVISIONAL map")
    st.caption(title)
    if cfg.get("engine", "TradingView lightweight").startswith("TradingView"):
        html = LW.build(day1, None, levels, (f_dt, t_dt), markers, U.theme_name(), cfg.get("candles", False), 540,
                        anchor=grid["C15"], lo=min(ys) - 0.1 * em, hi=max(ys) + 0.1 * em, proxy_name="", candle_alpha=cfg.get("candle_opacity", 0.7))
        components.html(html, height=556, scrolling=False)
    else:
        fig = C.session_chart(day1, sess, grid, {"call_node": lv["call_node"], "put_node": lv["put_node"]},
                              {"call_fence": sg["call_fence"], "put_fence": sg["put_fence"]},
                              {"c39": gap["c39"], "c41": gap["c41"], "c42": gap["c42"]} if gap["active"] else None,
                              spot=last, height=540, candles=cfg.get("candles", False), overnight=None, show_premarket=m < T_OPEN,
                              candle_alpha=cfg.get("candle_opacity", 0.7), window=(f_dt, t_dt))
        st.plotly_chart(fig, use_container_width=True, key="desk_chart")

    # ── 3. one line each: gate verdict · scanner · card
    c1, c2, c3 = st.columns([0.34, 0.33, 0.33])
    with c1:
        if gate is None:
            st.markdown("<span class='tag'>09:50 TEST</span> waiting for the 09:30 open", unsafe_allow_html=True)
        else:
            cls = {"acceptance": "ok", "trap": "warn", "unconfirmed": "", "pending": ""}[gate.status]
            st.markdown(f"<span class='tag {cls}'>09:50 TEST · {gate.status.upper()}</span> {gate.detail}", unsafe_allow_html=True)
    with c2:
        el = plan["eligible"]
        st.markdown("<span class='tag'>ELIGIBLE</span> " + " ".join(f"<span class='tag ok'>A{a}</span>" for a in el["valid"])
                    + " " + " ".join(f"<span class='tag bad'>A{a} banned</span>" for a in el["banned"]), unsafe_allow_html=True)
    with c3:
        from data import storage as S
        card = S.load_cards().get(sess.isoformat())
        st.markdown(f"<span class='tag {'ok' if card and card.get('locked') else 'warn'}'>CARD</span> " +
                    (card["text"][:140] if card else "none yet — Scenario & trade card page, before 09:25"), unsafe_allow_html=True)

    # ── 4. everything else folds away
    with st.expander("Levels · gap protocol · King Node (C10 entry lives here)", expanded=False):
        a, b = st.columns([0.55, 0.45])
        with a:
            U.level_table(plan, gap=True)
        with b:
            open_px = U.spx_open_print(sess) if (sess == now.date() and m >= T_OPEN + 1) else None
            drift_flag = plan["inputs"].get("c7") is not None and abs(plan["inputs"]["c7"]) >= 0.75
            if open_px:
                trig = open_px > plan["grid"]["c13"] or open_px < plan["grid"]["c17"] or abs((open_px - plan["grid"]["c5"]) / plan["grid"]["c5"] * 100) >= 0.75
                st.caption(f"09:30 cash open {open_px:,.2f} · {'RE-ANCHOR conditions met' if trig else 'inside the envelope, drift below 0.75 %'}")
                if trig and not st.session_state.get("c10_value"):
                    if st.button("Enter the 09:30 open in C10 (activate the Gap Re-Anchor Engine)", use_container_width=True):
                        st.session_state["c10_value"] = open_px
                        st.rerun()
            elif drift_flag:
                st.caption(f"Overnight drift {plan['inputs']['c7']:+.2f} % ≥ 0.75 %: probable gap day — enter the 09:30 cash open in C10 at 09:31.")
            c10 = st.number_input("C10 Today's 09:30 cash open (0 = blank)", min_value=0.0, step=0.01,
                                  value=float(st.session_state.get("c10_value") or 0.0), key="c10_widget")
            if (c10 or None) != st.session_state.get("c10_value"):
                st.session_state["c10_value"] = c10 or None
                st.rerun()
            st.markdown(f"<span class='tag {'warn' if gap['active'] else ''}'>{gap['c38']}</span>", unsafe_allow_html=True)
            if plan.get("oi_node"):
                o = plan["oi_node"]
                st.caption(f"Live chain OI King Node (book definition): {o['strike']:,.0f} with {o['total_oi']:,.0f} contracts within 1 EM.")
    with st.expander("Scanner detail — also checked", expanded=False):
        if live:
            for line in live["also_checked"]:
                st.write("• " + line)
            pr = live.get("proximity", {})
            if pr:
                st.caption(f"Last {pr['last']:,.2f} ({pr['last_time']}) · to put node {pr['put_node']:+.2f} · to call node {pr['call_node']:+.2f} · "
                           f"to C16 {pr['C16']:+.2f} · to C14 {pr['C14']:+.2f}")
        else:
            st.caption("No regular-hours bars yet.")
    with st.expander("Feeds", expanded=False):
        st.caption(f"Price feed {px_src or cfg['price_symbol']} · official SPX close {plan['sources'].get('spx')} · VIX {plan['sources'].get('vix')} · "
                   f"options chain {plan['sources'].get('chain')}")
        try:
            from data import barchart as _BC
            st.caption(f"Barchart cookies: {_BC.cookie_source()}")
        except Exception:
            pass
        st.caption(f"C5 {plan['notes'].get('c5', '')} · C6 {plan['notes'].get('c6', '')} · C7 {plan['notes'].get('c7', '')}")
        if last_spx is not None:
            st.caption(f"Last price print {last_spx:,.2f} at {last_t}.")
