"""
app.py — AZRAËL DESK · the 1-Trade-Per-Day SPX execution workstation on Streamlit.

Run locally:   streamlit run app.py          (AZRAEL_DEMO=1 streamlit run app.py  for synthetic data, no network)
Deploy:        Streamlit Community Cloud, Python 3.11, main file app.py — see README.md
"""
from __future__ import annotations

import logging

import streamlit as st

st.set_page_config(page_title="Azraël Desk — SPX 1-Trade-Per-Day Workstation", page_icon="🜂", layout="wide",
                   initial_sidebar_state="expanded")
logging.basicConfig(level=logging.INFO)

from views import common as U                       # noqa: E402
from views import desk, premarket, scenario_view, credit_view, journal_view, audit_view, knowledge   # noqa: E402

U.setup()
U.configure_storage()
cfg = U.settings()

if cfg["auto"]:
    @st.fragment(run_every=cfg["poll"])
    def _tick():
        pass
    _tick()

plan, label = U.get_plan(cfg)


def _page(fn):
    def run():
        fn(cfg, plan, label)
    return run


pages = [
    st.Page(_page(desk.render), title="Desk", icon="🖥️", default=True, url_path="desk"),
    st.Page(_page(premarket.render), title="Premarket math", icon="📐", url_path="premarket"),
    st.Page(_page(scenario_view.render), title="Scenario & trade card", icon="🗺️", url_path="scenario"),
    st.Page(_page(credit_view.render), title="Credit spread vault", icon="🏦", url_path="credit"),
    st.Page(_page(journal_view.render), title="Trade journal", icon="📓", url_path="journal"),
    st.Page(_page(audit_view.render), title="Settlement audit", icon="🧾", url_path="audit"),
    st.Page(_page(knowledge.render), title="Desk knowledge", icon="📚", url_path="knowledge"),
]
st.navigation(pages, position="sidebar").run()
