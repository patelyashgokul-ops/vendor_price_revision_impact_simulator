# Transactional approved vendor price application — PR22

PR22 is the first operational APP06 pricing writer. It changes only exact approved
`product.supplierinfo` fields and creates APP06 transaction/audit records. PR23 is
not started. Verification is VERIFIED for the source-bound scope in evidence/DEV-11-pr22-summary.md; browser/FULL release tests remain NOT_RUN.

## Authority and deliberate confirmation

Approval authorizes a commercial scope; it does not grant execution permission.
The existing **Pricing Operator** role is the explicit application capability.
An operator also needs independently assigned Purchase/Finance source access,
all source warehouse/order grants, the selected authorized company and native
create/write permissions for the operations actually required. This addon adds
no native pricing ACL and uses no sudo for price discovery or mutation. A
Purchase/Finance role alone, Pricing Operator alone, Auditor, Sales-only or
portal/public identity cannot bypass these requirements.

The published company policy optionally requires an operator distinct from the
maker/requester and/or all approval actors/principals. These are explicit optional
controls, not invented universal separation rules. Policy versions remain
immutable. The new execution controls do not rewrite signed PR19–21 routing or
financial packages; execution records capture their exact published values.

The confirmation wizard shows one plan, company, vendor, approval, source/target
fingerprints, dates and operation counts. The owner must affirm that operational
Vendor Pricelist records will change. Its plan and captured fingerprint cannot be
reassigned. No generic Apply All, approval-triggered execution, activation cron,
supplier email or unattended application is introduced.

## Exact source and target scope

The service accepts only an immutable current PR21 plan. It reconstructs PR21
evidence once, including PR20 final decision/quorum/maker-checker/validity and
PR16 financial reconciliation, under execution locks. A historical READY or
APPROVED flag alone never suffices. Wrong type, expired/invalidated authority,
changed assumptions, payload, native targets, company or policy block the batch.

Operational values come from the approved original-currency price representation,
not company-currency financial cost. USD110/Box10 can become USD11/Unit with MOQ10
when that precise conversion and target unit were approved; an INR analytical
equivalent cannot replace it. Existing PR21 exact precision, tax, discount and
conditional-scenario limitations remain enforced. Missing evidence is not zero
exposure or guessed eligibility. Margin and markup, projections and realized
results, accounting cost and replacement cost remain distinct.

Identity includes exact legal vendor ID, company, variant/template relationship,
MOQ, currency, UoM and inclusive dates. Names, arbitrary first matches and caller
target IDs are not authority. Shared/company-neutral and template-wide records
cannot be overwritten for an ordinary company/variant approval. Duplicate or
conflicting targets, unsupported representations and unresolved price-selection
conflicts block. The entire approved operation set must be eligible; there is no
partial approved subset silently applied from a blocked plan.

Ordinary updates change only price and explicitly approved discount. Lead time,
sequence, vendor code/name and all identity fields remain unchanged. Creation
uses the exact approved material fields, including explicit metadata. Native
defaults or client context cannot substitute another vendor/product/company.
Only a minimal trusted context is passed to the native ORM.

## Dates and explicit close-old/create-new coverage

An optional `close_previous_id` on a draft creation intent explicitly captures
the old native row and the future date end (`new start - 1 day`) before independent
approval. It requires the same vendor, exact variant/company, currency, unit and
MOQ; it cannot silently widen or drop another quantity scope. The transition
must preserve all past periods. Both the old rule closure and new dated price
are frozen in the PR20 payload, rendered as separate immutable PR21 lines and
executed atomically. The old price and unrelated metadata stay unchanged.

If that coverage was not approved, the executor never guesses a closure. An
already safely closed old period can be preserved while creating the new rule.
An in-place identity/currency/UoM/MOQ/start-date rewrite is not inferred. The
company IANA calendar is frozen; caller timezone cannot move historical bounds.
Writing a future rule does not mean its price is active before its dates.

## Transaction and concurrency protocol

Odoo owns commit/rollback. There are no per-line commits, independent mutation
cursors, partial success loops or automatic compensating price writes.

The application lock order is company -> source batch -> approval/request identity
-> operator/group share locks -> partner hierarchy share locks -> sorted
vendor/template scope epochs -> target-UoM/ancestor share locks -> sorted exact
native target rows. The existing company/request epochs serialize policy,
approval and duplicate application changes. Native create/write/unlink methods
also use the same natural-scope barriers, including old/new identities and
parent/contact intersections. They preserve original native permissions.

Scope epochs live in an internal price-free table unique on vendor/template.
An INSERT/ON CONFLICT UPDATE creates a row version; an old Odoo Repeatable Read
snapshot must serialize/retry after a competing commit. This avoids the stale
snapshot problem of advisory locking alone and protects a not-yet-existing create
target. The barrier spans companies/variants for a template so shared/template
or hierarchy edits intersect correctly. It is not a global uniqueness constraint
on supplierinfo and does not prohibit legitimate native overlapping price rules.
There are no supplierinfo table locks. Existing financial-source share locks are
retained; long source revalidation can extend their duration.

After locking, the service invalidates native caches, checks current complete
plan evidence, authority and SoD, and builds field dictionaries on the server.
All writes, mandatory verification and ledger creation occur inside one savepoint.
A later line, create, audit or verification failure rolls back the whole batch
even when a Python caller catches the exception. The caller receives an error;
no successfully applied header or partial successful ledger remains.

## Verification and actual commit semantics

Every native result is flushed, invalidated and re-read; expected dictionaries
are never compared only with themselves. All material fields and the complete
scoped native universe must match. Actual installed-version selectors are checked
at MOQ, above/below thresholds and date boundaries, with cached repeated contexts.
Native eligibility is verified; a last-PO fallback is not called an applied rule.
Wrong company, variant, currency/unit or effective net price blocks the batch.
Outside-scope contexts retain prior behavior or another explicitly approved
operation's behavior. No representative sample is falsely presented as complete
bulk execution verification.

The immutable receipt stores the originating PostgreSQL transaction ID and the
actual verification instant. In that transaction its state is **PENDING_COMMIT**
and `executed_at` is absent. A fresh reader can see **VERIFIED** only after commit
makes the receipt and native changes visible together. The timestamp is the
verification instant becoming authoritative on commit, not a fabricated exact
database commit timestamp. Standard Odoo RPC delivers the result action only
after successful framework transaction completion.

A deferred read-only database constraint checks every recorded target's actual
material values and approval expiry/invalidation at the real commit boundary.
Thus later code cannot commit the receipt after altering a verified target or
letting its authority expire. This is a validation/atomic rollback safeguard,
not a PR23 automatic rollback workflow. Commit failure cannot leave a successful
receipt. Ordinary ORM checks still provide earlier actionable errors.

## Idempotency, audit and safe retry

The durable execution key binds company, immutable authorization and approved
payload. Database uniqueness on both key and authorization prevents a second
successful application even through another plan version. Duplicate callers
serialize and retry in fresh transactions. A committed exact execution returns
its original receipt without another native write or a new audit record.

NO_CHANGE records a verified unchanged target and does not invent earlier
historical application. ALREADY_APPLIED refers to a genuine prior receipt. After
an external edit the old approval never restores its old price; it reports a
target-changed conflict and preserves original evidence. Replay checks original
request/artifact/plan/payload hashes and APP source input/version stamps. It does
not rerun financial baselines against its own applied native mutation and does
not assert fresh approval authority or current financial profit. A changed
source stamp blocks reapplication; historical receipt reads remain available to
authorized users. New changes require new governed authority.

Receipts and lines retain exact approval, source payload, plan/version, operator,
transaction, native IDs, before/approved/observed values, all fingerprints,
currency/unit/MOQ/dates and actual selector evidence. Header and lines are immutable;
ordinary ORM create/write/delete/copy cannot forge success. Internal audit creation
also requires an opaque server capability, not a user context flag or private
method name alone. Source/company/role restrictions cover search, aggregation,
export, related records and document streams. Extra mutable execution attachments
and attachment reassignment are rejected; original supplier files remain protected.

Failed-transaction audit inserts roll back with their prices. The service raises
a controlled error and logs plan/operator identifiers without price contents. It
does not falsely claim permanent failed-attempt rows. Retrying requires current
authority, plan, targets and locks; there is no assumption of partial application.

## Business safety and PR23 boundary

There are no writes to existing RFQs/POs, SOs, customer pricelists, product standard
cost, stock/reservations, valuation, landed costs, currency rates or accounting.
Existing document onchange methods are not called to refresh prices. Application
success is an operational rule result, not realized savings or accounting profit.

PR23 may build governed historical integrity/selection monitoring, exception and
incident review, explicit recovery proposals and company-scoped audit reconciliation.
It must use the original receipt/authority, check all external edits and obtain
new approval for any compensating operation. No monitoring cron, price restoration,
historical repair, executive dashboard or automatic recovery is implemented here.

Actual test results, failure history, measured workloads and limitations will be
published in TEST_REPORT.json and evidence/DEV-11-pr22-summary.md. Browser UAT,
production capacity and untested addon combinations are not inferred from a
successful isolated test. Test databases are retained stopped; none are deleted.


### Native numeric storage at commit

The deferred verifier compares the same material values seen by original-user ORM.
Odoo reads nullable numeric columns as zero, including legacy supplierinfo discount.
Those numeric columns use zero normalization during SQL comparison; partner,
product/template, company, currency and UoM identities remain strict. Application
does not rewrite unrelated NULL metadata to zero. A targeted deferred-constraint
regression exercises an existing SQL-NULL discount, approved price UPDATE and unchanged
native discount storage; actual concurrent UPDATE commits exercise the same path.
Financial data-completeness gates remain independent of this storage comparison.


### Explicit target-unit transaction barrier

An approved target UoM can differ from the source, product base and existing vendor
units. Execution read-locks that target and all its hierarchy ancestors before the
full financial/plan reconstruction, and retains those locks through commit. Existing
commercial-source locks still protect original currency/rates, units and identities.
The dedicated two-cursor extra-Box20 factor-edit probe checks serialization before
financial reconstruction and rejection of the changed approved target on fresh retry.
Actual outcomes are recorded in the source-bound concurrency evidence, not inferred
from this design description. PR23 monitoring must include target/ancestor unit-factor
and hierarchy changes as well as native price material and selection drift.


### Measured workload limit

Final-source functional gates are VERIFIED. The actual2,000-line warm isolated
CREATE batch took3820.78 seconds (63.68 minutes) including commit; source/approval/
plan setup took5510.79 seconds (91.85 minutes). Retry took10.22 seconds. This is
a substantial measured latency limit, not qualification for interactive or
production RPC capacity. See the full five-size table and timer interpretations
in evidence/DEV-11-pr22-summary.md. Browser/UAT and FULL release remain NOT_RUN.
