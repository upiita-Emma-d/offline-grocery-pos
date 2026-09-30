from .models import StoreSettings


def store_settings(request):
    return {'store': StoreSettings.current()}
