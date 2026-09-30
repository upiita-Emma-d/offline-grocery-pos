import hashlib
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Create and verify a consistent copy of the SQLite database.'

    def add_arguments(self, parser):
        parser.add_argument('--dest', help='Backup directory, ideally on another drive. Defaults to POS_BACKUP_DIR or data/backups.')
        parser.add_argument('--keep', type=int, default=0, help='Keep only the newest N backups in the destination (0 keeps all).')

    def handle(self, *args, **options):
        source = Path(settings.DATABASES['default']['NAME'])
        if not source.exists():
            raise CommandError('The database does not exist yet.')
        dest_dir = Path(options['dest'] or os.environ.get('POS_BACKUP_DIR') or settings.DATA_DIR / 'backups')
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f'store-{datetime.now(timezone.utc):%Y%m%d-%H%M%S-%f}.sqlite3'
        try:
            # sqlite3's online backup API gives a consistent copy even while the server is running.
            with sqlite3.connect(str(source)) as origin, sqlite3.connect(str(dest)) as copy:
                origin.backup(copy)
                result = copy.execute('PRAGMA integrity_check').fetchone()[0]
            if result != 'ok':
                raise CommandError(f'The backup failed the integrity check: {result}')
            digest = hashlib.sha256(dest.read_bytes()).hexdigest()
        except (OSError, sqlite3.Error) as error:
            raise CommandError(f'Could not create the backup: {error}')
        if options['keep'] > 0:
            for old in sorted(dest_dir.glob('store-*.sqlite3'), reverse=True)[options['keep']:]:
                old.unlink()
        self.stdout.write(self.style.SUCCESS(f'Verified backup: {dest}\nSHA256: {digest}'))
