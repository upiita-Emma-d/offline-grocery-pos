from django import forms

from .models import UNIT_CHOICES, Customer, Product, StoreSettings


class ProductForm(forms.ModelForm):
    unit = forms.ChoiceField(choices=UNIT_CHOICES, initial='piece', label='Unidad')

    class Meta:
        model = Product
        # "active" is deliberately excluded: deactivation is a separate, audited action.
        fields = ['sku', 'barcode', 'name', 'unit', 'price', 'cost', 'min_stock', 'photo']
        labels = {'sku': 'Clave', 'barcode': 'Código de barras', 'name': 'Nombre', 'price': 'Precio', 'cost': 'Costo', 'min_stock': 'Existencia mínima', 'photo': 'Foto'}

    def clean_barcode(self):
        return self.cleaned_data['barcode'] or None


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
