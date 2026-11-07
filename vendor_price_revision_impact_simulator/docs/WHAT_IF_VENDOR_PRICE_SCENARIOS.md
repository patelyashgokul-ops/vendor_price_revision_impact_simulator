# PR17 - hypothetical vendor price alternatives

Scenarios compare purchasing assumptions before a commercial decision. They never
accept supplier terms, approve spend, apply supplier/customer prices, change a PO,
reserve/move/revalue inventory, post accounting or send negotiation messages.
PR18 recommendations and later approvals/application are separate future prompts.

## Baseline and immutable lifecycle

Create from an authorized exact PR16 reconciliation using its form button. Finance
requires the same active company, every selected warehouse cost/supply/demand grant,
customer-commercial grant and native sales rights as the baseline. Finance is the
only editing/calculating role in this implementation. Scoped confidential readers
(including auditors under existing role definitions) read history only. Purchase or
Sales roles alone receive no financial scenario disclosure.

The header records company/batch/reconciliation/parent identity. Each assumption
change creates an immutable input version and exact product or protected-PO line.
Each calculation creates immutable result/detail evidence; unchanged inputs and
current sources return the existing result. Old values and failures remain history.
Cloning copies permitted inputs into a new identity and never copies results or
verification. Input changes invalidate the current getter and analytical preference.
Archive appends an event, retains evidence and blocks further editing/calculation;
cloning remains possible. Public create/write/unlink/copy cannot forge history.

Stored results are historical evidence. Use get_current_scenario in an authorized
fresh transaction; list history does not certify currentness. The scenario form
computes live current_state. Draft/not calculated, incomplete, blocked, stale and
financially_verified are distinct. Financially_verified means all mandatory
analytical controls and the PR16 readiness gate passed. Commercial assumptions
remain hypothetical, never externally accepted or actual accounting costs.

## Prices, discounts and partial overrides

Original proposal is inherited for every omitted product. One explicit net-source-
purchase-unit mode applies per selected product (or exact protected PO hypothesis):
original, explicit price, fixed per-unit discount, percentage discount, verified
proposal tier. A fixed reduction3 from115 gives112; ten percent from115 gives103.50.
The input form shows stored original net source price, its supplier currency and
purchase UoM, eligible comparison-unit quantity and warehouse; PO hypotheses
show the exact normalized agreed source-unit basis. These labels are read-only
source evidence, not a currentness or acceptance assertion.
Discount base defaults explicitly to original proposal, or selects old comparable
terms. Price methods cannot be combined; FX/date/landed dimensions are independent
and retained with every changed assumption. Missing/nonfinite/negative prices are
invalid. Zero is an explicit hypothetical result, not evidence of an accepted
zero-cost supplier agreement. No order-wide discount or repeated discounting.

Amounts use PR08 Decimal normalization and native Odoo20 UoM factors. Overrides
must retain exact original source currency/UoM. PO hypotheses use the exact PR12
normalized comparison unit/source currency; this different basis is explicit.
Product/vendor/batch identities are exact, never SKU/name inference. One product's
override cannot replace another product or another vendor's terms.

## MOQ and buying groups

Select an exact commercially validated PR08 proposal row. PR13 replacement-price
eligibility checks the proposal's exact product/UoM, effective/end dates and minimum
normalized quantity, highest eligible threshold and ambiguity gates. Grouping is
explicit with an audit reason, limited to residual new procurement of the same
company/vendor/product/UoM/warehouse in the already coherent source cohort. It does
not change demand allocation. Per-entry buying remains the default. An optional
buying quantity must equal actual eligible residual procurement. A cheaper tier
requiring surplus stock is blocked/review-required; no cash, holding-cost or surplus
optimization is fabricated. No RFQ/PO creation or unrestricted vendor substitution.

## FX and price decomposition

Rate direction is company currency per1 source currency. Price-only common FX,
combined price/FX and FX-only sensitivity are labeled separately. A price-only
common-FX override requires a common-rate PR14 baseline. A two-date source must
use its coherent common-rate baseline or an explicitly documented combined-rate
assumption; its FX effect cannot hide behind a price-only label. FX-only retains
original commercial price. Alternate positive rates require a published Finance-
governed FX override policy and an explicit rate date. Rates remain hypothetical;
res.currency.rate is never written. Missing FX cannot become1:1. Same-currency
sensitivity rates are rejected. PR08 old-rate-first decomposition separates supplier
price and FX effects: USD10->11 at90->94 gives price90, FX44, combined134 per unit.
Original foreign unit price, source rates and dates remain traceable.

## Date, PO and landed hypotheses

Changing price-effective date retains the PR10 physical supply allocation. Explicit
commercial commitment date/evidence determines before/after applicability, inclusive
at the effective-date boundary. Delivery/arrival date is not assumed to be a
commercial commitment. Unknown timing blocks complete calculations. Changes to
physical supply timing are unsupported inputs and require a new upstream allocation,
never actual reservation changes. A date delay models a hypothetical agreement to
retain old terms, not an assertion that a supplier has accepted the extension.

Default existing stock and verified protected incoming retain exact PR13/12 cost.
An exact allocated open protected PO line may receive a separate explicit unapproved
amendment hypothesis. Its already allocated quantity is changed once in that
alternative, never additionally treated as new procurement.40@100->115 is600 extra
hypothetical cost. Missing protection/old cost stays incomplete. No actual PO terms,
confirmation, liability, bill or stock valuation changes.

Future landed components require the published scenario_landed_policy option
evidenced_nonrecoverable_charges. This separate PR17 permission preserves the
existing PR13 net-price baseline; default is exclude. Publication, versioning,
configuration-role authorization and audit use the existing PR04 policy guard.
Each component has a unique code, company-currency per comparison-unit amount,
source/evidence and explicit nonrecoverable/not-already-included assertions.
Recoverable tax, duplicate components and already capitalized charges are rejected.
Existing stock/protected PO costs never receive those future charges. No landed-cost
posting. Current PR13 marks future charges incomplete without attribution evidence;
therefore if the original PR13 additional_cost_policy itself requires unavailable
charges, that PR16 baseline cannot be upgraded to
financially_verified merely by PR17 assumptions. A draft exploratory result may
show reproducible hypothetical costs but remains not financially verified, with no
rankable proposal improvement when the original proposal cost is unavailable.

## Shared calculations and controls

Read frozen PR08-16 evidence, rerun PR16 Reconciler for source/quantity/identity/
revenue/cost/policy freshness, then use the existing PR14 calculate and aggregate
services over isolated dictionaries. PR15 profitability, risk assess and aggregate
services calculate unchanged customer revenue minus scenario source-weighted costs,
all reasons and company policy thresholds. Independent PR16 profit/risk equations
and Controls/readiness verify line/aggregate identities and complete scope. No
second financial engine, new live policy override or unsafe context bypass exists.

Old baseline, original proposal and negotiated alternative remain separate. The
potential improvement versus proposal is proposal cost minus scenario cost; it is
not realized savings. Incremental exposure is scenario cost minus old baseline.
Margins are amount ratios, not average line percentages or markup. Margin change
versus proposal uses percentage points. Risk is recalculated per line/company;
one removed warning does not remove independent erosion/materiality/fixed-price
conditions. Missing values remain null in exact evidence and blank in Char fields;
unknown numeric UI cells are hidden and require the cost_known flag.

## Comparison, auditing and security

Select scenario rows and use Compare Current Hypothetical Alternatives. It requires
exactly the same immutable baseline ID, current source versions and complete
financially_verified results. Costs can be sorted without an opaque score or additive
totals. FX/date/tier/landed/PO dimensions remain disclosed in each result provenance;
differences across multiple dimensions are not claimed as pure negotiation benefit.
Different companies, demand/quotation cohorts or baseline versions are incomparable.
Conditional quotation/portfolio sources retain PR10/14/15 exact confirmed references
and shared-capacity allocation; alternative totals are never added together.

Shortlisted/preferred-for-review are append-only analytical events. They confer no
supplier acceptance, approval or application rights. Source drilldown rechecks read
access. Immutable child records use global active-company, warehouse cost/supply/
demand and customer/native-order scope rules. Direct ORM, exports and grouped search
must obey the same financial confidentiality. Assignment/selection grants no access.
Untrusted context flags and one2many commands cannot bypass immutable writes.

## Transactions, limits and evidence

Company/batch/scenario locks serialize calculations and input revisions. Existing
upstream source shared locks protect the frozen cohort; serialization conflicts
require a fresh transaction/retry. No manual business commits or native repairs.
Header/detail publication uses a savepoint so failed results cannot claim success.
Finite bounded numbers,1000 assumption lines,20 landed components and100 compared
alternatives keep the analytical API bounded. Reconciliation source limits remain
those of PR16. Large list history omits repeated live freshness calculations.

See TEST_REPORT.json and the PR17 handoff for actual executed checks and failures.
Manual browser UAT, larger workloads and peak memory are not certified without
measurements. Incomplete warehouse/lot FIFO acquisition lineage, uncertain original
terms, unallocated customer adjustments and unsupported landed attribution remain
upstream limitations; scenarios never turn them into verified facts.

## PR18 handoff

Consume only current authorized exact scenario results with baseline reconciliation,
source IDs/versions/fingerprints, product/vendor mapping, affected demand, protected
supply and new quantities, source price/UoM/currency/FX/date/tier assumptions,
unchanged customer price/protection, baseline and scenario cost/profit/margin,
policy thresholds, recalculated risk/reasons, independent control outcomes and
completeness. Retain preferred-for-review as a hypothetical selection only. Future
customer repricing recommendations need their own controls and authorization.
PR18 NOT_STARTED. STOP after PR17.
