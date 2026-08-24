# Contributing to Vault67

Thank you for improving Vault67. Use Python 3.13+, copy `.env.example` to `.env`,
and use Docker or install `requirements-dev.txt` for local development.

Run `pytest`, `ruff check .`, and `make security` before opening a pull request.
Follow Django conventions, retain `Decimal` for financial values, keep financial
logic in services, and add regression tests for changes.

Please do not disclose security vulnerabilities in public issues; follow
[`SECURITY.md`](SECURITY.md). Contributions are submitted under AGPL-3.0-or-later
unless another written agreement applies. No CLA is required today; maintainers
may introduce a formal contributor agreement later if dual licensing requires it.
