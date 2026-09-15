import urllib.request
import re

url = "https://www.marukyu-koyamaen.co.jp/english/shop/products/11b1100c1"

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

request = urllib.request.Request(url, headers=headers)

with urllib.request.urlopen(request, timeout=30) as response:

    html = response.read().decode("utf-8", errors="replace")

    print("STATUS:", response.status)

    # 只取真正的商品購買區域
    start = html.find('<div class="variations_form cart"')

    if start == -1:
        print("ERROR: variations_form cart not found")
        raise SystemExit

    # 往後取足夠大的區塊
    section = html[start:start + 30000]

    # 壓縮空白，讓 Log 比較好看
    section = re.sub(r"\s+", " ", section)

    print("\n===== PRODUCT PURCHASE AREA =====\n")
    print(section)
