# PR10 — Analytical demand and supply allocation



This Odoo20 Community layer consumes current PR09 supply evidence and produces

quantity coverage only. It does not reserve inventory, change operational documents,

compute monetary exposure, approve revision prices or apply vendor prices.



## Authorization and operator workflow



An active PR09 analytical grant must additionally enable **Customer Demand** for

all selected warehouses. This opt-in intentionally permits fixed sales quantity

and customer/source-ID projections through the private analytical service. It

adds no native Sales/Purchase/Stock administration rights. Cost mode also requires

PR09 cost permission on every selected warehouse. Existing grants migrate with

demand access disabled. Configuration-only and Sales-only roles cannot collect;

Auditors can read authorized evidence but cannot run it.



Classify exact physical locations and complete PR06–PR08 first. Collect current

PR09 supply, then open **Allocate Demand (Simulation)** on the batch. Preview

Authorized Sales Sources shows eligible order IDs/references/states within the

company, warehouse and affected product scope. Enter confirmed source IDs, or leave

blank for all affected confirmed orders in scope. Select quotation IDs explicitly;

a multi-quote portfolio needs a justification that addresses commercial alternatives.

The preview never returns selling prices or bypasses source forms' native access.



Every result references the supply snapshot, immutable source evidence, policy,

warehouse scope, optional date horizon, creation time and actor. The review form

shows demand, actual reservation-backed coverage, simulated free/incoming coverage,

protected incoming subset, new procurement, unresolved quantities, source capacities

and issues. **Check Current Sources** verifies current applicability; historical

numbers alone are not current commitments. Source opening checks native permissions.



## Demand and fulfillment



Only actual `sale` orders are confirmed in this target version. Draft/sent are

conditional; cancel is excluded. Display/downpayment lines are not stock demand.

Only exact current PR08 variants are included. Ordered/delivered/move quantities

are normalized to product base UoM with PR08 Decimal/common-reference helpers.

There is no invoice-quantity fallback.



One commercial sales line is one demand identity, regardless of pick/pack/ship

moves or backorders. Customer boundary done, pending and cancelled quantities

reconcile to ordered quantity; net delivered is cross-checked with Odoo's

`stock_move` delivery method. Partial delivery100/40 yields60 outstanding.

Short-closing without backorder retains original planned demand on the done move

in this Odoo20 tree. Cancelling that warehouse remainder does not amend an unchanged

confirmed sales quantity: ordered100/delivered40 remains60 outstanding and requires

commercial/fulfillment review. A separately evidenced commercial reduction to40

leaves zero open demand. Cancelled old routes are nonadditive when a valid active

replacement route covers the same remaining obligation. Unsupported/manual/negative

or inconsistent delivery evidence remains unresolved rather than being dropped.

Customer returns and replacement chains require review; a net return is never

silently interpreted as a new replacement obligation.



Nonstock/untracked/service demand is explicitly outside verified physical allocation;

its quantity remains unresolved/not applicable, with no fabricated new procurement.

Required date uses customer commitment, otherwise the order's expected date labeled

as an estimate. Missing dates require review. A horizon filters required dates,

never rewrites source dates or represents a historical stock reconstruction.



## Reservation evidence and source uniqueness



Quant reserved quantity alone cannot identify an SO owner. Active stock.move.line

quantities must reconcile with quant reservations across exact company/product/

location/lot/package/owner dimensions. The collector follows bounded downstream

move lineage to a unique sales line. Included confirmed owners receive that actual

reservation once; excluded owners' quantities remain unavailable. Missing/ambiguous

lineage and unusable reserved locations remain explicit uncertainty.



Free stock is PR09 eligible unreserved quantity; reservations are already subtracted.

Reservation capacity keys are `reserved:move_line:id`; free keys are `free:quant:id`.

Incoming keys are `incoming:move:id`, each tied to one PR09 `po_line:id` bucket.

Receipt legs share that bucket's verified supplier-unreceived capacity; received,

cancelled, putaway and internal transfer quantities do not add procurement capacity.

Every capacity records initial/consumed/remaining quantity. A unique source cannot

be consumed twice in a scenario, and no remainder can become negative.



## Priority, procurement ownership and timing



Default policy is `conservative_default_v1`: actual linked reservations, valid

direct procurement ownership, free stock, then general timely incoming. Among

comparable confirmed demands use earliest required date, confirmation date, order

ID, line ID. A versioned company policy can select confirmation-date-first instead.

All changes require Configuration Administrator access and a retained reason/audit.

The policy never permits stealing reservations or allocating another company's stock.



Incoming receipt move destination chains preserve direct MTO/customer ownership.

Only confirmed sales owners receive actual reservation-backed coverage; a custom

reservation attached to a draft/sent quote stays unavailable and is flagged.

A uniquely linked leg stays with its owner, including when that owner is excluded

from analysis. Ambiguous multiple-owner/missing chains are reviewed, not arbitrarily

assigned. An MTO flag without a verifiable owner is not general incoming stock.

There is no origin-text guess or unrestricted procurement-group assumption.



Warehouse matching is exact; there is no automatic cross-warehouse transfer or

lead-time assumption. Required/arrival datetimes use Odoo's naive UTC convention.

Supplier ETA is saleable availability only for an explicitly saleable destination.

Input receipts require an audited company policy enabling a documented Input-to-stock

planning delay (0–744 hours); that delay is added to the scheduled receipt. Without

it, incoming quantity remains unresolved. Quality/staging/transit and unclassified

destinations never gain automatic release from that buffer. The policy is a stated

analytical planning assumption, not an operational putaway or quality release.

Late incoming is retained as potential supply with a warning and does not count

as on-time coverage. Unknown ETA is unresolved, never fabricated. Source price

protection and demand availability are evaluated separately: known timely quantity

can cover demand even with unverified price. PR09 firm original-currency terms are

not an FX hedge or realized cost guarantee. No old/new supplier price is substituted.



## Reconciliation and conditional scenarios



For a resolved demand:



`outstanding = reserved_backed + free_stock + incoming + new_procurement`



With uncertainty, the mutually exclusive unresolved portion is added to the right

side. Unknown source quantity stays null. Ambiguous supply capacity is consumed

at most once as uncertainty, so it cannot falsely cover demand or be simultaneously

classified as definite new procurement. Residual procurement is a quantity gap,

not a PO, supplier stock or financial impact amount.



Confirmed baseline runs exclude quotes. A single quote or justified portfolio

references an independent current confirmed baseline and preserves every confirmed

line's coverage. Quotes consume residual capacity after confirmed commitments.

Alternative standalone quote scenarios each have independent pools and cannot be

summed. Explicit portfolios share one pool and deduplicate order IDs. Quote-to-SO

conversion invalidates the old conditional scenario; the new confirmed source is

included once. Expired quotes are excluded by the current-scenario policy.



Totals group exact product, warehouse, base UoM and confirmed/conditional class.

Never sum unrelated products or add committed baseline residual to a scenario

residual that already includes it. The detailed ledger reconciles back to each

commercial line and each physical/incoming capacity.



## Immutable history, current checks and concurrency



Snapshots/demand lines/entries/issues are system-authored and immutable through

ORM, RPC, context defaults and nested commands. Refresh appends a version per

selection; unchanged fingerprints reuse the prior snapshot. Policy, sales state,

quantity/delivery, reservation, procurement graph, ETA, UoM and PR09-source changes

invalidate current consumption. Administrative notes and source write timestamps

alone do not. Explicitly selected quote state changes cannot silently reclassify a

historic what-if as a confirmed baseline.



Company/batch serialization, existing source read locks and a publication savepoint

prevent mixed successful partial results. Errors propagate with no false success

header or mid-transaction commit. Retained prior evidence survives failed retries.

Independent transactions may encounter serialization failures and must retry from

a fresh transaction. These are analytical claims only: different explicit scenarios

are alternatives, not permanent operational reservations. Existing-row locks do

not freeze future inserts; consumers must use a fresh transaction/current getter.



Security rules globally intersect company, every selected demand warehouse and

cost mode with normal app ownership/role rules. Direct search/read/export/group

paths follow the same scope. Revocation blocks historical evidence, not just new

runs. Product/customer/source IDs are retained analytical evidence, not elevated

live references. Standard Odoo source visibility outside this app remains governed

by standard modules; this addon does not claim to revoke it globally.



## Bounds and PR11 handoff



Sources are projected in bounded bulk queries, with a 10,000-record/query and

10,000-move graph bound, and at most twelve graph expansion rounds. Overflow fails

closed. No one-stock-search-per-SO-line strategy is used. The source bounds are

not measured throughput guarantees. A 100-order/100-line quantity workload is selected for fresh/install and update

milestones; its actual elapsed time and bulk projection counts belong in the test

report only after execution. This is not a throughput guarantee. The 500-order,

2,000-line, 10,000-record and peak-memory matrix remains unmeasured unless stated

with actual evidence. Manual browser UAT is tracked separately.



PR11 must call `batch.get_current_allocation(warehouse_ids, costs, horizon,

confirmed_order_ids, quotation_ids, portfolio_reason)` in a fresh authorized

transaction. Preserve allocation/supply IDs, versions/digests, scenario selection,

company/warehouse/product/UoM/date dimensions, exact sales source keys, capacities,

cost confidence and issues. Reservations are already deducted from free supply;

protected incoming is a subset of incoming. New procurement is not a supplier

commitment; unresolved quantities cannot be priced as definite procurement.

Customer contract pricing, monetary exposure, margin, approvals and application

remain for later prompts. PR11 has not been started by this implementation.


## PR11 integration correction: stable quotation dates

Odoo20 draft/sent expected_date rolls with the clock. PR11 excludes that unused
value from allocation provenance/freshness when a stored commitment_date governs
the line. Conditional demand without a stored commitment date remains date-review
and unresolved; confirmed fallback remains based on native confirmation date.
The analytical date-basis contract is versioned. Prior PR10 records are retained
unchanged but require explicit allocation revalidation under the corrected
projection. No source order dates are changed or invented. See
SALES_EXPOSURE_FOUNDATION.md for the current sales-side handoff.
