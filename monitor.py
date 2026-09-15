import os
import re
import json
import html as html_lib
import urllib.request
import urllib.error


GAS_WEBHOOK_URL = os.environ.get("GAS_WEBHOOK_URL")
MONITOR_SECRET = os.environ.get("MONITOR_SECRET")

STATE_FILE = "stock_state.json"


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ============================================================
# 正式監控 12 款
# ============================================================

PRODUCTS = [

    {
        "en": "Kiwami Choan",
        "zh": "極 長安",
        "url": (
            "https://www.marukyu-koyamaen.co.jp/"
            "english/shop/products/1g36020c1"
        ),
    },

    {
        "en": "Tenju",
        "zh": "天授",
        "url": (
            "https://www.marukyu-koyamaen.co.jp/"
            "english/shop/products/1111020c1"
        ),
    },

    {
        "en": "Choan",
        "zh": "長安",
        "url": (
            "https://www.marukyu-koyamaen.co.jp/"
            "english/shop/products/1121020c1"
        ),
    },

    {
        "en": "Eiju",
        "zh": "永寿",
        "url": (
            "https://www.marukyu-koyamaen.co.jp/"
            "english/shop/products/1131020c1"
        ),
    },

    {
        "en": "Unkaku",
        "zh": "雲鶴",
        "url": (
            "https://www.marukyu-koyamaen.co.jp/"
            "english/shop/products/1141020c1"
        ),
    },

    {
        "en": "Kinrin",
        "zh": "金輪",
        "url": (
            "https://www.marukyu-koyamaen.co.jp/"
            "english/shop/products/1151020c1"
        ),
    },

    {
        "en": "Wako",
        "zh": "和光",
        "url": (
            "https://www.marukyu-koyamaen.co.jp/"
            "english/shop/products/1161020c1"
        ),
    },

    {
        "en": "Yugen",
        "zh": "又玄",
        "url": (
            "https://www.marukyu-koyamaen.co.jp/"
            "english/shop/products/1171020c1"
        ),
    },

    {
        "en": "Chigi no Shiro",
        "zh": "千木の白",
        "url": (
            "https://www.marukyu-koyamaen.co.jp/"
            "english/shop/products/1181040c1"
        ),
    },

    {
        "en": "Isuzu",
        "zh": "五十鈴",
        "url": (
            "https://www.marukyu-koyamaen.co.jp/"
            "english/shop/products/1191040c1"
        ),
    },

    {
        "en": "Aoarashi",
        "zh": "青嵐",
        "url": (
            "https://www.marukyu-koyamaen.co.jp/"
            "english/shop/products/11a1040c1"
        ),
    },

    {
        "en": "Wakatake",
        "zh": "若竹",
        "url": (
            "https://www.marukyu-koyamaen.co.jp/"
            "english/shop/products/11b1100c1"
        ),
    },
]


# ============================================================
# 抓取商品頁
# ============================================================

def fetch_html(url):

    request = urllib.request.Request(
        url,
        headers=HEADERS
    )

    with urllib.request.urlopen(
        request,
        timeout=30
    ) as response:

        if response.status != 200:
            raise RuntimeError(
                f"HTTP {response.status}"
            )

        return response.read().decode(
            "utf-8",
            errors="replace"
        )


# ============================================================
# 擷取真正的購買區域
# ============================================================

def get_purchase_area(page_html):

    start = page_html.find(
        '<div class="variations_form cart"'
    )

    if start == -1:
        raise RuntimeError(
            "Purchase area not found"
        )

    # 找購買區後面的 currency switcher，
    # 避免抓到 Recommended Items。
    end = page_html.find(
        '<label class="woocs_auto_switcher"',
        start
    )

    if end == -1:
        end = start + 30000

    return page_html[start:end]


# ============================================================
# 判斷庫存
# ============================================================

def detect_status(purchase_area):

    # 丸久真正的商品缺貨標記
    if re.search(
        r'class=["\'][^"\']*'
        r'single-stock-status[^"\']*'
        r'out-of-stock[^"\']*["\']',
        purchase_area,
        re.I
    ):
        return "SOLD_OUT"

    # 正常有商品 variation
    if "product-form-row" in purchase_area:
        return "AVAILABLE"

    return "ERROR"


# ============================================================
# 擷取 SKU / 容量 / JPY 價格
# ============================================================

def extract_variants(purchase_area):

    variants = []

    positions = [
        match.start()
        for match in re.finditer(
            r'<div class="product-form-row',
            purchase_area,
            re.I
        )
    ]

    for index, start in enumerate(positions):

        if index + 1 < len(positions):
            end = positions[index + 1]
        else:
            end = len(purchase_area)

        row = purchase_area[start:end]


        sku_match = re.search(
            r'<dl class="pa pa-sku">.*?'
            r'<dd>(.*?)</dd>',
            row,
            re.I | re.S
        )


        size_match = re.search(
            r'<dl class="pa pa-size">.*?'
            r'<dd>(.*?)</dd>',
            row,
            re.I | re.S
        )


        price_match = re.search(
            r'woocs_price_JPY.*?'
            r'woocommerce-Price-currencySymbol'
            r'[^>]*>&yen;</span>'
            r'\s*([\d,]+)',
            row,
            re.I | re.S
        )


        if not size_match:
            continue


        size = clean_text(
            size_match.group(1)
        )


        sku = (
            clean_text(
                sku_match.group(1)
            )
            if sku_match
            else ""
        )


        price = (
            "¥" + price_match.group(1)
            if price_match
            else ""
        )


        variants.append({
            "sku": sku,
            "size": size,
            "price": price,
        })


    return variants


def clean_text(value):

    value = re.sub(
        r"<[^>]+>",
        "",
        value
    )

    value = html_lib.unescape(
        value
    )

    return re.sub(
        r"\s+",
        " ",
        value
    ).strip()


# ============================================================
# 讀取前一次狀態
# ============================================================

def load_state():

    if not os.path.exists(
        STATE_FILE
    ):
        return {}


    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

            return (
                data
                if isinstance(data, dict)
                else {}
            )

    except Exception as error:

        print(
            "Unable to read state:",
            repr(error)
        )

        return {}


# ============================================================
# 儲存狀態
# ============================================================

def save_state(state):

    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            state,
            file,
            ensure_ascii=False,
            indent=2,
            sort_keys=True
        )


# ============================================================
# 發送給 GAS
# ============================================================

def notify_gas(products):

    if not GAS_WEBHOOK_URL:
        raise RuntimeError(
            "GAS_WEBHOOK_URL is missing"
        )


    if not MONITOR_SECRET:
        raise RuntimeError(
            "MONITOR_SECRET is missing"
        )


    payload = {

        "source":
            "github-monitor",

        "secret":
            MONITOR_SECRET,

        "products":
            products,
    }


    request = urllib.request.Request(

        GAS_WEBHOOK_URL,

        data=json.dumps(
            payload,
            ensure_ascii=False
        ).encode("utf-8"),

        headers={
            "Content-Type":
                "application/json",

            "User-Agent":
                "MarukyuStockMonitor/1.0",
        },

        method="POST"
    )


    with urllib.request.urlopen(
        request,
        timeout=30
    ) as response:

        print(
            "GAS notification HTTP:",
            response.status
        )


# ============================================================
# 主程式
# ============================================================

def main():

    previous_state = load_state()

    new_state = dict(
        previous_state
    )

    restocked = []

    successful_checks = 0


    print(
        "=========================================="
    )

    print(
        "Marukyu Koyamaen Stock Monitor"
    )

    print(
        "Products:",
        len(PRODUCTS)
    )

    print(
        "Previous state:",
        previous_state
    )

    print(
        "=========================================="
    )


    for product in PRODUCTS:

        name = product["en"]

        print(
            "\n------------------------------------------"
        )

        print(
            "Checking:",
            product["zh"],
            name
        )

        print(
            "URL:",
            product["url"]
        )


        try:

            page_html = fetch_html(
                product["url"]
            )


            purchase_area = (
                get_purchase_area(
                    page_html
                )
            )


            status = detect_status(
                purchase_area
            )


            variants = extract_variants(
                purchase_area
            )


            previous = (
                previous_state.get(
                    name
                )
            )


            print(
                "Previous:",
                previous
            )

            print(
                "Current:",
                status
            )


            for variant in variants:

                print(
                    "  ",
                    variant["sku"],
                    "|",
                    variant["size"],
                    "|",
                    variant["price"]
                )


            # ================================================
            # 無法判斷時不要覆寫舊狀態
            # ================================================

            if status == "ERROR":

                print(
                    "WARNING: "
                    "Unable to determine stock."
                )

                continue


            successful_checks += 1


            # ================================================
            # 只有缺貨 -> 有貨才通知
            # ================================================

            if (
                previous == "SOLD_OUT"
                and
                status == "AVAILABLE"
            ):

                print(
                    "*** RESTOCK DETECTED ***"
                )


                restocked.append({

                    "en":
                        product["en"],

                    "zh":
                        product["zh"],

                    "url":
                        product["url"],

                    "variants":
                        variants,
                })


            # ================================================
            # 第一次只建立 baseline
            # ================================================

            if previous is None:

                print(
                    "Baseline created. "
                    "No notification."
                )


            new_state[name] = status


        except urllib.error.HTTPError as error:

            print(
                "HTTP ERROR:",
                error.code
            )


        except Exception as error:

            print(
                "ERROR:",
                repr(error)
            )


    # ========================================================
    # 防止整站異常時污染 state
    # ========================================================

    if successful_checks == 0:

        print(
            "\nCRITICAL: "
            "No products could be checked."
        )

        raise RuntimeError(
            "All product checks failed"
        )


    # ========================================================
    # 先通知，再寫入新狀態
    #
    # 如果 LINE/GAS 通知失敗，
    # workflow 會失敗，狀態不會被標成 AVAILABLE，
    # 下次還有機會重新通知。
    # ========================================================

    if restocked:

        print(
            "\n=========================================="
        )

        print(
            "Restocked products:"
        )

        for product in restocked:

            print(
                "-",
                product["zh"],
                product["en"]
            )


        notify_gas(
            restocked
        )


    else:

        print(
            "\nNo restock detected."
        )


    save_state(
        new_state
    )


    print(
        "\n=========================================="
    )

    print(
        "Successful checks:",
        successful_checks,
        "/",
        len(PRODUCTS)
    )

    print(
        "New state:",
        new_state
    )

    print(
        "Monitor completed."
    )

    print(
        "=========================================="
    )


if __name__ == "__main__":
    main()
