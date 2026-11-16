"""Data dictionary and lineage diagram, generated from dbt's own manifest so they never drift from the models.

Writes docs/data_dictionary.md and docs/figures/data_lineage.png. Needs `dbt docs generate` to have run
(it writes dbt/target/manifest.json and catalog.json) and Playwright for the diagram.
Run from the repo root:  .venv/bin/python docs/process/data_docs.py
"""

import html
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
TARGET = REPO / "dbt" / "target"
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"
LAYERS = {"stg_transactions": "Staging", "fct_transaction_features": "Features", "fct_rules_baseline": "Rules",
          "rpt_rules_baseline_performance": "Report", "fairness_attributes": "Restricted"}

# The Python and app layers that read the dbt models (not in dbt's manifest).
DOWNSTREAM = """
    fct_transaction_features --> TRAIN["train.py / final_model.py<br/>model selection, champion in MLflow"]
    TRAIN --> SCORES[("scoring.model_scores")]
    SCORES --> DEC["decisioning.py<br/>four routes, business case"]
    DEC --> DECISIONS[("scoring.decisions")]
    DECISIONS --> EXPLAIN["explain.py<br/>SHAP reasons"]
    EXPLAIN --> ALERTS[("app.alerts and<br/>app.alert_decision_log")]
    ALERTS --> APP["Streamlit app<br/>queue and MI"]
    DECISIONS --> DRIFT["drift.py"] --> MON[("monitoring.drift_monthly")]
    fct_transaction_features --> DRIFT
    fairness_attributes -. aggregates only .-> FAIR["fairness.py<br/>fairness audit"]
    DECISIONS --> FAIR
"""


def lineage(manifest: dict) -> str:
    lines = ["flowchart LR"]
    for src in manifest["sources"].values():
        lines.append(f'    raw_{src["name"]}[("raw: {src["name"]}<br/>card numbers, personal data")]')
    for node in manifest["nodes"].values():
        if node["resource_type"] != "model":
            continue
        label = f'{LAYERS.get(node["name"], "")}: {node["name"]}'
        lines.append(f'    {node["name"]}["{label}<br/>schema {node["schema"]}"]')
        for dep in node["depends_on"]["nodes"]:
            parent = dep.split(".")[-1]
            parent_id = f"raw_{parent}" if dep.startswith("source.") else parent
            lines.append(f"    {parent_id} --> {node['name']}")
    lines.append(DOWNSTREAM)
    lines.append("    classDef restricted fill:#fdecea,stroke:#d03b3b")
    lines.append("    class fairness_attributes,FAIR restricted")
    return "\n".join(lines)


def dictionary(manifest: dict, catalog: dict) -> str:
    tests = [n for n in manifest["nodes"].values() if n["resource_type"] == "test"]
    out = ["# Data dictionary", "",
           "Generated from dbt's manifest by `docs/process/data_docs.py`; every column below is documented in the "
           "dbt YAML next to its model. Card numbers and personal data exist only in the raw table; "
           "`analytics_restricted` holds age band and gender for the fairness audit only.", "",
           "![Data lineage](figures/data_lineage.png)", "",
           f"dbt runs {len(tests)} data tests on these models (see `dbt/models/*/_*.yml` and `dbt/tests/`).", ""]
    for key, node in manifest["nodes"].items():
        if node["resource_type"] != "model":
            continue
        cat_cols = catalog["nodes"][key]["columns"]
        out += [f"## {node['schema']}.{node['name']}", "", " ".join(node["description"].split()), "",
                "| Column | Type | Description |", "|---|---|---|"]
        for name, col in sorted(cat_cols.items(), key=lambda kv: kv[1]["index"]):
            desc = node["columns"].get(name, {}).get("description", "")
            out.append(f"| `{name}` | {col['type']} | {' '.join(desc.split())} |")
        out.append("")
    return "\n".join(out)


def main() -> None:
    manifest = json.loads((TARGET / "manifest.json").read_text())
    catalog = json.loads((TARGET / "catalog.json").read_text())
    (REPO / "docs" / "data_dictionary.md").write_text(dictionary(manifest, catalog))
    page_html = (f'<!doctype html><html><head><meta charset="utf-8"><script src="{MERMAID}"></script></head>'
                 '<body style="margin:0;background:#fff"><div id="wrap" style="display:inline-block;padding:24px">'
                 f'<div class="mermaid">{html.escape(lineage(manifest))}</div></div><script>mermaid.initialize('
                 '{startOnLoad:true,theme:"neutral",flowchart:{useMaxWidth:false},themeVariables:{fontSize:"16px"}});'
                 '</script></body></html>')
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=2)
        page.set_content(page_html)
        page.wait_for_selector(".mermaid svg", timeout=30_000)
        page.locator("#wrap").screenshot(path=str(REPO / "docs" / "figures" / "data_lineage.png"))
        browser.close()
    print("Wrote docs/data_dictionary.md and docs/figures/data_lineage.png")


if __name__ == "__main__":
    main()
