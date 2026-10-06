"""
Inline dashboard_data.json into the template to produce a single
self-contained dashboard/index.html.

    python python/05_build_dashboard.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DASH = os.path.join(ROOT, "dashboard")

with open(os.path.join(DASH, "dashboard_data.json")) as f:
    data_text = f.read()
with open(os.path.join(DASH, "_template.html")) as f:
    tpl = f.read()

TOKEN = "/*__DATA__*/ null"
if TOKEN not in tpl:
    raise SystemExit("data placeholder not found in template")

html = tpl.replace(TOKEN, data_text.strip())
out = os.path.join(DASH, "index.html")
with open(out, "w") as f:
    f.write(html)

print(f"[built] {out}  ({len(html)//1024} KB)")
