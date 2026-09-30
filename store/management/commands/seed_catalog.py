import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from store.models import Product
from store.services import record_receipt

# Approximate reference prices for a small Mexican grocery store (September 2026). They are not any
# store's real prices: review them when receiving goods. Barcodes are left empty on purpose; the real
# code is assigned by scanning the product on the receiving screen.
# (sku, Spanish product name, unit, price, sample stock, minimum stock)
CATALOG = [
    # Soft drinks, water and beverages
    ('COCA600', 'Coca-Cola 600 ml', 'piece', '22.00', 24, 8),
    ('COCA2L', 'Coca-Cola 2 L', 'piece', '39.00', 12, 4),
    ('COCA3L', 'Coca-Cola 3 L', 'piece', '52.00', 6, 2),
    ('PEPSI600', 'Pepsi 600 ml', 'piece', '19.00', 12, 4),
    ('SPRITE600', 'Sprite 600 ml', 'piece', '20.00', 12, 4),
    ('FANTA600', 'Fanta naranja 600 ml', 'piece', '20.00', 12, 4),
    ('JARRI600', 'Jarritos tamarindo 600 ml', 'piece', '17.00', 12, 4),
    ('PENAF600', 'Peñafiel mineral 600 ml', 'piece', '18.00', 12, 4),
    ('CIEL600', 'Agua Ciel 600 ml', 'piece', '12.00', 24, 8),
    ('BONAF1L', 'Agua Bonafont 1 L', 'piece', '16.00', 12, 4),
    ('CIEL15L', 'Agua Ciel 1.5 L', 'piece', '19.00', 12, 4),
    ('BOING500', 'Boing mango 500 ml', 'piece', '16.00', 12, 4),
    ('JUMEX335', 'Jumex durazno lata 335 ml', 'piece', '17.00', 12, 4),
    ('GATOR600', 'Gatorade 600 ml', 'piece', '26.00', 6, 2),
    ('ELECT625', 'Electrolit 625 ml', 'piece', '29.00', 6, 2),
    ('VOLT473', 'Bebida energética Volt 473 ml', 'piece', '22.00', 6, 2),
    # Dairy and eggs
    ('LALA1L', 'Leche Lala entera 1 L', 'piece', '30.00', 12, 6),
    ('LALADES1L', 'Leche Lala deslactosada 1 L', 'piece', '33.00', 12, 6),
    ('ALPURA1L', 'Leche Alpura clásica 1 L', 'piece', '31.00', 6, 3),
    ('YOGLALA', 'Yogurt bebible Lala 250 g', 'piece', '13.00', 12, 4),
    ('CREMALALA', 'Crema Lala 450 ml', 'piece', '36.00', 4, 2),
    ('QUESOPAN', 'Queso panela a granel', 'kg', '150.00', '1.500', '0.500'),
    ('JAMONPAV', 'Jamón de pavo a granel', 'kg', '140.00', '1.500', '0.500'),
    ('HUEVOKG', 'Huevo blanco a granel', 'kg', '46.00', 10, 3),
    ('HUEVO12', 'Huevo blanco 12 piezas', 'pack', '44.00', 6, 2),
    # Bread and snack cakes
    ('BIMBOG', 'Pan blanco Bimbo grande', 'piece', '53.00', 4, 2),
    ('BIMBOINT', 'Pan integral Bimbo', 'piece', '58.00', 3, 1),
    ('TIARO10', 'Tortillinas Tía Rosa 10 piezas', 'pack', '28.00', 6, 2),
    ('GANSITO', 'Gansito Marinela', 'piece', '21.00', 12, 4),
    ('PINGUI', 'Pingüinos Marinela 2 piezas', 'pack', '22.00', 12, 4),
    ('MANTECADA', 'Mantecadas Bimbo 4 piezas', 'pack', '30.00', 6, 2),
    # Chips, cookies and candy
    ('SABRI45', 'Sabritas sal 45 g', 'piece', '21.00', 12, 4),
    ('DORINA', 'Doritos nacho 58 g', 'piece', '21.00', 12, 4),
    ('RUFQUESO', 'Ruffles queso 50 g', 'piece', '21.00', 12, 4),
    ('CHEETOS', 'Cheetos torciditos 52 g', 'piece', '17.00', 12, 4),
    ('TAKISF', 'Takis Fuego 70 g', 'piece', '21.00', 12, 4),
    ('CACAHJAP', 'Cacahuate japonés 100 g', 'piece', '18.00', 8, 3),
    ('MARIAS', 'Galletas Marías Gamesa 170 g', 'pack', '19.00', 8, 3),
    ('EMPERADOR', 'Galletas Emperador chocolate 109 g', 'pack', '20.00', 8, 3),
    ('PRINCIPE', 'Galletas Príncipe Marinela 90 g', 'pack', '19.00', 8, 3),
    ('CHOKIS', 'Galletas Chokis 84 g', 'pack', '19.00', 8, 3),
    ('CARLOSV', 'Chocolate Carlos V 18 g', 'piece', '9.00', 24, 8),
    ('MAZAPAN', 'Mazapán De la Rosa', 'piece', '5.00', 30, 10),
    ('HALLS', 'Halls mentol', 'piece', '12.00', 12, 4),
    ('TRIDENT', 'Chicles Trident 4 piezas', 'piece', '8.00', 12, 4),
    # Pantry staples
    ('ARROZ1K', 'Arroz súper extra 1 kg', 'piece', '34.00', 10, 4),
    ('FRIJNEG1K', 'Frijol negro 1 kg', 'piece', '42.00', 10, 4),
    ('AZUCAR1K', 'Azúcar estándar 1 kg', 'piece', '33.00', 10, 4),
    ('SALFINA1K', 'Sal La Fina 1 kg', 'piece', '16.00', 6, 2),
    ('ACEI123', 'Aceite 1-2-3 1 L', 'piece', '44.00', 8, 3),
    ('NUTRIO850', 'Aceite Nutrioli 850 ml', 'piece', '48.00', 6, 2),
    ('MASECA1K', 'Harina de maíz Maseca 1 kg', 'piece', '26.00', 10, 4),
    ('HTRIGO1K', 'Harina de trigo 1 kg', 'piece', '28.00', 6, 2),
    ('FIDEO200', 'Pasta fideo La Moderna 200 g', 'piece', '11.00', 20, 6),
    ('SPAGH200', 'Pasta spaghetti La Moderna 200 g', 'piece', '11.00', 12, 4),
    ('ATUNDOL', 'Atún Dolores en agua 140 g', 'piece', '27.00', 12, 4),
    ('SARDTOM', 'Sardinas en tomate 425 g', 'piece', '38.00', 6, 2),
    ('JALCOST', 'Chiles jalapeños La Costeña 220 g', 'piece', '21.00', 8, 3),
    ('FRIJREF', 'Frijoles refritos La Sierra 430 g', 'piece', '27.00', 8, 3),
    ('PURETOM', 'Puré de tomate 210 g', 'piece', '10.00', 12, 4),
    ('MAYOMC', 'Mayonesa McCormick 390 g', 'piece', '49.00', 4, 2),
    ('CATSUP', 'Catsup 320 g', 'piece', '25.00', 4, 2),
    ('CONSOME', 'Consomé de pollo en cubos 8 piezas', 'pack', '18.00', 8, 3),
    ('MARUCH', 'Sopa instantánea Maruchan 64 g', 'piece', '17.00', 24, 8),
    ('NESCAF120', 'Café Nescafé Clásico 120 g', 'piece', '105.00', 3, 1),
    ('ABUELITA', 'Chocolate Abuelita tableta 90 g', 'piece', '27.00', 6, 2),
    ('AVENA400', 'Avena Quaker 400 g', 'piece', '33.00', 4, 2),
    ('ZUCARIT', 'Cereal Zucaritas 290 g', 'piece', '62.00', 3, 1),
    ('LECHERA', 'Leche condensada La Lechera 375 g', 'piece', '36.00', 4, 2),
    ('CARNATION', 'Leche evaporada Carnation 360 g', 'piece', '29.00', 4, 2),
    ('GELATINA', 'Gelatina en polvo 120 g', 'piece', '14.00', 8, 3),
    # Cleaning and household
    ('PAPEL4', 'Papel higiénico 4 rollos', 'pack', '38.00', 8, 3),
    ('SERVIL', 'Servilletas 125 piezas', 'pack', '21.00', 6, 2),
    ('ZOTE400', 'Jabón Zote 400 g', 'piece', '26.00', 6, 2),
    ('ROMA1K', 'Detergente Roma 1 kg', 'piece', '39.00', 6, 2),
    ('FABUL1L', 'Limpiador Fabuloso 1 L', 'piece', '33.00', 4, 2),
    ('CLORAL950', 'Blanqueador Cloralex 950 ml', 'piece', '23.00', 6, 2),
    ('SUAVI850', 'Suavizante Suavitel 850 ml', 'piece', '33.00', 4, 2),
    ('AXION400', 'Lavatrastes Axion 400 ml', 'piece', '31.00', 4, 2),
    ('VELADORA', 'Veladora de vaso', 'piece', '22.00', 6, 2),
    ('PILAAA2', 'Pilas AA 2 piezas', 'pack', '48.00', 4, 2),
    ('CERILLOS', 'Cerillos caja chica', 'piece', '4.00', 20, 5),
    # Personal care
    ('ESCUDO', 'Jabón de tocador Escudo 150 g', 'piece', '24.00', 6, 2),
    ('COLGATE', 'Pasta dental Colgate 100 ml', 'piece', '33.00', 4, 2),
    ('SHAMPOO', 'Shampoo Sedal 190 ml', 'piece', '36.00', 4, 2),
    ('TOALLAS', 'Toallas femeninas 10 piezas', 'pack', '36.00', 4, 2),
    # Bulk produce
    ('JITOMATE', 'Jitomate saladet', 'kg', '28.00', 5, 2),
    ('CEBOLLA', 'Cebolla blanca', 'kg', '30.00', 4, 2),
    ('PAPA', 'Papa blanca', 'kg', '32.00', 5, 2),
    ('LIMON', 'Limón sin semilla', 'kg', '38.00', 3, 1),
    ('PLATANO', 'Plátano tabasco', 'kg', '24.00', 4, 2),
    ('CHILESER', 'Chile serrano', 'kg', '45.00', 1, '0.500'),
    ('AGUACATE', 'Aguacate Hass', 'kg', '75.00', 2, 1),
]


class Command(BaseCommand):
    help = 'Load a reference grocery catalog with approximate prices; optionally a sample goods receipt with stock.'

    def add_arguments(self, parser):
        parser.add_argument('--with-stock', metavar='OWNER_USERNAME', help='Record a sample goods receipt with stock, authored by this owner account.')

    def handle(self, *args, **options):
        owner = None
        if options['with_stock']:
            owner = get_user_model().objects.filter(username=options['with_stock'], is_superuser=True).first()
            if owner is None:
                raise CommandError('That user does not exist or is not an owner (superuser).')
        with transaction.atomic():
            created = []
            for sku, name, unit, price, stock, minimum in CATALOG:
                product, is_new = Product.objects.get_or_create(sku=sku, defaults={'name': name, 'unit': unit, 'price': Decimal(price), 'min_stock': Decimal(str(minimum))})
                if is_new:
                    created.append((product, stock))
            if owner and created:
                record_receipt(user=owner, request_id=uuid.uuid4(), supplier='Carga inicial de ensayo', document='Existencias aproximadas; confirmar con conteo',
                               items=[{'product_id': p.id, 'quantity': str(s)} for p, s in created])
        suffix = ' with a sample goods receipt' if owner and created else ''
        self.stdout.write(self.style.SUCCESS(f'{len(created)} reference products created{suffix}. Review prices and assign barcodes by scanning on the receiving screen.'))
