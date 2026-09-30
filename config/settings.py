"""Django settings for the Tienda POS. Configuration comes from environment variables, optionally
loaded from a `.env` file next to manage.py (see .env.example)."""
import os
import sys
from pathlib import Path

from django.core.management.utils import get_random_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent


def load_env_file(path):
    """Minimal .env reader (KEY=VALUE per line). Real environment variables win."""
    if not path.exists():
        return
    for raw in path.read_text(encoding='utf-8-sig').splitlines():  # PowerShell 5 writes a BOM
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file(BASE_DIR / '.env')

# Tests must never reach a real printer configured in .env; printing tests set a fake host themselves.
TESTING = len(sys.argv) > 1 and sys.argv[1] == 'test'
if TESTING:
    os.environ['POS_PRINTER_HOST'] = ''

# Database, secret key for development, backups and uploaded photos live here, outside Git.
DATA_DIR = Path(os.environ.get('POS_DATA_DIR') or BASE_DIR / 'data')
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEBUG = os.environ.get('POS_DEBUG', '1') == '1'
SECRET_KEY = os.environ.get('POS_SECRET_KEY')
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError('POS_SECRET_KEY is required when POS_DEBUG=0.')
    # Development only: a random key persisted in the data directory.
    key_file = DATA_DIR / 'dev-secret-key.txt'
    if not key_file.exists():
        try:
            with key_file.open('x', encoding='utf-8') as handle:
                handle.write(get_random_secret_key())
        except FileExistsError:
            pass
    SECRET_KEY = key_file.read_text(encoding='utf-8').strip()

ALLOWED_HOSTS = [host.strip() for host in os.environ.get('POS_ALLOWED_HOSTS', '127.0.0.1,localhost').split(',') if host.strip()]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'store',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'builtins': ['store.templatetags.store_tags'],
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'store.context_processors.store_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': DATA_DIR / 'store.sqlite3',
        # A single server process owns the database; wait instead of failing on a brief write lock.
        'OPTIONS': {'timeout': 20},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# The user interface is Spanish (Mexico); code and documentation are English.
LANGUAGE_CODE = 'es-mx'
TIME_ZONE = os.environ.get('POS_TIME_ZONE', 'America/Mexico_City')
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'  # filled by `collectstatic` and served by WhiteNoise
STATIC_ROOT.mkdir(exist_ok=True)
MEDIA_URL = 'media/'
MEDIA_ROOT = DATA_DIR / 'media'
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'login'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
