# Incident Diagnostics

Status: runtime contract and operator procedure

## Stream and privacy boundary

`PLAYER_WIKI_INCIDENT_DIAGNOSTICS_ENABLED` defaults on and can be set to `false`
independently of the older request trail and live timing switches. Events use
the existing application logger/stdout as one `incident_event_v1` JSON line.
It emits at WARNING so the event is available at the normal production logger
threshold without enabling unrelated INFO logs. WARNING here is a transport
level, not a claim that every recorded access or request is faulty.
No new storage or retention service exists. Confirm the hosting platform's log
availability and retention before an incident; absence of a line is not proof
that an action did not happen.

The allowlisted schema contains `schema`, `event`, random request-local
`request_id`, static `endpoint_category` and `operation`, bounded `method`,
integer `duration_ms`, database query/write/commit/rollback counts, and,
when relevant, numeric `status`, access `decision`, `reason`, `scope`, `role`,
`visibility`, or aggregate recovery counts. The optional
`X-Incident-Request-ID` response header supports correlation. Repeated events
for one request share the same ID. Counts are request-scoped instrumentation,
not a transaction receipt.

Generic `request_outcome` records contain HTTP status, timing, and database
counters without a `decision`. They show an observed response, not whether a
write happened, was refused, rolled back, or is safe to retry. Access decisions
and named operation outcomes have their own event-specific meanings.

No event includes raw URL/path/query, request or response content, headers or
tokens, IP, account/campaign/character/page identifiers or slugs, filesystem
path, dynamic operation ID/digest, exception message, or audit metadata.
Endpoint categories and decision fields are fixed enums; numeric fields are
clamped. The logger is best effort, so its failure must never change an access
decision or write result. Other older log streams may have separate privacy
properties; use only `incident_event_v1` as this contract's event source.

Example with fabricated correlation only:

```text
incident_event_v1 {"db_commit_count":0,"db_query_count":0,"db_rollback_count":0,"db_write_count":0,"duration_ms":1,"endpoint_category":"api","event":"access_decision","method":"POST","operation":"http_request","reason":"authentication_required","request_id":"0123456789abcdef01234567","scope":"content","role":"anonymous","decision":"deny","schema":"incident_event_v1"}
```

## Incident drill

This procedure is for a concrete incident or uncertainty. It is not a routine
candidate acceptance drill; candidate acceptance follows the independent
precommit adversarial review in [Repo Guardrails](workflows/repo-guardrails.md).

1. Record the symptom, time window, environment, and authorized scope outside
   tracked history. Verify that the stream is enabled; a live configuration
   change or deploy needs its separate operator approval.
2. Use a disposable local database and content root for reproduction. Send an
   anonymous browser access, an API access, a hidden resource read, an allowed
   read, one refused mutation, and one authorized mutation only against this
   disposable environment. Exercise wiki reconciliation and character apply
   only when a disposable case can be safely induced.
3. Take `X-Incident-Request-ID` from the response and search application logs
   for the exact ID. Group `access_decision`, `request_start`,
   `request_outcome`/`request_exception`, and named `operation_outcome`
   records. Compare observational HTTP status, duration, and DB counters with
   event-specific access and operation decisions. Do not infer a write outcome
   from the generic response record or copy raw production logs into tracked
   files.
4. For a possible interrupted file publication, distinguish `confirmed`,
   `pending`, `refused`, and `uncertain`; inspect the existing read-only
   reconciliation procedure before any repair. Both 2xx and >=400 responses
   can coexist with side effects. Inspect named operation and data-level
   evidence before any retry or repair; escalate missing or conflicting
   evidence rather than inferring success, rollback, or retry safety.
5. Redact and retain only the minimum incident evidence under approved local
   storage. Document any missing lines, disabled logging, sampling or retention
   gaps, and scope that was not reproduced. Seek explicit approval before any
   deploy, live write, credential, recovery, or retention change.

Diagnostics narrow hypotheses and support correlation. They cannot prove
correctness, establish the absence of silent faults, or replace data-level
inspection when a write's outcome is uncertain.
