"""Render the Mermaid process maps to PNG (docs/process_as_is.png, docs/process_to_be.png).

A one-off documentation tool, not part of the pipeline. Needs Playwright and its Chromium:
    .venv/bin/pip install playwright==1.55.0 && .venv/bin/python -m playwright install chromium
Run from the repo root:  .venv/bin/python docs/process/render.py
"""

import html
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
DOCS = HERE.parent
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<script src="{mermaid}"></script>
<style>body {{ margin: 0; background: #ffffff; font-family: Helvetica, Arial, sans-serif; }}
#wrap {{ display: inline-block; padding: 24px; background: #ffffff; }}</style></head>
<body><div id="wrap"><div class="mermaid">{source}</div></div>
<script>mermaid.initialize({{ startOnLoad: true, theme: "neutral", flowchart: {{ curve: "basis", useMaxWidth: false }},
  themeVariables: {{ fontSize: "16px" }} }});</script></body></html>"""

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=2)
    for name in ("as_is", "to_be"):
        source = (HERE / f"{name}.mmd").read_text()
        page.set_content(PAGE.format(mermaid=MERMAID, source=html.escape(source)))
        page.wait_for_selector(".mermaid svg", timeout=30_000)
        page.locator("#wrap").screenshot(path=str(DOCS / f"process_{name}.png"))
        print(f"Wrote docs/process_{name}.png")
    browser.close()
