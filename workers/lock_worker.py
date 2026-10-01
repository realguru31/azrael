"""lock_worker.py — GitHub Actions at 08:31 ET: build the session plan from the feeds and commit it as
store/baseline/<session>.json so the 08:30 lock survives app reboots. No streamlit import."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import plan as P
from data import storage as S
from utils.timeutil import now_et, session_date, is_trading_day

def main():
    now = now_et()
    if not is_trading_day(now.date()):
        print("not a trading day"); return
    sess = session_date(now)
    c8 = float(os.environ.get("AZRAEL_C8", 25000)); c9 = float(os.environ.get("AZRAEL_C9", 1.0))
    creds = (os.environ.get("TV_USERNAME"), os.environ.get("TV_PASSWORD"))
    creds = creds if all(creds) else None
    plan = P.build_plan(sess, os.environ.get("AZRAEL_VIX_PRINT", "08:15"), os.environ.get("AZRAEL_ES_PRINT", "08:20"),
                        c8, c9, 8.0, 0.55, {}, creds)
    if not plan.get("ok"):
        print("plan failed:", plan.get("notes")); sys.exit(1)
    plan["locked_at"] = now.strftime("%H:%M ET"); plan["lock_source"] = "GitHub Actions"
    p = S.save_baseline(sess.isoformat(), plan)
    print("saved", p, "C5", plan["inputs"]["c5"], "C6", plan["inputs"]["c6"], "C7", plan["inputs"]["c7"])

if __name__ == "__main__":
    main()
