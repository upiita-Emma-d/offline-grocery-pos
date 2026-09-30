import json
import uuid
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Max, Sum
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.decorators.http import require_GET, require_POST

from .forms import CustomerForm, ProductForm, StoreSettingsForm
from .models import CashOut, Customer, GoodsReceipt, PriceChange, Product, ProductStatusChange, RemovedLine, Sale, SaleLine, SaleReturn, Shift, StockCount, StockMovement, StoreSettings
from .services import (
    DENOMINATIONS, OperationError, adjust_count, cash_count_detail, close_shift, customer_balance, network_printer_configured,
    parse_cash_count, print_sale, print_shift_close, print_shift_open, record_cash_out, record_count, record_credit_payment,
    record_receipt, record_removed_line, record_return, record_sale, returned_by_line, shift_summary, ticket_item_summary,
)


def is_owner(request):
    return request.user.is_superuser


def owner_only_json(request):
    if not is_owner(request):
        return JsonResponse({'error': 'Solo el propietario puede hacer esto.'}, status=403)
    return None


def read_json(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise OperationError('Solicitud inválida.')
    if not isinstance(data, dict):
        raise OperationError('Solicitud inválida.')
    return data


def product_json(product):
    return {'id': product.id, 'sku': product.sku, 'barcode': product.barcode or '', 'name': product.name, 'price': str(product.price),
            'unit': product.unit, 'unit_label': product.unit_label, 'is_bulk': product.is_bulk, 'stock': str(product.stock)}


def current_shift():
    return Shift.objects.filter(closed_at__isnull=True).select_related('cashier').first()


def can_see_shift(request, shift):
    return shift.cashier_id == request.user.id or is_owner(request)


@login_required
def home(request):
    active = list(Product.objects.filter(active=True).with_stock())
    negative = [p for p in active if p.stock < 0]
    low = [p for p in active if 0 <= p.stock <= p.min_stock][:8]
    recent = Sale.objects.select_related('cashier').order_by('-id')[:8]
    return render(request, 'store/home.html', {'shift': current_shift(), 'recent': recent, 'low': low, 'negative': negative})


@login_required
def checkout(request):
    customers = [(c, customer_balance(c)) for c in Customer.objects.filter(active=True)]
    return render(request, 'store/checkout.html', {'shift': current_shift(), 'request_id': uuid.uuid4(), 'customers': customers})


@login_required
@require_GET
def product_search(request):
    term = request.GET.get('q', '').strip()[:80]
    if not term:
        return JsonResponse({'products': []})
    products = Product.objects.filter(active=True).matching(term)
    if request.GET.get('without_barcode') == '1':
        products = products.filter(barcode__isnull=True)
    return JsonResponse({'products': [product_json(p) for p in products.with_stock()[:20]]})


@login_required
@require_GET
def barcode_lookup(request):
    """Exact match only: a barcode, or a SKU ignoring case. Never a "similar" product."""
    code = request.GET.get('code', '').strip()[:80]
    if not code:
        return JsonResponse({'error': 'Escribe o escanea un código.'}, status=400)
    product = Product.objects.filter(active=True, barcode=code).with_stock().first()
    if product is None:
        product = Product.objects.filter(active=True, sku__iexact=code).with_stock().first()
    if product is None:
        return JsonResponse({'error': f'Código {code} no registrado.'}, status=404)
    return JsonResponse({'product': product_json(product)})


@login_required
@require_POST
def charge(request):
    try:
        data = read_json(request)
        sale, created = record_sale(user=request.user, request_id=data.get('request_id'), items=data.get('items'), payment=data.get('payment'), customer_id=data.get('customer_id'))
    except OperationError as error:
        return JsonResponse({'error': str(error)}, status=400)
    if created:
        print_sale(sale)
    return JsonResponse({'folio': sale.id, 'total': str(sale.total), 'created': created, 'ticket_url': reverse('sale_ticket', args=[sale.id])})


@login_required
def catalog(request):
    if not is_owner(request):
        return HttpResponseForbidden('Solo el propietario puede administrar el catálogo.')
    term = request.GET.get('q', '').strip()[:80]
    products = Product.objects.all()
    if term:
        products = products.matching(term)
    products = list(products.with_stock()[:100])
    # One match (typically a scanned barcode) goes straight to its price box.
    return render(request, 'store/catalog.html', {'products': products, 'term': term, 'single': term and len(products) == 1})


@login_required
def product_edit(request, product_id=None):
    if not is_owner(request):
        return HttpResponseForbidden('Solo el propietario puede editar productos.')
    product = get_object_or_404(Product, pk=product_id) if product_id else None
    old_price = product.price if product else None
    initial = {'barcode': request.GET.get('barcode', '').strip()[:80]} if product is None else None
    # "next" lets checkout send the owner here for an unknown code and get the product back (ADR-006).
    next_url = request.POST.get('next') or request.GET.get('next') or ''
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = ''
    form = ProductForm(request.POST or None, request.FILES or None, instance=product, initial=initial)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            saved = form.save()
            if old_price is not None and old_price != saved.price:
                PriceChange.objects.create(product=saved, old_price=old_price, new_price=saved.price, user=request.user)
        if old_price is not None and old_price != saved.price:
            messages.success(request, f'{saved.name} guardado. Precio: ${old_price:.2f} → ${saved.price:.2f}.')
        else:
            messages.success(request, f'{saved.name} guardado.')
        if next_url:
            code = saved.barcode or saved.sku
            return redirect(f'{next_url}?{urlencode({"scan": code})}' if next_url.startswith(reverse('checkout')) else next_url)
        if 'another' in request.POST:
            return redirect('product_new')
        return redirect(f'{reverse("catalog")}?{urlencode({"q": saved.barcode or saved.sku})}')
    status_changes = product.status_changes.select_related('user').order_by('-id')[:5] if product else []
    price_history = product.price_changes.select_related('user').order_by('-id')[:5] if product else []
    return render(request, 'store/product_form.html', {'form': form, 'product': product, 'status_changes': status_changes, 'price_history': price_history, 'next_url': next_url})


@login_required
@require_POST
def product_status(request, product_id):
    """Reversible deactivation: only with zero stock, a reason and an audit record."""
    if not is_owner(request):
        return HttpResponseForbidden('Solo el propietario puede dar de baja productos.')
    reason = request.POST.get('reason', '').strip()[:200]
    if len(reason) < 4:
        messages.error(request, 'Escribe un motivo de al menos cuatro caracteres.')
        return redirect('product_edit', product_id=product_id)
    with transaction.atomic():
        product = get_object_or_404(Product.objects.select_for_update(), pk=product_id)
        if product.active:
            if product.stock != 0:
                messages.error(request, 'No se puede dar de baja: registra o concilia primero las existencias.')
                return redirect('product_edit', product_id=product_id)
            product.active, action = False, 'deactivate'
        else:
            product.active, action = True, 'reactivate'
        product.save(update_fields=['active', 'updated_at'])
        ProductStatusChange.objects.create(product=product, action=action, reason=reason, user=request.user)
    messages.success(request, 'Producto dado de baja.' if action == 'deactivate' else 'Producto reactivado.')
    return redirect('product_edit', product_id=product_id)


@login_required
@require_POST
def product_price(request, product_id):
    if not is_owner(request):
        return HttpResponseForbidden('Solo el propietario puede cambiar precios.')
    product = get_object_or_404(Product, pk=product_id)
    term = request.POST.get('q', '').strip()[:80]
    back = f'{reverse("catalog")}?{urlencode({"q": term})}' if term else reverse('catalog')
    try:
        new_price = Decimal(request.POST.get('price', ''))
        if not new_price.is_finite() or new_price < 0 or new_price.as_tuple().exponent < -2:
            raise InvalidOperation
    except (InvalidOperation, TypeError):
        messages.error(request, 'Precio inválido.')
        return redirect(back)
    old_price = product.price
    if new_price != old_price:
        with transaction.atomic():
            PriceChange.objects.create(product=product, old_price=old_price, new_price=new_price, user=request.user)
            product.price = new_price
            product.save(update_fields=['price', 'updated_at'])
        messages.success(request, f'{product.name}: ${old_price:.2f} → ${new_price:.2f}.')
    else:
        messages.info(request, f'{product.name} ya costaba ${old_price:.2f}.')
    # Keep the search so the next price can be changed without searching again.
    return redirect(back)


@login_required
def inventory(request):
    if not is_owner(request):
        return HttpResponseForbidden('Solo el propietario puede registrar inventario.')
    if request.method == 'POST':
        term = request.POST.get('q', '').strip()[:80]
        try:
            action = request.POST.get('action')
            if action == 'count':
                product = get_object_or_404(Product, pk=request.POST.get('product_id'))
                count = record_count(user=request.user, product=product, counted=request.POST.get('quantity', ''))
                messages.success(request, f'Conteo de {product.name} registrado. Diferencia: {count.difference}. No se ajustó el saldo.')
            elif action == 'adjust':
                adjust_count(user=request.user, count_id=request.POST.get('count_id'))
                messages.success(request, 'Ajuste registrado con trazabilidad.')
                term = ''
            else:
                raise OperationError('Acción inválida.')
        except OperationError as error:
            messages.error(request, str(error))
        target = reverse('inventory')
        return redirect(f'{target}?{urlencode({"q": term})}' if term else target)
    term = request.GET.get('q', '').strip()[:80]
    found, exact = [], False
    if term:
        found = list(Product.objects.filter(active=True, barcode=term).with_stock()[:1])
        exact = bool(found)
        if not found:
            found = list(Product.objects.filter(active=True).matching(term).with_stock()[:20])
    counts = list(StockCount.objects.select_related('product', 'user').order_by('-id')[:15])
    latest = dict(StockCount.objects.filter(product__in={c.product_id for c in counts}).values_list('product').annotate(latest=Max('id')))
    for count in counts:
        count.superseded = latest.get(count.product_id) != count.id
    movements = StockMovement.objects.select_related('product', 'user').order_by('-id')[:15]
    receipts = GoodsReceipt.objects.select_related('user').annotate(line_count=Count('movements')).order_by('-id')[:8]
    return render(request, 'store/inventory.html', {'term': term, 'found': found, 'exact': exact, 'counts': counts, 'movements': movements, 'receipts': receipts})


@login_required
def receiving(request):
    if not is_owner(request):
        return HttpResponseForbidden('Solo el propietario puede recibir mercancía.')
    return render(request, 'store/receiving.html', {'request_id': uuid.uuid4()})


@login_required
def receipt_detail(request, receipt_id):
    if not is_owner(request):
        return HttpResponseForbidden('Solo el propietario puede consultar recepciones.')
    receipt = get_object_or_404(GoodsReceipt.objects.select_related('user'), pk=receipt_id)
    lines = list(receipt.movements.select_related('product').order_by('product__name'))
    for movement in lines:
        movement.amount = (movement.unit_cost * movement.quantity).quantize(Decimal('0.01')) if movement.unit_cost is not None else None
    total_cost = sum((m.amount for m in lines if m.amount is not None), Decimal('0'))
    return render(request, 'store/receipt_detail.html', {'receipt': receipt, 'lines': lines, 'total_cost': total_cost, 'payments': receipt.payments.all()})


@login_required
@require_POST
def receipt_confirm(request):
    if denied := owner_only_json(request):
        return denied
    try:
        data = read_json(request)
        receipt, created = record_receipt(user=request.user, request_id=data.get('request_id'), supplier=data.get('supplier'), document=data.get('document'), items=data.get('items'), cash_payment=data.get('cash_payment'))
    except OperationError as error:
        return JsonResponse({'error': str(error)}, status=400)
    return JsonResponse({'receipt': receipt.id, 'created': created, 'url': reverse('receipt_detail', args=[receipt.id])})


@login_required
@require_POST
def assign_barcode(request, product_id):
    """Give an unknown barcode to a product that has none; an existing barcode is never replaced here."""
    if denied := owner_only_json(request):
        return denied
    try:
        code = str(read_json(request).get('barcode', '')).strip()[:80]
        if not code:
            raise OperationError('Falta el código.')
        with transaction.atomic():
            product = get_object_or_404(Product.objects.select_for_update(), pk=product_id, active=True)
            if product.barcode:
                raise OperationError(f'{product.name} ya tiene el código {product.barcode}. Cámbialo desde su ficha si es necesario.')
            if Product.objects.filter(barcode=code).exists():
                raise OperationError(f'El código {code} ya pertenece a otro producto.')
            product.barcode = code
            product.save(update_fields=['barcode', 'updated_at'])
    except OperationError as error:
        return JsonResponse({'error': str(error)}, status=400)
    return JsonResponse({'product': product_json(product)})


@login_required
@require_POST
def quick_create(request):
    if denied := owner_only_json(request):
        return denied
    try:
        data = read_json(request)
    except OperationError as error:
        return JsonResponse({'error': str(error)}, status=400)
    code = str(data.get('barcode', '')).strip()[:80]
    sku = str(data.get('sku', '')).strip() or code
    form = ProductForm({'sku': sku, 'barcode': code, 'name': str(data.get('name', '')).strip(), 'unit': str(data.get('unit', '')).strip() or 'piece', 'price': str(data.get('price', '')).strip(), 'min_stock': '0'})
    if not form.is_valid():
        errors = [f'{form.fields[field].label}: {errs[0]}' if field in form.fields else errs[0] for field, errs in form.errors.items()]
        return JsonResponse({'error': ' '.join(errors)}, status=400)
    return JsonResponse({'product': product_json(form.save())}, status=201)


def report_printing(request, printed, document):
    if printed:
        messages.info(request, f'Se imprimió {document} en la Epson.')
    elif network_printer_configured():
        messages.warning(request, f'No se pudo imprimir {document} en la Epson; lo guardado no cambia. Reimprímelo desde el corte o el navegador.')


def denomination_fields():
    return [(f'd_{key}', label, value) for key, label, value in DENOMINATIONS]


@login_required
def shifts(request):
    shift = current_shift()
    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'open':
                if shift:
                    raise OperationError('Ya existe un turno abierto.')
                count, amount = parse_cash_count(request.POST, request.POST.get('amount', ''))
                new_shift = Shift.objects.create(cashier=request.user, opening_float=amount, opening_count=count)
                messages.success(request, f'Turno abierto con fondo de ${amount:.2f}.')
                report_printing(request, print_shift_open(new_shift), 'la apertura')
            elif action == 'close':
                if not shift or not can_see_shift(request, shift):
                    raise OperationError('No puedes cerrar este turno.')
                count, amount = parse_cash_count(request.POST, request.POST.get('amount', ''))
                closed = close_shift(shift=shift, counted_cash=amount, cash_count=count)
                messages.success(request, f'Turno cerrado. Contado ${closed.counted_cash:.2f}; esperado ${closed.expected_cash:.2f}; diferencia ${closed.difference:.2f}.')
                report_printing(request, print_shift_close(closed), 'el corte')
                return redirect('shift_report', shift_id=closed.id)
            elif action == 'cash_out':
                cash_out, created = record_cash_out(user=request.user, request_id=request.POST.get('request_id'), kind=request.POST.get('kind'), amount=request.POST.get('cash_out_amount', ''), concept=request.POST.get('concept'))
                if created:
                    messages.success(request, f'Salida registrada: {cash_out.get_kind_display()} ${cash_out.amount:.2f}.')
            else:
                raise OperationError('Acción inválida.')
        except (OperationError, IntegrityError) as error:
            messages.error(request, f'No se pudo registrar: {error}')
        return redirect('shifts')
    history = Shift.objects.select_related('cashier').order_by('-id')
    if not is_owner(request):
        history = history.filter(cashier=request.user)
    cash_outs = shift.cash_outs.select_related('user').order_by('-id') if shift else []
    can_operate = bool(shift) and can_see_shift(request, shift)
    return render(request, 'store/shifts.html', {'shift': shift, 'history': history[:20], 'cash_outs': cash_outs, 'can_operate': can_operate, 'denominations': denomination_fields(), 'cash_out_kinds': CashOut.KINDS, 'request_id': uuid.uuid4()})


@login_required
def shift_report(request, shift_id):
    shift = get_object_or_404(Shift.objects.select_related('cashier'), pk=shift_id)
    if not can_see_shift(request, shift):
        return HttpResponseForbidden('No puedes consultar este turno.')
    if not shift.closed_at:
        # Blind close: expected cash is never shown before the cash is counted.
        return HttpResponseForbidden('El corte se emite al cerrar el turno; el esperado no se muestra antes del conteo.')
    context = {
        'network_printer': network_printer_configured(), 'shift': shift, 'summary': shift_summary(shift),
        'opening_count': cash_count_detail(shift.opening_count), 'closing_count': cash_count_detail(shift.closing_count),
        'cash_outs': shift.cash_outs.select_related('user').order_by('id'),
        'returns': shift.returns.select_related('sale', 'authorized_by').order_by('id'),
        'removed': shift.removed_lines.select_related('product', 'user').order_by('id'),
    }
    return render(request, 'store/shift_report.html', context)


@login_required
@require_POST
def shift_reprint(request, shift_id, document):
    shift = get_object_or_404(Shift, pk=shift_id)
    if not can_see_shift(request, shift):
        return HttpResponseForbidden('No puedes imprimir este turno.')
    if document == 'close' and not shift.closed_at:
        return HttpResponseForbidden('El corte se emite al cerrar el turno.')
    if document == 'close':
        report_printing(request, print_shift_close(shift), 'el corte')
        return redirect('shift_report', shift_id=shift.id)
    report_printing(request, print_shift_open(shift), 'la apertura')
    return redirect('shifts')


@login_required
def sales(request):
    records = Sale.objects.select_related('cashier', 'customer').annotate(returned=Sum('returns__total')).order_by('-id')
    if not is_owner(request):
        records = records.filter(cashier=request.user)
    filters = {k: request.GET.get(k, '').strip() for k in ['from', 'to', 'shift', 'cashier', 'payment', 'folio']}
    if parse_date(filters['from']):
        records = records.filter(created_at__date__gte=parse_date(filters['from']))
    if parse_date(filters['to']):
        records = records.filter(created_at__date__lte=parse_date(filters['to']))
    if filters['shift'].isdigit():
        records = records.filter(shift_id=filters['shift'])
    if filters['cashier'].isdigit():
        records = records.filter(cashier_id=filters['cashier'])
    if filters['payment'] in dict(Sale.PAYMENT_CHOICES):
        records = records.filter(payment=filters['payment'])
    if filters['folio'].isdigit():
        records = records.filter(pk=filters['folio'])
    summary = records.aggregate(n=Count('id', distinct=True), total=Sum('total'))
    cashiers = get_user_model().objects.filter(sale__isnull=False).distinct().order_by('username') if is_owner(request) else []
    return render(request, 'store/sales.html', {'sales': records[:300], 'filters': filters, 'summary': summary, 'cashiers': cashiers, 'payments': Sale.PAYMENT_CHOICES})


@login_required
def sale_ticket(request, sale_id):
    sale = get_object_or_404(Sale.objects.select_related('cashier', 'customer'), pk=sale_id)
    if sale.cashier_id != request.user.id and not is_owner(request):
        return HttpResponseForbidden('No puedes consultar este ticket.')
    lines = list(sale.lines.select_related('product'))
    pieces, bulk = ticket_item_summary(lines)
    balance = customer_balance(sale.customer) if sale.customer_id else None
    return render(request, 'store/sale_ticket.html', {'sale': sale, 'lines': lines, 'pieces': pieces, 'bulk': bulk, 'balance': balance, 'returns': sale.returns.order_by('id'), 'network_printer': network_printer_configured()})


@login_required
@require_POST
def sale_reprint(request, sale_id):
    sale = get_object_or_404(Sale, pk=sale_id)
    if sale.cashier_id != request.user.id and not is_owner(request):
        return HttpResponseForbidden('No puedes imprimir este ticket.')
    # Reprinting uses the same folio; it never creates a second sale.
    if not network_printer_configured():
        messages.warning(request, 'No hay impresora de red configurada. Usa «Imprimir ticket»: sale por la impresora instalada en Windows.')
    elif print_sale(sale):
        messages.success(request, 'Ticket enviado a la impresora.')
    else:
        messages.warning(request, 'La impresora de red no respondió. La venta está guardada; usa «Imprimir ticket».')
    return redirect('sale_ticket', sale_id=sale.id)


@login_required
def sale_return(request, sale_id):
    sale = get_object_or_404(Sale.objects.select_related('cashier', 'customer'), pk=sale_id)
    if sale.cashier_id != request.user.id and not is_owner(request):
        return HttpResponseForbidden('No puedes devolver esta venta.')
    lines = list(sale.lines.select_related('product'))
    previous = returned_by_line(sale)
    for line in lines:
        line.remaining = line.quantity - previous.get(line.id, (Decimal('0'), Decimal('0')))[0]
    if request.method == 'POST':
        # A cashier needs the owner's credentials typed on the same screen (supervisor override).
        authorizer = request.user if is_owner(request) else authenticate(request, username=request.POST.get('owner_username', ''), password=request.POST.get('owner_password', ''))
        requested = {str(line.id): {'quantity': request.POST.get(f'quantity_{line.id}', ''), 'restock': request.POST.get(f'restock_{line.id}') == '1'} for line in lines}
        try:
            if authorizer is None or not authorizer.is_superuser:
                raise OperationError('Usuario o contraseña del propietario incorrectos.')
            record, _ = record_return(user=request.user, authorizer=authorizer, request_id=request.POST.get('request_id'), sale_id=sale.id, lines=requested, reason=request.POST.get('reason'))
        except OperationError as error:
            messages.error(request, str(error))
            return redirect('sale_return', sale_id=sale.id)
        messages.success(request, f'Devolución registrada: ${record.total:.2f} por {record.get_method_display().lower()}.')
        return redirect('return_detail', return_id=record.id)
    return render(request, 'store/sale_return.html', {'sale': sale, 'lines': lines, 'request_id': uuid.uuid4(), 'shift': current_shift()})


@login_required
def return_detail(request, return_id):
    record = get_object_or_404(SaleReturn.objects.select_related('sale', 'user', 'authorized_by', 'sale__customer'), pk=return_id)
    if record.user_id != request.user.id and record.sale.cashier_id != request.user.id and not is_owner(request):
        return HttpResponseForbidden('No puedes consultar esta devolución.')
    return render(request, 'store/return_detail.html', {'record': record, 'lines': record.lines.select_related('sale_line')})


@login_required
@require_POST
def removed_line(request):
    try:
        data = read_json(request)
        record_removed_line(user=request.user, request_id=data.get('request_id'), product_id=data.get('product_id'), quantity=data.get('quantity'), reason=data.get('reason'))
    except OperationError as error:
        return JsonResponse({'error': str(error)}, status=400)
    return JsonResponse({'ok': True})


def can_see_credit(request):
    shift = current_shift()
    return is_owner(request) or (bool(shift) and shift.cashier_id == request.user.id)


@login_required
def customers(request):
    if not can_see_credit(request):
        return HttpResponseForbidden('Solo el propietario o quien opera el turno puede consultar el fiado.')
    rows = [(c, customer_balance(c)) for c in Customer.objects.all()]
    return render(request, 'store/customers.html', {'customers': rows, 'total': sum((balance for _, balance in rows), Decimal('0'))})


@login_required
def customer_edit(request, customer_id=None):
    if not is_owner(request):
        return HttpResponseForbidden('Solo el propietario registra clientes de fiado.')
    customer = get_object_or_404(Customer, pk=customer_id) if customer_id else None
    form = CustomerForm(request.POST or None, instance=customer)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        messages.success(request, 'Cliente guardado.')
        return redirect('customer_detail', customer_id=saved.id)
    return render(request, 'store/customer_form.html', {'form': form, 'customer': customer})


@login_required
def customer_detail(request, customer_id):
    customer = get_object_or_404(Customer, pk=customer_id)
    shift = current_shift()
    operates = bool(shift) and can_see_shift(request, shift)
    if not is_owner(request) and not operates:
        return HttpResponseForbidden('Solo el propietario o quien opera el turno puede consultar el fiado.')
    if request.method == 'POST':
        try:
            payment, created = record_credit_payment(user=request.user, request_id=request.POST.get('request_id'), customer=customer, amount=request.POST.get('amount', ''), payment=request.POST.get('payment'))
            if created:
                messages.success(request, f'Abono de ${payment.amount:.2f} registrado.')
        except OperationError as error:
            messages.error(request, str(error))
        return redirect('customer_detail', customer_id=customer.id)
    # (date, description, amount, adds to the debt, link)
    ledger = [(s.created_at, f'Venta #{s.id}', s.total, True, reverse('sale_ticket', args=[s.id])) for s in customer.sales.filter(payment=Sale.CREDIT)]
    ledger += [(r.created_at, f'Devolución #{r.id} de venta #{r.sale_id}', r.total, False, reverse('return_detail', args=[r.id])) for r in SaleReturn.objects.filter(sale__customer=customer, method=Sale.CREDIT)]
    ledger += [(p.created_at, f'Abono en {p.get_payment_display().lower()} · {p.user.username}', p.amount, False, None) for p in customer.payments.select_related('user')]
    ledger.sort(key=lambda entry: entry[0], reverse=True)
    return render(request, 'store/customer_detail.html', {'customer': customer, 'balance': customer_balance(customer), 'ledger': ledger[:100], 'operates': operates, 'request_id': uuid.uuid4()})


@login_required
def store_settings(request):
    if not is_owner(request):
        return HttpResponseForbidden('Solo el propietario configura la tienda.')
    form = StoreSettingsForm(request.POST or None, instance=StoreSettings.current())
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Configuración guardada. Los próximos tickets ya la usan.')
        return redirect('store_settings')
    return render(request, 'store/settings.html', {'form': form})


@login_required
def report(request):
    if not is_owner(request):
        return HttpResponseForbidden('Solo el propietario consulta reportes.')
    date_from = parse_date(request.GET.get('from', '')) or timezone.localdate()
    date_to = parse_date(request.GET.get('to', '')) or date_from
    in_range = dict(created_at__date__gte=date_from, created_at__date__lte=date_to)
    period_sales = Sale.objects.filter(**in_range)
    by_payment = [(dict(Sale.PAYMENT_CHOICES)[r['payment']], r['n'], r['t']) for r in period_sales.values('payment').annotate(n=Count('id'), t=Sum('total')).order_by('payment')]
    totals = period_sales.aggregate(n=Count('id'), t=Sum('total'))
    returns = SaleReturn.objects.filter(**in_range).aggregate(n=Count('id'), t=Sum('total'))
    lines = SaleLine.objects.filter(sale__in=period_sales)
    top_products = lines.values('product__name', 'product__unit').annotate(quantity=Sum('quantity'), amount=Sum('subtotal')).order_by('-amount')[:25]
    costed = lines.filter(unit_cost__isnull=False).aggregate(revenue=Sum('subtotal'), cost=Sum(ExpressionWrapper(F('unit_cost') * F('quantity'), output_field=DecimalField(max_digits=16, decimal_places=5))))
    costed_revenue = costed['revenue'] or Decimal('0')
    margin = (costed_revenue - (costed['cost'] or Decimal('0'))).quantize(Decimal('0.01')) if costed_revenue else None
    total_sales = totals['t'] or Decimal('0')
    context = {
        'date_from': date_from, 'date_to': date_to, 'by_payment': by_payment, 'totals': totals, 'returns': returns,
        'net': total_sales - (returns['t'] or Decimal('0')),
        'average': (total_sales / totals['n']).quantize(Decimal('0.01')) if totals['n'] else None,
        'top_products': top_products, 'margin': margin,
        'margin_pct': (margin / costed_revenue * 100).quantize(Decimal('0.1')) if margin is not None else None,
        'cost_coverage': (costed_revenue / total_sales * 100).quantize(Decimal('1')) if total_sales else None,
        'cash_outs': [(dict(CashOut.KINDS)[r['kind']], r['t']) for r in CashOut.objects.filter(**in_range).values('kind').annotate(t=Sum('amount')).order_by('kind')],
        'removed': RemovedLine.objects.filter(**in_range).values('user__username').annotate(n=Count('id')).order_by('-n'),
        'shifts': Shift.objects.filter(opened_at__date__gte=date_from, opened_at__date__lte=date_to).select_related('cashier').order_by('id'),
    }
    return render(request, 'store/report.html', context)
