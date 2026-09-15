import urllib.request
import urllib.error
import re

PRODUCTS = {
    "Wakatake": "https://www.marukyu-koyamaen.co.jp/english/shop/products/11b1100c1",
    "Kiwami Choan": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1g36020c1",
}

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

KEYWORDS = [
    "out of stock",
    "sold out",
    "unavailable",
    "add to cart",
    "shopping cart",
    "20g",
    "40g",
    "100g",
    "200g",
    "¥",
]

for name, url in PRODUCTS.items():

    print("\n" + "=" * 80)
    print("PRODUCT:", name)
    print("URL:", url)

    request = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=30) as response:

            raw = response.read()
            html = raw.decode("utf-8", errors="replace")

            print("STATUS:", response.status)
            print("HTML LENGTH:", len(raw))

            # 儲存 HTML，方便下一步分析
            filename = name.lower().replace(" ", "_") + ".html"

            with open(filename, "w", encoding="utf-8") as f:
                f.write(html)

            print("SAVED:", filename)

            # 搜尋關鍵字附近 HTML
            lower_html = html.lower()

            for keyword in KEYWORDS:

                positions = [
                    m.start()
                    for m in re.finditer(
                        re.escape(keyword.lower()),
                        lower_html
                    )
                ]

                print(
                    f"\nKEYWORD [{keyword}] "
                    f"FOUND {len(positions)} TIME(S)"
                )

                # 每個關鍵字最多顯示前 5 個
                for pos in positions[:5]:

                    start = max(0, pos - 300)
                    end = min(len(html), pos + 500)

                    snippet = html[start:end]

                    print("-" * 50)
                    print(snippet)

    except urllib.error.HTTPError as e:
        print("HTTP ERROR:", e.code)

    except Exception as e:
        print("ERROR:", repr(e))
