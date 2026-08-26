# Vault67

> Track everything. Know your worth.

Support Vault67 on [Ko-fi](https://ko-fi.com/cyberhazard).

Vault67 Community is licensed under [AGPL-3.0-or-later](LICENSE).

Self-hosted personal-finance management with a user-owned, signed-entry ledger. It is a Django 5.2 MVP focused on accounts, manually-entered transactions, investments metadata, and audit-friendly Decimal calculations.

## Architecture

- `accounts`: custom user, institutions, and financial accounts.
- `ledger`: logical transactions and signed entries. A positive entry increases the displayed balance; a negative entry decreases it. A same-currency transfer is one transaction with two atomic linked entries.
- `core`: currencies and manually entered FX rates.
- `investments`: securities, historical prices, and investment transaction detail.
- `dashboard`: authenticated overview. `tax` and `reporting` are intentionally small extension points.

Money uses `DecimalField`; no monetary float calculations are used. Balances are derived from ledger entries rather than stored. Cross-currency transfers are intentionally rejected until an explicit FX-transfer service is added.

## Run with Docker

```bash
cp .env.example .env
docker compose up --build
```

The web server applies migrations on startup and is available at `http://localhost:8000`. Create an administrator with:

```bash
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py seed_demo_data
```

The demo user is `demo` / `demo`. Never use it outside local development.

The included Compose configuration is for local use and runs Django's development
settings on `localhost`. For a public deployment, run `config.settings.production`
behind a TLS-terminating reverse proxy and provide production host/CSRF settings.

## Developer commands

```bash
make build
make up
make migrate
make migrations
make test
make shell
make down
```

For local tests install `requirements-dev.txt` then run `pytest`. Tests use an in-memory SQLite database; Docker uses PostgreSQL with persistent `postgres_data`.

## Environment

Required values are documented in `.env.example`: Django secret/debug/hosts, PostgreSQL credentials and host/port, and `DEFAULT_CURRENCY` (EUR by default). Production should set `DJANGO_DEBUG=False`, a strong secret, correct hosts, and terminate TLS in a reverse proxy before enabling secure cookies.

## Security and production deployment

Use HTTPS, a strong unique `DJANGO_SECRET_KEY`, a strong database password, and
specific `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` values. Never
run `DEBUG=True` publicly, expose PostgreSQL, or commit `.env`. Rotate any leaked
secret immediately. Keep images and dependencies updated, back up PostgreSQL,
and protect backups: they contain sensitive financial data and should be
encrypted, access-controlled, stored separately, and restoration-tested.

## Backup and restore

Export all Vault67 data—including users, accounts, transactions, investments,
and settings—to a portable JSON file:

```bash
docker compose exec -T web python manage.py export_data > vault67-backup.json
```

To restore it, start a new Vault67 instance so migrations have completed, but
before creating any users or entering data. Then run:

```bash
docker compose exec -T web python manage.py import_data - < vault67-backup.json
```

Restoration deliberately refuses a database containing Vault67 data. The
initially seeded currencies on a new container are safely replaced with the
currencies in the backup. Backup files contain credentials hashes and sensitive
financial data; store and transfer them securely.

Vault67 never stores online-banking usernames or passwords. Future integrations
must use official Open Banking/PSD2, OAuth, or institution-provided APIs. Add
login rate limiting before exposing a deployment to the public Internet. CSV
transaction files and supported text-based PDF statements can be imported into
an account. Imports validate ownership, file type, size, content, currency, and
transaction rows before writing the complete batch atomically.

Run `make security` with production environment values to perform static,
dependency, and Django deployment checks. See [SECURITY.md](SECURITY.md) for
private vulnerability reporting.

Production starts with a conservative one-hour HSTS policy. It intentionally
does not include subdomains or enable browser preload; enable either only after
confirming every current and future subdomain is permanently HTTPS-only.

## License

Vault67 Community is licensed under the GNU Affero General Public License,
version 3 or later (AGPL-3.0-or-later). You may use, modify, and redistribute
Community code under that license. Providing the software over a network can
trigger AGPL source-sharing obligations. Future Vault67 Pro components may be
distributed under separate proprietary terms; the AGPL applies only to code
distributed under it. This is a practical project summary, not legal advice;
refer to [LICENSE](LICENSE) for the actual terms.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the future Community/Pro separation.

## Available pages

- `/login/`, `/logout/`
- `/` dashboard
- `/accounts/` accounts, create/edit/archive and detail
- `/ledger/` transaction history and deposit/withdrawal/income/expense/transfer forms
- `/investments/` brokerage valuation, holdings, trades, dividends, prices, and FX rates
- `/admin/` administrative management for all major models

## Investments and valuation

Every buy, sell, dividend, investment fee, and investment tax is an immutable
`InvestmentTransaction` linked one-to-one to its cash `Transaction`. Both are
posted atomically. Transactions are the historical source of truth; holdings
are replayed from them and valuations are calculated from holdings plus manual
prices and historical FX. Current quantities are never stored as authoritative
balances.

Weighted-average cost is the only cost-basis method in this phase. A buy adds
gross consideration, buy fees, and buy taxes to acquisition cost. A partial
sale removes `quantity × prevailing average cost`; its net realized gain is
gross proceeds minus sell fees, sell taxes, and allocated cost. Sell costs do
not change the remaining position. Native cost is retained and the explicit
trade-time rate (`1 transaction currency = X account-currency units`) preserves
base-currency cost. Short selling is rejected.

Prices and FX rates are append-only historical observations. Lookup selects the
latest observation on or before the requested date, never future data. FX is
stored as `1 base_currency = rate quote_currency`; helpers transparently invert
a stored pair. Missing prices or foreign rates make affected valuation and
portfolio totals visibly incomplete rather than substituting zero or one.

Market value minus remaining cost is unrealized gain; realized and unrealized
gain are accounting measures, not XIRR or time-weighted performance. Brokerage
totals present cash separately from holdings to avoid double counting.

## Current limits and next milestone

Deferred: external price and FX APIs, automatic feeds, FIFO/LIFO/specific-lot
cost basis, short selling, options and derivatives, splits, full capital-gains
tax and tax-year rules, XIRR/TWR, scheduled jobs, broker synchronization, Open
Banking, and background queues.

## Fixed-term deposits

`FIXED_TERM` accounts store their contract in a separate `FixedTermDetails`
record. Rates use decimal fractions internally (`0.0325` means 3.25%), while the
form accepts the familiar percentage value (`3.25`). Simple and compound
projections use ACT/365; compound terms support daily, monthly, quarterly, and
annual frequencies. Actual calendar days are always divided by 365, including
terms that cross a leap day.

The contractual principal is distinct from the ledger balance. On creation,
Vault67 posts either one linked same-currency transfer from the selected funding
account or an opening deposit when no funding account is selected. Editing the
contract later does not rewrite that ledger history. Projected gross interest,
accrued interest, and maturity values are estimates only: they do not post
interest, settle maturity, renew a deposit, calculate penalties, or withhold tax.

## Return tax estimates

Return tax treatments are reusable, user-owned settings that can be attached to savings and
fixed-term accounts. Rates are entered as percentages (`15.00` means 15%). Vault67 first
calculates a gross return, then applies the treatment to estimate tax and the net return; it
never changes the ledger or treats an estimate as a tax payment.

`WITHHOLDING` estimates tax deducted at source. `YEAR_END` estimates tax due later, even though
the gross return may still be received. `CUSTOM` follows its “tax deducted at source” setting.
`NONE` and `EXEMPT` have no estimated tax. Jurisdiction is informational only: Vault67 does not
yet implement country-specific rules, tax years, tax bands, allowances, deductions, automatic
withholding transactions, tax posting, or tax authority integration. Tax estimates are not tax
advice.
