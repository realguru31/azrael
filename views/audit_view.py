"""audit_view.py — the 04:15 PM Settlement Audit & Rules Replay, plus the 20-session feedback loop."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from core import audit as AU
from core import daydata as DD
from core import plan as P
from core import rules as R
from core import workstation as ws
from data import fetcher as F
from data import storage as S
from utils import charts as C
from utils.timeutil import fmt_session_title, is_trading_day
from views import common as U


def render(cfg, plan, label):
    U.status_bar(plan, label, cfg["session"])
    st.markdown("### Settlement audit & rules replay")
    default = U.last_completed_session()
    sess: date = st.date_input("Session to audit", value=default, key="audit_session")
    if not is_trading_day(sess):
        st.info("Not a trading day.")
        return
    saved = S.load_audit(sess.isoformat())
    base = S.load_baseline(sess.isoformat())
    if base is None or not base.get("ok"):
        with st.spinner("No 08:30 lock on file for this session — rebuilding the morning map from the feeds…"):
            base = U.build_plan(sess.isoformat(), cfg["vix_print"], cfg["es_print"], cfg["c8"], cfg["c9"], cfg["c27"], cfg["c28"], "{}", None, U.bucket())
        src_note = "morning map rebuilt from the feeds (no lock file for this date)"
    else:
        src_note = f"locked {base.get('locked_at', '')} · {base.get('lock_source', '')}"
    if not base.get("ok"):
        st.error("Could not build the morning map for that date.")
        return

    spx5, spx_src = U.bars("SPX", "5", 800, U.bucket())
    spy5, spy_src = U.bars("SPY", "5", 800, U.bucket())
    qqq5, qqq_src = U.bars("QQQ", "5", 800, U.bucket())
    spx_d, spxd_src = U.bars("SPX", "D", 8, U.bucket())
    feed5, feed_src = U.price_bars(cfg["price_symbol"], "5", 800, U.bucket()) if base.get("es") else (None, "")
    spx1_, spx1_src = U.bars("SPX", "1", 800, U.bucket())
    vix5_, vix5_src = U.bars("VIX", "5", 400, U.bucket())
    # the audit itself (also what the day-data zip contains): core/daydata.audit_for — the code that lived here up to 1.8.0
    a, lv, grid, day = DD.audit_for(sess, base, spx5, spy5, qqq5, spx_d, feed5, spx1_, vix5_, U.now_et())
    st.caption(f"Map source: {src_note}. Rules measured on {'the re-anchored gap grid' if lv['mode'] == 'gap' else 'the standard grid'}; on the index, not fills.")
    # ── scoreboard (execution read) + the full desk-format text in its own box (daily reconcile)
    sb_l, sb_r = st.columns([0.42, 0.58])
    with sb_l:
        reg = ws.REGIME_NAME.get(base.get("regime"), "")
        settle_txt = f"settled {a.settlement:,.2f} · {'inside' if a.inside_1sigma else 'OUTSIDE'} 1σ" if a.settlement is not None else f"LIVE — last {a.last_print:,.2f} at {a.last_print_time}" if a.provisional else "no settlement"
        rng_txt = f"range {a.range_em:.2f} EM" if a.range_em is not None else ""
        rows = [f"<div style='font-size:1.15rem;font-weight:600;color:var(--text)'>{fmt_session_title(sess)} · {settle_txt} · {rng_txt}</div>",
                f"<div class='small'>VIX {a.vix:.2f} · EM ±{a.em:.2f} · nodes {a.put_node:,.0f} / {a.call_node:,.0f} · walls {grid['C17']:,.2f} / {grid['C13']:,.2f} · {reg}</div>"]
        if a.replay:
            r_ = a.replay
            rn_ = "FLAT 11:30" if str(r_.get("resolution", "")).startswith("flat") else str(r_.get("resolution", "")).upper()
            res = (f"{rn_} {r_['exit_time']} at {r_['exit_price']:,.2f} · {r_['r_multiple']:+.2f}R" if r_.get("exit_price") is not None else "open")
            rows.append(f"<div style='margin-top:8px;font-family:IBM Plex Mono,monospace'><span class='tag ok'>REPLAY</span> A{r_['archetype']} {'LONG CALLS' if r_['side'] == 'long' else 'LONG PUTS'} · {r_['trigger_time']} bar {r_['entry']:,.2f} → {res}</div>")
            rows.append(f"<div style='font-family:IBM Plex Mono,monospace'><span class='tag'>SCORE</span> {a.score_line}</div>")
        else:
            rows.append("<div style='margin-top:8px;font-family:IBM Plex Mono,monospace'><span class='tag'>REPLAY</span> Watch Day — no qualifying bar</div>")
        rows.append(f"<div class='small' style='margin-top:8px'><b>LESSON</b> {a.lesson}</div>")
        if a.stops_run:
            rows.append(f"<div class='small'><b>STOPS RUN</b> {'; '.join(a.stops_run)}</div>")
        st.markdown("<div style='padding:12px 14px;border-radius:8px;background:var(--panel);border:1px solid var(--border)'>" + "".join(rows) + "</div>", unsafe_allow_html=True)
    with sb_r:
        long_form = st.toggle("Desk-format text (long form, for word-by-word reconcile)", value=False, key="audit_long")
        st.code(AU.audit_text(a) if long_form else AU.audit_text_compact(a), language=None, wrap_lines=True)
    left, right = st.columns([0.0001, 0.9999])
    with right:
        cols = st.columns(2)
        if cols[0].button("Save this audit", type="primary", use_container_width=True, disabled=bool(a.provisional),
                          help="Enabled after the 16:00 settlement; the 16:20 bot saves the official version."):
            S.save_audit(sess.isoformat(), a.as_dict()); st.success("Saved."); st.rerun()
        if a.provisional:
            cols[1].caption("Session not settled — preview only (replay is final after 11:30).")
        if saved:
            cols[1].caption(f"Saved audit on file for {sess}.")
        frames = {"SPX_5m": (spx5, spx_src), "SPY_5m": (spy5, spy_src), "QQQ_5m": (qqq5, qqq_src), "SPX_daily": (spx_d, spxd_src),
                  "PRICE_5m": (feed5, feed_src), "SPX_1m": (spx1_, spx1_src), "VIX_5m": (vix5_, vix5_src)}
        settings = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in cfg.items()}
        version = U.APP_VERSION

        def make() -> bytes:
            return DD.export_audit(sess, base, a, frames, settings, version, U.now_et(), src_note)

        U.download_zip(f"⬇ Download this session's data · {sess:%b %d}", make, f"azrael_audit_{sess.isoformat()}.zip", key="audit_zip",
                       help="One zip: the bars, the morning map and this audit (compact + desk-format text) for any date.")
    with right:
        fig = C.session_chart(day, sess, grid, {"call_node": lv["call_node"], "put_node": lv["put_node"]},
                              {"call_fence": base["strike_grid"]["call_fence"], "put_fence": base["strike_grid"]["put_fence"]},
                              None, a.replay, a.settlement, title=f"THE VAULT | SESSION AUDIT & RULES REPLAY · {fmt_session_title(sess)}")
        st.plotly_chart(fig, use_container_width=True, key="audit_chart")
        q = st.columns(4)
        q[0].metric("1.0 walls held at settle", "yes" if a.inside_1sigma else "no" if a.inside_1sigma is not None else "—")
        q[1].metric("0.5 shelves mean-reverted", "yes" if a.half_shelves_held else "no" if a.half_shelves_held is not None else "—")
        q[2].metric("King Node touched", a.king_node_touched or "—")
        q[3].metric("Range in EM", f"{a.range_em:.2f}" if a.range_em is not None else "—")

    st.markdown("---")
    st.markdown("### Twenty of these in a row")
    hist = S.list_audits(60)
    if not hist:
        st.caption("No saved audits yet. Save one each day at 16:15 — over 20 sessions the loop compounds your read.")
        return
    stats = AU.history_stats(hist)
    c = st.columns(5)
    c[0].metric("Sessions", stats["n"])
    c[1].metric("Settled inside ±1.0", f"{stats.get('inside_1sigma_pct', 0):.0f} %")
    c[2].metric("Settled inside ±0.5", f"{stats.get('inside_half_pct', 0):.0f} %")
    c[3].metric("1.0 wall tested", f"{stats.get('walls_tested_pct', 0):.0f} %")
    c[4].metric("Replay avg R", f"{stats.get('replay_avg_r', 0):.2f}" if stats.get("replay_trades") else "—")
    if stats.get("by_regime"):
        st.caption("±1.0 held by regime: " + " · ".join(f"{ws.REGIME_NAME[k]} {v['held_pct']:.0f} % (n={v['n']})" for k, v in stats["by_regime"].items()))
    fig2 = C.r_history_chart(hist)
    if fig2 is not None:
        st.plotly_chart(fig2, use_container_width=True, key="r_hist")
    rows = [{"Session": h["session"], "Settle": h.get("settlement"), "Zone": h.get("settle_zone"), "Range EM": h.get("range_em"),
             "Replay": (f"A{h['replay']['archetype']} {h['replay']['side']} {h['replay']['r_multiple']:+.2f}R ({h['replay']['resolution']})" if h.get("replay") else "Watch Day"),
             "Regime": ws.REGIME_NAME.get(h.get("regime"), "")} for h in hist]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
