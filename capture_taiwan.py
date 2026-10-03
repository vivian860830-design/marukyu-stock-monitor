"""Runs in its OWN dedicated job (monitor.yml's `capture-taiwan` job),
parallel to — but never folded into — the 12 per-product `capture` matrix
jobs. Confirmed 2026-09-15 (see capture_one.py's docstring): a single
job/browser session that loads more than one page gets Cloudflare-blocked
after the first navigation. So this script must stay the only thing that
runs in its job, and must never be appended onto a product capture job.

Visits the checkout page ONCE, with the shared logged-in session, and
reads the real, authoritative Taiwan-shipping signal: whether WooCommerce
found a matching shipping rate for the account's saved billing address.
Confirmed 2026-10-03 against the user's own account/billing address
(Taiwan): with "Ship to a different address" left UNCHECKED, the
checkout page's order-review table shows either a computed shipping cost
(shipping enabled) or "No shipping options were found for <city>,
Taiwan." (shipping not enabled) — see
stock_classifier.taiwan_shipping_status_from_checkout() for the exact
markup this reads.

This requires one item to already be sitting in the account's cart —
checkout redirects elsewhere with an empty cart. Confirmed 2026-10-03
with "Tama Homare - 40g bag"
(https://www.marukyu-koyamaen.co.jp/english/shop/products/1127040c6) left
in the cart for exactly this purpose. This script never adds, removes,
or submits anything — it only loads the checkout page and reads it.

Writes diagnostic-output/taiwan-shipping.json, shaped so aggregate.py's
existing loader (which just globs every *.json under product-results/,
see load_product_results()) picks it up like any other product result:
no "rows", so it never contributes a restock, but its "taiwan" field is
exactly what aggregate.py's
`if taiwan == "UNKNOWN": taiwan = result.get("taiwan", "UNKNOWN")` loop
ends up using. No changes to aggregate.py were needed for this.
"""
import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from stock_classifier import taiwan_shipping_status_from_checkout

OUT = Path("diagnostic-output")
CHECKOUT_URL = "https://www.marukyu-koyamaen.co.jp/english/shop/cart/checkout"


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
    storage_state = load_storage_state()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            context_kwargs = dict(locale="en-US", timezone_id="Asia/Tokyo", viewport={"width": 1440, "height": 1600})
            if storage_state is not None:
                context_kwargs["storage_state"] = storage_state
            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            response = page.goto(CHECKOUT_URL, wait_until="domcontentloaded", timeout=45000)
            settle(page)
            html = page.content()
        finally:
            browser.close()

    taiwan = taiwan_shipping_status_from_checkout(html) if html else "UNKNOWN"
    result = {
        "product_slug": "taiwan-shipping-check",
        "rows": [],
        "page_status": "OK" if taiwan != "UNKNOWN" else "UNKNOWN",
        "page_reason": "CHECKOUT_SHIPPING_READ" if taiwan != "UNKNOWN" else "CHECKOUT_MARKUP_NOT_FOUND",
        "http_status": response.status if response else None,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "taiwan": taiwan,
    }
    (OUT / "taiwan-shipping.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[taiwan-shipping] taiwan={taiwan} http_status={result['http_status']}")


if __name__ == "__main__":
    main()
