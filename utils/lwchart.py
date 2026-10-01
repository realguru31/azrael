"""
lwchart.py — TradingView Lightweight Charts (open-source JS library) embedded in Streamlit.

Why: a white price line with the levels as TradingView-style price lines (labels on the price axis) is what the desk's
charts look like, and the library renders pre-market, RTH and the empty hours of the night in one time scale.
Times are shifted to New York so the axis reads ET.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

STYLE = {"solid": 0, "dotted": 1, "dashed": 2, "largedashed": 3, "sparsedotted": 4}
THEME = {
    "dark": {"bg": "#0e1117", "text": "#a0a0a0", "grid": "#1a2a4a", "border": "#263653", "line": "#ffffff", "proxy": "#c9a227"},
    "light": {"bg": "#ffffff", "text": "#5b6672", "grid": "#e3e7ec", "border": "#d4dae2", "line": "#111827", "proxy": "#a07f00"},
}


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
          anchor: float = 0.0, lo: float = 0.0, hi: float = 0.0, proxy_name: str = "proxy") -> str:
    th = THEME.get(theme, THEME["dark"])
    f_dt, t_dt = window
    f_s, t_s = _ts(pd.Timestamp(f_dt)), _ts(pd.Timestamp(t_dt))
    # invisible frame series: fixes the visible time range and forces the price scale to include the whole map
    frame = [{"time": f_s, "value": lo}, {"time": f_s + 60, "value": hi}]
    mk = []
    for dt, text in markers:
        s = _ts(pd.Timestamp(dt))
        if f_s + 60 < s < t_s:
            frame.append({"time": s, "value": anchor})
            mk.append({"time": s, "position": "inBar", "color": th["text"], "shape": "square", "size": 0.6, "text": text})
    frame.append({"time": t_s, "value": anchor})
    frame = sorted({p["time"]: p for p in frame}.values(), key=lambda p: p["time"])
    data = {
        "theme": th, "candles": candles, "height": height, "from": f_s, "to": t_s, "frame": frame, "markers": mk,
        "spx": _series(spx, candles), "proxy": _series(proxy, False), "levels": levels, "proxyName": proxy_name,
    }
    payload = json.dumps(data)
    return f"""
<div id="wrap" style="position:relative;width:100%;height:{height}px;background:{th['bg']};border-radius:6px;overflow:hidden;">
  <div id="chart" style="width:100%;height:100%;"></div>
  <div id="legend" style="position:absolute;top:8px;left:10px;font:11px 'IBM Plex Mono',monospace;color:{th['text']};z-index:5;pointer-events:none;"></div>
</div>
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
if (D.proxy.length) {{
  const px = chart.addLineSeries({{ color: D.theme.proxy, lineWidth: 1, lineStyle: 1, priceLineVisible: false, lastValueVisible: true, title: D.proxyName }});
  px.setData(D.proxy);
}}
let main = null;
if (D.spx.length) {{
  if (D.candles) {{
    main = chart.addCandlestickSeries({{ upColor: 'rgba(30,144,255,0.3)', downColor: 'rgba(255,0,255,0.3)', borderVisible: true,
                                         borderUpColor: 'rgba(30,144,255,0.3)', borderDownColor: 'rgba(255,0,255,0.3)',
                                         wickUpColor: 'rgba(30,144,255,0.3)', wickDownColor: 'rgba(255,0,255,0.3)' }});
  }} else {{
    main = chart.addLineSeries({{ color: D.theme.line, lineWidth: 2, priceLineVisible: true, lastValueVisible: true, title: 'SPX' }});
  }}
  main.setData(D.spx);
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
