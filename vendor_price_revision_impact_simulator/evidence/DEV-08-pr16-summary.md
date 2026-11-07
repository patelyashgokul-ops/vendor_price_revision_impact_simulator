# APP06 PR16 / DEV08 - implementation, testing and PR17 handoff

## A - Environment and prerequisite audit

Odoo20.0 Community FINAL, Python3.14.6, PostgreSQL18.4, Windows. Addon
vendor_price_revision_impact_simulator. Local release source, exact90-file PR15
ledger and retained PR00-15 PASS evidence verified before edits; see
pr16-predevelopment-audit.json. Official [Community builds](https://nightly.odoo.com/)
confirm20 stable. Existing major preserved; no Enterprise dependencies or migration.
All database verification uses newly created explicitly allowlisted synthetic
fixtures on an owned disposable loopback55447 cluster, no production data/credentials.

## B - Independent controls implemented

Immutable reconciliation.run/check/exception/review models retain named controls,
source/version references, exact/categorical evidence, typed numeric values,
difference, currency/UoM-derived tolerances, status/severity and coverage metrics.
One current-profitability getter checks native source freshness and shared locks;
independent equations additionally inspect PR08-15 stored evidence. No repeated
pipeline execution per check or upstream publisher. Expected profit/risk calculations
do not call upstream profitability/risk helpers.

Checks cover original file SHA256/size, revision/row/version/variant lineage,
physical/reserved/free stock, unique physical/source receipts, PO supplier remainder,
ordered/delivered/outstanding demand, allocation sums/owners/capacities, exact cost
entry/segment coverage, unchanged stock/protected PO cost, old/new procurement
tier/date/FX, PR14 signed line extensions/totals/decomposition, PR11 revenue/FX,
PR15 gross profits/margins/erosion/relative ratios, risk thresholds/outcomes/reasons,
order/product/customer/company amount-ratio groups and conditional scenario isolation.

PASS/FAIL/BLOCKED/NOT_APPLICABLE/NOT_RUN/STALE remain distinct. A critical required
FAIL blocks readiness; stale/missing/not-run evidence is not-ready. Unknown cost or
revenue is never zero, incremental-only cost does not establish complete profit.
No eligible demand is explicit, not100 percent. Completeness metrics preserve
numerator/denominator/scope; quantity coverage is grouped by product/UoM and is never
called monetary confidence. Partial complete lines do not make an entire scope ready.

Existing governed PR04 policy gains a readiness-basis dimension: strict_verified
default versus explicit documented_projection for complete projected review. This
uses existing dated configuration ownership/version/publication/audit. Even permitted
projection review retains scenario/estimate confidence and grants no approval or
application. Every failed/blocked/stale control has an actionable exception; role
routing/owner assignment and append-only evidence cannot modify checks/readiness.
Closure requires an actual matching PASS in a later current same-scenario run.
Old failures persist and later recurrence creates a new open exception.

Runs are immutable, versioned, idempotent and source-fingerprinted. Publication
savepoints are atomic; existing company/batch serialization plus native shared
source locks protect concurrent collection and policy/source changes. No business
commits, sudo projection, source repair or native write actions.

## C - Actual relevant files

- __manifest__.py
- models/__init__.py
- models/reconciliation.py
- models/reconciliation_controls.py
- security/reconciliation_security.xml
- tests/__init__.py
- tests/test_profitability.py
- tests/test_reconciliation.py
- views/reconciliation_views.xml

docs/FINANCIAL_RECONCILIATION.md documents the contract. TESTING_SETUP.md,
TEST_REPORT.json and DEVELOPMENT_PROGRESS.md retain reproducible setup/status.
evidence/pr16-* retains the exact PR15 archive, cold capture, real logs, probes,
source ledger and final static evidence. Earlier business implementation is unchanged.
The sole prior-test change strengthens atomicity to preserve every existing record
value and reject any leaked fixture result, instead of assuming empty tables.
All other earlier tests are unchanged. Final cold-install selection covers the
full numerical reference, review wizard and module foundation; all PR16 cases
execute in the final-source upgrade milestone. The earlier complete50-test fresh
PASS remains its own historical source result, not a fifty-test final UI claim.

## D - Executed controlled reference

| Item | Actual synthetic reference |
|---|---:|
| Confirmed outstanding demand | 200 units |
| Stock / protected incoming / new procurement |60 /40 /100 units |
| Revenue | INR28,000 |
| Baseline / revised cost | INR20,000 /21,500 |
| Signed incremental cost | INR+1,500 |
| Baseline / revised projected profit | INR8,000 /6,500 |
| Signed profit change / reduction | INR-1,500 /+1,500 |
| Margins |28.57142857% /23.21428571% |
| Erosion |5.35714286 percentage points |
| Reconciliation |All required controls PASS under documented_projection policy |
| Readiness |ready_for_financial_review; never approved/signed off/applied |

The fixture retains estimated stock/scenario procurement basis. Under the default
strict_verified policy the same projected cost evidence is NOT_READY. Numeric
consistency and explicit projection review never certify actual accounting costs.

## E - Actual exception references

Controlled corruption tests retain220 allocated against200 demand (difference20),
duplicate physical quant identity, protected40 revised at115 instead of100, incorrect
sales revenue30000 instead of28000, changed product/aggregate/risk and exceeded supply
capacity. Definite integrity failures are BLOCKED, never balanced/repaired in PR16.
Missing FIFO keeps known incremental1500 but full cost/profit/margin unavailable.
Missing company FX and unverified PO protection are NOT_READY without1:1 FX or
invented prices. Incorrect additive quotation provenance is blocked; alternatives
require their exact confirmed baseline and compatible source scenario.

Review notes and owner assignment never produce PASS. Tests verify reason/evidence,
company-safe assignment, duplicate review idempotence, no arbitrary waiver,
closure only after current matching PASS, retained old failure and new recurrence.

## F - Completeness and current readiness

Reference source/demand/cost/revenue/margin scope is complete: source disposition1/1,
resolved demand1/1, known cost entries3/3, known revenue1/1, margin lines1/1.
All 212 controls PASS;0 failed/blocked controls and0 critical/high
exceptions under its explicit projection policy. Strict-basis and unknown-input fixtures
preserve blocked controls/high exceptions and not-ready status. Counts and all
coverage numerators/denominators are in each frozen run; no opaque blended score.
No-demand percentages stay null. Historical stored readiness is not current authority:
source changes set current_readiness=not_ready and require current getters/revalidation.
Corrected sources generate a new run; old checks/exceptions/readiness remain audit
history. A current result is evidence for future review, not actual management sign-off.

## G - Security

Only scoped Finance initiates runs. All headers/checks/exceptions/reviews require
selected active company, cost/supply/demand warehouse grants, customer-commercial
grant and native customer-order rights. Raw supplier costs, customer terms and derived
margin/check evidence share strict confidentiality. Sales-only/Purchase-only have
no automatic disclosure. Auditors read-only, portal/public denied. Direct ORM,
export/group, foreign selected company, forged write/context and revoked grant
checks run. Review assignments grant no extra source access; original attachments
remain protected by the established intake boundary. No new sudo disclosure.

## H - Actual tests and evidence

| Gate | Actual final-source result | Evidence |
|---|---|---|
| FRESH | PASS: 6 tests | evidence/pr16-fresh-install-20261031T010609+0000_milestone.log |
| HELPERS_VERIFY | PASS: 14 tests | evidence/pr16-helpers_verify-update-20261031T010919+0000_quick.log |
| TARGETED | PASS: 33 tests | evidence/pr16-targeted-update-20261031T010958+0000_targeted.log |
| UPGRADE | PASS: 60 tests | evidence/pr16-upgrade_verify-update-20261029T143617+0000_milestone.log |
| UPGRADE-PRESERVATION | PASS: 1 probe groups | evidence/pr16-upgrade-preservation-20261031T010129Z.log |
| CONCURRENCY | PASS: 9 probe groups | evidence/pr16-concurrency-20261031T010259Z.log |
| OPERATIONAL-SAFETY | PASS: 1 probe groups | evidence/pr16-operational-safety-20261031T010549Z.log |

46 new tests. Prior failures and interrupted attempts remain history:

- FAIL: 14 passed, 31 failed; evidence/pr16-fresh-install-20261029T131921+0000_milestone.log
- FAIL: 0 passed, 1 failed; evidence/pr16-smoke-update-20261029T132830+0000_targeted.log
- FAIL: 39 passed, 10 failed; evidence/pr16-allocation-update-20261029T133120+0000_targeted.log
- FAIL: 49 passed, 1 failed; evidence/pr16-fresh-install-20261029T134239+0000_milestone.log
- FAIL: 0 passed, 1 failed; evidence/pr16-smoke-update-20261029T135335+0000_targeted.log
- FAIL: 347 passed, 1 failed; evidence/pr16-upgrade-update-20261029T141656+0000_milestone.log
- FAIL: no completed test count; probe/runtime details retained in log; evidence/pr16-upgrade-preservation-20261031T010043Z.log
- FAIL: no completed test count; probe/runtime details retained in log; evidence/pr16-operational-safety-20261031T010342Z.log
- FAIL: no completed test count; probe/runtime details retained in log; evidence/pr16-operational-safety-20261031T010450Z.log

A resumed preservation probe initially compared a live calculated commercial status
against a fixture created two days earlier. Every stored-value comparison passed;
the original-as-of calculated assertion was then evaluated using the date recorded
in its retained commercial snapshot and passed. No application rule or stored data
was changed. This failed probe remains in history.

Two operational probe attempts exposed a fixture boundary error: adding the
Finance role after the before-capture produced a native res.users group-change
audit mail.message. The retained diagnostic log identifies that message. All
authorization setup now precedes the before-capture; unchanged full22-model and
13-upstream comparisons pass without excluding messages or changing application code.

The broad upgrade attempt executed348 tests:347 passed and one old atomicity test
assumed empty margin tables despite deliberately retained PR15 data. Its FAIL log
is retained, never relabeled PASS. The final-source focused upgrade follow-up
executes every PR16 test and the seed-aware PR15 snapshot class. All business code
and other tests are byte-identical to the broad attempt; only that atomicity test
now verifies all prior stored values and no leaked fixture result. Repeating all
unchanged upstream cases was unnecessary. Exact90-source PR15 archive was installed; all stored evidence/source bytes,
including real financial and margin/risk snapshots, were committed/cold-captured
before PR16 schema, then compared after actual update. Nine two-session races:
COLLECT, PRICE, RECEIPT, VALUE, PROPOSAL, SALES_PRICE, POLICY_PUBLICATION, FX, GRANT. The future-policy publication race verifies serialization
and non-invalidation of the unrelated current period; relevant policy-change
staleness is independently covered. Native22-model and upstream13-model immutability
probes PASS.100-line reconciliation measured23.115s after upstream preparation,
executing 6409 controls with0 exceptions.
Other workloads/peak memory NOT_MEASURED; manual browser UAT NOT_RUN. No statutory
GL audit, final release FULL or PR17 execution claim.

## I - Business safety

No supplier/customer price application, SO/PO change, stock reservation/movement,
valuation modification, journal/bill posting, actual management approval or
sign-off. PR16 creates only authorized analytical checks/runs/exceptions/reviews.
Native writes in probes prepare synthetic fixtures or controlled competing changes.
Disposable runtime removed after confirmed shutdown. All source services and prior
business/security tests remain unchanged except the stronger seed-aware atomicity
assertions described in section H.

## J - Progress and limitations

PR16 VERIFIED for the documented independent projected financial controls and review
readiness. Final 95-source ledger SHA256 a5dcea405b6f3406ece4fea569b5decdb74e3b4008bef2335facaaf7d8d71eb1. TEST_REPORT.json and
DEVELOPMENT_PROGRESS.md updated with real evidence. Unsupported upstream warehouse/
lot FIFO lineage, future landed components, unallocated discounts/FX, uncertain PO
amendments and historical source limitations remain incomplete. Existing current
getters/native semantics are retained, not reimplemented as a GL audit. Required
controls cannot be waived. Larger stress/memory and browser UAT remain unverified.
PR17 NOT_STARTED.

## K - PR17 handoff

Use only current get_current_reconciliation in an authorized fresh transaction.
Retain exact PR08-15 snapshot IDs/versions/fingerprints, original source hash,
normalized eligible quantities, protected PO/stock bases, procurement tiers, dates,
UoM/currency/FX methodology, current customer revenue, baseline/revised costs,
profit/margin/risk, confidence and all check evidence, required statuses, coverage
numerators/denominators and unresolved exceptions. A future what-if case must clone
bounded assumptions into new scenario evidence with a common confirmed baseline;
never mutate immutable baseline sources or add alternative scenario totals.
Readiness is not approval or price authority. Preserve company/customer/cost
confidentiality, no double-counting and missing-data invariants. Future negotiation,
repricing/sign-off/approval/application require separate governed phases.
STOP after PR16; PR17 remains NOT_STARTED.
