import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright


URL = (
    "https://www.marukyu-koyamaen.co.jp/"
    "english/shop/products/1151020c1"
)

TARGET_SKU = "1151040C1"
TARGET_VARIATION_ID = "16925"

OUTPUT_DIR = Path("diagnostic-output")
OUTPUT_DIR.mkdir(exist_ok=True)

NAVIGATION_TIMEOUT = 45_000


def clean(value):
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value)
    ).strip()


def safe_json(value):
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            default=str
        )
    except Exception:
        return repr(value)


def diagnose(browser, mode_name):

    print()
    print("=" * 80)
    print(f"MODE: {mode_name}")
    print("=" * 80)

    context = browser.new_context(
        locale="en-US",
        timezone_id="Asia/Tokyo",
        viewport={
            "width": 1440,
            "height": 1600,
        },
        extra_http_headers={
            "Accept-Language":
                "en-US,en;q=0.9",
        },
    )

    page = context.new_page()

    network_records = []

    # ========================================================
    # Browser / JS errors
    # ========================================================

    page.on(
        "pageerror",
        lambda error: print(
            "[PAGE ERROR]",
            error
        )
    )

    page.on(
        "console",
        lambda message: (
            print(
                "[CONSOLE ERROR]",
                message.text
            )
            if message.type == "error"
            else None
        )
    )

    # ========================================================
    # Network responses
    # ========================================================

    def handle_response(response):

        request = response.request

        resource_type = request.resource_type

        url_lower = response.url.lower()

        interesting = (
            resource_type in (
                "xhr",
                "fetch"
            )
            or
            "wc-ajax" in url_lower
            or
            "woocommerce" in url_lower
            or
            "variation" in url_lower
            or
            "shipping" in url_lower
            or
            "cart" in url_lower
        )

        if not interesting:
            return

        record = {
            "status": response.status,
            "resource_type": resource_type,
            "method": request.method,
            "url": response.url,
        }

        try:

            content_type = (
                response.headers.get(
                    "content-type",
                    ""
                )
            )

            record["content_type"] = (
                content_type
            )

            if (
                "json" in content_type.lower()
                or
                "text" in content_type.lower()
                or
                "javascript" in content_type.lower()
                or
                "html" in content_type.lower()
            ):

                body = response.text()

                if len(body) > 20_000:
                    body = (
                        body[:20_000]
                        + "\n...[TRUNCATED]..."
                    )

                record["body"] = body

        except Exception as error:

            record["body_error"] = (
                repr(error)
            )

        network_records.append(
            record
        )

    page.on(
        "response",
        handle_response
    )

    # ========================================================
    # Navigate
    # ========================================================

    response = page.goto(
        URL,
        wait_until="domcontentloaded",
        timeout=NAVIGATION_TIMEOUT,
    )

    print(
        "MAIN HTTP:",
        response.status
        if response
        else "NO RESPONSE"
    )

    try:

        page.wait_for_load_state(
            "networkidle",
            timeout=20_000,
        )

        print(
            "NETWORK IDLE: YES"
        )

    except Exception:

        print(
            "NETWORK IDLE: TIMEOUT"
        )

    # 額外等 WooCommerce JS
    page.wait_for_timeout(
        8000
    )

    print(
        "TITLE:",
        page.title()
    )

    print(
        "URL:",
        page.url
    )

    # ========================================================
    # Browser fingerprint
    # ========================================================

    print()
    print("-" * 80)
    print("BROWSER ENVIRONMENT")
    print("-" * 80)

    browser_environment = (
        page.evaluate(
            """
            () => ({
                userAgent: navigator.userAgent,
                webdriver: navigator.webdriver,
                language: navigator.language,
                languages: navigator.languages,
                platform: navigator.platform,
                vendor: navigator.vendor,
                hardwareConcurrency:
                    navigator.hardwareConcurrency,
                deviceMemory:
                    navigator.deviceMemory || null,
                timezone:
                    Intl.DateTimeFormat()
                        .resolvedOptions()
                        .timeZone,
                screen: {
                    width: screen.width,
                    height: screen.height,
                    colorDepth: screen.colorDepth
                }
            })
            """
        )
    )

    print(
        safe_json(
            browser_environment
        )
    )

    # ========================================================
    # Cookies
    # ========================================================

    print()
    print("-" * 80)
    print("COOKIES")
    print("-" * 80)

    cookies = context.cookies()

    for cookie in cookies:

        print(
            cookie.get("name"),
            "=",
            cookie.get("value")
        )

    # ========================================================
    # Product rows
    # ========================================================

    print()
    print("-" * 80)
    print("PRODUCT ROWS")
    print("-" * 80)

    rows = page.locator(
        ".product-form-row"
    )

    print(
        "ROW COUNT:",
        rows.count()
    )

    for index in range(
        rows.count()
    ):

        row = rows.nth(index)

        variation_id = (
            row.get_attribute(
                "data-variation_id"
            )
        )

        text = clean(
            row.inner_text()
        )

        buttons = row.locator(
            "button"
        )

        add_buttons = row.locator(
            "button.single_add_to_cart_button"
        )

        print()
        print(
            f"ROW {index + 1}"
        )

        print(
            "variation_id:",
            variation_id
        )

        print(
            "text:",
            text
        )

        print(
            "button count:",
            buttons.count()
        )

        print(
            "add-to-cart count:",
            add_buttons.count()
        )

        if (
            variation_id
            == TARGET_VARIATION_ID
        ):

            print()
            print(
                "*** TARGET KINRIN 40g ROW ***"
            )

            html = row.evaluate(
                "(el) => el.outerHTML"
            )

            print(html)

            (
                OUTPUT_DIR
                / f"{mode_name}-kinrin-40g.html"
            ).write_text(
                html,
                encoding="utf-8"
            )

    # ========================================================
    # variations_form
    # ========================================================

    print()
    print("-" * 80)
    print("VARIATIONS FORM")
    print("-" * 80)

    forms = page.locator(
        "form.variations_form"
    )

    print(
        "variations_form count:",
        forms.count()
    )

    if forms.count() > 0:

        form = forms.first

        attributes = (
            form.evaluate(
                """
                el => {
                    const result = {};

                    for (
                        const attr
                        of el.attributes
                    ) {
                        result[attr.name]
                            = attr.value;
                    }

                    return result;
                }
                """
            )
        )

        print(
            "FORM ATTRIBUTES:"
        )

        print(
            safe_json(
                attributes
            )
        )

        product_variations = (
            form.get_attribute(
                "data-product_variations"
            )
        )

        print()
        print(
            "data-product_variations present:",
            bool(product_variations)
        )

        if product_variations:

            print(
                "data-product_variations length:",
                len(product_variations)
            )

            try:

                parsed = json.loads(
                    product_variations
                )

                print(
                    "variation objects:",
                    len(parsed)
                    if isinstance(
                        parsed,
                        list
                    )
                    else "NOT LIST"
                )

                if isinstance(
                    parsed,
                    list
                ):

                    for variation in parsed:

                        variation_id = str(
                            variation.get(
                                "variation_id",
                                ""
                            )
                        )

                        if (
                            variation_id
                            == TARGET_VARIATION_ID
                        ):

                            print()
                            print(
                                "*** TARGET VARIATION JSON ***"
                            )

                            print(
                                safe_json(
                                    variation
                                )
                            )

            except Exception as error:

                print(
                    "Cannot parse "
                    "data-product_variations:",
                    repr(error)
                )

    # ========================================================
    # WooCommerce JS globals
    # ========================================================

    print()
    print("-" * 80)
    print("WOOCOMMERCE / JQUERY")
    print("-" * 80)

    js_environment = page.evaluate(
        """
        () => ({
            jquery:
                typeof window.jQuery
                    !== "undefined",

            wcVariationForm:
                typeof window.jQuery
                    !== "undefined"
                &&
                typeof window.jQuery.fn
                    .wc_variation_form
                    !== "undefined",

            wcAddToCartParams:
                typeof window
                    .wc_add_to_cart_params
                    !== "undefined",

            wcCartFragmentsParams:
                typeof window
                    .wc_cart_fragments_params
                    !== "undefined",

            wcCheckoutParams:
                typeof window
                    .wc_checkout_params
                    !== "undefined"
        })
        """
    )

    print(
        safe_json(
            js_environment
        )
    )

    # ========================================================
    # Search entire rendered HTML
    # ========================================================

    print()
    print("-" * 80)
    print("RENDERED HTML SEARCH")
    print("-" * 80)

    html = page.content()

    searches = [
        TARGET_SKU,
        TARGET_VARIATION_ID,
        "Add to cart",
        "add_to_cart",
        "is_in_stock",
        "is_purchasable",
        "variation_is_active",
        "variation_is_visible",
        "availability_html",
        "stock_status",
        "outofstock",
        "instock",
        "calc_shipping_country",
        "shipping-calculator-form",
        "United States",
        'value="US"',
        "Taiwan",
        'value="TW"',
    ]

    html_lower = html.lower()

    for search in searches:

        count = html_lower.count(
            search.lower()
        )

        print(
            f"{search}: {count}"
        )

    # ========================================================
    # Context around target SKU / variation
    # ========================================================

    print()
    print("-" * 80)
    print("TARGET CONTEXT")
    print("-" * 80)

    for needle in (
        TARGET_SKU,
        TARGET_VARIATION_ID,
        "is_in_stock",
        "is_purchasable",
    ):

        position = (
            html_lower.find(
                needle.lower()
            )
        )

        print()
        print(
            "SEARCH:",
            needle
        )

        if position == -1:

            print(
                "NOT FOUND"
            )

            continue

        start = max(
            0,
            position - 1500
        )

        end = min(
            len(html),
            position + 3000
        )

        print(
            html[start:end]
        )

    # ========================================================
    # Scripts
    # ========================================================

    print()
    print("-" * 80)
    print("INLINE SCRIPT SEARCH")
    print("-" * 80)

    scripts = page.locator(
        "script"
    )

    print(
        "SCRIPT COUNT:",
        scripts.count()
    )

    interesting_scripts = []

    keywords = [
        TARGET_SKU.lower(),
        TARGET_VARIATION_ID.lower(),
        "is_in_stock",
        "is_purchasable",
        "variation_is_active",
        "calc_shipping_country",
        "shipping-calculator",
    ]

    for index in range(
        scripts.count()
    ):

        script = scripts.nth(
            index
        )

        try:

            text = script.text_content() or ""

        except Exception:

            continue

        lower = text.lower()

        matched = [
            keyword
            for keyword in keywords
            if keyword in lower
        ]

        if not matched:
            continue

        print()
        print(
            f"SCRIPT {index + 1}"
        )

        print(
            "MATCHED:",
            ", ".join(
                matched
            )
        )

        preview = text

        if len(preview) > 12_000:

            preview = (
                preview[:12_000]
                + "\n...[TRUNCATED]..."
            )

        print(
            preview
        )

        interesting_scripts.append({
            "index": index + 1,
            "matched": matched,
            "content": text,
        })

    # ========================================================
    # Network
    # ========================================================

    print()
    print("-" * 80)
    print("XHR / FETCH / WOOCOMMERCE NETWORK")
    print("-" * 80)

    print(
        "Interesting responses:",
        len(network_records)
    )

    for index, record in enumerate(
        network_records,
        start=1
    ):

        print()
        print(
            f"NETWORK {index}"
        )

        print(
            "STATUS:",
            record.get(
                "status"
            )
        )

        print(
            "TYPE:",
            record.get(
                "resource_type"
            )
        )

        print(
            "METHOD:",
            record.get(
                "method"
            )
        )

        print(
            "URL:",
            record.get(
                "url"
            )
        )

        body = record.get(
            "body"
        )

        if body:

            body_lower = (
                body.lower()
            )

            important = any(
                keyword in body_lower
                for keyword in (
                    TARGET_SKU.lower(),
                    TARGET_VARIATION_ID,
                    "is_in_stock",
                    "is_purchasable",
                    "variation",
                    "shipping",
                )
            )

            if important:

                print(
                    "BODY:"
                )

                print(
                    body
                )

    # ========================================================
    # Save artifacts
    # ========================================================

    (
        OUTPUT_DIR
        / f"{mode_name}-page.html"
    ).write_text(
        html,
        encoding="utf-8"
    )

    (
        OUTPUT_DIR
        / f"{mode_name}-network.json"
    ).write_text(
        json.dumps(
            network_records,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8"
    )

    (
        OUTPUT_DIR
        / f"{mode_name}-scripts.json"
    ).write_text(
        json.dumps(
            interesting_scripts,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8"
    )

    page.screenshot(
        path=str(
            OUTPUT_DIR
            / f"{mode_name}-screenshot.png"
        ),
        full_page=True,
    )

    print()
    print(
        "Artifacts saved for:",
        mode_name
    )

    context.close()


def main():

    print("=" * 80)
    print("MARUKYU GITHUB ENVIRONMENT DIAGNOSTIC")
    print("=" * 80)

    with sync_playwright() as p:

        # ====================================================
        # TEST 1 — HEADLESS
        # ====================================================

        print()
        print(
            "Starting HEADLESS Chromium..."
        )

        headless_browser = (
            p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                ],
            )
        )

        try:

            diagnose(
                headless_browser,
                "headless"
            )

        finally:

            headless_browser.close()

        # ====================================================
        # TEST 2 — HEADED
        #
        # GitHub workflow 會透過 xvfb-run 執行。
        # ====================================================

        print()
        print(
            "Starting HEADED Chromium..."
        )

        headed_browser = (
            p.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                ],
            )
        )

        try:

            diagnose(
                headed_browser,
                "headed"
            )

        finally:

            headed_browser.close()

    print()
    print("=" * 80)
    print("DIAGNOSTIC COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()
