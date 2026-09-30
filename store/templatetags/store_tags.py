from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def money(value):
    """Pesos with cents and thousands separator; SQLite can return sums without decimals."""
    try:
        number = Decimal(str(value if value not in (None, '') else 0)).quantize(Decimal('0.01'))
    except InvalidOperation:
        return value
    return f'-${abs(number):,.2f}' if number < 0 else f'${number:,.2f}'


@register.filter
def unit_label(value):
    """Short Spanish label for a stored unit value (used where only the raw value is available)."""
    from store.models import UNIT_SHORT_LABELS
    return UNIT_SHORT_LABELS.get(value, value)
