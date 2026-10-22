"""tests/test_live.py — 1.8.0: the live engine reads only what is final, ARMED means something, alerts fire once, and the
MEIC ticket equals the desk's posted tickets.   Run:  python tests/test_live.py   (also collected by pytest)"""
import os
import sys
from datetime import date, datetime, time, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from core import alerts as AL, execution as X, live as L, meic as MC, rules as R, workstation as ws  # noqa: E402

ET = ZoneInfo("America/New_York")
S = date(2026, 9, 30)
# the Sep 30 desk-audit fixture of tests/test_core.py (A3 long on the 10:50 bar, stopped on the 10:55 close)
ROWS = [("09:30", 7689, 7695, 7686, 7692, 900), ("09:35", 7692, 7702, 7690, 7700, 900), ("09:40", 7700, 7705, 7695, 7703, 900),
        ("09:45", 7703, 7706, 7692, 7705, 900), ("09:50", 7705, 7709.5, 7702, 7708, 900), ("09:55", 7708, 7709, 7704, 7706, 900),
        ("10:00", 7706, 7709.9, 7703, 7708, 900), ("10:05", 7708, 7721.39, 7708, 7714.29, 900), ("10:10", 7714, 7716, 7709, 7711, 900),
        ("10:15", 7711, 7709, 7700, 7702, 900), ("10:20", 7702, 7712, 7701, 7710, 900), ("10:25", 7710, 7716, 7704, 7711, 900),
        ("10:30", 7711, 7715.73, 7702.43, 7712, 900), ("10:35", 7712, 7715, 7705, 7710, 900), ("10:40", 7710, 7714, 7704, 7711, 900),
        ("10:45", 7711, 7713, 7703, 7711, 900), ("10:50", 7711, 7722.88, 7710, 7721.74, 1500), ("10:55", 7721.74, 7722.88, 7712, 7714.75, 1300),
        ("11:00", 7714.75, 7716, 7708, 7712, 900), ("11:05", 7712, 7714, 7706, 7711, 900)]


def _bars(day, rows):
    idx = [datetime.combine(day, time(*map(int, t.split(":"))), tzinfo=ET) for t, *_ in rows]
    return pd.DataFrame([r[1:] for r in rows], columns=["open", "high", "low", "close", "volume"], index=pd.DatetimeIndex(idx))


def _at(day, hhmm, sec=0):
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(day, time(h, m, sec), tzinfo=ET)


def _three(rows):
    spx = _bars(S, rows)
    spy = _bars(S, [(t, o / 10, h / 10, l / 10, c / 10, v) for t, o, h, l, c, v in rows])
    qqq = _bars(S, [(t, o / 10.3, h / 10.3, l / 10.3, c / 10.3, v) for t, o, h, l, c, v in rows])
    return spx, spy, qqq


def _plan(c5, c6, c7=0.0):
    g = ws.standard_grid(c5, c6)
    sg = ws.strike_grid(g.c15, g.c12)
    return {"regime": ws.regime_code(c6), "eligible": ws.eligible_archetypes(c6), "sizing": ws.sizing(ws.max_1r(25000, 1.0), 8.0, 0.55).as_dict(),
            "grid": g.as_dict(), "strike_grid": sg.as_dict(), "gap": ws.gap_engine(c5, c6, g.c13, g.c17, None).as_dict(),
            "inputs": {"c5": c5, "c6": c6, "c7": c7}}


SEP30 = _plan(7670.84, 16.11)
LV = R.rule_levels(SEP30)
GRID = {k: LV[k] for k in ("C13", "C14", "C15", "C16", "C17")}


def _status(spx, spy, qqq):
    return R.live_status(spx, spy, qqq, GRID, LV["em"], LV["put_node"], LV["call_node"], 16.11)


def _upto(rows, last_time):
    return [r for r in rows if r[0] <= last_time]


def test_closed_and_known_drop_the_forming_bar():
    spx = _bars(S, _upto(ROWS, "10:50"))
    asof = _at(S, "10:52", 30)                           # the 10:50 bar is still forming
    c = L.closed(spx, 5, asof)
    k = L.known(spx, 5, asof)
    assert c.index[-1].strftime("%H:%M") == "10:45" and len(k) == len(c) + 1
    stub = k.iloc[-1]
    assert stub["open"] == stub["high"] == stub["low"] == stub["close"] == 7711 and stub["volume"] == 0
    assert len(L.known(spx, 5, _at(S, "10:55"))) == len(spx)          # at 10:55:00 the 10:50 bar is final
    clk = L.bar_clock(_at(S, "10:52", 30))
    assert clk["open"].strftime("%H:%M") == "10:50" and clk["close"].strftime("%H:%M") == "10:55" and clk["secs_left"] == 150


def test_forming_bar_cannot_trigger_a_fakeout():
    """10:52:30 — the forming 10:50 bar is 7 pts through the box, then fails: the old live path went ACTIVE on it."""
    rows = _upto(ROWS, "10:45") + [("10:50", 7711, 7722.88, 7710, 7721.74, 1500)]
    spx, spy, qqq = _three(rows)
    old = _status(spx, spy, qqq)
    assert old["chosen"] is not None and old["chosen"].trigger_time == "10:50"          # what 1.7.2 did live (premature)
    asof = _at(S, "10:52", 30)
    new = _status(L.known(spx, 5, asof), L.known(spy, 5, asof), L.known(qqq, 5, asof))
    assert new["chosen"] is None                                                      # nothing until the close
    # the bar closes back inside: no trigger ever existed
    fake = _upto(ROWS, "10:45") + [("10:50", 7711, 7722.88, 7710, 7712.5, 1500)]
    f_spx, f_spy, f_qqq = _three(fake)
    assert _status(f_spx, f_spy, f_qqq)["chosen"] is None


def test_engine_identical_once_the_bar_closed():
    spx, spy, qqq = _three(ROWS)
    full = _status(spx, spy, qqq)["chosen"]
    asof = _at(S, "16:05")
    live = _status(L.known(spx, 5, asof), L.known(spy, 5, asof), L.known(qqq, 5, asof))["chosen"]
    for f in ("archetype", "side", "trigger_time", "entry", "stop", "target", "risk_pts", "resolution", "exit_time", "exit_price", "r_multiple"):
        assert getattr(full, f) == getattr(live, f), f
    assert full.trigger_time == "10:50" and full.entry == 7721.74 and full.resolution == "stopped" and full.r_multiple == -1.16
    # at 10:55:30 the trigger bar has closed: ACTIVE with the audit's numbers, the exit not yet known
    a = _at(S, "10:55", 30)
    rows = _upto(ROWS, "10:55")
    s2, y2, q2 = _three(rows)
    ch = _status(L.known(s2, 5, a), L.known(y2, 5, a), L.known(q2, 5, a))["chosen"]
    assert ch.trigger_time == "10:50" and ch.entry == 7721.74 and ch.resolution == "open"


def test_forming_bar_cannot_stop_a_trade():
    """10:57 — the forming 10:55 bar trades below the 7715.73 stop; the stop is a 5-minute CLOSE, so the trade stays open."""
    rows = _upto(ROWS, "10:50") + [("10:55", 7721.74, 7722.88, 7712, 7714.0, 900)]
    spx, spy, qqq = _three(rows)
    assert _status(spx, spy, qqq)["chosen"].resolution == "stopped"                 # 1.7.2 live: DONE before the close
    a = _at(S, "10:57")
    ch = _status(L.known(spx, 5, a), L.known(spy, 5, a), L.known(qqq, 5, a))["chosen"]
    assert ch.resolution == "open"


def test_s4_enters_on_the_open_of_the_forming_bar():
    """S4 enters 'on the open of the second candle following acceptance': the open is final the moment that bar starts."""
    p = _plan(7690.73, 18.89)                                                         # Negative Gamma, Oct 20 map
    lv = R.rule_levels(p)
    grid = {k: lv[k] for k in ("C13", "C14", "C15", "C16", "C17")}
    sh = lv["C14"]
    rows = [("09:30", 7700, 7708, 7698, 7705, 1000), ("09:35", 7705, 7712, 7703, 7710, 900), ("09:40", 7710, 7716, 7707, 7714, 900),
            ("09:45", 7714, 7720, 7712, 7718, 900), ("09:50", 7718, 7725, 7716, 7722, 900), ("09:55", 7722, 7730, 7720, 7728, 900),
            ("10:00", 7728, 7742, 7727, round(sh + 3, 2), 2500), ("10:05", round(sh + 3, 2), 7745, 7737, round(sh + 6, 2), 1200),
            ("10:10", round(sh + 6, 2), 7746, 7738, round(sh + 5, 2), 1100), ("10:15", round(sh + 5.5, 2), round(sh + 9, 2), round(sh + 4, 2), round(sh + 8, 2), 900)]
    full = _bars(date(2026, 10, 20), rows)
    done = R.replay_a4(full, lv["C13"], lv["C14"], lv["C16"], lv["C17"])
    assert done.qualified and done.trigger_time == "10:15" and done.entry == round(sh + 5.5, 2)
    a = datetime.combine(date(2026, 10, 20), time(10, 15, 20), tzinfo=ET)               # 20 s into the entry bar
    live = R.replay_a4(L.known(full, 5, a), lv["C13"], lv["C14"], lv["C16"], lv["C17"])
    assert live.qualified and live.trigger_time == "10:15" and live.entry == done.entry and live.resolution == "open"
    assert R.live_status(L.known(full, 5, a), None, None, grid, lv["em"], lv["put_node"], lv["call_node"], 18.89)["chosen"].archetype == 4


def test_s3_armed_means_outside_the_box():
    p = _plan(7712.57, 17.34)                                                         # Oct 21 map, Balanced
    lv = R.rule_levels(p)
    rows = [("10:25", 7716, 7729.95, 7714.27, 7722, 900), ("10:30", 7722, 7728, 7716, 7725, 900), ("10:35", 7725, 7729, 7718, 7720, 900),
            ("10:40", 7720, 7727, 7715, 7724, 900)]
    d = date(2026, 10, 21)
    bars = _bars(d, rows)
    em = lv["em"]
    for last, st, key in ((7724.0, "watch", "A3"), (7731.0, "armed", "A3-long"), (7712.0, "armed", "A3-short")):
        plays = X.plays_for(p, lv, bars, last, p["sizing"], closed_bars=bars)
        a3 = next(q for q in plays if q.archetype == 3)
        assert a3.status == st and a3.key == key, (last, a3.status, a3.key)
    a3 = next(q for q in X.plays_for(p, lv, bars, 7731.0, p["sizing"], closed_bars=bars) if q.archetype == 3)
    assert abs(a3.trigger_px - (7729.95 + 0.05 * em)) < 1e-9 and a3.stop_px == 7729.95 and a3.target_px == lv["C14"] and a3.ready
    assert a3.box["start"] == "10:25" and a3.box["end"] == "10:40"
    # before 09:50 nothing arms, whatever the distance
    b = X.banner(p, lv, bars, 7731.0, 9 * 60 + 40, None, None, None, True, closed_bars=bars)
    assert b.state == "GATE" and not any(q.status == "armed" for q in b.plays)
    b = X.banner(p, lv, bars, 7731.0, 10 * 60 + 47, None, None, None, True, closed_bars=bars)
    assert b.state == "ARMED" and "3-ticker" in b.headline


def test_meic_ticket_equals_the_desk_tickets():
    # (prior close, VIX 08:15) -> desk ticket (short put, short call), Oct 16 / 19 / 20 / 21 2026
    for c5, c6, sp, sc, reg in ((7744.06, 16.05, 7645, 7840, 2), (7659.44, 18.59, 7545, 7770, 3), (7690.73, 18.89, 7575, 7805, 3),
                                (7712.57, 17.34, 7605, 7820, 2)):
        t = MC.ticket(_plan(c5, c6))
        assert (t["short_put"], t["short_call"]) == (sp, sc), (c5, c6, t["short_put"], t["short_call"])
        assert (t["long_put"], t["long_call"]) == (sp - 10, sc + 10) and (t["put_trigger"], t["call_trigger"]) == (sp + 5, sc - 5)
        assert t["regime"] == reg
    t = MC.ticket(_plan(7712.57, 17.34))
    assert t["mandate"] == "SINGLE-SIDED SPREADS OR POST-11:30 RANGE CONDOR (0.75R Size, 1DTE preferred)" and t["expiry_index"] == 1
    assert MC.ticket(_plan(7690.73, 18.89))["mandate"] == "IRON CONDORS BANNED (Negative Gamma). Wide 15-20pt single-sided spreads only."
    d = MC.defense_status(7816.0, t)
    assert d["call"]["hit"] and not d["put"]["hit"] and round(d["put"]["dist"], 2) == 206.0


def test_range_condor_check_follows_the_desk_text():
    p = _plan(7712.57, 17.34)
    t = MC.ticket(p)
    em = p["grid"]["c12"]
    d = date(2026, 10, 21)
    rot = [("09:30", 7712, 7720, 7705, 7716, 0), ("09:35", 7716, 7722, 7710, 7718, 0), ("09:40", 7718, 7724, 7712, 7714, 0),
           ("09:45", 7714, 7718, 7700, 7704, 0), ("09:50", 7704, 7716, 7700, 7715, 0), ("09:55", 7715, 7722, 7708, 7708, 0),
           ("10:00", 7708, 7720, 7704, 7718, 0), ("10:05", 7718, 7722, 7702, 7706, 0)]
    ok = MC.range_condor_check(_bars(d, rot), t, em, 7712.57, 11 * 60 + 31)
    assert ok["verdict"] == "CONFIRMED", ok
    bad = MC.range_condor_check(_bars(d, rot + [("10:10", 7706, 7760, 7705, 7758, 0)]), t, em, 7712.57, 10 * 60 + 20)
    assert bad["verdict"] == "FAILED" and not bad["checks"][0]["ok"]


def test_alerts_fire_once_and_skip_stale_facts():
    d = date(2026, 10, 21)
    trade = {"archetype": 3, "side": "long", "trigger_time": "10:45", "entry": 7735.54, "stop": 7729.95, "target": 7754.69,
             "risk_pts": 5.59, "resolution": "open"}
    now = _at(d, "10:50", 40)
    f = AL.desk_events(d, now, "ACTIVE", trade, [], 7737.0)
    fire, seen, armed = AL.select(f, {}, [], now, first_run=False)
    assert [e.kind for e in fire] == ["gate", "trigger"]
    fire, seen, armed = AL.select(AL.desk_events(d, now + timedelta(minutes=1), "ACTIVE", trade, [], 7738.0), seen, armed,
                                  now + timedelta(minutes=1), first_run=False)
    assert fire == []                                                                     # nothing new: no repeat
    # opening the page at 11:10: the 10:50 trigger is stale -> remembered silently; the live target touch still fires
    late = _at(d, "11:10")
    fire, seen2, _ = AL.select(AL.desk_events(d, late, "ACTIVE", trade, [], 7755.0), {}, [], late, first_run=True)
    assert [e.kind for e in fire] == ["touch"] and any("|trigger|" in k for k in seen2)
    done = dict(trade, resolution="target", exit_time="11:10", exit_price=7754.69, r_multiple=3.43)
    fire, _, _ = AL.select(AL.desk_events(d, _at(d, "11:15", 20), "DONE", done, [], 7756.0), seen2, [], _at(d, "11:15", 20), first_run=False)
    assert [e.kind for e in fire] == ["exit"] and not fire[0].major                    # already announced by TARGET TOUCHED


def test_armed_alert_transition_and_cooldown():
    d = date(2026, 10, 21)
    p = X.Play(3, "LONG CALLS", "t", "c", "e", "s", "g", "armed", "x", 1.2, key="A3-long", trigger_px=7733.5, trigger_rule="close ≥ 7733.5")
    t0 = _at(d, "10:46")
    fire, seen, armed = AL.select(AL.desk_events(d, t0, "ARMED", None, [p], 7731.0), {}, [], t0, first_run=False)
    assert [e.kind for e in fire] == ["gate", "armed"]
    t1 = t0 + timedelta(minutes=1)                                                        # still armed: silent
    fire, seen, armed = AL.select(AL.desk_events(d, t1, "ARMED", None, [p], 7731.5), seen, armed, t1, first_run=False)
    assert fire == []
    t2 = t1 + timedelta(minutes=1)                                                        # flaps out ...
    fire, seen, armed = AL.select(AL.desk_events(d, t2, "WATCHING", None, [], 7726.0), seen, armed, t2, first_run=False)
    t3 = t2 + timedelta(minutes=1)                                                        # ... and back in: cooldown holds
    fire, seen, armed = AL.select(AL.desk_events(d, t3, "ARMED", None, [p], 7731.0), seen, armed, t3, first_run=False)
    assert fire == []
    t4 = t0 + timedelta(minutes=16)                                                       # after 15 min it may alert again
    fire, seen, armed = AL.select(AL.desk_events(d, t4, "WATCHING", None, [], 7726.0), seen, armed, t4, first_run=False)
    fire, seen, armed = AL.select(AL.desk_events(d, t4 + timedelta(minutes=1), "ARMED", None, [p], 7731.0), seen, armed,
                                  t4 + timedelta(minutes=1), first_run=False)
    assert [e.kind for e in fire] == ["armed"]
    p.ready = False                                                                       # S2 without its 15-pt displacement: no alert
    assert not [e for e in AL.desk_events(d, t4, "ARMED", None, [p], 7731.0) if e.kind == "armed"]


def test_meic_defense_and_regime_flip_events():
    d = date(2026, 10, 21)
    t = MC.ticket(_plan(7712.57, 17.34))
    now = _at(d, "13:20")
    ev = AL.meic_events(d, now, t, 7816.0, 18.62, 17.34)
    kinds = sorted((e.kind, e.key.split("|")[2]) for e in ev)
    assert kinds == [("defense", "call"), ("flip", "flip")] and all(e.major for e in ev)
    assert AL.meic_events(d, _at(d, "09:45"), t, 7816.0, 18.62, 17.34) == []          # the ticket starts at 09:50
    assert AL.meic_events(d, now, t, 7760.0, 17.9, 17.34) == []


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
