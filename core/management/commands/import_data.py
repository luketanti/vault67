from django.apps import apps
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import connection, transaction

from core.backup import BACKUP_MODELS, FRESH_INSTANCE_MODELS


class Command(BaseCommand):
    help = "Restore a Vault67 JSON backup into a fresh instance."

    def add_arguments(self, parser):
        parser.add_argument(
            "input",
            help="Path to a JSON backup file, or '-' for standard input.",
        )

    def handle(self, *args, **options):
        populated_models = [
            label for label in FRESH_INSTANCE_MODELS if apps.get_model(label).objects.exists()
        ]
        if populated_models:
            raise CommandError(
                "Restore only into a fresh instance; existing data was found in: "
                + ", ".join(populated_models)
            )

        currency_model = apps.get_model("core.currency")
        with transaction.atomic():
            currency_model.objects.all().delete()
            call_command(
                "loaddata",
                options["input"],
                format="json",
                verbosity=options["verbosity"],
            )
            self._reset_sequences()

        self.stdout.write(self.style.SUCCESS("Vault67 backup restored successfully."))

    def _reset_sequences(self):
        models = [apps.get_model(label) for label in BACKUP_MODELS]
        sequence_sql = connection.ops.sequence_reset_sql(no_style(), models)
        with connection.cursor() as cursor:
            for statement in sequence_sql:
                cursor.execute(statement)
