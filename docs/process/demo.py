"""Record the README demo: a GIF of one alert being worked, and a screenshot of one alert's reasons.

A one-off documentation tool. Drives the running app (http://localhost:8501) with Playwright:
Overview -> Alert queue -> enter a name -> read why the top alert was flagged -> confirm fraud -> MI.
It records one decision as "Demo analyst"; remove it afterwards with the SQL printed at the end.

Writes docs/figures/demo.gif and docs/figures/app_alert.png.
Run from the repo root:  .venv/bin/python docs/process/demo.py
"""

import io
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

FIGURES = Path(__file__).resolve().parents[1] / "figures"
URL = "http://localhost:8501"
WIDTH, HEIGHT = 1440, 900
GIF_WIDTH = 960


def frame(page, hold_ms: int) -> tuple[Image.Image, int]:
    image = Image.open(io.BytesIO(page.screenshot())).convert("RGB")
    image = image.resize((GIF_WIDTH, round(image.height * GIF_WIDTH / image.width)), Image.LANCZOS)
    return image, hold_ms


def settle(page, ms: int = 2500) -> None:
    """Streamlit re-runs the page after every action; wait for it to finish."""
    page.wait_for_timeout(500)
    page.wait_for_function("() => !document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=30_000)
    page.wait_for_timeout(ms)


def main() -> None:
    frames = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)

        page.goto(URL)
        settle(page, 4000)
        frames.append(frame(page, 3500))                                   # 1. Overview

        page.get_by_role("link", name="Alert queue").first.click()
        settle(page)
        frames.append(frame(page, 2500))                                   # 2. The queue

        page.get_by_role("textbox", name="Your name").fill("Demo analyst")
        page.get_by_role("textbox", name="Your name").press("Enter")
        settle(page)

        page.get_by_role("heading", name="Step 3").scroll_into_view_if_needed()
        page.mouse.wheel(0, -60)
        settle(page, 1500)
        frames.append(frame(page, 5000))                                   # 3. Why it was flagged

        # Screenshot for the README: the alert's header, route, reasons and score chart.
        # Streamlit scrolls an inner panel, not the window, so use a tall viewport for this one shot
        # and clip between the step 3 and step 4 headings (bounding boxes are viewport-relative).
        page.set_viewport_size({"width": WIDTH, "height": 2400})
        page.get_by_role("heading", name="Step 3").scroll_into_view_if_needed()
        settle(page, 1500)
        top = page.get_by_role("heading", name="Step 3").bounding_box()
        bottom = page.get_by_role("heading", name="Step 4").bounding_box()
        page.screenshot(path=str(FIGURES / "app_alert.png"),
                        clip={"x": top["x"] - 10, "y": top["y"] - 10,
                              "width": WIDTH - top["x"] - 40, "height": bottom["y"] - top["y"] - 10})
        page.set_viewport_size({"width": WIDTH, "height": HEIGHT})

        page.get_by_role("heading", name="Step 4").scroll_into_view_if_needed()
        page.get_by_role("textbox", name="Note (optional)").fill("Customer did not recognise the payment")
        settle(page, 800)
        frames.append(frame(page, 2500))                                   # 4. Decide
        page.get_by_role("button", name="Confirm fraud").click()
        settle(page, 1200)
        frames.append(frame(page, 2500))                                   # 5. Recorded

        page.get_by_role("link", name="Management information").first.click()
        settle(page, 3000)
        frames.append(frame(page, 4500))                                   # 6. MI
        browser.close()

    images, durations = zip(*frames)
    images[0].save(FIGURES / "demo.gif", save_all=True, append_images=list(images[1:]), duration=list(durations),
                   loop=0, optimize=True)
    size_mb = (FIGURES / "demo.gif").stat().st_size / 1e6
    print(f"Wrote docs/figures/demo.gif ({len(images)} frames, {size_mb:.1f} MB) and docs/figures/app_alert.png")
    print("Remove the demo decision: DELETE FROM app.alert_decision_log WHERE decided_by = 'Demo analyst'; "
          "UPDATE app.alerts SET status='open', analyst_decision=NULL, analyst_note=NULL, decided_by=NULL, "
          "decided_at=NULL WHERE decided_by = 'Demo analyst';")


if __name__ == "__main__":
    main()
