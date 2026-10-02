"""
tests/test_smoke.py — demo-mode end-to-end smoke test. Runs without network, Streamlit or Plotly installed:
both are stubbed, AZRAEL_DEMO=1 feeds synthetic bars. It exercises every code path the pages call, so a release
cannot ship with an import error, a bad f-string, or a banner state that raises.

Run:  python tests/test_smoke.py      (also collected by pytest)
"""
import os
import re
import sys
import types
from datetime import date, datetime, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["AZRAEL_DEMO"] = "1"
os.environ["AZRAEL_STORE"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_store_smoke")

# ── stubs ─────────────────────────────────────────────────────────────────────
_out = []
st = types.ModuleType("streamlit")
st.markdown = lambda html, unsafe_allow_html=False: _out.append(html)
st.cache_data = lambda **k: (lambda fn: fn)
st.session_state = {"set_price_symbol": "CAPITALCOM:SPX500", "set_poll": 60, "set_cboe_fallback": True}
st.secrets = {}
sys.modules["streamlit"] = st
pl = types.ModuleType("plotly"); go = types.ModuleType("plotly.graph_objects")
for n in ("Figure", "Scatter", "Bar", "Candlestick"):
    setattr(go, n, object)
sys.modules["plotly"] = pl; sys.modules["plotly.graph_objects"] = go

from zoneinfo import ZoneInfo  # noqa: E402
import pandas as pd  # noqa: E402

from core import plan as P, rules as R, execution as X, scenario as SC, workstation as ws, audit as AU, credit as CR  # noqa: E402
from data import fetcher as F, storage as S  # noqa: E402
from utils import lwchart as LW  # noqa: E402
from utils.text import strike_grid_post  # noqa: E402
from views import common as U  # noqa: E402

ET = ZoneInfo("America/New_York")
SESS = date(2026, 10, 1)


def _plan():
    p = P.build_plan(SESS, "08:15", "08:20", 25000, 1.0, 8.0, 0.55, {}, None, None, "CAPITALCOM:SPX500")
    assert p["ok"], p
    return p


def test_plan_builds_and_has_every_cell():
    p = _plan()
    for k in ("c5", "c6", "c7", "price_print_px", "pm_high_spx", "prev_high"):
        assert k in p["inputs"], k
    assert set(p["levels"]) == {"C13", "C14", "C15", "C16", "C17"}
    assert p["strike_grid"]["call_node"] % 5 == 0 and p["gap"]["c38"] == ws.C38_STANDARD_BLANK
    assert p["spy"] and p["es"] and p["es"]["name"].startswith("CAPITALCOM:SPX500")
    assert "price" in p["sources"] and "es" not in p["sources"]            # no CME anywhere
    assert "CME" not in str(p["notes"]) and "/ES" not in p["notes"]["c7"]


def test_lock_tiers_round_trip():
    p = _plan()
    S.save_baseline(SESS.isoformat(), {**p, "locked_at": "08:31 ET", "lock_source": "test"})
    label, saved = P.lock_status(SESS, p)
    assert label.startswith("LOCKED") and saved["lock_source"] == "test"
    P.unlock(SESS)
    label, _ = P.lock_status(date(2030, 1, 2), p)
    assert label.startswith("PROVISIONAL")


def test_status_bar_and_strike_grid_text():
    p = _plan()
    U.status_bar(p, "PROVISIONAL · locks at 08:30 ET", SESS)
    html = re.sub(r"<[^>]+>", " ", _out[-1])
    assert "CAPITALCOM:SPX500" in html and "C6 VIX" in html and "C7 drift" in html and "/ES" not in html
    txt = strike_grid_post(p, "THURSDAY (OCT 01, 2026)")
    assert "Call King Node (+0.5 EM)" in txt and "Beyond 0DTE" in txt and "/ES" not in txt


def test_banner_state_machine_through_the_day():
    p = _plan()
    lv = R.rule_levels(p)
    spx5, _ = F.get_bars("SPX", "5", 400)
    day = F.session_slice(spx5, SESS)
    seen = []
    for mins in (2 * 60, 8 * 60 + 45, 9 * 60 + 40, 10 * 60 + 5, 11 * 60 + 10, 11 * 60 + 45, 16 * 60 + 30):
        gate = R.gate_test(day) if not day.empty else None
        live = R.live_status(day, None, None, {k: lv[k] for k in ("C13", "C14", "C15", "C16", "C17")}, lv["em"],
                             lv["put_node"], lv["call_node"], p["inputs"]["c6"]) if not day.empty else None
        b = X.banner(p, lv, day, 7700.0, mins, gate, live, None, mins >= 510)
        seen.append(b.state)
        assert b.headline and b.credit
        if mins < 9 * 60 + 50:
            assert not any(pl_.status == "armed" for pl_ in b.plays), "nothing may arm before the gate closes"
    assert seen[0] == "PREMARKET" and seen[1] == "LOCKED" and seen[2] == "GATE" and seen[-1] == "SETTLE"


def test_lightweight_chart_html_and_window():
    p = _plan()
    lv = R.rule_levels(p)
    px1, src = U.price_bars("CAPITALCOM:SPX500", "1", 1400, 0)
    assert px1 is not None and len(px1) > 100 and src
    f_dt, t_dt = U.chart_window(SESS)
    assert t_dt > f_dt
    levels = [{"price": lv["C13"], "color": "#3d8bff", "style": 1, "title": "+1.0 wall"}]
    html = LW.build(px1, None, levels, (datetime.combine(SESS, time(2, 0), tzinfo=ET), datetime.combine(SESS, time(14, 0), tzinfo=ET)),
                    [(datetime.combine(SESS, time(9, 30), tzinfo=ET), "09:30")], "dark", True, 540, lv["C15"], lv["C17"] - 8, lv["C13"] + 8, "", 0.7)
    assert "createChart" in html and "rgba(30,144,255,0.7)" in html and "rgba(255,0,255,0.7)" in html


def test_scenario_map_card_credit_and_audit():
    p = _plan()
    g, sg = ws.StandardGrid(**p["grid"]), ws.StrikeGrid(**p["strike_grid"])
    m = SC.scenario_map("THURSDAY", g, sg, p["inputs"]["c7"], p["spy"], p["es"])
    assert m["A"].startswith("A.") and m["B"].startswith("B.") and "/ES" not in SC.scenario_text(m)
    card = SC.TradeCard(SESS.isoformat(), "Watch Day", "—", "—", "—", 250.0, 0, "—", "", "09:10 ET", True)
    assert card.text().startswith("Watch Day.")
    grid = CR.meic_grid(g.c13, g.c17, p["gap"]["c45"], p["gap"]["c46"], False, g.c6, 250.0, None)
    assert grid["fences"]["short_call_min"] >= p["gap"]["c45"] + 5 and grid["fences"]["short_put_max"] <= p["gap"]["c46"] - 5
    spx5, _ = F.get_bars("SPX", "5", 400)
    lv = R.rule_levels(p)
    a = AU.build_audit("THURSDAY", F.session_slice(spx5, SESS), None, None, None, g.c15, g.c6, "08:15",
                       {k: lv[k] for k in ("C13", "C14", "C15", "C16", "C17")}, lv["em"], lv["put_node"], lv["call_node"],
                       sg.put_fence, sg.call_fence, g.c6, [], p.get("stop_clusters"))
    txt = AU.audit_text(a)
    assert "SETTLEMENT AUDIT" in txt and "Rules Replay" in txt and "/ES Against" not in txt


def test_stylesheet_formats_for_both_themes():
    for name in ("dark", "light"):
        css = U.CSS_BASE % U.THEME_VARS[name]
        assert "bannerpulse" in css and "%(" not in css


def test_journal_roundtrip_and_stats():
    df = S.append_journal({"Date": "10/01/2026", "Setup Type": ws.JOURNAL_SETUP_TYPES[1], "PnL ($)": 120, "R-Multiple": 1.5, "1-Trade Rule?": "Yes"})
    stats = S.journal_stats(df)
    assert stats["total_trades"] >= 1 and stats["discipline"] == 100.0


if __name__ == "__main__":
    import shutil
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
    shutil.rmtree(os.environ["AZRAEL_STORE"], ignore_errors=True)
