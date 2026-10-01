"""
charts.py — Plotly builders. Colours follow the desk's own charts: walls dotted blue, 0.5 shelves dashed orange,
anchor solid grey, King Nodes dotted purple, fences dotted yellow, discovery gate red shade, execution window
green shade, 11:30 shutdown dash-dot.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go

from utils.timeutil import ET

BG = "#0d1117"
GRID = "#1d2733"
COL = {"wall": "#3d8bff", "shelf": "#ff9d2e", "anchor": "#a7b1bd", "node": "#b06cff", "fence": "#ffd75e",
       "gate": "rgba(192,57,43,0.25)", "exec": "rgba(30,158,106,0.18)", "dead": "rgba(90,100,112,0.15)",
       "spot": "#f4f6f8", "call": "#3d8bff", "put": "#ff5c8a", "up": "#1e9e6a", "dn": "#c0392b"}


def _t(d: date, hh: int, mm: int) -> datetime:
    return datetime.combine(d, time(hh, mm), tzinfo=ET)


def _base_layout(fig: go.Figure, height: int, title: str = "") -> go.Figure:
    if title:
        fig.update_layout(title=dict(text=title, font=dict(size=13, color="#d7dde3")))
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG, height=height,
        margin=dict(t=44 if title else 16, b=36, l=54, r=16), font=dict(size=11, color="#c6ccd3"),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, font=dict(size=10),
                    bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(gridcolor=GRID, showgrid=True), yaxis=dict(gridcolor=GRID, showgrid=True, tickformat=",.0f"),
        hovermode="x unified",
    )
    return fig


def session_chart(bars: pd.DataFrame, session: date, levels: Dict[str, float], nodes: Dict[str, float],
                  fences: Optional[Dict[str, float]] = None, gap_levels: Optional[Dict[str, float]] = None,
                  replay: Optional[Dict] = None, settlement: Optional[float] = None, spot: Optional[float] = None,
                  extra_lines: Optional[List[Dict]] = None, height: int = 560, title: str = "") -> go.Figure:
    fig = go.Figure()
    x0, x1 = _t(session, 9, 30), _t(session, 16, 0)
    # shaded windows
    fig.add_vrect(x0=x0, x1=_t(session, 9, 50), fillcolor=COL["gate"], line_width=0, layer="below",
                  annotation_text="09:30–09:50 gate", annotation_position="top left", annotation_font_size=10)
    fig.add_vrect(x0=_t(session, 9, 50), x1=_t(session, 11, 30), fillcolor=COL["exec"], line_width=0, layer="below",
                  annotation_text="execution window", annotation_position="top left", annotation_font_size=10)
    fig.add_vrect(x0=_t(session, 11, 30), x1=x1, fillcolor=COL["dead"], line_width=0, layer="below")
    fig.add_vline(x=_t(session, 11, 30), line=dict(color="#8a97a6", dash="dashdot", width=1),
                  annotation_text="11:30 shutdown", annotation_font_size=10, annotation_position="top right")
    fig.add_vline(x=_t(session, 11, 5), line=dict(color="#5c6470", dash="dot", width=1),
                  annotation_text="11:05 last qualifying bar", annotation_font_size=9, annotation_position="bottom right")
    fig.add_vline(x=_t(session, 10, 15), line=dict(color="#5c6470", dash="dot", width=1),
                  annotation_text="10:15 primary window", annotation_font_size=9, annotation_position="bottom left")

    def hline(y, color, dash, name, width=1.4):
        fig.add_shape(type="line", x0=x0, x1=x1, y0=y, y1=y, line=dict(color=color, dash=dash, width=width), layer="above")
        fig.add_annotation(x=x1, y=y, text=f"{name} {y:,.2f}", showarrow=False, xanchor="left", font=dict(size=10, color=color),
                           bgcolor="rgba(13,17,23,0.85)")

    hline(levels["C13"], COL["wall"], "dot", "+1.0 wall C13")
    hline(levels["C14"], COL["shelf"], "dash", "+0.5 shelf C14")
    hline(levels["C15"], COL["anchor"], "solid", "anchor C15", 1.8)
    hline(levels["C16"], COL["shelf"], "dash", "−0.5 shelf C16")
    hline(levels["C17"], COL["wall"], "dot", "−1.0 wall C17")
    if nodes:
        hline(nodes["call_node"], COL["node"], "dot", "call node")
        hline(nodes["put_node"], COL["node"], "dot", "put node")
    if fences:
        hline(fences["call_fence"], COL["fence"], "dot", "call fence")
        hline(fences["put_fence"], COL["fence"], "dot", "put fence")
    if gap_levels:
        for k, nm in (("c39", "gap anchor C39"), ("c41", "+0.5 intraday C41"), ("c42", "−0.5 intraday C42")):
            hline(gap_levels[k], "#c084fc", "longdash", nm, 1.2)
    for ln in extra_lines or []:
        hline(ln["y"], ln.get("color", "#9aa0a6"), ln.get("dash", "dot"), ln["name"], ln.get("width", 1))

    if bars is not None and not bars.empty:
        fig.add_trace(go.Scatter(x=bars.index.to_pydatetime(), y=bars["close"].tolist(), mode="lines",
                                 line=dict(color=COL["spot"], width=1.8), name="SPX cash, 5-minute closes"))
    if replay and replay.get("qualified"):
        t_in = _t(session, *map(int, replay["trigger_time"].split(":")))
        fig.add_trace(go.Scatter(x=[t_in], y=[replay["entry"]], mode="markers+text",
                                 marker=dict(color="#4cc9ff", size=11, symbol="circle"), name="replay entry",
                                 text=[f"A{replay['archetype']} {'long' if replay['side'] == 'long' else 'short'} {replay['entry']:.2f}"],
                                 textposition="top center", textfont=dict(size=10, color="#4cc9ff")))
        fig.add_shape(type="line", x0=t_in, x1=x1, y0=replay["stop"], y1=replay["stop"],
                      line=dict(color="#ff5c5c", dash="dash", width=1))
        fig.add_shape(type="line", x0=t_in, x1=x1, y0=replay["target"], y1=replay["target"],
                      line=dict(color="#4ade80", dash="dash", width=1))
        if replay.get("exit_time") and replay.get("exit_price") is not None:
            t_out = _t(session, *map(int, replay["exit_time"].split(":")))
            col = "#4ade80" if (replay.get("pnl_pts") or 0) > 0 else "#ff5c5c"
            fig.add_trace(go.Scatter(x=[t_out], y=[replay["exit_price"]], mode="markers+text",
                                     marker=dict(color=col, size=11, symbol="x"), name="replay exit",
                                     text=[f"{replay['resolution'].upper()} {replay['exit_price']:.2f} ({replay['r_multiple']:+.2f}R)"],
                                     textposition="bottom center", textfont=dict(size=10, color=col)))
    if settlement is not None:
        fig.add_trace(go.Scatter(x=[x1], y=[settlement], mode="markers+text", marker=dict(color="#ffd75e", size=12),
                                 name="settlement", text=[f"SETTLEMENT {settlement:.2f}"], textposition="middle left",
                                 textfont=dict(size=10, color="#ffd75e")))
    elif spot is not None:
        fig.add_annotation(x=x1, y=spot, text=f"last {spot:,.2f}", showarrow=False, xanchor="right",
                           font=dict(size=10, color=COL["spot"]))
    _base_layout(fig, height, title)
    fig.update_xaxes(range=[_t(session, 9, 25), _t(session, 16, 5)], tickformat="%H:%M")
    return fig


def node_map(levels: Dict[str, float], sg: Dict[str, float], oi_profile: Optional[pd.DataFrame] = None,
             height: int = 300, title: str = "MODEL NODE MAP (WORKSTATION EM MODEL)") -> go.Figure:
    """The bot's illustrative node map; if a real chain is available the bars are actual open interest."""
    fig = go.Figure()
    if oi_profile is not None and not oi_profile.empty:
        fig.add_trace(go.Bar(x=oi_profile["strike"], y=oi_profile["c_oi"], name="call OI (CBOE)", marker_color=COL["call"], opacity=0.85))
        fig.add_trace(go.Bar(x=oi_profile["strike"], y=-oi_profile["p_oi"], name="put OI (CBOE)", marker_color=COL["put"], opacity=0.85))
        fig.update_layout(barmode="overlay")
        ytitle = "open interest (puts negative)"
    else:
        import numpy as np
        xs = np.arange(levels["C17"] - 40, levels["C13"] + 45, 5)
        cw = np.exp(-((xs - sg["call_node"]) / 18) ** 2) * (xs > levels["C15"])
        pw = np.exp(-((xs - sg["put_node"]) / 18) ** 2) * (xs < levels["C15"])
        fig.add_trace(go.Bar(x=xs, y=cw, name="call node profile (model shape)", marker_color=COL["call"]))
        fig.add_trace(go.Bar(x=xs, y=-pw, name="put node profile (model shape)", marker_color=COL["put"]))
        fig.update_layout(barmode="overlay")
        ytitle = "illustrative node weight (not measured OI)"
    for y, c, d, n in ((levels["C15"], COL["anchor"], "solid", "anchor"), (levels["C14"], COL["shelf"], "dash", "+0.5"),
                       (levels["C16"], COL["shelf"], "dash", "−0.5"), (levels["C13"], COL["wall"], "dot", "+1.0"),
                       (levels["C17"], COL["wall"], "dot", "−1.0"), (sg["call_fence"], COL["fence"], "dot", "call fence"),
                       (sg["put_fence"], COL["fence"], "dot", "put fence"), (sg["call_node"], COL["node"], "dot", "call node"),
                       (sg["put_node"], COL["node"], "dot", "put node")):
        fig.add_vline(x=y, line=dict(color=c, dash=d, width=1.2), annotation_text=n, annotation_font_size=9,
                      annotation_position="top")
    _base_layout(fig, height, title)
    fig.update_yaxes(title=ytitle, tickformat=",.0f")
    fig.update_xaxes(title="SPX strike level", tickformat=",.0f")
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
        fig.add_vline(x=spot, line=dict(color="#ffd75e", dash="dash", width=1), annotation_text=f"spot {spot:,.0f}",
                      annotation_font_size=9, annotation_position="top")
    _base_layout(fig, height, "Net gamma exposure per strike — the Archetype 4 air-pocket check")
    fig.update_xaxes(tickformat=",.0f")
    return fig


def r_history_chart(audits: List[Dict], height: int = 260) -> Optional[go.Figure]:
    rows = [(a["session"], a["replay"]["r_multiple"], a["replay"]["archetype"]) for a in audits
            if a.get("replay") and a["replay"].get("r_multiple") is not None]
    if not rows:
        return None
    rows.sort()
    fig = go.Figure()
    fig.add_trace(go.Bar(x=[r[0] for r in rows], y=[r[1] for r in rows],
                         marker_color=[COL["up"] if r[1] > 0 else COL["dn"] for r in rows],
                         text=[f"A{r[2]}" for r in rows], textposition="outside", name="replay R"))
    fig.add_hline(y=0, line=dict(color="#5c6470", width=1))
    _base_layout(fig, height, "Rules-replay R by session (hindsight, index points)")
    return fig
