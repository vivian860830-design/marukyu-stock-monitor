import re

from playwright.sync_api import sync_playwright


URL = (
    "https://www.marukyu-koyamaen.co.jp/"
    "english/shop/products/1151020c1"
)

NAVIGATION_TIMEOUT = 45_000


def clean(value):
    if value is None:
        return ""

    return re.sub(r"\s+", " ", value).strip()


def main():

    print("=" * 70)
    print("MARUKYU KINRIN DIAGNOSTIC")
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
        # JS / HTTP 錯誤
        # ====================================================

        page.on(
            "pageerror",
            lambda error:
            print(
                "PAGE JS ERROR:",
                error
            )
        )

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
        # 開 Kinrin
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
        # 等待網站 JS
        # ====================================================

        try:

            page.wait_for_load_state(
                "networkidle",
                timeout=20_000,
            )

            print("NETWORK IDLE: YES")

        except Exception:

            print("NETWORK IDLE: TIMEOUT")

        # 再額外等 8 秒
        page.wait_for_timeout(
            8000
        )

        print()
        print("=" * 70)
        print("PAGE")
        print("=" * 70)

        print(
            "TITLE:",
            page.title()
        )

        print(
            "HTML LENGTH:",
            len(page.content())
        )

        # ====================================================
        # PRODUCT ROWS
        # ====================================================

        print()
        print("=" * 70)
        print("PRODUCT ROWS")
        print("=" * 70)

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

                text = clean(
                    row.inner_text()
                )

            except Exception as error:

                text = repr(error)

            print(
                "TEXT:",
                text
            )

            # -----------------------------------------------
            # Variation ID
            # -----------------------------------------------

            try:

                variation_id = (
                    row.get_attribute(
                        "data-variation_id"
                    )
                )

            except Exception:

                variation_id = ""

            print(
                "VARIATION ID:",
                variation_id
            )

            # -----------------------------------------------
            # 所有 button
            # -----------------------------------------------

            buttons = row.locator(
                "button"
            )

            print(
                "BUTTON COUNT:",
                buttons.count()
            )

            for button_index in range(
                buttons.count()
            ):

                button = buttons.nth(
                    button_index
                )

                try:

                    print(
                        "BUTTON",
                        button_index + 1,
                        ":",
                        clean(
                            button.inner_text()
                        ),
                        "| class =",
                        button.get_attribute(
                            "class"
                        )
                    )

                except Exception as error:

                    print(
                        "BUTTON ERROR:",
                        repr(error)
                    )

            # -----------------------------------------------
            # Add To Cart selector
            # -----------------------------------------------

            add_buttons = row.locator(
                "button.single_add_to_cart_button"
            )

            print(
                "single_add_to_cart_button:",
                add_buttons.count()
            )

            # -----------------------------------------------
            # HTML
            # -----------------------------------------------

            try:

                html = row.evaluate(
                    "(element) => element.outerHTML"
                )

                print()
                print("ROW HTML START")
                print(html)
                print("ROW HTML END")

            except Exception as error:

                print(
                    "HTML ERROR:",
                    repr(error)
                )

        # ====================================================
        # 全頁 Add To Cart
        # ====================================================

        print()
        print("=" * 70)
        print("GLOBAL ADD TO CART")
        print("=" * 70)

        selectors = [
            "button.single_add_to_cart_button",
            ".single_add_to_cart_button",
            "button[type='submit']",
        ]

        for selector in selectors:

            try:

                print(
                    selector,
                    "=>",
                    page.locator(
                        selector
                    ).count()
                )

            except Exception as error:

                print(
                    selector,
                    "ERROR",
                    repr(error)
                )

        # ====================================================
        # SHIPPING
        # ====================================================

        print()
        print("=" * 70)
        print("SHIPPING")
        print("=" * 70)

        shipping_selectors = [
            "#shipping-calculator-form",
            ".shipping-calculator-form",
            "#calc_shipping_country",
            "select[name='calc_shipping_country']",
            "#calc_shipping_state",
            "#calc_shipping_city",
            "#calc_shipping_postcode",
        ]

        for selector in shipping_selectors:

            try:

                count = page.locator(
                    selector
                ).count()

                print(
                    selector,
                    "=>",
                    count
                )

            except Exception as error:

                print(
                    selector,
                    "ERROR:",
                    repr(error)
                )

        # ====================================================
        # Country select
        # ====================================================

        country = page.locator(
            "#calc_shipping_country"
        )

        if country.count() > 0:

            print()
            print(
                "COUNTRY SELECT FOUND"
            )

            options = country.locator(
                "option"
            )

            print(
                "COUNTRY OPTION COUNT:",
                options.count()
            )

            targets = {
                "US": False,
                "GB": False,
                "TW": False,
            }

            for index in range(
                options.count()
            ):

                option = options.nth(
                    index
                )

                value = clean(
                    option.get_attribute(
                        "value"
                    )
                ).upper()

                text = clean(
                    option.inner_text()
                )

                if value in targets:

                    targets[value] = True

                    print(
                        "FOUND:",
                        value,
                        "|",
                        text
                    )

            print()
            print(
                "US:",
                "FOUND"
                if targets["US"]
                else "NOT FOUND"
            )

            print(
                "GB:",
                "FOUND"
                if targets["GB"]
                else "NOT FOUND"
            )

            print(
                "TW:",
                "FOUND"
                if targets["TW"]
                else "NOT FOUND"
            )

        else:

            print()
            print(
                "COUNTRY SELECT NOT FOUND"
            )

        # ====================================================
        # 搜尋 HTML
        # ====================================================

        html = page.content()

        print()
        print("=" * 70)
        print("HTML SEARCH")
        print("=" * 70)

        print(
            "Add to cart:",
            html.lower().count(
                "add to cart"
            )
        )

        print(
            "calc_shipping_country:",
            html.lower().count(
                "calc_shipping_country"
            )
        )

        print(
            "United States:",
            html.lower().count(
                "united states"
            )
        )

        print(
            "Taiwan:",
            html.lower().count(
                "taiwan"
            )
        )

        print(
            'value="US":',
            html.upper().count(
                'VALUE="US"'
            )
        )

        print(
            'value="TW":',
            html.upper().count(
                'VALUE="TW"'
            )
        )

        # ====================================================
        # Screenshot
        # ====================================================

        page.screenshot(
            path="kinrin-debug.png",
            full_page=True,
        )

        print()
        print(
            "Screenshot saved: kinrin-debug.png"
        )

        context.close()
        browser.close()

    print()
    print("=" * 70)
    print("DIAGNOSTIC COMPLETED")
    print("=" * 70)


if __name__ == "__main__":
    main()
