"""common.py — shared Streamlit plumbing for every view. Data access goes through the cached loaders here."""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime
from typing import Dict, Optional, Tuple

import pandas as pd
import streamlit as st

from core import plan as P
from core import workstation as ws
from data import fetcher as F
from data import storage as S
from utils.timeutil import (ET, current_phase, fmt_hm, fmt_session_title, is_trading_day, minutes_of, now_et,
                            prev_trading_day, session_date, T_CLOSE)

CSS_BASE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
:root { --bg:%(bg)s; --panel:%(panel)s; --panel2:%(panel2)s; --border:%(border)s; --text:%(text)s; --muted:%(muted)s; --num:%(num)s; }
html, body, [class*="css"] { font-family: 'IBM Plex Sans', system-ui, sans-serif; }
.stApp, .stApp > header, [data-testid="stAppViewContainer"], [data-testid="stHeader"] { background: var(--bg) !important; color: var(--text) !important; }
[data-testid="stSidebar"], [data-testid="stSidebar"] > div { background: var(--panel) !important; }
[data-testid="stSidebar"] *, .stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp .stMarkdown,
.stApp [data-testid="stMetricLabel"], .stApp [data-testid="stMetricValue"], .stApp [data-testid="stWidgetLabel"] { color: var(--text) !important; }
.stApp [data-testid="stCaptionContainer"], .stApp .small { color: var(--muted) !important; }
.stApp input, .stApp textarea, .stApp [data-baseweb="select"] > div, .stApp [data-baseweb="input"] > div, .stApp [data-testid="stNumberInputContainer"] > div
  { background: var(--panel2) !important; color: var(--text) !important; border-color: var(--border) !important; }
.stApp [data-testid="stExpander"] details { background: var(--panel) !important; border-color: var(--border) !important; }
.stApp .stDataFrame, .stApp [data-testid="stTable"] { background: var(--panel) !important; }
.stApp .stCode, .stApp pre, .stApp code { background: var(--panel2) !important; color: var(--text) !important; }
.stApp .stAlert { background: var(--panel) !important; }
.stApp hr { border-color: var(--border) !important; }
.block-container { padding-top: 0.8rem; padding-bottom: 2rem; }
.num, .mono { font-family: 'IBM Plex Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }
.statusbar { display:flex; flex-wrap:wrap; gap:14px 22px; align-items:baseline; padding:9px 14px; border-radius:6px;
             background:var(--panel); border:1px solid var(--border); margin-bottom:6px; }
.statusbar .item { display:inline-flex; gap:6px; align-items:baseline; }
.statusbar .k { color:var(--muted); font-size:0.78rem; }
.statusbar .v { color:var(--text); font-size:1.02rem; font-family:'IBM Plex Mono', monospace; }
.statusbar .up { color:#26a69a; } .statusbar .dn { color:#ef5350; }
.phase { padding:10px 14px; border-radius:6px; border-left:6px solid; margin:6px 0 12px 0; background:var(--panel); }
.phase .t { font-weight:600; font-size:1.02rem; color:var(--text); }
.phase .d { color:var(--muted); font-size:0.86rem; margin-top:2px; }
.phase .c { float:right; font-family:'IBM Plex Mono', monospace; color:var(--text); font-size:1.1rem; }
.lvl { display:grid; grid-template-columns: 1fr auto; gap:3px 12px; font-size:0.9rem; }
.lvl .name { color:var(--muted); } .lvl .val { font-family:'IBM Plex Mono', monospace; color:var(--num); text-align:right; }
.wall { color:#3d8bff !important; } .shelf { color:#ff9d2e !important; } .anchor { color:var(--text) !important; } .node { color:#b06cff !important; } .fence { color:#e3b600 !important; }
.tag { display:inline-block; padding:2px 8px; border-radius:4px; font-size:0.78rem; margin-right:6px; background:var(--panel2); color:var(--text); border:1px solid var(--border); }
.tag.ok { background:rgba(38,166,154,0.18); color:#26a69a; border-color:#26a69a; } .tag.warn { background:rgba(255,214,0,0.15); color:#d29a1c; border-color:#d29a1c; }
.tag.bad { background:rgba(239,83,80,0.15); color:#ef5350; border-color:#ef5350; }
.small { color:var(--muted); font-size:0.8rem; }
div[data-testid="stMetricValue"] { font-family:'IBM Plex Mono', monospace; }
</style>
"""
THEME_VARS = {
    "dark": {"bg": "#0e1117", "panel": "#16213e", "panel2": "#1a2a4a", "border": "#263653", "text": "#e0e0e0", "muted": "#a0a0a0", "num": "#ffffff"},
    "light": {"bg": "#ffffff", "panel": "#f3f5f8", "panel2": "#e9edf2", "border": "#d4dae2", "text": "#1f2937", "muted": "#5b6672", "num": "#111827"},
}

REFRESH_SECONDS = 60


def theme_name() -> str:
    return st.session_state.get("set_theme", "dark")


def setup() -> None:
    from utils import charts as _C
    name = theme_name()
    st.markdown(CSS_BASE % THEME_VARS[name], unsafe_allow_html=True)
    _C.set_theme(name)


# ── secrets ───────────────────────────────────────────────────────────────────
def tv_creds() -> Optional[Tuple[str, str]]:
    try:
        s = st.secrets.get("tvdatafeed", {})
        if s.get("username") and s.get("password"):
            return (s["username"], s["password"])
    except Exception:
        pass
    return None


def configure_storage() -> None:
    try:
        gs = st.secrets.get("gsheets", None)
        if gs:
            S.configure_gsheets({"service_account": dict(gs["service_account"]), "spreadsheet_key": gs["spreadsheet_key"],
                                 "worksheet": gs.get("worksheet", "Trade Journal")})
    except Exception:
        pass


# ── settings (sidebar, persisted in session_state) ────────────────────────────
DEFAULTS = {"c8": 25000.0, "c9": 1.0, "c27": 8.0, "c28": 0.55, "vix_print": "08:15", "es_print": "08:20",
            "ov_c5": 0.0, "ov_c6": 0.0, "ov_c7": "", "c10": 0.0, "macro": "", "auto_refresh": True, "theme": "dark",
            "candles": False, "overnight": True, "engine": "TradingView lightweight", "poll": 60,
            "price_symbol": "CAPITALCOM:SPX500", "rules_feed": "SPX cash 5-min (book)"}


def settings() -> Dict:
    for k, v in DEFAULTS.items():
        st.session_state.setdefault(f"set_{k}", v)
    with st.sidebar:
        st.radio("Theme", ["dark", "light"], horizontal=True, key="set_theme",
                 help="Dark is the SPX dash palette. Streamlit's own widgets follow .streamlit/config.toml — keep that file in the repo.")
        st.markdown("### Desk settings")
        sess = st.date_input("Session", value=st.session_state.get("set_session", session_date()), key="set_session_input")
        st.session_state["set_session"] = sess
        st.number_input("C8  Account size ($)", min_value=0.0, step=500.0, key="set_c8")
        st.number_input("C9  Max risk per trade (%)", min_value=0.1, max_value=10.0, step=0.1, key="set_c9")
        st.number_input("C27 Structural stop (SPX pts)", min_value=0.5, step=0.5, key="set_c27")
        st.number_input("C28 Option delta", min_value=0.05, max_value=1.0, step=0.05, key="set_c28")
        st.text_input("Price feed (chart & live price)", key="set_price_symbol",
                      help="24-hour feed drawn on the chart and used for the live price. SP:SPX is used only for the official prior close and settlement.")
        st.radio("Rules engine runs on", ["SPX cash 5-min (book)", "Price feed 5-min"], key="set_rules_feed",
                 help="The desk audit measures on the SPX index; switch if you want the scanner on the same feed as the chart.")
        st.radio("Chart", ["TradingView lightweight", "Plotly"], horizontal=True, key="set_engine")
        st.slider("Poll feeds every (seconds)", min_value=30, max_value=300, step=15, key="set_poll",
                  help="How often the page re-runs and pulls new 1-minute bars. 30 s is the practical floor on TradingView's anonymous feed.")
        st.checkbox("Candlesticks instead of closes line", key="set_candles")
        st.checkbox("Show /ES overnight (basis-adjusted) before the open", key="set_overnight")
        with st.expander("Feed timing · overrides", expanded=False):
            st.selectbox("VIX print used for C6", ["08:15", "08:30"], key="set_vix_print",
                         help="Desk bot: the 08:15 AM ET print. Manual: the live quote at 08:30.")
            st.selectbox("/ES price used for C7", ["08:20", "08:30"], key="set_es_print", help="Desk bot: the 08:20 AM ET price vs settle.")
            st.number_input("Override C5 SPX close (0 = feed)", min_value=0.0, step=0.01, key="set_ov_c5")
            st.number_input("Override C6 VIX (0 = feed)", min_value=0.0, step=0.01, key="set_ov_c6",
                            help="08:33 cross-check: if the desk bot's C13/C17 differ by more than 2 pts, align C6 to the bot's VIX.")
            st.text_input("Override C7 drift % (blank = feed)", key="set_ov_c7")
            st.text_input("Macro note (CPI · PPI · NFP · FOMC)", key="set_macro")
            st.checkbox(f"Auto-refresh every {REFRESH_SECONDS}s", key="set_auto_refresh")
        st.caption(f"ET {now_et().strftime('%H:%M:%S')} · {'DEMO DATA' if F.DEMO else 'live feeds'}")
    ov = {}
    if st.session_state["set_ov_c5"]:
        ov["c5"] = st.session_state["set_ov_c5"]
    if st.session_state["set_ov_c6"]:
        ov["c6"] = st.session_state["set_ov_c6"]
    if str(st.session_state["set_ov_c7"]).strip():
        try:
            ov["c7"] = float(st.session_state["set_ov_c7"])
        except ValueError:
            pass
    return {"session": sess, "c8": float(st.session_state["set_c8"]), "c9": float(st.session_state["set_c9"]),
            "c27": float(st.session_state["set_c27"]), "c28": float(st.session_state["set_c28"]),
            "vix_print": st.session_state["set_vix_print"], "es_print": st.session_state["set_es_print"],
            "overrides": ov, "macro": st.session_state["set_macro"], "auto": st.session_state["set_auto_refresh"],
            "c10": st.session_state.get("c10_value"), "candles": bool(st.session_state.get("set_candles")),
            "overnight": bool(st.session_state.get("set_overnight", True)), "engine": st.session_state.get("set_engine", "TradingView lightweight"),
            "poll": int(st.session_state.get("set_poll", 60)),
            "price_symbol": (st.session_state.get("set_price_symbol") or "CAPITALCOM:SPX500").strip().upper(),
            "rules_feed": st.session_state.get("set_rules_feed", "SPX cash 5-min (book)")}


def bucket(seconds: Optional[int] = None) -> int:
    """Cache key that changes once per poll interval (the slider), so each poll fetches exactly once."""
    s = seconds or int(st.session_state.get("set_poll", REFRESH_SECONDS))
    return int(time.time() // max(s, 15))


# ── cached feeds ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def bars(key: str, interval: str, n: int, _b: int) -> Tuple[Optional[pd.DataFrame], str]:
    return F.get_bars(key, interval, n, tv_creds())


@st.cache_data(ttl=300, show_spinner=False)
def price_bars(ticker: str, interval: str, n: int, _b: int) -> Tuple[Optional[pd.DataFrame], str]:
    return F.get_symbol_bars(ticker, interval, n, tv_creds())


@st.cache_data(ttl=300, show_spinner=False)
def build_plan(session_iso: str, vix_print: str, es_print: str, c8: float, c9: float, c27: float, c28: float,
               overrides_json: str, c10: Optional[float], _b: int) -> Dict:
    return P.build_plan(date.fromisoformat(session_iso), vix_print, es_print, c8, c9, c27, c28,
                        json.loads(overrides_json), tv_creds(), c10)


@st.cache_data(ttl=300, show_spinner=False)
def chain(expiry: str, underlying: str, _b: int) -> Optional[pd.DataFrame]:
    return F.cboe_chain(expiry, underlying)


def get_plan(cfg: Dict) -> Tuple[Dict, str]:
    """Locked plan if one exists for the session (tier 1/2), else a provisional live build (tier 3).
    C8/C9/C27/C28/C10 are always re-applied to the locked C5/C6/C7."""
    sess: date = cfg["session"]
    live = build_plan(sess.isoformat(), cfg["vix_print"], cfg["es_print"], cfg["c8"], cfg["c9"], cfg["c27"], cfg["c28"],
                      json.dumps(cfg["overrides"], sort_keys=True), None, bucket())
    label, plan = P.lock_status(sess, live)
    if plan.get("ok"):
        plan = P.rebuild_from_inputs(plan, cfg["c8"], cfg["c9"], cfg["c27"], cfg["c28"], cfg.get("c10"))
        plan["live_inputs"] = live.get("inputs", {})
    return plan, label


def chart_window(session: date) -> Tuple[datetime, datetime]:
    """Rolling 12 hours ending one hour ahead of now until the open; then pre-market + the whole session; after the
    close, the session alone."""
    from datetime import timedelta, time as dtime
    now = now_et()
    if session != now.date():
        return datetime.combine(session, dtime(9, 25), tzinfo=ET), datetime.combine(session, dtime(16, 5), tzinfo=ET)
    m = minutes_of(now)
    if m < 9 * 60 + 30:
        return now - timedelta(hours=11), now + timedelta(hours=1)
    if m < 16 * 60 + 5:
        return datetime.combine(session, dtime(7, 30), tzinfo=ET), datetime.combine(session, dtime(16, 5), tzinfo=ET)
    return datetime.combine(session, dtime(9, 25), tzinfo=ET), datetime.combine(session, dtime(16, 5), tzinfo=ET)


def proxy_overnight_spx(plan: Dict, session: date) -> Tuple[Optional[pd.DataFrame], str]:
    """Capital.com SPX500 (or the next proxy that answers) from 18:00 the prior evening to the open, shifted onto
    SPX points by the prior-16:00 basis. Falls back to /ES when the CFD feeds give nothing."""
    from datetime import timedelta, time as dtime
    px1, src = bars("PROXY", "1", 1400, bucket())
    basis = 0.0                                   # Capital.com SPX500 (and the CFD fallbacks) track the cash index directly
    if px1 is None or px1.empty or "CME" in src:
        es = es_overnight_spx(plan, session)
        return es, "/ES (basis-adjusted)"
    start = datetime.combine(session - timedelta(days=1), dtime(18, 0), tzinfo=ET)
    end = datetime.combine(session, dtime(9, 30), tzinfo=ET)
    w = px1[(px1.index >= start) & (px1.index < end)].copy()
    if w.empty:
        return None, src
    for c in ("open", "high", "low", "close"):
        w[c] = w[c] - (basis or 0.0)
    return w, src


def es_overnight_spx(plan: Dict, session: date) -> Optional[pd.DataFrame]:
    """/ES 1-minute bars from 18:00 the prior evening to the open, shifted into SPX points with the prior-16:00 basis."""
    es1, _ = bars("ES", "1", 1400, bucket())
    basis = (plan.get("inputs") or {}).get("es_basis") if plan.get("ok") else None
    if es1 is None or es1.empty or basis is None:
        return None
    from datetime import timedelta, time as dtime
    start = datetime.combine(session - timedelta(days=1), dtime(18, 0), tzinfo=ET)
    end = datetime.combine(session, dtime(9, 30), tzinfo=ET)
    w = es1[(es1.index >= start) & (es1.index < end)].copy()
    if w.empty:
        return None
    for c in ("open", "high", "low", "close"):
        w[c] = w[c] - basis
    return w


def spx_open_print(session: date) -> Optional[float]:
    """The official 09:30 cash open — the 09:30 1-minute bar's open (for C10 on gap days)."""
    df, _ = bars("SPX", "1", 800, bucket())
    day = F.session_slice(df, session)
    if day.empty:
        return None
    b = day[(day.index.hour == 9) & (day.index.minute == 30)]
    return float(b["open"].iloc[0]) if not b.empty else None


# ── header widgets ────────────────────────────────────────────────────────────
def _item(k, v, cls=""):
    return f"<span class='item'><span class='k'>{k}</span><span class='v {cls}'>{v}</span></span>"


def status_bar(plan: Dict, label: str, session: date) -> None:
    sym = (st.session_state.get("set_price_symbol") or "CAPITALCOM:SPX500").strip().upper()
    px1, src = price_bars(sym, "1", 300, bucket())
    last, last_t = F.latest(px1)
    i = plan.get("inputs", {}) if plan.get("ok") else {}
    c5 = i.get("c5")
    items = []
    if last is not None:
        items.append(_item(src or sym, f"{last:,.2f}" + (f" <span class='k'>({last_t})</span>" if last_t else "")))
        if c5:
            chg = last - c5
            items.append(_item("vs C5", f"{chg:+.2f} ({chg / c5 * 100:+.2f}%)", "up" if chg >= 0 else "dn"))
    else:
        items.append(_item("SPX", "no bars"))
    if plan.get("ok"):
        items.append(_item("C5 close", f"{i['c5']:,.2f}"))
        items.append(_item("C6 VIX", f"{i['c6']:.2f}"))
        vl = plan.get("live_inputs", i).get("vix_live")
        if vl:
            items.append(_item("VIX now", f"{vl:.2f}"))
        items.append(_item("C7 /ES", f"{i['c7']:+.2f}%" if i.get("c7") is not None else "—"))
        items.append(_item("EM C12", f"±{plan['grid']['c12']:.2f}"))
        items.append(_item("Regime", ws.REGIME_NAME[plan["regime"]]))
    items.append(_item(fmt_session_title(session), now_et().strftime("%H:%M:%S") + " ET"))
    items.append(f"<span class='tag {'ok' if label.startswith('LOCKED') else 'warn'}'>{label}</span>")
    st.markdown("<div class='statusbar'>" + "".join(items) + "</div>", unsafe_allow_html=True)


def phase_banner() -> None:
    ph = current_phase()
    m = minutes_of(now_et())
    cd = f"{fmt_hm(ph.next_at)} in {ph.next_at - m} min" if ph.next_at and ph.next_at > m else ""
    st.markdown(f"<div class='phase' style='border-color:{ph.colour}'><span class='c'>{cd}</span>"
                f"<div class='t'>{ph.label}</div><div class='d'>{ph.detail}</div></div>", unsafe_allow_html=True)


def level_table(plan: Dict, gap: bool = False) -> None:
    g, sg = plan["grid"], plan["strike_grid"]
    rows = [("+1.0 EM wall · C13", g["c13"], "wall"), ("+0.5 EM shelf · C14", g["c14"], "shelf"), ("Cash anchor · C15", g["c15"], "anchor"),
            ("−0.5 EM shelf · C16", g["c16"], "shelf"), ("−1.0 EM wall · C17", g["c17"], "wall"),
            ("Call King Node (+0.5 EM)", sg["call_node"], "node"), ("Put King Node (−0.5 EM)", sg["put_node"], "node"),
            ("Upper / lower Strike Wall", f"{sg['upper_wall']:,.0f} / {sg['lower_wall']:,.0f}", "wall"),
            ("Fences (±1.25 EM) · short call above / short put below", f"{sg['call_fence']:,.0f} / {sg['put_fence']:,.0f}", "fence")]
    if gap and plan["gap"]["active"]:
        gp = plan["gap"]
        rows += [("Gap anchor · C39", gp["c39"], "node"), ("+0.5 intraday shelf · C41", gp["c41"], "shelf"),
                 ("−0.5 intraday shelf · C42", gp["c42"], "shelf"), ("Intraday King Nodes · C43 / C44", f"{gp['c43']:,.0f} / {gp['c44']:,.0f}", "node"),
                 ("Intraday fences · C45 / C46", f"{gp['c45']:,.0f} / {gp['c46']:,.0f}", "fence")]
    html = "<div class='lvl'>" + "".join(
        f"<div class='name {c}'>{n}</div><div class='val'>{(f'{v:,.2f}' if isinstance(v, (int, float)) else v)}</div>" for n, v, c in rows) + "</div>"
    st.markdown(html, unsafe_allow_html=True)


def last_completed_session(now: Optional[datetime] = None) -> date:
    now = now or now_et()
    d = now.date()
    if is_trading_day(d) and minutes_of(now) >= T_CLOSE:
        return d
    return prev_trading_day(d)
