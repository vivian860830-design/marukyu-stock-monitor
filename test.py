import urllib.request
import urllib.error

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

for name, url in PRODUCTS.items():
    print("=" * 60)
    print(f"Testing: {name}")
    print(f"URL: {url}")

    request = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            html = response.read()

            print(f"STATUS: {response.status}")
            print(f"HTML LENGTH: {len(html)}")

            if response.status == 200:
                print("RESULT: SUCCESS")

    except urllib.error.HTTPError as e:
        body = e.read()

        print(f"STATUS: {e.code}")
        print(f"HTML LENGTH: {len(body)}")
        print("RESULT: BLOCKED / HTTP ERROR")

    except Exception as e:
        print(f"RESULT: ERROR")
        print(str(e))
