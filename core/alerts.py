"""
alerts.py — which desk facts deserve an alert, as pure functions (no Streamlit, no browser).

Facts are produced from the live snapshot every poll; `select()` turns the facts that are NEW into alerts. Keys are unique
per occurrence (session · kind · setup · bar), so an alert fires once however many polls, pages or reruns see it.

Weights (the book trade drives the alerts; the Scenario Book score only annotates):
    TRADE TRIGGERED / EXIT / TARGET TOUCHED / MEIC DEFENSE / REGIME FLIP   major: tone + notification + card that stays
    ARMED / STOP AT RISK                                                   heads-up: soft tone + card (no notification)
    09:50 GATE                                                             info: soft tone + notification
    STAND DOWN / IDEA SENT · DROPPED                                       quiet: card only
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import date, datetime, time, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from utils.timeutil import ET, T_GATE_END, T_LAST_QUALIFYING, T_CLOSE, minutes_of

SETUP = {1: "S1 SHELF FADE", 2: "S2 NODE ABSORPTION", 3: "S3 THREE-TICKER BREAK", 4: "S4 SHELF BREAK RUNNER"}
INSTR = {"long": "LONG CALLS", "short": "LONG PUTS"}
GREEN, RED, AMBER, BLUE, GREY, VIOLET = "#10b981", "#ef4444", "#f59e0b", "#38bdf8", "#94a3b8", "#a78bfa"
ARMED_COOLDOWN_S = 15 * 60


@dataclass
class Event:
    key: str
    kind: str                 # gate | armed | trigger | touch | stoprisk | exit | standdown | score | defense | flip
    tone: str                 # trigger | exit | armed | info | defense | none
    major: bool
    pill: str
    title: str
    body: str
    at: datetime              # when the fact happened (ET) — used to skip stale facts when a page first opens
    accent: str = BLUE
    notify: bool = False
    extra: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        d = asdict(self)
        d["at"] = self.at.isoformat()
        return d


def _at(sess: date, hhmm: str, plus_min: int = 0) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(sess, time(h, m), tzinfo=ET) + timedelta(minutes=plus_min)


def desk_events(sess: date, now: datetime, state: str, trade: Optional[Dict], plays: Iterable, last: Optional[float],
                gate=None, score: Optional[Dict] = None, ticket: Optional[Dict] = None, bar: Optional[Dict] = None) -> List[Event]:
    """Facts that are true now on the directional desk."""
    m = minutes_of(now)
    out: List[Event] = []
    if m >= T_GATE_END:
        verdict = ""
        if gate is not None and getattr(gate, "status", "") in ("acceptance", "trap", "unconfirmed"):
            verdict = f" · 09:50 test: {gate.status.upper()}" + (f" {'UP' if gate.direction > 0 else 'DOWN'}" if gate.status != "unconfirmed" else "")
        meic = (f" · MEIC: SELL {ticket['short_call']:,.0f}C / BUY {ticket['long_call']:,.0f}C · SELL {ticket['short_put']:,.0f}P / "
                f"BUY {ticket['long_put']:,.0f}P") if ticket else ""
        out.append(Event(f"{sess}|gate", "gate", "info", False, "09:50 DISCOVERY GATE", "EXECUTION WINDOW OPEN",
                         f"One setup, qualifying closes until 11:05, flat by 11:30{verdict}{meic}", _at(sess, "09:50"), BLUE, True))
    if trade:
        a, tt, side = int(trade["archetype"]), str(trade["trigger_time"]), trade["side"]
        entry, stop, tgt, risk = float(trade["entry"]), float(trade["stop"]), float(trade["target"]), float(trade["risk_pts"] or 0)
        rr = abs(tgt - entry) / risk if risk else 0.0
        t_at = _at(sess, tt, 0 if a == 4 else 5)
        where = f"open of the {tt} bar" if a == 4 else f"{tt} bar close"
        out.append(Event(f"{sess}|trigger|A{a}|{tt}", "trigger", "trigger", True, f"TRADE TRIGGERED · {t_at:%H:%M}",
                         f"{SETUP[a]} — {INSTR[side]}",
                         f"In {entry:,.2f} ({where}) · stop {stop:,.2f} on a 5-min close · target {tgt:,.2f} = {rr:.2f}R · 1R {risk:.2f} pts · flat by 11:30",
                         t_at, GREEN, True, {"archetype": a, "side": side}))
        res = trade.get("resolution")
        if state == "ACTIVE" and last is not None:
            long = side == "long"
            if (long and last >= tgt) or ((not long) and last <= tgt):
                out.append(Event(f"{sess}|touch|A{a}|{tt}", "touch", "exit", True, "TARGET TOUCHED", f"TAKE 100% OUT — {tgt:,.2f}",
                                 f"Live price {last:,.2f} reached the {tgt:,.2f} target (+{rr:.2f}R). The book exits on first touch.",
                                 now, GREEN, True))
            elif (long and last <= stop) or ((not long) and last >= stop):
                lbl = bar["label"] if bar else "the forming 5-minute bar"
                bkey = bar["open"].strftime("%H%M") if bar else now.strftime("%H%M")
                out.append(Event(f"{sess}|stoprisk|A{a}|{tt}|{bkey}", "stoprisk", "armed", False, "STOP AT RISK",
                                 "THE 5-MINUTE CLOSE DECIDES",
                                 f"Live {last:,.2f} is {'below' if long else 'above'} the {stop:,.2f} stop · {lbl} — a close there is the exit. Not a wick: wait for the close.",
                                 now, AMBER, False))
        if res in ("target", "stopped") or str(res).startswith("flat"):
            et = trade.get("exit_time") or tt
            px = trade.get("exit_price")
            r = trade.get("r_multiple")
            name = "TARGET" if res == "target" else "STOPPED" if res == "stopped" else "FLAT 11:30"
            col = GREEN if res == "target" else RED if res == "stopped" else GREY
            out.append(Event(f"{sess}|exit|A{a}|{tt}|{name}", "exit", "exit", True, f"SETUP RESOLVED · {_at(sess, et, 5):%H:%M}",
                             f"{name} {r:+.2f}R — {SETUP[a]}" if r is not None else f"{name} — {SETUP[a]}",
                             (f"Exit {px:,.2f} on the {et} bar" if px is not None else f"the {et} bar")
                             + " · one setup per day — the desk is closed for you. Log the journal row at 16:15.",
                             _at(sess, et, 5), col, True, {"resolution": res}))
    elif state == "STAND_DOWN":
        out.append(Event(f"{sess}|standdown", "standdown", "none", False, "11:05 · STAND DOWN", "WATCH DAY",
                         "No qualifying 5-minute close by 11:05. Capital intact, discipline intact. Flat by 11:30.",
                         _at(sess, "11:05"), GREY, False))
    if not trade and T_GATE_END <= m < T_LAST_QUALIFYING:
        for p in plays or []:
            if getattr(p, "status", "") != "armed" or not getattr(p, "ready", True):
                continue
            side = "LONG" if "CALLS" in p.side and "PUTS" not in p.side else "SHORT" if "PUTS" in p.side and "CALLS" not in p.side else ""
            dist = p.distance
            dtxt = ""
            if dist is not None:
                dtxt = (f" · {dist:.2f} pts to go" if dist > 0 else f" · {abs(dist):.2f} pts through — the close decides")
            when = f" · {bar['label']}" if bar else ""
            out.append(Event(f"{sess}|armed|{p.key or ('A' + str(p.archetype))}", "armed", "armed", False, f"⚡ ARMED · {now:%H:%M}",
                             f"{SETUP.get(p.archetype, 'SETUP')}{(' — ' + side) if side else ''}",
                             f"{p.trigger_rule or p.condition}{dtxt}{when}", now, AMBER, False,
                             {"play": p.key, "trigger": p.trigger_px}))
    if score and trade and score.get("status") in ("SENT", "DROPPED", "EXPIRED", "CUTOFF", "NOT_SENT"):
        stt = score["status"]
        lab = {"SENT": "IDEA SENT", "DROPPED": "IDEA DROPPED", "EXPIRED": "IDEA DROPPED", "CUTOFF": "IDEA CUT-OFF", "NOT_SENT": "IDEA NOT SENT"}[stt]
        at = _at(sess, score["sent_time"]) if (stt == "SENT" and score.get("sent_time")) else now
        out.append(Event(f"{sess}|score|{trade['trigger_time']}|{stt}", "score", "none", False, "SCENARIO BOOK SCORE",
                         f"{lab} — SCORE {score['score']:.1f}", score.get("status_text", ""), at, VIOLET, False))
    return out


def meic_events(sess: date, now: datetime, t: Optional[Dict], spot: Optional[float], vix_now: Optional[float],
                c6: Optional[float]) -> List[Event]:
    """5-Point Defense Law and the intraday regime flip, live from 09:50 to the close."""
    m = minutes_of(now)
    if t is None or m < T_GATE_END or m >= T_CLOSE:
        return []
    out: List[Event] = []
    if spot is not None:
        if spot >= t["call_trigger"]:
            rc = t["roll_call"]
            out.append(Event(f"{sess}|meic|call|{t['short_call']:.0f}", "defense", "defense", True, "MEIC 5-PT DEFENSE",
                             f"{t['short_call']:,.0f}C WING TESTED",
                             f"SPX {spot:,.2f} is within 5 pts of the {t['short_call']:,.0f}C short (trigger {t['call_trigger']:,.0f}). "
                             f"Roll out 1 day and 5 pts wider ({rc[0]:,.0f}/{rc[1]:,.0f}C) for a credit or scratch — or exit now.",
                             now, RED, True))
        if spot <= t["put_trigger"]:
            rp = t["roll_put"]
            out.append(Event(f"{sess}|meic|put|{t['short_put']:.0f}", "defense", "defense", True, "MEIC 5-PT DEFENSE",
                             f"{t['short_put']:,.0f}P WING TESTED",
                             f"SPX {spot:,.2f} is within 5 pts of the {t['short_put']:,.0f}P short (trigger {t['put_trigger']:,.0f}). "
                             f"Roll out 1 day and 5 pts wider ({rp[0]:,.0f}/{rp[1]:,.0f}P) for a credit or scratch — or exit now.",
                             now, RED, True))
    if vix_now is not None and c6 is not None and c6 <= 18.5 < vix_now:
        out.append(Event(f"{sess}|meic|flip", "flip", "defense", True, "REGIME FLIP", "CLOSE THE CONDOR AT MARKET",
                         f"VIX {vix_now:.2f} is above 18.5 (08:15 print {c6:.2f}): Negative Gamma. The volatility-dampening premise "
                         f"has evaporated — close the entire Iron Condor; do not hold through a regime flip.", now, RED, True))
    return out


def select(facts: List[Event], seen: Dict[str, float], armed_prev: Iterable[str], now: datetime, first_run: bool,
           fresh_s: int = 300) -> Tuple[List[Event], Dict[str, float], List[str]]:
    """New facts -> alerts. Returns (alerts, seen', armed_now).
    • A fact fires once per key. On the first evaluation of a browser session, facts older than `fresh_s` are recorded
      silently (opening the app at 11:10 must not replay the 10:50 trigger), facts about 'now' still fire.
    • ARMED fires on the transition into armed, then at most every 15 minutes per play (no flapping)."""
    ts = now.timestamp()
    seen = dict(seen)
    prev = set(armed_prev)
    armed_now: List[str] = []
    fire: List[Event] = []
    for e in facts:
        if e.kind == "armed":
            armed_now.append(e.key)
            if e.key in prev:
                continue                                   # still armed since the last poll: nothing new
            last_fire = seen.get(e.key)
            if last_fire is not None and ts - last_fire < ARMED_COOLDOWN_S:
                continue
            seen[e.key] = ts
            e.key = f"{e.key}|{now:%H%M}"
            fire.append(e)
            continue
        if e.key in seen:
            continue
        seen[e.key] = ts
        if first_run and (ts - e.at.timestamp()) > fresh_s:
            continue                                       # stale on page open: remember silently
        if e.kind == "exit" and e.extra.get("resolution") == "target":
            p = e.key.split("|")                            # sess|exit|A3|10:45|TARGET -> sess|touch|A3|10:45
            if "|".join([p[0], "touch", p[2], p[3]]) in seen:
                e.major, e.tone, e.notify = False, "none", False   # already announced by the live TARGET TOUCHED alert
        fire.append(e)
    return fire, seen, armed_now
