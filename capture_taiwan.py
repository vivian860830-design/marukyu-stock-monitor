"""Runs in its OWN dedicated job (monitor.yml's `capture-taiwan` job),

parallel to — but never folded into — the 12 per-product `capture` matrix
jobs. Confirmed 2026-09-15 (see capture_one.py's docstring): a single
job/browser session that loads more than one page gets Cloudflare-blocked
after the first navigation. So this script must stay the only thing that
runs in its job, and must never be appended onto a product capture job.

Visits the checkout page ONCE, with the shared logged-in session, and
reads the real Taiwan-shipping signal (see
stock_classifier.taiwan_shipping_status_from_checkout()).

CHANGE vs the previous version (2026-10-24): the checkout page's
"Ship to an address different from the billing address" checkbox is
observed to be CHECKED by default on the user's account. When checked,
WooCommerce computes shipping for the saved *shipping* address, not the
billing address. This version unchecks it IN PLACE (an ajax recalculation,
not a second page navigation, so it does not add a Cloudflare-exposed
request) and only then reads the result.

Fail-closed rules:
  - checkbox found but still checked after the attempt -> taiwan = UNKNOWN
  - checkbox not found -> read as before, but record checkbox="not_found"
    in the JSON so the situation is visible
Never clicks Place order, never adds/removes cart items, never submits.

Checkbox selector confirmed from a DevTools screenshot (input name
`ship_to_different_address`, label `#ship-to-different-address`). Still
unverified: the ajax name `update_order_review` (falls back to a fixed wait)
and whether the label click actually toggles it on the live page (checked
afterwards; if not toggled the result is UNKNOWN, never a guess).
"""

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from stock_classifier import taiwan_shipping_status_from_checkout

OUT = Path("diagnostic-output")
CHECKOUT_URL = "https://www.marukyu-koyamaen.co.jp/english/shop/cart/checkout"
# Confirmed from the user's DevTools screenshot (2026-10-24): the input is
# <input id="use_shipping_address" name="ship_to_different_address" type="checkbox" checked>,
# inside <label id="ship-to-different-address"> (custom-styled via ::before).
CHECKBOX = 'input[name="ship_to_different_address"]'
LABEL = "#ship-to-different-address"


# Diagnostics: booleans / counts / URL path only. Deliberately NO page text,
# address, name or e-mail -- artifacts of a public repository are downloadable.
JS_DIAG = """() => {
  const text = document.body?.innerText || '';
  const row = document.querySelector('tr.woocommerce-shipping-totals');
  return {
    title: (document.title || '').slice(0, 80),
    challenge: /Just a moment/i.test(document.title) ||
               /Performing security verification|Verify you are human/.test(text) ||
               !!document.querySelector('#cf-turnstile, .cf-turnstile, input[name="cf-turnstile-response"]'),
    logged_in: document.body.classList.contains('logged-in') ||
               !!document.querySelector('a[href*="customer-logout"]'),
    checkout_form_present: !!document.querySelector('form.checkout'),
    cart_items: document.querySelectorAll('tr.cart_item').length,
    shipping_row: !!row,
    destination_p: !!document.querySelector('p.woocommerce-shipping-destination'),
    not_enabled_class: !!document.querySelector('.woocommerce-shipping-not-enabled'),
    no_options_message: /No shipping options were found/i.test(row ? row.textContent : ''),
    shipping_method_inputs: document.querySelectorAll('input[name^="shipping_method"]').length,
    checkbox_present: !!document.querySelector('input[name="ship_to_different_address"]'),
    checkbox_checked: (document.querySelector('input[name="ship_to_different_address"]') || {}).checked === true
  };
}"""


def diagnostics(page):
    try:
        data = page.evaluate(JS_DIAG)
        data["path"] = urlsplit(page.url).path
        return data
    except Exception as error:
        return {"error": type(error).__name__}


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


def uncheck_ship_to_different(page):
    """Returns 'not_found' | 'already_unchecked' | 'unchecked' | 'still_checked'."""
    box = page.locator(CHECKBOX)
    if box.count() != 1:
        return "not_found"
    if not box.is_checked():
        return "already_unchecked"
    # The real input is hidden behind a custom-styled label, so click the
    # label (what a human clicks). The ajax name is unverified; if it never
    # fires we fall through to settle().
    try:
        with page.expect_response(lambda r: "update_order_review" in r.url, timeout=15000):
            page.locator(LABEL).click()
    except Exception:
        pass
    settle(page)
    if box.is_checked():
        try:
            box.uncheck(force=True)  # fallback if the label click did not toggle it
        except Exception:
            pass
        settle(page)
    return "still_checked" if box.is_checked() else "unchecked"


def main():
    OUT.mkdir(exist_ok=True)
    storage_state = load_storage_state()
    html = ""
    response = None
    checkbox = "not_attempted"
    diag_before = diag_after = None
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
            diag_before = diagnostics(page)
            checkbox = uncheck_ship_to_different(page)
            diag_after = diagnostics(page)
            html = page.content()
        finally:
            browser.close()

    if checkbox == "still_checked":
        taiwan, reason = "UNKNOWN", "CHECKBOX_STILL_CHECKED"
    else:
        taiwan = taiwan_shipping_status_from_checkout(html) if html else "UNKNOWN"
        reason = "CHECKOUT_SHIPPING_READ" if taiwan != "UNKNOWN" else "CHECKOUT_MARKUP_NOT_FOUND"

    result = {
        "product_slug": "taiwan-shipping-check",
        "rows": [],
        "page_status": "OK" if taiwan != "UNKNOWN" else "UNKNOWN",
        "page_reason": reason,
        "ship_to_different_checkbox": checkbox,
        "diag_before_uncheck": diag_before,
        "diag_after_uncheck": diag_after,
        "http_status": response.status if response else None,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "taiwan": taiwan,
    }
    (OUT / "taiwan-shipping.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[taiwan-shipping] taiwan={taiwan} checkbox={checkbox} http_status={result['http_status']}")
    print(f"[taiwan-shipping] diag_before={json.dumps(diag_before)}")
    print(f"[taiwan-shipping] diag_after={json.dumps(diag_after)}")


if __name__ == "__main__":
    main()
