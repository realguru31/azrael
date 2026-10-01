# Azraël Desk — the 1-Trade-Per-Day SPX execution workstation on Streamlit

Automates *AZRAEL_OPTIONS_SPX_Premarket_Workstation.xlsx* (Tab 1 cell for cell, Tab 2 journal) and the daily desk
workflow of *The Vault Official Member Execution Manual* and the Discord knowledge base — 08:30 math, strike grid,
scenario map, trade card, execution clock, credit-spread grid, 16:15 settlement audit with the hindsight rules replay.

## Pages
| Page | What it does |
|---|---|
| Desk | status bar (SPX, C6, C7, EM, regime, lock state), phase clock with countdowns, levels, live 5-minute chart with shelves/nodes/fences and the gate/execution shading, gap protocol (C10 from the 09:30 open), the 09:50 test, live archetype scanner, today's card |
| Premarket math | every workstation cell C5–C46, sizing ladder (1R/0.75R/0.5R/XSP), 08:33 desk-bot cross-check, the bot's Strike Grid post reproduced (SPX, SPY, /ES, fences, beyond-0DTE), node map over live CBOE open interest, the book's OI King Node, micro desk (XSP/SPY), 08:45 stop clusters |
| Scenario & trade card | A/B/C If/Then map generated from the locked math in the desk's format; trade card builder (Archetype · Trigger · Invalidation · 1R cap) with sizing and instrument rules; Watch Day; lock before 09:25 |
| Credit spread vault | MEIC blueprint strikes and the ±1.25 EM fences, live mids from CBOE, (width − credit) × 100 sizing, regime protocol, 5-point test and regime-flip alarms, expiry ladder |
| Trade journal | Tab 2 columns and dropdown lists exactly, header formulas (total, net PnL, win rate, avg R, discipline score), CSV import/export, optional Google Sheets mirror, R by setup/regime/hour |
| Settlement audit | the 04:15 audit text in the desk format, chart replica, four settlement questions, saved history and 20-session statistics |
| Desk knowledge | laws, SOP, archetype cards, regimes, credit rules, risk table, case studies |

## Data
* **tvDatafeed** (anonymous; optional login in secrets): SPX, SPY, QQQ, VIX (08:15 print), /ES (08:20 price, drift vs settle), 1- and 5-minute bars, daily closes.
* **CBOE delayed quotes** (free): SPX/SPXW chain with open interest, volume, IV and greeks → OI King Node, air-pocket check, MEIC mids.
* Optional **Barchart** live chain (`data/barchart.py`) if you maintain WAF cookies — see the docstring.
* Spot never comes from the chain vendor.

## The lock
C5/C6/C7 are frozen at 08:30 ET. Tier 1: GitHub Actions writes `store/baseline/<date>.json` at 08:31 (survives reboots).
Tier 2: the first app load after 08:30 writes the same file. Tier 3: before 08:30 the numbers are provisional and say so.
C8, C9, C27, C28 and C10 are re-applied to the locked inputs whenever you change them.

## Deploy on Streamlit Community Cloud
1. Push this folder to a **new** GitHub repo (one app per repo). Keep `store/*/.gitkeep`.
2. Settings → Actions → General → Workflow permissions → **Read and write** (the bots commit the lock and the audit).
3. share.streamlit.io → New app → main file `app.py` → Advanced: **Python 3.11**. Paste `.streamlit/secrets.toml.example` values if you use them.
4. After any dependency change: Manage app → **Reboot** (pulling code does not reinstall).
5. Add repo secrets `TV_USERNAME` / `TV_PASSWORD` if you want the CI workers to use your TradingView login.

Local: `pip install -r requirements.txt && streamlit run app.py`. Offline demo: `AZRAEL_DEMO=1 streamlit run app.py`.
Tests: `python tests/test_core.py` — every worked example from the manual, the workbook and the desk bot posts.

## Conventions worth knowing
* King Nodes on the Desk/Scenario pages are the **desk bot's** parametric nodes (±0.5 EM rounded to 5-point strikes); the workbook's C43/C44 use 0.52 and are shown on the Premarket page; the book's OI definition is computed from the live chain and shown alongside.
* Two fence conventions are shown in the vault: the MEIC blueprint (one strike beyond the rounded Strike Wall) and the bot's ±1.25 EM fences.
* Rules replay is mechanical and measured on the index (5-minute closes), exactly like the desk audit — not fills.
