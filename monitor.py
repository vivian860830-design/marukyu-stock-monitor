import os
import json
import re
import time
import random
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# ============================================================
# 基本設定
# ============================================================

GAS_WEBHOOK_URL = os.environ.get("GAS_WEBHOOK_URL", "").strip()
MONITOR_SECRET = os.environ.get("MONITOR_SECRET", "").strip()

STATE_FILE = Path("stock_state.json")

NAVIGATION_TIMEOUT = 45_000
PRODUCT_RENDER_TIMEOUT = 20_000
SHIPPING_RENDER_TIMEOUT = 12_000

# 商品與商品之間稍微間隔，避免短時間連續請求
MIN_DELAY_SECONDS = 4
MAX_DELAY_SECONDS = 7

# 至少要成功抓到幾款才允許寫入 state
# 我們有 12 款；正式 baseline 應該全部成功。
MIN_SUCCESSFUL_PRODUCTS = 12


# ============================================================
# 監控商品
# ============================================================

PRODUCTS = [
    {
        "en": "Kiwami Choan",
        "zh": "極 長安",
        "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1g36020c1",
    },
    {
        "en": "Tenju",
        "zh": "天授",
        "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1111020c1",
    },
    {
        "en": "Choan",
        "zh": "長安",
        "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1121020c1",
    },
    {
        "en": "Eiju",
        "zh": "永寿",
        "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1131020c1",
    },
    {
        "en": "Unkaku",
        "zh": "雲鶴",
        "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1141020c1",
    },
    {
        "en": "Kinrin",
        "zh": "金輪",
        "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1151020c1",
    },
    {
        "en": "Wako",
        "zh": "和光",
        "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1161020c1",
    },
    {
        "en": "Yugen",
        "zh": "又玄",
        "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1171020c1",
    },
    {
        "en": "Chigi no Shiro",
        "zh": "千木の白",
        "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1181040c1",
    },
    {
        "en": "Isuzu",
        "zh": "五十鈴",
        "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1191040c1",
    },
    {
        "en": "Aoarashi",
        "zh": "青嵐",
        "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/11a1040c1",
    },
    {
        "en": "Wakatake",
        "zh": "若竹",
        "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/11b1100c1",
    },
]


# ============================================================
# 工具
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    return re.sub(r"\s+", " ", value).strip()


def load_state():
    if not STATE_FILE.exists():
        return {}

    try:
        with STATE_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)

        return data if isinstance(data, dict) else {}

    except Exception as error:
        print("WARNING: Unable to read stock_state.json")
        print(repr(error))
        return {}


def save_state(state):
    with STATE_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            state,
            file,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )


# ============================================================
# Taiwan 配送
# ============================================================

def detect_taiwan_shipping(page):
    try:
        # 配送計算器可能比商品資料晚出現
        page.wait_for_selector(
            "#calc_shipping_country",
            state="attached",
            timeout=SHIPPING_RENDER_TIMEOUT,
        )

        country_select = page.locator("#calc_shipping_country")

        if country_select.count() == 0:
            return "UNKNOWN"

        options = country_select.locator("option")

        for index in range(options.count()):
            option = options.nth(index)

            value = clean_text(
                option.get_attribute("value")
            ).upper()

            text = clean_text(
                option.inner_text()
            ).lower()

            if value == "TW":
                return "AVAILABLE"

            if "taiwan" in text:
                return "AVAILABLE"

        # 選單成功載入，但沒有 Taiwan
        return "UNAVAILABLE"

    except PlaywrightTimeoutError:
        print(
            "WARNING: Shipping country selector "
            "did not appear."
        )
        return "UNKNOWN"

    except Exception as error:
        print(
            "WARNING: Taiwan shipping detection failed:",
            repr(error),
        )
        return "UNKNOWN"


# ============================================================
# SKU 資料
# ============================================================

def extract_sku(row):
    selectors = [
        ".pa-sku dd",
        ".sku",
    ]

    for selector in selectors:
        try:
            locator = row.locator(selector)

            if locator.count() > 0:
                value = clean_text(
                    locator.first.inner_text()
                ).upper()

                if value:
                    return value

        except Exception:
            pass

    return ""


def extract_size(row):
    selectors = [
        ".pa-size dd",
        ".pa-package dd",
    ]

    for selector in selectors:
        try:
            locator = row.locator(selector)

            if locator.count() > 0:
                value = clean_text(
                    locator.first.inner_text()
                )

                if value:
                    return value

        except Exception:
            pass

    return ""


def extract_jpy_price(row):
    # 優先找 JPY 專用元素
    selectors = [
        ".woocs_price_JPY",
        ".woocommerce-Price-amount",
        ".price",
    ]

    for selector in selectors:
        try:
            locator = row.locator(selector)

            if locator.count() == 0:
                continue

            text = clean_text(
                locator.first.inner_text()
            )

            match = re.search(
                r"[¥￥]\s*([\d,]+)",
                text,
            )

            if match:
                return "¥" + match.group(1)

        except Exception:
            pass

    # fallback：整列搜尋 ¥
    try:
        text = clean_text(row.inner_text())

        match = re.search(
            r"[¥￥]\s*([\d,]+)",
            text,
        )

        if match:
            return "¥" + match.group(1)

    except Exception:
        pass

    return ""


# ============================================================
# SKU 庫存判斷
# ============================================================

def detect_variant_stock(row):
    try:
        add_buttons = row.locator(
            "button.single_add_to_cart_button"
        )

        if add_buttons.count() > 0:
            button = add_buttons.first

            classes = clean_text(
                button.get_attribute("class")
            ).lower()

            text = clean_text(
                button.inner_text()
            ).lower()

            try:
                disabled = button.is_disabled()
            except Exception:
                disabled = False

            if (
                not disabled
                and "disabled" not in classes
                and "add to cart" in text
            ):
                return "AVAILABLE"

        row_text = clean_text(
            row.inner_text()
        ).lower()

        if (
            "out of stock" in row_text
            or "sold out" in row_text
            or "unavailable" in row_text
        ):
            return "SOLD_OUT"

        # 根據目前實際 rendered DOM：
        # 可購買 SKU 會有 single_add_to_cart_button。
        if add_buttons.count() == 0:
            return "SOLD_OUT"

        return "ERROR"

    except Exception as error:
        print(
            "Variant stock detection error:",
            repr(error),
        )
        return "ERROR"


# ============================================================
# 單一商品
# ============================================================

def inspect_product(browser, product):
    """
    每一款商品建立自己的 Browser Context。

    不與上一款商品共用 cookie / session / page。
    """

    context = None

    try:
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

        print()
        print("=" * 70)
        print(
            "Checking:",
            product["zh"],
            product["en"],
        )
        print(
            "URL:",
            product["url"],
        )

        response = page.goto(
            product["url"],
            wait_until="domcontentloaded",
            timeout=NAVIGATION_TIMEOUT,
        )

        if response is None:
            raise RuntimeError(
                "No HTTP response received."
            )

        print(
            "HTTP:",
            response.status,
        )

        if response.status != 200:
            raise RuntimeError(
                f"HTTP {response.status}"
            )

        # ----------------------------------------------------
        # 商品 variation
        # ----------------------------------------------------

        page.wait_for_selector(
            ".product-form-row",
            state="attached",
            timeout=PRODUCT_RENDER_TIMEOUT,
        )

        # 等 JS 將 Add to Cart / Out of stock 狀態更新完成
        page.wait_for_timeout(2500)

        # ----------------------------------------------------
        # Taiwan
        # ----------------------------------------------------

        taiwan = detect_taiwan_shipping(
            page
        )

        print(
            "Taiwan shipping:",
            taiwan,
        )

        # ----------------------------------------------------
        # SKU rows
        # ----------------------------------------------------

        rows = page.locator(
            ".variations_form.cart .product-form-row"
        )

        if rows.count() == 0:
            rows = page.locator(
                ".product-form-row"
            )

        row_count = rows.count()

        if row_count == 0:
            raise RuntimeError(
                "No product variations found."
            )

        variants = []

        for index in range(row_count):
            row = rows.nth(index)

            sku = extract_sku(row)
            size = extract_size(row)
            price = extract_jpy_price(row)

            if not sku:
                print(
                    f"WARNING: Row {index + 1} "
                    "has no SKU; skipped."
                )
                continue

            status = detect_variant_stock(
                row
            )

            variants.append({
                "sku": sku,
                "size": size,
                "price": price,
                "status": status,
            })

            print(
                f"{sku} | "
                f"{size} | "
                f"{price} | "
                f"{status}"
            )

        if not variants:
            raise RuntimeError(
                "No valid SKU could be parsed."
            )

        return {
            "taiwan": taiwan,
            "variants": variants,
        }

    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass


# ============================================================
# GAS
# ============================================================

def notify_gas(products, taiwan_status):
    if not GAS_WEBHOOK_URL:
        raise RuntimeError(
            "GAS_WEBHOOK_URL is missing."
        )

    if not MONITOR_SECRET:
        raise RuntimeError(
            "MONITOR_SECRET is missing."
        )

    payload = {
        "source": "github-monitor",
        "secret": MONITOR_SECRET,
        "taiwan": taiwan_status,
        "products": products,
    }

    body = json.dumps(
        payload,
        ensure_ascii=False,
    ).encode("utf-8")

    request = urllib.request.Request(
        GAS_WEBHOOK_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "MarukyuStockMonitor/3.0",
        },
        method="POST",
    )

    with urllib.request.urlopen(
        request,
        timeout=30,
    ) as response:

        print(
            "GAS notification HTTP:",
            response.status,
        )

        if response.status < 200 or response.status >= 300:
            raise RuntimeError(
                f"GAS returned HTTP {response.status}"
            )


# ============================================================
# State 格式判斷
# ============================================================

def state_is_complete_sku_format(state):
    """
    只有 12 款商品全部存在，且都有 variants，
    才把它視為正式可比較的新版 baseline。
    """

    if not isinstance(state, dict):
        return False

    if len(state) != len(PRODUCTS):
        return False

    for product in PRODUCTS:
        data = state.get(product["en"])

        if not isinstance(data, dict):
            return False

        variants = data.get("variants")

        if not isinstance(variants, dict):
            return False

        if len(variants) == 0:
            return False

    return True


# ============================================================
# Taiwan 整體狀態
# ============================================================

def determine_taiwan_status(results):
    valid = [
        value
        for value in results
        if value != "UNKNOWN"
    ]

    if not valid:
        return "UNKNOWN"

    # Taiwan 是網站配送區域設定。
    # 只要任一成功頁面明確看到 TW，就視為可配送。
    if "AVAILABLE" in valid:
        return "AVAILABLE"

    if all(
        value == "UNAVAILABLE"
        for value in valid
    ):
        return "UNAVAILABLE"

    return "UNKNOWN"


# ============================================================
# 主程式
# ============================================================

def main():
    previous_state = load_state()

    previous_state_complete = (
        state_is_complete_sku_format(
            previous_state
        )
    )

    if previous_state and not previous_state_complete:
        print(
            "Incomplete or legacy stock_state.json detected."
        )
        print(
            "A complete SKU-level baseline "
            "must be created before notifications are enabled."
        )

    elif not previous_state:
        print(
            "No previous stock state."
        )
        print(
            "A new SKU-level baseline will be created."
        )

    else:
        print(
            "Valid SKU-level baseline loaded."
        )

    print()
    print("=" * 70)
    print(
        "Marukyu Koyamaen SKU Stock Monitor"
    )
    print(
        "Products:",
        len(PRODUCTS),
    )
    print("=" * 70)

    new_state = {}

    restocked_products = []

    successful_products = 0
    failed_products = []

    taiwan_results = []

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True
        )

        try:
            for index, product in enumerate(PRODUCTS):

                try:
                    result = inspect_product(
                        browser,
                        product,
                    )

                    successful_products += 1

                    if result["taiwan"]:
                        taiwan_results.append(
                            result["taiwan"]
                        )

                    previous_product = (
                        previous_state.get(
                            product["en"],
                            {}
                        )
                        if previous_state_complete
                        else {}
                    )

                    previous_variants = (
                        previous_product.get(
                            "variants",
                            {}
                        )
                        if isinstance(
                            previous_product,
                            dict,
                        )
                        else {}
                    )

                    current_variants = {}
                    product_restocked = []

                    for variant in result["variants"]:

                        sku = variant["sku"]
                        status = variant["status"]

                        previous_variant = (
                            previous_variants.get(
                                sku,
                                {}
                            )
                        )

                        if not isinstance(
                            previous_variant,
                            dict,
                        ):
                            previous_variant = {}

                        previous_status = (
                            previous_variant.get(
                                "status"
                            )
                        )

                        print(
                            "Previous:",
                            sku,
                            previous_status,
                            "→ Current:",
                            status,
                        )

                        # ====================================
                        # ERROR 不覆蓋舊資料
                        # ====================================

                        if status == "ERROR":

                            if previous_variant:
                                current_variants[sku] = (
                                    previous_variant
                                )

                            continue

                        current_variants[sku] = {
                            "size": variant["size"],
                            "price": variant["price"],
                            "status": status,
                        }

                        # ====================================
                        # 只有正式 baseline 存在時
                        # 才允許判斷補貨
                        # ====================================

                        if (
                            previous_state_complete
                            and
                            previous_status == "SOLD_OUT"
                            and
                            status == "AVAILABLE"
                        ):

                            print(
                                "*** SKU RESTOCK DETECTED ***",
                                sku,
                                variant["size"],
                            )

                            product_restocked.append({
                                "sku": sku,
                                "size": variant["size"],
                                "price": variant["price"],
                            })

                        elif not previous_state_complete:
                            print(
                                "Baseline:",
                                sku,
                                status,
                            )

                    # ========================================
                    # 正式 baseline 已存在時，
                    # 若某個舊 SKU 暫時沒有解析到，
                    # 保留舊資料。
                    # ========================================

                    if previous_state_complete:

                        for (
                            sku,
                            old_variant
                        ) in previous_variants.items():

                            if sku not in current_variants:
                                current_variants[sku] = (
                                    old_variant
                                )

                    if not current_variants:
                        raise RuntimeError(
                            "No usable SKU states."
                        )

                    new_state[
                        product["en"]
                    ] = {
                        "zh": product["zh"],
                        "url": product["url"],
                        "taiwan": result["taiwan"],
                        "variants": current_variants,
                    }

                    if product_restocked:

                        restocked_products.append({
                            "en": product["en"],
                            "zh": product["zh"],
                            "url": product["url"],
                            "variants": product_restocked,
                        })

                except Exception as error:

                    print(
                        "ERROR checking",
                        product["en"],
                        ":",
                        repr(error),
                    )

                    failed_products.append(
                        product["en"]
                    )

                # ============================================
                # 最後一款不用等
                # ============================================

                if index < len(PRODUCTS) - 1:

                    delay = random.uniform(
                        MIN_DELAY_SECONDS,
                        MAX_DELAY_SECONDS,
                    )

                    print(
                        f"Waiting {delay:.1f} seconds "
                        "before next product..."
                    )

                    time.sleep(delay)

        finally:
            browser.close()

    # ========================================================
    # 結果
    # ========================================================

    print()
    print("=" * 70)

    print(
        "Successful product checks:",
        successful_products,
        "/",
        len(PRODUCTS),
    )

    if failed_products:
        print(
            "Failed products:",
            ", ".join(failed_products),
        )

    # ========================================================
    # 最重要的安全機制
    #
    # 不完整資料絕對不寫入 stock_state.json。
    # ========================================================

    if (
        successful_products
        < MIN_SUCCESSFUL_PRODUCTS
    ):
        print()
        print(
            "ERROR: Product check is incomplete."
        )

        print(
            "stock_state.json will NOT be updated."
        )

        print(
            "No LINE notification will be sent."
        )

        raise RuntimeError(
            "Only "
            f"{successful_products}/"
            f"{len(PRODUCTS)} "
            "products were successfully checked."
        )

    # 再確認 new_state 本身有 12 款
    if len(new_state) != len(PRODUCTS):

        raise RuntimeError(
            "New stock state is incomplete. "
            "Existing state will be preserved."
        )

    # ========================================================
    # Taiwan
    # ========================================================

    overall_taiwan = determine_taiwan_status(
        taiwan_results
    )

    print(
        "Overall Taiwan shipping:",
        overall_taiwan,
    )

    # ========================================================
    # 第一次完整成功
    #
    # 只建立 baseline，不通知。
    # ========================================================

    if not previous_state_complete:

        print()
        print(
            "Complete SKU baseline successfully created."
        )

        print(
            "No restock notification will be sent "
            "during baseline creation."
        )

        save_state(
            new_state
        )

        print(
            "stock_state.json updated."
        )

        print(
            "Monitor completed."
        )

        print("=" * 70)

        return

    # ========================================================
    # 已有 baseline → 正常補貨判斷
    # ========================================================

    if restocked_products:

        print()
        print("Restocked SKUs:")

        for product in restocked_products:

            for variant in product["variants"]:

                print(
                    "-",
                    product["zh"],
                    product["en"],
                    "|",
                    variant["size"],
                    "|",
                    variant["price"],
                )

        # ----------------------------------------------------
        # LINE 成功後才更新 state。
        #
        # 若 GAS / LINE 失敗，程式會失敗，
        # AVAILABLE 不會寫入 state，
        # 下一輪仍可重新嘗試通知。
        # ----------------------------------------------------

        notify_gas(
            restocked_products,
            overall_taiwan,
        )

    else:

        print(
            "No SKU restock detected."
        )

    # ========================================================
    # 儲存完整 state
    # ========================================================

    save_state(
        new_state
    )

    print(
        "stock_state.json updated."
    )

    print(
        "Monitor completed."
    )

    print("=" * 70)


if __name__ == "__main__":
    main()
