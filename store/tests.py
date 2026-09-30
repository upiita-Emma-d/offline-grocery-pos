import json
import uuid
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import services
from .forms import ProductForm
from .models import CashOut, Customer, GoodsReceipt, Product, ProductStatusChange, RemovedLine, Sale, SaleReturn, Shift, StockCount, StockMovement, StoreSettings
from .services import adjust_count, close_shift, record_count, record_sale

User = get_user_model()


def post_json(client, url, body):
    return client.post(url, data=json.dumps(body), content_type='application/json')


class SaleRulesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='cashier', password='TestPassword123!')
        self.product = Product.objects.create(sku='MILK', name='Leche', price=Decimal('30.00'))
        self.shift = Shift.objects.create(cashier=self.user, opening_float=Decimal('100.00'))
        StockMovement.objects.create(product=self.product, quantity=10, kind='receipt', reason='Compra', user=self.user)

    def make_owner(self):
        self.user.is_superuser = True
        self.user.save(update_fields=['is_superuser'])

    def test_retry_does_not_duplicate_sale_or_stock_movement(self):
        data = dict(user=self.user, request_id=uuid.uuid4(), items=[{'product_id': self.product.id, 'quantity': '2'}], payment='cash')
        first, created = record_sale(**data)
        second, repeated = record_sale(**data)
        self.assertTrue(created)
        self.assertFalse(repeated)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Sale.objects.count(), 1)
        self.assertEqual(self.product.stock, Decimal('8'))
        self.assertEqual(first.total, Decimal('60.00'))

    def test_closing_reconciles_cash(self):
        record_sale(user=self.user, request_id=uuid.uuid4(), items=[{'product_id': self.product.id, 'quantity': '1'}], payment='cash')
        closed = close_shift(shift=self.shift, counted_cash=Decimal('125.00'))
        self.assertEqual(closed.expected_cash, Decimal('130.00'))
        self.assertEqual(closed.difference, Decimal('-5.00'))

    def test_count_does_not_change_stock(self):
        StockCount.objects.create(product=self.product, expected=10, counted=8, difference=-2, user=self.user)
        self.assertEqual(self.product.stock, Decimal('10'))

    def test_operation_screens_respond(self):
        self.client.force_login(self.user)
        for name in ['home', 'checkout', 'shifts', 'sales']:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertEqual(self.client.get(reverse('catalog')).status_code, 403)

    def test_owner_can_see_catalog_and_inventory(self):
        self.make_owner()
        self.client.force_login(self.user)
        for name in ['catalog', 'inventory', 'product_new', 'receiving', 'report', 'store_settings']:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_http_flow_receipt_sale_ticket_and_close(self):
        self.make_owner()
        self.client.force_login(self.user)
        receipt = post_json(self.client, reverse('receipt_confirm'), {'request_id': str(uuid.uuid4()), 'supplier': 'Proveedor demo', 'document': 'Factura demo', 'items': [{'product_id': self.product.id, 'quantity': '3'}]})
        self.assertEqual(receipt.status_code, 200)
        body = {'request_id': str(uuid.uuid4()), 'payment': 'cash', 'items': [{'product_id': self.product.id, 'quantity': '2'}]}
        first = post_json(self.client, reverse('charge'), body)
        second = post_json(self.client, reverse('charge'), body)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.json()['created'], False)
        self.assertEqual(self.product.stock, Decimal('11'))
        self.assertContains(self.client.get(reverse('sale_ticket', args=[first.json()['folio']])), 'Leche')
        close = self.client.post(reverse('shifts'), {'action': 'close', 'amount': '155.00'})
        self.assertEqual(close.status_code, 302)
        self.shift.refresh_from_db()
        self.assertEqual(self.shift.difference, Decimal('-5.00'))

    def test_lookup_requires_exact_code_and_keeps_leading_zeros(self):
        self.product.barcode = '00750012345678'
        self.product.save(update_fields=['barcode'])
        self.client.force_login(self.user)
        url = reverse('barcode_lookup')
        found = self.client.get(url, {'code': '00750012345678'})
        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.json()['product']['id'], self.product.id)
        self.assertEqual(found.json()['product']['barcode'], '00750012345678')
        self.assertEqual(self.client.get(url, {'code': '750012345678'}).status_code, 404)
        self.assertEqual(self.client.get(url, {'code': 'MIL'}).status_code, 404)
        self.assertEqual(self.client.get(url, {'code': 'milk'}).json()['product']['id'], self.product.id)

    def test_reversible_deactivation_requires_owner_reason_and_zero_stock(self):
        url = reverse('product_status', args=[self.product.id])
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(url, {'reason': 'Prueba de baja'}).status_code, 403)
        self.make_owner()
        self.assertNotIn('active', ProductForm.base_fields)
        self.client.post(url, {'reason': 'Prueba de baja'})
        self.product.refresh_from_db()
        self.assertTrue(self.product.active)
        self.assertEqual(ProductStatusChange.objects.count(), 0)
        StockMovement.objects.create(product=self.product, quantity=-10, kind='adjustment', reason='Conciliación de prueba', user=self.user)
        self.client.post(url, {'reason': 'Prueba de baja'})
        self.product.refresh_from_db()
        self.assertFalse(self.product.active)
        self.assertEqual(self.client.get(reverse('barcode_lookup'), {'code': self.product.sku}).status_code, 404)
        self.assertEqual(ProductStatusChange.objects.get().action, 'deactivate')
        attempt = post_json(self.client, reverse('receipt_confirm'), {'request_id': str(uuid.uuid4()), 'supplier': 'Intento', 'items': [{'product_id': self.product.id, 'quantity': '5'}]})
        self.assertEqual(attempt.status_code, 400)
        self.client.post(reverse('inventory'), {'action': 'count', 'product_id': self.product.id, 'quantity': '5'})
        self.assertFalse(StockCount.objects.exists())
        self.assertEqual(self.product.stock, Decimal('0'))
        self.client.post(url, {'reason': 'Regresa al catálogo'})
        self.product.refresh_from_db()
        self.assertTrue(self.product.active)
        self.assertEqual(ProductStatusChange.objects.count(), 2)

    def test_new_product_and_historic_price_on_ticket(self):
        self.make_owner()
        self.client.force_login(self.user)
        created = self.client.post(reverse('product_new'), {'sku': 'TEST1', 'barcode': '0000000000017', 'name': 'Producto de prueba', 'unit': 'piece', 'price': '17.25', 'min_stock': '0'})
        self.assertEqual(created.status_code, 302)
        self.assertTrue(Product.objects.filter(sku='TEST1', barcode='0000000000017').exists())
        sale, _ = record_sale(user=self.user, request_id=uuid.uuid4(), items=[{'product_id': self.product.id, 'quantity': '1'}], payment='cash')
        self.client.post(reverse('product_price', args=[self.product.id]), {'price': '99.00'})
        self.assertEqual(sale.lines.get().unit_price, Decimal('30.00'))
        self.assertContains(self.client.get(reverse('sale_ticket', args=[sale.id])), '$30.00')

    def test_transfer_does_not_increase_expected_cash(self):
        record_sale(user=self.user, request_id=uuid.uuid4(), items=[{'product_id': self.product.id, 'quantity': '2'}], payment='transfer')
        closed = close_shift(shift=self.shift, counted_cash=Decimal('100.00'))
        self.assertEqual(closed.expected_cash, Decimal('100.00'))
        self.assertEqual(closed.difference, Decimal('0.00'))


class InventoryTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser(username='owner', password='TestPassword123!')
        self.cashier = User.objects.create_user(username='cashier', password='TestPassword123!')
        self.product = Product.objects.create(sku='MILK', name='Leche', price=Decimal('30.00'))
        StockMovement.objects.create(product=self.product, quantity=8, kind='receipt', reason='Compra', user=self.owner)
        Shift.objects.create(cashier=self.owner, opening_float=Decimal('0'))

    def receive(self, user=None, **changes):
        self.client.force_login(user or self.owner)
        body = {'request_id': str(uuid.uuid4()), 'supplier': 'Lala', 'document': 'F-10', 'items': [{'product_id': self.product.id, 'quantity': '2'}, {'product_id': self.product.id, 'quantity': '1'}]}
        body.update(changes)
        return post_json(self.client, reverse('receipt_confirm'), body), body

    def test_adjustment_applies_the_count_difference_even_after_later_sales(self):
        count = record_count(user=self.owner, product=self.product, counted='7')
        self.assertEqual(count.difference, Decimal('-1'))
        record_sale(user=self.owner, request_id=uuid.uuid4(), items=[{'product_id': self.product.id, 'quantity': '2'}], payment='cash')
        adjust_count(user=self.owner, count_id=count.id)
        self.assertEqual(self.product.stock, Decimal('5'))
        with self.assertRaises(services.OperationError):
            adjust_count(user=self.owner, count_id=count.id)

    def test_only_the_latest_count_can_be_adjusted(self):
        old = record_count(user=self.owner, product=self.product, counted='7')
        new = record_count(user=self.owner, product=self.product, counted='6')
        with self.assertRaises(services.OperationError):
            adjust_count(user=self.owner, count_id=old.id)
        self.client.force_login(self.owner)
        self.client.post(reverse('inventory'), {'action': 'adjust', 'count_id': new.id})
        self.assertEqual(self.product.stock, Decimal('6'))
        self.assertContains(self.client.get(reverse('inventory')), 'Reemplazado por un conteo posterior')

    def test_receipt_groups_merges_lines_and_is_not_duplicated(self):
        first, body = self.receive()
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()['created'])
        second = post_json(self.client, reverse('receipt_confirm'), body)
        self.assertFalse(second.json()['created'])
        receipt = GoodsReceipt.objects.get()
        self.assertEqual(receipt.movements.get().quantity, Decimal('3'))
        self.assertIn('F-10', receipt.movements.get().reason)
        self.assertEqual(self.product.stock, Decimal('11'))
        self.assertContains(self.client.get(first.json()['url']), 'Leche')

    def test_receipt_requires_owner_and_supplier(self):
        response, _ = self.receive(user=self.cashier)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get(reverse('receiving')).status_code, 403)
        response, _ = self.receive(supplier='  ')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(GoodsReceipt.objects.exists())

    def test_barcode_is_only_assigned_to_products_without_one(self):
        self.client.force_login(self.owner)
        url = reverse('assign_barcode', args=[self.product.id])
        self.assertEqual(post_json(self.client, url, {'barcode': '0750100000017'}).status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.barcode, '0750100000017')
        self.assertEqual(post_json(self.client, url, {'barcode': '0750100000024'}).status_code, 400)
        water = Product.objects.create(sku='WATER', name='Agua', price=Decimal('12.00'))
        self.assertEqual(post_json(self.client, reverse('assign_barcode', args=[water.id]), {'barcode': '0750100000017'}).status_code, 400)
        self.client.force_login(self.cashier)
        self.assertEqual(post_json(self.client, reverse('assign_barcode', args=[water.id]), {'barcode': '1'}).status_code, 403)

    def test_quick_create_uses_barcode_as_sku_when_missing(self):
        self.client.force_login(self.owner)
        response = post_json(self.client, reverse('quick_create'), {'barcode': '0007501', 'name': 'Gansito', 'price': '21.00', 'unit': 'piece'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Product.objects.get(barcode='0007501').sku, '0007501')
        self.assertEqual(post_json(self.client, reverse('quick_create'), {'barcode': '0007501', 'name': 'Otro', 'price': '1'}).status_code, 400)
        self.assertEqual(post_json(self.client, reverse('quick_create'), {'barcode': '999', 'name': 'Sin precio'}).status_code, 400)

    def test_inventory_finds_exact_barcode(self):
        self.product.barcode = '0750100000017'
        self.product.save(update_fields=['barcode'])
        Product.objects.create(sku='MILK2', name='Leche deslactosada', price=Decimal('33.00'))
        self.client.force_login(self.owner)
        self.assertEqual(len(self.client.get(reverse('inventory'), {'q': '0750100000017'}).context['found']), 1)
        self.assertEqual(len(self.client.get(reverse('inventory'), {'q': 'leche'}).context['found']), 2)

    def test_search_matches_every_word_in_any_order(self):
        Product.objects.create(sku='COCA600', name='Coca-Cola 600 ml', price=Decimal('22.00'))
        Product.objects.create(sku='COCA2L', name='Coca-Cola 2 L', price=Decimal('39.00'))
        self.client.force_login(self.cashier)
        names = lambda q: [p['name'] for p in self.client.get(reverse('product_search'), {'q': q}).json()['products']]
        self.assertEqual(names('coca 600'), ['Coca-Cola 600 ml'])
        self.assertEqual(names('600 coca'), ['Coca-Cola 600 ml'])
        self.assertEqual(len(names('coca')), 2)
        self.assertEqual(names('coca 3 litros'), [])

    def test_negative_stock_is_shown_separately(self):
        record_sale(user=self.owner, request_id=uuid.uuid4(), items=[{'product_id': self.product.id, 'quantity': '10'}], payment='cash')
        self.client.force_login(self.owner)
        response = self.client.get(reverse('home'))
        self.assertEqual([p.id for p in response.context['negative']], [self.product.id])
        self.assertEqual(response.context['low'], [])

    def test_simultaneous_submission_returns_the_existing_sale(self):
        data = dict(user=self.owner, request_id=uuid.uuid4(), items=[{'product_id': self.product.id, 'quantity': '1'}], payment='cash')
        first, _ = record_sale(**data)
        original = services.find_previous
        calls = []

        def blind_first_time(model, key, user):
            # Simulates that the other submission was not yet visible: the insert hits the unique key.
            calls.append(model)
            return None if len(calls) == 1 else original(model, key, user)

        with mock.patch.object(services, 'find_previous', side_effect=blind_first_time):
            second, created = record_sale(**data)
        self.assertFalse(created)
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(Sale.objects.count(), 1)
        self.assertEqual(self.product.stock, Decimal('7'))

    def test_reference_catalog_with_sample_receipt(self):
        call_command('seed_catalog', with_stock='owner', stdout=mock.MagicMock())
        coke = Product.objects.get(sku='COCA600')
        self.assertEqual(coke.stock, Decimal('24'))
        self.assertIsNone(coke.barcode)
        self.assertEqual(GoodsReceipt.objects.get().supplier, 'Carga inicial de ensayo')
        call_command('seed_catalog', with_stock='owner', stdout=mock.MagicMock())
        self.assertEqual(GoodsReceipt.objects.count(), 1)
        self.assertEqual(coke.stock, Decimal('24'))


class BulkSaleTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser(username='owner', password='TestPassword123!')
        self.cheese = Product.objects.create(sku='CHEESE', name='Queso panela', unit='kg', price=Decimal('150.00'))
        self.ham = Product.objects.create(sku='HAM', name='Jamón', unit='kg', price=Decimal('140.00'))
        Shift.objects.create(cashier=self.owner, opening_float=Decimal('0'))

    def sell(self, *lines):
        return record_sale(user=self.owner, request_id=uuid.uuid4(), items=[{'product_id': p.id, 'quantity': q} for p, q in lines], payment='cash')[0]

    def test_grams_and_amount_are_charged_at_price_per_kilo(self):
        # 400 g of cheese at $150/kg and "50 pesos of ham" converted to 0.357 kg by the checkout screen.
        sale = self.sell((self.cheese, 0.4), (self.ham, 0.357))
        self.assertEqual(sale.lines.get(product=self.cheese).subtotal, Decimal('60.00'))
        self.assertEqual(sale.lines.get(product=self.ham).subtotal, Decimal('49.98'))
        self.assertEqual(sale.total, Decimal('109.98'))
        self.assertEqual(self.cheese.stock, Decimal('-0.4'))

    def test_fractions_below_one_gram_are_rejected(self):
        with self.assertRaises(services.OperationError):
            self.sell((self.cheese, '0.0005'))
        self.assertFalse(Sale.objects.exists())

    def test_lookup_reports_bulk_products(self):
        self.cheese.barcode = '2000000000015'
        self.cheese.save(update_fields=['barcode'])
        self.client.force_login(self.owner)
        self.assertTrue(self.client.get(reverse('barcode_lookup'), {'code': '2000000000015'}).json()['product']['is_bulk'])
        self.assertTrue(self.client.get(reverse('product_search'), {'q': 'queso'}).json()['products'][0]['is_bulk'])
        Product.objects.create(sku='COKE', name='Coca', price=Decimal('22.00'))
        coke = self.client.get(reverse('product_search'), {'q': 'coca'}).json()['products'][0]
        self.assertFalse(coke['is_bulk'])
        self.assertEqual(coke['unit_label'], 'pieza')

    def test_unit_comes_from_a_closed_list(self):
        data = {'sku': 'X1', 'name': 'Prueba', 'price': '10', 'min_stock': '0'}
        self.assertFalse(ProductForm({**data, 'unit': 'Kilo'}).is_valid())
        self.assertTrue(ProductForm({**data, 'unit': 'kg'}).is_valid())


class CashControlTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser(username='owner', password='OwnerPassword123!')
        self.cashier = User.objects.create_user(username='cashier', password='CashierPassword123!')
        self.milk = Product.objects.create(sku='MILK', name='Leche', price=Decimal('30.00'))
        self.cheese = Product.objects.create(sku='CHEESE', name='Queso', unit='kg', price=Decimal('45.55'))
        for product in (self.milk, self.cheese):
            StockMovement.objects.create(product=product, quantity=20, kind='receipt', reason='Inicial', user=self.owner)

    def open(self, user, **pieces):
        self.client.force_login(user)
        self.client.post(reverse('shifts'), {'action': 'open', **{f'd_{k}': v for k, v in pieces.items()}})
        return Shift.objects.get(closed_at__isnull=True)

    def sell(self, user, payment='cash', customer=None, **quantities):
        products = {'milk': self.milk, 'cheese': self.cheese}
        return record_sale(user=user, request_id=uuid.uuid4(), items=[{'product_id': products[k].id, 'quantity': v} for k, v in quantities.items()], payment=payment, customer_id=customer.id if customer else None)[0]

    def return_items(self, sale, lines, user=None, **authorization):
        self.client.force_login(user or self.owner)
        data = {'request_id': str(uuid.uuid4()), 'reason': 'Producto en mal estado', **authorization}
        for line, (quantity, restock) in lines.items():
            data[f'quantity_{line.id}'] = quantity
            data[f'restock_{line.id}'] = '1' if restock else '0'
        return self.client.post(reverse('sale_return', args=[sale.id]), data)

    def test_expected_cash_includes_sales_returns_cash_outs_and_credit_payments(self):
        # Opening float of $1,700: three $500 bills and two $100 bills.
        shift = self.open(self.cashier, b500=3, b100=2)
        self.assertEqual(shift.opening_float, Decimal('1700'))
        self.assertEqual(shift.opening_count, {'b500': 3, 'b100': 2})
        sale = self.sell(self.cashier, milk=4)
        self.client.post(reverse('shifts'), {'action': 'cash_out', 'request_id': str(uuid.uuid4()), 'kind': 'supplier_payment', 'cash_out_amount': '300', 'concept': 'Repartidor Lala'})
        self.client.force_login(self.owner)
        receipt = post_json(self.client, reverse('receipt_confirm'), {'request_id': str(uuid.uuid4()), 'supplier': 'Bimbo', 'cash_payment': '200', 'items': [{'product_id': self.milk.id, 'quantity': 5}]})
        self.assertEqual(receipt.status_code, 200)
        self.return_items(sale, {sale.lines.get(): ('1', True)})
        customer = Customer.objects.create(name='Doña Mari')
        self.sell(self.cashier, payment='credit', customer=customer, milk=2)
        self.client.force_login(self.cashier)
        self.client.post(reverse('customer_detail', args=[customer.id]), {'request_id': str(uuid.uuid4()), 'amount': '50', 'payment': 'cash'})
        # 1700 + 120 sales − 30 return − 300 − 200 cash outs + 50 credit payment
        close = self.client.post(reverse('shifts'), {'action': 'close', 'd_b1000': '1', 'd_b200': '1', 'd_b100': '1', 'd_c10': '2'})
        shift.refresh_from_db()
        self.assertRedirects(close, reverse('shift_report', args=[shift.id]))
        self.assertEqual(shift.expected_cash, Decimal('1340'))
        self.assertEqual(shift.counted_cash, Decimal('1320'))
        self.assertEqual(shift.difference, Decimal('-20'))
        report = self.client.get(reverse('shift_report', args=[shift.id]))
        self.assertContains(report, 'Repartidor Lala')
        self.assertContains(report, 'Moneda $10 × 2')

    def test_shift_report_is_hidden_until_closed(self):
        shift = self.open(self.cashier, b100=5)
        self.assertEqual(self.client.get(reverse('shift_report', args=[shift.id])).status_code, 403)

    def test_cash_out_requires_own_shift_and_concept_and_is_not_duplicated(self):
        with self.assertRaises(services.OperationError):
            services.record_cash_out(user=self.cashier, request_id=uuid.uuid4(), kind='expense', amount='10', concept='Garrafón')
        self.open(self.owner, b100=1)
        with self.assertRaises(services.OperationError):
            services.record_cash_out(user=self.cashier, request_id=uuid.uuid4(), kind='expense', amount='10', concept='Garrafón')
        with self.assertRaises(services.OperationError):
            services.record_cash_out(user=self.owner, request_id=uuid.uuid4(), kind='expense', amount='10', concept='')
        key = uuid.uuid4()
        services.record_cash_out(user=self.owner, request_id=key, kind='drop', amount='500', concept='A la caja fuerte')
        _, created = services.record_cash_out(user=self.owner, request_id=key, kind='drop', amount='500', concept='A la caja fuerte')
        self.assertFalse(created)
        self.assertEqual(CashOut.objects.count(), 1)

    def test_return_requires_owner_password(self):
        self.open(self.cashier, b100=5)
        sale = self.sell(self.cashier, milk=2)
        line = sale.lines.get()
        self.return_items(sale, {line: ('1', True)}, user=self.cashier, owner_username='owner', owner_password='wrong')
        self.return_items(sale, {line: ('1', True)}, user=self.cashier, owner_username='cashier', owner_password='CashierPassword123!')
        self.assertFalse(SaleReturn.objects.exists())
        self.return_items(sale, {line: ('1', True)}, user=self.cashier, owner_username='owner', owner_password='OwnerPassword123!')
        record = SaleReturn.objects.get()
        self.assertEqual((record.user, record.authorized_by, record.total), (self.cashier, self.owner, Decimal('30.00')))

    def test_return_never_exceeds_what_was_sold_and_cents_add_up(self):
        self.open(self.owner, b100=5)
        sale = self.sell(self.owner, cheese='0.3')
        line = sale.lines.get()
        self.assertEqual(line.subtotal, Decimal('13.67'))
        for _ in range(3):
            self.return_items(sale, {line: ('0.1', True)})
        self.assertEqual(sum(r.total for r in SaleReturn.objects.all()), Decimal('13.67'))
        self.return_items(sale, {line: ('0.1', True)})
        self.assertEqual(SaleReturn.objects.count(), 3)
        self.assertEqual(self.cheese.stock, Decimal('20'))

    def test_waste_does_not_go_back_to_stock(self):
        self.open(self.owner, b100=5)
        sale = self.sell(self.owner, milk=3)
        self.return_items(sale, {sale.lines.get(): ('3', False)})
        self.assertEqual(self.milk.stock, Decimal('17'))
        self.assertEqual(SaleReturn.objects.get().total, Decimal('90.00'))

    def test_cash_return_requires_an_open_shift(self):
        shift = self.open(self.owner, b100=5)
        sale = self.sell(self.owner, milk=1)
        services.close_shift(shift=shift, counted_cash=Decimal('530'))
        self.return_items(sale, {sale.lines.get(): ('1', True)})
        self.assertFalse(SaleReturn.objects.exists())

    def test_store_credit_limit_return_and_payments(self):
        self.open(self.cashier, b100=5)
        customer = Customer.objects.create(name='Don Pepe', credit_limit=Decimal('100'))
        with self.assertRaises(services.OperationError):
            self.sell(self.cashier, payment='credit', milk=1)
        sale = self.sell(self.cashier, payment='credit', customer=customer, milk=3)
        with self.assertRaises(services.OperationError):
            self.sell(self.cashier, payment='credit', customer=customer, milk=1)
        self.return_items(sale, {sale.lines.get(): ('1', True)})
        self.assertEqual(services.customer_balance(customer), Decimal('60.00'))
        with self.assertRaises(services.OperationError):
            services.record_credit_payment(user=self.cashier, request_id=uuid.uuid4(), customer=customer, amount='61', payment='cash')
        services.record_credit_payment(user=self.cashier, request_id=uuid.uuid4(), customer=customer, amount='60', payment='transfer')
        self.assertEqual(services.customer_balance(customer), Decimal('0'))
        self.assertEqual(services.shift_summary(Shift.objects.get())['cash_payments'], Decimal('0'))
        customer.active = False
        customer.save()
        with self.assertRaises(services.OperationError):
            self.sell(self.cashier, payment='credit', customer=customer, milk=1)

    def test_only_owner_registers_customers(self):
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get(reverse('customer_new')).status_code, 403)
        self.assertEqual(self.client.get(reverse('customers')).status_code, 403)
        self.open(self.cashier, b100=1)
        self.assertEqual(self.client.get(reverse('customers')).status_code, 200)
        self.client.force_login(self.owner)
        self.client.post(reverse('customer_new'), {'name': 'Doña Lupe', 'phone': '', 'credit_limit': '500', 'active': 'on'})
        self.assertEqual(Customer.objects.get().credit_limit, Decimal('500'))

    def test_receipt_cost_is_frozen_in_the_sale_and_gives_margin(self):
        self.open(self.owner, b100=1)
        post_json(self.client, reverse('receipt_confirm'), {'request_id': str(uuid.uuid4()), 'supplier': 'Lala', 'items': [{'product_id': self.milk.id, 'quantity': 12, 'cost': '24.50'}]})
        self.milk.refresh_from_db()
        self.assertEqual(self.milk.cost, Decimal('24.50'))
        sale = self.sell(self.owner, milk=2)
        self.milk.cost = Decimal('26.00')
        self.milk.save()
        self.assertEqual(sale.lines.get().unit_cost, Decimal('24.50'))
        report = self.client.get(reverse('report'))
        self.assertEqual(report.context['margin'], Decimal('11.00'))
        self.assertEqual(report.context['net'], Decimal('60.00'))

    def test_removed_lines_are_logged_in_the_shift(self):
        shift = self.open(self.cashier, b100=1)
        body = {'request_id': str(uuid.uuid4()), 'product_id': self.milk.id, 'quantity': 2, 'reason': 'removed'}
        self.assertEqual(post_json(self.client, reverse('removed_line'), body).status_code, 200)
        post_json(self.client, reverse('removed_line'), body)
        self.assertEqual(RemovedLine.objects.get().unit_price, Decimal('30.00'))
        self.assertEqual(services.shift_summary(shift)['removed'], 1)

    def test_sales_history_filters_and_cashier_sees_only_own_sales(self):
        self.open(self.owner, b100=1)
        self.sell(self.owner, milk=1)
        self.sell(self.owner, payment='card', milk=2)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse('sales'), {'payment': 'card'}).context['summary']['n'], 1)
        self.assertEqual(self.client.get(reverse('sales'), {'from': timezone.localdate().isoformat()}).context['summary']['n'], 2)
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get(reverse('sales')).context['summary']['n'], 0)
        self.assertEqual(self.client.get(reverse('report')).status_code, 403)

    def test_cash_count_rejects_invalid_pieces(self):
        with self.assertRaises(services.OperationError):
            services.parse_cash_count({'d_b100': '1.5'}, '')
        self.assertEqual(services.parse_cash_count({'d_c050': '3', 'd_b20': '1'}, '999'), ({'b20': 1, 'c050': 3}, Decimal('21.50')))
        self.assertEqual(services.parse_cash_count({}, '850.50'), ({}, Decimal('850.50')))


class FormattingTests(TestCase):
    def test_money_always_has_cents(self):
        from .templatetags.store_tags import money, unit_label
        self.assertEqual(money(Decimal('73')), '$73.00')
        self.assertEqual(money(Decimal('1262.5')), '$1,262.50')
        self.assertEqual(money(Decimal('-5')), '-$5.00')
        self.assertEqual(money(None), '$0.00')
        self.assertEqual(unit_label('piece'), 'pieza')


class FakePrinter:
    """Replaces socket.create_connection and keeps what was sent, without touching the network."""

    def __init__(self, fail=False):
        self.fail, self.sent, self.targets = fail, [], []

    def __call__(self, target, timeout=None):
        self.targets.append(target)
        if self.fail:
            raise OSError('Tiempo de espera agotado')
        printer = self

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def sendall(self, data):
                printer.sent.append(data)
        return Connection()


class TicketPrintingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username='owner', password='OwnerPassword123!')
        product = Product.objects.create(sku='MILK', name='Leche', price=Decimal('30.00'))
        Shift.objects.create(cashier=self.user, opening_float=Decimal('0'))
        self.sale = record_sale(user=self.user, request_id=uuid.uuid4(), items=[{'product_id': product.id, 'quantity': '1'}], payment='cash')[0]
        self.client.force_login(self.user)

    def test_without_network_printer_reprint_is_not_offered(self):
        with mock.patch.dict('os.environ', {'POS_PRINTER_HOST': ''}):
            page = self.client.get(reverse('sale_ticket', args=[self.sale.id]))
            self.assertNotContains(page, 'Reenviar a Epson')
            self.assertContains(page, 'Imprimir ticket')
            response = self.client.post(reverse('sale_reprint', args=[self.sale.id]), follow=True)
        self.assertContains(response, 'No hay impresora de red configurada')
        self.assertEqual(Sale.objects.count(), 1)

    def test_with_network_printer_reprint_is_offered(self):
        with mock.patch.dict('os.environ', {'POS_PRINTER_HOST': '192.0.2.10'}):
            self.assertContains(self.client.get(reverse('sale_ticket', args=[self.sale.id])), 'Reenviar a Epson')


class ShiftPrintingTests(TestCase):
    def setUp(self):
        self.cashier = User.objects.create_user(username='cashier', password='CashierPassword123!')
        self.milk = Product.objects.create(sku='MILK', name='Leche', price=Decimal('30.00'))
        self.client.force_login(self.cashier)
        env = mock.patch.dict('os.environ', {'POS_PRINTER_HOST': '192.0.2.50', 'POS_PRINTER_PORT': '9100', 'POS_PRINTER_COLUMNS': '42'})
        env.start()
        self.addCleanup(env.stop)

    def test_opening_and_closing_print_shift_documents(self):
        printer = FakePrinter()
        with mock.patch('store.services.socket.create_connection', printer):
            self.client.post(reverse('shifts'), {'action': 'open', 'd_b500': '3', 'd_b100': '2'})
            shift = Shift.objects.get()
            record_sale(user=self.cashier, request_id=uuid.uuid4(), items=[{'product_id': self.milk.id, 'quantity': '2'}], payment='cash')
            self.client.post(reverse('shifts'), {'action': 'close', 'd_b1000': '1', 'd_b500': '1', 'd_b200': '1', 'd_c20': '3'})
        self.assertEqual(printer.targets[0], ('192.0.2.50', 9100))
        opening, closing = printer.sent[0], printer.sent[-1]
        self.assertIn(b'Apertura de turno', opening)
        self.assertIn(b'Billete $500 x 3', opening)
        self.assertIn(b'$1,700.00', opening)
        self.assertTrue(opening.startswith(b'\x1b@') and opening.endswith(b'\x1dVB\x03'))
        self.assertIn(b'Corte de turno', closing)
        self.assertIn(b'ESPERADO', closing)
        self.assertIn(b'$1,760.00', closing)
        self.assertEqual(list(shift.print_attempts.values_list('document', 'result')), [('shift_open', 'ok'), ('shift_close', 'ok')])

    def test_printer_failure_does_not_prevent_opening_the_shift(self):
        with mock.patch('store.services.socket.create_connection', FakePrinter(fail=True)):
            response = self.client.post(reverse('shifts'), {'action': 'open', 'd_b100': '5'}, follow=True)
        shift = Shift.objects.get()
        self.assertEqual(shift.opening_float, Decimal('500'))
        self.assertEqual(shift.print_attempts.get().result, 'failed')
        self.assertContains(response, 'No se pudo imprimir la apertura')

    def test_columns_set_the_line_width(self):
        self.assertEqual(len(services.two_columns('TOTAL', '$94.50', 42)), 42)
        self.assertEqual(services.printer_text('Recepción ñ'), b'Recepcion n')

    def test_without_ip_it_never_connects(self):
        with mock.patch.dict('os.environ', {'POS_PRINTER_HOST': ''}), mock.patch('store.services.socket.create_connection') as connect:
            self.client.post(reverse('shifts'), {'action': 'open', 'd_b100': '1'})
        connect.assert_not_called()
        self.assertEqual(Shift.objects.get().print_attempts.get().result, 'manual')


class StoreSettingsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser(username='owner', password='OwnerPassword123!')
        self.cashier = User.objects.create_user(username='cashier', password='CashierPassword123!')
        self.milk = Product.objects.create(sku='MILK', name='Leche Lala 1 L', price=Decimal('30.00'))
        self.cheese = Product.objects.create(sku='CHEESE', name='Queso panela', unit='kg', price=Decimal('150.00'))
        Shift.objects.create(cashier=self.owner, opening_float=Decimal('0'))

    def test_only_owner_configures_and_name_is_shown(self):
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get(reverse('store_settings')).status_code, 403)
        self.client.force_login(self.owner)
        self.client.post(reverse('store_settings'), {'name': 'Abarrotes La Esquina', 'header': 'Calle Hidalgo 5\nTel. 55 1234', 'footer': '¡Gracias, vuelva pronto!'})
        sale = record_sale(user=self.owner, request_id=uuid.uuid4(), items=[{'product_id': self.milk.id, 'quantity': '2'}, {'product_id': self.cheese.id, 'quantity': '0.4'}], payment='cash')[0]
        page = self.client.get(reverse('sale_ticket', args=[sale.id]))
        self.assertContains(page, 'Abarrotes La Esquina', count=2)  # browser tab title and ticket
        self.assertContains(page, 'ABARROTES LA ESQUINA')  # top bar
        self.assertContains(page, 'Calle Hidalgo 5')
        self.assertContains(page, 'Artículos: 2 + 1 a granel')

    def test_network_ticket_has_name_footer_and_accents(self):
        StoreSettings.objects.update_or_create(pk=1, defaults={'name': 'Abarrotes La Esquina', 'footer': '¡Gracias por su compra!'})
        sale = record_sale(user=self.owner, request_id=uuid.uuid4(), items=[{'product_id': self.milk.id, 'quantity': '12'}], payment='cash')[0]
        printer = FakePrinter()
        with mock.patch.dict('os.environ', {'POS_PRINTER_HOST': '192.0.2.50', 'POS_PRINTER_COLUMNS': '42', 'POS_PRINTER_ACCENTS': '1'}), mock.patch('store.services.socket.create_connection', printer):
            self.assertTrue(services.print_sale(sale))
        data = printer.sent[0]
        self.assertTrue(data.startswith(b'\x1b@\x1bt\x10'))
        self.assertIn(b'Abarrotes La Esquina', data)
        self.assertIn('Atendió'.encode('cp1252'), data)
        self.assertIn('¡Gracias por su compra!'.encode('cp1252'), data)
        self.assertIn(b'Art\xedculos: 12', data)

    def test_long_name_wraps_for_double_width_font(self):
        self.assertEqual(services.wrap('Abarrotes y Cremería La Esperanza del Centro', 21), ['Abarrotes y Cremería', 'La Esperanza del', 'Centro'])


class DemoDataTests(TestCase):
    def test_seed_demo_fills_an_empty_database_and_refuses_real_data(self):
        call_command('seed_demo', owner_password='OwnerPassword123!', cashier_password='CashierPassword123!', stdout=mock.MagicMock())
        self.assertEqual(StoreSettings.current().name, 'Abarrotes La Esquina')
        closed = Shift.objects.get(closed_at__isnull=False)
        self.assertEqual(closed.difference, Decimal('-8.00'))
        self.assertTrue(Shift.objects.filter(closed_at__isnull=True, cashier__username='lupita').exists())
        self.assertEqual(Product.objects.get(barcode='0000000000055').unit, 'kg')
        with self.assertRaises(Exception):
            call_command('seed_demo', owner_password='x', cashier_password='y', stdout=mock.MagicMock())
