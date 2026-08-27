import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
        ("tax", "0002_returntaxtreatment"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameField(
            model_name="taxrule", old_name="tax_year", new_name="legacy_tax_year"
        ),
        migrations.CreateModel(
            name="TaxYear",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=80)),
                ("jurisdiction", models.CharField(max_length=2)),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("status", models.CharField(choices=[("OPEN", "Open"), ("CLOSED", "Closed"), ("FILED", "Filed"), ("ARCHIVED", "Archived")], default="OPEN", max_length=12)),
                ("notes", models.TextField(blank=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tax_years", to=settings.AUTH_USER_MODEL)),
                ("reporting_currency", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.currency")),
            ],
            options={"ordering": ["-start_date", "jurisdiction", "name"]},
        ),
        migrations.AddConstraint(model_name="taxyear", constraint=models.CheckConstraint(condition=models.Q(("end_date__gte", models.F("start_date"))), name="tax_year_dates_valid")),
        migrations.AddConstraint(model_name="taxyear", constraint=models.UniqueConstraint(fields=("owner", "jurisdiction", "name"), name="unique_named_tax_year")),
        migrations.AddField(model_name="taxrule", name="owner", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="tax_rules", to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name="taxrule", name="tax_year", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="rules", to="tax.taxyear")),
        migrations.AddField(model_name="taxrule", name="category", field=models.CharField(choices=[("INTEREST", "Interest"), ("DIVIDEND", "Dividend"), ("CAPITAL_GAIN", "Capital gain"), ("EMPLOYMENT_INCOME", "Employment income"), ("OTHER_INCOME", "Other income"), ("OVERALL", "Overall taxable basis")], default="OTHER_INCOME", max_length=24), preserve_default=False),
        migrations.AddField(model_name="taxrule", name="fixed_amount", field=models.DecimalField(blank=True, decimal_places=4, max_digits=20, null=True)),
        migrations.AddField(model_name="taxrule", name="priority", field=models.PositiveSmallIntegerField(default=100)),
        migrations.AlterField(model_name="taxrule", name="legacy_tax_year", field=models.PositiveIntegerField(blank=True, null=True)),
        migrations.AlterField(model_name="taxrule", name="rule_type", field=models.CharField(choices=[("FLAT_RATE", "Flat rate"), ("THRESHOLD", "Threshold"), ("ALLOWANCE", "Allowance"), ("DEDUCTION", "Deduction")], max_length=32)),
        migrations.AlterField(model_name="taxrule", name="rate", field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
        migrations.AlterModelOptions(name="taxrule", options={"ordering": ["priority", "name"]}),
        migrations.AddConstraint(model_name="taxrule", constraint=models.CheckConstraint(condition=models.Q(("rate__isnull", True), models.Q(("rate__gte", 0), ("rate__lte", 100)), _connector="OR"), name="annual_tax_rule_rate_valid")),
        migrations.AddConstraint(model_name="taxrule", constraint=models.CheckConstraint(condition=models.Q(("threshold__isnull", True), ("threshold__gte", 0), _connector="OR"), name="annual_tax_rule_threshold_nonnegative")),
        migrations.AddConstraint(model_name="taxrule", constraint=models.CheckConstraint(condition=models.Q(("fixed_amount__isnull", True), ("fixed_amount__gte", 0), _connector="OR"), name="annual_tax_rule_fixed_nonnegative")),
        migrations.CreateModel(
            name="TaxAllowance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("active", models.BooleanField(default=True)), ("name", models.CharField(max_length=120)), ("category", models.CharField(choices=[("INTEREST", "Interest"), ("DIVIDEND", "Dividend"), ("CAPITAL_GAIN", "Capital gain"), ("EMPLOYMENT_INCOME", "Employment income"), ("OTHER_INCOME", "Other income"), ("OVERALL", "Overall taxable basis")], max_length=24)), ("amount", models.DecimalField(decimal_places=4, max_digits=20, validators=[django.core.validators.MinValueValidator(0)])), ("notes", models.TextField(blank=True)), ("currency", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.currency")), ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)), ("tax_year", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="tax.taxyear")),
            ], options={"ordering": ["category", "name"]},
        ),
        migrations.AddConstraint(model_name="taxallowance", constraint=models.CheckConstraint(condition=models.Q(("amount__gte", 0)), name="tax_allowance_nonnegative")),
        migrations.CreateModel(
            name="TaxDeduction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("active", models.BooleanField(default=True)), ("name", models.CharField(max_length=120)), ("category", models.CharField(choices=[("INTEREST", "Interest"), ("DIVIDEND", "Dividend"), ("CAPITAL_GAIN", "Capital gain"), ("EMPLOYMENT_INCOME", "Employment income"), ("OTHER_INCOME", "Other income"), ("OVERALL", "Overall taxable basis")], max_length=24)), ("amount", models.DecimalField(decimal_places=4, max_digits=20, validators=[django.core.validators.MinValueValidator(0)])), ("date", models.DateField()), ("notes", models.TextField(blank=True)), ("currency", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.currency")), ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)), ("tax_year", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="tax.taxyear")),
            ], options={"ordering": ["date", "name"]},
        ),
        migrations.AddConstraint(model_name="taxdeduction", constraint=models.CheckConstraint(condition=models.Q(("amount__gte", 0)), name="tax_deduction_nonnegative")),
        migrations.CreateModel(
            name="TaxAdjustment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("active", models.BooleanField(default=True)), ("category", models.CharField(choices=[("INTEREST", "Interest"), ("DIVIDEND", "Dividend"), ("CAPITAL_GAIN", "Capital gain"), ("CAPITAL_LOSS", "Capital loss"), ("EMPLOYMENT_INCOME", "Employment income"), ("OTHER_INCOME", "Other income"), ("DEDUCTION", "Deduction"), ("ALLOWANCE", "Allowance"), ("WITHHOLDING_TAX", "Withholding tax"), ("TAX_PAYMENT", "Tax payment")], max_length=24)), ("applies_to", models.CharField(blank=True, choices=[("INTEREST", "Interest"), ("DIVIDEND", "Dividend"), ("CAPITAL_GAIN", "Capital gain"), ("EMPLOYMENT_INCOME", "Employment income"), ("OTHER_INCOME", "Other income"), ("OVERALL", "Overall taxable basis")], max_length=24)), ("description", models.CharField(max_length=180)), ("amount", models.DecimalField(decimal_places=4, max_digits=20)), ("date", models.DateField()), ("notes", models.TextField(blank=True)), ("currency", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="core.currency")), ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)), ("tax_year", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="tax.taxyear")),
            ], options={"ordering": ["date", "category", "description"]},
        ),
        migrations.AddConstraint(model_name="taxadjustment", constraint=models.CheckConstraint(condition=models.Q(("amount", 0), _negated=True), name="tax_adjustment_nonzero")),
    ]
