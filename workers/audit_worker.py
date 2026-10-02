"""audit_worker.py — GitHub Actions at 16:20 ET: settlement audit of today's session against the 08:30 map,
committed as store/audits/<session>.json. No streamlit import."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import audit as AU, plan as P, rules as R
from data import fetcher as F, storage as S
from utils.timeutil import now_et, is_trading_day, fmt_session_title, prev_trading_day

def main():
    now = now_et(); sess = now.date()
    if not is_trading_day(sess) or now.hour * 60 + now.minute < 16 * 60 + 15:
        # before the 16:15 review (or on a weekend/holiday) audit the last completed session instead — this is what a
        # manual 'Run workflow' at 03:00 should do; the 16:20 schedule audits today
        sess = prev_trading_day(sess)
        print(f"{now:%H:%M} ET is before today's settlement — auditing the last completed session {sess}")
    creds = (os.environ.get("TV_USERNAME"), os.environ.get("TV_PASSWORD")); creds = creds if all(creds) else None
    base = S.load_baseline(sess.isoformat())
    if not base or not base.get("ok"):
        base = P.build_plan(sess, "08:15", "08:20", 25000, 1.0, 8.0, 0.55, {}, creds, None, os.environ.get("AZRAEL_PRICE_SYMBOL", "CAPITALCOM:SPX500"))
    if not base.get("ok"):
        print("no map"); sys.exit(1)
    spx5, _ = F.get_bars("SPX", "5", 600, creds); spy5, _ = F.get_bars("SPY", "5", 600, creds); qqq5, _ = F.get_bars("QQQ", "5", 600, creds)
    spxd, _ = F.daily("SPX", 3, creds)
    settle = float(spxd["close"].iloc[-1]) if spxd is not None and not spxd.empty and spxd.index[-1].date() == sess else None
    lv = R.rule_levels(base); grid = {k: lv[k] for k in ("C13", "C14", "C15", "C16", "C17")}
    proxies = []
    for key, blk in (("SPY", base.get("spy")), ("FEED", base.get("es"))):
        if blk:
            b5, _ = F.get_bars("SPY", "5", 600, creds) if key == "SPY" else F.get_symbol_bars(os.environ.get("AZRAEL_PRICE_SYMBOL", "CAPITALCOM:SPX500"), "5", 600, creds)
            d5 = F.session_slice(b5, sess)
            px = float(d5["close"].iloc[-1]) if not d5.empty else None
            proxies.append({"name": blk.get("name", key), "settle": px, "band_lo": blk["band_lo"], "band_hi": blk["band_hi"], "em": blk["em"]})
    a = AU.build_audit(fmt_session_title(sess), F.session_slice(spx5, sess), F.session_slice(spy5, sess), F.session_slice(qqq5, sess),
                       settle, base["grid"]["c15"], base["inputs"]["c6"], base["inputs"].get("vix_print", "08:15"), grid, lv["em"],
                       lv["put_node"], lv["call_node"], base["strike_grid"]["put_fence"], base["strike_grid"]["call_fence"],
                       base["inputs"]["c6"], proxies, base.get("stop_clusters"))
    p = S.save_audit(sess.isoformat(), a.as_dict())
    print("saved", p); print(AU.audit_text(a))

if __name__ == "__main__":
    main()
