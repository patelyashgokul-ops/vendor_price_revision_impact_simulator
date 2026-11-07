# PR10 / DEV05 — Completion report

## A — Environment

Odoo **20.0 Community FINAL**, addon `vendor_price_revision_impact_simulator`,
manifest20.0.1.0.0. Direct dependencies: base, product, purchase_stock and sale_stock;
Community native purchase/stock/sales integration is reused, including stock_account.
No repository major version or existing database was upgraded. Verification used
a disposable PostgreSQL18.4 cluster on127.0.0.1:55441, exact database allowlists,
isolated filestores and disabled external/mail/cron/payment/live-accounting effects.
All test runtime resources have been removed after confirmed shutdown.

## B — Implementation

Current PR09 supply is mandatory. Confirmed `sale` demand remains distinct from
explicit draft/sent quotation scenarios. Exact sales lines preserve product,
company, warehouse, customer/source IDs, ordered/delivered/outstanding/base units,
dates and delivery evidence. Partial100/40 gives60 open; pick/pack/ship and backorders
do not create additional commercial demand. Cancelling logistics alone does not erase an unchanged sales quantity: that
remaining obligation stays unresolved until commercial amendment or a valid
replacement fulfillment flow is evidenced. Returns, unsupported delivery methods
and inconsistencies remain review/unresolved, not invented replacement commitments.

Quant reservations reconcile to active move-line dimensions and unique downstream
sales ownership. Included confirmed owners receive their reservation once; other
owners' stock stays unavailable. Draft/sent reservation owners do not become
confirmed reservation coverage. A source-capacity ledger consumes free quants and
incoming receipt legs once, preserving exact procurement/MTO ownership.

Stable date/confirmation/source-ID priority is versioned and audited. Same-warehouse
allocation has no invented cross-warehouse transfer lead time. Incoming price
protection and demand availability are separate. Input arrival needs an explicit
documented company planning delay to saleable stock; Quality/staging/transit never
receive automatic release. Late/unknown availability is not verified timely coverage.
Known gaps, uncertainty and actual coverage reconcile without negative residuals.

Immutable snapshots reference source supply/version/digest, commercial context,
policy, scope and actor/time. Unchanged inputs are idempotent. Material changes
stale the current getter; notes alone do not. Source locks and one publication
savepoint avoid mixed/partial success. Independent quote scenarios preserve
confirmed allocations; justified portfolios share one residual capacity pool.

## C — Relevant files

- __manifest__.py; models/__init__.py: sale_stock Community dependency/registration.
- models/allocation_policy.py: demand opt-in grants and versioned priority/Input planning policy.
- models/allocation_engine.py: bounded source projections, fulfillment/reservation/MTO/time/quantity logic and reconciliation.
- models/allocation_snapshot.py: immutable header/demand/ledger/issues, current getter and review/preview wizard.
- security/allocation_security.xml; views/allocation_views.xml: global company/all-warehouse/cost rules and analytical review filters/forms.
- tests/test_demand_allocation.py; tests/__init__.py; tests/test_module_foundation.py:71 new methods and dependency contract.
- docs/DEMAND_ALLOCATION.md; README.md; TESTING_SETUP.md; DEVELOPMENT_PROGRESS.md; TEST_REPORT.json.
- evidence/pr10-* drivers/probes/logs, pr09-source-baseline.zip/.sha256 and pr10-verified-source-sha256.json.

## D — Actual fixture results

| Case | Verified coverage / residual |
|---|---|
| A:200 demand; physical80 with20 reserved outside selected demand | Reserved0 + free60 + protected incoming40 + new100 =200 |
| B:200 demand;20 reserved for included confirmed line | Reserved20 + free60 + protected incoming40 + new80 =200 |
| C:80 and70 demand competing for100 free | Allocations80/20; new50; source consumption100 |
| D:200 committed plus70 conditional quote | Baseline200/new100; separate scenario270/new170; incremental conditional new70 |

Actual source-qualified A–D markers are retained in evidence/pr10-fresh-install-20261029T032214+0000_quick.log.
Other executed cases cover fractional/boxed units, physical reservation stages,
partial delivery/backorders/returns, unknown lineage, direct/ambiguous MTO, Input
putaway policy, late/unknown ETA, warehouse boundaries, quote conversion/portfolio,
atomic failure, current versions and authorized source preview. No monetary
exposure or future INR1500 financial reference was computed.

## E — Security

Every selected warehouse needs explicit customer-demand opt-in and, for cost mode,
its cost grant. Existing grants are not automatically enabled. Company/role/own-
batch and global all-warehouse/cost intersections protect direct reads, searches,
exports, grouping and children; role combinations cannot bypass company scope.
Auditors remain read-only, and Odoo's separate export permission remains required.
Sales-only/Configuration-only/Portal/unauthorized users cannot run or inspect
confidential allocation evidence. Quantity-only projections omit selling/vendor
prices and accounting costs. Approved source-ID previews avoid native Sales ACL
broadening; source forms still check native permissions. Cross-scope physical
fulfillment/procurement graphs block publication before confidential output.

## F — Automated verification

| Selection | Actual result | Evidence |
|---|---|---|
| QUICK Decimal/capacity helpers |2 tests PASS|evidence/pr10-helpers_verify-update-20261029T033733+0000_quick.log|
| TARGETED PR10 + affected PR09/PR08/source security |235 tests PASS|evidence/pr10-targeted-update-20261029T031536+0000_targeted.log|
| Final clean installation |318 tests PASS|evidence/pr10-fresh-install-20261029T032214+0000_quick.log|
| Actual PR09 update MILESTONE |318 tests PASS|evidence/pr10-upgrade-update-20261029T030622+0000_milestone.log|
| Upgrade source/supply/commercial/operational preservation |PASS|evidence/pr10-upgrade-preservation-20261029T034420Z.log|
| Eight independent-session races |PASS|evidence/pr10-concurrency-20261029T033836Z.log|
| Eighteen-model operational safety |PASS|evidence/pr10-operational-safety-20261029T031516Z.log|
| Static/cleanup/hash checks |106 PASS|evidence/DEV-05-pr10-static-validation.txt|

The 100-order/100-line workload measured **0.848s** for allocation
after fixture/upstream preparation. Demand200/free100/new100 reconciles, with
one sales-line projection, one order projection and 3 bulk move projections.
This does not measure general throughput, full workflow setup or peak memory.
500-order/2000-line/10000-record stress: NOT_MEASURED. Browser UAT: NOT_RUN.

All mandatory final runtime/static records match frozen68-file ledger
`12c598701f13e094fcac8d8bd44c1a98c3102be2d542de3fefe6aba6626285b1` with no source changes during execution. The exact62-source PR09 archive
and hash are retained. Failed draft/setup/representation attempts remain in report
history; no regression was disabled or weakened to obtain a pass. The draft short-close
expectation was corrected to retain unchanged commercial obligations and
strengthened with amendment/replacement cases. Fixture failures
were corrected by establishing actual intended operational state, including
removing automatic downstream reservation before the explicit20-unit stage test.

## G — Business safety

Normal app methods change only app analytical/governance records. They do not
reserve/unreserve stock, mutate moves/move lines/pickings, validate deliveries or
receipts, confirm/cancel/reprice SO/PO, create procurement, change supplier rules/
product costs, revalue inventory or post entries. No financial exposure, margin,
revision approval or price application engine is implemented.

The safety fixture intentionally created confirmed SO/PO, package stock50/reserved3/
free47, a valued done stock move3500 and a posted balanced entry before analysis.
All18 operational/master/mail/cron/package model values, IDs, write dates and counts
remain identical around repeated allocation/current checks. Odoo20 valuation is
stock.move.value here; absent stock.valuation.layer is not falsely claimed tested.

## H — Progress and limits

PR10 is VERIFIED; TEST_REPORT.json and DEVELOPMENT_PROGRESS.md contain actual
source-bound evidence. PR11 is NOT_STARTED. M2 remains IN_PROGRESS for subsequent
detailed sales/purchase/inventory analysis. Known unresolved routes and permission,
source-lock, date-planning and measurement limits are documented in
docs/DEMAND_ALLOCATION.md and TEST_REPORT.json. No larger-load, memory, browser-UAT
or future financial test result is invented.

## I — PR11 handoff

Use `batch.get_current_allocation(warehouse_ids, costs, horizon,
confirmed_order_ids, quotation_ids, portfolio_reason)` in a fresh authorized
transaction. Do not select a latest numeric ID and assume it is current. Retain
allocation/supply IDs/versions/digests, scenario/scope/policy/time, exact sales line
and customer/source IDs, product/warehouse/base-UoM/date dimensions and capacity keys.
Read outstanding/reserved/free/incoming/protected/new/unresolved quantities and
issues; source keys identify quant, move-line and incoming receipt-leg consumption.
Reservations are already deducted from free stock, protected incoming is a subset,
and conditional standalone scenarios must not be added together.

Incoming cost classifications/dispute/amendment/incomplete details remain in PR09
source attestations and immutable provenance; a generic unverified ledger label
must never be treated as protected cost. Customer contract selling-price context
and detailed financial exposure remain future work. Preserve company/all-warehouse/
role/cost/revocation rules and native source-opening permissions. Analytical claims
are not permanent reservations; fresh-source/retry semantics remain mandatory.
No PR11 or later engine was started.
