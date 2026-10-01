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
COOKIE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "session", "cookies.json")
FIELDS = "strikePrice,lastPrice,volatility,delta,gamma,theta,vega,volume,openInterest,optionType,bidPrice,askPrice,baseLastPrice"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def _headers(ua):
    return {"Accept": "application/json", "Accept-Language": "en-US,en;q=0.9", "Referer": BC_PAGE, "Origin": "https://www.barchart.com",
            "User-Agent": ua, "sec-ch-ua": '"Chromium";v="120", "Google Chrome";v="120", "Not-A.Brand";v="99"', "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"', "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin",
            "X-Requested-With": "XMLHttpRequest"}

_last_reason = "not attempted"
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REQUIRED = ("aws-waf-token", "laravel_session")
_url_cache = {"ts": 0.0, "blob": None, "url": None}
# public mint jobs already running elsewhere (same recipe, same blob format) — read when no secret is set
DEFAULT_COOKIE_URLS = ("https://raw.githubusercontent.com/realguru31/spxdash/main/data/session/cookies.json",)


def last_reason() -> str:
    return _last_reason


def _secret(name: str) -> str:
    return str(os.environ.get(name) or "").strip()        # Streamlit secrets are exported to env by views/common.py


def _valid(blob, where: str, why: list):
    ck = (blob or {}).get("cookies") or {}
    if any(k not in ck for k in _REQUIRED):
        why.append(f"{where}: blob lacks {list(_REQUIRED)} — re-mint"); return None
    blob["_path"] = where
    try:
        blob["_age_min"] = (time.time() - float(blob.get("minted_at", 0))) / 60.0
    except Exception:
        blob["_age_min"] = float("nan")
    return blob


def _cookies():
    """Minted cookie blob, in the priority of the proven vs3d2 loader:
      (0) BC_COOKIES_JSON secret — the blob pasted verbatim (Colab mint)
      (1) BC_COOKIE_URL secret   — raw GitHub URL of the cookies.json your mint job already commits
                                   (BC_COOKIE_TOKEN for a private repo; ?v= busts raw's 5-min cache)
      (2) on disk: store/session/cookies.json · data/session/cookies.json · data/baseline/cookies.json
    Requires aws-waf-token AND laravel_session; ALL blob cookies are sent as-is."""
    global _last_reason
    why = []
    raw = _secret("BC_COOKIES_JSON")
    if raw:
        try:
            b = _valid(json.loads(raw), "secret:BC_COOKIES_JSON", why)
            if b:
                _last_reason = "ok"; return b
        except Exception as e:
            why.append(f"BC_COOKIES_JSON is not valid JSON ({type(e).__name__})")
    url, tok = _secret("BC_COOKIE_URL"), _secret("BC_COOKIE_TOKEN")
    if url:
        try:
            if _url_cache["blob"] is not None and _url_cache["url"] == url and time.time() - _url_cache["ts"] < 60:
                return _url_cache["blob"]
            import requests as _rq
            hdr = {"accept": "application/json", "user-agent": UA}
            if tok:
                hdr["authorization"] = "token " + tok
            r = _rq.get(url, params={"v": int(time.time() // 60)}, headers=hdr, timeout=10)
            if r.status_code == 200:
                b = _valid(r.json(), "url:" + url, why)
                if b:
                    _url_cache.update(ts=time.time(), blob=b, url=url); _last_reason = "ok"; return b
            else:
                why.append(f"BC_COOKIE_URL → HTTP {r.status_code} ("
                           + ("file not published yet — run the mint workflow once" if r.status_code == 404
                              else "private repo needs BC_COOKIE_TOKEN" if r.status_code in (401, 403) else "check the URL") + ")")
        except Exception as e:
            why.append(f"BC_COOKIE_URL fetch failed: {type(e).__name__}: {e}")
    # disk candidates (this repo's own mint) + the proven public mint in realguru31/spxdash: the FRESHEST valid blob wins
    candidates = []
    paths = []
    for base in (_APP_DIR, os.getcwd()):
        for rel in (os.path.join("data", "session", "cookies.json"), os.path.join("store", "session", "cookies.json"),
                    os.path.join("data", "baseline", "cookies.json")):
            pth = os.path.join(base, rel)
            if pth not in paths:
                paths.append(pth)
    for pth in paths:
        try:
            if not os.path.exists(pth):
                continue
            b = _valid(json.load(open(pth)), pth, why)
            if b:
                candidates.append(b)
        except Exception as e:
            why.append(f"{pth}: {type(e).__name__}: {e}")
    for durl in DEFAULT_COOKIE_URLS:
        try:
            if _url_cache["blob"] is not None and _url_cache["url"] == durl and time.time() - _url_cache["ts"] < 60:
                candidates.append(_url_cache["blob"]); continue
            import requests as _rq
            r = _rq.get(durl, params={"v": int(time.time() // 60)}, headers={"accept": "application/json", "user-agent": UA}, timeout=10)
            if r.status_code == 200:
                b = _valid(r.json(), "url:" + durl, why)
                if b:
                    _url_cache.update(ts=time.time(), blob=b, url=durl); candidates.append(b)
            else:
                why.append(f"{durl} → HTTP {r.status_code}")
        except Exception as e:
            why.append(f"{durl}: {type(e).__name__}: {e}")
    if candidates:
        best = max(candidates, key=lambda b: float(b.get("minted_at", 0) or 0))
        _last_reason = "ok"
        return best
    if not why:
        why.append("no cookies: no secret, no cookies.json in this repo, and the spxdash public mint file was unreachable")
    _last_reason = "; ".join(why)
    return None


def cookie_age_min() -> Optional[float]:
    blob = _cookies()
    return blob.get("_age_min") if blob else None


def get_rows(expiry: str, base_symbol: str = "$SPX") -> Optional[pd.DataFrame]:
    """Flat contract rows for one expiry in the fetcher schema (strike, type c/p, root, oi, volume, iv, greeks, bid, ask,
    last, mark), or None on any failure so the caller falls back to CBOE. orderDir=desc keeps ATM inside the 1000-row cap."""
    global _last_reason
    blob = _cookies()
    if not blob:
        return None
    try:
        from curl_cffi import requests as creq
    except ImportError:
        _last_reason = "curl_cffi not installed (add it to requirements.txt and reboot the app)"; return None
    try:
        s = creq.Session(impersonate="chrome120")
        r = s.get(BC_API, params={"baseSymbol": base_symbol, "groupBy": "optionType", "expirationDate": expiry, "orderBy": "strikePrice",
                                  "orderDir": "desc", "raw": "1", "fields": FIELDS}, cookies=blob["cookies"],
                  headers=_headers(blob.get("user_agent", UA)), timeout=20)
        if r.status_code != 200:
            age = blob.get("_age_min", float("nan"))
            _last_reason = f"HTTP {r.status_code} — cookies {age:.0f} min old from {blob.get('_path')} were sent and REJECTED (re-mint)"; return None
        data = r.json().get("data") or {}
    except Exception as e:
        _last_reason = f"request failed: {type(e).__name__}: {e}"; return None
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
        _last_reason = f"HTTP 200 but no contracts for {expiry} (expiry not listed?)"; return None
    _last_reason = "ok"
    df = pd.DataFrame(rows)
    nz = df["iv"][df["iv"] > 0]
    if len(nz) and nz.median() > 1:          # normalise IV to a decimal at the boundary
        df["iv"] = df["iv"] / 100.0
    return df


if __name__ == "__main__":
    print("mint moved to scripts/mint_cookies.py (stdlib + Playwright) — run that instead")
