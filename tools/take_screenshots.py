"""Drive the real UI with Playwright (Microsoft Edge) against a demo server and save documentation
screenshots to docs/images/. It doubles as an end-to-end smoke test: any JavaScript error fails the run.

Usage (see docs/development.md):
    python manage.py seed_demo --owner-password ... --cashier-password ...   # on an EMPTY data dir
    python manage.py runserver 127.0.0.1:8010
    python tools/take_screenshots.py --base-url http://127.0.0.1:8010 --owner-password ... --cashier-password ...
"""
import argparse
import random
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

OUT = Path(__file__).resolve().parent.parent / 'docs' / 'images'
LAPTOP = {'width': 1366, 'height': 768}
PHONE = {'width': 390, 'height': 844}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8010')
    parser.add_argument('--owner-password', required=True)
    parser.add_argument('--cashier-password', required=True)
    parser.add_argument('--headed', action='store_true')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=not args.headed)

        def new_page(viewport, username=None, password=None, mobile=False):
            context = browser.new_context(viewport=viewport, locale='es-MX', timezone_id='America/Mexico_City', device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile)
            page = context.new_page()
            page.on('pageerror', lambda exc: errors.append(f'{page.url}: {exc}'))
            # Expected 404s (an unknown barcode lookup) are part of the flow; server errors are not.
            page.on('response', lambda response: response.status >= 500 and errors.append(f'{response.url}: HTTP {response.status}'))
            if username:
                page.goto(f'{args.base_url}/cuentas/login/')
                page.fill('input[name=username]', username)
                page.fill('input[name=password]', password)
                page.click('button.primary')
                page.wait_for_url(f'{args.base_url}/')
            return page

        def shot(page, name, full_page=False):
            page.screenshot(path=str(OUT / f'{name}.png'), full_page=full_page)
            print('saved', name)

        # Login screen
        page = new_page(LAPTOP)
        page.goto(f'{args.base_url}/cuentas/login/')
        shot(page, '01-login')

        # Cashier: checkout with a search, two scans, a bulk item and change calculation
        cashier = new_page(LAPTOP, 'lupita', args.cashier_password)
        shot(cashier, '02-home-cashier')
        cashier.goto(f'{args.base_url}/caja/')
        cashier.fill('#search', 'coca 600')
        cashier.locator('#results .result').first.click()
        cashier.fill('#search', '0000000000024')
        cashier.press('#search', 'Enter')
        expect(cashier.locator('#status')).to_contain_text('Sabritas')
        cashier.fill('#search', '0000000000017')
        cashier.press('#search', 'Enter')
        expect(cashier.locator('.cart-item input').first).to_have_value('2')
        cashier.fill('#search', '0000000000055')
        cashier.press('#search', 'Enter')
        expect(cashier.locator('#bulk-panel')).to_be_visible()
        cashier.fill('#bulk-grams', '350')
        expect(cashier.locator('#bulk-summary')).to_contain_text('0.350 kg')
        shot(cashier, '03-checkout-bulk')
        cashier.click('#bulk-add')
        cashier.fill('#paid-with', '200')
        expect(cashier.locator('#change')).not_to_have_text('—')
        expect(cashier.locator('#credit-box')).to_be_hidden()  # only shown for store credit
        shot(cashier, '04-checkout-cart', full_page=True)
        cashier.click('#charge')
        cashier.wait_for_url('**/ticket/')
        shot(cashier, '05-sale-ticket', full_page=True)
        sale_url = cashier.url

        cashier.goto(f'{args.base_url}/turnos/')
        cashier.select_option('select[name=kind]', 'supplier_payment')
        cashier.fill('input[name=cash_out_amount]', '120')
        cashier.fill('input[name=concept]', 'Repartidor Coca-Cola, nota 77')
        cashier.locator('form:has(input[name=concept]) button').click()
        cashier.wait_for_load_state()
        cashier.fill('input[name=d_b200]', '4')
        cashier.fill('input[name=d_b100]', '2')
        expect(cashier.locator('[data-total]')).to_contain_text('1,000.00')
        shot(cashier, '06-shifts-cash-count', full_page=True)

        # Return from the cashier's account: the owner's password is requested on the same screen
        cashier.goto(sale_url.replace('/ticket/', '/devolucion/'))
        cashier.locator('input[name^=quantity_]').first.fill('1')
        cashier.locator('select[name^=restock_]').first.select_option('0')
        cashier.fill('input[name=reason]', 'Lata abollada')
        cashier.fill('input[name=owner_username]', 'admin')
        cashier.fill('input[name=owner_password]', args.owner_password)
        shot(cashier, '07-sale-return')
        cashier.locator('form.card button.primary').click()
        cashier.wait_for_url('**/devoluciones/**')
        shot(cashier, '08-return-receipt', full_page=True)

        # Owner screens
        owner = new_page(LAPTOP, 'admin', args.owner_password)
        shot(owner, '09-home-owner')
        owner.goto(f'{args.base_url}/turnos/1/corte/')
        shot(owner, '10-shift-report', full_page=True)
        owner.goto(f'{args.base_url}/reportes/')
        shot(owner, '11-daily-report', full_page=True)
        owner.goto(f'{args.base_url}/ventas/')
        shot(owner, '12-sales-history')
        owner.goto(f'{args.base_url}/catalogo/?q=leche')
        shot(owner, '13-catalog')
        owner.goto(f'{args.base_url}/inventario/?q=coca')
        owner.locator('.count-row input[name=quantity]').first.fill('17')
        owner.locator('.count-row button').first.click()
        owner.wait_for_load_state()
        shot(owner, '14-inventory-count')
        owner.goto(f'{args.base_url}/clientes/')
        shot(owner, '15-credit-customers')
        owner.locator('a:has-text("Ver / abonar")').first.click()
        shot(owner, '16-credit-customer-detail')
        owner.goto(f'{args.base_url}/configuracion/')
        shot(owner, '17-store-settings')

        # Receiving on a phone: a known scan plus an unknown code
        phone = new_page(PHONE, 'admin', args.owner_password, mobile=True)
        phone.evaluate("localStorage.removeItem('store-receiving-draft')")
        phone.goto(f'{args.base_url}/inventario/recepcion/')
        phone.fill('#supplier', 'Coca-Cola (ruta)')
        phone.fill('#search', '0000000000017')
        phone.press('#search', 'Enter')
        expect(phone.locator('#scan-status')).to_contain_text('Coca-Cola')
        unknown_code = f'0000{random.randint(0, 10**9 - 1):09d}'  # fictitious and new on every run
        phone.fill('#search', unknown_code)
        phone.press('#search', 'Enter')
        expect(phone.locator('#unknown')).to_be_visible()
        phone.click('#show-create')
        phone.fill('#create-form input[name=name]', 'Agua mineral 1 L')
        phone.fill('#create-form input[name=price]', '19.50')
        shot(phone, '18-receiving-phone-unknown-code', full_page=True)
        phone.locator('#create-form button.primary').click()
        expect(phone.locator('#scan-status')).to_contain_text('Agua mineral')
        phone.fill('#cash-payment', '264')
        phone.click('#confirm')
        phone.wait_for_url('**/recepciones/**')
        shot(phone, '19-receipt-detail-phone', full_page=True)

        browser.close()

    if errors:
        print('\nJavaScript errors found:', *errors, sep='\n  ')
        sys.exit(1)
    print(f'\nAll screenshots saved in {OUT} without JavaScript errors.')


if __name__ == '__main__':
    main()
