"""Kinrin authentication diagnostic. Never writes stock_state.json or sends LINE."""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

URL = 'https://www.marukyu-koyamaen.co.jp/english/shop/products/1151020c1'
ACCOUNT = 'https://www.marukyu-koyamaen.co.jp/english/shop/account'
SKU, VARIATION = '1151040C1', '16925'
OUT = Path('diagnostic-output')
FIELDS = ('is_in_stock', 'is_purchasable', 'variation_is_active',
          'variation_is_visible', 'stock_status', 'availability_html')


def save(name, value):
    OUT.mkdir(exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def signals(value):
    """Only retain objects explicitly identifying the target; never infer from price."""
    result = []
    if isinstance(value, dict):
        identity = str(value.get('variation_id', '')) == VARIATION or value.get('sku') == SKU
        contradictory = (value.get('sku') not in (None, '', SKU)
                         or str(value.get('variation_id', VARIATION)) != VARIATION)
        if identity and not contradictory:
            found = {k: value[k] for k in FIELDS if k in value}
            if found:
                # Stock HTML is reduced to stock text, not saved as arbitrary HTML.
                if 'availability_html' in found:
                    found['availability_html'] = re.sub('<[^>]+>', ' ', str(found['availability_html'])).strip()
                result.append(found)
        for child in value.values():
            result.extend(signals(child))
    elif isinstance(value, list):
        for child in value:
            result.extend(signals(child))
    return result


def classify(snapshot):
    if snapshot['challenge']:
        return 'UNKNOWN', 'CLOUDFLARE_CHALLENGE'
    if snapshot['login_required']:
        return 'UNKNOWN', 'LOGIN_REQUIRED'
    rows = snapshot['rows']
    if len(rows) != 1 or rows[0]['sku'] != SKU:
        return 'UNKNOWN', 'TARGET_MISSING_OR_AMBIGUOUS'
    row = rows[0]
    available = row['enabled_add_buttons'] > 0
    sold_out = bool(re.search(r'\bout\s+of\s+stock\b|\bsold\s*out\b', row['stock_text'], re.I))
    for item in snapshot['signals']:
        available |= item.get('is_in_stock') is True and item.get('is_purchasable') is True
        sold_out |= item.get('is_in_stock') is False or item.get('stock_status') == 'outofstock'
    if available and sold_out:
        return 'UNKNOWN', 'CONFLICTING_SIGNALS'
    if available:
        return 'AVAILABLE', 'EXPLICIT_SKU_SIGNAL'
    if sold_out:
        return 'SOLD_OUT', 'EXPLICIT_SKU_SIGNAL'
    return 'UNKNOWN', 'NO_EXPLICIT_SKU_SIGNAL'


def settle(page):
    try:
        page.wait_for_load_state('networkidle', timeout=15000)
    except PlaywrightTimeout:
        pass
    page.wait_for_timeout(2000)


def inspect(page):
    return page.evaluate('''() => {
      const text = document.body?.innerText || '';
      const rows = [...document.querySelectorAll('.product-form-row[data-variation_id="16925"]')];
      const country = document.querySelector('#calc_shipping_country');
      return {
        challenge: /Just a moment/i.test(document.title) || /Performing security verification|Verify you are human/.test(text),
        login_required: /You must\\s+register and login\\s+to shop/i.test(text),
        logged_in_marker: document.body.classList.contains('logged-in') || !!document.querySelector('a[href*="customer-logout"]'),
        total_rows: document.querySelectorAll('.product-form-row').length,
        rows: rows.map(r => ({
          sku: r.querySelector('.pa-sku dd')?.textContent.trim() || '',
          size: r.querySelector('.pa-size dd')?.textContent.trim() || '',
          stock_text: r.innerText,
          enabled_add_buttons: [...r.querySelectorAll('button.single_add_to_cart_button')].filter(b =>
            !b.disabled && b.getAttribute('aria-disabled') !== 'true' &&
            !b.classList.contains('disabled') && !b.classList.contains('wc-variation-is-unavailable') &&
            b.getClientRects().length > 0).length
        })),
        shipping_calculator: !!document.querySelector('#shipping-calculator-form, .shipping-calculator-form'),
        country_selector: !!country,
        us_option: country ? !!country.querySelector('option[value="US"]') : null,
        variation_json: [...document.querySelectorAll('[data-product_variations]')].map(e => e.getAttribute('data-product_variations')),
        json_scripts: [...document.querySelectorAll('script[type="application/json"], script[type="application/ld+json"]')].map(e => e.textContent),
        inline_keyword_counts: Object.fromEntries(['is_in_stock','is_purchasable','variation_is_active','1151040C1','16925'].map(k =>
          [k, [...document.scripts].filter(s => !s.src && s.textContent.includes(k)).length]))
      };
    }''')


def capture(page, label):
    network = []
    def response_seen(response):
        if response.request.resource_type not in ('xhr', 'fetch'):
            return
        parts = urlsplit(response.url)
        if parts.hostname != 'www.marukyu-koyamaen.co.jp' or not parts.path.startswith('/english/shop/'):
            return
        record = {'path': parts.path, 'status': response.status, 'signals': []}
        try:
            if 'json' in response.headers.get('content-type', ''):
                record['signals'] = signals(response.json())
        except Exception:
            record['json_read_error'] = True
        network.append(record)
    page.on('response', response_seen)
    try:
        response = page.goto(URL, wait_until='domcontentloaded', timeout=45000)
        settle(page)
        data = inspect(page)
        data['http_status'] = response.status if response else None
        data['signals'] = []
        for raw in data.pop('variation_json') + data.pop('json_scripts'):
            try:
                data['signals'].extend(signals(json.loads(raw)))
            except (ValueError, TypeError):
                pass
        for record in network:
            data['signals'].extend(record['signals'])
        data['status'], data['reason'] = classify(data)
        if data['http_status'] != 200 and not data['challenge']:
            data['status'], data['reason'] = 'UNKNOWN', 'HTTP_ERROR'
        data['network'] = network
        data['label'] = label
        data['observed_at'] = datetime.now(timezone.utc).isoformat()
        # Only screenshot target SKU: no account screen, cookie values or session files.
        row = page.locator('.product-form-row[data-variation_id="16925"]')
        if row.count() == 1:
            row.screenshot(path=str(OUT / f'{label}-kinrin-40g.png'))
        save(f'{label}.json', data)
        return data
    finally:
        page.remove_listener('response', response_seen)


def login(page, mode):
    username = os.environ.get('MARUKYU_USERNAME', '')
    password = os.environ.get('MARUKYU_PASSWORD', '')
    if not username or not password:
        return 'SECRETS_MISSING'
    documents = []
    def document_seen(response):
        if response.request.resource_type == 'document':
            parts = urlsplit(response.url)
            documents.append({'host': parts.hostname, 'path': parts.path,
                              'status': response.status})
    page.on('response', document_seen)
    try:
        page.goto(ACCOUNT, wait_until='domcontentloaded', timeout=45000)
        settle(page)
        # Observe whether an automatic check resolves; do not click challenges.
        for _ in range(6):
            if not inspect(page)['challenge']:
                break
            page.wait_for_timeout(5000)
        info = page.evaluate("""() => ({
            title: document.title,
            login_forms: document.querySelectorAll('form.woocommerce-form-login, form.login').length,
            human_verification: /Verify you are human/i.test(document.body?.innerText || ''),
            security_verification: /Performing security verification/i.test(document.body?.innerText || ''),
            frames: [...document.querySelectorAll('iframe[src]')].map(f => {
                try { const u = new URL(f.src); return {host: u.hostname, path: u.pathname}; }
                catch { return {host: 'unknown'}; }
            })
        })""")
        info['challenge'] = inspect(page)['challenge']
        info['documents'] = documents
        info['observed_at'] = datetime.now(timezone.utc).isoformat()
        save(f'{mode}-login-before-submit.json', info)
        # Fresh context, before filling credentials; mask all input elements.
        page.screenshot(path=str(OUT / f'{mode}-login-before-submit.png'),
                        full_page=False, mask=[page.locator('input')])
    finally:
        page.remove_listener('response', document_seen)
    if info['challenge']:
        return 'LOGIN_CHALLENGE' 
    form = page.locator('form.woocommerce-form-login, form.login').first
    if not form.count():
        return 'LOGIN_FORM_MISSING'
    # Standard WooCommerce fields; fail closed if the site changes.
    form.locator('input[name="username"]').fill(username)
    form.locator('input[name="password"]').fill(password)
    form.locator('button[name="login"], input[name="login"]').first.click()
    settle(page)
    cookies = page.context.cookies(URL)
    return 'LOGIN_COOKIE_PRESENT' if any(c['name'].startswith('wordpress_logged_in_') for c in cookies) else 'LOGIN_NOT_CONFIRMED'


def main():
    OUT.mkdir(exist_ok=True)
    summary = []
    with sync_playwright() as p:
        for mode in ('headed', 'headless'):
            browser = None
            try:
                browser = p.chromium.launch(headless=(mode == 'headless'))
                context = browser.new_context(locale='en-US', timezone_id='Asia/Tokyo', viewport={'width': 1440, 'height': 1600})
                page = context.new_page()
                guest = capture(page, f'{mode}-guest')
                summary.append(guest)
                outcome = login(page, mode)
                if outcome == 'LOGIN_COOKIE_PRESENT':
                    authenticated = capture(page, f'{mode}-authenticated')
                    authenticated['login_result'] = outcome
                    summary.append(authenticated)
                else:
                    summary.append({'label': f'{mode}-authenticated', 'status': 'UNKNOWN', 'reason': outcome})
            except Exception as error:
                # Avoid exception text: it can include account form contents.
                summary.append({'label': mode, 'status': 'UNKNOWN', 'reason': type(error).__name__})
            finally:
                if browser:
                    browser.close()
    save('summary.json', summary)
    for item in summary:
        print(item['label'], item['status'], item['reason'])
    print('Diagnostic only. No baseline updates and no notifications.')
    if not any(x.get('label', '').endswith('-authenticated') and x.get('status') in ('AVAILABLE', 'SOLD_OUT') for x in summary):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
