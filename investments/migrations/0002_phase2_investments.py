import decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def populate_account(apps, schema_editor):
    InvestmentTransaction = apps.get_model("investments", "InvestmentTransaction")
    for item in InvestmentTransaction.objects.filter(account__isnull=True):
        entry = item.transaction.entries.order_by("pk").first()
        if entry:
            item.account_id = entry.account_id
            item.save(update_fields=["account"])


def normalize_manual_sources(apps, schema_editor):
    apps.get_model("investments", "SecurityPrice").objects.filter(source="manual").update(
        source="MANUAL"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_financialaccount_savings_annual_interest_rate"),
        ("investments", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="investmenttransaction",
            name="account",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="investment_transactions",
                to="accounts.financialaccount",
            ),
        ),
        migrations.AddField(
            model_name="investmenttransaction",
            name="settlement_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="investmenttransaction",
            name="quantity",
            field=models.DecimalField(blank=True, decimal_places=8, max_digits=28, null=True),
        ),
        migrations.AlterField(
            model_name="investmenttransaction",
            name="price_per_unit",
            field=models.DecimalField(blank=True, decimal_places=8, max_digits=28, null=True),
        ),
        migrations.AlterField(
            model_name="investmenttransaction",
            name="exchange_rate",
            field=models.DecimalField(
                blank=True,
                decimal_places=12,
                max_digits=24,
                null=True,
                validators=[django.core.validators.MinValueValidator(decimal.Decimal("1E-12"))],
            ),
        ),
        migrations.AlterField(
            model_name="securityprice",
            name="source",
            field=models.CharField(choices=[("MANUAL", "Manual")], default="MANUAL", max_length=64),
        ),
        migrations.RunPython(populate_account, migrations.RunPython.noop),
        migrations.RunPython(normalize_manual_sources, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="investmenttransaction",
            name="account",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="investment_transactions",
                to="accounts.financialaccount",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="security", name="unique_security_symbol_exchange"
        ),
        migrations.AddConstraint(
            model_name="security",
            constraint=models.UniqueConstraint(
                condition=models.Q(("exchange", ""), _negated=True),
                fields=("symbol", "exchange"),
                name="unique_security_symbol_exchange",
            ),
        ),
        migrations.AddConstraint(
            model_name="security",
            constraint=models.UniqueConstraint(
                condition=models.Q(("isin", ""), _negated=True),
                fields=("isin",),
                name="unique_security_isin",
            ),
        ),
        migrations.AddConstraint(
            model_name="investmenttransaction",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("quantity__isnull", True), ("quantity__gt", 0), _connector="OR"
                ),
                name="investment_quantity_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="investmenttransaction",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("price_per_unit__isnull", True), ("price_per_unit__gte", 0), _connector="OR"
                ),
                name="investment_price_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="investmenttransaction",
            constraint=models.CheckConstraint(
                condition=models.Q(("gross_amount__gte", 0)), name="investment_gross_nonnegative"
            ),
        ),
        migrations.AddConstraint(
            model_name="investmenttransaction",
            constraint=models.CheckConstraint(
                condition=models.Q(("fees__gte", 0)), name="investment_fees_nonnegative"
            ),
        ),
        migrations.AddConstraint(
            model_name="investmenttransaction",
            constraint=models.CheckConstraint(
                condition=models.Q(("taxes__gte", 0)), name="investment_taxes_nonnegative"
            ),
        ),
        migrations.AlterModelOptions(
            name="investmenttransaction",
            options={"ordering": ["transaction__transaction_date", "transaction_id"]},
        ),
    ]
