# Post-application vendor price monitoring (PR23 / DEV12)

PR23 DOES NOT AUTOMATICALLY RESTORE OR CHANGE VENDOR PRICES.

Monitoring reads a committed PR22 execution and its exact native supplierinfo ID.
It records today's operational values separately from the immutable original
approval, plan, before/after evidence and original post-write verification.
It never calls the application gateway or creates, updates or deletes a price.
POs, RFQs, sales, customer pricelists, stock, valuation, accounting and currency
rates are outside its write scope. No vendor/customer messages are generated.

The existing repository remains Odoo 20.0 Community. Official release/build pages
identified 20 as stable at development start; no core upgrade was performed.

## Evidence and comparison

`vendor.price.revision.application.monitor.run`, `.check`, `.incident`, `.event`
and `.correction` reuse the existing immutable source/read/export guard. The
application namespace also preserves PR22's source-watch contract: subsequent
monitoring observations do not invalidate the original execution source hash.
Public evidence create/write/unlink/copy and guessed context capability flags are
denied. Checks retain source references, expected/current fingerprints, exact
differences, selection contexts, last ORM writer/time, and observation time.

Historical validation checks the committed receipt's contract and fingerprints,
authorization payload, company, plan, source identities and exact line ledger.
It does not reconstruct the original event using today's editable price. Present
approval expiry or changed financial source does not retroactively undo a real
committed application. Invalid historical evidence is blocked, never passed.

The material contract is the PR22 set: price, discount, currency, MOQ, UoM, validity
dates, vendor, exact product/template/company, sequence, delay, vendor product code
and name. Numeric values compare persisted decimal representations. Odoo20 price
has `min_display_digits`, not a fixed storage-rounding tolerance; display rounding
and today's FX rates cannot hide a stored change. Price differences carry their
currency/UoM in the structured expected/observed terms. A monetary difference is
omitted if either unit or currency changes. No affected demand or realized loss is
invented and no financial simulator is rebuilt by monitoring.

The frozen PR21 target-unit definition is also compared with its current factor,
relative definition, hierarchy and active status. Keeping the same UoM ID while
changing its conversion factor is not a clean price observation. Cosmetic unit
name changes alone do not create commercial drift. Frozen product identity,
company, active and purchase-eligible scope is checked separately from the native
supplierinfo fields. A changed physical unit basis suppresses a misleading
unit-price difference.

Existence is resolved for the original ID with inactive records included. Model
read permission is checked first. A real absent ID is `TARGET_NOT_FOUND_VERIFIED`;
permission failures are `TARGET_INACCESSIBLE` / BLOCKED, not deletion. Current
foreign-company costs are never copied into an originating company's check.
Shared-scope expansion is an anomaly. This installed Community supplierinfo model
has no `active` field. The optional active-field branch records archive drift
where the installed schema supports it; this baseline cannot archive a native
supplierinfo. Product/vendor archiving and complete native rule-event history
are not reconstructed from access-log fields.

## Successors, date context and selection

A later committed execution can replace the expectation for the same exact target
and compatible vendor, product, company, tier, currency, unit and validity scope.
It must independently pass immutable historical source validation. An explicit
PR22 approved old-rule date-boundary closure is handled separately. Incompatible
or incomplete later events require review. A note claiming later approval is not
authority. Historical applied values remain retained when a legitimate successor
becomes the current baseline; the monitor never silently substitutes a similarly
named native row for a missing original ID.

Future-dated rules are evaluated at their recorded reference dates and can be
intact before activation. Expired intact rules can be historical only. A current
date test is distinct from reconstructing configuration that existed in the past.

The monitor compares PR22's supported selector schema/implementation signature
with the installed selector, then uses native `_select_seller` in exact company,
vendor, variant, quantity and purchase UoM contexts: at, below and above MOQ,
before/start, and end/after-end where recorded. It records chosen native IDs and
commercial terms separately from direct target differences. Exact duplicate
effective identities are detected even if the winner remains stable. Unsupported
selector signatures/contracts are BLOCKED (`SELECTION_CHECK_UNAVAILABLE`). This
does not create procurement documents or promise the price used by an actual RFQ.
Last-PO fallback is labelled as lacking a supplierinfo reference.

`write_uid` / `write_date` describe only the last ORM write when present. They
neither prove unauthorized conduct nor capture all intervening changes. Today's
native selector at a historical reference date is not a complete historical
reconstruction. Actual confirmed PO prices remain independent recorded terms.

## Incidents and corrective planning

Codes distinguish price, discount, currency, unit, MOQ, validity dates, vendor,
product, company, metadata, missing/archived target, selection, duplicate identity,
source integrity, access and unverified successor linkage. Company/vendor/product
scope and historical evidence failures are CRITICAL; active commercial drift is
HIGH; metadata/unsupported selector findings are WARNING. These are operational
review priorities, not arbitrary monetary exposure thresholds.

An incident's unique key binds company, current effective execution line and baseline
fingerprint and anomaly code. Repeated identical findings update the latest
observation without changing the original first detection. Changed values retain
each immutable check and append review history. Every check remains an audit
observation. No check is erased when a later check becomes clean.

Historical checks remain linked to their original application. Once a verified
successor supplies the current expectation, old and current observations share
one current incident key. This prevents one external edit creating a separate
active case for every superseded event. Prior closed/resolved episodes retain
their evidence and can be revalidated explicitly under the correct current basis.

The detecting manager initially owns the incident. Assignment requires an active
internal company-authorized Purchase/Finance Manager with access to the exact
source. Assignment never grants source/cost or native write permissions. All
authorized source managers can investigate, request evidence, revalidate, propose
a correction, or reopen. Auditors/directors are read-only. Public, portal and
sales-only users have no monitoring grant. Cost, warehouse and customer-order
source rules are inherited from the execution's protected approval scope.

Review reasons and retained evidence references are mandatory. Verified closure
requires a latest clean revalidation and performs another fresh current check in
the closure transaction. Comments or a correction proposal alone cannot close a
live anomaly. A recurring anomaly reopens a verified-closed case and retains its
earlier resolution. Documented-exception closure is deliberately unsupported: the
implemented policy grants no waiver authority to silently accept critical drift.

Correction proposals are immutable, hypothetical records. Without established
current commercial terms their status is EVIDENCE_REQUIRED and no historical price
is automatically selected. Explicit proposed terms require fresh business review,
new approval, a new PR21 plan and separate PR22 execution. There is no correction
application method, restore action or self-approval in this workstream.

## Manual, scheduled and concurrent processing

The execution form starts a bounded exact-execution observation. At most 100 lines
are admitted; the line cursor and `has_more` disclose remaining work. An explicit
after-line window can resume the same execution. A coherent repeatable-read
transaction snapshot supplies each observation; a later external commit requires
a subsequent check. PASS is an observation at that snapshot, not a lifetime
guarantee. Database conflicts and interruptions roll back the atomic chunk, so a
fresh retry cannot leave fabricated success or half-written incidents.

The optional `.monitor.policy` is owner/company scoped, disabled by default, with
1–100 line batches and 1–168 hour configured frequency. The shipped `ir.cron` is
also inactive. A deployment must explicitly configure its scheduler user to the
same already authorized manager and activate the required schedule. Cron performs
no sudo or user impersonation. It sees only that original user's selected company
and authorized source records. It is not an audit of inaccessible company data.

The deterministic execution-line ID cursor advances only after persisted checks;
each complete cycle resets to revalidate old targets, not merely new write dates.
A 20-second cooperative budget stops between observations and exposes partial
coverage; one indivisible native selector/source validation may exceed it. A
company batch can split an execution across pages. A unique schedule plus row
locking protects progress. A nonblocking execution advisory lock rejects overlap,
while a unique incident key and normal versioned ORM writes protect stale
snapshots/reviews. Retry uses a fresh transaction; no business method commits.

No automatic activities or external messages are emitted in this implementation;
there is consequently no recurring notification spam. Managers review the
company-scoped incident register. Optional escalation/notification integration
requires a later explicit policy and confidentiality review.

Candidate reads and historical successor discovery are bounded and cached per
chunk. No import attachments or entire financial analyses are reread per check.
Native supplier selection remains authoritative; dense overlapping tier sets can
be expensive. Benchmark coverage, times and limitations belong in the PR23 test
report. Unmeasured throughput or incomplete pages must not be called verified
production capacity.

## Retention and PR24 handoff

Source/approval/plan/execution remain the original history, with separate immutable
monitoring checks and incident review/correction references. Source drill-down
rechecks access. Additional attachments to observations are prohibited; protected
original source evidence references remain available. Existing export boundary
guards and mandatory company/source rules apply to reads, search/grouping and
exports. Raw confidential values are not logged on failure.

PR24 may consume authorized observations, policy versions, current integrity
basis, successor links, incident states, recurrence and resolution history. It
must reconcile summaries with authorized detail and disclose partial/blocked
coverage, unit/currency basis and financial confidence. Audit exports, management
analytics, exception governance, notification policy, retention/archive policy,
browser UAT and release-level integration remain separate future work. No PR24
dashboard or compliance export suite is implemented by PR23.
