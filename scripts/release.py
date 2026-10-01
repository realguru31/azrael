"""Build the release zip after the harness passes. Usage: python scripts/release.py [out_dir]
Produces <out_dir>/azrael_desk_v<VERSION>.zip; the zip never contains desk_settings.toml, store/ data or caches."""
import os, subprocess, sys, zipfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
if subprocess.run([sys.executable, "scripts/check.py"]).returncode != 0:
    sys.exit("harness failed — not building")
version = open("VERSION").read().strip()
out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist")
os.makedirs(out_dir, exist_ok=True)
out = os.path.join(out_dir, f"azrael_desk_v{version}.zip")
SKIP_DIRS = {"__pycache__", ".git", "dist", "_store_smoke"}
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for dp, dns, fns in os.walk("."):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, ".")
            if rel == "desk_settings.toml" or rel.endswith(".pyc"):
                continue
            if rel.startswith("store/") and not fn == ".gitkeep":
                continue
            z.write(p, os.path.join("azrael_desk", rel))
print("built", out)
