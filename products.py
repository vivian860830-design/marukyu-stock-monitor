"""Single source of truth for the 12 products, shared by capture_one.py
(one product per GitHub Actions matrix job) and aggregate.py (the
downstream job that merges all 12 results). `slug` must match the matrix
value in monitor.yml and the artifact name each capture job uploads."""

PRODUCTS = [
    {"slug": "unkaku", "zh": "雲鶴", "en": "Unkaku", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1141020c1"},
    {"slug": "choan", "zh": "長安", "en": "Choan", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1121020c1"},
    {"slug": "eiju", "zh": "永寿", "en": "Eiju", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1131020c1"},
    {"slug": "kinrin", "zh": "金輪", "en": "Kinrin", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1151020c1"},
    {"slug": "chigi-no-shiro", "zh": "千木の白", "en": "Chigi no Shiro", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1181040c1"},
    {"slug": "isuzu", "zh": "五十鈴", "en": "Isuzu", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1191040c1"},
    {"slug": "aoarashi", "zh": "青嵐", "en": "Aoarashi", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/11a1040c1"},
    {"slug": "kiwami-choan", "zh": "極 長安", "en": "Kiwami Choan", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1g36020c1"},
    {"slug": "wako", "zh": "和光", "en": "Wako", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1161020c1"},
    {"slug": "tenju", "zh": "天授", "en": "Tenju", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1111020c1"},
    {"slug": "yugen", "zh": "又玄", "en": "Yugen", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/1171020c1"},
    {"slug": "wakatake", "zh": "若竹", "en": "Wakatake", "url": "https://www.marukyu-koyamaen.co.jp/english/shop/products/11b1100c1"},
]

SLUGS = [p["slug"] for p in PRODUCTS]


def get_product(slug: str) -> dict:
    for product in PRODUCTS:
        if product["slug"] == slug:
            return product
    raise KeyError(f"Unknown product slug: {slug!r}")
