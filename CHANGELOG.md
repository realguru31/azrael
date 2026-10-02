# Changelog
All notable changes to the Azraël Desk app. Format: Keep a Changelog; versions are semantic.

## [1.2.1] — 2026-10-02
### Fixed
- The chain source/reason was a module-wide variable shared by every page and session: rebuilding yesterday's map on the
  Settlement audit page (expired expiry → "HTTP 200 but no contracts for 2026-10-01") overwrote the note the Desk shows,
  producing a false "CHAIN NOT ON BARCHART" tag while the Desk's own chain was live. The source now travels with each
  chain result (`get_chain_with_source`); the Feeds line shows the source now and at lock.
- Files: `data/fetcher.py`, `core/plan.py`, `core/execution.py`, `views/common.py`, `views/desk.py`, `views/credit_view.py`, `views/premarket.py`.

## [1.2.0] — 2026-10-02
### Added
- Live fragments: the Desk, Credit vault and Premarket live blocks re-run on their own every poll interval and carry a
  "↻ Refresh now" button that re-pulls feeds for that block only. The previous auto-refresh was wired to an empty
  fragment and did not update the page.
- Alerts on banner state change (LOCKED, GATE, WATCHING, ARMED, ACTIVE, DONE, STAND DOWN): toast, flashing browser-tab
  title, optional two-tone beep and browser notification (sidebar toggles, `desk_settings.toml` keys `sound`, `notify`).
- Chart overlays: armed plays draw their trigger level as a thick pulsing line with an ARMED box; a live trade draws
  entry / stop / target lines and a marker on the trigger bar (TradingView and Plotly engines). Banner pulses while armed.
- Audit: Microstructure Lesson generated from the nearest miss on a Watch Day (desk style).
### Fixed
- Lightweight chart time axis collapsed empty time (10:58 → 16:00); every minute of the window is now reserved.
- Right-edge labels on the Plotly chart overprinted when levels sat within a point; now staggered.
- ACTIVE/DONE line shows the XSP/SPY size when SPX sizes to zero.
- Stale "CBOE" labels removed (credit heading, node-map title, chart legends, scenario and grid OI note, comments).
- Lock bot: retry crons at :41 and :56 UTC (guard skips once the lock exists).
### Files
- `views/desk.py`, `utils/lwchart.py`, `views/common.py`, `views/credit_view.py`, `views/premarket.py`, `app.py`,
  `core/execution.py`, `core/audit.py`, `utils/charts.py`, `core/scenario.py`, `utils/text.py`, `core/plan.py`,
  `.github/workflows/lock_0830.yml`, `desk_settings.example.toml`.

## [Unreleased]
### Investigate
- VIX 08:15 print convention — desk 16.32 vs app 16.30 (Oct 1), 16.11 vs 16.17 (Sep 30): bar open (08:15:00) vs close;
  decide after 3–5 sessions.
### Later
- Options chain page: OI and today's volume side by side per strike, shelves/nodes/fences across both, strike ladder
  with V/OI and net GEX; refreshes with the poll.

## [1.1.1] — 2026-10-01
### Changed
- Chart labels read "Call King Node / Put King Node" (desk definition, ±0.5 EM). The OI King Node (Barchart book) and the
  volume node (today's flow) are drawn on the Desk chart in cyan when the chain is available.
- Files: `views/desk.py`.

## [1.1.0] — 2026-10-01
### Added
- Volume King Node: the strike with today's largest combined 0DTE volume within ±1 EM (live-flow proxy, the Pine
  indicator's method), shown on the Premarket page next to the OI node; chain source and expiry stated there too.
- Feeds expander shows which cookie source Barchart is using (file path or URL) instead of the secret note.
- Files: `data/chain.py`, `core/plan.py`, `data/barchart.py`, `views/premarket.py`, `views/desk.py`.

## [1.0.5] — 2026-10-01
### Changed
- With no secrets set, the cookie loader now reads the public spxdash mint file
  (`raw.githubusercontent.com/realguru31/spxdash/main/data/session/cookies.json`) alongside this repo's own
  `data/session/cookies.json` and uses the freshest valid blob. Barchart works from the first poll via the proven job.
- Files: `data/barchart.py`.

## [1.0.4] — 2026-10-01
### Changed
- Cookie mint replaced by the working vs3d2 job verbatim: `scripts/mint_cookies.py` (stdlib + Playwright only) and
  `.github/workflows/barchart_cookies.yml` (same install lines, `permissions: contents: write`, commits
  `data/session/cookies.json`). The app's default cookie path is that file.
- Files: `scripts/mint_cookies.py`, `.github/workflows/barchart_cookies.yml`, `data/barchart.py`, `data/session/.gitkeep`, `scripts/release.py`.

## [1.0.3] — 2026-10-01
### Changed
- Barchart cookie loader ported from the working vs3d2 app: `BC_COOKIES_JSON` secret → `BC_COOKIE_URL` (+`BC_COOKIE_TOKEN`,
  `?v=` cache-bust) → disk (`store/session`, `data/session`, `data/baseline`), paths anchored to the app folder; every
  failing source explains itself in the Feeds line. `baseLastPrice` added to the field set. Streamlit secrets are exported
  to the environment for the fetch layer.
- Files: `data/barchart.py`, `views/common.py`, `.streamlit/secrets.toml.example`.

## [1.0.2] — 2026-10-01
### Added
- Barchart cookies can be supplied through Streamlit secrets (`[barchart] cookies_json`), e.g. minted in Colab with
  `tools/colab_barchart_check.py`, which now prints the exact secret to paste. The newer of secret vs repo cookies wins.
  The Feeds expander reports which was used.
- Files: `views/common.py`, `views/desk.py`, `tools/colab_barchart_check.py`, `.streamlit/secrets.toml.example`.

## [1.0.1] — 2026-10-01
### Fixed
- Plotly chart (fallback engine) drew no price: it received the SPX cash 5-minute bars (empty before 09:30) instead of the
  CAPITALCOM:SPX500 feed. It now takes the price feed and the same rolling window as the TradingView chart; the y-range is
  computed from the bars inside the window.
- Files: `utils/charts.py`, `views/desk.py`.

## [1.0.0] — 2026-10-01
First versioned release. Everything below was previously shipped as unversioned zips.
### Added
- `VERSION`, `CHANGELOG.md`, release harness (`scripts/check.py`), release builder (`scripts/release.py`), CI workflow (`ci.yml`).
- `desk_settings.toml` (user settings, never shipped) with `desk_settings.example.toml`; candle opacity is a setting (default 0.7).
- Demo-mode smoke test `tests/test_smoke.py` covering plan, lock tiers, banner states, charts, grid text, map, card, credit grid, audit, journal.
- Version shown in the sidebar and the status bar.
### Changed
- Files: `app.py`, `views/common.py`, `views/desk.py`, `utils/lwchart.py`, `utils/charts.py`, `README.md`.

## [0.9.x] — 2026-10-01 (unversioned zips, in order)
- Barchart as the options source with minted WAF cookies (`data/barchart.py`, `barchart_cookies.yml`); CBOE delayed only as a flagged fallback; red "CHAIN NOT ON BARCHART" tag; optional fallback switch; bots install `curl_cffi`.
- CME removed entirely: C7 overnight drift and pre-market high/low from CAPITALCOM:SPX500; the strike-grid "/ES block" became the SPX500-feed block.
- CAPITALCOM:SPX500 as the single 24-hour price feed on the Desk (configurable), rules engine on SPX cash 5-min with a switch.
- Poll-interval slider; candles dodger-blue/magenta; theme toggle (SPX dash palette) independent of `config.toml`.
- TradingView Lightweight Charts price chart with price-line levels and a rolling 12-hour window; TRADE OPPORTUNITY banner (state machine, plays with entry/stop/target, XSP sizing, credit line); plays arm only after 09:50.
- Audit worker audits the last completed session when run before 16:15; DST guards on both bots; futures-settle date label.
### Fixed
- Empty chart before 09:30 (date axis forced; y-range from levels); light theme fallback; Finder "replace folder" data loss noted in README.

## [0.8.0] — 2026-09-30
- Review against the manuals and the Discord knowledge base: 11:05 last-qualifying-bar semantics, Archetype 2 "best touch" wording, strict 3-ticker requirement, Archetype 4 entry timing, gap-day level set for the rules engine, Positive-Gamma Scenario B per the desk, gap mornings favour Archetype 3, 0.5R sizing option, 10:15 primary window, stop-cluster levels, Micro Desk (XSP), both fence conventions, 08:33 cross-check panel.

## [0.7.0] — 2026-09-30
- Initial Streamlit app: workstation cells C5–C46 cell-exact, desk-bot strike grid (±0.5 EM nodes, ±1.0 walls, ±1.25 fences, SPY block, beyond-0DTE), rules engine and hindsight replay for Archetypes 1–4, 04:15 audit in the desk format, scenario map and trade card, credit vault, Tab 2 journal, settlement history, desk knowledge, 08:31 lock and 16:20 audit bots.
