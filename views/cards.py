"""cards.py — the Desk's state cards and the MEIC ticket, in the desk's own visual language (#live-trade-ideas
'LIVE EXECUTION ALERT', #daily-scenarios '08:35 TACTICAL MATRIX', #meic-condor-desk '09:50 MEIC CONDOR DESK'):
gradient pill, bold uppercase title, grey subtitle with • separators, outlined status pill, five KPI tiles, panels, footer.

Pure HTML builders (strings). Rendered with st.markdown(unsafe_allow_html=True); every builder returns ONE line of HTML
(Streamlit's markdown would turn indented or blank lines into code blocks)."""
from __future__ import annotations

import html
from typing import Dict, List, Optional

from core.alerts import SETUP, INSTR
from utils.timeutil import T_SHUTDOWN, T_LAST_QUALIFYING, T_PRIMARY_END, fmt_hm

BLUE, RED, AMBER, GREEN, YELLOW, VIOLET, GREY, CYAN = "#38bdf8", "#ef4444", "#f59e0b", "#10b981", "#facc15", "#a78bfa", "#94a3b8", "#22d3ee"

CARD_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@500;600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap');
.az-card{background:var(--az-card);border:1px solid var(--az-line);border-radius:14px;padding:16px 18px 11px;margin:6px 0 10px;color:var(--az-text);font-family:Inter,'IBM Plex Sans',system-ui,sans-serif;}
.az-card *{box-sizing:border-box;}
.az-head{display:flex;flex-wrap:wrap;align-items:flex-start;justify-content:space-between;gap:10px 16px;padding-bottom:12px;border-bottom:1px solid var(--az-line);margin-bottom:12px;}
.az-hl{display:flex;align-items:flex-start;gap:8px 14px;min-width:0;flex:1 1 420px;flex-wrap:wrap;}
.az-hr{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end;align-items:center;}
.az-pill{display:inline-block;padding:6px 12px;border-radius:7px;font:700 0.76rem 'JetBrains Mono',ui-monospace,monospace;letter-spacing:.08em;color:#fff;white-space:nowrap;background:linear-gradient(90deg,#0ea5e9,#6366f1);margin-top:2px;}
.az-pill.amber{background:linear-gradient(90deg,#f59e0b,#ea580c);}
.az-pill.green{background:linear-gradient(90deg,#10b981,#0ea5e9);}
.az-pill.red{background:linear-gradient(90deg,#ef4444,#be123c);}
.az-pill.slate{background:linear-gradient(90deg,#64748b,#334155);}
.az-pill.violet{background:linear-gradient(90deg,#8b5cf6,#6366f1);}
.az-title{font-weight:800;font-size:1.3rem;letter-spacing:.005em;text-transform:uppercase;line-height:1.18;color:var(--az-text);}
.az-sub{color:var(--az-muted);font-size:.88rem;margin-top:4px;line-height:1.35;}
.az-status{display:inline-block;padding:6px 14px;border-radius:999px;border:1.5px solid currentColor;font:600 .8rem 'JetBrains Mono',ui-monospace,monospace;letter-spacing:.05em;white-space:nowrap;}
.az-tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:12px;}
.az-tile{background:var(--az-tile);border:1px solid var(--az-line);border-radius:10px;padding:11px 13px;min-width:0;}
.az-k{font:700 .68rem Inter,sans-serif;letter-spacing:.09em;color:var(--az-muted);text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.az-v{font:700 1.42rem 'JetBrains Mono',ui-monospace,monospace;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.az-s{color:var(--az-muted);font-size:.78rem;margin-top:3px;line-height:1.3;}
.az-cols{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:12px;}
@media (max-width:900px){.az-cols{grid-template-columns:1fr;}}
.az-panel{background:var(--az-tile);border:1px solid var(--az-line);border-radius:10px;padding:12px 14px;min-width:0;}
.az-ph{display:flex;justify-content:space-between;align-items:baseline;gap:8px;font:800 .76rem Inter,sans-serif;letter-spacing:.07em;text-transform:uppercase;margin-bottom:8px;color:var(--az-text);}
.az-ph .r{font:700 .76rem 'JetBrains Mono',ui-monospace,monospace;white-space:nowrap;}
.az-row{display:grid;grid-template-columns:6.9rem 1fr 2.5rem;align-items:center;gap:10px;font-size:.85rem;margin:6px 0;}
.az-row .v{font:700 .8rem 'JetBrains Mono',ui-monospace,monospace;text-align:right;}
.az-bar{height:7px;border-radius:5px;background:var(--az-track);overflow:hidden;}
.az-bar>i{display:block;height:100%;border-radius:5px;}
.az-mono{font-family:'JetBrains Mono',ui-monospace,monospace;}
.az-li{font-size:.84rem;line-height:1.38;margin:5px 0;padding-left:12px;border-left:2px solid var(--az-line);}
.az-li.first{border-left-color:#f59e0b;}
.az-foot{display:flex;flex-wrap:wrap;justify-content:space-between;gap:6px 16px;border-top:1px solid var(--az-line);margin-top:12px;padding-top:9px;font-size:.8rem;color:var(--az-muted);}
.az-foot b{color:var(--az-text);}
.az-foot .r{font-family:'JetBrains Mono',ui-monospace,monospace;}
.az-trk{margin:2px 2px 14px;}
.az-trk-bar{position:relative;height:12px;border-radius:7px;background:linear-gradient(90deg,rgba(239,68,68,.30),var(--az-track) 35%,var(--az-track) 65%,rgba(16,185,129,.30));}
.az-trk-fill{position:absolute;top:0;height:12px;border-radius:7px;opacity:.85;}
.az-trk-entry{position:absolute;top:-5px;width:2px;height:22px;background:#38bdf8;}
.az-trk-dot{position:absolute;top:-4px;width:20px;height:20px;margin-left:-10px;border-radius:50%;border:3px solid var(--az-card);box-shadow:0 0 0 2px currentColor;background:currentColor;}
.az-trk-lbl{display:grid;grid-template-columns:1fr auto 1fr;gap:8px;margin-top:9px;font:600 .78rem 'JetBrains Mono',ui-monospace,monospace;}
.az-trk-lbl .c{text-align:center;} .az-trk-lbl .r{text-align:right;}
.az-pb{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:8px 11px;border:1px solid var(--az-line);border-radius:9px;margin:6px 0;font-size:.86rem;}
.az-pb.on{border-color:rgba(16,185,129,.75);} .az-pb.armed{border-color:#f59e0b;box-shadow:inset 0 0 0 1px rgba(245,158,11,.35);} .az-pb.fired{border-color:#38bdf8;}
.az-pb .n{font-weight:600;} .az-pb.off .n{color:var(--az-muted);}
.az-tag{font:700 .68rem 'JetBrains Mono',ui-monospace,monospace;letter-spacing:.04em;padding:3px 8px;border-radius:5px;white-space:nowrap;}
.az-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;}
.az-chip{display:inline-block;padding:4px 10px;border-radius:7px;font:600 .76rem 'JetBrains Mono',ui-monospace,monospace;border:1px solid var(--az-line);background:var(--az-tile);color:var(--az-text);}
.az-chip.armed{border-color:#f59e0b;color:#f59e0b;} .az-chip.off{color:var(--az-muted);}
.az-tt{display:grid;grid-template-columns:3.2rem 1fr auto;gap:8px;align-items:center;font-size:.84rem;margin:6px 0;}
.az-ok{color:#10b981;font-weight:700;} .az-no{color:#ef4444;font-weight:700;} .az-mid{color:#f59e0b;font-weight:700;}
@keyframes azglow{0%{box-shadow:0 0 0 0 rgba(245,158,11,.5)}70%{box-shadow:0 0 0 12px rgba(245,158,11,0)}100%{box-shadow:0 0 0 0 rgba(245,158,11,0)}}
@keyframes azglowg{0%{box-shadow:0 0 0 0 rgba(16,185,129,.45)}70%{box-shadow:0 0 0 12px rgba(16,185,129,0)}100%{box-shadow:0 0 0 0 rgba(16,185,129,0)}}
.az-card.armed{border-color:#f59e0b;animation:azglow 1.8s infinite;}
.az-card.live{border-color:#10b981;animation:azglowg 2.4s infinite;}
.az-card.compact{padding:12px 16px;}
.az-card.compact .az-head{border-bottom:none;padding-bottom:0;margin-bottom:0;}
.az-card.compact .az-title{font-size:1.06rem;}
.az-wing{border:1px solid var(--az-line);border-left:4px solid;border-radius:10px;padding:11px 14px;margin:8px 0;background:var(--az-card);}
.az-wing .w1{font:700 .8rem Inter,sans-serif;letter-spacing:.03em;text-transform:uppercase;}
.az-wing .w2{font:700 1.38rem 'JetBrains Mono',ui-monospace,monospace;margin:4px 0;}
.az-wing .w3{font-size:.84rem;}
.az-flow{height:12px;border-radius:7px;overflow:hidden;display:flex;margin-top:6px;}
.az-side{font-size:.8rem;margin:6px 0 0;color:var(--az-muted);}
.az-mini{border:1px solid var(--border);border-left:4px solid;border-radius:8px;padding:7px 10px;margin:2px 0 8px;background:var(--panel2);font-size:.84rem;line-height:1.35;}
.az-mini .t{font:700 .78rem 'JetBrains Mono',ui-monospace,monospace;letter-spacing:.03em;}
.az-log{font-size:.76rem;color:var(--muted);margin:2px 0;}
</style>"""


def esc(x) -> str:
    return html.escape(str(x), quote=True)


def f2(x: Optional[float]) -> str:
    return "—" if x is None else f"{x:,.2f}"


def pill(text: str, cls: str = "") -> str:
    return f"<span class='az-pill {cls}'>{esc(text)}</span>"


def status(text: str, color: str) -> str:
    return f"<span class='az-status' style='color:{color}'>{esc(text)}</span>"


def tile(k: str, v: str, s: str, color: str) -> str:
    return (f"<div class='az-tile'><div class='az-k'>{esc(k)}</div><div class='az-v' style='color:{color}'>{esc(v)}</div>"
            f"<div class='az-s'>{s}</div></div>")


def head(pill_html: str, title: str, sub: str, right: str = "") -> str:
    return (f"<div class='az-head'><div class='az-hl'>{pill_html}<div style='min-width:0'><div class='az-title'>{esc(title)}</div>"
            f"<div class='az-sub'>{sub}</div></div></div><div class='az-hr'>{right}</div></div>")


def foot(left: str, right: str) -> str:
    return f"<div class='az-foot'><div>{left}</div><div class='r'>{esc(right)}</div></div>"


# ── panels ────────────────────────────────────────────────────────────────────
def scorecard(sc) -> str:
    """The ten checks as bars (green 1, amber ½, empty 0), the app's own definitions; notes on hover."""
    if sc is None:
        return ("<div class='az-panel'><div class='az-ph'><span>10-check scorecard</span><span class='r'>—</span></div>"
                "<div class='az-s'>Scored once the setup has fired (Scenario Book overlay; alerts follow the book rule).</div></div>")
    col = {"SENT": GREEN, "WAITING": YELLOW, "NOT_SENT": GREY, "DROPPED": RED, "EXPIRED": RED, "CUTOFF": GREY}.get(sc.status, GREY)
    tag = {"SENT": "SENT", "WAITING": "WAITING", "NOT_SENT": "NOT SENT", "DROPPED": "DROPPED", "EXPIRED": "DROPPED", "CUTOFF": "CUT-OFF"}.get(sc.status, sc.status)
    rows = ""
    for c in sc.checks:
        cc = GREEN if c.value >= 1 else AMBER if c.value > 0 else GREY
        rows += (f"<div class='az-row' title='{esc(c.note)}'><span>{esc(c.name)}</span><span class='az-bar'><i style='width:{min(c.value, 1) * 100:.0f}%;"
                 f"background:{cc}'></i></span><span class='v' style='color:{cc}'>{c.value:.1f}</span></div>")
    return (f"<div class='az-panel'><div class='az-ph'><span>10-check quantitative scorecard</span><span class='r' style='color:{col}'>"
            f"{sc.score:.1f} / 9.5 · {tag}</span></div>{rows}<div class='az-s' style='margin-top:8px'>{esc(sc.status_text)} · send rule: "
            f"{esc(sc.send_rule)} · hover a row for its measurement</div></div>")


def playbook(plan: Dict, plays: List, trade: Optional[Dict], vix: float) -> str:
    """VIX-gated playbook status, the engine's view (A2 is checked in every regime)."""
    valid = plan["eligible"]["valid"]
    need = {1: "needs VIX under 15", 3: "needs VIX 15 or over", 4: "needs VIX above 18.5"}
    names = {1: "S1 Shelf Fade", 2: "S2 Node Absorption", 3: "S3 Three-Ticker Break", 4: "S4 Shelf Break Runner"}
    rows = ""
    for a in (1, 2, 3, 4):
        armed = any(getattr(p, "archetype", 0) == a and p.status == "armed" for p in plays or [])
        if trade and int(trade.get("archetype", 0)) == a:
            cls, tag, tc = "fired", "TRIGGERED", BLUE
        elif armed:
            cls, tag, tc = "armed", "ARMED", AMBER
        elif a in valid:
            cls, tag, tc = "on", "PLAYBOOK ACTIVE", GREEN
        elif a == 2:
            cls, tag, tc = "on", "CHECKED · ALL REGIMES", GREY
        else:
            cls, tag, tc = "off", f"OFF ({need[a]})", GREY
        rows += (f"<div class='az-pb {cls}'><span class='n'>{names[a]}</span><span class='az-tag' style='color:{tc};"
                 f"background:color-mix(in srgb,{tc} 14%,transparent)'>{esc(tag)}</span></div>")
    return (f"<div class='az-panel'><div class='az-ph'><span>VIX-gated playbook status</span><span class='r' style='color:{CYAN}'>"
            f"VIX {vix:.2f}</span></div>{rows}</div>")


def exits_panel(exits: List[str]) -> str:
    items = "".join(f"<div class='az-li{' first' if i == 0 else ''}'>{esc(e)}</div>" for i, e in enumerate(exits or []))
    return f"<div class='az-panel'><div class='az-ph'><span>Exit plan — nearest first</span></div>{items}</div>"


def track(stop: float, entry: float, target: float, now: Optional[float], risk: float) -> str:
    """Stop (left) → target (right), whatever the side; the dot is the live price."""
    span = (target - stop) or 1e-9
    pos = lambda p: max(0.0, min(1.0, (p - stop) / span)) * 100.0
    e = pos(entry)
    out = f"<div class='az-trk'><div class='az-trk-bar'>"
    r_now = None
    if now is not None:
        n = pos(now)
        r_now = ((now - entry) / risk) if target > stop else ((entry - now) / risk)
        lo, hi = sorted((e, n))
        c = GREEN if (r_now or 0) >= 0 else RED
        out += f"<span class='az-trk-fill' style='left:{lo:.1f}%;width:{hi - lo:.1f}%;background:{c}'></span>"
    out += f"<span class='az-trk-entry' style='left:{e:.1f}%'></span>"
    if now is not None:
        out += f"<span class='az-trk-dot' style='left:{pos(now):.1f}%;color:{GREEN if r_now >= 0 else RED}'></span>"
    rr = abs(target - entry) / risk if risk else 0.0
    mid = (f"<span style='color:{GREEN if r_now >= 0 else RED}'>NOW {now:,.2f} · {r_now:+.2f}R</span>" if now is not None else
           f"<span style='color:{BLUE}'>ENTRY {entry:,.2f}</span>")
    out += (f"</div><div class='az-trk-lbl'><span style='color:{RED}'>STOP {stop:,.2f} · −1R</span><span class='c'>{mid}</span>"
            f"<span class='r' style='color:{GREEN}'>TARGET {target:,.2f} · +{rr:.2f}R</span></div></div>")
    return out


# ── state cards ───────────────────────────────────────────────────────────────
def _time_left(m: int) -> str:
    left = T_SHUTDOWN - m
    return f"{left} min left" if left > 0 else "time stop reached"


def active_card(s, size_txt: str) -> str:
    b, t = s.banner, s.banner.trade
    a, side, tt = int(t["archetype"]), t["side"], t["trigger_time"]
    entry, stop, tgt, risk = t["entry"], t["stop"], t["target"], t["risk_pts"] or 1e-9
    long = side == "long"
    last = s.last
    pnl = ((last - entry) if long else (entry - last)) if last is not None else None
    r_now = pnl / risk if pnl is not None else None
    room = abs(tgt - entry)
    hh, mm = map(int, tt.split(":"))
    close_t = fmt_hm(hh * 60 + mm + (0 if a == 4 else 5))
    when = f"entered on the open of the {tt} bar ({close_t} ET)" if a == 4 else f"triggered on the {tt} bar close ({close_t} ET)"
    right = ""
    if r_now is not None:
        right += status(f"LIVE {r_now:+.2f}R", GREEN if r_now >= 0 else RED)
    sc = s.score
    if sc is not None:
        col = {"SENT": GREEN, "WAITING": YELLOW, "DROPPED": RED, "EXPIRED": RED}.get(sc.status, GREY)
        lab = {"SENT": "SENT", "WAITING": "WAITING", "NOT_SENT": "NOT SENT", "DROPPED": "DROPPED", "EXPIRED": "DROPPED", "CUTOFF": "CUT-OFF"}.get(sc.status, sc.status)
        right += status(f"SCORE {sc.score:.1f} / 9.5 · {lab}", col)
    d_stop = abs(last - stop) if last is not None else None
    d_tgt = abs(tgt - last) if last is not None else None
    tiles = (tile("Entry reference", f2(entry), f"{'Open of the' if a == 4 else 'Trigger bar'} {tt}" + (" · close" if a != 4 else ""), BLUE)
             + tile("Structural stop", f2(stop), "5-min close invalidation" + (f" · {d_stop:.2f} pts away" if d_stop is not None else ""), RED)
             + tile("1R planned risk", f"{risk:.2f} pts", esc(size_txt), AMBER)
             + tile("Primary target", f2(tgt), f"{room:.2f} pts ({room / risk:.2f}R)" + (f" · {d_tgt:.2f} away" if d_tgt is not None else ""), GREEN)
             + tile("Hard time stop", "11:30 ET", f"Zero midday hold · {_time_left(s.m)}", YELLOW))
    body = (f"<div class='az-cols'>{exits_panel(b.exits)}{scorecard(sc)}</div>")
    return (f"<div class='az-card live'>{head(pill('LIVE EXECUTION · BOOK TRADE'), f'{SETUP[a]} — {INSTR[side]}', f'{esc(when)} • A{a} • SPXW 0DTE • flat by 11:30 ET', right)}"
            f"<div class='az-tiles'>{tiles}</div>{track(stop, entry, tgt, last, risk)}{body}"
            + foot(f"<b>Manage, don't add:</b> the stop is a 5-minute CLOSE {'below' if long else 'above'} {stop:,.2f} — not a wick. "
                   f"Late entry only within 0.5R ({0.5 * risk:.2f} pts) of the entry.", "Azraël Desk • book rules · Scenario Book score")
            + "</div>")


def done_card(s) -> str:
    b, t = s.banner, s.banner.trade
    a, side, tt = int(t["archetype"]), t["side"], t["trigger_time"]
    res = str(t.get("resolution"))
    name = "TARGET" if res == "target" else "STOPPED" if res == "stopped" else "FLAT 11:30"
    col = GREEN if res == "target" else RED if res == "stopped" else GREY
    r = t.get("r_multiple")
    pnl = t.get("pnl_pts")
    et = t.get("exit_time") or tt
    eh, em_ = map(int, et.split(":"))
    th, tm = map(int, tt.split(":"))
    mins_in = (eh * 60 + em_ + 5) - (th * 60 + tm + (0 if a == 4 else 5))
    chosen = (s.live_s or {}).get("chosen")
    best = getattr(chosen, "best_excursion", None) if chosen is not None else None
    right = status(f"{name} {r:+.2f}R" if r is not None else name, col)
    if s.score is not None:
        right += status(f"SCORE {s.score.score:.1f} / 9.5", GREY)
    tiles = (tile("Entry", f2(t["entry"]), f"the {tt} bar" + (" open" if a == 4 else " close"), BLUE)
             + tile("Exit", f2(t.get("exit_price")), f"{name.lower()} · the {et} bar", col)
             + tile("Result", f"{pnl:+.2f} pts" if pnl is not None else "—", f"{r:+.2f}R on the index" if r is not None else "", col)
             + tile("Best excursion", f"{best:.2f} pts" if best is not None else "—", "in favour before the exit", CYAN)
             + tile("Time in trade", f"{max(mins_in, 0)} min", f"stop {t['stop']:,.2f} · target {t['target']:,.2f}", YELLOW))
    rows = "".join(f"<div class='az-li first'>{esc(n)}</div>" for n in (b.notes or [])[-1:])
    if chosen is not None and getattr(chosen, "trigger_text", ""):
        rows += f"<div class='az-li'><b>Setup mechanics:</b> {esc(chosen.trigger_text)}</div>"
    if chosen is not None and getattr(chosen, "invalidation_text", ""):
        rows += f"<div class='az-li'><b>Invalidation:</b> {esc(chosen.invalidation_text)}</div>"
    body = f"<div class='az-cols'><div class='az-panel'><div class='az-ph'><span>Resolution</span></div>{rows}</div>{scorecard(s.score)}</div>"
    return (f"<div class='az-card'>{head(pill('SETUP RESOLVED', 'green' if res == 'target' else 'red' if res == 'stopped' else 'slate'), f'{SETUP[a]} — {INSTR[side]}', 'One setup per day — the desk is closed for you • log the journal row at 16:15', right)}"
            f"<div class='az-tiles'>{tiles}</div>{body}"
            + foot("<b>Discipline:</b> no second trade, no revenge. Screens off at 11:30.", "Azraël Desk • settlement audit at 16:15") + "</div>")


def _armed_sorted(plays: List) -> List:
    return sorted((p for p in plays if p.status == "armed"),
                  key=lambda p: (not p.ready, abs(p.distance) if p.distance is not None else 9e9))


def armed_card(s) -> str:
    b = s.banner
    arm = _armed_sorted(b.plays)
    p = arm[0]
    a = p.archetype
    long = "CALLS" in p.side and "PUTS" not in p.side
    side_txt = "LONG CALLS" if long else "LONG PUTS"
    if a == 2:
        title = f"{SETUP[2]} — {'PUT NODE' if long else 'CALL NODE'} {p.trigger_px:,.0f}"
    elif a == 3:
        title = f"{SETUP[3]} — {'UPSIDE' if long else 'DOWNSIDE'} BREAK"
    else:
        title = f"{SETUP[a]} — {side_txt}"
    bar = s.bar
    right = status("WAIT FOR THE 5-MIN CLOSE", AMBER) if p.ready else status(f"NOT READY · {p.ready_note}", GREY)
    dist = p.distance
    dtxt = ("—" if dist is None else f"{dist:.2f} pts to go" if dist > 0 else f"{-dist:.2f} pts through")
    stop_sub = {1: "close 8 pts beyond the shelf", 2: "node ∓ 5 on a close, or two closes back through", 3: "the broken box edge (5-min close)",
                4: "close back inside the shelf"}[a]
    est = ""
    if p.target_px is not None and p.trigger_px is not None and p.stop_px is not None and abs(p.trigger_px - p.stop_px) > 1e-9:
        est = f"≈ {abs(p.target_px - p.trigger_px) / abs(p.trigger_px - p.stop_px):.2f}R from the trigger"
    trig_k = {1: "Shelf", 2: "Node", 3: "Break level", 4: "Shelf"}[a]
    trig_sub = {1: "two closes hold it, the third reverses on volume", 2: f"a close back {'above' if long else 'below'} with a > ½ wick",
                3: f"5-min close {'≥' if long else '≤'} this, SPY & QQQ outside too", 4: f"two 5-min closes {'above' if long else 'below'}, the next holds"}[a]
    tiles = (tile(trig_k, f2(p.trigger_px), trig_sub, AMBER)
             + tile("Live price", f2(s.last), esc(dtxt), BLUE)
             + tile("Stop if it fires", f2(p.stop_px), stop_sub, RED)
             + tile("Target if it fires", f2(p.target_px), est or esc(p.target), GREEN)
             + tile("Bar closes", bar["close"].strftime("%H:%M"), f"the {bar['open']:%H:%M} bar · {bar['countdown']} left", YELLOW))
    left = ""
    if a == 3 and s.three:
        rows = ""
        for nm in ("SPX", "SPY", "QQQ"):
            x = s.three.get(nm)
            if not x:
                rows += f"<div class='az-tt'><b>{nm}</b><span class='az-s'>no bars</span><span></span></div>"
                continue
            ok = (x["side"] == "above") if long else (x["side"] == "below")
            mark = "<span class='az-ok'>OUTSIDE ✓</span>" if ok else ("<span class='az-mid'>INSIDE</span>" if x["side"] == "inside" else "<span class='az-no'>WRONG SIDE</span>")
            rows += (f"<div class='az-tt'><b>{nm}</b><span class='az-mono' style='font-size:.8rem'>box {x['lo']:,.2f}–{x['hi']:,.2f} · live {x['px']:,.2f}</span>{mark}</div>")
        sx = s.three.get("SPX") or {}
        need = (f"SPX must CLOSE {'≥' if long else '≤'} {p.trigger_px:,.2f} ({sx.get('min_out', 0):.2f} beyond the box) and SPY and QQQ must close outside "
                f"their own boxes on the same bar; > 8 pts of room to {f2(p.target_px)}.") if p.trigger_px else ""
        left = (f"<div class='az-panel'><div class='az-ph'><span>3-ticker alignment (live)</span><span class='r' style='color:{AMBER}'>"
                f"box {p.box['start']}–{p.box['end']} · {p.box['width']:.2f} / {p.box['max_width']:.2f}</span></div>{rows}"
                f"<div class='az-s' style='margin-top:6px'>{esc(need)}</div></div>")
    else:
        left = (f"<div class='az-panel'><div class='az-ph'><span>What fires it</span></div><div class='az-li first'>{esc(p.condition)}</div>"
                f"<div class='az-li'>{esc(p.status_text)}</div><div class='az-li'>Entry: {esc(p.entry)}</div></div>")
    others = "".join(f"<span class='az-chip armed'>{esc(SETUP[q.archetype].split(' ')[0])} {esc(q.trigger_rule or q.title)}</span>" for q in arm[1:3])
    body = f"<div class='az-cols'>{left}{playbook(s.plan, b.plays, None, s.plan['inputs']['c6'])}</div>"
    pill_html = pill(f"⚡ ARMED · {s.now:%H:%M} ET", "amber")
    countdown = bar["countdown"]
    sub = f"{esc(p.trigger_rule)} • {esc(bar['label'])} (in {countdown})"
    return (f"<div class='az-card armed'>{head(pill_html, title, sub, right)}"
            f"<div class='az-tiles'>{tiles}</div>{body}" + (f"<div class='az-chips'>{others}</div>" if others else "")
            + foot("<b>Hands off until the close:</b> no close, no trade. The alert fires again only if the close qualifies.",
                   "Azraël Desk • armed heads-up") + "</div>")


def ladder_chips(plays: List) -> str:
    chips = ""
    for p in plays or []:
        nm = SETUP.get(p.archetype, "").split(" ")[0]
        if p.status == "blocked":
            chips += f"<span class='az-chip off'>{nm} {esc(p.status_text)}</span>"
            continue
        long = "CALLS" in p.side and "PUTS" not in p.side
        where = {1: ("−0.5 shelf" if long else "+0.5 shelf"), 2: ("put node" if long else "call node"),
                 4: ("+0.5 shelf" if long else "−0.5 shelf")}.get(p.archetype, "")
        if p.archetype == 3 and p.box:
            txt = f"{nm} box {p.box['lo']:,.2f}–{p.box['hi']:,.2f} · break ≥ {p.box['up_trigger']:,.2f} / ≤ {p.box['dn_trigger']:,.2f}"
        elif p.trigger_px is not None:
            d = f" · {abs(p.distance):.1f} pts away" if p.distance is not None else ""
            px = f"{p.trigger_px:,.0f}" if p.archetype == 2 else f"{p.trigger_px:,.2f}"
            txt = f"{nm} {where} {px}{d}" + ("" if p.ready else f" · {p.ready_note}")
        else:
            txt = f"{nm} {p.status_text}"
        chips += f"<span class='az-chip{' armed' if p.status == 'armed' else ''}'>{esc(txt)}</span>"
    return f"<div class='az-chips'>{chips}</div>" if chips else ""


def watching_card(s) -> str:
    b = s.banner
    win = f"primary window until {fmt_hm(T_PRIMARY_END)}" if s.m < T_PRIMARY_END else f"last qualifying bar closes {fmt_hm(T_LAST_QUALIFYING)}"
    return (f"<div class='az-card compact'>{head(pill(f'WATCHING · {s.now:%H:%M} ET', 'slate'), 'Waiting for a qualifying 5-minute close', esc(b.sub), status(win.upper(), GREY))}"
            f"{ladder_chips(b.plays)}</div>")


COMPACT = {"PREMARKET": ("slate", "PRE-MARKET"), "LOCKED": ("violet", "PLAN LOCKED"), "GATE": ("red", "DISCOVERY GATE"),
           "STAND_DOWN": ("slate", "11:05 STAND DOWN"), "SHUTDOWN": ("slate", "DESK CLOSED"), "SETTLE": ("slate", "SETTLEMENT")}


def compact_card(s) -> str:
    b = s.banner
    cls, lab = COMPACT.get(b.state, ("slate", b.state))
    chips = ladder_chips(b.plays) if b.state in ("LOCKED", "GATE", "PREMARKET") else ""
    return f"<div class='az-card compact'>{head(pill(lab, cls), b.headline, esc(b.sub))}{chips}</div>"


def state_card(s, size_txt: str) -> str:
    b = s.banner
    if b.state == "ACTIVE" and b.trade:
        return active_card(s, size_txt)
    if b.state == "DONE" and b.trade:
        return done_card(s)
    if b.state == "ARMED" and any(p.status == "armed" for p in b.plays):
        return armed_card(s)
    if b.state == "WATCHING":
        return watching_card(s)
    return compact_card(s)


def mini_status(s) -> str:
    """One line for the sidebar on every page."""
    if s is None or not s.ok or s.banner is None:
        return "<div class='az-mini' style='border-left-color:#64748b'><span class='t'>DESK</span> · no plan yet</div>"
    b = s.banner
    if b.state == "ACTIVE" and b.trade:
        t = b.trade
        long = t["side"] == "long"
        r = (((s.last - t["entry"]) if long else (t["entry"] - s.last)) / (t["risk_pts"] or 1e-9)) if s.last is not None else None
        txt = (f"<span class='t' style='color:{GREEN}'>🟢 TRADE ACTIVE</span> · {SETUP[int(t['archetype'])].split(' ')[0]} {INSTR[t['side']]}"
               + (f" · <b>{r:+.2f}R</b>" if r is not None else "") + f"<br>stop {t['stop']:,.2f} · target {t['target']:,.2f}")
        col = GREEN
    elif b.state == "DONE" and b.trade:
        t = b.trade
        res = str(t.get("resolution"))
        col = GREEN if res == "target" else RED if res == "stopped" else GREY
        txt = f"<span class='t' style='color:{col}'>🏁 DONE</span> · {esc(b.headline.replace('DAY DONE — ', ''))}"
    elif b.state == "ARMED":
        arm = _armed_sorted(b.plays)
        p = arm[0] if arm else None
        col = AMBER
        txt = f"<span class='t' style='color:{AMBER}'>⚡ ARMED</span>" + (f" · {SETUP[p.archetype].split(' ')[0]} · {esc(p.trigger_rule)}" if p else "")
    else:
        col = {"GATE": RED, "LOCKED": VIOLET, "WATCHING": "#64748b"}.get(b.state, "#64748b")
        short = {"PREMARKET": ("PRE-MARKET", "provisional map · locks 08:30"), "LOCKED": ("PLAN LOCKED", "nothing until the 09:50 gate"),
                 "GATE": ("DISCOVERY GATE", "no trades · verdict at 09:50"), "WATCHING": ("WATCHING", "waiting for a qualifying 5-min close"),
                 "STAND_DOWN": ("STAND DOWN", "Watch Day · flat by 11:30"), "SHUTDOWN": ("DESK CLOSED", "dead zone · no new positions"),
                 "SETTLE": ("SETTLEMENT", "run the 16:15 audit")}.get(b.state, (b.state.replace("_", " "), b.headline))
        txt = f"<span class='t'>{esc(short[0])}</span> · {esc(short[1])}"
    return f"<div class='az-mini' style='border-left-color:{col}'>{txt}</div>"


# ── MEIC ──────────────────────────────────────────────────────────────────────
def payoff_svg(t: Dict, pay: Dict, spot: Optional[float]) -> str:
    """Expiration payoff with the harvest cage, defense triggers and the live SPX print."""
    W, H, L, R_, T, B = 760, 520, 56, 18, 44, 56
    x0, x1 = pay["x_lo"], pay["x_hi"]
    if spot is not None:
        x0, x1 = min(x0, spot - 10), max(x1, spot + 10)
    y_hi, y_lo = pay["max_gain"], -pay["max_loss"]
    X = lambda v: L + (v - x0) / (x1 - x0) * (W - L - R_)
    Y = lambda v: T + (y_hi - v) / (y_hi - y_lo) * (H - T - B) * 0.82 + (H - T - B) * 0.06
    zero = Y(0.0)
    cage = (f"<rect x='{X(t['short_put']):.1f}' y='{T}' width='{X(t['short_call']) - X(t['short_put']):.1f}' height='{H - T - B}' fill='rgba(16,185,129,.10)'/>"
            f"<rect x='{L}' y='{T}' width='{X(t['short_put']) - L:.1f}' height='{H - T - B}' fill='rgba(239,68,68,.08)'/>"
            f"<rect x='{X(t['short_call']):.1f}' y='{T}' width='{W - R_ - X(t['short_call']):.1f}' height='{H - T - B}' fill='rgba(239,68,68,.08)'/>")
    path = " ".join(f"{'M' if i == 0 else 'L'}{X(x):.1f},{Y(y):.1f}" for i, (x, y) in enumerate(pay["points"]))
    lines = (f"<line x1='{L}' x2='{W - R_}' y1='{zero:.1f}' y2='{zero:.1f}' stroke='#64748b' stroke-width='1'/>"
             f"<line x1='{X(t['short_put']):.1f}' x2='{X(t['short_put']):.1f}' y1='{T}' y2='{H - B}' stroke='{RED}' stroke-dasharray='5 4' stroke-width='1.5'/>"
             f"<line x1='{X(t['short_call']):.1f}' x2='{X(t['short_call']):.1f}' y1='{T}' y2='{H - B}' stroke='{RED}' stroke-dasharray='5 4' stroke-width='1.5'/>"
             f"<line x1='{X(t['put_trigger']):.1f}' x2='{X(t['put_trigger']):.1f}' y1='{T}' y2='{H - B}' stroke='{AMBER}' stroke-dasharray='2 4' stroke-width='1.2'/>"
             f"<line x1='{X(t['call_trigger']):.1f}' x2='{X(t['call_trigger']):.1f}' y1='{T}' y2='{H - B}' stroke='{AMBER}' stroke-dasharray='2 4' stroke-width='1.2'/>"
             f"<line x1='{X(t['anchor']):.1f}' x2='{X(t['anchor']):.1f}' y1='{T}' y2='{H - B}' stroke='{YELLOW}' stroke-dasharray='3 4' stroke-width='1.5'/>")
    mono = "font-family='JetBrains Mono,ui-monospace,monospace'"
    labels = (f"<text x='{(X(t['short_put']) + X(t['short_call'])) / 2:.1f}' y='{T - 12}' text-anchor='middle' {mono} font-size='14' font-weight='700' fill='{GREEN}'>"
              f"100% PROFIT HARVEST CAGE ({t['short_put']:,.0f}P TO {t['short_call']:,.0f}C = {t['cage']:,.0f} PTS WIDE)</text>"
              f"<text x='{X(t['short_put']):.1f}' y='{H - B + 18}' text-anchor='middle' {mono} font-size='13' font-weight='700' fill='{RED}'>SHORT {t['short_put']:,.0f}P</text>"
              f"<text x='{X(t['short_call']):.1f}' y='{H - B + 18}' text-anchor='middle' {mono} font-size='13' font-weight='700' fill='{RED}'>SHORT {t['short_call']:,.0f}C</text>"
              f"<text x='{X(t['anchor']):.1f}' y='{H - B + 18}' text-anchor='middle' {mono} font-size='13' font-weight='700' fill='{YELLOW}'>CENTER {t['anchor']:,.0f}</text>"
              f"<text x='{X(t['put_trigger']) + 4:.1f}' y='{H - B - 6}' {mono} font-size='12' fill='{AMBER}'>defend {t['put_trigger']:,.0f}</text>"
              f"<text x='{X(t['call_trigger']) - 4:.1f}' y='{H - B - 6}' text-anchor='end' {mono} font-size='12' fill='{AMBER}'>defend {t['call_trigger']:,.0f}</text>"
              f"<text x='{L - 6}' y='{Y(y_hi) + 4:.1f}' text-anchor='end' {mono} font-size='12' fill='{GREEN}'>+{y_hi:.2f}</text>"
              f"<text x='{L - 6}' y='{Y(y_lo) + 4:.1f}' text-anchor='end' {mono} font-size='12' fill='{RED}'>−{-y_lo:.2f}</text>")
    spot_svg = ""
    if spot is not None:
        sx = X(spot)
        spot_svg = (f"<line x1='{sx:.1f}' x2='{sx:.1f}' y1='{T}' y2='{H - B}' stroke='#e5e7eb' stroke-width='2'/>"
                    f"<circle cx='{sx:.1f}' cy='{Y(pay['max_gain']):.1f}' r='6' fill='#e5e7eb' stroke='{GREEN}' stroke-width='2'/>"
                    f"<text x='{sx + 8:.1f}' y='{T + 14}' {mono} font-size='13' font-weight='700' fill='#e5e7eb'>SPX {spot:,.2f}</text>")
    return (f"<svg viewBox='0 0 {W} {H}' width='100%' preserveAspectRatio='xMidYMid meet' style='display:block'>{cage}{lines}"
            f"<path d='{path}' fill='none' stroke='{GREEN}' stroke-width='3' stroke-linejoin='round'/>{spot_svg}{labels}</svg>")


def wing(kind: str, t: Dict, leg: Optional[Dict], dfn: Optional[Dict], c19_txt: str) -> str:
    up = kind == "call"
    col = RED if up else GREEN
    sh, lg, trig = (t["short_call"], t["long_call"], t["call_trigger"]) if up else (t["short_put"], t["long_put"], t["put_trigger"])
    cp = "C" if up else "P"
    live = ""
    if leg and leg.get("credit") is not None:
        live = (f"<div class='az-side'>mid credit ≈ <b class='az-mono'>{leg['credit']:.2f}</b> · max loss ${leg['max_loss_per_contract']:,.0f}/ct · "
                f"<b>{leg['contracts_1r']}</b> ct inside {c19_txt}</div>")
    elif leg is not None:
        live = "<div class='az-side'>no live mids for these strikes (chain unavailable or not listed)</div>"
    st_ = ""
    if dfn and dfn.get(kind):
        d = dfn[kind]
        st_ = (f"<span class='az-tag' style='float:right;color:{RED if d['hit'] else GREEN};background:color-mix(in srgb,{RED if d['hit'] else GREEN} 14%,transparent)'>"
               + (f"DEFEND NOW · {abs(d['to_short']):.1f} TO SHORT" if d["hit"] else f"SAFE · {d['dist']:.1f} PTS TO TRIGGER") + "</span>")
    return (f"<div class='az-wing' style='border-left-color:{col}'>{st_}<div class='w1' style='color:{col}'>{'Upper wing — bear call credit spread' if up else 'Lower wing — bull put credit spread'}</div>"
            f"<div class='w2'>SELL {sh:,.0f}{cp} / BUY {lg:,.0f}{cp}</div><div class='w3'><b style='color:{AMBER}'>5-Pt Defense Trigger:</b> roll/exit if SPX touches "
            f"<b class='az-mono'>{trig:,.0f}</b></div>{live}</div>")


def flow_bar(flow: Optional[Dict], label: str) -> str:
    if not flow:
        return f"<div class='az-s' style='margin-top:8px'>Opening options flow: {esc(label)}</div>"
    cp = flow["call_pct"]
    return (f"<div style='margin-top:12px;border-top:1px solid var(--az-line);padding-top:10px'><div style='display:grid;grid-template-columns:1fr auto 1fr;gap:8px;font:700 .8rem Inter,sans-serif'>"
            f"<span style='color:{GREEN}'>CALL FLOW: ${flow['calls_usd'] / 1e6:,.1f}M ({cp:.0f}%)<br><span class='az-s'>{flow['calls_ct']:,}x</span></span>"
            f"<span class='az-mono' style='text-align:center'>NET:<br>{flow['net_usd'] / 1e6:+,.1f}M</span>"
            f"<span style='color:{RED};text-align:right'>PUT FLOW: ${flow['puts_usd'] / 1e6:,.1f}M ({100 - cp:.0f}%)<br><span class='az-s'>{flow['puts_ct']:,}x</span></span></div>"
            f"<div class='az-flow'><span style='width:{cp:.1f}%;background:{GREEN}'></span><span style='width:{100 - cp:.1f}%;background:{RED}'></span></div>"
            f"<div class='az-s' style='margin-top:5px'>{esc(label)}</div></div>")


def _dchip(lbl: str, d: Dict) -> str:
    col = RED if d["hit"] else AMBER if d["dist"] <= 10 else GREEN
    txt = "DEFEND NOW" if d["hit"] else f"{d['dist']:.1f} pts to trigger"
    return f"<span class='az-chip' style='border-color:{col};color:{col}'>{esc(lbl)} · {txt}</span>"


def meic_rules_card(t: Dict, dfn: Dict, vix_now: Optional[float], rc: Optional[Dict], live: bool) -> str:
    """Execution & defense rules: the regime mandate, the 5-Point Defense Law with live distances, the regime-flip
    monitor and (Balanced) Azraël's post-11:30 range-condor test."""
    reg_col = {1: GREEN, 2: AMBER, 3: RED}[t["regime"]] if t["allowed"] else RED
    mand = (f"<div class='az-li first'><b style='color:{reg_col}'>Regime Mandate:</b> {esc(t['mandate'])}</div>"
            f"<div class='az-s' style='margin:-2px 0 6px 12px'>{esc(t['mandate_source'])}</div>")
    if t.get("wide_alt"):
        wc, wp = t["wide_alt"]["call"], t["wide_alt"]["put"]
        mand += (f"<div class='az-li'>If you sell in Negative Gamma: one side only, 15–20 wide — e.g. SELL {wc[0]:,.0f}C / BUY {wc[1]:,.0f}C "
                 f"or SELL {wp[0]:,.0f}P / BUY {wp[1]:,.0f}P, size 0.5R.</div>")
    law = (f"<div class='az-li'><b style='color:{AMBER}'>5-Point Defense Law:</b> if SPX comes within 5 pts of either short strike "
           f"(<span class='az-mono'>{t['put_trigger']:,.0f}</span> or <span class='az-mono'>{t['call_trigger']:,.0f}</span>), roll out 1 day and 5 pts wider "
           f"({t['roll_put'][0]:,.0f}/{t['roll_put'][1]:,.0f}P · {t['roll_call'][0]:,.0f}/{t['roll_call'][1]:,.0f}C) or exit immediately.</div>")
    live_d = ""
    if live and dfn.get("spot") is not None:
        sp_lbl = f"{t['short_put']:,.0f}P"
        sc_lbl = f"{t['short_call']:,.0f}C"
        live_d = (f"<div class='az-chips'><span class='az-chip'>SPX {dfn['spot']:,.2f}</span>{_dchip(sp_lbl, dfn['put'])}"
                  f"{_dchip(sc_lbl, dfn['call'])}</div>")
    flip = ""
    if vix_now is not None:
        if t["vix"] <= 18.5:
            gap_ = 18.5 - vix_now
            col = RED if gap_ < 0 else AMBER if gap_ <= 0.5 else GREEN
            flip = (f"<div class='az-li'><b style='color:{col}'>Regime flip monitor:</b> VIX now {vix_now:.2f} (08:15 print {t['vix']:.2f}) · "
                    + ("ABOVE 18.5 — close the entire condor at market" if gap_ < 0 else f"{gap_:.2f} below the 18.5 flip") + "</div>")
        else:
            flip = f"<div class='az-li'><b style='color:{RED}'>Negative Gamma since 08:15:</b> VIX now {vix_now:.2f}. Condors stay banned all session.</div>"
    rc_html = ""
    if rc is not None and t["regime"] == 2 and t["allowed"]:
        vcol = {"CONFIRMED": GREEN, "ON TRACK": AMBER, "BUILDING": AMBER, "FAILED": RED, "NOT CONFIRMED": RED, "WAITING": GREY}.get(rc["verdict"], GREY)
        rows = "".join(f"<div class='az-tt' style='grid-template-columns:1.2rem 1fr'><span class='{'az-ok' if c['ok'] and not c.get('warn') else 'az-mid' if (c['ok'] or c.get('pending')) else 'az-no'}'>"
                       f"{'✓' if c['ok'] else '…' if c.get('pending') else '✗'}</span><span><b>{esc(c['name'])}</b> · <span class='az-s'>{esc(c['note'])}</span></span></div>" for c in rc["checks"])
        rc_html = (f"<div class='az-panel' style='margin-top:10px'><div class='az-ph'><span>Post-11:30 range condor test</span>"
                   f"<span class='r' style='color:{vcol}'>{esc(rc['verdict'])}</span></div>{rows}<div class='az-s' style='margin-top:6px'>{esc(rc['detail'])} · "
                   f"Azraël's criteria for a range condor after 11:30 (#live-desk-talk).</div></div>")
    return (f"<div class='az-card'><div class='az-ph' style='margin-bottom:6px'><span>Execution &amp; defense rules</span>"
            f"<span class='r' style='color:{reg_col}'>{esc(t['regime_pill'])}</span></div><div class='az-li'>{esc(t['hold'])}</div>"
            f"{mand}{law}{live_d}{flip}{rc_html}"
            + foot("<b>Size strictly via Workstation Row 29</b> (1% max account risk) × the regime factor.", "Azraël Desk • credit-spread vault rules")
            + "</div>")


def meic_card(s, t: Dict, pay: Dict, priced: Optional[Dict], dfn: Dict, flow: Optional[Dict], flow_label: str, live: bool) -> str:
    reg_col = {1: GREEN, 2: AMBER, 3: RED}[t["regime"]]
    sub = (f"{esc(t['basis'])} • VIX: {t['vix']:.2f} • 10-Point Defined-Risk Wings" + ("" if live else " • ticket posts at 09:50"))
    head_html = head(pill("09:50 MEIC CONDOR DESK" if live else "MEIC TICKET · PENDING 09:50", "" if live else "slate"),
                     "Post-discovery iron condor & credit spread blueprint", sub, status(t["regime_pill"], reg_col))
    c19_txt = f"{t['size_factor']:.2f}R"
    left = (f"<div class='az-panel'><div class='az-ph'><span>MEIC expiration payoff structure &amp; safe harvest zone</span>"
            f"<span class='r' style='color:{GREEN}'>{'LIVE MIDS' if not pay['schematic'] else 'SCHEMATIC (no mids)'}</span></div>"
            f"{payoff_svg(t, pay, dfn.get('spot'))}</div>")
    legs = priced or {}
    right = (f"<div class='az-panel'><div class='az-ph'><span>Exact 4-leg order ticket &amp; defense triggers</span><span class='r' style='color:{VIOLET}'>10-WIDE WINGS</span></div>"
             f"{wing('call', t, legs.get('call') if priced else None, dfn, c19_txt)}{wing('put', t, legs.get('put') if priced else None, dfn, c19_txt)}"
             + (f"<div class='az-side'>Condor credit ≈ <b class='az-mono'>{priced['condor']['credit']:.2f}</b> · max loss ${priced['condor']['max_loss_per_contract']:,.0f}/ct · "
                f"<b>{priced['condor']['contracts']}</b> ct inside {c19_txt} (${priced['risk_budget']:,.0f})</div>" if priced and priced.get("condor") else "")
             + flow_bar(flow, flow_label) + "</div>")
    return (f"<div class='az-card'>{head_html}<div class='az-cols' style='grid-template-columns:minmax(0,1.35fr) minmax(0,1fr)'>{left}{right}</div>"
            + foot(f"<b>How to Execute:</b> keep price inside {t['short_put']:,.0f}P and {t['short_call']:,.0f}C to harvest 100% of credit. "
                   f"Never hold a tested wing within 5 points without rolling.", "Azraël Desk • #meic-condor-desk") + "</div>")
