"""Marukyu Koyamaen 12-product SKU monitor — v4.

Confirmed working end-to-end (2026-09-15): a reused, human-solved login
session, applied to a Playwright context that goes straight to each
product page (never touching the Cloudflare-guarded /account login form),
reads real authenticated stock data in headed mode. Headless is dropped
entirely here — every round of evidence (v1 through v4) shows it gets a
Cloudflare challenge even on the guest product page, so there is nothing
for it to do.

What this does, once a run starts:
  1. Load stock_state.json from the repository (committed by the previous
     run; see monitor.yml's "Commit updated stock_state.json" step).
  2. For each of the 12 known products, open its page with the reused
     session and classify every SKU row with stock_classifier.classify_page().
  3. Compare each SKU's new reading against stock_state.json:
       - UNKNOWN readings never overwrite the stored state and never
         trigger a notification — a Cloudflare hiccup or a transient
         layout miss must not corrupt the baseline or fire a false alert.
       - A SKU seen for the first time (no prior entry) is recorded as
         baseline only. No notification on first sight.
       - A SKU that was SOLD_OUT last time and is AVAILABLE now is a
         restock: added to the GAS webhook payload.
       - Any other transition (AVAILABLE->SOLD_OUT, no change) updates the
         stored status but does not notify.
  4. If there is at least one restock, POST it to the existing GAS webapp
     (GAS_WEBHOOK_URL secret) in the exact shape handleGithubNotification()
     in the Apps Script expects. DRY_RUN (default true; see monitor.yml's
     workflow_dispatch input) logs the payload instead of sending it.
  5. Write the updated stock_state.json back to the repo root. The
     workflow, not this script, commits it — this file only ever touches
     the working tree, never runs git itself.

Never adds to cart, never fills a login form, never submits credentials.
"""
import base64
import json
import os
import random
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from stock_classifier import classify_page, taiwan_shipping_status

PRODUCTS = [
    {"zh": "雲鶴", "en": "Unkaku", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1141020c1"},
    {"zh": "長安", "en": "Choan", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1121020c1"},
    {"zh": "永寿", "en": "Eiju", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1131020c1"},
    {"zh": "金輪", "en": "Kinrin", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1151020c1"},
    {"zh": "千木の白", "en": "Chigi no Shiro", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1181040c1"},
    {"zh": "五十鈴", "en": "Isuzu", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1191040c1"},
    {"zh": "青嵐", "en": "Aoarashi", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/11a1040c1"},
    {"zh": "極 長安", "en": "Kiwami Choan", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1g36020c1"},
    {"zh": "和光", "en": "Wako", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1161020c1"},
    {"zh": "天授", "en": "Tenju", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1111020c1"},
    {"zh": "又玄", "en": "Yugen", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1171020c1"},
    {"zh": "若竹", "en": "Wakatake", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/11b1100c1"},
]

OUT = Path("diagnostic-output")
STATE_PATH = Path("stock_state.json")

# 2026-09-15 finding: with a valid reused session, the FIRST product page
# in a run loads fine, but every page after it gets a Cloudflare challenge
# (403, "Just a moment...") even though the cookie is still valid. Twelve
# page loads back-to-back in one browser session reads as scraping, not
# login. A randomized pause between navigations is the fix; tune with the
# MIN/MAX_PAGE_DELAY_SECONDS env vars if 12 products still trip it, or
# shorten it once you've confirmed a smaller delay is enough.
MIN_PAGE_DELAY_SECONDS = float(os.environ.get("MIN_PAGE_DELAY_SECONDS", "6"))
MAX_PAGE_DELAY_SECONDS = float(os.environ.get("MAX_PAGE_DELAY_SECONDS", "15"))


def save_evidence(name, value):
    OUT.mkdir(exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


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


def load_state():
    if not STATE_PATH.exists():
        return {"updated_at": None, "skus": {}}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        print("WARNING: stock_state.json exists but could not be parsed; starting a fresh baseline.")
        return {"updated_at": None, "skus": {}}
    if not isinstance(data, dict) or not isinstance(data.get("skus"), dict):
        print("WARNING: stock_state.json exists but is missing/malformed 'skus'; starting a fresh baseline "
              "(existing unrelated keys, if any, are dropped).")
        return {"updated_at": None, "skus": {}}
    return data


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def capture_product(page, product):
    response = page.goto(product["url"], wait_until="domcontentloaded", timeout=45000)
    settle(page)
    html = page.content()
    result = classify_page(html)
    result["product"] = product["en"]
    result["http_status"] = response.status if response else None
    result["observed_at"] = datetime.now(timezone.utc).isoformat()
    if result["http_status"] != 200 and not result["page"]["challenge"]:
        result["page_status"], result["page_reason"] = "UNKNOWN", "HTTP_ERROR"
    save_evidence(f"{product['en'].lower().replace(' ', '-')}.json", result)
    return result, html


def diff_and_update(state, product, rows):
    """Returns the list of variants that just went SOLD_OUT -> AVAILABLE
    for this product, and mutates `state` in place per the rules in the
    module docstring."""
    restocked = []
    for row in rows:
        key = row["variation_id"]
        if not key:
            continue
        current = row["status"]
        if current == "UNKNOWN":
            continue  # never overwrite state or notify on an unreadable row
        previous = state["skus"].get(key)
        if previous is not None and previous.get("status") == "SOLD_OUT" and current == "AVAILABLE":
            restocked.append({"sku": row["sku"], "size": row["size"]})
        state["skus"][key] = {
            "product_zh": product["zh"],
            "product_en": product["en"],
            "sku": row["sku"],
            "size": row["size"],
            "status": current,
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }
    return restocked


def send_gas_notification(products_with_restocks, taiwan, dry_run):
    webhook_url = os.environ.get("GAS_WEBHOOK_URL", "")
    secret = os.environ.get("MONITOR_SECRET", "")
    payload = {
        "source": "github-monitor",
        "secret": secret,
        "products": products_with_restocks,
        "taiwan": taiwan,
    }
    save_evidence("gas-notification-payload.json", {**payload, "secret": "***redacted***"})

    if dry_run:
        print("DRY_RUN=true: not sending. Payload would have been:")
        print(json.dumps({**payload, "secret": "***redacted***"}, ensure_ascii=False, indent=2))
        return

    if not webhook_url or not secret:
        print("ERROR: GAS_WEBHOOK_URL or MONITOR_SECRET is not set; cannot send notification.")
        return

    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(webhook_url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            print(f"GAS webhook responded: HTTP {response.status}")
    except urllib.error.HTTPError as error:
        print(f"GAS webhook HTTP error: {error.code} {error.reason}")
    except urllib.error.URLError as error:
        print(f"GAS webhook request failed: {error.reason}")


def main():
    OUT.mkdir(exist_ok=True)
    storage_state = load_storage_state()
    dry_run = os.environ.get("DRY_RUN", "true").strip().lower() != "false"
    state = load_state()

    all_results = []
    restocks_by_product = {}
    taiwan = "UNKNOWN"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            context_kwargs = dict(locale="en-US", timezone_id="Asia/Tokyo", viewport={"width": 1440, "height": 1600})
            if storage_state is not None:
                context_kwargs["storage_state"] = storage_state
            context = browser.new_context(**context_kwargs)
            page = context.new_page()

            for index, product in enumerate(PRODUCTS):
                if index > 0:
                    delay_ms = int(random.uniform(MIN_PAGE_DELAY_SECONDS, MAX_PAGE_DELAY_SECONDS) * 1000)
                    page.wait_for_timeout(delay_ms)
                try:
                    result, html = capture_product(page, product)
                except Exception as error:
                    result = {"product": product["en"], "page_status": "UNKNOWN", "page_reason": type(error).__name__, "rows": []}
                    html = ""
                all_results.append(result)

                if taiwan == "UNKNOWN" and html:
                    taiwan = taiwan_shipping_status(html)

                restocked = diff_and_update(state, product, result.get("rows", []))
                if restocked:
                    restocks_by_product.setdefault(product["en"], {
                        "zh": product["zh"], "en": product["en"], "url": product["url"], "variants": [],
                    })["variants"].extend(restocked)
        finally:
            browser.close()

    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state)

    for r in all_results:
        print(r.get("product"), r.get("page_status"), r.get("page_reason"))
    print(f"storage_state secret present: {storage_state is not None}")
    print(f"taiwan shipping signal: {taiwan}")
    print(f"DRY_RUN: {dry_run}")

    if restocks_by_product:
        print(f"RESTOCK DETECTED: {len(restocks_by_product)} product(s) -> {list(restocks_by_product.keys())}")
        send_gas_notification(list(restocks_by_product.values()), taiwan, dry_run)
    else:
        print("No SOLD_OUT -> AVAILABLE transitions this run. No notification sent.")


if __name__ == "__main__":
    main()
