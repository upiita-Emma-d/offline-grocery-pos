"""Domain operations. Every money or stock change goes through here, inside a transaction, with an
idempotency key. User-facing error messages are Spanish because they are shown in the UI."""
import os
import socket
import unicodedata
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.utils import timezone

from .models import CashOut, CreditPayment, Customer, GoodsReceipt, PrintAttempt, Product, RemovedLine, ReturnLine, Sale, SaleLine, SaleReturn, Shift, StockCount, StockMovement, StoreSettings

CENT = Decimal('0.01')


class OperationError(ValueError):
    pass


def positive_quantity(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise OperationError('La cantidad no es válida.')
    if not number.is_finite() or number <= 0 or number.as_tuple().exponent < -3:
        raise OperationError('La cantidad debe ser positiva y tener hasta tres decimales.')
    return number


def money_amount(value, *, label='El importe', allow_zero=False):
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, TypeError):
        raise OperationError(f'{label} no es válido.')
    if not number.is_finite() or number < 0 or (number == 0 and not allow_zero) or number.as_tuple().exponent < -2 or number > Decimal('9999999'):
        raise OperationError(f'{label} debe ser positivo y tener hasta dos decimales.')
    return number


def parse_request_id(request_id, label):
    try:
        return uuid.UUID(str(request_id))
    except (ValueError, TypeError):
        raise OperationError(f'La solicitud de {label} no es válida.')


def sum_items(items, maximum):
    """Validate [{product_id, quantity}] and merge repeated lines of the same product."""
    if not isinstance(items, list) or not items or len(items) > maximum:
        raise OperationError(f'Debe haber entre 1 y {maximum} renglones.')
    quantities = {}
    for item in items:
        try:
            product_id = int(item['product_id'])
            quantity = positive_quantity(item['quantity'])
        except (KeyError, TypeError, ValueError):
            raise OperationError('Hay un renglón inválido.')
        quantities[product_id] = quantities.get(product_id, Decimal('0')) + quantity
    products = {p.id: p for p in Product.objects.filter(id__in=quantities, active=True)}
    if len(products) != len(quantities):
        raise OperationError('Un producto ya no está disponible.')
    return [(products[product_id], quantity) for product_id, quantity in quantities.items()]


def find_previous(model, key, user):
    previous = model.objects.filter(request_id=key).first()
    if previous is None:
        return None
    author_id = previous.cashier_id if model is Sale else previous.user_id
    if author_id != user.id:
        raise OperationError('La solicitud ya pertenece a otra cuenta.')
    return previous


def idempotent(model, request_id, label, user, operation):
    """Run the operation once per key; a retry returns (previous record, False)."""
    key = parse_request_id(request_id, label)
    previous = find_previous(model, key, user)
    if previous:
        return previous, False
    try:
        return operation(key), True
    except IntegrityError:
        # Two simultaneous submissions with the same key: the second one returns the first record.
        previous = find_previous(model, key, user)
        if previous is None:
            raise
        return previous, False


def open_shift(user=None, *, operate=False):
    shift = Shift.objects.filter(closed_at__isnull=True).first()
    if operate and (not shift or (shift.cashier_id != user.id and not user.is_superuser)):
        raise OperationError('Abre tu turno antes de registrar movimientos de caja.')
    return shift


def customer_balance(customer):
    charges = Sale.objects.filter(customer=customer, payment=Sale.CREDIT).aggregate(t=Sum('total'))['t'] or Decimal('0')
    returned = SaleReturn.objects.filter(sale__customer=customer, method=Sale.CREDIT).aggregate(t=Sum('total'))['t'] or Decimal('0')
    paid = customer.payments.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    return (charges - returned - paid).quantize(CENT)


def record_sale(*, user, request_id, items, payment, customer_id=None):
    return idempotent(Sale, request_id, 'venta', user, lambda key: _record_sale(user=user, key=key, items=items, payment=payment, customer_id=customer_id))


@transaction.atomic
def _record_sale(*, user, key, items, payment, customer_id):
    if payment not in dict(Sale.PAYMENT_CHOICES):
        raise OperationError('Forma de pago no válida.')
    shift = Shift.objects.filter(closed_at__isnull=True).first()
    if not shift or (shift.cashier_id != user.id and not user.is_superuser):
        raise OperationError('Abre tu turno antes de cobrar.')
    customer = None
    if payment == Sale.CREDIT:
        customer = Customer.objects.select_for_update().filter(pk=customer_id if str(customer_id or '').isdigit() else None, active=True).first()
        if customer is None:
            raise OperationError('Elige un cliente de fiado registrado.')
    lines = []
    total = Decimal('0')
    for product, quantity in sum_items(items, 100):
        # The server prices every line; the browser never sends amounts.
        subtotal = (product.price * quantity).quantize(CENT, rounding=ROUND_HALF_UP)
        lines.append((product, quantity, subtotal))
        total += subtotal
    if customer and customer.credit_limit is not None:
        available = customer.credit_limit - customer_balance(customer)
        if total > available:
            raise OperationError(f'{customer.name} excede su límite de fiado: disponible ${max(available, Decimal("0")):.2f}.')
    sale = Sale.objects.create(request_id=key, shift=shift, cashier=user, payment=payment, customer=customer, total=total)
    for product, quantity, subtotal in lines:
        SaleLine.objects.create(sale=sale, product=product, sku=product.sku, name=product.name, quantity=quantity, unit_price=product.price, unit_cost=product.cost, subtotal=subtotal)
        StockMovement.objects.create(product=product, quantity=-quantity, kind='sale', reason=f'Venta {sale.id}', sale=sale, user=user)
    return sale


def record_receipt(*, user, request_id, supplier, document, items, cash_payment=None):
    return idempotent(GoodsReceipt, request_id, 'recepción', user, lambda key: _record_receipt(user=user, key=key, supplier=supplier, document=document, items=items, cash_payment=cash_payment))


@transaction.atomic
def _record_receipt(*, user, key, supplier, document, items, cash_payment):
    supplier = str(supplier or '').strip()[:120]
    document = str(document or '').strip()[:80]
    if not supplier:
        raise OperationError('Indica el proveedor.')
    lines = sum_items(items, 300)
    costs = {}
    for item in items:
        if str(item.get('cost') or '').strip():
            costs[int(item['product_id'])] = money_amount(item['cost'], label='El costo', allow_zero=True)
    payment = money_amount(cash_payment, label='El pago desde caja') if str(cash_payment or '').strip() else None
    shift = open_shift() if payment else None
    if payment and shift is None:
        raise OperationError('Para pagar desde caja debe haber un turno abierto.')
    receipt = GoodsReceipt.objects.create(request_id=key, supplier=supplier, document=document, user=user)
    reason = f'Recepción {receipt.id} · {supplier}' + (f' · {document}' if document else '')
    for product, quantity in lines:
        cost = costs.get(product.id)
        StockMovement.objects.create(product=product, quantity=quantity, kind='receipt', reason=reason[:200], receipt=receipt, unit_cost=cost, user=user)
        if cost is not None and cost != product.cost:
            product.cost = cost
            product.save(update_fields=['cost', 'updated_at'])
    if payment:
        CashOut.objects.create(request_id=uuid.uuid4(), shift=shift, kind='supplier_payment', amount=payment, concept=reason[:200], receipt=receipt, user=user)
    return receipt


def record_cash_out(*, user, request_id, kind, amount, concept):
    def operation(key):
        if kind not in dict(CashOut.KINDS):
            raise OperationError('Tipo de salida no válido.')
        text = str(concept or '').strip()[:200]
        if len(text) < 3:
            raise OperationError('Escribe el concepto: a quién o para qué se entregó el dinero.')
        value = money_amount(amount)
        with transaction.atomic():
            shift = open_shift(user, operate=True)
            return CashOut.objects.create(request_id=key, shift=shift, kind=kind, amount=value, concept=text, user=user)
    return idempotent(CashOut, request_id, 'salida', user, operation)


def record_credit_payment(*, user, request_id, customer, amount, payment):
    def operation(key):
        if payment not in dict(CreditPayment.PAYMENT_CHOICES):
            raise OperationError('Forma de pago no válida.')
        value = money_amount(amount)
        with transaction.atomic():
            shift = open_shift(user, operate=True)
            locked = Customer.objects.select_for_update().get(pk=customer.pk)
            balance = customer_balance(locked)
            if value > balance:
                raise OperationError(f'El abono excede la deuda de ${balance:.2f}.')
            return CreditPayment.objects.create(request_id=key, customer=locked, shift=shift, amount=value, payment=payment, user=user)
    return idempotent(CreditPayment, request_id, 'abono', user, operation)


def record_removed_line(*, user, request_id, product_id, quantity, reason):
    def operation(key):
        if reason not in dict(RemovedLine.REASONS):
            raise OperationError('Motivo no válido.')
        shift = open_shift()
        product = Product.objects.filter(pk=product_id).first() if str(product_id).isdigit() else None
        if shift is None or product is None:
            raise OperationError('No hay turno abierto o el producto no existe.')
        return RemovedLine.objects.create(request_id=key, shift=shift, product=product, quantity=positive_quantity(quantity), unit_price=product.price, reason=reason, user=user)
    return idempotent(RemovedLine, request_id, 'renglón', user, operation)


def returned_by_line(sale):
    rows = ReturnLine.objects.filter(sale_line__sale=sale).values('sale_line').annotate(quantity=Sum('quantity'), subtotal=Sum('subtotal'))
    return {row['sale_line']: (row['quantity'], row['subtotal']) for row in rows}


def record_return(*, user, authorizer, request_id, sale_id, lines, reason):
    """lines: {sale_line_id: {'quantity': ..., 'restock': bool}}. The authorizer must be an owner."""
    def operation(key):
        if authorizer is None or not authorizer.is_superuser:
            raise OperationError('La devolución requiere autorización del propietario.')
        text = str(reason or '').strip()[:200]
        if len(text) < 4:
            raise OperationError('Escribe el motivo de la devolución.')
        with transaction.atomic():
            sale = Sale.objects.select_for_update().filter(pk=sale_id).first()
            if sale is None:
                raise OperationError('La venta no existe.')
            sale_lines = {line.id: line for line in sale.lines.select_related('product')}
            previous = returned_by_line(sale)
            requested = []
            for line_id, data in (lines or {}).items():
                line = sale_lines.get(int(line_id)) if str(line_id).isdigit() else None
                if line is None:
                    raise OperationError('Un renglón no pertenece a la venta.')
                if not str(data.get('quantity') or '').strip():
                    continue
                quantity = positive_quantity(data['quantity'])
                done_quantity, done_subtotal = previous.get(line.id, (Decimal('0'), Decimal('0')))
                remaining = line.quantity - done_quantity
                if quantity > remaining:
                    raise OperationError(f'De {line.name} solo quedan {remaining.normalize()} por devolver.')
                # Returning everything that is left refunds exactly what was charged, without rounding drift.
                subtotal = line.subtotal - done_subtotal if quantity == remaining else (line.unit_price * quantity).quantize(CENT, rounding=ROUND_HALF_UP)
                restock = bool(data.get('restock'))
                if restock and not line.product.active:
                    raise OperationError(f'{line.name} está dado de baja: márcalo como merma o reactívalo.')
                requested.append((line, quantity, subtotal, restock))
            if not requested:
                raise OperationError('Indica al menos una cantidad a devolver.')
            shift = open_shift()
            if sale.payment == Sale.CASH and shift is None:
                raise OperationError('Para devolver efectivo debe haber un turno abierto.')
            total = sum(subtotal for _, _, subtotal, _ in requested)
            sale_return = SaleReturn.objects.create(request_id=key, sale=sale, shift=shift, method=sale.payment, total=total, reason=text, user=user, authorized_by=authorizer)
            for line, quantity, subtotal, restock in requested:
                ReturnLine.objects.create(sale_return=sale_return, sale_line=line, quantity=quantity, subtotal=subtotal, restock=restock)
                if restock:
                    StockMovement.objects.create(product=line.product, quantity=quantity, kind='return', reason=f'Devolución {sale_return.id} de venta {sale.id}', sale_return=sale_return, user=user)
            return sale_return
    return idempotent(SaleReturn, request_id, 'devolución', user, operation)


@transaction.atomic
def record_count(*, user, product, counted):
    try:
        counted = Decimal(str(counted))
    except (InvalidOperation, TypeError):
        raise OperationError('Conteo inválido.')
    if not counted.is_finite() or counted < 0 or counted.as_tuple().exponent < -3:
        raise OperationError('Conteo inválido.')
    product = Product.objects.select_for_update().get(pk=product.pk)
    if not product.active:
        raise OperationError('Reactiva el producto antes de registrar movimientos.')
    expected = product.stock
    return StockCount.objects.create(product=product, expected=expected, counted=counted, difference=counted - expected, user=user)


@transaction.atomic
def adjust_count(*, user, count_id):
    count = StockCount.objects.select_for_update().select_related('product').filter(pk=count_id).first()
    if count is None or count.adjustment_id:
        raise OperationError('El conteo no existe o ya fue ajustado.')
    if not count.product.active:
        raise OperationError('Reactiva el producto antes de registrar movimientos.')
    if StockCount.objects.filter(product=count.product, id__gt=count.id).exists():
        raise OperationError('Hay un conteo más reciente de este producto; ajusta ese.')
    if not count.difference:
        raise OperationError('El conteo no tiene diferencia que ajustar.')
    # Apply the difference observed when counting: sales made afterwards are already in the balance.
    movement = StockMovement.objects.create(product=count.product, quantity=count.difference, kind='adjustment', reason=f'Ajuste autorizado por conteo {count.id}', user=user)
    count.adjustment = movement
    count.save(update_fields=['adjustment'])
    return movement


# Mexican peso denominations: (key, Spanish label, value).
DENOMINATIONS = [
    ('b1000', 'Billete $1000', Decimal('1000')), ('b500', 'Billete $500', Decimal('500')), ('b200', 'Billete $200', Decimal('200')),
    ('b100', 'Billete $100', Decimal('100')), ('b50', 'Billete $50', Decimal('50')), ('b20', 'Billete $20', Decimal('20')),
    ('c20', 'Moneda $20', Decimal('20')), ('c10', 'Moneda $10', Decimal('10')), ('c5', 'Moneda $5', Decimal('5')),
    ('c2', 'Moneda $2', Decimal('2')), ('c1', 'Moneda $1', Decimal('1')), ('c050', 'Moneda 50¢', Decimal('0.50')),
]


def parse_cash_count(data, amount):
    """Return (count, total). With pieces per denomination the server computes the total; otherwise it uses the typed amount."""
    count = {}
    for key, _, _ in DENOMINATIONS:
        value = str(data.get(f'd_{key}', '') or '').strip()
        if not value:
            continue
        if not value.isdigit() or int(value) > 100000:
            raise OperationError('Las piezas por denominación deben ser números enteros.')
        if int(value):
            count[key] = int(value)
    if count:
        return count, sum(value * count.get(key, 0) for key, _, value in DENOMINATIONS)
    return {}, money_amount(amount, label='El efectivo', allow_zero=True)


def cash_count_detail(count):
    return [(label, count[key], value * count[key]) for key, label, value in DENOMINATIONS if count.get(key)]


def shift_summary(shift):
    """The single source of expected cash, used by both the closing and the shift report."""
    sales = {r['payment']: (r['n'], r['t']) for r in shift.sales.values('payment').annotate(n=Count('id'), t=Sum('total'))}
    returns = {r['method']: (r['n'], r['t']) for r in shift.returns.values('method').annotate(n=Count('id'), t=Sum('total'))}
    cash_outs = {r['kind']: (r['n'], r['t']) for r in shift.cash_outs.values('kind').annotate(n=Count('id'), t=Sum('amount'))}
    payments = {r['payment']: (r['n'], r['t']) for r in shift.credit_payments.values('payment').annotate(n=Count('id'), t=Sum('amount'))}
    removed = shift.removed_lines.aggregate(n=Count('id'))['n']
    zero = Decimal('0')
    cash_sales = sales.get(Sale.CASH, (0, zero))[1]
    cash_returns = returns.get(Sale.CASH, (0, zero))[1]
    total_cash_outs = sum((t for _, t in cash_outs.values()), zero)
    cash_payments = payments.get('cash', (0, zero))[1]
    expected = shift.opening_float + cash_sales - cash_returns - total_cash_outs + cash_payments
    return {
        'sales': [(label, *sales[key]) for key, label in Sale.PAYMENT_CHOICES if key in sales],
        'returns': [(label, *returns[key]) for key, label in Sale.PAYMENT_CHOICES if key in returns],
        'cash_outs': [(label, *cash_outs[key]) for key, label in CashOut.KINDS if key in cash_outs],
        'credit_payments': [(label, *payments[key]) for key, label in CreditPayment.PAYMENT_CHOICES if key in payments],
        'cash_sales': cash_sales, 'cash_returns': cash_returns, 'total_cash_outs': total_cash_outs,
        'cash_payments': cash_payments, 'expected': expected, 'removed': removed,
        'total_sales': sum((t for _, t in sales.values()), zero), 'sale_count': sum(n for n, _ in sales.values()),
    }


@transaction.atomic
def close_shift(*, shift, counted_cash, cash_count=None):
    shift = Shift.objects.select_for_update().get(pk=shift.pk)
    if shift.closed_at:
        raise OperationError('El turno ya está cerrado.')
    shift.expected_cash = shift_summary(shift)['expected']
    shift.counted_cash = counted_cash
    shift.closing_count = cash_count or {}
    shift.difference = counted_cash - shift.expected_cash
    shift.closed_at = timezone.now()
    shift.save(update_fields=['expected_cash', 'counted_cash', 'closing_count', 'difference', 'closed_at'])
    return shift


# --- ESC/POS printing (Epson TM thermal printers over TCP port 9100) ---
# The cut uses GS V 66 (feed to the cutter, then cut). GS V 1 cuts at the print head and leaves the
# last lines inside a TM-T88V, at the top of the next ticket.
ESC_INIT = b'\x1b@'
ESC_CENTER, ESC_LEFT = b'\x1ba\x01', b'\x1ba\x00'
ESC_BOLD, ESC_NORMAL = b'\x1bE\x01', b'\x1bE\x00'
ESC_DOUBLE, ESC_SINGLE = b'\x1d!\x11', b'\x1d!\x00'
ESC_TALL = b'\x1d!\x01'
ESC_CUT = b'\n\x1dVB\x03'
ESC_CODEPAGE_1252 = b'\x1bt\x10'  # ESC t 16: Windows-1252 (accents and ñ) on the TM-T88V


def printer_settings():
    """(host, port, columns, accents) from the environment; an empty host means no network printer."""
    host = os.environ.get('POS_PRINTER_HOST', '').strip()
    try:
        port = int(os.environ.get('POS_PRINTER_PORT', '9100'))
        columns = int(os.environ.get('POS_PRINTER_COLUMNS', '32'))
    except ValueError:
        raise OperationError('Puerto o columnas de la impresora inválidos.')
    if not 1 <= port <= 65535 or not 24 <= columns <= 64:
        raise OperationError('Puerto o columnas de la impresora inválidos.')
    return host, port, columns, os.environ.get('POS_PRINTER_ACCENTS', '0') == '1'


def network_printer_configured():
    return bool(os.environ.get('POS_PRINTER_HOST', '').strip())


def printer_text(value, accents=False):
    text = str(value).replace('¢', 'c')
    if accents:
        return text.encode('cp1252', errors='replace')
    # Without a confirmed code page, send ASCII: «Recepción» prints as «Recepcion».
    normalized = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in normalized if not unicodedata.combining(c)).encode('ascii', errors='replace')


def two_columns(left, right, columns):
    left = str(left)[:max(columns - len(str(right)) - 1, 1)]
    return left + ' ' * max(columns - len(left) - len(str(right)), 1) + str(right)


def wrap(text, columns):
    words, lines, current = str(text).split(), [], ''
    for word in words:
        if current and len(current) + 1 + len(word) > columns:
            lines.append(current)
            current = word[:columns]
        else:
            current = f'{current} {word}'.strip()[:columns]
    return lines + ([current] if current else [])


def money_text(value):
    return f'${Decimal(value or 0).quantize(CENT):,.2f}'


def escpos_document(subtitle, body, columns, accents=False, footer=True):
    """Store header, subtitle, body and footer. A body tuple (text, style) uses style 'bold', 'center' or 'tall'."""
    store = StoreSettings.current()
    encode = lambda value: printer_text(value, accents)
    data = ESC_INIT + (ESC_CODEPAGE_1252 if accents else b'') + ESC_CENTER
    for line in wrap(store.name, columns // 2):
        data += ESC_DOUBLE + ESC_BOLD + encode(line) + b'\n' + ESC_SINGLE + ESC_NORMAL
    for header_line in store.header_lines():
        for line in wrap(header_line, columns):
            data += encode(line) + b'\n'
    data += ESC_BOLD + encode(subtitle) + b'\n' + ESC_NORMAL + ESC_LEFT
    for entry in body:
        text, style = entry if isinstance(entry, tuple) else (entry, None)
        if style == 'bold':
            data += ESC_BOLD + encode(text) + b'\n' + ESC_NORMAL
        elif style == 'center':
            data += ESC_CENTER + encode(text) + b'\n' + ESC_LEFT
        elif style == 'tall':
            data += ESC_TALL + ESC_BOLD + encode(text) + b'\n' + ESC_NORMAL + ESC_SINGLE
        else:
            data += encode(text) + b'\n'
    if footer and store.footer_lines():
        data += b'\n' + ESC_CENTER
        for footer_line in store.footer_lines():
            for line in wrap(footer_line, columns):
                data += encode(line) + b'\n'
        data += ESC_LEFT
    return data + ESC_CUT


def send_to_printer(document, build, **relation):
    """Print after saving; a failure is only recorded and never rolls back the operation."""
    try:
        host, port, columns, accents = printer_settings()
    except OperationError as error:
        PrintAttempt.objects.create(document=document, result='failed', detail=str(error), **relation)
        return False
    if not host:
        PrintAttempt.objects.create(document=document, result='manual', detail='Sin impresora de red; usar impresión del navegador.', **relation)
        return False
    try:
        with socket.create_connection((host, port), timeout=3) as connection:
            connection.sendall(build(columns, accents))
        PrintAttempt.objects.create(document=document, result='ok', **relation)
        return True
    except OSError as error:
        PrintAttempt.objects.create(document=document, result='failed', detail=str(error)[:240], **relation)
        return False


def ticket_item_summary(lines):
    """Spanish item summary: pieces are added up, bulk products are counted as lines."""
    pieces = sum((line.quantity for line in lines if not line.product.is_bulk), Decimal('0'))
    bulk = sum(1 for line in lines if line.product.is_bulk)
    return pieces, bulk


def print_sale(sale):
    def build(width, accents):
        lines = list(sale.lines.select_related('product'))
        body = ['-' * width, two_columns(f'Folio: {sale.id}', timezone.localtime(sale.created_at).strftime('%d/%m/%Y %H:%M'), width), f'Atendió: {sale.cashier.username}', '-' * width]
        for line in lines:
            body += [line.name[:width], two_columns(f'  {line.quantity.normalize():f} x {money_text(line.unit_price)}', money_text(line.subtotal), width)]
        pieces, bulk = ticket_item_summary(lines)
        summary = f'Artículos: {pieces.normalize():f}' + (f' + {bulk} a granel' if bulk else '')
        body += ['-' * width, summary, (two_columns('TOTAL', money_text(sale.total), width), 'tall'), f'Pago: {sale.get_payment_display()}']
        if sale.customer_id:
            body += [f'Cliente: {sale.customer.name}', two_columns('Saldo pendiente', money_text(customer_balance(sale.customer)), width)]
        return escpos_document('Ticket de venta', body, width, accents)
    return send_to_printer('sale', build, sale=sale)


def print_shift_open(shift):
    def build(width, accents):
        body = ['-' * width, two_columns(f'Turno #{shift.id}', timezone.localtime(shift.opened_at).strftime('%d/%m/%Y %H:%M'), width), f'Cajera: {shift.cashier.username}', '-' * width]
        for label, pieces, amount in cash_count_detail(shift.opening_count):
            body.append(two_columns(f'{label} x {pieces}', money_text(amount), width))
        body += ['-' * width, (two_columns('FONDO INICIAL', money_text(shift.opening_float), width), 'bold'), '', '', 'Entrega: ____________________', '', 'Recibe:  ____________________']
        return escpos_document('Apertura de turno', body, width, accents, footer=False)
    return send_to_printer('shift_open', build, shift=shift)


def print_shift_close(shift):
    summary = shift_summary(shift)

    def build(width, accents):
        body = ['-' * width, f'Turno #{shift.id} · {shift.cashier.username}', f'{timezone.localtime(shift.opened_at):%d/%m %H:%M} a {timezone.localtime(shift.closed_at):%d/%m %H:%M}', '-' * width, (f'VENTAS ({summary["sale_count"]})', 'bold')]
        body += [two_columns(f'{label} ({n})', money_text(t), width) for label, n, t in summary['sales']]
        body.append(two_columns('Total vendido', money_text(summary['total_sales']), width))
        for title, rows, sign in [('DEVOLUCIONES', summary['returns'], '-'), ('SALIDAS', summary['cash_outs'], '-'), ('ABONOS FIADO', summary['credit_payments'], '')]:
            if rows:
                body.append((title, 'bold'))
                body += [two_columns(f'{label} ({n})', sign + money_text(t), width) for label, n, t in rows]
        body += ['-' * width, ('EFECTIVO', 'bold'),
                 two_columns('Fondo inicial', money_text(shift.opening_float), width),
                 two_columns('+ Ventas efectivo', money_text(summary['cash_sales']), width),
                 two_columns('- Devoluciones', money_text(summary['cash_returns']), width),
                 two_columns('- Salidas', money_text(summary['total_cash_outs']), width),
                 two_columns('+ Abonos efectivo', money_text(summary['cash_payments']), width),
                 (two_columns('ESPERADO', money_text(shift.expected_cash), width), 'bold'),
                 (two_columns('CONTADO', money_text(shift.counted_cash), width), 'bold'),
                 (two_columns('DIFERENCIA', money_text(shift.difference), width), 'bold')]
        closing = cash_count_detail(shift.closing_count)
        if closing:
            body += ['-' * width, ('ARQUEO DE CIERRE', 'bold')] + [two_columns(f'{label} x {pieces}', money_text(amount), width) for label, pieces, amount in closing]
        body += ['-' * width, f'Renglones quitados: {summary["removed"]}', '', '', 'Entrega: ____________________', '', 'Recibe:  ____________________']
        return escpos_document('Corte de turno', body, width, accents, footer=False)
    return send_to_printer('shift_close', build, shift=shift)


def print_test():
    def build(width, accents):
        digits = '1234567890' * (width // 10) + '1234567890'[:width % 10]
        body = [f'Columnas configuradas: {width}', digits, two_columns('Izquierda', 'Derecha', width), ('Negrita', 'bold'), ('Centrado', 'center'), ('TOTAL $94.50', 'tall'), 'Acentos: áéíóú ñ Ñ ¡¿', timezone.localtime().strftime('%d/%m/%Y %H:%M')]
        return escpos_document('Hoja de prueba', body, width, accents)
    return send_to_printer('test', build)
