"""
timeutil.py — the desk runs on New York time. Everything time-related lives here.

Phases (from the manual, Ch.3 and Ch.6, and the Discord SOP):
    08:30  premarket math          08:33  desk-bot cross-check        08:40  chart marking
    08:45  scenario map            09:15  trade card (before 09:25)   09:25  set 09:50 timer
    09:30–09:50  DISCOVERY GATE (hands off)      09:31 gap protocol (outlier opens only)
    09:50  the 09:50 test          09:51–11:30  execution window (11:05 = last qualifying bar)
    11:30  desk shutdown (dead zone)              16:00 cash settlement   16:15 settlement audit
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import List, Optional

from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# ── the desk clock, in minutes after midnight ET ─────────────────────────────
T_MATH = 8 * 60 + 30
T_CROSSCHECK = 8 * 60 + 33
T_MARK = 8 * 60 + 40
T_MAP = 8 * 60 + 45
T_CARD = 9 * 60 + 15
T_CARD_DEADLINE = 9 * 60 + 25
T_OPEN = 9 * 60 + 30
T_GATE_END = 9 * 60 + 50
T_PRIMARY_END = 10 * 60 + 15        # SOP: 09:51–10:15 primary execution window
T_LAST_QUALIFYING = 11 * 60 + 5     # desk bot: no qualifying bar closed by 11:05 = no trade
T_SHUTDOWN = 11 * 60 + 30
T_CLOSE = 16 * 60
T_AUDIT = 16 * 60 + 15

# NYSE full-day holidays (observed). Extend as years pass.
NYSE_HOLIDAYS = {
    # 2025
    date(2025, 1, 1), date(2025, 1, 9), date(2025, 1, 20), date(2025, 2, 17), date(2025, 4, 18),
    date(2025, 5, 26), date(2025, 6, 19), date(2025, 7, 4), date(2025, 9, 1), date(2025, 11, 27),
    date(2025, 12, 25),
    # 2026
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3), date(2026, 5, 25),
    date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26), date(2026, 12, 25),
    # 2027
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26), date(2027, 5, 31),
    date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6), date(2027, 11, 25), date(2027, 12, 24),
}


def now_et() -> datetime:
    return datetime.now(ET)


def minutes_of(dt: datetime) -> int:
    dt = dt.astimezone(ET) if dt.tzinfo else dt.replace(tzinfo=ET)
    return dt.hour * 60 + dt.minute


def fmt_hm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in NYSE_HOLIDAYS


def next_trading_day(d: date) -> date:
    d = d + timedelta(days=1)
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


def prev_trading_day(d: date) -> date:
    d = d - timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def session_date(now: Optional[datetime] = None) -> date:
    """The session the desk is working: today until the 16:15 audit, then the next trading day."""
    now = now or now_et()
    d = now.date()
    if not is_trading_day(d) or minutes_of(now) >= T_AUDIT:
        return next_trading_day(d)
    return d


def trading_days_between(start: date, end: date) -> int:
    """Number of trading sessions from `start` (exclusive) to `end` (inclusive)."""
    n, d = 0, start
    while d < end:
        d += timedelta(days=1)
        if is_trading_day(d):
            n += 1
    return n


def upcoming_expiries(session: date, count: int = 5) -> List[date]:
    """0DTE plus the next trading days (SPXW lists Monday–Friday)."""
    out, d = [session], session
    while len(out) < count:
        d = next_trading_day(d)
        out.append(d)
    return out


@dataclass
class Phase:
    key: str
    label: str
    detail: str
    colour: str          # hex used by the UI banner
    next_key: Optional[str]
    next_at: Optional[int]  # minutes after midnight, for the countdown


def current_phase(now: Optional[datetime] = None) -> Phase:
    now = now or now_et()
    m = minutes_of(now)
    if not is_trading_day(now.date()):
        return Phase("closed", "Market closed", "Weekend or exchange holiday. Next session's plan is shown.",
                     "#5c6470", "math", None)
    if m < T_MATH:
        return Phase("premarket", "Pre-market", "Inputs lock at 08:30. Nothing to do yet but read.",
                     "#5c6470", "math", T_MATH)
    if m < T_MAP:
        return Phase("math", "08:30 Premarket math", "Lock C5–C9, note C22 regime and C23 inventory bias, "
                     "cross-check C13/C17 within 2 pts of the desk bot, mark the eight coordinates.",
                     "#2d7ff9", "map", T_MAP)
    if m < T_CARD:
        return Phase("map", "08:45 Scenario map", "Read the If/Then map: favoured side, trap zones, King Nodes. "
                     "Check the calendar for CPI/PPI/NFP/FOMC. Confirm the map agrees with C22.",
                     "#2d7ff9", "card", T_CARD)
    if m < T_CARD_DEADLINE:
        return Phase("card", "09:15 Trade card", "Post Archetype | Trigger | Invalidation | 1R cap before 09:25. "
                     "No setup? Post Watch Day.", "#d29a1c", "timer", T_CARD_DEADLINE)
    if m < T_OPEN:
        return Phase("timer", "09:25 Set the 09:50 timer", "Hands off order entry until the timer fires.",
                     "#d29a1c", "gate", T_OPEN)
    if m < T_GATE_END:
        return Phase("gate", "09:30–09:50 Discovery gate — NO TRADES",
                     "Institutional price discovery. Classify the open: acceptance or trap. "
                     "Gap day? Enter the 09:30 cash open in C10 at 09:31.", "#c0392b", "exec", T_GATE_END)
    if m < T_PRIMARY_END:
        return Phase("exec", "09:51–10:15 Primary execution window — one setup, 1R", "The 09:50 test decides A or B. "
                     "Execute only on a qualifying 5-minute close. MEIC entries go on here once the opening volatility has cleared.",
                     "#1e9e6a", "exec2", T_PRIMARY_END)
    if m < T_LAST_QUALIFYING:
        return Phase("exec2", "Execution window — qualifying bars close by 11:05", "Still inside the window (manual: 09:51–11:30). "
                     "A bar must CLOSE by 11:05 to qualify — the 11:00 bar is the last one.", "#1e9e6a", "late", T_LAST_QUALIFYING)
    if m < T_SHUTDOWN:
        return Phase("late", "After 11:05 — no new qualifying bars", "Manage the open trade only. Flat by 11:30.",
                     "#1e9e6a", "dead", T_SHUTDOWN)
    if m < T_CLOSE:
        return Phase("dead", "11:30 Desk shutdown — dead zone", "Desk closed for new positions. Screens off.",
                     "#5c6470", "settle", T_CLOSE)
    if m < T_AUDIT:
        return Phase("settle", "16:00 Cash settlement", "Wait for the official close, then run the audit.",
                     "#8e44ad", "audit", T_AUDIT)
    return Phase("audit", "16:15 Settlement audit", "Log the journal row, run the audit against the 08:30 map, "
                 "post the broker card. Tomorrow's plan is provisional until 08:30.", "#8e44ad", None, None)


def et_dt(d: date, minutes: int) -> datetime:
    return datetime.combine(d, time(minutes // 60, minutes % 60), tzinfo=ET)


def fmt_session_title(d: date) -> str:
    return d.strftime("%A (%b %d, %Y)").upper()
