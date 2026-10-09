"""desk.py — the session cockpit. The live block (banner, chart, gate, scanner) is a Streamlit fragment: it re-runs on
its own every poll and has its own refresh button, so the rest of the page never flickers. State changes raise alerts."""
from __future__ import annotations

from datetime import date, datetime, time as dtime

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
ALERT_STATES = {"GATE": "⛔", "ARMED": "⚡", "ACTIVE": "🟢", "DONE": "🏁", "STAND_DOWN": "⏸", "LOCKED": "🔒", "WATCHING": "👁"}


def _banner(b: X.Banner, sc=None):
    """Two lines: what's armed / what's on, and the Scenario Book score line. Everything else folds into Details."""
    bg, fg = TONE.get(b.tone, TONE["neutral"])
    pulse = " pulse" if b.state == "ARMED" else ""
    icon = {"PREMARKET": "🕗", "LOCKED": "🔒", "GATE": "⛔", "WATCHING": "👁", "ARMED": "⚡", "ACTIVE": "🟢", "DONE": "🏁",
            "STAND_DOWN": "⏸", "SHUTDOWN": "🌙", "SETTLE": "🧾"}.get(b.state, "")
    # line 1
    if b.state in ("ACTIVE", "DONE") and b.trade:
        t = b.trade
        side = "LONG CALLS" if t["side"] == "long" else "LONG PUTS"
        l1 = (f"{icon} BOOK TRADE · A{t['archetype']} {side} · in {t['entry']:,.2f} · stop {t['stop']:,.2f} · target {t['target']:,.2f}"
              + (f" · {b.sub.split(' · now ')[-1]}" if " · now " in b.sub else "")
              + (f" · {('FLAT 11:30' if str(t['resolution']).startswith('flat') else str(t['resolution']).upper())} {t['exit_price']:,.2f} ({t['r_multiple']:+.2f}R)" if b.state == "DONE" and t.get("exit_price") is not None else ""))
    elif b.state == "ARMED":
        a = next((p for p in b.plays if p.status == "armed"), None)
        l1 = f"{icon} ARMED · {a.side} · {a.title}" if a else f"{icon} ARMED"
    else:
        l1 = f"{icon} {b.headline}"
    # line 2
    if sc is not None:
        col = {"SENT": "#26a69a", "WAITING": "#ffd600", "NOT_SENT": "#a0a0a0", "DROPPED": "#ef5350", "EXPIRED": "#ef5350", "CUTOFF": "#a0a0a0"}[sc.status]
        tag = {"SENT": "ALLOWED — SENT", "WAITING": "ALLOWED — WAITING", "NOT_SENT": "NOT SENT", "DROPPED": "DROPPED", "EXPIRED": "DROPPED", "CUTOFF": "CUT-OFF"}[sc.status]
        l2 = f"<span style='color:{col};font-weight:600'>SCORE {sc.score:.1f} / 9.5 · {tag}</span> <span class='small'>· {sc.status_text}</span>"
    elif b.state == "ARMED":
        a = next((p for p in b.plays if p.status == "armed"), None)
        l2 = f"<span class='small'>needs: {a.condition}</span>" if a else ""
    elif b.state in ("ACTIVE", "DONE") and b.exits:
        l2 = f"<span class='small'>next exit: {b.exits[0]}</span>"
    else:
        l2 = f"<span class='small'>{b.sub}</span>"
    st.markdown(
        f"<div class='banner{pulse}' style='padding:12px 16px;border-radius:8px;background:{bg};border-left:8px solid {fg};margin:6px 0 6px 0;'>"
        f"<div style='font-size:1.3rem;font-weight:600;color:{fg};font-family:IBM Plex Mono,monospace'>{l1}</div>"
        f"<div style='margin-top:4px;font-size:1rem;color:var(--text)'>{l2}</div></div>", unsafe_allow_html=True)
    with st.expander("Details — plays · exits · score checks · credit · notes", expanded=False):
        if sc is not None:
            rows = "".join(f"<tr><td style='padding:2px 10px 2px 0;color:var(--muted)'>{c.name}</td><td style='padding:2px 10px;font-family:IBM Plex Mono,monospace'>{c.value:g}</td>"
                           f"<td style='padding:2px 0;color:var(--text)'>{c.note}</td></tr>" for c in sc.checks)
            st.markdown(f"<div class='small'>Scenario Book checks (app definitions, 1 / ½ / 0; bare minimum = 0) · send rule: {sc.send_rule}</div>"
                        f"<table style='font-size:0.85rem;border-collapse:collapse'>{rows}</table>", unsafe_allow_html=True)
        if b.exits:
            st.markdown("<div class='small' style='margin-top:8px'><b>EXIT PLAN</b> (nearest first)</div>" +
                        "".join(f"<div style='font-family:IBM Plex Mono,monospace;font-size:0.86rem'>{e}</div>" for e in b.exits), unsafe_allow_html=True)
        for p in b.plays:
            badge = {"armed": "ok", "watch": "", "blocked": "bad"}[p.status]
            st.markdown(f"<div style='margin-top:6px'><span class='tag {badge}'>{p.status.upper()}</span> <b>{p.side}</b> — {p.title}"
                        f"<div class='small'>Condition: {p.condition}</div><div class='small'>Entry: {p.entry} · Stop: {p.stop} · Target: {p.target}</div>"
                        f"<div class='small'>{p.status_text}</div></div>", unsafe_allow_html=True)
        st.markdown(f"<div style='margin-top:8px;font-size:0.9rem'><b>CREDIT</b> · {b.credit}</div>", unsafe_allow_html=True)
        for n in b.notes:
            st.markdown(f"<div class='small'>▲ {n}</div>", unsafe_allow_html=True)


def _alerts(b: X.Banner, cfg):
    """Toast + tab-title flash + optional beep / browser notification when the state changes."""
    prev = st.session_state.get("last_banner_state")
    if prev == b.state:
        return
    st.session_state["last_banner_state"] = b.state
    if prev is None or b.state not in ALERT_STATES:
        return
    icon = ALERT_STATES[b.state]
    st.toast(f"{b.state.replace('_', ' ')} — {b.headline}", icon=icon)
    state_txt = b.state.replace("_", " ")
    head = b.headline.replace("'", "\\'")[:120]
    js = f"""<script>
(function(){{
  {'try{const c=new (window.AudioContext||window.webkitAudioContext)();const o=c.createOscillator();const g=c.createGain();o.connect(g);g.connect(c.destination);o.frequency.value=880;g.gain.value=0.12;o.start();setTimeout(()=>{o.frequency.value=1320;},160);setTimeout(()=>{o.stop();c.close();},480);}catch(e){}' if cfg.get('sound') else ''}
  try{{const d=window.parent.document;const t0=d.title;let n=0;const iv=setInterval(()=>{{d.title=(n%2?t0:'{icon} {state_txt} — Azraël Desk');if(++n>16){{clearInterval(iv);d.title=t0;}}}},700);}}catch(e){{}}
  {'try{if(window.Notification&&Notification.permission==="granted"){new Notification("Azraël Desk — ' + state_txt + '",{body:"' + head + '"});}}catch(e){}' if cfg.get('notify') else ''}
}})();</script>"""
    components.html(js, height=0)


def _levels_for_chart(plan, lv, grid, sg, gap):
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
    return levels


def _armed_and_trade(b: X.Banner, lv, sess, shift: int = 0):
    """Trigger levels of armed plays + the live trade for the chart overlays."""
    armed = []
    for p in b.plays:
        if p.status != "armed":
            continue
        if p.archetype == 2:
            armed.append({"price": lv["put_node"] if "put node" in p.title else lv["call_node"], "title": f"{p.side} · {p.title.split(' at ')[0]}"})
        elif p.archetype == 1:
            armed.append({"price": lv["C16"] if "−0.5" in p.title else lv["C14"], "title": f"{p.side} · half-EM fade"})
        elif p.archetype == 4:
            armed.append({"price": lv["C14"] if "+0.5" in p.title else lv["C16"], "title": f"{p.side} · runner"})
    trade = None
    if b.state in ("ACTIVE", "DONE") and b.trade:
        t = b.trade
        hh, mm = map(int, t["trigger_time"].split(":"))
        from datetime import timedelta as _td
        end_dt = datetime.combine(sess, dtime(11, 30), tzinfo=ET)
        exit_dt = None
        if t.get("exit_time"):
            ehh, emm = map(int, t["exit_time"].split(":"))
            exit_dt = datetime.combine(sess, dtime(ehh, emm), tzinfo=ET) + _td(minutes=shift)
            end_dt = datetime.combine(sess, dtime(ehh, emm), tzinfo=ET) + _td(minutes=5)
        rmult = (t["target"] - t["entry"]) / t["risk_pts"] if t["side"] == "long" else (t["entry"] - t["target"]) / t["risk_pts"]
        trade = {"entry": t["entry"], "stop": t["stop"], "target": t["target"], "side": t["side"], "done": b.state == "DONE",
                 "time": datetime.combine(sess, dtime(hh, mm), tzinfo=ET) + _td(minutes=shift), "end": end_dt, "rmult": rmult,
                 "exit_time": exit_dt, "exit_price": t.get("exit_price"), "resolution": t.get("resolution"), "r_done": t.get("r_multiple"),
                 "label": f"A{t['archetype']} {'LONG CALLS' if t['side'] == 'long' else 'LONG PUTS'} {t['entry']:.2f}"}
    return armed, trade


def render(cfg, plan0, label0):
    sess: date = cfg["session"]
    poll = cfg["poll"] if cfg.get("auto", True) else None

    @st.fragment(run_every=poll)
    def live():
        plan, label = U.get_plan(cfg)
        U.status_bar(plan, label, sess)
        U.refresh_button("desk_refresh")
        if not plan.get("ok"):
            st.error(f"Feeds did not return C5/C6 for {sess}: {plan.get('notes')}. Use the overrides in the sidebar or try again.")
            return
        now = now_et()
        m = minutes_of(now)
        locked = label.startswith("LOCKED")

        # ── data
        five = str(cfg.get("interval", "1-minute")).startswith("5")
        days_back = max(0, (now.date() - sess).days)
        n_bars = min(2000, 400 + days_back * 300) if five else min(5000, 1400 + days_back * 1440)   # a 24-hour feed prints ~1,400 1-min bars a day
        px1, px_src = U.price_bars(cfg["price_symbol"], "5" if five else "1", n_bars, U.bucket())
        shift = 0 if five else 5                       # on the 1-minute view the 5-minute bar's close is 5 minutes after its stamp
        if cfg.get("rules_feed", "").startswith("Price"):
            spx5, _ = U.price_bars(cfg["price_symbol"], "5", 400, U.bucket())
        else:
            spx5, _ = U.bars("SPX", "5", 400, U.bucket())
        spy5, _ = U.bars("SPY", "5", 400, U.bucket())
        qqq5, _ = U.bars("QQQ", "5", 400, U.bucket())
        day1 = px1 if px1 is not None else None
        day5 = F.session_slice(spx5, sess)
        day_spy, day_qqq = F.session_slice(spy5, sess), F.session_slice(qqq5, sess)
        last, last_t = F.latest(day1)
        lv = R.rule_levels(plan)
        grid = {k: lv[k] for k in ("C13", "C14", "C15", "C16", "C17")}
        gate = R.gate_test(day5) if not day5.empty else None
        live_s = R.live_status(day5, day_spy, day_qqq, grid, lv["em"], lv["put_node"], lv["call_node"], plan["inputs"]["c6"]) if not day5.empty else None
        chain, chain_src = U.chain(plan["expiries"][0], "SPX", U.bucket())

        # ── 1. banner + alerts
        b = X.banner(plan, lv, day5, last, m, gate, live_s, chain, locked, chain_src, session_ahead=(sess > now.date()),
                     past_session=(sess < now.date()))
        sc = None
        if b.state in ("ACTIVE", "DONE") and live_s and live_s.get("chosen") is not None:
            from core import scoring as SCR
            spx1_idx, _ = U.bars("SPX", "1", 800, U.bucket())
            vix1, _ = U.bars("VIX", "1", 300, U.bucket())
            vnow, _ = F.latest(F.session_slice(vix1, sess)) if vix1 is not None else (None, None)
            sc = SCR.score_idea(live_s["chosen"], plan, lv, day5, day_spy, day_qqq, gate, vnow, F.session_slice(spx1_idx, sess), m)
            b.score = sc.as_dict()
        _banner(b, sc)
        _alerts(b, cfg)

        # ── 1b. log the real fill (the replay records the rule's exit; the journal must record yours)
        if b.state in ("ACTIVE", "DONE") and b.trade:
            from data import storage as S
            with st.expander("Log my exit (fills the journal row)", expanded=False):
                e1, e2, e3, e4 = st.columns([0.25, 0.2, 0.4, 0.15])
                ex_px = e1.number_input("Exit price (SPX)", min_value=0.0, step=0.01, value=float(last or 0.0), key="exit_px")
                ex_t = e2.text_input("Exit time", value=now.strftime("%H:%M"), key="exit_t")
                ex_note = e3.text_input("Note", value="", key="exit_note", placeholder="e.g. exited at the King Node")
                if e4.button("Save", key="exit_save", use_container_width=True):
                    S.save_manual_exit(sess.isoformat(), ex_px, ex_t, ex_note)
                    st.toast("Exit logged — the journal form is pre-filled.", icon="📓")
                me = (S.load_cards().get(sess.isoformat()) or {}).get("manual_exit")
                if me:
                    t = b.trade
                    pnl = (me["price"] - t["entry"]) if t["side"] == "long" else (t["entry"] - me["price"])
                    st.caption(f"Logged: exit {me['price']:,.2f} at {me['time']} → {pnl:+.2f} pts = {pnl / t['risk_pts']:+.2f}R on the {t['risk_pts']:.2f}-pt stop.")

        # ── 2. chart with armed / trade overlays
        sg, gap = plan["strike_grid"], plan["gap"]
        levels = _levels_for_chart(plan, lv, grid, sg, gap)
        armed, trade = _armed_and_trade(b, lv, sess, shift)
        armed_marker = None
        if armed and last is not None and day1 is not None and not day1.empty:
            ap = next((p for p in b.plays if p.status == "armed"), None)
            dist = abs(ap.distance) if (ap and ap.distance is not None) else None
            armed_marker = {"time": day1.index[-1], "price": float(day1["high"].iloc[-1]),
                            "text": f"ARMED · {dist:.1f} pts" if dist is not None else "ARMED"}
        f_dt, t_dt = U.chart_window(sess)
        markers = [(datetime.combine(sess, dtime(h, mi), tzinfo=ET), txt) for h, mi, txt in
                   ((9, 30, "09:30 open"), (9, 50, "09:50 gate"), (10, 15, "10:15"), (11, 5, "11:05 last bar"), (11, 30, "11:30 shutdown"), (16, 0, "16:00 settle"))]
        vis = day1[(day1.index >= f_dt) & (day1.index <= t_dt)] if day1 is not None and not day1.empty else day1
        ys = [l["price"] for l in levels] + ([float(vis["low"].min()), float(vis["high"].max())] if vis is not None and not vis.empty else []) \
            + [a["price"] for a in armed] + ([trade["stop"], trade["target"]] if trade else [])
        em = plan["grid"]["c12"]
        st.caption(f"{px_src or cfg['price_symbol']} · {'5-minute' if five else '1-minute'} · rules on {'the price feed' if cfg.get('rules_feed', '').startswith('Price') else 'SPX cash (SP:SPX)'}"
                   + ("" if locked else " · PROVISIONAL map") + f" · updated {now.strftime('%H:%M:%S')} ET")
        if cfg.get("engine", "TradingView lightweight").startswith("TradingView"):
            html = LW.build(day1, None, levels, (f_dt, t_dt), markers, U.theme_name(), cfg.get("candles", False), 540,
                            anchor=grid["C15"], lo=min(ys) - 0.1 * em, hi=max(ys) + 0.1 * em, proxy_name="",
                            candle_alpha=cfg.get("candle_opacity", 0.7), armed=armed, trade=trade, armed_marker=armed_marker)
            components.html(html, height=556, scrolling=False)
        else:
            extra = [{"y": a["price"], "name": "⚡ ARMED " + a["title"], "color": "#ffd600", "width": 3} for a in armed]
            fig = C.session_chart(day1, sess, grid, {"call_node": lv["call_node"], "put_node": lv["put_node"]},
                                  {"call_fence": sg["call_fence"], "put_fence": sg["put_fence"]},
                                  {"c39": gap["c39"], "c41": gap["c41"], "c42": gap["c42"]} if gap["active"] else None,
                                  replay=(b.trade if trade else None), spot=last, height=540, candles=cfg.get("candles", False),
                                  overnight=None, show_premarket=m < T_OPEN, candle_alpha=cfg.get("candle_opacity", 0.7),
                                  window=(f_dt, t_dt), extra_lines=extra, time_shift_min=shift)
            st.plotly_chart(fig, use_container_width=True, key="desk_chart")

        # ── 3. one line each: gate · eligible · card
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

        # ── 4. folded detail
        with st.expander("Levels · gap protocol · King Node (C10 entry lives here)", expanded=False):
            a, bcol = st.columns([0.55, 0.45])
            with a:
                U.level_table(plan, gap=True)
            with bcol:
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
                    st.caption(f"OI King Node (book): {o['strike']:,.0f} with {o['total_oi']:,.0f} contracts within 1 EM"
                               + (f" · volume node {plan['vol_node']['strike']:,.0f}" if plan.get("vol_node") else ""))
        with st.expander("Scanner detail — also checked", expanded=False):
            if live_s:
                for line in live_s["also_checked"]:
                    st.write("• " + line)
                pr = live_s.get("proximity", {})
                if pr:
                    st.caption(f"Last {pr['last']:,.2f} ({pr['last_time']}) · to put node {pr['put_node']:+.2f} · to call node {pr['call_node']:+.2f} · "
                               f"to C16 {pr['C16']:+.2f} · to C14 {pr['C14']:+.2f}")
            else:
                st.caption("No regular-hours bars yet.")
        with st.expander("Feeds", expanded=False):
            st.caption(f"Price feed {px_src or cfg['price_symbol']} · official SPX close {plan['sources'].get('spx')} · VIX {plan['sources'].get('vix')} · "
                       f"options chain now: {chain_src['note']} (at lock: {plan['sources'].get('chain')})")
            try:
                from data import barchart as _BC
                st.caption(f"Barchart cookies: {_BC.cookie_source()}")
            except Exception:
                pass
            st.caption(f"C5 {plan['notes'].get('c5', '')} · C6 {plan['notes'].get('c6', '')} · C7 {plan['notes'].get('c7', '')}")
            if last is not None:
                st.caption(f"Last price print {last:,.2f} at {last_t}.")

    live()
