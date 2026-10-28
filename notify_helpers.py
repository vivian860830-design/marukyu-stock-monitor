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
