"""journal_view.py — Tab 2, the 1-Trade-Per-Day Accountability Journal, with the workbook's exact columns and header formulas."""
from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from core import workstation as ws
from data import storage as S
from utils.timeutil import now_et
from views import common as U


def render(cfg, plan, label):
    sess = cfg["session"]
    U.status_bar(plan, label, sess)
    st.markdown("### 1-Trade-Per-Day Accountability Journal (Tab 2)")
    df = S.load_journal()
    if df.empty and S.gsheets_pull() is not None:
        df = S.gsheets_pull(); S.save_journal(df)
    stats = S.journal_stats(df)
    c = st.columns(5)
    c[0].metric("TOTAL TRADES", stats["total_trades"])
    c[1].metric("NET PnL ($)", f"{stats['net_pnl']:,.2f}")
    c[2].metric("WIN RATE (%)", f"{stats['win_rate']:.1f}")
    c[3].metric("AVG R-MULTIPLE", f"{stats['avg_r']:.2f}")
    d = stats["discipline"]
    c[4].metric("DISCIPLINE SCORE %", f"{d:.1f}", help="Sessions with one trade or fewer ÷ total sessions. 90+ = disciplined desk operator; below 80 = your off-plan sessions are your worst.")
    if stats["total_trades"]:
        st.markdown(f"<span class='tag {'ok' if d >= 90 else 'warn' if d >= 80 else 'bad'}'>{'Disciplined desk operator' if d >= 90 else 'Watch the off-plan days' if d >= 80 else 'Below 80: the deviation days contain the catastrophic losses'}</span>", unsafe_allow_html=True)

    st.markdown("**Log today's row** (broker P&L confirmation only — no estimated P&L)")
    card = S.load_cards().get(sess.isoformat())
    with st.form("journal_row", clear_on_submit=True):
        r1 = st.columns(4)
        date_v = r1[0].text_input("Date", value=sess.strftime("%m/%d/%Y"))
        setup = r1[1].selectbox("Setup Type", ws.JOURNAL_SETUP_TYPES,
                                index=ws.JOURNAL_SETUP_TYPES.index(card["archetype"]) if card and card.get("archetype") in ws.JOURNAL_SETUP_TYPES else 0)
        strike = r1[2].text_input("Strike & Expiry", placeholder="SPXW 7645C 0DTE")
        entry_t = r1[3].text_input("Entry Time", placeholder="10:20 AM")
        r2 = st.columns(4)
        inval = r2[0].text_input("Invalidation Level (Stop)", value=card["invalidation_level"] if card and card.get("archetype") != "Watch Day" else "")
        exit_p = r2[1].text_input("Exit Price", placeholder="7674 (anchor)")
        pnl = r2[2].number_input("PnL ($)", step=10.0, value=0.0)
        pnl_pct = r2[3].number_input("PnL (%)", step=0.01, value=0.0)
        r3 = st.columns(3)
        rmult = r3[0].number_input("R-Multiple", step=0.01, value=0.0)
        rule = r3[1].selectbox("1-Trade Rule?", ["Yes", "No"])
        chan = r3[2].selectbox("Discord Channel Logged", ws.JOURNAL_CHANNELS)
        notes = st.text_area("Microstructure Notes", height=70, placeholder="Regime, what the shelves did, whether the King Node acted as gravity, where stops were run, stop moved? (never).")
        if st.form_submit_button("Append row", type="primary"):
            S.append_journal({"Date": date_v, "Setup Type": setup, "Strike & Expiry": strike, "Entry Time": entry_t,
                              "Invalidation Level (Stop)": inval, "Exit Price": exit_p, "PnL ($)": pnl, "PnL (%)": pnl_pct,
                              "R-Multiple": rmult, "1-Trade Rule?": rule, "Discord Channel Logged": chan, "Microstructure Notes": notes})
            st.success("Row appended."); st.rerun()

    st.markdown("**Journal** — edit in place; the Setup Type and channel lists are the workbook's data-validation lists")
    edited = st.data_editor(
        df, num_rows="dynamic", use_container_width=True, hide_index=True, key="journal_editor",
        column_config={
            "Setup Type": st.column_config.SelectboxColumn("Setup Type", options=ws.JOURNAL_SETUP_TYPES),
            "1-Trade Rule?": st.column_config.SelectboxColumn("1-Trade Rule?", options=["Yes", "No"]),
            "Discord Channel Logged": st.column_config.SelectboxColumn("Discord Channel Logged", options=ws.JOURNAL_CHANNELS),
            "Microstructure Notes": st.column_config.TextColumn("Microstructure Notes", width="large"),
        })
    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("Save edits", use_container_width=True):
            S.save_journal(edited); st.success("Saved."); st.rerun()
    with b2:
        st.download_button("Download CSV (Tab 2 columns)", df.to_csv(index=False).encode(), "trade_journal.csv", "text/csv", use_container_width=True)
    with b3:
        up = st.file_uploader("Upload CSV to replace", type=["csv"], label_visibility="collapsed")
        if up is not None:
            new = pd.read_csv(up, dtype=str).fillna("")
            S.save_journal(new); st.success("Journal replaced."); st.rerun()

    # ── Ch.5: what the journal tells you after 30 sessions
    if not df.empty:
        st.markdown("---")
        st.markdown("**What the journal says** (R by setup, by regime of the session, by entry hour)")
        x = df.copy()
        x["R"] = pd.to_numeric(x["R-Multiple"], errors="coerce")
        x["PnL"] = pd.to_numeric(x["PnL ($)"], errors="coerce")
        x["hour"] = x["Entry Time"].astype(str).str.extract(r"(\d{1,2}):")[0]
        # regime from the locked baselines of each date
        def regime_of(dstr):
            try:
                d = pd.to_datetime(dstr).date().isoformat()
                bl = S.load_baseline(d)
                return ws.REGIME_NAME.get(bl["regime"], "—") if bl else "—"
            except Exception:
                return "—"
        x["Regime"] = x["Date"].apply(regime_of)
        c1, c2, c3 = st.columns(3)
        with c1:
            st.dataframe(x.groupby("Setup Type")["R"].agg(["count", "mean"]).rename(columns={"count": "n", "mean": "avg R"}).round(2), use_container_width=True)
        with c2:
            st.dataframe(x.groupby("Regime")["R"].agg(["count", "mean"]).rename(columns={"count": "n", "mean": "avg R"}).round(2), use_container_width=True)
        with c3:
            st.dataframe(x.groupby("hour")["R"].agg(["count", "mean"]).rename(columns={"count": "n", "mean": "avg R"}).round(2), use_container_width=True)
        wins = (x["PnL"] > 0).sum(); n = x["PnL"].notna().sum()
        if n:
            st.caption(f"Actual win rate {wins / n * 100:.1f} % on {n} logged trades — compare with what you think it is.")
