# Independent financial reconciliation and review readiness - PR16 / DEV08

## Purpose and boundaries

PR16 checks projected affected-demand simulation across PR08-15. It is an
analytical control run, not a general-ledger/statutory audit, management approval,
financial sign-off, supplier acceptance or application authority. It never repairs
native business data or upstream analytical evidence. Ready for financial review
means only that the explicitly scoped required controls passed under the dated
company readiness-basis policy. PR17 and later actions are outside this phase.

## Exact source contract

Select one exact PR15 margin snapshot. Its PR14 financial, PR13 cost, PR12 purchase,
PR11 sales, PR10 allocation and PR09 supply snapshots must have matching company,
revision, allocation, warehouse, sales-line and scenario identities. A PR12 purchase
snapshot is optional only when the selected allocation has no incoming purchase
contribution; its absence in an all-stock case is not fabricated missing evidence. PR08 current
commercial/product/structural results and original source bytes are retained.
Every control has a stable code/source identity, category, required flag, status,
severity, unit, exact currency/UoM fields, typed numeric expected/observed/difference/tolerance and exact JSON
evidence. numeric_known distinguishes unavailable numeric values from actual zero;
category and identity evidence are JSON, not fabricated monetary amounts. Unknown
numeric cells are hidden in review views; canonical evidence stays null.

The reconciler calls the existing current-profitability getter once per run to
verify native sources/current policies and retain existing shared locks. It does
not rebuild pipelines per individual check or publish upstream values. In addition,
it independently calculates equations, checks coverage and unique identities and
compares stored PR15 risk against independent threshold logic. It does not call the
upstream profit or risk calculation helper. A hash or upstream VERIFIED label alone
is insufficient. Source fingerprints, snapshots, policy versions and source bytes
are retained. Serialization/database/access failures propagate; anticipated stale
source validation becomes a STALE control with not-ready evidence.

## Control families

Source integrity verifies original SHA256/size, revision linkage, extracted row
coverage, current validation, per-row disposition and exact commercial variant.
Explicit exclusions require retained correction history. Missing/unverified source
rows block readiness instead of silently shrinking scope. The file is not reparsed.

Odoo20 uses the native Product Unit decimal precision for UoM comparison; no
removed uom.rounding field is assumed. Quantity controls check physical = reserved + unreserved, eligible free <=
unreserved, native quant identity uniqueness, supplier boundary receipt identities,
PO ordered-received-cancelled open balance and supplier remainder uniqueness. Internal
putaway is not an extra external receipt. PR09/10 native-source freshness verifies
movement graph semantics; independent quantities verify the resulting buckets.
Outstanding demand = ordered-delivered under the selected PR10 supported basis;
all allocation entries sum to the same outstanding quantity. Unresolved quantities
remain explicit. Each capacity's allocated and remaining values reconcile to initial
capacity, summed consumption cannot exceed it, and product/warehouse/linked demand
owner dimensions must match. No balancing allocation or inventory adjustment exists.

Cost controls cover exact PR10 entries once, sum all segments to entry quantity,
retain unique source segment identity and verify quantity*unit cost extensions.
Protected incoming requires current exact PR12 confirmed independent protection;
unknown/disputed/pending amendments remain blocked. Historical stock/protected cost
must remain unchanged in both PR14 scenarios. Native FIFO pools cannot establish
warehouse/lot lineage and no replacement/standard cost is substituted for unknown
FIFO. Existing capitalized charges are not added again: PR14 cost must equal the
selected PR13 source unit and each extension, not an extra landed component.

Procurement controls compare PR13/14 exact commercial result, product/UoM, explicit
timing, eligible maximum MOQ tier, old normalized tier*old FX and new normalized
proposal*new FX. Missing dates/rates remain blocked. Common-rate and date-specific
methods preserve PR14 decomposition; supplier-price plus FX effects must reconcile
where the upstream source currencies support that split. No 1:1 FX fallback exists.

Financial controls check quantity*baseline/revised unit, per-line signed delta,
line-to-total sums and revised-baseline=incremental. An unchanged unknown stock delta
may be known independently; total stock cost/profit remains unavailable. Missing
amounts never become zero. No artificial balancing amount is created.

Revenue controls independently compare PR11 net unit*outstanding quantity using
source-currency rounding, then PR11 FX conversion with company rounding, and exact
PR15 source revenue. PR11 native tax/discount service remains the source authority;
current pricelists never replace order terms. Unallocated global discounts remain
incomplete; freight/service/full-order totals are not silently mixed into affected
product scope. Partially delivered quantities remain excluded through current PR10.

Profit/margin controls independently calculate revenue-cost, profit/positive revenue,
signed profit change, positive-oriented reduction, percentage-point erosion and
valid relative ratios. Zero/nonpositive denominators are blocked for percentages,
not falsely reported as 0%. Negative profit and margins below-100% remain valid.
Exact sales-line costs consume each financial contribution once. Order/product/
source-customer/company aggregates preserve demand class, exact source group counts,
ratio-of-sums margins and unique grouping keys. Alternative quotation totals cannot
be additive; exact confirmed baseline and conditional profit difference are checked.

Independent risk checks use PR04 minimum/target inclusive boundaries, erosion pp,
company-currency bands, negative-profit rule, precedence, baseline versus revised
risk, revision effect and all reason codes. Stored policy IDs/thresholds must match
the governed source definitions. Scenario/estimate confidence is never upgraded to
verified actual procurement or accounting income.

## Status, completeness and readiness

PASS means executed criteria met; FAIL means a definite violation; BLOCKED means
required evidence is unavailable; STALE means sources no longer match; NOT_RUN is
not executed; NOT_APPLICABLE is genuinely excluded under documented upstream scope.
Blocked/not-run/stale controls are never counted as pass. Named checks and structured
exceptions remain visible, including partial results. A critical required FAIL
blocks readiness. Stale required evidence is not-ready. Any required blocked/not-run
control is not-ready. No eligible demand is explicitly no_eligible_demand, not100%.
Only all required applicable PASS controls with eligible complete demand can be
fully_reconciled and ready_for_financial_review.

Existing dated PR04 configuration is the sole readiness policy authority. The added
reconciliation_basis_policy defaults strict_verified: estimated/scenario cost cannot
be ready. Explicit documented_projection permits complete numerically reconciled
projected bases for financial review only; it does not accept unknown evidence or
turn projected estimates into verified actual costs. It uses existing Configuration
Administrator mutation/publication/audit/version rules. Both source confidence and
selected policy remain visible in frozen provenance. No waivers can bypass required
controls or achieve readiness.

Coverage metrics retain numerator, denominator, exact scope and null percentage on
zero denominator. Counts cover all source rows, resolved demand, known-cost entries,
known-revenue lines, numerically complete margin lines and executed check passes.
Quantity cost coverage is grouped by exact product/UoM; heterogeneous quantities
are never summed. Quantity coverage is not verified monetary exposure. Required
excluded rows retain explicit reasons and are not silently lost from reporting.

## Exception register and controlled review

Every non-pass required control creates one immutable exception with code/source,
severity, check evidence, routed role and recommended correction/revalidation action.
No monetary amount is invented for unknown exposure. Mapping/pricing/PO issues route
to Purchase Manager, revenue to Sales Manager, remaining controls to Finance. An
explicit active internal owner must belong to the company; assignment never grants
source rights or triggers unrestricted notifications.

Scoped Finance/Purchase/Sales managers may append assignment, in_review,
revalidation_required or reopened events with reason and traceable evidence. Notes
never alter checks/readiness. closed_verified requires an actual matching PASS in a
later current run of the same batch/scenario; mere notes or old results cannot
close it. Stable semantic check keys survive regenerated upstream IDs. Old exceptions
remain historical; a later recurrence creates a new open exception with full prior
history retained. Nonblocking waiver is not enabled in this implementation.

Public create/write/unlink/copy cannot forge evidence; review history is append-only.
Repeated unchanged review action/run reuses existing evidence. Atomic publication
savepoint prevents partial success headers/checks on failure; safe retry is supported.
Company/batch serialization prevents concurrent duplicates. Existing native-source
shared locks and fresh getters prevent mixing source versions; retry serialization
failures in a fresh transaction. No business manual commits are introduced.

## Security, currentness and review UI

Initiating reconciliation requires scoped Finance Manager. Access to all records
requires selected company, active user, every cost/supply/demand warehouse grant,
customer-commercial grant and native access to included customer orders. Raw costs,
customer terms and derived profit/risk/check evidence share the same confidentiality.
Purchase-only/Sales-only receive no automatic financial disclosure; auditors are
read-only. Global parent-scope rules protect header, checks, exceptions and review
events including direct ORM/group/export/related data. Original attachments retain
existing PR05 protected-source controls; no public attachment copies are created.

Financial Analysis provides run/check/exception review lists and forms, paginated
20/60 records. Raw stored readiness is historical. Current-source check computes
live freshness/current_readiness and refuses stale evidence; it never grants approval.
List pages do not automatically rebuild all historical pipelines. Source mutation,
policy changes, receipt/delivery/FX/price/protection changes invalidate currentness;
unchanged source/policy reruns reuse one result. Access revocation also withholds
current readiness. Correct through standard authorized source processes, revalidate
upstream snapshots and then rerun, never via PR16 operational repair shortcuts.

## Verification and limitations

Actual logs/counts belong in TEST_REPORT.json and evidence/DEV-08-pr16-summary.md.
This document is not test evidence. Tests cover independent arithmetic, corrupted
quantities/prices/revenue/identities, missing inputs, duplicate capacity/source use,
readiness, controlled exception closure, scope isolation, atomicity and staleness.
Milestone regression reuses PR08-15 relevant financial/security tests. Actual PR15
archive install/cold capture/update preserves original supplier files and all
commercial/supply/allocation/sales/purchase/cost/financial/margin/risk evidence.
Real concurrent sessions and native/upstream before/after probes verify safety.
Only executed performance figures are reported; larger workloads/memory/manual UAT
remain NOT_MEASURED/NOT_RUN unless independently measured.

The source control engine is bounded to existing upstream limits and100000 checks
per run. It does not certify unsupported warehouse/lot FIFO lineage, future landed
charges, unallocated order discounts, uncertain PO amendments or statutory GL totals.
It checks the supported frozen quantities and native source freshness rather than
reimplementing Odoo receipt/return/tax engines. Company policy can permit documented
projection review, but never absent or conflicting evidence. No actual sign-off,
approval, pricing recommendation, negotiation optimizer or application is included.

## PR17 handoff

Consume only current authorized get_current_reconciliation results. Retain exact
PR08-15 source IDs, fingerprints/versions, eligible quantities, protected terms,
tiers/UoM/currency/FX/date assumptions, current revenue and baseline/revised cost,
profit/margin/risk, explicit confidence and coverage numerator/denominator, every
required check and unresolved exception. Clone future what-if assumptions into new
bounded scenario evidence; never mutate this baseline or native business records.
Compare alternatives against their common confirmed baseline; do not add scenario
totals. Historical readiness is not approval and cannot bypass future governance.
PR17 remains NOT_STARTED. Stop after PR16.
