from django import forms

from .models import UNIT_CHOICES, Customer, Product, StoreSettings


def next_free_sku():
    """P00001-style internal code for products created without SKU nor barcode."""
    number = Product.objects.count() + 1
    while Product.objects.filter(sku=f'P{number:05d}').exists():
        number += 1
    return f'P{number:05d}'


class ProductForm(forms.ModelForm):
    unit = forms.ChoiceField(choices=UNIT_CHOICES, initial='piece', label='Unidad')

    class Meta:
        model = Product
        # Ordered by how often each field is used (ADR-006). "active" is deliberately excluded:
        # deactivation is a separate, audited action.
        fields = ['barcode', 'name', 'price', 'unit', 'sku', 'cost', 'min_stock', 'photo']
        labels = {'sku': 'Clave interna (opcional)', 'barcode': 'Código de barras', 'name': 'Nombre', 'price': 'Precio de venta', 'cost': 'Costo', 'min_stock': 'Existencia mínima', 'photo': 'Foto'}
        help_texts = {'sku': 'Si la dejas vacía se usa el código de barras o una clave automática.', 'barcode': 'Escanéalo o escríbelo tal cual, con sus ceros.'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['sku'].required = False
        for name in ('price', 'cost', 'min_stock'):
            self.fields[name].widget.attrs['data-numpad'] = ''  # on-screen keypad on phones (ADR-006)

    def clean_barcode(self):
        return self.cleaned_data['barcode'] or None

    def clean(self):
        data = super().clean()
        if not data.get('sku'):
            # An empty SKU becomes the barcode or the next free automatic code.
            sku = (data.get('barcode') or '')[:40] or next_free_sku()
            if Product.objects.filter(sku=sku).exclude(pk=self.instance.pk).exists():
                sku = next_free_sku()
            data['sku'] = sku
            self.instance.sku = sku
        return data


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'phone', 'credit_limit', 'active']
        labels = {'name': 'Nombre o alias', 'phone': 'Teléfono (opcional)', 'credit_limit': 'Límite de crédito (opcional)', 'active': 'Puede comprar a fiado'}


class StoreSettingsForm(forms.ModelForm):
    class Meta:
        model = StoreSettings
        fields = ['name', 'header', 'footer']
        labels = {'name': 'Nombre de la tienda', 'header': 'Encabezado del ticket', 'footer': 'Pie del ticket'}
        widgets = {'header': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Calle y número, colonia\nTel. 55 0000 0000'}), 'footer': forms.Textarea(attrs={'rows': 2})}
