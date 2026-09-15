import os
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright


# ============================================================
# 基本設定
# ============================================================

GAS_WEBHOOK_URL = os.environ.get("GAS_WEBHOOK_URL", "").strip()
MONITOR_SECRET = os.environ.get("MONITOR_SECRET", "").strip()

STATE_FILE = Path("stock_state.json")

NAVIGATION_TIMEOUT = 45_000
RENDER_WAIT_MS = 2_500


# ============================================================
# 正式監控 12 款
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
# 文字清理
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    return re.sub(r"\s+", " ", value).strip()


# ============================================================
# 讀取舊 state
# ============================================================

def load_state():
    if not STATE_FILE.exists():
        return {}

    try:
        with STATE_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            return {}

        return data

    except Exception as error:
        print("WARNING: Unable to read stock_state.json")
        print(repr(error))
        return {}


# ============================================================
# 儲存 state
# ============================================================

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
# 判斷 Taiwan 是否在配送國家選單
# ============================================================

def detect_taiwan_shipping(page):
    try:
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

            if text == "taiwan" or "taiwan" in text:
                return "AVAILABLE"

        return "UNAVAILABLE"

    except Exception as error:
        print(
            "WARNING: Unable to determine Taiwan shipping:",
            repr(error),
        )

        return "UNKNOWN"


# ============================================================
# 取得 JPY 價格
# ============================================================

def extract_jpy_price(row):
    try:
        jpy = row.locator(".woocs_price_JPY")

        if jpy.count() == 0:
            return ""

        text = clean_text(
            jpy.first.inner_text()
        )

        # 例如：
        # ¥3,700
        match = re.search(
            r"[¥￥]\s*([\d,]+)",
            text,
        )

        if match:
            return "¥" + match.group(1)

        # fallback
        number = re.search(
            r"([\d,]+)",
            text,
        )

        if number:
            return "¥" + number.group(1)

        return text

    except Exception:
        return ""


# ============================================================
# 從一個 product-form-row 取得 SKU
# ============================================================

def extract_sku(row):
    try:
        sku = row.locator(".pa-sku dd")

        if sku.count() == 0:
            return ""

        return clean_text(
            sku.first.inner_text()
        ).upper()

    except Exception:
        return ""


# ============================================================
# 從一個 product-form-row 取得 Size
# ============================================================

def extract_size(row):
    try:
        size = row.locator(".pa-size dd")

        if size.count() == 0:
            return ""

        return clean_text(
            size.first.inner_text()
        )

    except Exception:
        return ""


# ============================================================
# 判斷單一 SKU 是否可購買
# ============================================================

def detect_variant_stock(row):
    try:
        # ----------------------------------------------------
        # 第一優先：
        # 實際可購買按鈕
        # ----------------------------------------------------

        add_button = row.locator(
            "button.single_add_to_cart_button"
        )

        if add_button.count() > 0:
            button = add_button.first

            disabled = button.is_disabled()

            classes = clean_text(
                button.get_attribute("class")
            ).lower()

            text = clean_text(
                button.inner_text()
            ).lower()

            if (
                not disabled
                and "disabled" not in classes
                and "add to cart" in text
            ):
                return "AVAILABLE"

        # ----------------------------------------------------
        # 明確缺貨文字
        # ----------------------------------------------------

        row_text = clean_text(
            row.inner_text()
        ).lower()

        if (
            "out of stock" in row_text
            or "sold out" in row_text
            or "unavailable" in row_text
        ):
            return "SOLD_OUT"

        # ----------------------------------------------------
        # 沒有 Add to Cart
        #
        # 根據目前丸久 rendered DOM：
        # 有貨 SKU 才會生成 single_add_to_cart_button。
        # ----------------------------------------------------

        if add_button.count() == 0:
            return "SOLD_OUT"

        return "ERROR"

    except Exception as error:
        print(
            "Variant stock detection error:",
            repr(error),
        )

        return "ERROR"


# ============================================================
# 檢查單一商品
# ============================================================

def inspect_product(page, product):
    print()
    print("=" * 70)
    print(
        "Checking:",
        product["zh"],
        product["en"],
    )
    print("URL:", product["url"])

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

    # 等待商品 variation 出現
    page.wait_for_selector(
        ".product-form-row",
        timeout=NAVIGATION_TIMEOUT,
    )

    # 再留一點時間讓網站 JS 更新購買按鈕
    page.wait_for_timeout(
        RENDER_WAIT_MS
    )

    # --------------------------------------------------------
    # Taiwan 配送狀態
    # --------------------------------------------------------

    taiwan = detect_taiwan_shipping(
        page
    )

    print(
        "Taiwan shipping:",
        taiwan,
    )

    # --------------------------------------------------------
    # SKU
    # --------------------------------------------------------

    rows = page.locator(
        ".variations_form.cart .product-form-row"
    )

    if rows.count() == 0:
        # fallback
        rows = page.locator(
            ".product-form-row"
        )

    if rows.count() == 0:
        raise RuntimeError(
            "No product variations found."
        )

    variants = []

    for index in range(rows.count()):
        row = rows.nth(index)

        sku = extract_sku(row)
        size = extract_size(row)
        price = extract_jpy_price(row)

        if not sku:
            print(
                "WARNING: Row without SKU skipped."
            )
            continue

        status = detect_variant_stock(
            row
        )

        variant = {
            "sku": sku,
            "size": size,
            "price": price,
            "status": status,
        }

        variants.append(
            variant
        )

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


# ============================================================
# 傳送補貨資料給 GAS
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

    import urllib.request

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
            "User-Agent": "MarukyuStockMonitor/2.0",
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


# ============================================================
# 主程式
# ============================================================

def main():
    previous_state = load_state()

    # --------------------------------------------------------
    # 舊版 stock_state.json 是商品層級：
    #
    # "Choan": "AVAILABLE"
    #
    # 新版是 SKU 層級。
    #
    # 若偵測到舊格式，直接建立全新 baseline，
    # 避免升級當天誤發大量補貨通知。
    # --------------------------------------------------------

    legacy_state = False

    for value in previous_state.values():
        if isinstance(value, str):
            legacy_state = True
            break

    if legacy_state:
        print(
            "Legacy stock_state.json detected."
        )
        print(
            "A new SKU-level baseline will be created."
        )
        previous_state = {}

    new_state = {}

    restocked_products = []

    successful_products = 0

    taiwan_results = []

    print("=" * 70)
    print("Marukyu Koyamaen SKU Stock Monitor")
    print("Products:", len(PRODUCTS))
    print("=" * 70)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
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

        for product in PRODUCTS:
            product_key = product["en"]

            try:
                result = inspect_product(
                    page,
                    product,
                )

                successful_products += 1

                taiwan = result["taiwan"]

                if taiwan != "UNKNOWN":
                    taiwan_results.append(
                        taiwan
                    )

                previous_product = (
                    previous_state.get(
                        product_key,
                        {}
                    )
                )

                if not isinstance(
                    previous_product,
                    dict,
                ):
                    previous_product = {}

                previous_variants = (
                    previous_product.get(
                        "variants",
                        {}
                    )
                )

                if not isinstance(
                    previous_variants,
                    dict,
                ):
                    previous_variants = {}

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

                    # ----------------------------------------
                    # ERROR 不覆蓋舊狀態
                    # ----------------------------------------

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

                    # ----------------------------------------
                    # 只有 SOLD_OUT → AVAILABLE 才補貨
                    # ----------------------------------------

                    if (
                        previous_status == "SOLD_OUT"
                        and status == "AVAILABLE"
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

                    elif previous_status is None:
                        print(
                            "Baseline:",
                            sku,
                            status,
                        )

                # 如果有舊 SKU 暫時沒解析到，
                # 保留舊資料，避免直接刪除造成狀態污染。
                for sku, old_variant in (
                    previous_variants.items()
                ):
                    if sku not in current_variants:
                        current_variants[sku] = (
                            old_variant
                        )

                new_state[product_key] = {
                    "zh": product["zh"],
                    "url": product["url"],
                    "taiwan": taiwan,
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

                # 整個商品失敗時保留舊 state
                if product_key in previous_state:
                    new_state[product_key] = (
                        previous_state[product_key]
                    )

        browser.close()

    # ========================================================
    # 安全檢查
    # ========================================================

    if successful_products == 0:
        raise RuntimeError(
            "All product checks failed."
        )

    print()
    print("=" * 70)
    print(
        "Successful product checks:",
        successful_products,
        "/",
        len(PRODUCTS),
    )

    # ========================================================
    # 決定本次 Taiwan 狀態
    # ========================================================

    if "AVAILABLE" in taiwan_results:
        overall_taiwan = "AVAILABLE"

    elif (
        taiwan_results
        and all(
            value == "UNAVAILABLE"
            for value in taiwan_results
        )
    ):
        overall_taiwan = "UNAVAILABLE"

    else:
        overall_taiwan = "UNKNOWN"

    print(
        "Overall Taiwan shipping:",
        overall_taiwan,
    )

    # ========================================================
    # 有真正補貨才通知
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
                    variant["size"],
                    variant["price"],
                )

        # 先通知。
        # 如果 GAS / LINE 發送失敗，程式直接失敗，
        # stock_state 不更新成 AVAILABLE。
        notify_gas(
            restocked_products,
            overall_taiwan,
        )

    else:
        print(
            "No SKU restock detected."
        )

    # 通知成功後才寫入 state
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
