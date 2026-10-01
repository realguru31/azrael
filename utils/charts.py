"""
charts.py — Plotly builders. Theme-aware (dark palette from the SPX gamma dashboard: #0e1117 / #16213e / #1a2a4a,
calls #1e90ff, puts #ff00ff, highlight #ffd600). Every figure gets an explicit date axis and a y-range derived from
the levels, so the provisional map renders at 02:00 with no bars at all.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go

from utils.timeutil import ET

THEMES = {
    "dark": {"bg": "#0e1117", "panel": "#16213e", "grid": "#1a2a4a", "text": "#e0e0e0", "muted": "#a0a0a0",
             "spot": "#f4f6f8", "template": "plotly_dark", "annot_bg": "rgba(14,17,23,0.85)"},
    "light": {"bg": "#ffffff", "panel": "#f3f5f8", "grid": "#e3e7ec", "text": "#1f2937", "muted": "#5b6672",
              "spot": "#111827", "template": "plotly_white", "annot_bg": "rgba(255,255,255,0.85)"},
}
COL = {"wall": "#3d8bff", "shelf": "#ff9d2e", "anchor": "#9aa4b0", "node": "#b06cff", "fence": "#ffd600",
       "gate": "rgba(192,57,43,0.22)", "exec": "rgba(30,158,106,0.16)", "dead": "rgba(120,130,140,0.12)",
       "call": "#1e90ff", "put": "#ff00ff", "up": "#26a69a", "dn": "#ef5350", "es": "#c9a227", "entry": "#4cc9ff"}
_T = THEMES["dark"]


def set_theme(name: str) -> None:
    global _T
    _T = THEMES.get(name, THEMES["dark"])


def _t(d: date, hh: int, mm: int) -> datetime:
    return datetime.combine(d, time(hh, mm), tzinfo=ET)


def _layout(fig: go.Figure, height: int, title: str = "") -> go.Figure:
    if title:
        fig.update_layout(title=dict(text=title, font=dict(size=13, color=_T["text"]), x=0.01))
    fig.update_layout(template=_T["template"], paper_bgcolor=_T["bg"], plot_bgcolor=_T["bg"], height=height,
                      margin=dict(t=46 if title else 18, b=36, l=58, r=110), font=dict(size=11, color=_T["muted"]),
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, font=dict(size=10),
                                  bgcolor="rgba(0,0,0,0)"), hovermode="x unified",
                      xaxis=dict(gridcolor=_T["grid"], showgrid=True, zeroline=False, color=_T["muted"]),
                      yaxis=dict(gridcolor=_T["grid"], showgrid=True, zeroline=False, tickformat=",.0f", color=_T["muted"]))
    return fig


def session_chart(bars: pd.DataFrame, session: date, levels: Dict[str, float], nodes: Dict[str, float],
                  fences: Optional[Dict[str, float]] = None, gap_levels: Optional[Dict[str, float]] = None,
                  replay: Optional[Dict] = None, settlement: Optional[float] = None, spot: Optional[float] = None,
                  extra_lines: Optional[List[Dict]] = None, height: int = 560, title: str = "",
                  candles: bool = False, overnight: Optional[pd.DataFrame] = None, show_premarket: bool = False) -> go.Figure:
    """SPX session chart. `bars` = today's 5-minute bars (may be empty). `overnight` = /ES bars already converted to
    SPX points (basis-adjusted) for the pre-market context."""
    fig = go.Figure()
    x0, x1 = _t(session, 9, 30), _t(session, 16, 0)
    start = _t(session, 4, 0) if show_premarket else _t(session, 9, 25)
    end = _t(session, 16, 5)

    # ── shaded windows and clock lines
    fig.add_vrect(x0=x0, x1=_t(session, 9, 50), fillcolor=COL["gate"], line_width=0, layer="below")
    fig.add_vrect(x0=_t(session, 9, 50), x1=_t(session, 11, 30), fillcolor=COL["exec"], line_width=0, layer="below")
    fig.add_vrect(x0=_t(session, 11, 30), x1=x1, fillcolor=COL["dead"], line_width=0, layer="below")
    for hh, mm, txt, dash in ((9, 30, "09:30 open", "dot"), (9, 50, "09:50 gate", "dot"), (10, 15, "10:15", "dot"),
                              (11, 5, "11:05 last bar", "dot"), (11, 30, "11:30 shutdown", "dashdot")):
        fig.add_vline(x=_t(session, hh, mm), line=dict(color=_T["muted"], dash=dash, width=1))
        fig.add_annotation(x=_t(session, hh, mm), y=1.0, yref="paper", text=txt, showarrow=False, yanchor="bottom",
                           font=dict(size=9, color=_T["muted"]))

    # ── horizontal levels (shapes + right-edge annotations)
    ys: List[float] = []

    def hline(y, color, dash, name, width=1.4):
        if y is None:
            return
        ys.append(float(y))
        fig.add_shape(type="line", x0=start, x1=end, y0=y, y1=y, line=dict(color=color, dash=dash, width=width), layer="above")
        fig.add_annotation(x=end, y=y, text=f"{name} {y:,.2f}", showarrow=False, xanchor="left", xshift=4,
                           font=dict(size=10, color=color), bgcolor=_T["annot_bg"])

    hline(levels["C13"], COL["wall"], "dot", "+1.0 wall C13")
    hline(levels["C14"], COL["shelf"], "dash", "+0.5 shelf C14")
    hline(levels["C15"], COL["anchor"], "solid", "anchor C15", 1.8)
    hline(levels["C16"], COL["shelf"], "dash", "−0.5 shelf C16")
    hline(levels["C17"], COL["wall"], "dot", "−1.0 wall C17")
    if nodes:
        hline(nodes.get("call_node"), COL["node"], "dot", "call node")
        hline(nodes.get("put_node"), COL["node"], "dot", "put node")
    if fences:
        hline(fences.get("call_fence"), COL["fence"], "dot", "call fence")
        hline(fences.get("put_fence"), COL["fence"], "dot", "put fence")
    if gap_levels:
        for k, nm in (("c39", "gap anchor C39"), ("c41", "+0.5 intraday C41"), ("c42", "−0.5 intraday C42")):
            hline(gap_levels.get(k), "#c084fc", "longdash", nm, 1.2)
    for ln in extra_lines or []:
        hline(ln.get("y"), ln.get("color", _T["muted"]), ln.get("dash", "dot"), ln["name"], ln.get("width", 1))

    # ── price
    lows, highs = [], []
    if overnight is not None and not overnight.empty:
        ov = overnight[(overnight.index >= start) & (overnight.index < x0)]
        if not ov.empty:
            fig.add_trace(go.Scatter(x=ov.index.to_pydatetime(), y=ov["close"].tolist(), mode="lines",
                                     line=dict(color=COL["es"], width=1.3, dash="dot"), name="/ES overnight, basis-adjusted to SPX"))
            lows.append(float(ov["low"].min())); highs.append(float(ov["high"].max()))
    if bars is not None and not bars.empty:
        if candles:
            fig.add_trace(go.Candlestick(x=bars.index.to_pydatetime(), open=bars["open"], high=bars["high"], low=bars["low"],
                                         close=bars["close"], name="SPX 5-minute",
                                         increasing_line_color="rgba(30,144,255,0.7)", decreasing_line_color="rgba(255,0,255,0.7)",
                                         increasing_fillcolor="rgba(30,144,255,0.7)", decreasing_fillcolor="rgba(255,0,255,0.7)"))
        else:
            fig.add_trace(go.Scatter(x=bars.index.to_pydatetime(), y=bars["close"].tolist(), mode="lines",
                                     line=dict(color=_T["spot"], width=1.8), name="SPX cash, 5-minute closes"))
        lows.append(float(bars["low"].min())); highs.append(float(bars["high"].max()))

    # an invisible anchor trace forces a date axis even with no bars, so the shapes above always render
    fig.add_trace(go.Scatter(x=[start, end], y=[levels["C15"], levels["C15"]], mode="lines",
                             line=dict(color="rgba(0,0,0,0)", width=0.1), hoverinfo="skip", showlegend=False))

    # ── replay markers
    if replay and replay.get("qualified"):
        t_in = _t(session, *map(int, replay["trigger_time"].split(":")))
        fig.add_trace(go.Scatter(x=[t_in], y=[replay["entry"]], mode="markers+text",
                                 marker=dict(color=COL["entry"], size=11), name="replay entry",
                                 text=[f"A{replay['archetype']} {replay['side']} {replay['entry']:.2f}"], textposition="top center",
                                 textfont=dict(size=10, color=COL["entry"])))
        fig.add_shape(type="line", x0=t_in, x1=x1, y0=replay["stop"], y1=replay["stop"], line=dict(color=COL["dn"], dash="dash", width=1))
        fig.add_shape(type="line", x0=t_in, x1=x1, y0=replay["target"], y1=replay["target"], line=dict(color=COL["up"], dash="dash", width=1))
        ys += [replay["stop"], replay["target"]]
        if replay.get("exit_time") and replay.get("exit_price") is not None:
            t_out = _t(session, *map(int, replay["exit_time"].split(":")))
            col = COL["up"] if (replay.get("pnl_pts") or 0) > 0 else COL["dn"]
            fig.add_trace(go.Scatter(x=[t_out], y=[replay["exit_price"]], mode="markers+text", marker=dict(color=col, size=11, symbol="x"),
                                     name="replay exit", text=[f"{replay['resolution'].upper()} {replay['exit_price']:.2f} ({replay['r_multiple']:+.2f}R)"],
                                     textposition="bottom center", textfont=dict(size=10, color=col)))
    if settlement is not None:
        fig.add_trace(go.Scatter(x=[x1], y=[settlement], mode="markers+text", marker=dict(color=COL["fence"], size=12), name="settlement",
                                 text=[f"SETTLEMENT {settlement:.2f}"], textposition="middle left", textfont=dict(size=10, color=COL["fence"])))
        ys.append(settlement)
    elif spot is not None:
        fig.add_annotation(x=end, y=spot, text=f"last {spot:,.2f}", showarrow=False, xanchor="right", yshift=10,
                           font=dict(size=10, color=_T["spot"]))

    # ── axes: explicit date type and a y-range that always contains the map
    em = abs(levels["C13"] - levels["C15"]) or 10.0
    lo = min(ys + lows) - 0.15 * em
    hi = max(ys + highs) + 0.15 * em
    _layout(fig, height, title)
    fig.update_xaxes(type="date", range=[start, end], tickformat="%H:%M")
    fig.update_yaxes(range=[lo, hi])
    fig.update_layout(xaxis_rangeslider_visible=False)
    return fig


def node_map(levels: Dict[str, float], sg: Dict[str, float], oi_profile: Optional[pd.DataFrame] = None,
             height: int = 300, title: str = "MODEL NODE MAP (WORKSTATION EM MODEL)") -> go.Figure:
    fig = go.Figure()
    if oi_profile is not None and not oi_profile.empty:
        fig.add_trace(go.Bar(x=oi_profile["strike"], y=oi_profile["c_oi"], name="call OI (CBOE)", marker_color=COL["call"], opacity=0.85))
        fig.add_trace(go.Bar(x=oi_profile["strike"], y=-oi_profile["p_oi"], name="put OI (CBOE)", marker_color=COL["put"], opacity=0.85))
        ytitle = "open interest (puts negative)"
    else:
        import numpy as np
        xs = np.arange(levels["C17"] - 40, levels["C13"] + 45, 5)
        cw = np.exp(-((xs - sg["call_node"]) / 18) ** 2) * (xs > levels["C15"])
        pw = np.exp(-((xs - sg["put_node"]) / 18) ** 2) * (xs < levels["C15"])
        fig.add_trace(go.Bar(x=xs, y=cw, name="call node profile (model shape)", marker_color=COL["call"]))
        fig.add_trace(go.Bar(x=xs, y=-pw, name="put node profile (model shape)", marker_color=COL["put"]))
        ytitle = "illustrative node weight (not measured OI)"
    fig.update_layout(barmode="overlay")
    for y, c, d, n in ((levels["C15"], COL["anchor"], "solid", "anchor"), (levels["C14"], COL["shelf"], "dash", "+0.5"),
                       (levels["C16"], COL["shelf"], "dash", "−0.5"), (levels["C13"], COL["wall"], "dot", "+1.0"),
                       (levels["C17"], COL["wall"], "dot", "−1.0"), (sg["call_fence"], COL["fence"], "dot", "call fence"),
                       (sg["put_fence"], COL["fence"], "dot", "put fence"), (sg["call_node"], COL["node"], "dot", "call node"),
                       (sg["put_node"], COL["node"], "dot", "put node")):
        fig.add_vline(x=y, line=dict(color=c, dash=d, width=1.2))
        fig.add_annotation(x=y, y=1.0, yref="paper", text=n, showarrow=False, yanchor="bottom", font=dict(size=9, color=c))
    _layout(fig, height, title)
    fig.update_yaxes(title=ytitle, tickformat=",.0f")
    fig.update_xaxes(title="SPX strike level", tickformat=",.0f", range=[levels["C17"] - 45, levels["C13"] + 45])
    return fig


def gex_chart(prof: pd.DataFrame, levels: Dict[str, float], spot: Optional[float], height: int = 300) -> go.Figure:
    fig = go.Figure()
    if prof is not None and not prof.empty:
        colors = [COL["call"] if v >= 0 else COL["put"] for v in prof["net_gex"]]
        fig.add_trace(go.Bar(x=prof["strike"], y=prof["net_gex"], marker_color=colors, name="net dealer GEX (CBOE OI × gamma × 100)"))
    for k, c, d in (("C13", COL["wall"], "dot"), ("C14", COL["shelf"], "dash"), ("C15", COL["anchor"], "solid"),
                    ("C16", COL["shelf"], "dash"), ("C17", COL["wall"], "dot")):
        fig.add_vline(x=levels[k], line=dict(color=c, dash=d, width=1))
    if spot:
        fig.add_vline(x=spot, line=dict(color=COL["fence"], dash="dash", width=1))
    _layout(fig, height, "Net gamma exposure per strike — the Archetype 4 air-pocket check")
    fig.update_xaxes(tickformat=",.0f")
    return fig


def r_history_chart(audits: List[Dict], height: int = 260) -> Optional[go.Figure]:
    rows = [(a["session"], a["replay"]["r_multiple"], a["replay"]["archetype"]) for a in audits
            if a.get("replay") and a["replay"].get("r_multiple") is not None]
    if not rows:
        return None
    rows.sort()
    fig = go.Figure()
    fig.add_trace(go.Bar(x=[r[0] for r in rows], y=[r[1] for r in rows], marker_color=[COL["up"] if r[1] > 0 else COL["dn"] for r in rows],
                         text=[f"A{r[2]}" for r in rows], textposition="outside", name="replay R"))
    fig.add_hline(y=0, line=dict(color=_T["muted"], width=1))
    _layout(fig, height, "Rules-replay R by session (hindsight, index points)")
    return fig
