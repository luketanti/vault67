# Architecture notes

## Community and Pro

Vault67 Community is the runnable, self-hosted AGPL-3.0-or-later distribution in
this repository. Future Vault67 Pro functionality should be distributed from a
separate repository/package (for example `vault67-pro`) under separate terms.

Community must remain fully usable without Pro. It must not unconditionally
import proprietary modules. Any future optional integration should use explicit,
documented extension points at the boundary, rather than placing proprietary
placeholders in this repository.

## Investment accounting layers

Investment cash uses the generic ledger. `InvestmentTransaction` carries the
security-specific facts and points to exactly one `Transaction`; its brokerage
account entry is created in the same database transaction. Historical records
are correction-only rather than casually editable or deletable.

The layers are intentionally one-way:

1. transactions are the historical source of truth;
2. holdings and weighted-average cost are derived by ordered replay;
3. valuation combines holdings with date-bounded security prices and FX.

Accounting services live in `investments/services/`; the general historical FX
lookup lives in `core/services/fx.py`. The cost-basis interface can later route
to FIFO, LIFO, or specific-lot implementations without changing views.
