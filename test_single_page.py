"""Minimal single-page diagnostic for the "does each GitHub Actions job get
a fresh Cloudflare trust slot" test. Visits exactly ONE product page (the
same Kinrin URL every time, on purpose, so a result difference between two
jobs cannot be explained by which product it was) with the reused session,
and prints AVAILABLE/SOLD_OUT/UNKNOWN. Never touches stock_state.json,
never calls the GAS webhook. Delete this file and test-ip-experiment.yml
once the matrix-job question is settled either way.
"""
import base64
import json
import os
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from stock_classifier import classify_page

URL = "https://www.marukyu-koyamaen.co.jp/english/shop/products/1151020c1"  # Kinrin, same URL every time
OUT = Path("diagnostic-output")


def settle(page):
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PlaywrightTimeout:
        pass
    page.wait_for_timeout(2000)


def load_storage_state():
    encoded = os.environ.get("MARUKYU_STORAGE_STATE", "")
    if not encoded:
        return None
    return json.loads(base64.b64decode(encoded))


def outbound_ip():
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=10) as response:
            return response.read().decode().strip()
    except Exception as error:
        return f"UNKNOWN ({type(error).__name__})"


def main():
    OUT.mkdir(exist_ok=True)
    job_label = os.environ.get("JOB_LABEL", "unknown-job")
    ip = outbound_ip()
    print(f"[{job_label}] outbound IP: {ip}")

    storage_state = load_storage_state()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            context_kwargs = dict(locale="en-US", timezone_id="Asia/Tokyo", viewport={"width": 1440, "height": 1600})
            if storage_state is not None:
                context_kwargs["storage_state"] = storage_state
            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            response = page.goto(URL, wait_until="domcontentloaded", timeout=45000)
            settle(page)
            html = page.content()
            result = classify_page(html)
            result["job_label"] = job_label
            result["outbound_ip"] = ip
            result["http_status"] = response.status if response else None
        finally:
            browser.close()

    (OUT / f"{job_label}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{job_label}] page_status={result['page_status']} page_reason={result['page_reason']} http_status={result['http_status']}")
    for row in result["rows"]:
        print(f"[{job_label}]  {row['sku']} {row['size']} -> {row['status']}")


if __name__ == "__main__":
    main()
