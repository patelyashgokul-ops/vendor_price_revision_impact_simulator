# PR13 — allocation cost reference contract

This read-only foundation attaches source costs to one immutable, current PR10
allocation. It does not calculate consolidated exposure, gross profit or margin,
approve commercial terms, buy stock, change prices, or post valuation/accounting.

## Entry points and upstream authority

`batch.action_attribute_costs(allocation_id, purchase_id=0, procurement_date=None)`
collects a version. `batch.get_current_costs(...)` returns only the latest version
whose complete fingerprint still matches. The allocation must contain costs and
belong to the same batch/company. Its original supply and allocation current
getters must succeed. No quantities are reallocated. Each PR10 entry has exactly
one cost line; its segments sum to its original base-UoM quantity. Unresolved
entries retain their quantities with an unavailable cost, not a numeric zero.

An optional PR12 snapshot must reference that exact allocation and warehouse
scope and exclude bill detail. The current PR12 getter must succeed. Missing
PR12 evidence leaves incoming costs incomplete; PR09 classifications alone do
not establish fixed commercial protection.

## Existing stock: accounting reference versus acquisition history

Standard Cost uses the current company-dependent configured cost. It is not proof
of what a particular quant cost to acquire. Native company/product AVCO uses the
current company-dependent average cost; it is not recalculated as a warehouse
average. Both capture a `verified_accounting_basis` source and label attribution
`supported_estimate`. Reserved and free stock remain distinct PR10 entries and
consume no additional stock capacity. Changing a vendor proposal does not change
these recorded cost references. Negative or unevidenced default-zero cost is
unavailable. A documented current native manual zero-cost record can establish
zero; a supplier's explicitly verified zero proposal is also distinct from missing.

Lot-valuated products currently require review: a lot identifier by itself does
not establish a reconciled lot cost. Consignment, excluded locations and negative
stock cannot create additional stock allocations through this service; PR09/10
remain authoritative for eligibility.

## Odoo 20 FIFO evidence and its limit

The inspected Community source uses `stock.move.value`, `product.value` manual
adjustment history, and `product.product._get_fifo_stack()`. The stack returns
incoming moves plus the remaining portion on its first move. It is not the older
`stock.valuation.layer` API. This service calls the read-only stack getter, never
`_run_fifo(correction=True)`, `_update_standard_price`, or any valuation action.

The service preserves move IDs, full and remaining quantities, recorded values,
proportional remaining values and company-product reference totals. The remaining
quantity must reconcile to the native company valuation quantity. Insufficient
or negative valuation evidence has no Standard Cost fallback. Thirty units at
90 plus thirty at 100 form a company pool of 60, value 5,700, weighted reference
95. This does **not** prove which warehouse quant or customer demand owns those
layers. Warehouse-specific FIFO cost remains incomplete. Pool quantities are
retained once in header provenance; entry evidence is a reference, never another
layer consumption ledger. Alternative scenarios must never be added together.

## Incoming purchase commitments

Incoming stock uses an exact current PR12 line with matching vendor, variant,
warehouse, UoM and verified open quantity. Across entries of one scenario, the
consumed incoming quantity cannot exceed that open quantity. Only
`protected_verified`, commercially valued, confirmed terms can select a protected
company-currency cost. Pending/disputed amendments retain recorded and proposed
alternatives but select neither as a final protected cost. A protected 40 at 100
remains a 4,000 reference even if the supplier proposes 115. This is neither an
accounts-payable amount nor a legal determination made by the cost service.

## Replacement, tiers, dates, FX and taxes

New procurement uses only current PR08 proposed prices. It never substitutes the
current supplierinfo baseline, creates a PO, or switches vendors. An explicit
planning date is required. Applicable exact-variant proposal periods are inclusive;
the highest eligible unique normalized MOQ is selected. Each PR10 entry supplies
its own **hypothetical** buying quantity. There is no cross-demand consolidation,
order splitting, automatic MOQ uplift or guarantee of an actual buying tier.
For an explicit entry buying scenario of 100, an MOQ-100 proposal at 109 may be
a scenario reference. Two entries of 60 do not jointly qualify for that tier.

Source prices/discounts, base UoM normalization, source currency, company currency,
selected proposal/result IDs, baseline evidence, date and quantity basis remain
traceable. Conversion reuses the PR08 guarded FX resolver at the planning date
or published company reference date. Future FX requires independently authorized
PR08 scenario evidence; missing rates never become 1:1. Source-specific accounting,
PO and replacement dates are retained independently. Decimal arithmetic uses
precision 38; reporting rounds separately to the recorded company currency step.

Only the current verified tax-exclusive PR08 basis is consumed. Recoverable tax
does not silently become inventory cost. Existing native move values/accounting
costs already include capitalized adjustments; no historical landed charge is
added again. A recorded 105 including 5 remains 105, not 110. The published
`exclude` policy yields a net commercial replacement reference, explicitly not a
fully landed estimate. Evidenced future freight/duty is not implemented in this
foundation; a policy requiring those components leaves replacement cost incomplete.
No landed-cost or accounting records are created/validated/posted.

## Confidence, freshness and transactions

Quantity confidence remains separate from cost confidence. Selected sources can
be `verified_commercial_basis`, `supported_estimate` or `scenario_assumption`;
missing evidence is `unavailable` or `review_required`. Blank cost/value fields
must not be summed as zero. Per-entry source reference values are not final
incremental exposure. No mixed-currency aggregate is published.

Snapshots, lines and issues inherit immutable server-side guards. Versioned
fingerprints include current upstream digests, valuation moves/manual changes,
optional installed landed-cost adjustments, product/company costs, policy,
proposal applicability, FX and UoM evidence. Historical versions remain intact.
Collection uses the shared company/batch serialization and a savepoint, with
shared source-row locks. Errors roll back the complete publication. Operational
source writes after collection invalidate the fresh getter; future inserts are
detected on the next fresh read. There are no application commits or retries
that swallow a serialization error. Callers must revalidate stale upstream evidence.

## Security and review

Global company, supply-warehouse, cost-warehouse and demand-warehouse rules apply
to headers and children. Roles still restrict which revisions a preparer owns.
Sales-only, portal and public users receive no cost access. Confidential readers
need all scope grants; auditors cannot collect or alter snapshots. Private source
projection uses fixed models, fields and exact company/product domains only after
authorization. It is not a generic sudo API. Company-wide valuation references
are explicitly company-product evidence, not other-warehouse stock availability.
Native operational drilldown independently checks native source permissions.

The allocation form opens a bounded input wizard; immutable list pages use 20
headers and 40 detail lines per page. Source evidence, quantity segments,
exceptions and reconciliation are inspectable. Direct ORM writes/copies/deletes,
nested commands and context-default forged outcomes remain blocked. Exports use
the existing protected evidence/export guards.

## PR14 handoff and unsupported inputs

PR14 must use `get_current_costs`, retain allocation-entry IDs and snapshot version,
preserve base quantities/UoMs/currencies/dates, and reconcile each selected source
once. It must distinguish accounting references, protected commitments and
hypothetical replacement costs. It must never turn unknown/partial costs into zero,
add alternatives, reuse FIFO layers as physical lineage, or interpret scenario
benefit as realized outcome. Access must be rechecked server-side for every use.

Unsupported exact warehouse FIFO tracing, unreconciled lot valuations, evidenced
future landed components, missing FX/date/UoM and disputed PO commitments remain
unresolved inputs. PR14 profitability/exposure/approval/application is not started.
