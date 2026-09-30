from django.core.management.base import BaseCommand, CommandError

from store.models import PrintAttempt
from store.services import print_test, printer_settings


class Command(BaseCommand):
    help = 'Print a test page on the configured network printer (POS_PRINTER_HOST).'

    def handle(self, *args, **options):
        host, port, columns, accents = printer_settings()
        if not host:
            raise CommandError('Set POS_PRINTER_HOST to the printer IP address first.')
        self.stdout.write(f'Sending test page to {host}:{port} with {columns} columns' + (' and accents' if accents else '') + '...')
        if not print_test():
            raise CommandError(f'Could not print: {PrintAttempt.objects.latest("id").detail}')
        self.stdout.write(self.style.SUCCESS('Test page sent. Check that no text is cut and the digit line fills the paper width.'))
