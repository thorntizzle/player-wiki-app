# Local Read Qualification

Use this bounded development helper for one fixed, credential-free `/readyz`
GET after a local source change. It checks ordinary application construction,
readiness dispatch, unchanged complete selected inputs and owned process closure.
It does not qualify Character mechanics, authentication, browser interaction,
deployment, a backup or a mutation. Independent review remains required.

## Inputs And Invocation

Use the exact interpreter selected by `local.ps1 -Action environment-check`,
with `-I -B`. Keep the existing environment-check at its actual admission boundary;
this helper does not reinstall dependencies or repeat that command per request.
Before owned helper/application imports, the adapter selects a fresh nonexistent
Python cache prefix and requires `-B`. Existing bytecode cannot satisfy those
imports, and no new cache is written. Existing caches are left untouched; `-B`
by itself would only prevent writes and would not establish source execution.

Supply an existing stopped, exclusively owned local corpus under repo `.local/`:
a rollback-journal SQLite database with no WAL/SHM/journal sidecars, plus the
complete campaign directory intended for this check. A verified retained corpus
or separately authorized supported restore can prepare it. Never point at a
running app, production data, a worktree's default data or an unverified archive.
The confirmation flag asserts exclusive ownership; the helper cannot prove it.

```powershell
& $configuredPython -I -B scripts/qualify_local_read.py `
  --db .local/read-corpus/app.sqlite3 `
  --campaigns .local/read-corpus/campaigns `
  --output .local/read-results/new-run `
  --confirm-isolated
```

Create the output parent first. The run directory must be new and outside the
campaign tree. Existing outputs, links/reparse inputs and unsupported SQLite
journaling refuse. No automatic cleanup, retry, migration, admission or recovery
write is provided. A capture is not a recoverable backup.

## Evidence And Meaning

The adapter records source and interpreter identities once at admission and at
closure, complete PRE/FINAL state, one request result, native/launcher closure,
comparison and timing in the private run directory. SQLite uses a read-only
connection, `query_only` and one read transaction. Schema and complete column
metadata are retained; all cells have typed representations and complete row
multisets retain duplicate counts. Campaign files have byte lengths and hashes;
empty directories are retained. Raw SQLite bytes and repeated file observations
must remain stable during each capture. Captures require a quiet owner and do
not create a cross-filesystem atomic snapshot or detect every hostile race.

`compare_states` defaults to exact no-change. There is no generic ignore list or
permission to omit tables, rows, files or incidental writes. Raw data remains in
the isolated corpus; hashed evidence is also private and stays out of Git.

The worker makes one ordinary Flask WSGI test-client GET, without a listener,
credentials, session substitution, access bypass or product monkeypatch. Health
routes already exclude automatic publication/deletion recovery. Readiness must
return 200 with all three stock checks OK and no cookie. Full startup-to-final
capture still detects unexpected durable effects. No timing claim about a
character page or production follows.

The launched process records its actual PID while waiting for the parent's
nonce-bound handshake. On Windows, the parent opens a minimal-rights live native
handle, separately retains any Python forwarder exit and requires both normal
exits. A timeout is UNKNOWN. The helper never kills a process or repeats a read.
Inspect the recorded owned PIDs and retained stderr before any new disposition;
do not call UNKNOWN closure a successful cleanup. Output JSON may be partial
after an interruption; a missing/malformed artifact supplies no acceptance.

## Timing And Review

`outcome.json` distinguishes source admission, complete captures, process startup,
worker execution/closure and final comparison. The worker separately records app
construction and `/readyz`. Its intervals are nested inside the parent's worker
interval: do not add them to it. The reusable summary reports interval union,
overlap and unattributed wall time, never exclusive CPU or saved minutes.

Record preparation-start and independent verdict UTC in the existing program
record to measure preparation-to-verdict. Runner observation is not independent
acceptance. Keep source, input and reviewer identities bound to the exact
candidate; proposed or historical guidance does not authorize another operation.

Focused disposable nonprivate checks can resolve capture, duplicate/type,
incomplete evidence, timing overlap or child-lifetime uncertainties. Retired
automated suites remain unavailable. Review the complete adapter/capture/process/
comparison path independently under [Proportionate Delivery](agent-operating-model.md#proportionate-delivery).
Future authenticated or mutation adapters need their own exact effects, normal
authentication/currentness, preservation and independent review scope.
