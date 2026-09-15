"""Static-HTML SKU stock classifier for Marukyu Koyamaen product pages.

Shared by monitor.py (fed live page.content() from Playwright) and
offline_regression_test.py (fed saved HTML snapshots), so the exact same
rule set is what gets tested offline and what runs in GitHub Actions.

Design rules carried over from the handoff (README-交接說明.md section 7-8),
now enforced in code instead of only in prose:

- Never infer stock from price alone.
- Never infer stock from "has an Add to cart button" alone — every row,
  in stock or not, HAS the button; only its disabled state differs.
- Read the explicit `.stock` element's class (`in-stock` / `out-of-stock`)
  and cross-check it against the button's disabled state. Agreement is
  required for a definite AVAILABLE/SOLD_OUT. Any missing element,
  disagreement between the two signals, or Cloudflare/login gating is
  UNKNOWN — this module never guesses to fill a gap.
"""
from __future__ import annotations

from bs4 import BeautifulSoup

CHALLENGE_TITLE_MARKERS = ("just a moment",)
CHALLENGE_BODY_MARKERS = (
    "verify you are human",
    "performing security verification",
)
LOGIN_BODY_MARKERS = (
    "register and login to shop",
    "you must register and login",
)


def page_signals(html: str) -> dict:
    """Page-level signals: Cloudflare challenge, login gate, logged-in marker."""
    soup = BeautifulSoup(html, "lxml")
    title = (soup.title.string or "") if soup.title else ""
    body_text = soup.get_text(" ", strip=True).lower()
    challenge = any(m in title.lower() for m in CHALLENGE_TITLE_MARKERS) or any(
        m in body_text for m in CHALLENGE_BODY_MARKERS
    )
    login_required = any(m in body_text for m in LOGIN_BODY_MARKERS)
    body_classes = soup.body.get("class", []) if soup.body else []
    logged_in_marker = "logged-in" in body_classes or bool(
        soup.select_one('a[href*="customer-logout"]')
    )
    return {
        "challenge": challenge,
        "login_required": login_required,
        "logged_in_marker": logged_in_marker,
        "title": title.strip(),
    }


def classify_row(row) -> dict:
    """Classify a single `.product-form-row[data-variation_id]` element."""
    variation_id = row.get("data-variation_id", "")
    sku_el = row.select_one(".pa-sku dd")
    size_el = row.select_one(".pa-size dd")
    sku = sku_el.get_text(strip=True) if sku_el else ""
    size = size_el.get_text(strip=True) if size_el else ""

    stock_el = row.select_one(".stock")
    btn = row.select_one("button.single_add_to_cart_button")

    stock_classes = stock_el.get("class", []) if stock_el else []
    stock_class_str = " ".join(stock_classes) if stock_el else None
    in_stock_class = "in-stock" in stock_classes
    out_of_stock_class = "out-of-stock" in stock_classes

    btn_disabled = None
    if btn is not None:
        btn_disabled = (
            btn.has_attr("disabled")
            or btn.get("aria-disabled") == "true"
            or "disabled" in (btn.get("class") or [])
        )

    if stock_el is None or btn is None:
        status, reason = "UNKNOWN", "NO_STOCK_MARKUP"
    elif in_stock_class and out_of_stock_class:
        status, reason = "UNKNOWN", "CONFLICTING_STOCK_CLASS"
    elif in_stock_class and btn_disabled is False:
        status, reason = "AVAILABLE", "STOCK_CLASS_AND_BUTTON_AGREE"
    elif out_of_stock_class and btn_disabled is True:
        status, reason = "SOLD_OUT", "STOCK_CLASS_AND_BUTTON_AGREE"
    elif in_stock_class or out_of_stock_class:
        status, reason = "UNKNOWN", "STOCK_CLASS_BUTTON_MISMATCH"
    else:
        status, reason = "UNKNOWN", "NO_STOCK_CLASS"

    return {
        "variation_id": variation_id,
        "sku": sku,
        "size": size,
        "stock_class": stock_class_str,
        "button_disabled": btn_disabled,
        "status": status,
        "reason": reason,
    }


def classify_page(html: str) -> dict:
    """Classify every SKU row on one product page snapshot."""
    signals = page_signals(html)
    soup = BeautifulSoup(html, "lxml")
    rows = soup.select(".product-form-row[data-variation_id]")
    results = [classify_row(r) for r in rows]

    if signals["challenge"]:
        for r in results:
            r["status"], r["reason"] = "UNKNOWN", "CLOUDFLARE_CHALLENGE"
        page_status = "UNKNOWN"
        page_reason = "CLOUDFLARE_CHALLENGE"
    elif not rows:
        page_status, page_reason = "UNKNOWN", "TARGET_MISSING"
    elif signals["login_required"] or (
        not signals["logged_in_marker"] and all(r["stock_class"] is None for r in results)
    ):
        for r in results:
            r["status"] = "UNKNOWN"
            r["reason"] = "LOGIN_REQUIRED"
        page_status, page_reason = "UNKNOWN", "LOGIN_REQUIRED"
    else:
        page_status, page_reason = "OK", "ROWS_CLASSIFIED"

    return {"page": signals, "page_status": page_status, "page_reason": page_reason, "rows": results}
