"""mint_cookies.py — Barchart WAF cookie mint, verbatim from the working vs3d2 `--mint` (stdlib + Playwright ONLY).
Runs in a bare GitHub Actions container: solves the AWS WAF challenge in a real browser, verifies the options API
IN-PAGE, writes data/session/cookies.json. Raises on failure so CI fails loudly rather than publishing dead cookies."""
import asyncio, json, os, sys, time

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
BASE = "https://www.barchart.com"
OPTIONS_URL = f"{BASE}/proxies/core-api/v1/options/get"
BC_PAGE = f"{BASE}/stocks/quotes/$SPX/volatility-greeks"
_REQUIRED_COOKIES = ("aws-waf-token", "laravel_session")
_KEEP_COOKIES = ("aws-waf-token", "laravel_session", "bc_anon", "bcFreeUserPageView")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MINT_PATH = os.path.join(_ROOT, "data", "session", "cookies.json")


def _cli_mint():
    try:
        from playwright.async_api import async_playwright
    except Exception:
        print("ERROR: playwright not installed. `pip install playwright && python -m playwright install --with-deps chromium`",
              file=sys.stderr); sys.exit(1)

    async def _run():
        p = await async_playwright().start()
        b = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"])
        ctx = await b.new_context(user_agent=_UA, viewport={"width": 1440, "height": 900}, locale="en-US")
        pg = await ctx.new_page(); t0 = time.time()
        await pg.goto(BC_PAGE, wait_until="domcontentloaded", timeout=60000)
        ck = {}
        for _ in range(40):        # WAF solves in-page, THEN the app sets laravel_session
            ck = {c["name"]: c["value"] for c in await ctx.cookies()}
            if all(k in ck for k in _REQUIRED_COOKIES):
                break
            await pg.wait_for_timeout(1000)
        title = await pg.title()
        verify = await pg.evaluate(
            """async (url)=>{const r=await fetch(url,{headers:{'Accept':'application/json'},credentials:'include'});const t=await r.text();return {status:r.status,len:t.length,waf:r.headers.get('x-amzn-waf-action'),deny:r.headers.get('x-deny-reason'),cf:r.headers.get('cf-mitigated'),body:t.slice(0,160)};}""",
            OPTIONS_URL + "?baseSymbol=%24SPX&groupBy=optionType&expirationDate=nearest&orderBy=strikePrice&orderDir=desc&raw=1&fields=strikePrice,gamma,openInterest,optionType")
        await b.close(); await p.stop()
        print(f"solve {time.time() - t0:.1f}s | title {title[:60]!r} | cookies {sorted(ck)} | "
              f"in-page verify {verify['status']} bytes={verify['len']}", flush=True)
        if verify["status"] != 200:
            why = ("OWN network egress filter (x-deny-reason=%s) — not Barchart" % verify["deny"] if verify.get("deny")
                   else "AWS WAF challenge not cleared (x-amzn-waf-action=%s) — challenge did not solve in 40s" % verify["waf"] if verify.get("waf")
                   else "Cloudflare challenge" if verify.get("cf") else "see body")
            raise RuntimeError(f"in-page verify failed: HTTP {verify['status']} — {why} | cookies seen {sorted(ck)} | body {verify['body']!r}")
        kept = {k: v for k, v in ck.items() if k in _KEEP_COOKIES}
        miss = [k for k in _REQUIRED_COOKIES if k not in kept]
        if miss:
            raise RuntimeError(f"missing required cookies: {miss}")
        return kept

    kept = asyncio.run(_run())
    os.makedirs(os.path.dirname(_MINT_PATH), exist_ok=True)
    blob = {"minted_at": int(time.time()), "minted_at_iso": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "user_agent": _UA, "cookies": kept}
    with open(_MINT_PATH, "w") as f:
        json.dump(blob, f, indent=2)
    print(f"saved {_MINT_PATH} ({len(kept)} cookies)")


if __name__ == "__main__":
    _cli_mint()
