"""barchart.py — OPTIONAL live chain via Barchart behind AWS WAF (skill: scraping-waf-protected-apis).
Only used when store/session/cookies.json exists (minted by `python data/barchart.py --mint` in CI with Playwright).
The app never requires it: fetcher.cboe_chain is the default chain source. To enable: add curl_cffi>=0.7.0 to
requirements.txt, create a cookie-mint workflow (every 30 min, weekdays), and call get_chain() before the CBOE path."""
import json, os, sys, time, logging
from typing import Optional
import pandas as pd
logger = logging.getLogger(__name__)
BC_API = "https://www.barchart.com/proxies/core-api/v1/options/get"
BC_PAGE = "https://www.barchart.com/stocks/quotes/$SPX/volatility-greeks"
COOKIE_PATH = "store/session/cookies.json"
FIELDS = "strikePrice,lastPrice,volatility,delta,gamma,theta,vega,volume,openInterest,optionType,bidPrice,askPrice"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def _headers(ua):
    return {"Accept": "application/json", "Accept-Language": "en-US,en;q=0.9", "Referer": BC_PAGE, "Origin": "https://www.barchart.com",
            "User-Agent": ua, "sec-ch-ua": '"Chromium";v="120", "Google Chrome";v="120", "Not-A.Brand";v="99"', "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"', "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin",
            "X-Requested-With": "XMLHttpRequest"}

def _cookies():
    if not os.path.exists(COOKIE_PATH):
        return None
    try:
        blob = json.load(open(COOKIE_PATH))
        return blob if {"aws-waf-token", "laravel_session"} <= set(blob.get("cookies", {})) else None
    except Exception:
        return None

def cookie_age_min() -> Optional[float]:
    blob = _cookies()
    return (time.time() - blob.get("minted_at", 0)) / 60 if blob else None


def get_rows(expiry: str, base_symbol: str = "$SPX") -> Optional[pd.DataFrame]:
    """Flat contract rows for one expiry in the fetcher schema (strike, type c/p, root, oi, volume, iv, greeks, bid, ask,
    last, mark), or None on any failure so the caller falls back to CBOE. orderDir=desc keeps ATM inside the 1000-row cap."""
    blob = _cookies()
    if not blob:
        return None
    try:
        from curl_cffi import requests as creq
    except ImportError:
        logger.warning("curl_cffi not installed — Barchart unavailable"); return None
    try:
        s = creq.Session(impersonate="chrome120")
        r = s.get(BC_API, params={"baseSymbol": base_symbol, "groupBy": "optionType", "expirationDate": expiry, "orderBy": "strikePrice",
                                  "orderDir": "desc", "raw": "1", "fields": FIELDS}, cookies=blob["cookies"],
                  headers=_headers(blob.get("user_agent", UA)), timeout=20)
        if r.status_code != 200:
            logger.warning("Barchart %s — falling back to CBOE", r.status_code); return None
        data = r.json().get("data") or {}
    except Exception as e:
        logger.warning("Barchart request failed: %s", e); return None
    rows = []
    for side, opts in (data.items() if isinstance(data, dict) else []):
        if not isinstance(opts, list):
            continue
        px = "c" if str(side).lower().startswith("c") else "p"
        for o in opts:
            rec = o.get("raw", o) if isinstance(o, dict) else None
            if not isinstance(rec, dict):
                continue
            bid, ask, last = float(rec.get("bidPrice") or 0), float(rec.get("askPrice") or 0), float(rec.get("lastPrice") or 0)
            rows.append({"strike": float(rec.get("strikePrice") or 0), "type": px, "root": "BC",
                         "oi": int(float(rec.get("openInterest") or 0)), "volume": int(float(rec.get("volume") or 0)),
                         "iv": float(rec.get("volatility") or 0), "delta": float(rec.get("delta") or 0), "gamma": float(rec.get("gamma") or 0),
                         "vega": float(rec.get("vega") or 0), "theta": float(rec.get("theta") or 0), "bid": bid, "ask": ask, "last": last,
                         "mark": round((bid + ask) / 2, 2) if (bid > 0 and ask > 0) else last})
    if not rows:
        logger.warning("Barchart: no contracts for %s", expiry); return None
    df = pd.DataFrame(rows)
    nz = df["iv"][df["iv"] > 0]
    if len(nz) and nz.median() > 1:          # normalise IV to a decimal at the boundary
        df["iv"] = df["iv"] / 100.0
    return df


async def _mint_async():
    from playwright.async_api import async_playwright
    p = await async_playwright().start()
    b = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"])
    ctx = await b.new_context(user_agent=UA, viewport={"width": 1440, "height": 900}, locale="en-US"); page = await ctx.new_page()
    await page.goto(BC_PAGE, wait_until="domcontentloaded", timeout=60000)
    cookies = {}
    for _ in range(40):
        cookies = {c["name"]: c["value"] for c in await ctx.cookies()}
        if "laravel_session" in cookies and "aws-waf-token" in cookies:
            break
        await page.wait_for_timeout(1000)
    verify = await page.evaluate("""async (url) => { const r = await fetch(url, {headers:{'Accept':'application/json'}, credentials:'include'}); return r.status; }""",
                                 BC_API + "?baseSymbol=%24SPX&groupBy=optionType&expirationDate=nearest&orderBy=strikePrice&orderDir=desc&raw=1&fields=strikePrice,optionType")
    await b.close(); await p.stop()
    if verify != 200:
        raise RuntimeError(f"in-page verify failed: {verify}")
    return {k: v for k, v in cookies.items() if k in ("aws-waf-token", "laravel_session", "bc_anon", "bcFreeUserPageView")}

def mint():
    import asyncio
    os.makedirs(os.path.dirname(COOKIE_PATH), exist_ok=True)
    ck = asyncio.run(_mint_async())
    json.dump({"minted_at": int(time.time()), "user_agent": UA, "cookies": ck}, open(COOKIE_PATH, "w"), indent=2)
    print("saved", COOKIE_PATH)

if __name__ == "__main__":
    import sys
    if "--mint" in sys.argv:
        mint()
