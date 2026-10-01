"""audit_view.py — the 04:15 PM Settlement Audit & Rules Replay, plus the 20-session feedback loop."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from core import audit as AU
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

    spx5, _ = U.bars("SPX", "5", 800, U.bucket())
    spy5, _ = U.bars("SPY", "5", 800, U.bucket())
    qqq5, _ = U.bars("QQQ", "5", 800, U.bucket())
    day = F.session_slice(spx5, sess)
    settle = None
    spx_d, _ = U.bars("SPX", "D", 8, U.bucket())
    if spx_d is not None and not spx_d.empty:
        m = spx_d[[x.date() == sess for x in spx_d.index]]
        completed = sess < U.now_et().date() or U.minutes_of(U.now_et()) >= 16 * 60
        if not m.empty and completed:
            settle = float(m["close"].iloc[-1])
    lv = R.rule_levels(base)
    grid = {k: lv[k] for k in ("C13", "C14", "C15", "C16", "C17")}
    # proxies against their own morning bands
    proxies = []
    for key, blk in (("SPY", base.get("spy")), ("/ES", base.get("es"))):
        if not blk:
            continue
        b5, _ = U.bars("SPY" if key == "SPY" else "ES", "5", 800, U.bucket())
        d5 = F.session_slice(b5, sess)
        px = None
        if not d5.empty:
            at16 = d5[(d5.index.hour == 15) & (d5.index.minute == 55)]
            px = float(at16["close"].iloc[-1]) if not at16.empty else float(d5["close"].iloc[-1])
        proxies.append({"name": key, "settle": px, "band_lo": blk["band_lo"], "band_hi": blk["band_hi"], "em": blk["em"]})
    a = AU.build_audit(fmt_session_title(sess), day, F.session_slice(spy5, sess), F.session_slice(qqq5, sess), settle,
                       base["grid"]["c15"], base["inputs"]["c6"], base["inputs"].get("vix_print", "08:15"), grid, lv["em"],
                       lv["put_node"], lv["call_node"], base["strike_grid"]["put_fence"], base["strike_grid"]["call_fence"],
                       base["inputs"]["c6"], proxies, base.get("stop_clusters"))
    st.caption(f"Map source: {src_note}. Rules measured on {'the re-anchored gap grid' if lv['mode'] == 'gap' else 'the standard grid'}; on the index, not fills.")
    left, right = st.columns([0.45, 0.55])
    with left:
        st.code(AU.audit_text(a), language=None)
        cols = st.columns(2)
        if cols[0].button("Save this audit", type="primary", use_container_width=True):
            S.save_audit(sess.isoformat(), a.as_dict()); st.success("Saved."); st.rerun()
        if saved:
            cols[1].caption(f"Saved audit on file for {sess}.")
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
