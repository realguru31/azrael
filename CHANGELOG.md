# Changelog
All notable changes to the Azraël Desk app. Format: Keep a Changelog; versions are semantic.

## [1.5.0] — 2026-10-03
### Added
- Trade markers on their own series so the arrow tip sits ON the entry price (arrowDown from above for a short, arrowUp
  from below for a long); exit markers at the exit price: green circle on a target touch, red circle on a stop-out,
  grey square at the 11:30 flat, each with the R; a yellow ARMED square over the live candle with the distance to the trigger.
- 1-minute / 5-minute candle toggle (sidebar). On the 1-minute view the entry/exit markers, lines and bands are placed
  at the 5-minute bar's close (e.g. the "10:50 bar" at 10:55); on the 5-minute view the trigger bar is one candle.
- Files: `utils/lwchart.py`, `utils/charts.py`, `views/common.py`, `views/desk.py`.

## [1.4.1] — 2026-10-03
### Fixed
- Status strip showed only its second row: the iframe component was being clipped by the browser. Replaced with two
  plain inline lines in the page itself (no iframe, no flex layout) — nothing left that can collapse or scroll.
- Files: `views/common.py`, `tests/test_smoke.py`.

## [1.4.0] — 2026-10-03
### Fixed
- Top strip hidden on fresh load: the page content started under Streamlit's fixed header (padding 0.8rem + opaque header).
  Content now starts below the header (4.5rem).
### Added
- Stop and target made execution-grade on every chart: TradingView main chart draws a red risk band (entry→stop) and a
  green reward band (entry→target) over the trade window with thick labelled lines ("STOP 7,742.58 · −1R · 5-min close",
  "TARGET 7,705.28 · +8.03R"); the Plotly main chart and the settlement-audit chart draw the same bands and labels.
- ACTIVE banner: the desk's late-entry rule (valid only within 0.5R of the trigger close; beyond that, pass).
- Weekend / evening: the banner reads "NEXT SESSION — provisional map" instead of a clock-driven state.
- No change to any firing or stop rule (verified verbatim against the manual and the desk audits).
- Files: `views/common.py`, `utils/lwchart.py`, `utils/charts.py`, `views/desk.py`, `core/execution.py`.

## [1.3.0] — 2026-10-02
### Added
- EXIT PLAN block in the ACTIVE banner: the archetype's written exits (target · stop · divergence/reversal · 11:30 time
  stop) with live distances, nearest first.
- "Log my exit" under the banner (price, time, note) → saved on the session card and pre-filled into the journal's
  Exit Price; shows your points and R on the rule's stop.
### Fixed
- Status strip rendered as a self-contained component (own CSS, fixed two rows) outside any column, so Streamlit's
  re-layout inside fragments can no longer collapse its items; refresh button on its own line at natural width.
- Settlement audit before 16:00 no longer invents a settlement from the last print: header reads "LIVE — session not
  settled", no dot, no verification line; Save disabled until the close.
- Files: `core/execution.py`, `core/audit.py`, `views/audit_view.py`, `views/common.py`, `views/desk.py`,
  `views/credit_view.py`, `views/premarket.py`, `views/journal_view.py`, `data/storage.py`.

## [1.2.2] — 2026-10-02
### Fixed
- App failed to start: the banner pulse keyframes (`0%`, `70%`, `100%`) inside the %-formatted stylesheet raised
  "not enough arguments for format string". Percent signs escaped; the smoke test now renders the stylesheet for both themes.
- Files: `views/common.py`, `tests/test_smoke.py`.

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

## [1.6.2] — 2026-10-07
### Changed (labels only)
- Scoring status text labels a 1-minute close by its close time (the 10:00 bar's close is "the 10:01 close"), as the desk does.
- The A2 "window low/high from 09:50 to 11:30" statistic counts bars opening at or after 09:50 (desk convention). Report only;
  the trigger window is unchanged.
- Files: `core/scoring.py`, `core/rules.py`.

## [1.6.1] — 2026-10-07
### Fixed
- The "Live idea (app scoring)" line was appended in the lesson builder instead of the audit text; it now appears in the
  long-form text before the Microstructure Lesson (same place as the desk's Live Idea section).
- Files: `core/audit.py`.

## [1.6.0] — 2026-10-07
### Added
- Scenario Book scoring (`core/scoring.py`): the ten checks (Regime, Open, Trigger, Structure, SPY and QQQ, Volume, VIX,
  Reward, Reach, Path) with visible app definitions (1 / ½ / 0, bare minimum = 0), the score out of 9.5, and the send /
  wait / drop logic on 1-minute index closes exactly as written (≥ 7.5 at the close; 6–7 wait ≤ 2 bars; 4–5.5 wait ≤ 4 bars
  for a 1-min close 0.25R in its direction; dropped on invalidation or 0.5R past the trigger close; nothing after 11:05).
  The book trade and its alert are unchanged; the score is the second banner line and a line in the audit text.
- Banner redesign: two lines — what's armed / what's on, and the score line — with plays, exits, score checks, credit and
  notes folded into a Details expander.
- Audit page: scoreboard (settle · range · VIX/EM/nodes/walls · REPLAY · SCORE · LESSON) beside the full desk-format text
  in its own box; chart below.
- Audit text: "After the one setup: … Not taken: one setup per day." and the A2 node explanation in the desk's form.
### Changed
- Past sessions show "expired expiry — no live chain" instead of a red chain tag.
- Files: `core/scoring.py`, `core/rules.py`, `core/execution.py`, `core/audit.py`, `views/desk.py`, `views/audit_view.py`.

## [Unreleased]
### Later
- Options-chain page (OI vs today's volume per strike).
### Investigate
- VIX 08:15 print — keep logging.
- Scoring definitions: compare each check's note with the desk's posted scores; tune.

## [1.5.0] — 2026-10-03
### Added
- Trade markers on their own series so the arrow tip sits ON the entry price (arrowDown from above for a short, arrowUp
  from below for a long); exit markers at the exit price: green circle on a target touch, red circle on a stop-out,
  grey square at the 11:30 flat, each with the R; a yellow ARMED square over the live candle with the distance to the trigger.
- 1-minute / 5-minute candle toggle (sidebar). On the 1-minute view the entry/exit markers, lines and bands are placed
  at the 5-minute bar's close (e.g. the "10:50 bar" at 10:55); on the 5-minute view the trigger bar is one candle.
- Files: `utils/lwchart.py`, `utils/charts.py`, `views/common.py`, `views/desk.py`.

## [1.4.1] — 2026-10-03
### Fixed
- Status strip showed only its second row: the iframe component was being clipped by the browser. Replaced with two
  plain inline lines in the page itself (no iframe, no flex layout) — nothing left that can collapse or scroll.
- Files: `views/common.py`, `tests/test_smoke.py`.

## [1.4.0] — 2026-10-03
### Fixed
- Top strip hidden on fresh load: the page content started under Streamlit's fixed header (padding 0.8rem + opaque header).
  Content now starts below the header (4.5rem).
### Added
- Stop and target made execution-grade on every chart: TradingView main chart draws a red risk band (entry→stop) and a
  green reward band (entry→target) over the trade window with thick labelled lines ("STOP 7,742.58 · −1R · 5-min close",
  "TARGET 7,705.28 · +8.03R"); the Plotly main chart and the settlement-audit chart draw the same bands and labels.
- ACTIVE banner: the desk's late-entry rule (valid only within 0.5R of the trigger close; beyond that, pass).
- Weekend / evening: the banner reads "NEXT SESSION — provisional map" instead of a clock-driven state.
- No change to any firing or stop rule (verified verbatim against the manual and the desk audits).
- Files: `views/common.py`, `utils/lwchart.py`, `utils/charts.py`, `views/desk.py`, `core/execution.py`.

## [1.3.0] — 2026-10-02
### Added
- EXIT PLAN block in the ACTIVE banner: the archetype's written exits (target · stop · divergence/reversal · 11:30 time
  stop) with live distances, nearest first.
- "Log my exit" under the banner (price, time, note) → saved on the session card and pre-filled into the journal's
  Exit Price; shows your points and R on the rule's stop.
### Fixed
- Status strip rendered as a self-contained component (own CSS, fixed two rows) outside any column, so Streamlit's
  re-layout inside fragments can no longer collapse its items; refresh button on its own line at natural width.
- Settlement audit before 16:00 no longer invents a settlement from the last print: header reads "LIVE — session not
  settled", no dot, no verification line; Save disabled until the close.
- Files: `core/execution.py`, `core/audit.py`, `views/audit_view.py`, `views/common.py`, `views/desk.py`,
  `views/credit_view.py`, `views/premarket.py`, `views/journal_view.py`, `data/storage.py`.

## [1.2.2] — 2026-10-02
### Fixed
- App failed to start: the banner pulse keyframes (`0%`, `70%`, `100%`) inside the %-formatted stylesheet raised
  "not enough arguments for format string". Percent signs escaped; the smoke test now renders the stylesheet for both themes.
- Files: `views/common.py`, `tests/test_smoke.py`.

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
