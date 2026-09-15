"""Runs in ONE matrix job (monitor.yml's `capture` job), for ONE product.

Confirmed 2026-09-15: a single GitHub Actions job visiting one product
page with the reused session succeeds — the problem was never the login,
it was multiple page loads inside the SAME job/browser session getting
Cloudflare-blocked after the first. Two independent jobs, each doing one
page load, got different outbound IPs and both succeeded. So the fix is
structural: one job per product, never more than one product page per
job. See ROOT-CAUSE-ANALYSIS.md section 12.

Reads PRODUCT_SLUG from the environment, captures that one product's
stock rows plus the Taiwan shipping signal, and writes
diagnostic-output/<slug>.json — which the workflow uploads as an artifact
for aggregate.py to pick up. Never writes stock_state.json (that's
aggregate.py's job, after all 12 results are in), never calls the GAS
webhook.
"""
import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from stock_classifier import classify_page, taiwan_shipping_status
from products import get_product

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
    try:
        return json.loads(base64.b64decode(encoded))
    except Exception:
        print("WARNING: MARUKYU_STORAGE_STATE present but could not be decoded; continuing as guest.")
        return None


def main():
    OUT.mkdir(exist_ok=True)
    slug = os.environ.get("PRODUCT_SLUG", "")
    if not slug:
        raise SystemExit("PRODUCT_SLUG environment variable is required.")
    product = get_product(slug)
    storage_state = load_storage_state()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            context_kwargs = dict(locale="en-US", timezone_id="Asia/Tokyo", viewport={"width": 1440, "height": 1600})
            if storage_state is not None:
                context_kwargs["storage_state"] = storage_state
            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            response = page.goto(product["url"], wait_until="domcontentloaded", timeout=45000)
            settle(page)
            html = page.content()
        finally:
            browser.close()

    result = classify_page(html)
    result["product_slug"] = slug
    result["product_zh"] = product["zh"]
    result["product_en"] = product["en"]
    result["product_url"] = product["url"]
    result["http_status"] = response.status if response else None
    result["observed_at"] = datetime.now(timezone.utc).isoformat()
    result["taiwan"] = taiwan_shipping_status(html) if html else "UNKNOWN"
    if result["http_status"] != 200 and not result["page"]["challenge"]:
        result["page_status"], result["page_reason"] = "UNKNOWN", "HTTP_ERROR"

    (OUT / f"{slug}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{slug}] page_status={result['page_status']} page_reason={result['page_reason']} http_status={result['http_status']}")
    for row in result["rows"]:
        print(f"[{slug}]  {row['sku']} {row['size']} -> {row['status']}")


if __name__ == "__main__":
    main()
