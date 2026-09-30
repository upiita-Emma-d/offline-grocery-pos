import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce

# Stored values are English; the second element of each choice is the Spanish label shown in the UI.
UNIT_CHOICES = [('piece', 'pieza'), ('kg', 'kg (a granel)'), ('liter', 'litro'), ('pack', 'paquete')]
UNIT_SHORT_LABELS = {'piece': 'pieza', 'kg': 'kg', 'liter': 'litro', 'pack': 'paquete'}


class ProductQuerySet(models.QuerySet):
    def matching(self, term):
        """Every word must appear in the name, SKU or barcode: «coca 600» finds «Coca-Cola 600 ml»."""
        for word in term.split()[:6]:
            self = self.filter(Q(name__icontains=word) | Q(sku__icontains=word) | Q(barcode__icontains=word))
        return self

    def with_stock(self):
        return self.annotate(computed_stock=Coalesce(Sum('movements__quantity'), Decimal('0'), output_field=models.DecimalField(max_digits=12, decimal_places=3)))


class Product(models.Model):
    objects = ProductQuerySet.as_manager()
    sku = models.CharField(max_length=40, unique=True)
    barcode = models.CharField(max_length=80, unique=True, null=True, blank=True)
    name = models.CharField(max_length=160)
    unit = models.CharField(max_length=24, choices=UNIT_CHOICES, default='piece')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    min_stock = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    active = models.BooleanField(default=True)
    photo = models.FileField(upload_to='products/', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.sku} · {self.name}'

    @property
    def stock(self):
        """Stock is always derived from movements; no screen edits it directly."""
        if hasattr(self, 'computed_stock'):
            return self.computed_stock
        return self.movements.aggregate(total=Sum('quantity'))['total'] or Decimal('0')

    @property
    def is_bulk(self):
        """Bulk products are priced per kilogram and sold by grams or amount (ADR-003)."""
        return self.unit == 'kg'

    @property
    def unit_label(self):
        return UNIT_SHORT_LABELS.get(self.unit, self.unit)


class PriceChange(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='price_changes')
    old_price = models.DecimalField(max_digits=10, decimal_places=2)
    new_price = models.DecimalField(max_digits=10, decimal_places=2)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class ProductStatusChange(models.Model):
    ACTIONS = [('deactivate', 'Baja'), ('reactivate', 'Reactivación')]
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='status_changes')
    action = models.CharField(max_length=20, choices=ACTIONS)
    reason = models.CharField(max_length=200)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class Shift(models.Model):
    register = models.CharField(max_length=30, default='MAIN')
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    opening_float = models.DecimalField(max_digits=12, decimal_places=2)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    opening_count = models.JSONField(default=dict, blank=True)
    closing_count = models.JSONField(default=dict, blank=True)
    counted_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    expected_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    difference = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['register'], condition=Q(closed_at__isnull=True), name='one_open_shift_per_register')]


class Customer(models.Model):
    """A store-credit (fiado) customer. Only a name or nickname and an optional phone are kept."""
    name = models.CharField(max_length=120, unique=True)
    phone = models.CharField(max_length=20, blank=True)
    credit_limit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Sale(models.Model):
    CASH = 'cash'
    CREDIT = 'credit'
    PAYMENT_CHOICES = [(CASH, 'Efectivo'), ('card', 'Tarjeta'), ('transfer', 'Transferencia'), (CREDIT, 'Fiado')]
    request_id = models.UUIDField(default=uuid.uuid4, unique=True)
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name='sales')
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    payment = models.CharField(max_length=20, choices=PAYMENT_CHOICES)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, null=True, blank=True, related_name='sales')
    total = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)


class SaleLine(models.Model):
    """Snapshot of sku, name, price and cost so later catalog changes never alter a ticket or its margin."""
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='lines')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    sku = models.CharField(max_length=40)
    name = models.CharField(max_length=160)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)


class GoodsReceipt(models.Model):
    request_id = models.UUIDField(default=uuid.uuid4, unique=True)
    supplier = models.CharField(max_length=120)
    document = models.CharField(max_length=80, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Recepción {self.id} · {self.supplier}'


class SaleReturn(models.Model):
    request_id = models.UUIDField(unique=True)
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='returns')
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, null=True, blank=True, related_name='returns')
    method = models.CharField(max_length=20, choices=Sale.PAYMENT_CHOICES)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=200)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='returns_recorded')
    authorized_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='returns_authorized')
    created_at = models.DateTimeField(auto_now_add=True)


class ReturnLine(models.Model):
    sale_return = models.ForeignKey(SaleReturn, on_delete=models.PROTECT, related_name='lines')
    sale_line = models.ForeignKey(SaleLine, on_delete=models.PROTECT, related_name='return_lines')
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    restock = models.BooleanField(default=True)


class StockMovement(models.Model):
    KINDS = [('receipt', 'Entrada'), ('sale', 'Venta'), ('adjustment', 'Ajuste'), ('return', 'Devolución')]
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='movements')
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    kind = models.CharField(max_length=20, choices=KINDS)
    reason = models.CharField(max_length=200)
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, null=True, blank=True)
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.PROTECT, null=True, blank=True, related_name='movements')
    sale_return = models.ForeignKey(SaleReturn, on_delete=models.PROTECT, null=True, blank=True, related_name='movements')
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class StockCount(models.Model):
    """A physical count records the difference; it never changes stock until an owner adjusts it."""
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    expected = models.DecimalField(max_digits=12, decimal_places=3)
    counted = models.DecimalField(max_digits=12, decimal_places=3)
    difference = models.DecimalField(max_digits=12, decimal_places=3)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    adjustment = models.OneToOneField(StockMovement, on_delete=models.PROTECT, null=True, blank=True)


class PrintAttempt(models.Model):
    DOCUMENTS = [('sale', 'Ticket de venta'), ('shift_open', 'Apertura de turno'), ('shift_close', 'Corte de turno'), ('test', 'Prueba')]
    RESULTS = [('ok', 'Correcto'), ('failed', 'Falló'), ('manual', 'Navegador')]
    document = models.CharField(max_length=20, choices=DOCUMENTS, default='sale')
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='print_attempts', null=True, blank=True)
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name='print_attempts', null=True, blank=True)
    result = models.CharField(max_length=20, choices=RESULTS)
    detail = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class CashOut(models.Model):
    KINDS = [('supplier_payment', 'Pago a proveedor'), ('expense', 'Gasto'), ('drop', 'Retiro parcial')]
    request_id = models.UUIDField(unique=True)
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name='cash_outs')
    kind = models.CharField(max_length=20, choices=KINDS)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    concept = models.CharField(max_length=200)
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.PROTECT, null=True, blank=True, related_name='payments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class CreditPayment(models.Model):
    PAYMENT_CHOICES = [('cash', 'Efectivo'), ('transfer', 'Transferencia')]
    request_id = models.UUIDField(unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='payments')
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name='credit_payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment = models.CharField(max_length=20, choices=PAYMENT_CHOICES)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class RemovedLine(models.Model):
    """Items removed or reduced before charging: a loss-prevention signal, never a block."""
    REASONS = [('removed', 'Quitado'), ('reduced', 'Cantidad reducida'), ('cleared', 'Venta vaciada')]
    request_id = models.UUIDField(unique=True)
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name='removed_lines')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=20, choices=REASONS)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class StoreSettings(models.Model):
    """Store name, header and footer printed on tickets and shift reports; a single row (pk=1)."""
    name = models.CharField(max_length=60, default='Tienda')
    header = models.TextField(blank=True, help_text='Dirección, teléfono u horario; una idea por renglón.')
    footer = models.TextField(blank=True, default='¡Gracias por su compra!', help_text='Mensaje al final del ticket; una idea por renglón.')
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def current(cls):
        return cls.objects.get_or_create(pk=1)[0]

    def header_lines(self):
        return [line.strip() for line in self.header.splitlines() if line.strip()]

    def footer_lines(self):
        return [line.strip() for line in self.footer.splitlines() if line.strip()]
