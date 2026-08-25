import csv
import io
from datetime import date
from decimal import Decimal


def _spreadsheet_safe(value):
    value = str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def _value_date(notes):
    prefix = "Value date: "
    for line in notes.splitlines():
        if line.startswith(prefix):
            try:
                return date.fromisoformat(line.removeprefix(prefix).strip())
            except ValueError:
                return None
    return None


def export_account_transactions(account):
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(["Transaction Date", "Value Date", "Description", "Amount"])
    entries = account.entries.select_related("transaction").order_by(
        "-transaction__transaction_date", "-id"
    )
    quantum = Decimal("0.01")
    for entry in entries:
        value_date = _value_date(entry.transaction.notes)
        writer.writerow(
            [
                entry.transaction.transaction_date.strftime("%d/%m/%Y"),
                value_date.strftime("%d/%m/%Y") if value_date else "",
                _spreadsheet_safe(entry.transaction.description),
                f"{entry.amount.quantize(quantum):,.2f}",
            ]
        )
    return output.getvalue()
