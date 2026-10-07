"""
storage.py — what must survive a rerun or a reboot.

Streamlit Cloud's disk is ephemeral across reboots, so three tiers are used, like the skill's baseline pattern:
    1. files committed by GitHub Actions (store/baseline, store/audits) — survive reboots
    2. files written by the app itself (store/…) — survive reruns, not reboots
    3. session_state — the current browser session only
The journal (Tab 2) is a CSV with the workbook's exact twelve columns; it can be downloaded/uploaded and,
if `gsheets` secrets exist, mirrored to a Google Sheet so it survives reboots too.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from core.workstation import JOURNAL_COLUMNS

STORE = os.environ.get("AZRAEL_STORE", "store")
BASELINE_DIR = os.path.join(STORE, "baseline")
AUDIT_DIR = os.path.join(STORE, "audits")
JOURNAL_DIR = os.path.join(STORE, "journal")
JOURNAL_CSV = os.path.join(JOURNAL_DIR, "trade_journal.csv")
CARDS_JSON = os.path.join(JOURNAL_DIR, "trade_cards.json")

for d in (BASELINE_DIR, AUDIT_DIR, JOURNAL_DIR):
    os.makedirs(d, exist_ok=True)


# ── generic json ──────────────────────────────────────────────────────────────
def _read_json(path: str) -> Optional[Dict]:
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _write_json(path: str, obj: Dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=str)


# ── 08:30 lock (baseline) ─────────────────────────────────────────────────────
def baseline_path(session: str) -> str:
    return os.path.join(BASELINE_DIR, f"{session}.json")


def load_baseline(session: str) -> Optional[Dict]:
    return _read_json(baseline_path(session))


def save_baseline(session: str, plan: Dict) -> str:
    p = baseline_path(session)
    _write_json(p, plan)
    return p


# ── audits ────────────────────────────────────────────────────────────────────
def audit_path(session: str) -> str:
    return os.path.join(AUDIT_DIR, f"{session}.json")


def load_audit(session: str) -> Optional[Dict]:
    return _read_json(audit_path(session))


def save_audit(session: str, audit: Dict) -> str:
    p = audit_path(session)
    _write_json(p, audit)
    return p


def list_audits(limit: int = 60) -> List[Dict]:
    out = []
    for fn in sorted(os.listdir(AUDIT_DIR), reverse=True):
        if fn.endswith(".json"):
            a = _read_json(os.path.join(AUDIT_DIR, fn))
            if a:
                out.append(a)
        if len(out) >= limit:
            break
    return out


# ── trade cards ───────────────────────────────────────────────────────────────
def load_cards() -> Dict[str, Dict]:
    return _read_json(CARDS_JSON) or {}


def save_manual_exit(session: str, price: float, time_txt: str, note: str = "") -> None:
    cards = load_cards()
    c = cards.get(session) or {"session": session, "archetype": "", "text": ""}
    c["manual_exit"] = {"price": price, "time": time_txt, "note": note}
    save_card(session, c)


def save_card(session: str, card: Dict) -> None:
    cards = load_cards()
    cards[session] = card
    _write_json(CARDS_JSON, cards)


# ── journal (Tab 2) ───────────────────────────────────────────────────────────
def load_journal() -> pd.DataFrame:
    if os.path.exists(JOURNAL_CSV):
        try:
            df = pd.read_csv(JOURNAL_CSV, dtype=str).fillna("")
            for c in JOURNAL_COLUMNS:
                if c not in df.columns:
                    df[c] = ""
            return df[JOURNAL_COLUMNS]
        except Exception:
            pass
    return pd.DataFrame(columns=JOURNAL_COLUMNS)


def save_journal(df: pd.DataFrame) -> None:
    df = df.copy()
    for c in JOURNAL_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    df[JOURNAL_COLUMNS].to_csv(JOURNAL_CSV, index=False)
    _gsheets_push(df[JOURNAL_COLUMNS])


def append_journal(row: Dict) -> pd.DataFrame:
    df = load_journal()
    df = pd.concat([df, pd.DataFrame([{c: row.get(c, "") for c in JOURNAL_COLUMNS}])], ignore_index=True)
    save_journal(df)
    return df


def journal_stats(df: pd.DataFrame) -> Dict[str, float]:
    """Tab 2 header cells, formula for formula:
        B3 = COUNTA(B7:B500)           D3 = SUM(H7:H500)
        F3 = COUNTIF(H7:H500,">0")/COUNTA*100     H3 = AVERAGE(J7:J500)
        J3 = COUNTIF(K7:K500,"Yes")/COUNTA*100"""
    if df is None or df.empty:
        return {"total_trades": 0, "net_pnl": 0.0, "win_rate": 0.0, "avg_r": 0.0, "discipline": 0.0}
    dated = df[df["Date"].astype(str).str.strip() != ""]
    n = len(dated)
    pnl = pd.to_numeric(dated["PnL ($)"], errors="coerce")
    r = pd.to_numeric(dated["R-Multiple"], errors="coerce")
    return {
        "total_trades": n,
        "net_pnl": float(pnl.fillna(0).sum()),
        "win_rate": float((pnl > 0).sum() / n * 100) if n else 0.0,
        "avg_r": float(r.dropna().mean()) if r.notna().any() else 0.0,
        "discipline": float((dated["1-Trade Rule?"].astype(str).str.strip().str.lower() == "yes").sum() / n * 100) if n else 0.0,
    }


# ── optional Google Sheets mirror ─────────────────────────────────────────────
_gs_conf: Optional[Dict] = None


def configure_gsheets(conf: Optional[Dict]) -> None:
    """conf = {"service_account": {...json...}, "spreadsheet_key": "...", "worksheet": "Trade Journal"}"""
    global _gs_conf
    _gs_conf = conf or None


def _gsheets_push(df: pd.DataFrame) -> None:
    if not _gs_conf:
        return
    try:
        import gspread  # type: ignore
        gc = gspread.service_account_from_dict(_gs_conf["service_account"])
        sh = gc.open_by_key(_gs_conf["spreadsheet_key"])
        try:
            ws = sh.worksheet(_gs_conf.get("worksheet", "Trade Journal"))
        except Exception:
            ws = sh.add_worksheet(_gs_conf.get("worksheet", "Trade Journal"), rows=600, cols=len(JOURNAL_COLUMNS))
        ws.clear()
        ws.update([JOURNAL_COLUMNS] + df.astype(str).values.tolist())
    except Exception:
        pass


def gsheets_pull() -> Optional[pd.DataFrame]:
    if not _gs_conf:
        return None
    try:
        import gspread  # type: ignore
        gc = gspread.service_account_from_dict(_gs_conf["service_account"])
        ws = gc.open_by_key(_gs_conf["spreadsheet_key"]).worksheet(_gs_conf.get("worksheet", "Trade Journal"))
        vals = ws.get_all_values()
        if len(vals) < 2:
            return None
        df = pd.DataFrame(vals[1:], columns=vals[0])
        for c in JOURNAL_COLUMNS:
            if c not in df.columns:
                df[c] = ""
        return df[JOURNAL_COLUMNS]
    except Exception:
        return None
