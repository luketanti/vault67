import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .models import Transaction
from .services import _create


class TransactionImportError(ValueError):
    pass


class CsvImportError(TransactionImportError):
    pass


class PdfImportError(TransactionImportError):
    pass


@dataclass(frozen=True)
class ImportedRow:
    transaction_date: date
    description: str
    amount: Decimal
    transaction_type: str
    notes: str = ""
    reference: str = ""
    currency_code: str | None = None


PDF_TRANSACTION_ROW = re.compile(
    r"^\s*(?P<date>\d{2}/\d{2}/\d{4})\s{2,}"
    r"(?P<description>.*?)\s{2,}"
    r"(?P<amount>-?[\d,.]+)\s+(?P<currency>[A-Z]{3})\s{2,}"
    r"(?P<balance>-?[\d,.]+)\s+(?P=currency)\s*$"
)
PDF_REFERENCE_ROW = re.compile(r"^\s*(?P<reference>\d{8,})\s{2,}(?P<related>\S.*?)\s*$")
PDF_OPENING_BALANCE = re.compile(
    r"Opening Balance\s+\d{2}/\d{2}/\d{4}\s+(?P<balance>-?[\d,.]+)\s+" r"(?P<currency>[A-Z]{3})"
)


def _normalise_header(value):
    return " ".join((value or "").strip().casefold().split())


def _parse_date(value, row_number):
    value = value.strip()
    try:
        if "/" in value:
            day, month, year = value.split("/")
            return date(int(year), int(month), int(day))
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        pass
    raise CsvImportError(f"Row {row_number}: Transaction Date must use DD/MM/YYYY or YYYY-MM-DD.")


def _parse_amount(value, row_number):
    value = value.strip().replace("\u00a0", "").replace(" ", "")
    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif "," in value:
        value = value.replace(",", ".")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise CsvImportError(f"Row {row_number}: Amount is not a valid number.") from exc
    if not amount.is_finite():
        raise CsvImportError(f"Row {row_number}: Amount must be a finite number.")
    if amount == 0:
        raise CsvImportError(f"Row {row_number}: Amount must not be zero.")
    if amount.as_tuple().exponent < -4 or abs(amount) >= Decimal(10000000000000000):
        raise CsvImportError(f"Row {row_number}: Amount has too many digits or decimal places.")
    return amount


def _transaction_type(description, amount):
    description = description.casefold()
    if "interest" in description:
        return Transaction.Type.INTEREST
    if "tax" in description:
        return Transaction.Type.TAX
    if "fee" in description or "charge" in description:
        return Transaction.Type.FEE
    return Transaction.Type.DEPOSIT if amount > 0 else Transaction.Type.WITHDRAWAL


def parse_transaction_csv(csv_file):
    try:
        content = csv_file.read().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvImportError("The CSV file must be UTF-8 encoded.") from exc
    if not content.strip():
        raise CsvImportError("The CSV file is empty.")

    try:
        dialect = csv.Sniffer().sniff(content[:4096], delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(content), dialect=dialect)
    if not reader.fieldnames:
        raise CsvImportError("The CSV file does not contain a header row.")

    headers = {_normalise_header(header): header for header in reader.fieldnames}
    required = ("transaction date", "description", "amount")
    missing = [name.title() for name in required if name not in headers]
    if missing:
        raise CsvImportError(f"Missing required column(s): {', '.join(missing)}.")

    rows = []
    for row_number, raw_row in enumerate(reader, start=2):
        if None in raw_row:
            raise CsvImportError(f"Row {row_number}: Found more values than header columns.")
        if not any((value or "").strip() for value in raw_row.values()):
            continue
        description = (raw_row.get(headers["description"]) or "").strip()
        if not description:
            raise CsvImportError(f"Row {row_number}: Description is required.")
        if len(description) > 255:
            raise CsvImportError(f"Row {row_number}: Description must be 255 characters or fewer.")
        transaction_date = _parse_date(raw_row.get(headers["transaction date"]) or "", row_number)
        amount = _parse_amount(raw_row.get(headers["amount"]) or "", row_number)
        notes = ""
        value_date_header = headers.get("value date")
        if value_date_header and (raw_row.get(value_date_header) or "").strip():
            value_date = _parse_date(raw_row[value_date_header], row_number)
            notes = f"Value date: {value_date.isoformat()}"
        rows.append(
            ImportedRow(
                transaction_date=transaction_date,
                description=description,
                amount=amount,
                transaction_type=_transaction_type(description, amount),
                notes=notes,
            )
        )
    if not rows:
        raise CsvImportError("The CSV file does not contain any transaction rows.")
    return rows


def _parse_pdf_number(value, transaction_date):
    try:
        number = Decimal(value.replace(",", ""))
    except InvalidOperation as exc:
        raise PdfImportError(
            f"Could not read the amount for the transaction dated {transaction_date}."
        ) from exc
    if not number.is_finite():
        raise PdfImportError(
            f"Could not read the amount for the transaction dated {transaction_date}."
        )
    return number


def _extract_pdf_text(pdf_file):
    try:
        pdf_file.seek(0)
        reader = PdfReader(pdf_file, strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise PdfImportError("Password-protected PDFs are not supported.")
        if len(reader.pages) > 100:
            raise PdfImportError("The PDF must contain 100 pages or fewer.")
        pages = [
            unicodedata.normalize("NFKC", page.extract_text(extraction_mode="layout") or "")
            for page in reader.pages
        ]
    except PdfImportError:
        raise
    except (PdfReadError, OSError, ValueError, TypeError, KeyError) as exc:
        raise PdfImportError("The PDF could not be read.") from exc
    text = "\n".join(pages)
    if not text.strip():
        raise PdfImportError(
            "No text was found in the PDF. Scanned image-only statements are not supported."
        )
    if len(text) > 2_000_000:
        raise PdfImportError("The extracted PDF text is too large to import.")
    return pages, text


def _raw_pdf_transactions(pages):
    records = []
    supported_layout = False
    for page in pages:
        if all(label in page for label in ("DATE/REF", "TRANSACTION DETAILS", "BALANCE AFTER")):
            supported_layout = True
        current = None
        for line in page.splitlines():
            transaction_match = PDF_TRANSACTION_ROW.match(line)
            if transaction_match:
                if current:
                    records.append(current)
                current = transaction_match.groupdict()
                current["details"] = []
                current["reference"] = ""
                current["related"] = ""
                continue
            if not current:
                continue
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(
                ("Credit balances", "Generated on:", "DATE/REF", "Opening Balance")
            ):
                records.append(current)
                current = None
                continue
            reference_match = PDF_REFERENCE_ROW.match(line)
            if reference_match and not current["reference"]:
                current["reference"] = reference_match.group("reference")
                current["related"] = reference_match.group("related")
                continue
            if line[:1].isspace():
                current["details"].append(stripped)
        if current:
            records.append(current)
    if not supported_layout:
        raise PdfImportError("This PDF does not use a supported bank-statement layout.")
    if not records:
        raise PdfImportError("No transactions were found in the PDF statement.")
    return records


def parse_transaction_pdf(pdf_file):
    pages, text = _extract_pdf_text(pdf_file)
    records = _raw_pdf_transactions(pages)
    opening_match = PDF_OPENING_BALANCE.search(text)
    previous_balance = (
        _parse_pdf_number(opening_match.group("balance"), "opening balance")
        if opening_match
        else None
    )
    opening_currency = opening_match.group("currency") if opening_match else None

    rows = []
    for record in records:
        raw_amount = _parse_pdf_number(record["amount"], record["date"])
        balance = _parse_pdf_number(record["balance"], record["date"])
        if raw_amount == 0:
            raise PdfImportError(f"The transaction dated {record['date']} has a zero amount.")
        if raw_amount.as_tuple().exponent < -4 or abs(raw_amount) >= Decimal(10000000000000000):
            raise PdfImportError(
                f"The amount for the transaction dated {record['date']} has too many digits "
                "or decimal places."
            )
        amount = raw_amount
        if previous_balance is not None:
            balance_change = balance - previous_balance
            if abs(balance_change) != abs(raw_amount):
                raise PdfImportError(
                    f"The running balance does not reconcile for the transaction dated "
                    f"{record['date']}."
                )
            amount = balance_change
        previous_balance = balance

        description_parts = [record["description"], *record["details"]]
        full_description = " ".join(part for part in description_parts if part).strip()
        description = full_description
        notes = [f"Balance after: {balance:,.2f} {record['currency']}"]
        if record["related"]:
            notes.insert(0, f"Related account: {record['related']}")
        if len(description) > 255:
            notes.append(f"Full description: {description}")
            description = f"{description[:252]}..."
        transaction_date = _parse_date(record["date"], record["date"])
        rows.append(
            ImportedRow(
                transaction_date=transaction_date,
                description=description,
                amount=amount,
                transaction_type=_transaction_type(description, amount),
                notes="\n".join(notes),
                reference=record["reference"][:100],
                currency_code=record["currency"],
            )
        )
    currencies = {row.currency_code for row in rows}
    if opening_currency:
        currencies.add(opening_currency)
    if len(currencies) != 1:
        raise PdfImportError("The PDF contains transactions in multiple currencies.")
    return rows


def import_transactions(owner, account, csv_file):
    if account.owner_id != owner.id:
        raise ValidationError("Account does not belong to user.")
    rows = (
        parse_transaction_pdf(csv_file)
        if csv_file.name.casefold().endswith(".pdf")
        else parse_transaction_csv(csv_file)
    )
    if any(row.currency_code and row.currency_code != account.currency.code for row in rows):
        raise TransactionImportError(
            f"The statement currency does not match this {account.currency.code} account."
        )
    with db_transaction.atomic():
        for row in rows:
            _create(
                owner,
                account,
                row.amount,
                row.transaction_type,
                row.transaction_date,
                row.description,
                row.notes,
                row.reference,
            )
    return len(rows)
