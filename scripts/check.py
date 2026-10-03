"""Release harness. Exit code 0 = ship. Runs: byte-compile, Python 3.11 syntax (no PEP 701 f-strings), unit tests,
demo-mode smoke test. Usage: python scripts/check.py"""
import ast, glob, os, re, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
fails = []
for f in glob.glob("**/*.py", recursive=True):
    if "/_store_smoke/" in f or f.startswith("tools/"):
        continue
    src = open(f, encoding="utf-8").read()
    try:
        compile(src, f, "exec")
        ast.parse(src, feature_version=(3, 11))
    except SyntaxError as e:
        fails.append(f"{f}:{e.lineno} {e.msg}")
    for i, line in enumerate(src.split("\n"), 1):
        if re.search(r'f"([^"\\]|\\.)*\{[^}]*"[^}]*\}', line) or re.search(r"f'([^'\\]|\\.)*\{[^}]*'[^}]*\}", line):
            fails.append(f"{f}:{i} nested same-quote f-string (Python 3.12 only)")
print("syntax:", "OK" if not fails else "\n".join(fails))
for t in ("tests/test_core.py", "tests/test_smoke.py"):
    r = subprocess.run([sys.executable, t], capture_output=True, text=True)
    ok = r.returncode == 0
    print(f"{t}: {'OK' if ok else 'FAIL'}")
    if not ok:
        fails.append(t); print(r.stdout[-2000:], r.stderr[-2000:])
version = open("VERSION").read().strip()
chlog = open("CHANGELOG.md").read()
if f"## [{version}]" not in chlog:
    fails.append(f"CHANGELOG.md has no entry for {version}")
print("changelog entry:", "OK" if f"## [{version}]" in chlog else "MISSING")
print("RESULT:", "SHIP" if not fails else "DO NOT SHIP")
sys.exit(1 if fails else 0)
