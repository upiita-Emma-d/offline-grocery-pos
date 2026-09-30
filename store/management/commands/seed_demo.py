import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from store.models import Customer, Product, Sale, Shift, StoreSettings
from store.services import close_shift, parse_cash_count, record_cash_out, record_credit_payment, record_receipt, record_return, record_sale

# Fictitious barcodes (they start with 0000 so they can never match a real product).
DEMO_BARCODES = {'COCA600': '0000000000017', 'SABRI45': '0000000000024', 'LALA1L': '0000000000031', 'GANSITO': '0000000000048', 'QUESOPAN': '0000000000055'}


class Command(BaseCommand):
    help = 'Fill an EMPTY database with a fictitious store for demos and screenshots (never run it on real data).'

    def add_arguments(self, parser):
        parser.add_argument('--owner-password', required=True)
        parser.add_argument('--cashier-password', required=True)

    def handle(self, *args, **options):
        if Sale.objects.exists() or Shift.objects.exists():
            raise CommandError('The database already has sales or shifts. seed_demo only runs on an empty database.')
        users = get_user_model().objects
        owner = users.filter(username='admin').first() or users.create_superuser('admin', password=options['owner_password'])
        cashier = users.filter(username='lupita').first() or users.create_user('lupita', password=options['cashier_password'])
        call_command('seed_catalog', with_stock='admin', stdout=self.stdout)
        with transaction.atomic():
            settings = StoreSettings.current()
            settings.name = 'Abarrotes La Esquina'
            settings.header = 'Av. Ejemplo 123, Col. Centro\nTel. 55 0000 0000'
            settings.footer = '¡Gracias por su compra!\nVuelva pronto'
            settings.save()
            for sku, code in DEMO_BARCODES.items():
                Product.objects.filter(sku=sku).update(barcode=code)
            products = {p.sku: p for p in Product.objects.all()}
            for product in products.values():
                # Fictitious cost around 78% of the price, so the report can show a margin.
                product.cost = (product.price * Decimal('0.78')).quantize(Decimal('0.01'))
                product.save(update_fields=['cost'])
            mari = Customer.objects.create(name='Doña Mari', phone='', credit_limit=500)
            Customer.objects.create(name='Don Pepe', credit_limit=300)

            def sell(payment, lines, customer=None):
                items = [{'product_id': products[sku].id, 'quantity': qty} for sku, qty in lines]
                return record_sale(user=cashier, request_id=uuid.uuid4(), items=items, payment=payment, customer_id=customer.id if customer else None)[0]

            # A finished morning shift, so the shift report and daily report have content.
            count, amount = parse_cash_count({'d_b500': '3', 'd_b100': '1', 'd_b50': '2'}, '')
            morning = Shift.objects.create(cashier=cashier, opening_float=amount, opening_count=count)
            first = sell('cash', [('COCA600', '3'), ('QUESOPAN', '0.4'), ('BIMBOG', '1')])
            sell('card', [('LALA1L', '2'), ('HUEVO12', '1'), ('ATUNDOL', '2')])
            sell('cash', [('MARUCH', '3'), ('SABRI45', '2'), ('GANSITO', '2')])
            sell('credit', [('LALA1L', '2'), ('BIMBOG', '1')], customer=mari)
            sell('transfer', [('NESCAF120', '1'), ('AZUCAR1K', '2')])
            record_receipt(user=owner, request_id=uuid.uuid4(), supplier='Bimbo (ruta)', document='Nota 889', items=[{'product_id': products['BIMBOG'].id, 'quantity': 6, 'cost': '44.00'}], cash_payment='264')
            record_cash_out(user=cashier, request_id=uuid.uuid4(), kind='supplier_payment', amount='180', concept='Repartidor Sabritas, nota 311')
            coke_line = first.lines.get(product=products['COCA600'])
            record_return(user=cashier, authorizer=owner, request_id=uuid.uuid4(), sale_id=first.id, lines={str(coke_line.id): {'quantity': '1', 'restock': False}}, reason='Lata abollada')
            record_credit_payment(user=cashier, request_id=uuid.uuid4(), customer=mari, amount='50', payment='cash')
            # $8 short on purpose, so the shift report shows how a difference looks.
            counted, total = parse_cash_count({'d_b500': '2', 'd_b200': '2', 'd_b100': '1', 'd_b50': '1', 'd_b20': '2'}, '')
            close_shift(shift=morning, counted_cash=total, cash_count=counted)
            # The afternoon shift stays open so the checkout screen works right away.
            count, amount = parse_cash_count({'d_b200': '5', 'd_b100': '3', 'd_c10': '10'}, '')
            Shift.objects.create(cashier=cashier, opening_float=amount, opening_count=count)
        self.stdout.write(self.style.SUCCESS('Demo store ready. Owner: admin · Cashier: lupita (passwords as given).'))
