"""
Colab check for the Barchart path — run cell by cell.

!pip -q install playwright curl_cffi pandas && playwright install --with-deps chromium
!git clone https://github.com/<you>/azrael && cd azrael && python data/barchart.py --mint
# -> expect: solve time, page title, cookies [...], in-page verify: status=200, saved store/session/cookies.json
%cd azrael
import sys; sys.path.insert(0, "."); from data import barchart as BC, fetcher as F
from datetime import date
exp = date.today().isoformat()
rows = BC.get_rows(exp)
print("reason:", BC.last_reason(), "| rows:", None if rows is None else len(rows))
if rows is not None:
    agg = F.aggregate_rows(rows)
    print(agg.sort_values("total_oi", ascending=False).head(10)[["strike", "c_oi", "p_oi", "total_oi", "c_volume", "p_volume", "c_mark", "p_mark"]])
# Paste into Streamlit secrets (Manage app -> Settings -> Secrets) to use these cookies without GitHub Actions:
import json; print("\n[barchart]\ncookies_json = '" + json.dumps(json.load(open("store/session/cookies.json"))) + "'")
# A table of the top-OI strikes means the chain path is good end to end; 'HTTP 403' means the minted cookies were rejected
# from this IP; 'no cookie file' means the mint step did not run or did not commit.
