"""Portable serialization support for Vault67 application data."""

BACKUP_MODELS = (
    "core.currency",
    "core.exchangerate",
    "accounts.user",
    "tax.returntaxtreatment",
    "tax.taxyear",
    "tax.taxrule",
    "tax.taxdeduction",
    "tax.taxallowance",
    "tax.taxadjustment",
    "accounts.institution",
    "accounts.financialaccount",
    "accounts.fixedtermdetails",
    "ledger.transaction",
    "ledger.transactionentry",
    "investments.security",
    "investments.securityprice",
    "investments.investmenttransaction",
)

# Currencies are initially seeded when the container starts. They are replaced
# during restoration so foreign-key primary keys in the backup remain valid.
FRESH_INSTANCE_MODELS = (
    "accounts.user",
    "accounts.institution",
    "accounts.financialaccount",
    "accounts.fixedtermdetails",
    "ledger.transaction",
    "ledger.transactionentry",
    "investments.security",
    "investments.securityprice",
    "investments.investmenttransaction",
    "tax.returntaxtreatment",
    "tax.taxyear",
    "tax.taxrule",
    "tax.taxdeduction",
    "tax.taxallowance",
    "tax.taxadjustment",
    "core.exchangerate",
)
