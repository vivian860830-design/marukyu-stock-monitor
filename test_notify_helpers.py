from notify_helpers import apply_taiwan_shipping, gas_response_ok, decide_taiwan

NOW = "2026-10-24T00:00:00+00:00"
calls = []


def ok():
    calls.append(1)
    return True


def fail():
    calls.append(1)
    return False


def run(state, taiwan, notify=ok):
    calls.clear()
    return apply_taiwan_shipping(state, taiwan, NOW, notify), len(calls)


def check(name, got, want):
    assert got == want, f"FAIL {name}: got {got!r}, want {want!r}"
    print("PASS", name)


# --- first sight: baseline only, never notifies
s = {}
check("first AVAILABLE -> baseline, no notify", run(s, "AVAILABLE"), ("BASELINE", 0))
check("baseline stored", s["taiwan_shipping"]["status"], "AVAILABLE")
s = {}
check("first UNAVAILABLE -> baseline", run(s, "UNAVAILABLE"), ("BASELINE", 0))

# --- UNKNOWN never touches state
s = {"taiwan_shipping": {"status": "UNAVAILABLE", "observed_at": "old"}}
check("UNKNOWN skipped", run(s, "UNKNOWN"), ("SKIPPED_UNKNOWN", 0))
check("UNKNOWN leaves state", s["taiwan_shipping"], {"status": "UNAVAILABLE", "observed_at": "old"})
s = {}
check("UNKNOWN with no state creates nothing", (run(s, "UNKNOWN"), s), (("SKIPPED_UNKNOWN", 0), {}))

# --- unchanged
s = {"taiwan_shipping": {"status": "UNAVAILABLE", "observed_at": "old"}}
check("unchanged UNAVAILABLE", run(s, "UNAVAILABLE"), ("UNCHANGED", 0))
check("unchanged keeps observed_at", s["taiwan_shipping"]["observed_at"], "old")

# --- the one real notification
s = {"taiwan_shipping": {"status": "UNAVAILABLE", "observed_at": "old"}}
check("UNAVAILABLE->AVAILABLE notifies", run(s, "AVAILABLE"), ("NOTIFIED", 1))
check("state advanced after success", s["taiwan_shipping"]["status"], "AVAILABLE")

# --- notify failure: state not advanced, retried next run
s = {"taiwan_shipping": {"status": "UNAVAILABLE", "observed_at": "old"}}
check("notify failure", run(s, "AVAILABLE", fail), ("NOTIFY_FAILED_WILL_RETRY", 1))
check("state NOT advanced on failure", s["taiwan_shipping"]["status"], "UNAVAILABLE")
check("next run retries and succeeds", run(s, "AVAILABLE"), ("NOTIFIED", 1))

# --- closing: state updates, no notification
s = {"taiwan_shipping": {"status": "AVAILABLE", "observed_at": "old"}}
check("AVAILABLE->UNAVAILABLE no notify", run(s, "UNAVAILABLE"), ("CLOSED", 0))
check("closed state stored", s["taiwan_shipping"]["status"], "UNAVAILABLE")

# --- malformed stored entry is treated as no baseline
s = {"taiwan_shipping": "garbage"}
check("malformed entry -> baseline", run(s, "AVAILABLE"), ("BASELINE", 0))

# --- GAS response check
check("200 OK", gas_response_ok(200, "OK"), True)
check("200 ERROR", gas_response_ok(200, "ERROR"), False)
check("200 error lowercase", gas_response_ok(200, " error: x"), False)
check("500", gas_response_ok(500, "OK"), False)
check("empty body 200", gas_response_ok(200, ""), True)

# --- decide_taiwan: first case is the REAL diag_after from the 2026-10-31 GitHub run
real = {"title": "Checkout | Shopping cart | Marukyu Koyamaen Online Shop", "challenge": False,
        "logged_in": True, "checkout_form_present": True, "cart_items": 1, "shipping_row": True,
        "destination_p": False, "not_enabled_class": False, "no_options_message": False,
        "shipping_method_inputs": 1, "checkbox_present": True, "checkbox_checked": False,
        "path": "/english/shop/cart/checkout"}
check("real 10/31 page, classifier UNKNOWN -> AVAILABLE", decide_taiwan("UNKNOWN", real), ("AVAILABLE", "SHIPPING_METHOD_PRESENT"))
check("classifier definite answer wins", decide_taiwan("UNAVAILABLE", real), ("UNAVAILABLE", "CHECKOUT_SHIPPING_READ"))
check("no-options message -> UNAVAILABLE",
      decide_taiwan("UNKNOWN", dict(real, no_options_message=True, shipping_method_inputs=0)), ("UNAVAILABLE", "NO_SHIPPING_OPTIONS_MESSAGE"))
check("not-enabled class -> UNAVAILABLE",
      decide_taiwan("UNKNOWN", dict(real, not_enabled_class=True, shipping_method_inputs=0)), ("UNAVAILABLE", "NO_SHIPPING_OPTIONS_MESSAGE"))
check("challenge -> UNKNOWN", decide_taiwan("UNKNOWN", dict(real, challenge=True))[0], "UNKNOWN")
check("logged out -> UNKNOWN", decide_taiwan("UNKNOWN", dict(real, logged_in=False))[0], "UNKNOWN")
check("not checkout -> UNKNOWN", decide_taiwan("UNKNOWN", dict(real, checkout_form_present=False))[0], "UNKNOWN")
check("empty cart -> UNKNOWN", decide_taiwan("UNKNOWN", dict(real, cart_items=0))[0], "UNKNOWN")
check("no shipping row -> UNKNOWN", decide_taiwan("UNKNOWN", dict(real, shipping_row=False))[0], "UNKNOWN")
check("billing country JP -> UNKNOWN", decide_taiwan("UNKNOWN", dict(real, billing_country="JP")), ("UNKNOWN", "BILLING_COUNTRY_NOT_TW"))
check("billing country TW ok", decide_taiwan("UNKNOWN", dict(real, billing_country="TW"))[0], "AVAILABLE")
check("billing country missing ok", decide_taiwan("UNKNOWN", dict(real, billing_country=None))[0], "AVAILABLE")
check("no message and no method -> UNKNOWN", decide_taiwan("UNKNOWN", dict(real, shipping_method_inputs=0)), ("UNKNOWN", "NO_MESSAGE_AND_NO_METHOD"))
check("diag missing -> UNKNOWN", decide_taiwan("UNKNOWN", None), ("UNKNOWN", "DIAG_UNAVAILABLE"))
check("diag error -> UNKNOWN", decide_taiwan("UNKNOWN", {"error": "Error"}), ("UNKNOWN", "DIAG_UNAVAILABLE"))
print("ALL PASSED")
