from django.urls import path

from . import views

# Page paths stay in Spanish because they are visible in the browser; API paths are English.
urlpatterns = [
    path('', views.home, name='home'),
    path('caja/', views.checkout, name='checkout'),
    path('api/products/', views.product_search, name='product_search'),
    path('api/products/lookup/', views.barcode_lookup, name='barcode_lookup'),
    path('api/products/quick-create/', views.quick_create, name='quick_create'),
    path('api/products/<int:product_id>/barcode/', views.assign_barcode, name='assign_barcode'),
    path('api/sales/', views.charge, name='charge'),
    path('api/receipts/', views.receipt_confirm, name='receipt_confirm'),
    path('api/removed-lines/', views.removed_line, name='removed_line'),
    path('catalogo/', views.catalog, name='catalog'),
    path('catalogo/nuevo/', views.product_edit, name='product_new'),
    path('catalogo/<int:product_id>/', views.product_edit, name='product_edit'),
    path('catalogo/<int:product_id>/estado/', views.product_status, name='product_status'),
    path('catalogo/<int:product_id>/precio/', views.product_price, name='product_price'),
    path('inventario/', views.inventory, name='inventory'),
    path('inventario/recepcion/', views.receiving, name='receiving'),
    path('inventario/recepciones/<int:receipt_id>/', views.receipt_detail, name='receipt_detail'),
    path('turnos/', views.shifts, name='shifts'),
    path('turnos/<int:shift_id>/corte/', views.shift_report, name='shift_report'),
    path('turnos/<int:shift_id>/imprimir/<str:document>/', views.shift_reprint, name='shift_reprint'),
    path('ventas/', views.sales, name='sales'),
    path('ventas/<int:sale_id>/ticket/', views.sale_ticket, name='sale_ticket'),
    path('ventas/<int:sale_id>/imprimir/', views.sale_reprint, name='sale_reprint'),
    path('ventas/<int:sale_id>/devolucion/', views.sale_return, name='sale_return'),
    path('devoluciones/<int:return_id>/', views.return_detail, name='return_detail'),
    path('clientes/', views.customers, name='customers'),
    path('clientes/nuevo/', views.customer_edit, name='customer_new'),
    path('clientes/<int:customer_id>/', views.customer_detail, name='customer_detail'),
    path('clientes/<int:customer_id>/editar/', views.customer_edit, name='customer_edit'),
    path('reportes/', views.report, name='report'),
    path('configuracion/', views.store_settings, name='store_settings'),
]
