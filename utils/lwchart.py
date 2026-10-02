"""
lwchart.py — TradingView Lightweight Charts embedded in Streamlit.

White price line (Capital.com SPX500, 24 h), the map as TradingView-style price lines, the session clock as markers,
an ARMED trigger level drawn thick when a play is armed, and entry / stop / target lines plus a trigger marker when a
trade is live. The time axis is linear through 16:05 because every minute of the window is reserved as whitespace
(Lightweight Charts otherwise collapses empty time).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd

STYLE = {"solid": 0, "dotted": 1, "dashed": 2, "largedashed": 3, "sparsedotted": 4}
THEME = {
    "dark": {"bg": "#0e1117", "text": "#a0a0a0", "grid": "#1a2a4a", "border": "#263653", "line": "#ffffff", "proxy": "#c9a227"},
    "light": {"bg": "#ffffff", "text": "#5b6672", "grid": "#e3e7ec", "border": "#d4dae2", "line": "#111827", "proxy": "#a07f00"},
}
TRADE_COL = {"entry": "#4cc9ff", "stop": "#ef5350", "target": "#26a69a", "armed": "#ffd600"}


def _ts(t: pd.Timestamp) -> int:
    """UNIX seconds shifted by the ET offset so Lightweight Charts (which draws UTC) shows New York time."""
    off = t.utcoffset().total_seconds() if t.utcoffset() is not None else 0
    return int(t.timestamp() + off)


def _series(df: Optional[pd.DataFrame], candles: bool) -> List[Dict]:
    if df is None or df.empty:
        return []
    out, seen = [], set()
    for ts, r in df.iterrows():
        t = _ts(ts)
        if t in seen:
            continue
        seen.add(t)
        if candles:
            out.append({"time": t, "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"])})
        else:
            out.append({"time": t, "value": float(r["close"])})
    return out


def build(spx: Optional[pd.DataFrame], proxy: Optional[pd.DataFrame], levels: List[Dict], window: Tuple[datetime, datetime],
          markers: List[Tuple[datetime, str]], theme: str = "dark", candles: bool = False, height: int = 540,
          anchor: float = 0.0, lo: float = 0.0, hi: float = 0.0, proxy_name: str = "proxy", candle_alpha: float = 0.7,
          armed: Optional[List[Dict]] = None, trade: Optional[Dict] = None) -> str:
    """armed: [{"price", "title"}] — trigger levels of armed plays. trade: {"entry","stop","target","time"(datetime),
    "label"} — the live/finished trade."""
    th = THEME.get(theme, THEME["dark"])
    f_dt, t_dt = window
    f_s, t_s = _ts(pd.Timestamp(f_dt)), _ts(pd.Timestamp(t_dt))
    # frame series: whitespace every minute keeps the axis linear; two extreme points force the price scale to hold the map
    frame: Dict[int, Dict] = {}
    t = f_s - (f_s % 60)
    while t <= t_s:
        frame[t] = {"time": t}
        t += 60
    frame[f_s - (f_s % 60)] = {"time": f_s - (f_s % 60), "value": lo}
    frame[f_s - (f_s % 60) + 60] = {"time": f_s - (f_s % 60) + 60, "value": hi}
    mk = []
    for dt, text in markers:
        s = _ts(pd.Timestamp(dt)); s -= s % 60
        if f_s < s < t_s:
            frame[s] = {"time": s, "value": anchor}
            mk.append({"time": s, "position": "inBar", "color": th["text"], "shape": "square", "size": 0.6, "text": text})
    frame_list = [frame[k] for k in sorted(frame)]
    spx_data = _series(spx, candles)
    trade_js = None
    if trade:
        tt = _ts(pd.Timestamp(trade["time"])) if trade.get("time") is not None else None
        if tt is not None:
            tt -= tt % 60
        trade_js = {"entry": trade.get("entry"), "stop": trade.get("stop"), "target": trade.get("target"), "time": tt,
                    "label": trade.get("label", "trade"), "side": trade.get("side", "long"), "done": bool(trade.get("done"))}
    up, dn = f"rgba(30,144,255,{candle_alpha:g})", f"rgba(255,0,255,{candle_alpha:g})"
    data = {"theme": th, "candles": candles, "height": height, "from": f_s, "to": t_s, "frame": frame_list, "markers": mk,
            "up": up, "dn": dn, "spx": spx_data, "proxy": _series(proxy, False), "levels": levels, "proxyName": proxy_name,
            "armed": armed or [], "trade": trade_js, "tc": TRADE_COL}
    payload = json.dumps(data)
    return f"""
<div id="wrap" style="position:relative;width:100%;height:{height}px;background:{th['bg']};border-radius:6px;overflow:hidden;">
  <div id="chart" style="width:100%;height:100%;"></div>
  <div id="legend" style="position:absolute;top:8px;left:10px;font:11px 'IBM Plex Mono',monospace;color:{th['text']};z-index:5;pointer-events:none;"></div>
  <div id="armedbox" style="position:absolute;top:8px;right:120px;z-index:6;pointer-events:none;display:none;
       font:12px 'IBM Plex Mono',monospace;color:#ffd600;border:2px solid #ffd600;border-radius:6px;padding:6px 10px;background:rgba(14,17,23,0.85);"></div>
</div>
<style>@keyframes pulse {{ 0%{{box-shadow:0 0 0 0 rgba(255,214,0,0.7)}} 70%{{box-shadow:0 0 0 10px rgba(255,214,0,0)}} 100%{{box-shadow:0 0 0 0 rgba(255,214,0,0)}} }}
#armedbox.on {{ display:block; animation: pulse 1.6s infinite; }}</style>
<script src="https://unpkg.com/lightweight-charts@4.2.1/dist/lightweight-charts.standalone.production.js"></script>
<script>
const D = {payload};
const el = document.getElementById('chart');
const chart = LightweightCharts.createChart(el, {{
  layout: {{ background: {{ type: 'solid', color: D.theme.bg }}, textColor: D.theme.text, fontFamily: "'IBM Plex Mono', monospace", fontSize: 11 }},
  grid: {{ vertLines: {{ color: D.theme.grid }}, horzLines: {{ color: D.theme.grid }} }},
  rightPriceScale: {{ borderColor: D.theme.border, scaleMargins: {{ top: 0.06, bottom: 0.06 }} }},
  timeScale: {{ borderColor: D.theme.border, timeVisible: true, secondsVisible: false, rightOffset: 2 }},
  crosshair: {{ mode: 0 }},
  handleScroll: true, handleScale: true,
}});
const frame = chart.addLineSeries({{ color: 'rgba(0,0,0,0)', lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }});
frame.setData(D.frame);
if (D.markers.length) frame.setMarkers(D.markers);
D.levels.forEach(l => frame.createPriceLine({{ price: l.price, color: l.color, lineWidth: l.width || 1, lineStyle: l.style, axisLabelVisible: true, title: l.title }}));
D.armed.forEach(a => frame.createPriceLine({{ price: a.price, color: D.tc.armed, lineWidth: 3, lineStyle: 2, axisLabelVisible: true, title: '⚡ ARMED · ' + a.title }}));
if (D.armed.length) {{ const b = document.getElementById('armedbox'); b.textContent = '⚡ ARMED — ' + D.armed.map(a => a.title + ' @ ' + a.price.toFixed(0)).join(' · ') + ' — wait for the qualifying 5-min close'; b.className = 'on'; }}
if (D.trade) {{
  const T = D.trade;
  if (T.entry != null) frame.createPriceLine({{ price: T.entry, color: D.tc.entry, lineWidth: 2, lineStyle: 0, axisLabelVisible: true, title: 'ENTRY ' + T.label }});
  if (T.stop != null) frame.createPriceLine({{ price: T.stop, color: D.tc.stop, lineWidth: 2, lineStyle: 2, axisLabelVisible: true, title: 'STOP (5-min close)' }});
  if (T.target != null) frame.createPriceLine({{ price: T.target, color: D.tc.target, lineWidth: 2, lineStyle: 2, axisLabelVisible: true, title: 'TARGET' }});
}}
if (D.proxy.length) {{
  const px = chart.addLineSeries({{ color: D.theme.proxy, lineWidth: 1, lineStyle: 1, priceLineVisible: false, lastValueVisible: true, title: D.proxyName }});
  px.setData(D.proxy);
}}
let main = null;
if (D.spx.length) {{
  if (D.candles) {{
    main = chart.addCandlestickSeries({{ upColor: D.up, downColor: D.dn, borderVisible: true, borderUpColor: D.up, borderDownColor: D.dn,
                                         wickUpColor: D.up, wickDownColor: D.dn }});
  }} else {{
    main = chart.addLineSeries({{ color: D.theme.line, lineWidth: 2, priceLineVisible: true, lastValueVisible: true, title: 'SPX' }});
  }}
  main.setData(D.spx);
  if (D.trade && D.trade.time != null) {{
    const times = D.spx.map(p => p.time);
    let best = times[0], bd = Math.abs(times[0] - D.trade.time);
    times.forEach(tm => {{ const d = Math.abs(tm - D.trade.time); if (d < bd) {{ bd = d; best = tm; }} }});
    const long = D.trade.side === 'long';
    main.setMarkers([{{ time: best, position: long ? 'belowBar' : 'aboveBar', color: D.tc.entry, shape: long ? 'arrowUp' : 'arrowDown', size: 2,
                        text: D.trade.label + (D.trade.done ? ' · done' : '') }}]);
  }}
}}
chart.timeScale().setVisibleRange({{ from: D.from, to: D.to }});
const legend = document.getElementById('legend');
chart.subscribeCrosshairMove(p => {{
  if (!p || !p.time) {{ legend.textContent = ''; return; }}
  const d = new Date(p.time * 1000);
  const hh = String(d.getUTCHours()).padStart(2,'0'), mm = String(d.getUTCMinutes()).padStart(2,'0');
  let txt = hh + ':' + mm + ' ET';
  if (main) {{ const v = p.seriesData.get(main); if (v) txt += '   SPX ' + (v.value !== undefined ? v.value : v.close).toFixed(2); }}
  legend.textContent = txt;
}});
new ResizeObserver(() => chart.applyOptions({{ width: el.clientWidth, height: el.clientHeight }})).observe(el);
</script>
"""
