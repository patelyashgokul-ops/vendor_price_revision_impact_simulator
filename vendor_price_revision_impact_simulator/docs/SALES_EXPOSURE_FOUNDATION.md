# Sales commercial exposure foundation — PR11

PR11 preserves the actual recorded customer sales-line terms associated with a
current PR10 allocation. Values describe outstanding fulfillment; they are not
recognized revenue, receivables, profit, margin or supplier-cost impact.

## Collect and review

From a current allocation choose **Collect Customer Sales Terms**. The collector
needs existing allocation and batch preparation authority, Sales Manager or
Finance Manager, native read access to every exact source order and line, and a
separate audited customer-commercial grant for every warehouse. Role combinations
are explicit: Finance alone does not acquire draft preparation authority; Sales
alone does not acquire confidential supplier evidence. No native Sales/Purchase/
Stock administration groups are added by the addon.

Configuration Administrators manage **Customer Commercial Access** with a reason.
Grants default to absent on upgrade. Sales-only readers need the APP06 Sales role,
native Sales read permissions and this grant. A snapshot is visible only when ALL
its warehouses and source orders are authorized. Native own-orders restrictions
therefore hide a combined snapshot containing another salesperson's orders.
Use narrower PR10 scopes to publish a suitably restricted projection.
Transient collection/review forms enforce the same fixed projection for nested
reads and searches; wizard export, grouping and generic search panels are disabled
to prevent alternate paths into live native costs.

The customer projection stores integer allocation/supply identifiers, version and
digest, and quantity-category selling values. It exposes no supplier-price fields,
raw allocation/supply provenance, supplier attachments or unrestricted source RPC.
Nested exports, web read specifications, grouping metadata, search/order joins and
aggregations are restricted to the captured sales projection and native identity/
labels. Native product permissions otherwise include costs in this Odoo baseline;
PR11 does not expose those live cost joins or change global native permissions.
Source drilldown enforces native Sales access. Exports and aggregation use the
same company, warehouse, role and source-order restrictions as direct reads.

On an exact customer line, a Sales Manager can record a documented price-protection
assessment, reference, reason and effective interval. This creates immutable review
history bound to that exact source price/discount/currency/order context. It grants
no authority to reprice a customer transaction. Review does not need supplier ACLs. A fixed-ID, company-scoped privileged read
checks only the originating batch/revision lifecycle; cancelled/retired contexts
cannot receive a new assessment. Source rows are locked while the review publishes.
No supplier terms or attachments are returned by this metadata check.
An amendment or expired/inapplicable latest review requires another assessment;
an older favorable assessment is never revived automatically. Confirmation alone
does not prove legally fixed prices or a right to adjust prices.

## Quantity and value basis

The current getter `batch.get_current_allocation(...)` is authoritative. PR11 keeps
its exact sales-line identity, base UoM, outstanding quantity, scenario and category
entry identifiers. It never allocates stock again or subtracts reservations twice.
Physical deliveries, backorders and returns remain PR10 responsibilities. Unresolved
return/replacement interpretation cannot generate a precise remaining sales value.
Invoiced quantities are context, never a replacement for physical fulfillment.

Actual `sale.order.line.price_unit` and `discount` are preserved. Today's pricelist
is context, never evidence that a confirmed price changed; the nonstored current
pricelist-rule cache is deliberately not represented as a historical applied rule.
No original confirmed price is reconstructed without prior snapshots or amendment
evidence. Previous snapshots retain earlier observed prices.

Odoo20's native `_prepare_base_line_for_taxes_computation` and tax-details service
provide the unrounded tax-excluded unit basis. Document tax mode, mapped line
taxes, included/excluded/fixed/group taxes and line discounts follow native rules.
Negative discounts retain their native surcharge meaning. Discount is applied
once. A zero source price remains explicit and reviewable, never replaced with
product list price. Invalid, negative or unsupported bases remain incomplete.

UoM pairs reuse PR08's verified common-reference validation and dimensional factors.
Price per source box converts inversely to quantity; a 1,400 price per Box10 is
140 per base unit. Decimal precision is 38 significant digits. Currency rounding
occurs at report-value boundaries; the precise category amounts and explicit
rounding residual reconcile to the rounded outstanding amount. A residual is
rounding evidence, never fictitious balancing revenue.

All same-order adjustment lines are inspected, including standard global discount
markers/product, negative lines and downpayments. Full order tax-excluded totals
and exact adjustment IDs/amounts are separate context. No arbitrary product
apportionment occurs. Such adjustments block precise product attribution; they
are never subtracted twice. Shipping and unrelated services are not product demand
or included in product selling values. Custom positive adjustment conventions that
carry no native marker need integration review; this foundation does not infer
external contract semantics from line descriptions.

## Quotations, currency and confidentiality

Confirmed and conditional amounts occupy distinct source-currency groups. Drafts,
sent offers, expiration and quote confirmation retain their actual classifications.
PR10 excludes newly selected expired quotations. Previously captured quotes remain
historical evidence and become stale as validity changes; they never become verified
active offers. A sent unexpired offer requires contractual review.
Standalone quotation alternatives cannot be summed. An explicit combined portfolio
must use its corresponding PR10 allocation. No automatic quotation/price/message
operation exists.

Foreign sales values remain in their original currency. Optional conversion needs
an explicit sales FX reference date; supplier FX dates are never inherited. The
guarded native Odoo20 convention is root-company rates before the requested date,
preferred over shared rates, target technical rate divided by source rate. Both
currency rates must exist and be positive. No earliest-rate or missing-rate 1:1
fallback is accepted. Same currency uses an explicit identity rate. Rate IDs,
dates, company, method and direction are frozen. Missing FX preserves valid source
values and leaves company references blank. The company reference converts the rounded source-currency outstanding value
and rounds once to the company-currency increment. No currency-rate record is changed.
This is a company-currency reference, not an accounting FX gain/loss calculation.

## History, freshness and concurrency

Public create/write/unlink/copy cannot forge snapshots, issues or reviews. Collection
publishes atomically inside a savepoint; unchanged inputs reuse the current version.
Source price/discount, quantities, state, validity, tax definitions, UoM, currency/
rates, adjustment evidence, assessment and upstream allocation changes invalidate
the fingerprint. Unrelated notes/write dates do not invalidate material terms.
Calendar changes matter when offer/review validity changes.

Collection serializes company/batch analytical publication and locks existing
source rows for share. Competing source writes block or require serialization
retry. Reviews use the same company lock. The analytical service never commits.
New source/rate inserts are not permanently frozen by existing-row locks; consumers
must use fresh authorized transactions and current getters, retrying conflicts.
Sales-only readers can inspect immutable evidence but cannot attest full upstream
freshness without allocation authority; their status conservatively shows stale/
access unavailable. Do not treat the stored state as a current financial approval.

Source projections are bounded at 10,000 records per query; large scopes fail
without partial publication. Native Sales metadata scope exceeding 10,000 orders
fails closed and needs narrower grants. Freshness-history filtering is capped at
1,000 snapshots. Views paginate; broader workload/memory guarantees require actual
measurement. Runtime results and unavailable checks are recorded in TEST_REPORT.

## Later-phase handoff

Call `allocation.get_current_sales_terms(fx_date)` in a fresh authorized transaction.
Retain exact source line/customer/company/product, confirmed or conditional scenario,
outstanding quantity/UoM, net tax-excluded price, sales currency, optional FX evidence,
contract status and review provenance, category entry IDs and snapshot digest/version.
Inspect independent value, protection and FX statuses and issues. Blank is missing,
not zero. Grouped totals are null when any constituent line is incomplete. The separately
labeled known subtotal and incomplete-line count remain available.
Do not combine unrelated snapshots, companies, currencies or conditional alternatives.

PR12 must independently establish supplier purchase commitments, dates, currency,
amendment/dispute and protection evidence. PR14–16 must reconcile all verified inputs
before financial aggregation. Neither purchase commitment analysis nor margin,
repricing recommendations, operational approval/application, stock valuation or
accounting posting is implemented by PR11. Stop after PR11.


PR11 integration correction: Odoo20 draft/sent expected_date is a rolling clock-
based estimate. PR10 no longer fingerprints that unused value when an explicit
commitment date governs demand. Conditional lines without a stored commitment
remain date-review/unresolved; confirmed orders retain their date_order-based
native expected-date fallback. The date-basis contract is versioned in allocation
provenance. Existing PR10 snapshots remain intact but require explicit revalidation
under this corrected projection; upgrade does not silently rebuild allocations.
