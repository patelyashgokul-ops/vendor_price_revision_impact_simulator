# PR22 - Transactional approved vendor price application - VERIFIED

## A - Environment

Odoo20.0 Community, existing repository retained; Python3.14.6 and PostgreSQL18.4.
Addon `vendor_price_revision_impact_simulator`. Own loopback cluster55453 and role
`codex_vpr_pr22`; HTTP/cron/outgoing operations disabled. Applied records are synthetic
fixtures only. Fixture business date2026-10-28 is distinct from the actual November2
approval/verification wall-clock timestamps in logs; no production approval is claimed.
Exact archived PR21 source and prerequisites: `pr22-predevelopment-audit.json`.

Actual native supplierinfo identity: partner, exact variant/template, company, MOQ,
original currency/UoM and inclusive dates. Material values also include price,
discount, delay, sequence and vendor names/codes. Odoo20 selection normalizes unit
prices and returns a dictionary. Last-PO fallback is recorded separately. Quantity
precision uses Product Unit decimal precision; Odoo20 UoM has no rounding field.

## B - Implementation

Immutable PR21 plans execute only under their exact PR20 authorization. Server-side
checks require selected company, explicit pricing operator, separate Purchase/Finance
source role and native operation ACLs; validate current approval/type/expiry/
invalidation, complete financial source, exact approved payload, latest plan/readiness,
persisted hashes and native before values. Optional immutable company policy separates
operator from maker/requester and/or actual approval actors/principals.

UPDATE writes only approved price/discount or expressly approved future date closure.
CREATE preserves exact original currency/UoM/MOQ/date and company/variant scope.
NO_CHANGE verifies without a native write. Shared/template conflicts block execution.
Actual selector results at MOQ and inclusive date boundaries are retained for every
line, including actual selected IDs and explicit fallback status. Equivalent approved
net prices across eligible equal-price tiers are allowed; no exact winning-ID claim
is made when native tie-breaking selects another eligible equal-price tier.

## C - Files changed

New models: `execution.py` (gateway/immutable ledger), `execution_lock.py` (versioned
native-writer scope), `execution_commit.py` (deferred actual-commit check),
`execution_policy.py` (optional separation policy), `execution_boundary.py` (explicit
future closure/create) and `execution_ui.py` (owner confirmation/history/documents).
New resources: `security/execution_security.xml`, `views/execution_views.xml` and
`tests/test_application_execution.py`. Only five old integration files changed:
manifest, model/test imports, existing application engine and intent input. All old
test cases remain byte-identical. Full hashes: `pr22-source-ledger.json`.

## D - Reference results

| Case | Genuine fixture result |
|---|---|
| A | Approved INR100 ->109 UPDATE; exact before/after ledger |
| B | MOQ100 INR109 CREATE; MOQ1 INR115 retained; native selection checked |
| C | NO_CHANGE verified; native write/create tripwires not called |
| D | Ten-line mixed UPDATE/CREATE, failure on line10: all prices/audit roll back; retry succeeds |
| E | Same plan repeated: original receipt returned, no second native mutation |
| F | Two real simultaneous CREATE requests: one rule/receipt, serialization and read-only retry |
| G | Expired authority before application and during write aborts |
| H | Target externally100 ->105: old109 plan blocked,105 retained |
| I | Wrong-variant/field arguments denied; injected defaults/context cannot redirect target |
| J | Shared-company and template-rule conflicts block, old values retained |
| K | Future109 rule inactive early; old100 history retained; explicitly approved closure/create atomic |

The assembler checks A/B/C/E markers in final QUICK, D/G-K in upgrade MILESTONE and F in
the concurrency log below. Template and owner-confirmation cases run in MILESTONE.

## E - Atomicity and recovery

One flushing savepoint covers all native writes, behavior verification and immutable
receipt insertion. No per-line commit, rollback or application cursor. Odoo owns commit.
Sorted company/batch/request, actor/group, vendor/template, explicit target-unit/ancestor and native-row locks protect
authority and targets. Versioned vendor/template epochs intersect normal native ORM
create/write/unlink, including parent/contact/shared/template competitors. Repeatable
Read snapshots serialize after conflicting commits rather than silently reuse old data.
Unique authorization and execution keys prevent duplicate application. Existing native
supplierinfo rules receive no global uniqueness constraint.

A deferred read-only PostgreSQL constraint checks all receipt targets and authority at
actual commit. Pending receipts expose no successful applied timestamp. A fresh cursor
reads VERIFIED only after commit. Genuine late-commit corruption of ten native targets
rolled back all prices and receipt; fresh retry succeeded. Before/approved-after/observed-
after values, fingerprints, exact source, operator and all selector contexts are retained.
Repeated committed requests return the original receipt; external edits are reported
without restoring an old approved price. Rolled-back failure rows cannot be called a
durable failure audit: controlled errors and price-free plan/operator logs remain.

## F - Security

No new native ACL grants or automatic group assignments. Role and native permission
checks are independent. Original-user ORM performs price writes, without native sudo.
Metadata-only attachment inspection retains existing protected-content access. Management/
audit access requires company, warehouse/cost/demand and native Sales-document scope.
Receipt CRUD/copy/forged success and attachment reassignment are denied. Internal receipt
authorship needs an opaque Python capability, not a client context flag. Confirmation
belongs to its creator and binds exact immutable plan hash. Both optional approver
separation and positive confirmation execution passed focused tests. Negative ORM/export/
company/native-permission/context-injection cases ran in the milestone.

## G - Automated tests

All following gates use the same frozen source and real nonzero test/assertion counts.
Source changes invalidate evidence; exit status alone is insufficient. Initial failures
are preserved in TEST_REPORT.json, not overwritten. Browser/UAT and FULL release suite
are NOT_RUN; cold/RPC/production capacity is NOT_MEASURED.

| Gate | Actual passed | Evidence |
|---|---:|---|
| PR22_SEPARATION | 2 tests | evidence/pr22-separation-update-20261102T064420+0000_targeted.log |
| PR22_CONCURRENCY | 7 groups | evidence/pr22-concurrency-20261102T070412Z.log |
| PR22_FRESH | 10 tests | evidence/pr22-fresh-install-20261102T071300+0000_milestone.log |
| PR22_UPGRADE | 146 tests | evidence/pr22-upgrade-update-20261102T072711+0000_milestone.log |
| PR22_UPGRADE-PRESERVATION | 1 groups | evidence/pr22-upgrade-preservation-20261102T084013Z.log |
| PR22_OPERATIONAL-SAFETY | 5 groups | evidence/pr22-operational-safety-20261102T090104Z.log |
| PR22_COLD-REPLAY | 2 groups | evidence/pr22-cold-replay-20261102T090804Z.log |
| PR22_HELPERS_VERIFY | 10 tests | evidence/pr22-helpers_verify-update-20261102T063905+0000_quick.log |
| PR22_APPROVED-PERFORMANCE | 6 groups | evidence/pr22-approved-performance-20261102T090828Z.log |

Operational groups additionally prove only exact supplierinfo additions,21 other native
models unchanged and27 upstream models unchanged. Independent-process replay is tested.
Actual archived PR21 install/seed/cold capture precedes update; retained source bytes,
old financial/commercial/security/decision/delegation records and approved PR21 plan
are compared after upgrade. Zero automatic executions or native price changes on update.

### Measured committed application workload

| Lines | Apply+commit seconds | Setup/approval/plan seconds | Client SQL | Audit JSON bytes | Retry seconds |
|---:|---:|---:|---:|---:|---:|
| 1 | 5.1474 | 76.4029 | 1525 | 17134 | 0.6616 |
| 10 | 5.6068 | 113.4116 | 1625 | 132335 | 0.5612 |
| 100 | 31.5328 | 459.9607 | 2615 | 1285604 | 0.9742 |
| 500 | 235.7368 | 1266.8933 | 7023 | 6428361 | 2.1647 |
| 2000 | 3820.7785 | 5510.7935 | 23553 | 25733718 | 10.2173 |

Every line uses actual native ORM creates, selector verification, immutable audit and
deferred commit guard; fresh-cursor success and no-write retry are checked. Timing/RSS
and phase breakdowns are retained in performance JSON logs. The raw selection_after
timer combines before+after selector calls; only the combined value is interpreted,
and separate post-write timing is NOT_MEASURED. The validation sub-timing
measures the PR20 source gate, not every pre-write check. Scope-lock sub-timing
measures the versioned price-scope helper, not all actor/unit/native-row lock SQL. Warm registry, one variant,
flat net price and distinct MOQ tiers; no cold/RPC/multi-SKU production capacity claim.

Retained failures include: Odoo20 UoM precision API and None/False create normalization;
bad synthetic product identity; stale approver field names and fixture group-assignment
actor; strict SQL-NULL versus ORM-zero commit verification (fixed without rewriting native metadata); race scenarios with unconsumed negotiated assumptions and stale Sales visibility
after adding demand. Production financial/access controls and old tests were not relaxed.

Measured capacity limitation: 2,000-line apply+commit took **63.68 minutes** and source/approval/plan preparation **91.85 minutes**; retry took10.22 seconds. These are substantial latency limits. Functional verification does not qualify this workload for interactive or production RPC use.

## H - Business safety

Supplierinfo changes stay within exact signed operational scope. Real fixture snapshots
cover PO/RFQ, SO/customer pricing, product costs, stock/reservations/moves/packages,
valuation, accounting, FX, mail and cron, plus upstream analytical evidence. No existing
document onchange/repricing, stock operation, valuation adjustment, accounting posting,
external communication or live operation is invoked by the application service.
Synthetic operational setup is separate from application. Applied price rules do not
claim realized savings or accounting profit.

## I - Progress

PR22 VERIFIED for the documented tested scope. TEST_REPORT.json retains actual history,
source hashes, counts, logs, measured limits and failure explanations; DEVELOPMENT_PROGRESS
records the verified handoff. No current mandatory blocker for this scope. Browser/UAT
and FULL release remain NOT_RUN. Owned runtime/filestore are stopped and retained under
TESTING_POLICY.md:51; no databases deleted.

## J - PR23 handoff

Concrete synthetic reference: execution10 / plan11 / request11; native supplierinfo20 created, no prior target, one CREATE and zero UPDATE. Company11, vendor90, variant14/template13; original USD110/Box10 approved as USD11/Unit, MOQ10, effective2026-11-01 with open end. Original operator68; verification timestamp2026-11-02 09:05:11 UTC, authoritative after actual commit. Complete fingerprints, signed source and selected contexts remain in the linked JSON. Fixture business date2026-10-28; this is not a production execution.

`pr22-committed-handoff.json` contains a genuine durable synthetic execution reference,
exact approved source payload and authority, company/vendor/variant, original currency/
UoM/MOQ/dates, created/updated counts, before/after values, source/target fingerprints,
operator, actual selected rule IDs and authoritative-after-commit verification timestamp.
The timestamp records in-transaction verification, becoming authoritative on commit;
it is not claimed to be PostgreSQL's precise commit timestamp.

PR23 must retain historical receipts, compare external edits/missing targets/source and
boundary/selection and target-unit/ancestor factor drift, scope audit per company and preserve original authority.
Incident review must distinguish historical successful execution from current target
integrity. Any compensating write needs current separately approved scope and conflict
review; no blind restoration or duplicate retry. Monitoring, exception/recovery proposals,
long-term reconciliation and response controls are handoff requirements only. No cron,
automatic rollback, historical repair or recovery execution is implemented. STOP after
PR22. PR23 NOT_STARTED.

Frozen source `771c6bd7d24b99108635ef5bc747bc17c4518f895b710f211aed356f95daa01f`; 139 files and 450 static checks.
