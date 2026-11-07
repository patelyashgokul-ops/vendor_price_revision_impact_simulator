# PR14 — projected financial exposure contract

## Scope and inputs

`batch.action_calculate_financial_exposure(cost_id, sales_id, confirmed_id=0,
fx_method='same_rate')` calculates an immutable financial scenario. It requires
current PR13 cost attribution and PR11 sales classification for the same exact
PR10 allocation, company and batch. PR13's current getter validates its PR08/09/10
and optional PR12 inputs. PR11's current getter verifies native order identity,
outstanding quantity and confirmed/conditional classification. Financial results
do not depend on a usable selling-value reference, and do not calculate revenue,
gross profit, margin, risk, repricing, approvals or price application.

`get_current_financial_exposure(...)` is the consumer contract. It rejects missing,
superseded, stale or unauthorized results. Calling collection does not collect
upstream snapshots, reserve stock, reallocate demand or create procurement.
Existing current-source getters rebuild their read-only verification projections;
they do not publish a second allocation or mutate native source data.

## Baseline and revised scenarios

Both scenarios use precisely the same physical allocation entries and quantities.
Existing reserved and free stock keep PR13's accounting reference in both cases.
Standard and AVCO allocation references remain supported estimates, not proof of
physical acquisition cost. FIFO company pools do not become warehouse/SO layer
costs. Protected incoming uses the exact verified PR12 agreed price, including a
negotiated price different from the supplier's old pricelist. Pending, disputed
and unverified PO protection remains incomplete; recorded and requested prices
stay in evidence, with no unapproved amendment selected into the base total.

New procurement uses PR10's residual quantity and PR13's eligible proposed price.
The old vendor tier is independently resolved with PR08's guarded tier helper
for that **same entry quantity and comparison UoM**, rather than copying the old
tier selected at a proposal row's smaller MOQ. PR08's verified pre-revision date,
context and historical attestation remain part of the counterfactual basis.
There is no Standard Cost, recent-PO, other-vendor or zero fallback for an old
vendor price. Missing/conflicting old terms leave comparison unavailable.

The baseline describes the stated counterfactual without accepting the revision;
it does not promise that a dated old offer is contractually available forever.
Pre-revision term continuation, future buying and acceptance of a proposal are
declared scenario assumptions. Results using PR13's hypothetical per-entry buying
quantity are labeled `scenario_only`, even when all numerical inputs reconcile.
No cross-customer consolidation or MOQ uplift is inferred. Different old/new tier
structures are resolved independently, using the same purchasing quantity.

An explicit planning date is required for procurement comparison. Before all
proposals for the product become effective, the engine can use old terms valid
on that actual planning date in both cases, with zero supplier-revision effect.
It cannot do that when the old terms themselves are unavailable. Unknown dates,
expired/ineligible proposals and unsupported FX dates remain incomplete. Sales
delivery dates are not invented purchasing dates.

## Money, FX and UoM

For each segment, `baseline = quantity × old unit cost`, `revised = quantity × new
unit cost`, and signed `incremental = revised − baseline`. Positive means projected
cost pressure, negative means potential cost reduction, and zero means unchanged.
No projected reduction is realized savings or recognized expense. Verified zero
prices remain numeric zero; missing prices remain null. No percentage relative
to zero is calculated.

Every line preserves source quantities, exact variant, source entry/capacity,
base comparison UoM, target company currency, source currencies, dates, rates,
policy, proposal/result IDs and old tier candidates/selection. Box pricing is
normalized before multiplication. Monetary totals can span products only in the
same target currency; quantity totals and weighted costs are grouped by exact
product, warehouse, UoM and demand classification. There is no global average of
unrelated units or products, and no write to product.standard_price.

`same_rate` converts old terms at the same explicit PR13 FX reference date as the
proposal, to isolate supplier price under that common reference. `date_specific`
uses the PR08 old FX reference and PR13 revised FX reference and labels the result
as combined price/FX effect. For the same source currency the decomposition is
supplier effect at old FX, followed by FX effect on the proposed price. Components
must reconcile; they are not counted again in totals. Changed source-currency
terms are labeled a comparable combined reference without inventing a unique
price/FX split. Future FX is never the last known rate disguised as a forecast;
the existing PR08 finance-authorized scenario mechanism is required for a
hypothetical FX assumption.

Calculations use Decimal precision 38 and retain raw unit and extended values.
Currency rounding occurs at report boundaries. Raw aggregate identities are
checked within the target currency quantum. Sum-of-rounded-lines versus
rounded-aggregate differences are retained explicitly and bounded by the
theoretical half-quantum error per rounding operation. There is no balancing
line and no hidden monetary adjustment. Original unrounded and reported values
remain inspectable.

Existing recorded costs already include capitalized charges; the engine adds
none again. PR13's net replacement references explicitly exclude unevidenced
future freight, duty and nonrecoverable tax. Fully landed future estimates,
authorized PO amendment what-if cases and procurement optimization are unsupported
here. No landed-cost, bill, valuation or journal posting occurs.

## Completeness and reconciliation

`cost_complete` and `delta_complete` are independent. An unchanged owned-stock
source can have a verified zero price-revision contribution even when its exact
warehouse FIFO cost is unavailable. Its baseline/revised cost still remains null.
That mathematical cancellation does not manufacture a complete total cost.

Header baseline/revised totals exist only when all selected source costs and
quantities are available. The projected incremental total exists only when every
selected delta and quantity is available. Known-subset delta and verified unchanged
subset delta have separate labels; neither is the full scenario total when other
deltas are missing. Incomplete entries never disappear from line counts or grouped
quantities. Unresolved demands block complete totals even if no priced entry could
be built for them. No-demand zero is explicitly limited to the selected current
demand scope and says nothing about future demand.

States distinguish `fully_verified`, `verified_incremental_only`,
`partially_verified`, `estimated`, `scenario_only` and `incomplete`. Numerical
completeness does not upgrade estimates or hypothetical buying to verified actual
commercial costs. Financial lines, product/UoM groups, scenario totals and currency
rounding reconcile to exact source entries. There is exactly one financial line
per PR10 entry; all PR13 entries must be present and have matching quantities.

## Confirmed and conditional demand

Confirmed snapshots contain only the PR10 confirmed baseline. A quotation or
portfolio snapshot requires the current financial result for its exact PR10
confirmed-baseline allocation with matching company, warehouse, planning date and
FX method. Scenario totals include their confirmed portion; they are not additional
amounts to add to the confirmed baseline. The separately displayed conditional
effect is `scenario incremental delta − confirmed incremental delta`, only when
both deltas are complete and comparable. Alternative quotations are never summed.
Explicit portfolios use PR10's existing shared-capacity allocation. Confirmation
or cancellation makes old classification/source evidence stale.

## Versions, transactions and security

Headers/lines/issues inherit immutable evidence guards: direct create/write,
copy/delete, nested commands and context-forged verification are rejected. Each
exact input scope has a fingerprint, version and previous result. Freshness covers
PR08 prices/tiers, quantities, policy, PR11 classification, PR12 protection, PR13
valuation/cost sources, currency/UoM/FX and the confirmed reference where applicable.
Repeated unchanged calculation is idempotent. Material changes preserve old results
and require current upstream evidence. Publication uses a savepoint, shared company/
batch serialization and existing source row locks, including all current vendor
tiers. The service has no commits or swallowed serialization failures. External
source changes after publication invalidate the fresh consumer; inserted sources
are checked on the next fresh read.

Financial collection is limited to authorized purchase preparers or Finance
Managers on extracted draft revisions. Finance may create analytical results
without editing upstream intake. Existing role/company ownership and audited
warehouse demand/supply/cost grants all apply. Customer-commercial warehouse grants
and native permission for every constituent order are additionally required.
Purchase access alone does not grant customer contract visibility. Confidential
readers/directors/auditors still need both cost and sales scope; auditors cannot
collect or modify evidence. Sales-only, portal and public users receive no raw
supplier costs or financial results. Global rules apply to headers and children,
including search/group/export. Native source drilldown checks native permissions.
There is no new sudo projection in the financial service and no new accounting
administrator grant. Existing formula-injection export protection is reused.

Review starts from cost attribution or Financial Analysis / Financial Exposure.
Immutable headers and lines are paginated at 20/40 records. Inspect scenario labels,
quantity/cost completeness, exceptions, raw and rounded values and source versions;
check current sources before using a historical amount. No live price/application
or customer repricing button exists.

## PR15 handoff

PR15 must consume only current authorized financial snapshots and retain exact
allocation/cost/demand IDs, company currency, grouped base UoMs, source-specific
costs, complete versus partial totals, signed delta, FX methodology/decomposition,
scenario/estimation assumptions and reconciliation. A PR11 reference is retained
for future native-authorized selling-value use; this feature does not certify that
revenue is complete or compatible for margin. Profitability additionally needs
current net selling values and complete comparable cost policy. Risk interpretation
needs independently governed thresholds. Neither margin nor risk is implemented.
Unknown, stale, estimated, disputed and conditional inputs cannot become realized
outcomes or unqualified committed exposure. PR15 remains NOT_STARTED.
