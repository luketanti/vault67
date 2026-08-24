# Architecture notes

## Community and Pro

Vault67 Community is the runnable, self-hosted AGPL-3.0-or-later distribution in
this repository. Future Vault67 Pro functionality should be distributed from a
separate repository/package (for example `vault67-pro`) under separate terms.

Community must remain fully usable without Pro. It must not unconditionally
import proprietary modules. Any future optional integration should use explicit,
documented extension points at the boundary, rather than placing proprietary
placeholders in this repository.
