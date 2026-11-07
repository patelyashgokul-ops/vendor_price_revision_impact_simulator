# APP06 PR15 / DEV08 - implementation, testing and PR16 handoff

## A - Environment and prerequisite audit

Odoo20.0 Community FINAL, Python3.14.6, PostgreSQL18.4, Windows. Addon
vendor_price_revision_impact_simulator. Native release source and retained PR00-14
PASS evidence checked before edits (evidence/pr15-predevelopment-audit.json).
Official [Community builds](https://nightly.odoo.com/) confirm20 stable. The existing
major is preserved. Optional Community sale_margin computes document margin from
purchase_price and document quantities; it does not represent this allocated future
vendor-revision scenario. No dependency on it/Enterprise, no native margin writes.
All runtime tests use newly created allowlisted synthetic disposable databases on
loopback55446; no production database or credentials used.

## B - Implementation

Immutable margin.snapshot/line/aggregate/risk models reuse current PR11 net sales
values and PR14 source-specific baseline/revised costs. Exact selected company,
order/line, variant, quantity/UoM, demand class, currency and allocation contribution
identity are checked. Revenue remains unchanged; no alternate price or valuation
calculation. Gross profit = revenue-cost; gross margin = profit/positive revenue.
Markup is separate and unused. Signed profit change reconciles to negative PR14
delta, reduction is baseline profit minus revised, erosion uses percentage points.
Relative reduction/decline require positive valid baselines. Decimal38 precedes
display rounding; risk uses raw values. Zero/negative revenue percentages stay null,
negative profits and margins below-100% remain visible. Missing values are not zero.

Exact sales lines are retained, with order/product.product/source-customer/company
amount-sum aggregates separated by confirmed/conditional class. Margins are ratios
of amount sums, never average percentages. Scope is affected remaining products,
not full-order margin. Unknown global adjustments remain incomplete under PR11.
Partial subset amounts are separately labeled. Conditional scenarios require the
exact current confirmed profitability baseline and expose scenario revised profit
minus confirmed revised profit only when complete; alternatives are never additive.

PR04 is the only risk authority. Existing minimum/target margin and company-currency
exposure bands are reused. Same governed margin rows now support explicit material
erosion pp and negative-profit critical settings, with existing configuration role,
audit, immutable publication and version controls. Product/category precedence is
preserved; company default is used for order/customer/company aggregate policy.
Highest known line severity remains separate from aggregate ratio risk; healthy
aggregate margins cannot hide a critical constituent. Readable source labels,
snapshot dates and stored-assessment warnings support review.
Every triggered reason retains stage, actual, threshold, policy ID and confidence.
Baseline risk is separate from revised risk and revision-induced deterioration.
Snapshots are immutable, source/policy fingerprinted, versioned and idempotent.
Current getters, company/batch serialization, shared source locks and atomic
savepoints prevent mixed publication. No business commits or sudo projections.

## C - Actual files changed

- __manifest__.py
- models/__init__.py
- models/profitability.py
- models/profitability_math.py
- models/profitability_policy.py
- security/profitability_security.xml
- tests/__init__.py
- tests/test_profitability.py
- views/profitability_views.xml

docs/PROFITABILITY_MARGIN_RISK.md documents the contract. TESTING_SETUP.md,
TEST_REPORT.json and DEVELOPMENT_PROGRESS.md contain setup, actual evidence and
status. evidence/pr15-* contains drivers, exact baseline archive/checksum, probes,
source ledger and full logs. Prior business/security tests remain unchanged.

## D - Executed reference results

| Item | Actual fixture result |
|---|---:|
| Unchanged net revenue | INR28,000 |
| Baseline / revised cost | INR20,000 /21,500 |
| Baseline / revised gross profit | INR8,000 /6,500 |
| Signed profit change / reduction | INR-1,500 /+1,500 |
| Baseline / revised margin | 28.57142857% /23.21428571% |
| Displayed margins | 28.57% /23.21% |
| Margin erosion | 5.35714286 percentage points |
| Relative profit reduction | 18.75% |
| Primary risk / revision effect | warning /new_warning |

These are actual synthetic PR11/14/15 integration results, not realized accounting
profit. Procurement assumptions keep the reference scenario_only. Verified
numerical arithmetic does not upgrade hypothetical procurement to actuals.

## E - Risk results and completeness

Reference company minimum15% is inclusive critical, target25% inclusive warning;
material erosion5pp is inclusive for positive deterioration, exposure band low.
LOW_REVISED_MARGIN and MATERIAL_MARGIN_EROSION both trigger; baseline margin is
above target and revised is warning. No minimum-margin critical breach in this
reference. Raw unrounded values determine boundaries. Tests cover14.99/15/15.01
and24.99/25/25.01, negative profits, extreme negative margin and overlapping flags.
Exposure uses existing [minimum,maximum) company-currency bands, never hardcoded INR.
Negative/minimum critical precedes high exposure, warning and normal. Incomplete
required inputs/policy/percentage yield review_required; independently known severe
flags remain visible. Estimated/scenario bases remain distinct from fully verified.

Pre-existing margin risk is compared with revised margin risk. New warning/critical,
warning-to-critical, existing critical worsened/unchanged, improvement and
undetermined classifications retain their explanations. Fixed verified customer
terms add context when profit falls; unknown flexibility remains explicit and never
authorizes a price change. Financial currentness and policy relevance are checked
separately; unrelated future policy publication does not stale the current period.

## F - Security

Raw costs and derived profit/margin/risk have the same protected boundary. Selected
company, active user, all cost/supply/demand warehouse grants, customer-commercial
grants and native access to every included order apply to headers and children.
Sales-only cannot infer vendor costs through margin; Purchase-only does not gain
customer terms. Auditor read-only; portal/public denied. Direct read/export/group,
immutable/nested/context forgery, foreign-company and revoked-scope checks execute.
Native sales drilldown reuses PR11 permission checks. No new privilege projection.

## G - Actual testing

| Gate | Actual final-source result | Evidence |
|---|---|---|
| FRESH | PASS: 59 tests | evidence/pr15-fresh-install-20261029T125200+0000_milestone.log |
| HELPERS_VERIFY | PASS: 25 tests | evidence/pr15-helpers_verify-update-20261029T125650+0000_quick.log |
| TARGETED | PASS: 96 tests | evidence/pr15-targeted-update-20261029T125709+0000_targeted.log |
| UPGRADE | PASS: 112 tests | evidence/pr15-upgrade-update-20261029T124202+0000_milestone.log |
| UPGRADE-PRESERVATION | PASS: 1 probe groups | evidence/pr15-upgrade-preservation-20261029T130339Z.log |
| CONCURRENCY | PASS: 9 probe groups | evidence/pr15-concurrency-20261029T125107Z.log |
| OPERATIONAL-SAFETY | PASS: 1 probe groups | evidence/pr15-operational-safety-20261029T125131Z.log |

55 new test methods. Historical PR15 failures and intentionally interrupted
runs remain retained. Earlier source-changed candidate runs are development
evidence only; only the final-source gates above establish verification:

- FAIL: 54 passed, 1 failed; evidence/pr15-fresh-install-20261029T121825+0000_milestone.log
- FAIL: no completed test count; intentionally interrupted; evidence/pr15-fresh-install-20261029T122527+0000_milestone.log

Actual PR14 archived84-source installation, committed cold capture before margin
schema creation, PR15 update and retained-field/source-byte preservation verify
upgrade safety including existing financial exposure. Nine real-session races:
COLLECT, PRICE, RECEIPT, VALUE, PROPOSAL, SALES_PRICE, POLICY_PUBLICATION, FX, GRANT. The policy race tests governed future-period publication
serialization and current-period non-invalidation; relevant policy staleness is
separately tested. No passing earlier business/security assertions were weakened.
100 affected-line calculation measured2.701s after upstream preparation.
500/2000/10000 inputs and peak memory NOT_MEASURED; manual browser UAT NOT_RUN.
No release-wide FULL or PR16 sign-off claim.

## H - Business safety

The native22-model fixture proves no SO price/status, vendor rule, PO, pricelist,
reservation, stock valuation, product/accounting or mail/cron changes. Nine upstream
analytical models remain unchanged by profitability. Synthetic native writes only
prepare disposable fixtures or intentional competing changes. The business service
does not create/modify native records, post entries, approve, reprice or apply prices.
Disposable runtime removed after confirmed shutdown.

## I - Progress and limitations

PR15 VERIFIED for the documented projected profitability/risk scope. Final source
ledger 90 files SHA256 ce5b7dfb34f95217fadc6b80284bb6ea56983b9023f93e88e1984c272a50173f. TEST_REPORT.json and DEVELOPMENT_PROGRESS.md
updated with real evidence. Missing warehouse/lot FIFO lineage, future landed costs,
unallocated sales adjustments/FX/costs and uncertain PO amendments retain upstream
limitations. No full-order discount/service allocation or commercial-parent rollup.
Browser UAT and larger workloads/memory remain unverified. PR16 NOT_STARTED.

## J - PR16 handoff

Use get_current_profitability only with current compatible PR11/14 source evidence
in a fresh authorized transaction. Retain exact company/customer/order/line/variant,
allocation/cost contribution IDs, currency/UoM, scenario/demand class and versions,
unchanged net revenue, baseline/revised costs, incremental exposure, profits,
margin percentages, erosion pp, signed profit change/reduction, relative ratios,
amount-sum aggregation keys, policy versions, reasons and independent completeness.
Partial/estimated/scenario-only values and unknown discount/FX/cost inputs cannot
become verified full totals or realized outcomes. Honor all confidentiality and
no-double-counting invariants. PR16 must independently reconcile full-source scope
before any sign-off foundation; no sign-off, approvals, pricing recommendations,
repricing, supplier application or accounting execution implemented here.
STOP after PR15.
