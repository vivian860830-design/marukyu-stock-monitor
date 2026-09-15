import re
import time

from playwright.sync_api import sync_playwright


URL = (
    "https://www.marukyu-koyamaen.co.jp/"
    "english/shop/products/1141020c1"
)

NAVIGATION_TIMEOUT = 45_000


def clean(value):
    if value is None:
        return ""

    return re.sub(r"\s+", " ", value).strip()


def main():

    print("=" * 70)
    print("MARUKYU DOM DIAGNOSTIC")
    print("Product: 雲鶴 Unkaku")
    print("=" * 70)

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        context = browser.new_context(
            locale="en-US",
            timezone_id="Asia/Tokyo",
            viewport={
                "width": 1440,
                "height": 1600,
            },
            user_agent=(
                "Mozilla/5.0 "
                "(X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/140.0.0.0 "
                "Safari/537.36"
            ),
        )

        page = context.new_page()

        # ====================================================
        # JS errors
        # ====================================================

        page.on(
            "pageerror",
            lambda error:
            print(
                "PAGE JS ERROR:",
                error
            )
        )

        # ====================================================
        # Response errors
        # ====================================================

        def response_logger(response):

            if response.status >= 400:

                print(
                    "FAILED RESPONSE:",
                    response.status,
                    response.url
                )

        page.on(
            "response",
            response_logger
        )

        # ====================================================
        # Open page
        # ====================================================

        response = page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=NAVIGATION_TIMEOUT,
        )

        print()
        print(
            "MAIN HTTP:",
            response.status
            if response
            else "NO RESPONSE"
        )

        # ====================================================
        # 等頁面 JS
        # ====================================================

        try:

            page.wait_for_load_state(
                "networkidle",
                timeout=20_000,
            )

            print(
                "networkidle: YES"
            )

        except Exception:

            print(
                "networkidle: TIMEOUT"
            )

        # 額外等 5 秒
        page.wait_for_timeout(
            5000
        )

        # ====================================================
        # 基本資料
        # ====================================================

        print()
        print("=" * 70)
        print("PAGE INFORMATION")
        print("=" * 70)

        print(
            "Title:",
            page.title()
        )

        print(
            "URL:",
            page.url
        )

        print(
            "Body length:",
            len(page.content())
        )

        # ====================================================
        # 全頁 Add To Cart
        # ====================================================

        print()
        print("=" * 70)
        print("ADD TO CART CHECK")
        print("=" * 70)

        selectors = [
            "button.single_add_to_cart_button",
            ".single_add_to_cart_button",
            "button[type='submit']",
            "text=Add To Cart",
            "text=Add to cart",
        ]

        for selector in selectors:

            try:

                count = page.locator(
                    selector
                ).count()

            except Exception:

                count = -1

            print(
                selector,
                "=>",
                count
            )

        # ====================================================
        # Product rows
        # ====================================================

        print()
        print("=" * 70)
        print("PRODUCT ROWS")
        print("=" * 70)

        rows = page.locator(
            ".product-form-row"
        )

        print(
            "product-form-row count:",
            rows.count()
        )

        for index in range(
            rows.count()
        ):

            row = rows.nth(index)

            print()
            print(
                "--------------------------------------------------"
            )

            print(
                "ROW",
                index + 1
            )

            print(
                "--------------------------------------------------"
            )

            try:

                variation_id = (
                    row.get_attribute(
                        "data-variation_id"
                    )
                )

            except Exception:

                variation_id = None

            print(
                "variation_id:",
                variation_id
            )

            # -----------------------------------------------
            # Row text
            # -----------------------------------------------

            try:

                text = clean(
                    row.inner_text()
                )

            except Exception as error:

                text = (
                    "ERROR: "
                    + repr(error)
                )

            print(
                "TEXT:",
                text
            )

            # -----------------------------------------------
            # Button count
            # -----------------------------------------------

            try:

                button_count = (
                    row.locator(
                        "button"
                    ).count()
                )

            except Exception:

                button_count = -1

            print(
                "BUTTON COUNT:",
                button_count
            )

            # -----------------------------------------------
            # Add button count
            # -----------------------------------------------

            try:

                add_count = (
                    row.locator(
                        ".single_add_to_cart_button"
                    ).count()
                )

            except Exception:

                add_count = -1

            print(
                "ADD BUTTON COUNT:",
                add_count
            )

            # -----------------------------------------------
            # 完整 row HTML
            # -----------------------------------------------

            try:

                html = row.evaluate(
                    "(el) => el.outerHTML"
                )

            except Exception as error:

                html = (
                    "ERROR: "
                    + repr(error)
                )

            print()
            print(
                "ROW HTML START"
            )

            print(
                html
            )

            print(
                "ROW HTML END"
            )

        # ====================================================
        # Shipping
        # ====================================================

        print()
        print("=" * 70)
        print("SHIPPING CHECK")
        print("=" * 70)

        shipping_selectors = [
            "#calc_shipping_country",
            "select[name='calc_shipping_country']",
            ".shipping-calculator-form",
            ".shipping-calculator-button",
            "#shipping-calculator-form",
        ]

        for selector in shipping_selectors:

            try:

                count = page.locator(
                    selector
                ).count()

            except Exception:

                count = -1

            print(
                selector,
                "=>",
                count
            )

        # ====================================================
        # 搜尋 Taiwan
        # ====================================================

        html = page.content()

        print()
        print(
            "Taiwan occurrences:",
            html.lower().count(
                "taiwan"
            )
        )

        print(
            'value="TW" occurrences:',
            html.upper().count(
                'VALUE="TW"'
            )
        )

        # ====================================================
        # Form
        # ====================================================

        print()
        print("=" * 70)
        print("VARIATION FORM")
        print("=" * 70)

        forms = page.locator(
            "form.variations_form"
        )

        print(
            "variation form count:",
            forms.count()
        )

        if forms.count() > 0:

            form = forms.first

            try:

                print(
                    form.evaluate(
                        "(el) => el.outerHTML"
                    )
                )

            except Exception as error:

                print(
                    "Unable to output form:",
                    repr(error)
                )

        # ====================================================
        # WooCommerce / jQuery
        # ====================================================

        print()
        print("=" * 70)
        print("JAVASCRIPT CHECK")
        print("=" * 70)

        try:

            jquery = page.evaluate(
                "() => typeof window.jQuery"
            )

            print(
                "window.jQuery:",
                jquery
            )

        except Exception as error:

            print(
                "jQuery check failed:",
                repr(error)
            )

        try:

            wc_variation = page.evaluate(
                """
                () => {
                    if (!window.jQuery) {
                        return "NO_JQUERY";
                    }

                    return typeof (
                        window.jQuery.fn
                        .wc_variation_form
                    );
                }
                """
            )

            print(
                "wc_variation_form:",
                wc_variation
            )

        except Exception as error:

            print(
                "WooCommerce variation check failed:",
                repr(error)
            )

        # ====================================================
        # Screenshot
        # ====================================================

        try:

            page.screenshot(
                path="unkaku-debug.png",
                full_page=True,
            )

            print()
            print(
                "Screenshot saved:"
            )

            print(
                "unkaku-debug.png"
            )

        except Exception as error:

            print(
                "Screenshot failed:",
                repr(error)
            )

        context.close()
        browser.close()

    print()
    print("=" * 70)
    print("DIAGNOSTIC COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    main()
