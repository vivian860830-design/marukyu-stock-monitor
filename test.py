import urllib.request
import re


URL = (
    "https://www.marukyu-koyamaen.co.jp/"
    "english/shop/products/1121020c1"
)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


request = urllib.request.Request(
    URL,
    headers=HEADERS
)


with urllib.request.urlopen(
    request,
    timeout=30
) as response:

    html = response.read().decode(
        "utf-8",
        errors="replace"
    )

    print("STATUS:", response.status)
    print("HTML LENGTH:", len(html))


# ============================================================
# 1. CHOAN 商品購買區
# ============================================================

start = html.find(
    '<div class="variations_form cart"'
)

if start == -1:

    print(
        "\nERROR: variations_form cart not found"
    )

else:

    end = html.find(
        '<div class="product-labelings">',
        start
    )

    if end == -1:
        end = start + 40000

    purchase_area = html[start:end]

    purchase_area = re.sub(
        r"\s+",
        " ",
        purchase_area
    )

    print(
        "\n\n"
        "========================================"
    )

    print(
        "CHOAN PURCHASE AREA"
    )

    print(
        "========================================\n"
    )

    print(
        purchase_area
    )


# ============================================================
# 2. 搜尋 Taiwan
# ============================================================

print(
    "\n\n"
    "========================================"
)

print(
    "TAIWAN SEARCH"
)

print(
    "========================================"
)


matches = list(
    re.finditer(
        r"taiwan",
        html,
        re.I
    )
)


print(
    "Taiwan occurrences:",
    len(matches)
)


for number, match in enumerate(
    matches[:20],
    start=1
):

    snippet_start = max(
        0,
        match.start() - 1000
    )

    snippet_end = min(
        len(html),
        match.end() + 1000
    )

    snippet = html[
        snippet_start:
        snippet_end
    ]

    snippet = re.sub(
        r"\s+",
        " ",
        snippet
    )

    print(
        "\n--- TAIWAN MATCH",
        number,
        "---\n"
    )

    print(
        snippet
    )


# ============================================================
# 3. 搜尋可能的國家 / 配送欄位
# ============================================================

print(
    "\n\n"
    "========================================"
)

print(
    "COUNTRY / SHIPPING FIELDS"
)

print(
    "========================================"
)


patterns = [
    r'<select[^>]*country[^>]*>.*?</select>',
    r'<select[^>]*shipping[^>]*>.*?</select>',
    r'<option[^>]*>Taiwan.*?</option>',
    r'<option[^>]*value=["\'][^"\']*TW[^"\']*["\'][^>]*>.*?</option>',
]


for pattern in patterns:

    results = re.findall(
        pattern,
        html,
        re.I | re.S
    )

    print(
        "\nPATTERN:",
        pattern
    )

    print(
        "FOUND:",
        len(results)
    )

    for result in results[:5]:

        result = re.sub(
            r"\s+",
            " ",
            result
        )

        print(
            result[:5000]
        )
