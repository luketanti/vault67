from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_financialaccount_return_tax_treatment"),
    ]

    operations = [
        migrations.AddField(
            model_name="financialaccount",
            name="savings_annual_interest_rate",
            field=models.DecimalField(
                blank=True,
                decimal_places=8,
                help_text="Annual rate stored as a decimal fraction; 0.0325 means 3.25%.",
                max_digits=12,
                null=True,
                validators=[MinValueValidator(0), MaxValueValidator(1)],
            ),
        ),
    ]
