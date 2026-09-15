"""Kinrin authenticated SKU diagnostic — v3.

Diagnostic only. Never writes stock_state.json, never sends LINE, never
adds to cart. This is the successor to code/02-auth-v2-current/monitor.py
in the ChatGPT handoff; see ROOT-CAUSE-ANALYSIS.md for why it's shaped
this way.

What changed vs v2, and why:

1. Stock classification now goes through stock_classifier.classify_page(),
   the exact function offline_regression_test.py checks against three
   saved HTML snapshots (guest / Cloudflare-challenged / real logged-in
   browser) before this file ever touches GitHub Actions. v2's classify()
   lived only inside browser-side JS and was never testable offline.

2. Primary path no longer drives Playwright through the Cloudflare-guarded
   /account login form at all. All three evidence rounds (evidence/01,
   evidence/02) show /account gets a Cloudflare challenge — 403 or
   307->403, a Turnstile iframe, "Just a moment..." — in both headed and
   headless mode, before any credential is ever filled in. Meanwhile the
   *product* page loads fine in headed mode as a guest. So instead this
   tries to reuse a Playwright storage_state (cookies) captured from one
   real, human-solved login done on the user's own machine, applied to
   the browser context *before* navigating straight to the product page —
   never visiting /account in CI at all. See "Experiment B" in
   ROOT-CAUSE-ANALYSIS.md and local/export_storage_state.py.

   THIS IS UNTESTED AGAINST THE LIVE SITE. Nothing in this sandbox has
   Marukyu credentials, and credentials should not be typed by an
   automated agent even if it had them — the login must be solved by an
   actual human once. Treat the "REUSED SESSION EXPERIMENT" line in the
   run output as the result of that first real test, not a guarantee.

3. If no MARUKYU_STORAGE_STATE secret is present, this falls back to the
   same interactive /account attempt v1/v2 made, purely to keep
   collecting Cloudflare evidence — expected, per every prior round, to
   still report LOGIN_CHALLENGE.

4. PRODUCTS currently lists only Kinrin, the one product URL actually in
   the handoff. The other 11 matcha names from README-交接說明.md section 1
   are NOT wired in — their product URLs were never provided and must not
   be guessed. Add them here once you have the URLs; capture_product()
   and classify_page() already work per-page, so no other change is
   needed to extend to more products.
"""
import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from stock_classifier import classify_page

PRODUCTS = [
    {"name": "Kinrin", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1151020c1"},
]
ACCOUNT_URL = "https://www.marukyu-koyamaen.co.jp/english/shop/account"
OUT = Path("diagnostic-output")


def save(name, value):
    OUT.mkdir(exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def settle(page):
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PlaywrightTimeout:
        pass
    page.wait_for_timeout(2000)


def load_storage_state():
    """Decode MARUKYU_STORAGE_STATE (base64 JSON) if the secret is set.
    Returns None (not an error) when absent, so the diagnostic still runs
    guest-only, matching v1/v2 behaviour."""
    encoded = os.environ.get("MARUKYU_STORAGE_STATE", "")
    if not encoded:
        return None
    try:
        return json.loads(base64.b64decode(encoded))
    except Exception:
        print("WARNING: MARUKYU_STORAGE_STATE present but could not be decoded as base64 JSON; ignoring it.")
        return None


def capture_product(page, product, label):
    response = page.goto(product["url"], wait_until="domcontentloaded", timeout=45000)
    settle(page)
    html = page.content()
    result = classify_page(html)
    result["label"] = label
    result["product"] = product["name"]
    result["http_status"] = response.status if response else None
    result["observed_at"] = datetime.now(timezone.utc).isoformat()
    if result["http_status"] != 200 and not result["page"]["challenge"]:
        result["page_status"], result["page_reason"] = "UNKNOWN", "HTTP_ERROR"
    save(f"{label}-{product['name'].lower()}.json", result)
    # Screenshot only the known SKU rows: never the account/login screen.
    for row in result["rows"]:
        vid = row["variation_id"]
        if not vid:
            continue
        locator = page.locator(f'.product-form-row[data-variation_id="{vid}"]')
        if locator.count() == 1:
            try:
                locator.first.screenshot(path=str(OUT / f"{label}-{product['name'].lower()}-{vid}.png"))
            except Exception:
                pass
    return result


def attempt_account_login_evidence(page, mode):
    """Evidence-gathering only, unchanged in intent from v1/v2: never
    clicks the challenge widget, never fills credentials once a challenge
    is detected. Expected, per every prior round, to hit LOGIN_CHALLENGE."""
    documents = []

    def document_seen(response):
        if response.request.resource_type == "document":
            parts = urlsplit(response.url)
            documents.append({"host": parts.hostname, "path": parts.path, "status": response.status})

    page.on("response", document_seen)
    try:
        page.goto(ACCOUNT_URL, wait_until="domcontentloaded", timeout=45000)
        settle(page)
        for _ in range(6):
            signals = classify_page(page.content())["page"]
            if not signals["challenge"]:
                break
            page.wait_for_timeout(5000)
        signals = classify_page(page.content())["page"]
        info = {
            "title": signals["title"],
            "challenge": signals["challenge"],
            "login_required": signals["login_required"],
            "documents": documents,
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }
        save(f"{mode}-account-attempt.json", info)
        return info
    finally:
        page.remove_listener("response", document_seen)


def run_mode(playwright, mode, storage_state):
    results = []
    browser = playwright.chromium.launch(headless=(mode == "headless"))
    try:
        context_kwargs = dict(locale="en-US", timezone_id="Asia/Tokyo", viewport={"width": 1440, "height": 1600})
        if storage_state is not None:
            context_kwargs["storage_state"] = storage_state
        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        label = f"{mode}-{'reused-session' if storage_state else 'guest'}"
        for product in PRODUCTS:
            results.append(capture_product(page, product, label))

        if storage_state is None:
            info = attempt_account_login_evidence(page, mode)
            results.append({"label": f"{mode}-account-attempt", "page_status": "UNKNOWN",
                             "page_reason": "LOGIN_CHALLENGE" if info["challenge"] else "SEE_JSON", **info})
    finally:
        browser.close()
    return results


def main():
    OUT.mkdir(exist_ok=True)
    storage_state = load_storage_state()
    summary = []
    with sync_playwright() as p:
        for mode in ("headed", "headless"):
            try:
                summary.extend(run_mode(p, mode, storage_state))
            except Exception as error:
                summary.append({"label": mode, "page_status": "UNKNOWN", "page_reason": type(error).__name__})
    save("summary.json", summary)

    for item in summary:
        print(item.get("label"), item.get("page_status"), item.get("page_reason"))

    print("Diagnostic only. No baseline updates and no notifications.")
    print(f"storage_state secret present: {storage_state is not None}")

    if storage_state is not None:
        got_real_data = any(
            item.get("label", "").endswith("reused-session")
            and any(r.get("status") in ("AVAILABLE", "SOLD_OUT") for r in item.get("rows", []))
            for item in summary
        )
        verdict = "SUCCESS - got authenticated stock data without visiting /account" if got_real_data \
            else "FAILED - still guest-gated or challenged even with the reused session, see summary.json"
        print(f"REUSED SESSION EXPERIMENT: {verdict}")


if __name__ == "__main__":
    main()
