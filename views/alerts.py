"""alerts.py — the desk's alert system, on every page.

Why the old alerts failed (1.2.0 – 1.7.2):
  • they lived inside the Desk page's fragment, so nothing fired while another page was open;
  • the live engine read the 5-minute bar that was still forming, so a half-built bar could 'trigger' or 'stop', then
    vanish on the next poll (ACTIVE ↔ ARMED flicker, alerts for trades that never were) — fixed in core/live.py;
  • S3 counted as ARMED whenever price was within 10 pts of its box edge — nearly always — and every flap re-alerted;
  • the beep created a new AudioContext inside a fresh zero-height iframe on each alert; that iframe never had a user
    gesture, so browsers kept it suspended (no sound); notifications were requested the same way (never granted);
  • the first state after a page load was swallowed, and dedupe was by state name only.

Now: a watcher fragment in the sidebar (every page) computes the shared live snapshot, turns NEW facts into alerts
(core/alerts.py: keyed per occurrence, stale facts skipped on page open, ARMED cooldown), and hands them to one engine
installed in the app window (not in a throw-away iframe): Web Audio unlocked by your first click anywhere, desktop
notifications allowed from a real click on 'Enable', cards that stay on screen, tab-title flash, per-day dedupe in
localStorage so a reload or a second tab never repeats an alert."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Dict, List

import streamlit as st

from core import alerts as AL
from utils.timeutil import minutes_of, now_et, session_date, T_GATE_END
from views import cards as K
from views import common as U

logger = logging.getLogger(__name__)
ENGINE_VER = "1.8.0"

# The engine body runs with W = the Streamlit app window. Injected as a <script> into the app document so its functions,
# timers and listeners belong to the app window and survive Streamlit reruns (component iframes come and go).
_ENGINE_BODY = r"""
var TOP = W; try { if (W.top && W.top.document) { TOP = W.top; } } catch (e) { TOP = W; }
if (W.__azrael && W.__azrael.ver === '__VER__') { return; }
var A = W.__azrael = W.__azrael || {};
A.ver = '__VER__'; A.mem = A.mem || {};
function ac(create) {
  try {
    if (!A.ctx && create) { var C = TOP.AudioContext || TOP.webkitAudioContext || W.AudioContext || W.webkitAudioContext; if (C) { A.ctx = new C(); } }
    if (A.ctx && A.ctx.state === 'suspended') { A.ctx.resume(); }
  } catch (e) {}
  return A.ctx || null;
}
A.unlock = function () { var c = ac(true); try { if (c) { var o = c.createOscillator(), g = c.createGain(); g.gain.value = 0.00001; o.connect(g); g.connect(c.destination); o.start(); o.stop(c.currentTime + 0.03); } } catch (e) {} return !!(c && c.state === 'running'); };
A.audio = function () { return A.ctx ? A.ctx.state : 'locked'; };
var TONES = { trigger: [[660, 0, .14], [880, .15, .14], [1320, .30, .42]], exit: [[1320, 0, .14], [990, .15, .14], [660, .30, .42]],
  armed: [[988, 0, .10], [988, .18, .10]], info: [[784, 0, .22]], defense: [[1180, 0, .11], [1180, .17, .11], [1180, .34, .11], [620, .52, .42, 'triangle']],
  test: [[660, 0, .12], [990, .14, .22]] };
A.beep = function (kind) {
  var c = ac(true); if (!c) { return false; }
  var seq = TONES[kind] || TONES.info, t0 = c.currentTime + 0.03, v = (kind === 'armed' || kind === 'info') ? 0.12 : 0.2;
  seq.forEach(function (s) { try { var o = c.createOscillator(), g = c.createGain(); o.type = s[3] || 'sine'; o.frequency.setValueAtTime(s[0], t0 + s[1]);
    g.gain.setValueAtTime(0.0001, t0 + s[1]); g.gain.exponentialRampToValueAtTime(v, t0 + s[1] + 0.015); g.gain.exponentialRampToValueAtTime(0.0001, t0 + s[1] + s[2]);
    o.connect(g); g.connect(c.destination); o.start(t0 + s[1]); o.stop(t0 + s[1] + s[2] + 0.05); } catch (e) {} });
  return c.state === 'running';
};
if (!A.listening) {
  A.listening = true;
  var h = function () { A.unlock(); };
  ['pointerdown', 'keydown', 'touchstart'].forEach(function (ev) {
    try { W.document.addEventListener(ev, h, true); } catch (e) {}
    try { if (TOP !== W) { TOP.document.addEventListener(ev, h, true); } } catch (e) {}
  });
}
A.N = function () { try { return TOP.Notification || W.Notification || null; } catch (e) { return W.Notification || null; } };
A.perm = function () { var N = A.N(); return N ? N.permission : 'unsupported'; };
A.ask = function (cb) {
  var N = A.N(); if (!N) { if (cb) { cb('unsupported'); } return; }
  try { var p = N.requestPermission(function (r) { if (cb) { cb(r); } }); if (p && p.then) { p.then(function (r) { if (cb) { cb(r); } }); } }
  catch (e) { if (cb) { cb(N.permission); } }
};
A.notify = function (title, body, tag) {
  var N = A.N(); if (!N || N.permission !== 'granted') { return false; }
  try { var n = new N(title, { body: body, tag: tag, renotify: true }); n.onclick = function () { try { TOP.focus(); W.focus(); } catch (e) {} n.close(); }; return true; }
  catch (e) { return false; }
};
A.flash = function (text) {
  try {
    if (A._fl) { clearInterval(A._fl); }
    var docs = [W.document]; if (TOP !== W) { docs.push(TOP.document); }
    var base = docs.map(function (d) { return d.title; }), n = 0;
    A._fl = setInterval(function () {
      n++; docs.forEach(function (d, i) { d.title = (n % 2) ? text : base[i]; });
      var focused = false; try { focused = TOP.document.hasFocus() && TOP.document.visibilityState === 'visible'; } catch (e) {}
      if (n > 60 || (focused && n > 8)) { clearInterval(A._fl); A._fl = null; docs.forEach(function (d, i) { d.title = base[i]; }); }
    }, 900);
  } catch (e) {}
};
function etTime(d) { try { return d.toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }); } catch (e) { return d.toLocaleTimeString(); } }
function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
var GRAD = { trigger: 'linear-gradient(90deg,#10b981,#0ea5e9)', exit: 'linear-gradient(90deg,#0ea5e9,#6366f1)', armed: 'linear-gradient(90deg,#f59e0b,#ea580c)',
  info: 'linear-gradient(90deg,#0ea5e9,#6366f1)', defense: 'linear-gradient(90deg,#ef4444,#be123c)', none: 'linear-gradient(90deg,#8b5cf6,#6366f1)' };
A.style = function () {
  if (W.document.getElementById('az-alert-style')) { return; }
  var s = W.document.createElement('style'); s.id = 'az-alert-style';
  s.textContent = '#az-alerts{position:fixed;bottom:18px;right:18px;width:min(430px,calc(100vw - 36px));max-height:calc(100vh - 90px);overflow:hidden;z-index:999999;display:flex;flex-direction:column-reverse;gap:10px;pointer-events:none;}'
    + '.az-al{pointer-events:auto;background:#0f1629;color:#e5e7eb;border:1px solid #22304d;border-left:5px solid #38bdf8;border-radius:12px;padding:11px 14px 12px;'
    + 'box-shadow:0 12px 32px rgba(0,0,0,.45);font-family:Inter,"IBM Plex Sans",system-ui,sans-serif;transition:opacity .5s,transform .5s;animation:azin .35s ease-out;}'
    + '.az-al.major{box-shadow:0 0 0 2px rgba(255,255,255,.08),0 14px 36px rgba(0,0,0,.55);}'
    + '.az-al.fade{opacity:0;transform:translateX(20px);}'
    + '.az-al-top{display:flex;justify-content:space-between;align-items:center;gap:8px;}'
    + '.az-al-pill{display:inline-block;padding:4px 10px;border-radius:6px;color:#fff;font:700 11px "JetBrains Mono",ui-monospace,monospace;letter-spacing:.07em;}'
    + '.az-al-x{background:none;border:none;color:#94a3b8;font-size:16px;cursor:pointer;padding:0 2px;line-height:1;}'
    + '.az-al-title{font-weight:800;font-size:15px;text-transform:uppercase;margin-top:7px;letter-spacing:.01em;}'
    + '.az-al-body{font-size:13px;color:#cbd5e1;margin-top:4px;line-height:1.4;}'
    + '.az-al-time{font:600 11px "JetBrains Mono",ui-monospace,monospace;color:#94a3b8;margin-top:6px;}'
    + '@keyframes azin{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:none}}';
  W.document.head.appendChild(s);
};
A.card = function (ev) {
  try {
    A.style();
    var box = W.document.getElementById('az-alerts');
    if (!box) { box = W.document.createElement('div'); box.id = 'az-alerts'; W.document.body.appendChild(box); }
    var c = W.document.createElement('div'); c.className = 'az-al' + (ev.major ? ' major' : '');
    c.style.borderLeftColor = ev.accent || '#38bdf8';
    var now = new Date();
    c.innerHTML = '<div class="az-al-top"><span class="az-al-pill" style="background:' + (GRAD[ev.tone] || GRAD.info) + '">' + esc(ev.pill) + '</span>'
      + '<button class="az-al-x" title="Dismiss">✕</button></div><div class="az-al-title">' + esc(ev.title) + '</div>'
      + '<div class="az-al-body">' + esc(ev.body) + '</div><div class="az-al-time">' + esc(etTime(now)) + ' ET</div>';
    c.querySelector('.az-al-x').onclick = function () { c.remove(); };
    box.insertBefore(c, box.firstChild);
    while (box.children.length > 3) { box.removeChild(box.lastChild); }
    var life = ev.major ? 20 * 60000 : 45000;
    setTimeout(function () { try { c.classList.add('fade'); setTimeout(function () { c.remove(); }, 600); } catch (e) {} }, life);
  } catch (e) {}
};
function lsKey(day) { return 'azrael_alerts_' + day; }
function seenList(day) { try { return JSON.parse(W.localStorage.getItem(lsKey(day)) || '[]'); } catch (e) { return A.mem[day] || []; } }
function remember(day, key) {
  var s = seenList(day); if (s.indexOf(key) < 0) { s.push(key); } if (s.length > 400) { s = s.slice(-400); } A.mem[day] = s;
  try { W.localStorage.setItem(lsKey(day), JSON.stringify(s)); } catch (e) {}
}
try {                                   /* forget days older than a week */
  var cut = Date.now() - 7 * 864e5;
  for (var i = W.localStorage.length - 1; i >= 0; i--) { var k = W.localStorage.key(i);
    if (k && k.indexOf('azrael_alerts_') === 0) { var d = Date.parse(k.slice(14)); if (d && d < cut) { W.localStorage.removeItem(k); } } }
} catch (e) {}
A.fire = function (json) {
  var evs = []; try { evs = JSON.parse(json); } catch (e) { return; }
  evs.forEach(function (ev) {
    if (seenList(ev.day).indexOf(ev.key) >= 0) { return; }
    remember(ev.day, ev.key);
    A.card(ev);
    if (ev.flash) { A.flash(ev.flashText || ev.title); }
    if (ev.sound && ev.tone && ev.tone !== 'none') { A.beep(ev.tone); }
    if (ev.notify) { A.notify(ev.ntitle || ev.pill, ev.title + ' — ' + ev.body, ev.key); }
    try { if (ev.major && W.navigator.vibrate) { W.navigator.vibrate([180, 90, 180]); } } catch (e) {}
  });
};
A.test = function () {
  A.unlock();
  A.card({ pill: 'TEST ALERT', title: 'Alerts are armed', body: 'This is how a trigger arrives: a card that stays, a tone, a desktop notification and a flashing tab title.', accent: '#10b981', major: false, tone: 'trigger' });
  A.beep('trigger'); A.flash('🔔 TEST — Azraël Desk'); A.notify('Azraël Desk — test alert', 'Desktop notifications are on.', 'az-test');
};
"""

_INSTALL = """
var W; try { W = window.parent; void W.document.body; } catch (e) { W = window; }
function install() {
  if (W.__azrael && W.__azrael.ver === __VERJS__) { return; }
  try { var s = W.document.createElement('script'); s.textContent = '(function(W){' + __SRC__ + '})(window);'; W.document.head.appendChild(s); } catch (e) {}
  if (!(W.__azrael && W.__azrael.ver === __VERJS__)) { try { (new Function('W', __SRC__))(W); } catch (e2) {} }
}
install();
"""


def _install_js() -> str:
    body = _ENGINE_BODY.replace("__VER__", ENGINE_VER)
    src = json.dumps(body).replace("</", "<\\/")
    return _INSTALL.replace("__SRC__", src).replace("__VERJS__", json.dumps(ENGINE_VER))


def _enable_widget_html() -> str:
    th = U.THEME_VARS[U.theme_name()]
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>"
            f"body{{margin:0;background:transparent;font-family:'IBM Plex Sans',system-ui,sans-serif;color:{th['text']};}}"
            f"button{{width:100%;padding:8px 10px;border-radius:8px;border:1px solid {th['border']};background:linear-gradient(90deg,#0ea5e9,#6366f1);"
            f"color:#fff;font:700 13px 'IBM Plex Sans',system-ui,sans-serif;cursor:pointer;letter-spacing:.02em;}}"
            f"button.ok{{background:{th['panel2']};color:{th['text']};}}"
            f"#st{{font-size:12px;margin-top:6px;color:{th['muted']};line-height:1.35;}} b{{font-weight:700;}}"
            f"</style></head><body><button id='en'>🔔 Enable alerts</button><div id='st'>…</div>"
            f"<script>{_install_js()}"
            "var en = document.getElementById('en'), st = document.getElementById('st');"
            "function upd(){ var a = W.__azrael; var au = a ? a.audio() : 'locked'; var pm = a ? a.perm() : 'unsupported';"
            " var snd = au === 'running' ? \"<b style='color:#10b981'>on</b>\" : \"<b style='color:#f59e0b'>locked</b> (click Enable once)\";"
            " var dsk = pm === 'granted' ? \"<b style='color:#10b981'>allowed</b>\" : pm === 'denied' ? \"<b style='color:#ef4444'>blocked</b> (site settings)\" : pm === 'unsupported' ? 'n/a here' : \"<b style='color:#f59e0b'>not allowed yet</b>\";"
            " st.innerHTML = 'Sound ' + snd + ' · Desktop ' + dsk;"
            " var ready = au === 'running' && pm !== 'default';"
            " en.textContent = ready ? '✓ Alerts on — send a test' : '🔔 Enable alerts'; en.className = ready ? 'ok' : ''; }"
            "en.onclick = function(){ install(); var a = W.__azrael; if (!a) { return; } a.unlock();"
            " a.ask(function(r){ if (r === 'granted') { a.notify('Azraël Desk', 'Desktop notifications are on.', 'az-enable'); } upd(); });"
            " a.test(); upd(); };"
            "setInterval(upd, 1500); upd();"
            "</script></body></html>")


def _dispatch_html(payload: List[Dict]) -> str:
    ev = json.dumps(json.dumps(payload)).replace("</", "<\\/")
    return ("<script>" + _install_js() +
            f"var EV = {ev};"
            "function go(){ if (W.__azrael && W.__azrael.fire) { W.__azrael.fire(EV); return true; } return false; }"
            "if (!go()) { var n = 0; var iv = setInterval(function(){ if (go() || ++n > 40) { clearInterval(iv); } }, 250); }"
            "</script>")


def _payload(fire: List[AL.Event], cfg: Dict, day: str) -> List[Dict]:
    out = []
    for e in fire:
        d = e.as_dict()
        d.update({"day": day, "sound": bool(cfg.get("sound", True)) and e.tone != "none",
                  "notify": bool(cfg.get("notify", True)) and e.notify,
                  "flash": e.major or e.kind in ("armed", "gate", "stoprisk"), "flashText": f"{e.pill} — {e.title}",
                  "ntitle": f"Azraël Desk — {e.pill}"})
        out.append(d)
    return out


def evaluate(cfg: Dict, s) -> List[AL.Event]:
    """New alerts for this poll (updates the session's memory)."""
    if s is None or not s.ok or s.banner is None or not s.today:
        return []
    b = s.banner
    trade = b.trade if b.state in ("ACTIVE", "DONE") else None
    plays = b.plays if cfg.get("alert_armed", True) else []
    score = b.score if b.score else None
    facts = AL.desk_events(s.sess, s.now, b.state, trade, plays, s.last, s.gate, score,
                           s.ticket if s.m >= T_GATE_END else None, s.bar)
    if cfg.get("alert_meic", True):
        facts += AL.meic_events(s.sess, s.now, s.ticket, s.last, s.vix_now, s.plan["inputs"].get("c6"))
    seen = st.session_state.get("az_seen")
    poll = int(cfg.get("poll", 60) or 60)
    fire, seen2, armed_now = AL.select(facts, seen or {}, st.session_state.get("az_armed_prev", []), s.now,
                                       first_run=seen is None, fresh_s=max(300, 2 * poll))
    st.session_state["az_seen"] = seen2
    st.session_state["az_armed_prev"] = armed_now
    return fire


def watch(cfg: Dict) -> None:
    """Sidebar block on every page: live desk status, the alert dispatcher, recent alerts, and the Enable button."""
    from views import live as LV
    poll = cfg["poll"] if cfg.get("auto", True) else None
    live_cfg = dict(cfg)
    live_cfg["session"] = session_date()             # alerts always watch the live session, whatever date a page is browsing

    @st.fragment(run_every=poll)
    def _watch():
        s = None
        try:
            s = LV.snapshot(live_cfg)
        except Exception as e:                       # a feed hiccup must never take the sidebar down
            logger.warning("watcher snapshot failed: %s", e)
        st.markdown(K.mini_status(s), unsafe_allow_html=True)
        if s is not None and s.ok and s.ticket and s.today and s.m >= T_GATE_END and s.last is not None:
            t = s.ticket
            dc, dp = t["call_trigger"] - s.last, s.last - t["put_trigger"]
            col = "#ef4444" if min(dc, dp) <= 0 else "#f59e0b" if min(dc, dp) <= 10 else "#10b981"
            st.markdown(f"<div class='az-mini' style='border-left-color:{col}'><span class='t'>MEIC</span> {t['short_put']:,.0f}P / {t['short_call']:,.0f}C"
                        f" · to defense {dp:+.1f} / {dc:+.1f}</div>", unsafe_allow_html=True)
        try:
            fire = evaluate(cfg, s)
        except Exception as e:
            logger.warning("alert evaluation failed: %s", e)
            fire = []
        if fire:
            U.html_frame(_dispatch_html(_payload(fire, cfg, s.sess.isoformat())), height=1)
            log = st.session_state.setdefault("az_log", [])
            for e in fire:
                log.insert(0, f"{now_et():%H:%M} · {e.pill} — {e.title}")
            del log[6:]
        for line in st.session_state.get("az_log", [])[:4]:
            st.markdown(f"<div class='az-log'>{K.esc(line)}</div>", unsafe_allow_html=True)

    _watch()
    U.html_frame(_enable_widget_html(), height=76)
