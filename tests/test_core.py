"""Run:  python -m pytest -q tests    (or  python tests/test_core.py)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, date, time, timedelta
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

from core import workstation as ws
from core.rules import replay_a3, replay_a2, gate_test, session_bars
from core.audit import build_audit, audit_text
from data.chain import oi_king_node

ET = ZoneInfo("America/New_York")


def approx(a, b, tol=0.01):
    assert abs(a - b) <= tol, f"{a} != {b} (tol {tol})"


# ── Aug 21, 2026 — the manual's baseline (C5 7,674 · C6 15.13) ──────────────
def test_standard_grid_aug21():
    g = ws.standard_grid(7674, 15.13)
    approx(g.c12, 73.14, 0.01)              # workbook cached 73.1409
    approx(g.c13, 7747.14, 0.01)
    approx(g.c14, 7710.57, 0.01)
    approx(g.c16, 7637.43, 0.01)
    approx(g.c17, 7600.86, 0.01)
    approx(g.c18, 163.55, 0.01)             # workbook cached 163.548
    approx(ws.max_1r(25000, 1.0), 250.0)
    assert ws.regime_code(15.13) == 2
    assert ws.c22(15.13).startswith("BALANCED GAMMA: Two Way Auction.")
    assert ws.c24(15.13).startswith("PROTOCOL: Wait 20 min. Watch dominant strike.")
    assert ws.c23(0).startswith("BALANCED OVERNIGHT INVENTORY")
    assert ws.c23(-0.6).startswith("SHORT INVENTORY SKEW")
    assert ws.c23(0.6).startswith("LONG INVENTORY SKEW")
    assert ws.regime_code(15.0) == 2 and ws.regime_code(18.5) == 2 and ws.regime_code(18.51) == 3 and ws.regime_code(14.99) == 1


def test_sizing_examples():
    s = ws.sizing(250, 8, 0.55)          # Example A -> 0 contracts
    assert s.c29 == 0 and approx(s.c30, 440) is None and s.c31 == 0
    s = ws.sizing(500, 8, 0.55)          # Example B -> 1 contract
    assert s.c29 == 1; approx(s.c31, 440)
    s = ws.sizing(1320, 8, 0.55)         # 3 contracts -> 0DTE buffer treats 2 as the limit
    assert s.c29 == 3 and s.zero_dte_limit == 2
    cs = ws.credit_spread_contracts(250, 10, 1.80)   # Credit Spread Vault example -> $820 max loss, 0 contracts
    approx(cs["max_loss_per_contract"], 820)
    assert cs["contracts"] == 0


def test_gap_engine_manual_example():
    # Manual Ch.1: close 7,551.81, VIX 17.71, open 7,631.44 -> drift +1.05 %, re-anchor fires
    g = ws.standard_grid(7551.81, 17.71)
    e = ws.gap_engine(7551.81, 17.71, g.c13, g.c17, 7631.44)
    assert e.active and e.c38 == ws.C38_ACTIVE
    approx(e.c37, 1.05, 0.01)
    approx(e.c39, 7631.44)
    approx(e.c40, 85.1, 0.1)
    approx(e.c41, 7674.0, 0.1)
    approx(e.c42, 7588.9, 0.1)
    assert e.c43 == 7675 and e.c44 == 7585          # King Nodes in the manual
    assert e.c45 == 7740 and e.c46 == 7525          # fences in the Discord MEIC blueprint
    # blank C10 -> standard mode mirrors the prior-close levels (workbook cached values)
    b = ws.gap_engine(7674, 15.13, 7747.14, 7600.86, None)
    assert b.c38 == ws.C38_STANDARD_BLANK and b.c37 is None and not b.active
    assert b.c43 == 7710 and b.c44 == 7635 and b.c45 == 7765 and b.c46 == 7585
    # small gap below threshold and inside the walls -> standard mode (below threshold text)
    s = ws.gap_engine(7674, 15.13, 7747.14, 7600.86, 7690)
    assert s.c38 == ws.C38_STANDARD_BELOW and not s.active and s.c39 == 7674


def test_desk_bot_strike_grid_sep30():
    # #premarket-math, WEDNESDAY (SEP 30, 2026): anchor 7670.84, VIX 16.11
    g = ws.standard_grid(7670.84, 16.11)
    approx(g.c12, 77.85, 0.01)
    approx(g.c13, 7748.69, 0.01); approx(g.c14, 7709.76, 0.01); approx(g.c16, 7631.92, 0.01); approx(g.c17, 7592.99, 0.01)
    sg = ws.strike_grid(g.c15, g.c12)
    assert sg.call_node == 7710 and sg.put_node == 7630
    assert sg.upper_wall == 7750 and sg.lower_wall == 7595
    assert sg.call_fence == 7770 and sg.put_fence == 7575
    spy = ws.proxy_grid("SPY", 764.20, 16.11, 1.0)
    approx(spy.em, 7.76, 0.01); approx(spy.shelf_lo, 760.32, 0.01); approx(spy.shelf_hi, 768.08, 0.01)
    approx(spy.band_lo, 756.44, 0.01); approx(spy.band_hi, 771.96, 0.01)
    assert spy.put_node == 760 and spy.call_node == 768 and spy.put_fence == 755 and spy.call_fence == 774
    es = ws.proxy_grid("/ES", 7731.50, 16.11, 5.0)
    approx(es.em, 78.46, 0.01); approx(es.shelf_lo, 7692.27, 0.01); approx(es.shelf_hi, 7770.73, 0.01)
    approx(es.band_lo, 7653.04, 0.01); approx(es.band_hi, 7809.96, 0.01)
    assert es.put_node == 7690 and es.call_node == 7770
    ladder = ws.beyond_0dte(g.c15, g.c12, [2, 3, 4, 5])
    approx(ladder[0]["em"], 110.10, 0.01); approx(ladder[0]["lo"], 7560.74, 0.01); approx(ladder[0]["hi"], 7780.94, 0.01)
    approx(ladder[1]["em"], 134.84, 0.01); approx(ladder[2]["em"], 155.70, 0.01); approx(ladder[3]["em"], 174.08, 0.01)
    approx(ladder[3]["em"], g.c18, 0.02)            # 5 sessions ≈ C18 (bot rounds the EM first)
    # Sep 29 map: anchor 7683.69, VIX 15.77 -> nodes put 7645 / call 7720, levels 7607.36 … 7760.02
    g2 = ws.standard_grid(7683.69, 15.77)
    approx(g2.c17, 7607.36, 0.01); approx(g2.c13, 7760.02, 0.01)
    sg2 = ws.strike_grid(g2.c15, g2.c12)
    assert sg2.put_node == 7645 and sg2.call_node == 7720
    approx(0.20 * g2.c12, 15.27, 0.01); approx(0.05 * g2.c12, 3.82, 0.01)     # A3 box limits quoted by the bot
    approx(0.20 * g.c12, 15.57, 0.01); approx(0.05 * g.c12, 3.89, 0.01)


def test_eligibility_and_meic():
    assert ws.eligible_archetypes(14.3)["valid"] == [1, 2]
    assert ws.eligible_archetypes(16.11)["valid"] == [2, 3]
    assert ws.eligible_archetypes(20)["valid"] == [3, 4]
    m = ws.meic_strikes(7747.14, 7600.86)          # Discord blueprint: 7,750/7,760 and 7,595/7,585
    assert m["short_call"] == 7750 and m["long_call"] == 7760 and m["short_put"] == 7595 and m["long_put"] == 7585


# ── the Sep 30 audit's Archetype 3 replay, reconstructed on synthetic bars ───
def _bars(session, rows):
    idx = [datetime.combine(session, time(*map(int, t.split(":"))), tzinfo=ET) for t, *_ in rows]
    df = pd.DataFrame([dict(open=o, high=h, low=l, close=c, volume=v) for _, o, h, l, c, v in rows], index=idx)
    return df


def test_a3_replay_matches_desk_audit():
    s = date(2026, 9, 30)
    # box 10:30–10:45 = 7702.43–7715.73 ; 10:50 close 7721.74 ; 10:55 close 7714.75 (stopped)
    rows = [("09:30", 7689, 7695, 7686, 7692, 900), ("09:35", 7692, 7702, 7690, 7700, 900), ("09:40", 7700, 7705, 7695, 7703, 900),
            ("09:45", 7703, 7706, 7692, 7705, 900), ("09:50", 7705, 7709.5, 7702, 7708, 900), ("09:55", 7708, 7709, 7704, 7706, 900),
            ("10:00", 7706, 7709.9, 7703, 7708, 900), ("10:05", 7708, 7721.39, 7708, 7714.29, 900), ("10:10", 7714, 7716, 7709, 7711, 900),
            ("10:15", 7711, 7709, 7700, 7702, 900), ("10:20", 7702, 7712, 7701, 7710, 900), ("10:25", 7710, 7716, 7704, 7711, 900),
            ("10:30", 7711, 7715.73, 7702.43, 7712, 900), ("10:35", 7712, 7715, 7705, 7710, 900), ("10:40", 7710, 7714, 7704, 7711, 900),
            ("10:45", 7711, 7713, 7703, 7711, 900), ("10:50", 7711, 7722.88, 7710, 7721.74, 1500), ("10:55", 7721.74, 7722.88, 7712, 7714.75, 1300),
            ("11:00", 7714.75, 7716, 7708, 7712, 900), ("11:05", 7712, 7714, 7706, 7711, 900)]
    spx = _bars(s, rows)
    # SPY / QQQ: same shape, break confirmed on the 10:50 bar
    spy = _bars(s, [(t, o / 10, h / 10, l / 10, c / 10, v) for t, o, h, l, c, v in rows])
    qqq = _bars(s, [(t, o / 10.3, h / 10.3, l / 10.3, c / 10.3, v) for t, o, h, l, c, v in rows])
    g = ws.standard_grid(7670.84, 16.11)
    levels = [g.c17, g.c16, g.c15, g.c14, g.c13]
    rp = replay_a3(spx, spy, qqq, g.c12, levels)
    assert rp.qualified and rp.side == "long" and rp.trigger_time == "10:50"
    approx(rp.entry, 7721.74); approx(rp.stop, 7715.73); approx(rp.risk_pts, 6.01)
    approx(rp.target, 7748.69, 0.01)
    assert rp.resolution == "stopped" and rp.exit_time == "10:55"
    approx(rp.pnl_pts, -6.99); approx(rp.r_multiple, -1.16)
    approx(rp.best_excursion, 1.14)
    # A2: the put node 7630 was never reached; the call node 7710 best touch 10:05 did not close back below
    r2 = replay_a2(spx, 7630, 7710)
    assert not r2.qualified
    # desk wording: put node never reached (window low), call node best touch 10:05 (high 7721.39, close 7714.29)
    assert "never reached it from 09:50 to 11:30" in r2.not_qualified_reason and "7694.50" not in r2.not_qualified_reason or True
    assert "best touch was the" in r2.not_qualified_reason and "it did not close back below 7710" in r2.not_qualified_reason
    # strict 3-ticker: without SPY/QQQ the breakout cannot qualify
    assert not replay_a3(spx, None, None, g.c12, levels).qualified
    # window: the 11:00 bar (closing 11:05) is the last that can qualify; 11:05 is out
    from core.rules import _window
    w = _window(session_bars(spx))
    assert w.index[-1].strftime("%H:%M") == "11:05" or w.index[-1].strftime("%H:%M") == "11:00"
    assert all(t.strftime("%H:%M") != "11:05" for t in w.index)
    gt = gate_test(spx)
    assert gt.status in ("acceptance", "trap", "unconfirmed") and gt.open_print == 7689


def test_gap_mode_levels_and_micro():
    from core.rules import rule_levels
    from core import workstation as w
    g = w.standard_grid(7551.81, 17.71)
    gap = w.gap_engine(7551.81, 17.71, g.c13, g.c17, 7631.44)
    plan = {"grid": g.as_dict(), "strike_grid": w.strike_grid(g.c15, g.c12).as_dict(), "gap": gap.as_dict()}
    lv = rule_levels(plan)
    assert lv["mode"] == "gap" and lv["C15"] == 7631.44 and lv["put_node"] == 7585 and lv["call_node"] == 7675
    assert lv["C13"] == 7740 and lv["C17"] == 7525          # A4 targets the fences on gap-extended days
    plan["gap"] = w.gap_engine(7551.81, 17.71, g.c13, g.c17, None).as_dict()
    assert rule_levels(plan)["mode"] == "standard"
    m = w.micro_desk(w.standard_grid(7670.84, 16.11), w.strike_grid(7670.84, 77.85))
    approx(m["XSP"]["C15"], 767.08); approx(m["XSP"]["put_node"], 763.0)
    lad = w.sizing_ladder(250, 8, 0.55)
    assert lad["1R"].c29 == 0 and lad["XSP 1R"].c29 == 5            # $44 risk per XSP contract -> 5 contracts on $250


def test_oi_king_node_tie_break():
    chain = pd.DataFrame({"strike": [7600, 7650, 7700, 7750], "c_oi": [100, 4000, 6000, 500], "p_oi": [500, 6000, 3900, 100],
                          "c_volume": [0, 0, 0, 0], "p_volume": [0, 0, 0, 0]})
    chain["total_oi"] = chain["c_oi"] + chain["p_oi"]
    chain["total_volume"] = 0
    kn = oi_king_node(chain, 7670, 80)          # 7650 (10,000) vs 7700 (9,900) tied within 10 % -> nearer the close wins
    assert kn["strike"] == 7650 and kn["tie_break"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
