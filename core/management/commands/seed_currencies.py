"""Seed current ISO 4217 currencies from the official maintenance agency."""

from urllib.error import URLError
from urllib.request import urlopen

from defusedxml import ElementTree

from django.core.management.base import BaseCommand

from core.models import Currency

ISO_4217_LIST_ONE_URL = (
    "https://www.six-group.com/dam/download/financial-information/"
    "data-center/iso-currrency/lists/list-one.xml"
)
SYMBOLS = {
    "AED": "د.إ",
    "AUD": "A$",
    "BRL": "R$",
    "CAD": "C$",
    "CHF": "CHF",
    "CNY": "¥",
    "EUR": "€",
    "GBP": "£",
    "HKD": "HK$",
    "INR": "₹",
    "JPY": "¥",
    "KRW": "₩",
    "MXN": "MX$",
    "NZD": "NZ$",
    "SGD": "S$",
    "TRY": "₺",
    "USD": "$",
    "ZAR": "R",
}
FALLBACK_CURRENCIES = (
    ("EUR", "Euro", "€", 2),
    ("USD", "US Dollar", "$", 2),
    ("GBP", "Pound Sterling", "£", 2),
    ("CHF", "Swiss Franc", "CHF", 2),
    ("JPY", "Yen", "¥", 0),
)


def fetch_iso_4217_currencies():
    """Return unique current currencies, excluding ISO funds and metals."""
    with urlopen(ISO_4217_LIST_ONE_URL, timeout=10) as response:  # nosec B310: official HTTPS feed
        document = ElementTree.fromstring(response.read())

    currencies = {}
    for entry in document.findall("./CcyTbl/CcyNtry"):
        code = entry.findtext("Ccy")
        minor_units = entry.findtext("CcyMnrUnts")
        name_element = entry.find("CcyNm")
        if not code or not minor_units or not minor_units.isdigit() or name_element is None:
            continue
        if name_element.get("IsFund") == "true":
            continue
        currencies.setdefault(
            code,
            (code, name_element.text.strip(), SYMBOLS.get(code, code), int(minor_units)),
        )
    return tuple(currencies[code] for code in sorted(currencies))


class Command(BaseCommand):
    help = "Create or update current ISO 4217 currencies used by Vault67."

    def add_arguments(self, parser):
        parser.add_argument(
            "--offline",
            action="store_true",
            help="Use only the bundled core currency fallback.",
        )

    def handle(self, *args, **options):
        currencies = FALLBACK_CURRENCIES
        if not options["offline"]:
            try:
                currencies = fetch_iso_4217_currencies()
            except (URLError, OSError, ElementTree.ParseError) as error:
                self.stderr.write(
                    self.style.WARNING(
                        f"Could not refresh ISO 4217 currencies: {error}. Using fallback."
                    )
                )

        for code, name, symbol, decimal_places in currencies:
            Currency.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "symbol": symbol,
                    "decimal_places": decimal_places,
                    "active": True,
                },
            )
        self.stdout.write(self.style.SUCCESS(f"{len(currencies)} current currencies are ready."))
