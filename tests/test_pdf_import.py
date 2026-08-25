from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from accounts.models import FinancialAccount, User
from core.models import Currency
from ledger.models import Transaction
from ledger.services import account_balance

STATEMENT_TEXT = """
Savings Account Statement
DATE/REF                       TRANSACTION DETAILS                    AMOUNT             BALANCE AFTER
10/03/2026                     Beneficiary: EXAMPLE             1,000.00 EUR             1,000.00 EUR
2026031018267045               MT00EXAMPLE
                               Transfer

01/04/2026                     Account                             10.00 EUR             1,010.00 EUR
2026040118827874               MT00EXAMPLE
                               interest, 2026-03-10 to 2026-04-01. Withheld income tax 1.50 EUR

02/04/2026                     Card payment                        50.00 EUR               960.00 EUR
2026040218827999               SHOP
                               Purchase

                               Opening Balance                  01/01/2026                 0.00 EUR
"""


class FakePage:
    def __init__(self, text):
        self.text = text

    def extract_text(self, extraction_mode=None):
        assert extraction_mode == "layout"
        return self.text


class FakeReader:
    is_encrypted = False

    def __init__(self, pdf_file, strict=False):
        assert strict is False
        self.pages = [FakePage(STATEMENT_TEXT)]


@pytest.fixture
def pdf_account(db):
    user = User.objects.create_user(username="pdf-importer", password="password")
    currency = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    account = FinancialAccount.objects.create(
        owner=user, name="PDF savings", account_type="SAVINGS", currency=currency
    )
    return user, account


def pdf_upload():
    return SimpleUploadedFile("statement.pdf", b"%PDF-fake", content_type="application/pdf")


@pytest.mark.django_db
def test_imports_pdf_rows_and_infers_amount_sign_from_running_balance(
    client, pdf_account, monkeypatch
):
    user, account = pdf_account
    monkeypatch.setattr("ledger.imports.PdfReader", FakeReader)
    client.force_login(user)

    response = client.post(reverse("ledger:import", args=[account.pk]), {"csv_file": pdf_upload()})

    assert response.status_code == 302
    assert account_balance(account) == Decimal("960.0000")
    transactions = Transaction.objects.order_by("transaction_date")
    assert [item.transaction_type for item in transactions] == [
        Transaction.Type.DEPOSIT,
        Transaction.Type.INTEREST,
        Transaction.Type.WITHDRAWAL,
    ]
    assert [item.reference for item in transactions] == [
        "2026031018267045",
        "2026040118827874",
        "2026040218827999",
    ]
    assert "Withheld income tax" in transactions[1].description


@pytest.mark.django_db
def test_pdf_currency_must_match_account(client, pdf_account, monkeypatch):
    user, account = pdf_account
    monkeypatch.setattr("ledger.imports.PdfReader", FakeReader)
    client.force_login(user)
    statement = pdf_upload()
    original_text = FakeReader.__init__

    def gbp_reader(reader, pdf_file, strict=False):
        original_text(reader, pdf_file, strict)
        reader.pages = [FakePage(STATEMENT_TEXT.replace("EUR", "GBP"))]

    monkeypatch.setattr(FakeReader, "__init__", gbp_reader)

    response = client.post(reverse("ledger:import", args=[account.pk]), {"csv_file": statement})

    assert response.status_code == 200
    assert "statement currency does not match" in response.content.decode()
    assert Transaction.objects.count() == 0


@pytest.mark.django_db
def test_image_only_pdf_is_rejected_without_partial_import(client, pdf_account, monkeypatch):
    user, account = pdf_account

    class EmptyReader(FakeReader):
        def __init__(self, pdf_file, strict=False):
            self.pages = [FakePage("")]

    monkeypatch.setattr("ledger.imports.PdfReader", EmptyReader)
    client.force_login(user)

    response = client.post(reverse("ledger:import", args=[account.pk]), {"csv_file": pdf_upload()})

    assert response.status_code == 200
    assert "Scanned image-only statements are not supported" in response.content.decode()
    assert Transaction.objects.count() == 0
