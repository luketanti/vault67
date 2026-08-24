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
docker compose exec web python manage.py seed_currencies
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

Vault67 never stores online-banking usernames or passwords. Future integrations
must use official Open Banking/PSD2, OAuth, or institution-provided APIs. Add
login rate limiting before exposing a deployment to the public Internet. CSV/OFX
uploads are not implemented; future import work must validate file type, size,
filename, and storage handling.

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
- `/admin/` administrative management for all major models

## Current limits and next milestone

No bank sync, market/FX API, tax engine, price-based investment valuation, categories, or reports are included. The next milestone should add explicit FX transfer entries, investment buy/sell ledger posting and holdings/cost-basis services, then a reporting-currency valuation layer.

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
