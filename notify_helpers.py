"""Pure helpers for aggregate.py (no network, no file I/O, easy to test offline).

1. apply_taiwan_shipping(): tracks Taiwan shippability in stock_state.json and
   notifies ONLY on UNAVAILABLE -> AVAILABLE.
   - taiwan values come from capture_taiwan.py / stock_classifier:
     "AVAILABLE" | "UNAVAILABLE" | "UNKNOWN".
   - UNKNOWN never overwrites the stored state and never notifies.
   - The first reading is recorded as baseline only (no notification).
   - If the notification fails, the stored state is NOT advanced, so the next
     run sees UNAVAILABLE -> AVAILABLE again and retries.
   - AVAILABLE -> UNAVAILABLE just updates the state, no notification.

2. gas_response_ok(): the Apps Script web app always answers HTTP 200, even when
   it rejected the payload (wrong secret, unknown payload shape, ...). The
   patched Code.gs answers with a body starting with "ERROR" in that case. An
   un-patched Code.gs answers "OK" for everything, so this check cannot detect
   failures until Code.gs is redeployed with the patch.
"""

KEY = "taiwan_shipping"
KNOWN = ("AVAILABLE", "UNAVAILABLE")


def apply_taiwan_shipping(state, taiwan, now_iso, notify):
    """Mutates `state`. `notify` is a zero-argument callable returning True on
    success. Returns a short action string for logging."""
    if taiwan not in KNOWN:
        return "SKIPPED_UNKNOWN"
    entry = state.get(KEY)
    previous = entry.get("status") if isinstance(entry, dict) else None
    record = {"status": taiwan, "observed_at": now_iso}
    if previous not in KNOWN:
        state[KEY] = record
        return "BASELINE"
    if previous == taiwan:
        return "UNCHANGED"
    if previous == "UNAVAILABLE" and taiwan == "AVAILABLE":
        if notify():
            state[KEY] = record
            return "NOTIFIED"
        return "NOTIFY_FAILED_WILL_RETRY"
    state[KEY] = record  # AVAILABLE -> UNAVAILABLE
    return "CLOSED"


def gas_response_ok(status, body):
    """True only for a 2xx response whose body does not start with ERROR."""
    return 200 <= status < 300 and not (body or "").strip().upper().startswith("ERROR")


def decide_taiwan(html_status, diag):
    """Decide the Taiwan shipping signal from (a) the existing HTML classifier
    result and (b) the boolean diagnostics read from the live checkout page
    AFTER the "ship to a different address" box was unchecked.
    Returns (taiwan, reason); taiwan is AVAILABLE / UNAVAILABLE / UNKNOWN.

    Added 2026-10-31 after a real GitHub run showed the checkout page with
    shipping_row=True, shipping_method_inputs=1, no "No shipping options"
    message and no p.woocommerce-shipping-destination element: the old HTML
    classifier only recognises that destination element, so it answered
    UNKNOWN for what looks like a page that has a shipping method.
    Rules (fail closed):
      1. A definite answer from the HTML classifier wins.
      2. Otherwise every precondition must hold: no Cloudflare challenge,
         logged in, checkout form present, cart not empty, shipping row
         present. If not -> UNKNOWN.
      3. A billing country that is present and is not TW -> UNKNOWN.
      4. The "No shipping options were found" message (or the not-enabled
         class) -> UNAVAILABLE.
      5. At least one shipping_method input -> AVAILABLE.
      6. Anything else -> UNKNOWN.
    """
    if html_status in ("AVAILABLE", "UNAVAILABLE"):
        return html_status, "CHECKOUT_SHIPPING_READ"
    d = diag or {}
    if "error" in d or not d:
        return "UNKNOWN", "DIAG_UNAVAILABLE"
    if d.get("challenge"):
        return "UNKNOWN", "CLOUDFLARE_CHALLENGE"
    if not d.get("logged_in"):
        return "UNKNOWN", "NOT_LOGGED_IN"
    if not d.get("checkout_form_present"):
        return "UNKNOWN", "NOT_ON_CHECKOUT"
    if not d.get("cart_items"):
        return "UNKNOWN", "CART_EMPTY"
    if not d.get("shipping_row"):
        return "UNKNOWN", "NO_SHIPPING_ROW"
    country = d.get("billing_country")
    if country not in (None, "") and str(country).upper() != "TW":
        return "UNKNOWN", "BILLING_COUNTRY_NOT_TW"
    if d.get("no_options_message") or d.get("not_enabled_class"):
        return "UNAVAILABLE", "NO_SHIPPING_OPTIONS_MESSAGE"
    if (d.get("shipping_method_inputs") or 0) > 0:
        return "AVAILABLE", "SHIPPING_METHOD_PRESENT"
    return "UNKNOWN", "NO_MESSAGE_AND_NO_METHOD"
