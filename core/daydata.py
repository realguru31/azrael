"""
daydata.py — "Download today's data": one zip with everything the desk used and decided for a session, so any day can be
replayed offline through the same engine and reconciled line by line against the desk's Discord posts.

Pure functions (no Streamlit): the sidebar button and the Settlement audit page pass in what they already hold; the
zip is built when the button is clicked. `audit_for()` is also what the Settlement audit page itself runs, so the
audit text in the zip is exactly the page's text.
"""
from __future__ import annotations

import io
import json
import platform
import re
import zipfile
from datetime import date, datetime
from typing import Dict, Optional, Tuple

import pandas as pd

from core import audit as AU
from core import meic as MC
from core import rules as R
from data import fetcher as F
from utils.timeutil import ET, fmt_hm, fmt_session_title, minutes_of

README = """AZRAEL DESK — DAY DATA EXPORT
All times are US/Eastern. Bars are stamped at their OPEN (the "10:45 bar" closes at 10:50).

meta.json          app version, session, when exported, the settings used, lock tier, every feed's source / rows / read time
plan.json          the 08:30 map the desk ran on (the locked baseline when one exists): C5 C6 C7, grid, nodes, fences, sizing
bars/*.csv         every series exactly as read from the feeds: time_et, open, high, low, close, volume
                     SPX_5m (SP:SPX, the rules feed) · SPY_5m · QQQ_5m · PRICE_1m (CAPITALCOM:SPX500 chart / live price)
                     SPX_1m (Scenario Book send rule) · VIX_1m (08:15 print) · VIX_5m · PRICE_5m · SPX_daily (C5, settlement)
chain_0dte.csv     the options chain snapshot behind the OI / volume nodes and MEIC mids (source in meta.json)
state.json         the app's decisions at export time: the card state, the book trade, every archetype's replay and reason,
                   the 09:50 gate, the Scenario Book checks, the MEIC ticket and defense distances, the alerts that fired
audit_compact.txt  the Settlement audit page's compact text for this session (a LIVE preview before 16:00)
audit_long.txt     the desk-format long text (word-by-word reconcile with the 04:15 post)
"""


# ── the Settlement audit, exactly as the page builds it ──────────────────────
def audit_for(sess: date, base: Dict, spx5: Optional[pd.DataFrame], spy5: Optional[pd.DataFrame], qqq5: Optional[pd.DataFrame],
              spx_daily: Optional[pd.DataFrame], price5: Optional[pd.DataFrame], spx1: Optional[pd.DataFrame],
              vix5: Optional[pd.DataFrame], now: datetime) -> Tuple[AU.SessionAudit, Dict, Dict, pd.DataFrame]:
    """(audit, rule levels, grid, session bars) — the code the Settlement audit page ran inline up to 1.8.0, moved here
    unchanged so the page and the export share it."""
    day = F.session_slice(spx5, sess)
    settle = None
    if spx_daily is not None and not spx_daily.empty:
        m = spx_daily[[x.date() == sess for x in spx_daily.index]]
        completed = sess < now.date() or minutes_of(now) >= 16 * 60
        if not m.empty and completed:
            settle = float(m["close"].iloc[-1])
    lv = R.rule_levels(base)
    grid = {k: lv[k] for k in ("C13", "C14", "C15", "C16", "C17")}
    # proxies against their own morning bands
    proxies = []
    for key, blk in (("SPY", base.get("spy")), ("FEED", base.get("es"))):
        if not blk:
            continue
        b5 = spy5 if key == "SPY" else price5
        d5 = F.session_slice(b5, sess)
        px = None
        if not d5.empty:
            at16 = d5[(d5.index.hour == 15) & (d5.index.minute == 55)]
            px = float(at16["close"].iloc[-1]) if not at16.empty else float(d5["close"].iloc[-1])
        proxies.append({"name": blk.get("name", key), "settle": px, "band_lo": blk["band_lo"], "band_hi": blk["band_hi"], "em": blk["em"]})
    a = AU.build_audit(fmt_session_title(sess), day, F.session_slice(spy5, sess), F.session_slice(qqq5, sess), settle,
                       base["grid"]["c15"], base["inputs"]["c6"], base["inputs"].get("vix_print", "08:15"), grid, lv["em"],
                       lv["put_node"], lv["call_node"], base["strike_grid"]["put_fence"], base["strike_grid"]["call_fence"],
                       base["inputs"]["c6"], proxies, base.get("stop_clusters"))
    # app scoring of the replay trade (Scenario Book), for the reconcile against the desk's "Live Idea" section
    if a.replay is not None:
        try:
            from core import scoring as SCR
            from core.rules import Replay as _R
            rr = _R(**{k: a.replay[k] for k in _R.__dataclass_fields__ if k in a.replay})
            vday = F.session_slice(vix5, sess) if vix5 is not None else None
            vnow = None
            if vday is not None and not vday.empty:
                at = vday[(vday.index.hour * 60 + vday.index.minute) <= (int(rr.trigger_time[:2]) * 60 + int(rr.trigger_time[3:]) + 5)]
                vnow = float(at["close"].iloc[-1]) if not at.empty else None
            scd = SCR.score_idea(rr, base, lv, day, F.session_slice(spy5, sess), F.session_slice(qqq5, sess), R.gate_test(day) if not day.empty else None,
                                 vnow, F.session_slice(spx1, sess), 16 * 60)
            a.score_line = f"score {scd.score:.1f} / 9.5 ({scd.send_rule}) — {scd.status_text}"
        except Exception as e:
            a.score_line = f"unavailable ({type(e).__name__})"
    return a, lv, grid, day


# ── serialisation ─────────────────────────────────────────────────────────────
def frame_csv(df: pd.DataFrame) -> str:
    cols = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    out = df[cols].copy()
    out.index = [pd.Timestamp(t).isoformat() for t in out.index]
    out.index.name = "time_et"
    return out.to_csv(float_format="%.4f")


def _strip(html_txt: Optional[str]) -> str:
    return re.sub(r"<[^>]+>", "", html_txt or "").strip()


def _iso(t) -> Optional[str]:
    if t is None:
        return None
    if isinstance(t, (int, float)):
        return datetime.fromtimestamp(float(t), ET).isoformat()
    return pd.Timestamp(t).isoformat()


def build_zip(meta: Dict, plan: Dict, frames: Dict[str, Tuple[Optional[pd.DataFrame], str]], chain: Optional[pd.DataFrame] = None,
              state: Optional[Dict] = None, texts: Optional[Dict[str, str]] = None) -> bytes:
    """frames: name -> (DataFrame, source). Missing or empty frames are listed in meta.json with 0 rows."""
    buf = io.BytesIO()
    manifest = {}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", README)
        for name, (df, src) in frames.items():
            if df is None or len(df) == 0:
                manifest[name] = {"rows": 0, "source": src}
                continue
            z.writestr(f"bars/{name}.csv", frame_csv(df))
            manifest[name] = {"rows": int(len(df)), "first": _iso(df.index[0]), "last": _iso(df.index[-1]), "source": src,
                              "read_at": _iso(df.attrs.get("fetched_at")) if getattr(df, "attrs", None) else None}
        z.writestr("plan.json", json.dumps(plan, indent=1, default=str))
        if chain is not None and len(chain):
            z.writestr("chain_0dte.csv", chain.to_csv(index=False, float_format="%.4f"))
        if state is not None:
            z.writestr("state.json", json.dumps(state, indent=1, default=str))
        for name, txt in (texts or {}).items():
            z.writestr(name, txt)
        z.writestr("meta.json", json.dumps(dict(meta, frames=manifest), indent=1, default=str))
    return buf.getvalue()


def state_from_snapshot(s, alerts: Optional[Dict] = None) -> Dict:
    """The live desk's decisions at export time, from the shared snapshot (views/live.py Snap)."""
    out: Dict = {"session": s.sess.isoformat(), "now_et": s.now.isoformat(), "clock": fmt_hm(s.m), "live_session": s.today,
                 "lock": s.label, "last_price": s.last, "last_price_bar": s.last_t, "price_feed": s.px_src, "vix_now": s.vix_now,
                 "rules_read_bars_closed_by": _iso(s.fetched_at),
                 "forming_bar": {"open": _iso(s.bar.get("open")), "close": _iso(s.bar.get("close"))} if s.bar else None}
    b = s.banner
    if b is not None:
        out["card"] = {"state": b.state, "headline": b.headline, "sub": b.sub, "trade": b.trade, "exits": b.exits, "notes": b.notes,
                       "credit": _strip(b.credit), "plays": [p.as_dict() for p in b.plays]}
    if s.gate is not None:
        out["gate_0950"] = s.gate.as_dict()
    if s.live_s:
        ch = s.live_s.get("chosen")
        out["rules_replay_live"] = {"chosen": ch.as_dict() if ch is not None else None,
                                    "results": {f"A{k}": v.as_dict() for k, v in (s.live_s.get("results") or {}).items()},
                                    "also_checked": s.live_s.get("also_checked"), "proximity": s.live_s.get("proximity"),
                                    "eligible": s.live_s.get("eligible")}
    if s.score is not None:
        out["scenario_book"] = s.score.as_dict()
    if s.ticket:
        out["meic"] = {"ticket": s.ticket, "defense": MC.defense_status(s.last if s.today else None, s.ticket)}
    if s.three:
        out["three_ticker_live"] = s.three
    out["alerts"] = alerts or {}
    return out


def _fetch(key: str, interval: str, n: int, creds, errors: Dict) -> Tuple[Optional[pd.DataFrame], str]:
    try:
        df, src = F.get_bars(key, interval, n, creds)
        return df, src
    except Exception as e:                                   # a feed hiccup must not lose the rest of the export
        errors[f"{key}_{interval}"] = f"{type(e).__name__}: {e}"
        return None, ""


def export_live(s, cfg: Dict, creds, alerts: Dict, version: str, now: datetime) -> bytes:
    """Zip for the live snapshot `s`: the frames the desk ran on, plus the series the audit needs, read now."""
    errors: Dict[str, str] = {}
    raw = dict(getattr(s, "raw", {}) or {})
    frames: Dict[str, Tuple[Optional[pd.DataFrame], str]] = {k: raw[k] for k in ("SPX_5m", "SPY_5m", "QQQ_5m", "PRICE_1m", "PRICE_5m") if k in raw}
    for name, key, iv, n in (("SPX_1m", "SPX", "1", 800), ("VIX_1m", "VIX", "1", 1400), ("VIX_5m", "VIX", "5", 400), ("SPX_daily", "SPX", "D", 8)):
        frames[name] = _fetch(key, iv, n, creds, errors)
    if "PRICE_5m" not in frames:
        try:
            frames["PRICE_5m"] = F.get_symbol_bars(cfg.get("price_symbol", "CAPITALCOM:SPX500"), "5", 800, creds)
        except Exception as e:
            errors["PRICE_5"] = f"{type(e).__name__}: {e}"
    texts: Dict[str, str] = {}
    try:
        a, _, _, _ = audit_for(s.sess, s.plan, frames.get("SPX_5m", (None, ""))[0], frames.get("SPY_5m", (None, ""))[0],
                               frames.get("QQQ_5m", (None, ""))[0], frames["SPX_daily"][0], frames.get("PRICE_5m", (None, ""))[0],
                               frames["SPX_1m"][0], frames["VIX_5m"][0], now)
        texts["audit_compact.txt"] = AU.audit_text_compact(a)
        texts["audit_long.txt"] = AU.audit_text(a)
    except Exception as e:
        errors["audit"] = f"{type(e).__name__}: {e}"
    state = None
    try:
        state = state_from_snapshot(s, alerts)
    except Exception as e:
        errors["state"] = f"{type(e).__name__}: {e}"
    meta = {"app": "Azraël Desk", "version": version, "kind": "live session export", "session": s.sess.isoformat(),
            "exported_at_et": now.isoformat(), "settings": cfg, "lock": s.label, "plan_sources": (s.plan or {}).get("sources"),
            "chain_source": (s.chain_src or {}).get("note"), "python": platform.python_version(), "pandas": pd.__version__,
            "errors": errors}
    return build_zip(meta, s.plan, frames, s.chain, state, texts)


def export_audit(sess: date, base: Dict, a: AU.SessionAudit, frames: Dict[str, Tuple[Optional[pd.DataFrame], str]], cfg: Dict,
                 version: str, now: datetime, map_source: str) -> bytes:
    """Zip for a Settlement audit page session (any date): the frames the page used and its audit, as shown."""
    meta = {"app": "Azraël Desk", "version": version, "kind": "settlement audit export", "session": sess.isoformat(),
            "exported_at_et": now.isoformat(), "settings": cfg, "map_source": map_source, "plan_sources": base.get("sources"),
            "python": platform.python_version(), "pandas": pd.__version__}
    texts = {"audit_compact.txt": AU.audit_text_compact(a), "audit_long.txt": AU.audit_text(a)}
    state = {"audit": a.as_dict()}
    return build_zip(meta, base, frames, None, state, texts)
