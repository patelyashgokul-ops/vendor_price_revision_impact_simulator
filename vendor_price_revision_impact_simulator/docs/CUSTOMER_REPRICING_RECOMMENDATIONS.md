# PR18 - analytical commercial recommendations

This register compares conditional ways to protect gross margin. It never edits or
sends quotations, changes discounts/pricelists/supplier prices/POs, reserves stock,
revalues inventory, posts accounting, approves supplier terms or executes decisions.
PR19 management routing/maker-checker is a future prompt. Review is not approval.

## Sources, targets and objectives

Create from the current PR17 scenario form. Exact immutable PR11/14/15/16/17 source
IDs, versions, financial scope, cost/revenue confidence and source fingerprints are
retained. Current PR17 financial verification and PR16 readiness cannot be waived.
Incomplete source data may produce an explicitly review-required register; it does
not produce a verified customer price. Stale sources require upstream revalidation.

Company target comes from the governed PR04 company margin policy. Each line uses
the existing PR15 product/category/company precedence, not the largest available
percentage. Target inversion supports conventional0 <= m <100 percent only.
For cost C, required tax-excluded revenue is C/(1-m/100), never C*(1+m/100).
The signed raw gap and nonnegative rounded recovery requirement remain separate.
Already-satisfied targets produce no unnecessary customer price increase or decrease.

Default objective is independent exact sales-line targets. The header company
selected-scenario target is informational and is not allocated across unrelated
orders/customers/conditional quotations. Explicit same-order recovery requires the
published recommendation_recovery_scope option, one coherent target and complete
source lines. Eligible revenue shares allocate the same-order gap deterministically.
Different product targets require independent line analysis. A fixed confirmed book
cannot transfer its recovery gap onto an unrelated quotation. Alternative supplier
or quotation scenarios must share exactly the same PR16 baseline and quantities;
their totals and benefits are never additive.

## Prices, rounding, discount and taxes

PR11 actual source prices, discounts, fiscal position, mapped taxes, currencies,
UoM and verified FX remain authoritative. Current product list_price/pricelist is
never a substitute. Required company net-unit values and recommended Odoo price_unit
references have separate labels. The latter uses the original sales currency and
sales UoM. Eligible subsets use the frozen comparison UoM. Whole-line minimum net
unit reference does not establish permission to amend that line.

Native Odoo20 _prepare_base_line_for_taxes_computation and account.tax tax details
provide isolated dictionaries, without an operational .new/write/price assignment.
An affine native forward probe solves display price, applies the source discount
once and validates the result through native forward tax calculation at the actual
eligible source quantity. Included/excluded, fixed, division/group taxes use actual
Odoo semantics; unsupported/custom nonaffine behavior is review-required. Negative
source discounts retain native surcharge semantics.100 percent discount cannot be
inverted into a finite positive net price. Unallocated global discounts retain
unknown product revenue and block exact verified price recommendations.

Minimum display price rounds upward to the source currency increment. Native
eligible subtotal/customer total/tax and company-currency revenue are recalculated;
rounding is checked against the target rather than assumed. A ceiling rounds
downward. Caps/floors that conflict or unsupported forward rounding produce review,
never a falsely satisfied target. Aggregate revenue rounding and unit price rounding
are different:21500/.75 rounds to28666.67 total, while143.3333 per unit rounds to
143.34, so200 repriced units yield28668. The raw target remains in evidence.

## Commercial eligibility and partial demand

Fixed-price verified commitments have zero direct eligible quantity. Unknown terms
require customer-contract review. A source-bound PR11 verified adjustment review
plus documented notice/customer-acceptance conditions is required for confirmed
order/sent-offer amendment review. Role membership or an arbitrary input flag does
not create a customer right. Even eligible classifications mean review only.

Unsent draft quotes may be reviewed under the published draft-review policy if no
fixed-price evidence overrides them. Sent valid offers are offer-validity review
without verified adjustment evidence. Expired offers require review, never automatic
permission to raise/send prices. Cancellation/quote confirmation, source terms,
validity and delivered quantities are checked by upstream current getters and the
recommendation date fingerprint. A confirmed quote cannot remain a current draft
opportunity. Source native order states are used, not simulated approval flags.

Outstanding = protected + eligible + review-required quantities within each exact
comparison unit. Delivered quantity is separate historical evidence, not added to
future outstanding demand. Conditional quotation quantity is a scope dimension,
not another additive supply/demand category. An optional eligible subset can only
restrict already eligible outstanding quantity. It cannot exceed demand, include
delivered units or override a fixed/unknown contract.

For a line/order gap, only its legitimately eligible quantity funds the uplift.
200 outstanding units with100 eligible use100, not200, as the recovery denominator.
No eligible quantity means customer repricing is unavailable; no division by zero.
Unchanged quantities keep the original source unit price, discount and tax basis.
Their forecast uses native remaining-quantity calculation and source/company
currency rounding; its difference from a proportional share of original revenue
is disclosed in unchanged_price_evidence. Required eligible revenue is solved
against that native remainder. Percentage caps use actual normalized native net
unit price. Calculation versionv2 invalidates former current recommendations.

## Constraints and alternatives

Optional published company maximum net uplift percent applies to recommendations;
blank means no invented cap and explicit zero means no increase. Per-line maximum/
minimum net prices use original sales currency/UoM with a reason. These are
restrictive documented/hypothetical bounds, never permission grants. Caps can leave
an unrecovered gap, which stays visible. No demand elasticity, conversion probability,
competitor price or guaranteed customer acceptance is invented.

Separate options retain additional net revenue, reduced procurement cost, projected
profit improvement, remaining target gap and risk reasons. Keep existing price,
customer review, supplier negotiation and exact PR17 alternatives stay separate.
Explicit combined options pair the actual customer candidate revenue with an exact
supplier scenario cost and recompute profit/margin/risk, never sum two claimed
savings figures. Supplier ceiling is N*(1-m), then (ceiling-unchanged cost)/eligible
new procurement only for a single linear, same-FX product/UoM basis. Multiple tiers,
grouped/nonlinear purchases, landed/date/PO/FX alterations, zero procurement or
incomplete cost require explicit PR17 alternatives instead of a fabricated ceiling.
A ceiling is a financial bound, not an accepted or achievable supplier offer.
Already-satisfied costs are not increased to that bound.

PR15 profitability supports an optional explicit baseline revenue for genuine
before/after customer-revenue comparisons. Existing three-argument callers retain
identical behavior. Independent PR16 profit equations have the same optional basis;
controls verify target inversion, quantities, price recovery and option risk. Actual
baseline cost/profit is preserved when revenue changes; no synthetic baseline cost
is created. Company policy inclusive risk boundaries remain unchanged: meeting25%
mathematically does not itself mean a risk-free or commercially accepted action.
Per-line projected outcomes and risk are retained with line evidence.

## History, review and security

Every generation is immutable, versioned and source-fingerprinted, with exact scope
and assumptions. Unchanged regeneration returns the same current record. Changed
source scenario/target/tax/discount/contract/date creates stale history until current
sources are rebuilt; generating then creates a linked version. Failed line/option
publication rolls back atomically. Repeated retries do not duplicate current rows.
Archive/review events append without erasing prior evidence. Regeneration after
archive creates a new version. Preferred-for-review requires an exact current
financially complete option and reason/evidence; it never approves or applies price.

Only scoped Finance generates/reviews. Confidential readers/auditors retain read-
only source-bound financial access. All headers/lines/options/reviews require the
selected company, all warehouse supply/demand/cost grants, customer-commercial and
native sales rights inherited from the exact PR17 cohort. A target price can reveal
cost, so Sales/Purchase roles alone gain no new financial disclosure. Global rules
apply to search/group/export and related fields. Public/portal are denied. Source
SO/quotation drilldown checks native read authority. Untrusted context flags, direct
ORM writes, child commands and cross-company inputs cannot forge verification.

Company/batch/scenario locks serialize generation, scenario input edits and policy
publication. Upstream shared source locks and fresh-transaction current getters
protect native changes. Competing changes may require serialization retry; completed
historical evidence is not a permanent freeze of future business records. No manual
business commits, source repairs or additional external workers.

## Verification and PR19 handoff

Use TEST_REPORT.json and the PR18 A-J handoff for actual executed counts, failures,
benchmarks and limitations. The separate performance probe requires real500/2000
line cohorts with native candidate prices and exact source counts, elapsed time,
SQL queries and sampled process RSS. The2000-line cohort has2000 records each
across PR11/13/14/15/17:10000 relevant stage references, not10000 independent orders.
Only executed evidence certifies these measurements. Manual browser UAT and
production/cold capacity are separate and are not inferred from synthetic timings.
Unknown warehouse/lot FIFO lineage and unsupported customer adjustments remain
upstream limitations. Recommendations never improve missing evidence into facts.

PR19 must consume only get_current_recommendation, exact source/baseline/scenario
IDs, frozen target policy, eligible/protected/review quantities, price/tax/discount/
FX/UoM evidence, proposed conditional benefits, residual gaps, financial controls,
commercial feasibility, risk and immutable review history. Future Sales/Purchase/
Finance/Director authority and maker-checker rules need a separate governed approval
implementation; none is executed here. No-price-application invariants remain.
STOP after PR18. PR19 NOT_STARTED.


Native partial rounding regression:3 units atUSD3.35 less10%, rate90, original
company revenue814.50, hypothetical scenario cost619.86, target826.48. Native
unchanged2-unit subtotalUSD6.03 =542.70. USD3.50 for1 eligible unit totals826.20
(margin24.97458243%), though proportional splitting would claim826.50. Corrected
USD3.51 totals827.10 and meets25%. A USD3.15 net cap retains displayUSD3.50 and
shows the actual0.28 residual. No source prices/discounts change.
