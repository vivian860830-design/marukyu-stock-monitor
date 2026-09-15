import os
import re
import json
import html as html_lib
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta


# ============================================================
# 基本設定
# ============================================================

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
# 監控商品
# ============================================================
#
# 已確認的固定 URL 先列入。
# 其他 Principal Matcha URL 會在下一階段補齊。
#

PRODUCTS = [
    {
        "en": "Wakatake",
        "zh": "若竹",
        "url": (
            "https://www.marukyu-koyamaen.co.jp/"
            "english/shop/products/11b1100c1"
        ),
    },
    {
        "en": "Kiwami Choan",
        "zh": "極 長安",
        "url": (
            "https://www.marukyu-koyamaen.co.jp/"
            "english/shop/products/1g36020c1"
        ),
    },
]


# ============================================================
# 下載商品頁
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
# 只擷取真正商品購買區
# ============================================================

def get_purchase_area(page_html):

    start = page_html.find(
        '<div class="variations_form cart"'
    )

    if start == -1:
        raise RuntimeError(
            "Purchase area not found"
        )

    # 目前丸久購買區大小遠低於此值。
    # 避免把 Recommended Items 的庫存 class 算進來。
    return page_html[start:start + 30000]


# ============================================================
# 判斷商品庫存
# ============================================================

def detect_status(purchase_area):

    # 真正的商品缺貨標記
    if re.search(
        r'class=["\'][^"\']*'
        r'single-stock-status[^"\']*'
        r'out-of-stock[^"\']*["\']',
        purchase_area,
        re.I
    ):
        return "SOLD_OUT"

    # 有商品 variation
    if "product-form-row" in purchase_area:
        return "AVAILABLE"

    return "ERROR"


# ============================================================
# 擷取規格與日圓價格
# ============================================================

def extract_variants(purchase_area):

    variants = []

    rows = re.findall(
        r'<div class="product-form-row[^"]*"'
        r'[^>]*>(.*?)'
        r'(?=<div class="product-form-row|'
        r'<p class="notice"|'
        r'</div>\s*<label class="woocs_auto_switcher")',
        purchase_area,
        re.I | re.S
    )

    # 上面結構若因 HTML nesting 無法完整切開，
    # 改用每個 SKU 起點切割。
    if not rows:

        positions = [
            match.start()
            for match in re.finditer(
                r'<div class="product-form-row',
                purchase_area,
                re.I
            )
        ]

        for i, start in enumerate(positions):

            if i + 1 < len(positions):
                end = positions[i + 1]
            else:
                end = len(purchase_area)

            rows.append(
                purchase_area[start:end]
            )

    for row in rows:

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

        # 只抓 JPY block
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
            clean_text(sku_match.group(1))
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

    value = html_lib.unescape(value)

    return re.sub(
        r"\s+",
        " ",
        value
    ).strip()


# ============================================================
# 上一次庫存狀態
# ============================================================

def load_state():

    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except Exception:
        return {}


def save_state(state):

    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# 通知 GAS
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
        "source": "github-monitor",
        "secret": MONITOR_SECRET,
        "products": products,
    }

    request = urllib.request.Request(
        GAS_WEBHOOK_URL,
        data=json.dumps(
            payload,
            ensure_ascii=False
        ).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "MarukyuStockMonitor/1.0",
        },
        method="POST"
    )

    with urllib.request.urlopen(
        request,
        timeout=30
    ) as response:

        print(
            "GAS notification:",
            response.status
        )


# ============================================================
# 主程式
# ============================================================

def main():

    previous_state = load_state()

    new_state = dict(previous_state)

    restocked = []

    print(
        "Previous state:",
        previous_state
    )

    for product in PRODUCTS:

        name = product["en"]

        print("\n" + "=" * 60)
        print("Checking:", name)

        try:

            page_html = fetch_html(
                product["url"]
            )

            purchase_area = get_purchase_area(
                page_html
            )

            status = detect_status(
                purchase_area
            )

            variants = extract_variants(
                purchase_area
            )

            previous = previous_state.get(
                name
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
                    "Variant:",
                    variant
                )

            # ERROR 不覆寫舊狀態
            if status == "ERROR":
                print(
                    "Unable to determine stock. "
                    "Keeping previous state."
                )
                continue

            # 只有 SOLD_OUT -> AVAILABLE 才通知
            if (
                previous == "SOLD_OUT"
                and status == "AVAILABLE"
            ):

                restocked.append({
                    "en": product["en"],
                    "zh": product["zh"],
                    "url": product["url"],
                    "variants": variants,
                })

            new_state[name] = status

        except Exception as error:

            print(
                "ERROR:",
                name,
                repr(error)
            )

    save_state(new_state)

    print(
        "\nNew state:",
        new_state
    )

    if restocked:

        print(
            "\nRestocked:",
            [
                item["en"]
                for item in restocked
            ]
        )

        notify_gas(restocked)

    else:
        print(
            "\nNo restock detected."
        )


if __name__ == "__main__":
    main()
