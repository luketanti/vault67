from django.core.management import call_command
from django.core.management.base import BaseCommand

from core.backup import BACKUP_MODELS


class Command(BaseCommand):
    help = "Write a portable backup of all Vault67 data as JSON."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            help="Write the backup to this file instead of standard output.",
        )

    def handle(self, *args, **options):
        arguments = [*BACKUP_MODELS, "--indent", "2"]
        if output := options["output"]:
            arguments.extend(["--output", output])
        call_command("dumpdata", *arguments, stdout=self.stdout)
