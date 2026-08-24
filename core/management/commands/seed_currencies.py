from django.core.management.base import BaseCommand

from core.models import Currency


class Command(BaseCommand):
    help = "Create or update the standard currencies used by Vault67."

    def handle(self, *args, **options):
        currencies = [
            ("EUR", "Euro", "€", 2),
            ("USD", "US Dollar", "$", 2),
            ("GBP", "Pound Sterling", "£", 2),
            ("CHF", "Swiss Franc", "CHF", 2),
            ("JPY", "Japanese Yen", "¥", 0),
        ]
        for code, name, symbol, decimal_places in currencies:
            Currency.objects.update_or_create(
                code=code,
                defaults={"name": name, "symbol": symbol, "decimal_places": decimal_places},
            )
        self.stdout.write(self.style.SUCCESS("Standard currencies are ready."))
