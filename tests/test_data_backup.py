from django.core.management import call_command

import pytest

from accounts.models import User
from core.models import Currency


@pytest.mark.django_db(transaction=True)
def test_data_backup_can_be_restored_to_a_fresh_database(tmp_path):
    User.objects.create_user(username="backup-user", password="safe-password")
    Currency.objects.create(code="EUR", name="Euro", symbol="€")
    backup_path = tmp_path / "vault67-backup.json"

    call_command("export_data", "--output", str(backup_path))
    call_command("flush", interactive=False)
    call_command("import_data", str(backup_path))

    restored_user = User.objects.get(username="backup-user")
    assert restored_user.check_password("safe-password")
    assert Currency.objects.get(code="EUR").name == "Euro"
