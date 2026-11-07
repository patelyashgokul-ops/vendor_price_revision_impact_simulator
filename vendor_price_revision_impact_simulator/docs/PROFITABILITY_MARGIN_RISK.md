# Projected profitability and margin risk - PR15 / DEV08

This read-only analysis covers selected affected remaining product demand, not an
entire sales order, realized accounting profit, recognized revenue or posted COGS.
No native Sales, Purchase, Inventory, price or accounting values are written.

## Financial contract

Revenue is the exact current PR11 company-currency, tax-excluded outstanding sales
value. PR11 handles native prices, discounts, taxes, quantities, FX and uncertain
order adjustments. Revenue is unchanged between baseline and revised scenarios.
There is no list-price fallback, selling-price assumption, price recommendation or
customer price application. Company rounding already present in PR11 is retained;
it is not replaced with independently reconstructed sales revenue.

Costs are sums of the exact current PR14 allocation contributions for that same
sales line, variant, company, demand class, comparison UoM and quantity. Every
financial contribution is consumed once. PR14 source-specific old/revised costs,
protected PO terms, stock values, date/MOQ/FX and scenario assumptions are reused.
No allocation, supplier price or valuation engine is duplicated. Incompatible or
stale snapshots fail closed. Exact source IDs, quantity/UoM, sales FX, protection,
cost issues and immutable source fingerprints remain traceable.

Baseline/revised projected gross profit = unchanged net revenue minus the
corresponding cost. Gross margin = profit / positive net revenue *100. Markup is
profit / cost *100 and is never used for risk thresholds. Signed profit change is
revised profit minus baseline profit. Positive-oriented profit reduction is the
negative of that change. In this unchanged-revenue phase, profit change reconciles
to negative PR14 incremental cost; no balancing adjustment is created.

Margin erosion = baseline margin minus revised margin, in percentage points.
Relative margin decline is separately labeled and requires positive baseline margin.
Relative profit reduction requires positive baseline profit. Neither is substituted
for percentage-point erosion. Decimal38 arithmetic precedes display rounding;
reported monetary values use company currency precision and percentages use two
decimals. Risk compares raw internal percentages, not the rounded display.

Zero revenue preserves supported monetary profit/loss but produces no margin
percentage. Negative revenue has no ordinary positive-sales margin; PR11 unsupported
credit/return bases remain incomplete. Negative gross profit and margins below
-100% are valid with positive revenue and are never clamped. Missing values stay
null, distinct from documented zero. A complete incremental cost delta with unknown
stock cost cannot establish complete gross profit or margin.

## Scope and aggregation

One profitability line represents an exact PR11 sales order line; it sums that
line's PR14 supply contributions rather than duplicating its revenue per source.
Two lines for the same SKU retain their individual prices and terms. Aggregates
use sums of amounts and then profit / revenue, never arithmetic averages of line
percentages. Highest known constituent-line severity is retained independently
from the aggregate amount-ratio risk, so profitable totals do not hide a critical
individual line. Persistent groups are company, exact order, product.product variant
and source customer ID, each separated by confirmed versus conditional demand.
There is no implicit commercial-parent/legal-customer rollup or mixed-company or
mixed-currency total. Aggregate source_id is interpreted only with its dimension.

All groups are **affected product scope**, not full-order margin. Shipping,
services and other unallocated components are excluded from this selected product
scope. Unattributed global discounts remain incomplete under PR11; PR15 neither
invents product splits nor claims full post-discount order profit. Incomplete
lines remain counted and visible; known complete subset amounts are separately
labeled in partial_amounts, never promoted to complete company/customer totals.

Conditional quotation/portfolio totals are alternative PR10 scenarios. Each needs
its exact current confirmed financial and profitability baselines. A complete
conditional revised-profit contribution is scenario revised profit minus confirmed
revised profit. Do not add a whole scenario total to confirmed profit or combine
standalone alternatives. Company/order/product/customer aggregates retain their
demand class; a scenario header explicitly includes its confirmed portion.

## Governed risk policy

The existing PR04 published company policy remains the sole authority. The analysis
date is PR11's explicit sales FX date, or the recorded calculation context date
when that snapshot has no FX date. Product-specific margin rows override category,
then company default, using the existing lookup. Order/customer/company aggregates
use the company default; product aggregates use the corresponding product policy.
No thresholds are averaged. Store selected policy ID, version, date and exact rules.

Existing minimum gross margin is the inclusive critical boundary; target gross
margin is the inclusive warning boundary above minimum. Above target is normal
for that dimension. Thus under minimum15/target25: 14.99 and15 are critical,
15.01 through25 warning,25.01 normal. Published policy validation enforces
0 <= minimum <= target <100. Observed negative margins are not policy thresholds
and can be arbitrarily negative.

PR15 extends the same governed margin row with an explicitly enabled positive
material erosion threshold in percentage points, and negative-profit-critical
switch (default enabled). Erosion is disabled for pre-existing policy rows until
explicitly configured; disabled is distinct from an assumed zero threshold.
Existing PR04 immutable publication, Configuration Administrator authorization,
company scope, versioning and before/after audit apply to the added fields.

Positive incremental cost/profit reduction uses existing company-currency PR04
[min,max) exposure bands (open final band): low maps normal, medium warning,
high high, critical critical. No INR amount is hardcoded in production. In the
unchanged-revenue scope, positive cost increase and profit reduction coincide;
reasons retain both interpretations without adding their amounts together.

Input completeness and policy availability gate primary assessment. Missing
revenue/cost/percentage or policy yields review_required, never normal. Known
independent severe flags are retained. Otherwise negative-profit and minimum-margin
critical flags precede high exposure, warning margin/material erosion and normal.
All reasons survive; one primary severity is the maximum applicable revised rule.
Risk basis remains fully_verified, estimated or scenario_only as appropriate;
numerical scenario risk is not realized loss. Customer price protection is an
independent context: fixed verified terms add a warning when profit falls, while
unknown/review terms remain an explicit uncertainty, never permission to reprice.

Baseline and revised minimum/target margin risks are assessed separately. Revision
effect is new_warning, new_critical, warning_to_critical,
existing_critical_worsened, existing_risk_unchanged, risk_improved,
no_new_margin_risk or undetermined. Improvement uses negative erosion; pre-existing
low margin is never wholly attributed to the supplier revision. Material exposure
and erosion flags remain visible even when the margin-category transition is
unchanged.

## Snapshots, authorization and currentness

Immutable margin.snapshot, margin.line, margin.aggregate and margin.risk records
retain inputs, source versions, raw/rounded results, status, exact risk reasons and
thresholds. Public create/write/unlink/copy and nested/context forgery cannot certify
results. Authorized purchase preparers and Finance calculate via the server action;
auditors only read. The publication savepoint is atomic. Unchanged exact inputs
reuse the current snapshot. Material policy/source changes preserve historical
values and require a new assessment, not rewriting history.

The current getter verifies the upstream PR14/11 authorities in a fresh transaction,
then exact policy and source fingerprints. Shared existing-source locks and existing
company/batch serialization protect calculation and concurrent policy/publication.
No business manual commit or unrestricted sudo is introduced. Serialization failures
require a fresh-transaction retry. Existing-row locks do not freeze future inserts;
currentness is checked again before consumption. No permanent global freeze is
claimed. A conditional comparison also verifies its confirmed baseline.

Raw costs and derived profits/margins/reasons have identical strict confidentiality.
All persistent headers/children require selected company, active user, explicit
warehouse supply/cost/demand grants, explicit customer-commercial grant and native
permission for every constituent order. Purchase-only has no automatic customer
permission; Sales-only has no cost-derived result access. Portal/public receive no
margin or risk data. Company and parent-scope global rules cover search/group/export
and related records. Native sales drilldown delegates PR11's native source checks.
Existing formula-injection protection applies at export boundaries.

Review uses Financial Analysis / Profitability & Margin Risk, or the financial
snapshot's calculation wizard. Lists are paginated20/40; current-source checks are
explicit instead of rebuilding every list row by default. The bounded stale search
fails closed beyond1000 authorized historical snapshots. Filters cover negative,
critical/below-target margins, material erosion/exposure, fixed terms, old/new risk,
improvement, confirmed/conditional and incomplete inputs. Do not interpret stored
historical risk as current without checking its sources.

## Verification and limitations

See evidence/DEV-08-pr15-summary.md and TEST_REPORT.json for actual results. Setup
or this document alone is not PASS evidence. Relevant PR11/14/15 tests, exact PR14
archive upgrade/preservation, real-session races and native/upstream no-mutation
probes are required. Reference: revenue28000, costs20000/21500, profit8000/6500,
change-1500, reduction1500, margins28.57142857/23.21428571, erosion5.35714286pp,
relative reduction18.75%. With minimum15/target25/erosion5 and low exposure band,
revised risk is warning; all procurement assumptions remain scenario-only.

Only the executed100-line workload is measured if retained in real logs.500,
2000,10000-input stress and peak memory remain NOT_MEASURED unless separately run.
Manual browser UAT remains NOT_RUN. Exact FIFO warehouse/lot acquisition lineage,
future landed components and uncertain PO amendments retain PR14 limitations.
Full order discount/service allocation, parent-customer rollup, actual accounting
profit, price recommendations, approvals and application are not implemented.

## PR16 handoff

Consume only get_current_profitability with current compatible PR11/14 references.
Retain exact company/customer/order/line/variant, allocation contribution IDs, demand
class, scenario, source versions, currency/UoM, net revenue, old/revised costs,
incremental exposure, profits, margins, erosion, signed change/reduction, risk reasons,
policy versions and raw/reported/partial completeness. Independently reconcile full
source scope and unresolved discounts/FX/cost assumptions before any sign-off.
Historical or scenario-only figures cannot become accounting outcomes or approvals.
PR16 full-source reconciliation/sign-off, PR18 repricing and later execution remain
NOT_STARTED. Stop after PR15.
