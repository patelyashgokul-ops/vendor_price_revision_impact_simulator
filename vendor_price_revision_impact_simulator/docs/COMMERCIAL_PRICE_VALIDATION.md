# Commercial price validation — PR-08

This phase compares vendor unit prices. It never applies prices, approves a
commercial agreement, changes SO/PO commitments, allocates supply/demand, computes
exposure/margin, or changes accounting/stock valuation. PR09 remains unstarted.

## Operators and validation gates

Start with an extracted batch on an editable draft, current PR06 structural
validation and current PR07 exact product.product resolution. Excluded, blocked,
ambiguous and stale product rows cannot complete a commercial comparison.

1. Select **Propose Commercial Context** on the batch. Explicitly identify net
   tax-exclusive supplier-price basis, any percentage discount, inclusive proposal
   end date, old baseline date basis, and common-rate or date-specific comparison.
2. Add exact supplier UoM aliases where needed. PCS/EA/BOX are never guessed. Each
   alias selects an existing UoM; this wizard creates no product/UoM master records.
3. A different Purchase Manager reviews the interpretation with a reason. Scenario
   FX instead requires a different Finance Manager and an explicitly enabled PR04
   finance-governed scenario policy. Interpretation verification is not price approval.
4. Run **Validate Commercial Prices**. Review current row status and plain unit-price,
   delta, currency, comparison-unit, normalized MOQ and effective-date columns.
   Drill into the immutable result for the calculation, rates, baseline candidates,
   rule selection, source/correction references and retained issues.
5. Correct source data through PR06, refresh product resolution where needed, and
   propose/verify a new interpretation when its material evidence changes. Re-run
   commercial validation; old decisions and issues remain. Unchanged runs reuse the
   current snapshot without duplicate issues or versions.

Purchase Users operate own accessible drafts; Purchase Managers operate company
drafts. Confidential readers can inspect authorized company results. Configuration-
only, Sales-only, portal/public users have no confidential source/cost access.

## Target-version findings

The verified local baseline remains Odoo Community 20.0. `uom.category` is absent.
Units use `relative_uom_id`, `relative_factor`, stored `factor` and `parent_path`.
Odoo20 `_compute_quantity` multiplies by source.factor / target.factor and
`_compute_price` uses the inverse dimensions. The conversion helper itself does
not enforce compatibility; APP06 explicitly checks `_has_common_reference`,
active units, all ancestor factors and positive values before conversion.

Supplier rules provide `uom_id`, min_qty, price, discount, currency, company and
inclusive date_start/date_end. `_get_filtered_supplier` supplies standard scoped
variant/vendor eligibility. `_select_seller` normally ranks eligible discounted
prices in company currency, then sequence and ID; it does not inherently prefer
company/variant specificity. Its FX fallback and an arbitrary ID tie are unsuitable
for an audited ambiguous comparison. APP06 uses the standard eligibility helper,
then the explicit conservative selection contract below.

Local purchase RFQ code can fall back to standard accounting cost when no seller
exists. APP06 never calls that fallback and never labels it a supplier baseline.
No recent PO or accounting-cost substitution is implemented.

## UoM and precision

Comparison basis is the exact variant's base UoM. Quantity and price conversions
are inverse: 2 Boxes of10 become20 Pieces; INR1150/Box becomes INR115/Piece.
Compatible Kg/Gram conversions use the same verified reference semantics. Different
hierarchies (Kg/Piece), inactive or missing/invalid factors block normalization.
Packaging text alone is not a conversion. Verified aliases capture exact UoM and
ancestor evidence; changing it requires renewed interpretation verification.

Numeric inputs are bounded to128 characters,38 coefficient digits and exponent
magnitude1000; unsupported inputs are rejected. Decimal calculations use 38
significant digits, retain source/canonical decimal
strings, and avoid display-rounded inputs. Standard supplier master float values
are captured through their decimal string representations; precision cannot exceed
the source master data. Company-currency rounding is stored separately for reporting.
The decision tolerance is explicitly zero so display rounding cannot hide a unit
price change. Missing monetary values are absent/null, not zero.

Only explicitly verified tax-exclusive net supplier terms complete comparison.
Known percentage supplier discounts and a reviewed proposed percentage discount
are normalized before comparison. Tax-inclusive/unknown basis, discounts outside
0–100 or unevidenced nonrecoverable charges remain incomplete. No freight/duty/tax
amount or weight-per-piece relationship is invented.

## Currency and FX

Resolve exact active res.currency names from PR06 input/fallback provenance. Company
currency is explicit. Same currency uses identity1 with an explicit method label;
unrelated currencies never receive a fabricated1 rate.

Use the published PR04 `currency_rate_policy`: proposed effective date, explicit
company reference date, or finance-governed scenario. Actual Odoo20 `_get_rates`
uses rates strictly before the requested date and root-company rates before shared
rates, but can fall back to an earliest future rate or1. APP06 reuses the verified
rate ratio (target technical rate / source technical rate) with explicit normal-user
company/rate searches and provenance. Both source and company technical rates must
exist before the requested date. The fallback paths are refused. This strict cutoff
is documented: a28 October fixing uses eligible records dated before28 October.

Root-company rate inheritance is allowed only when that root is authorized and
selected. Another company's rate is never queried as a price source. Future actual
FX dates are incomplete; use a documented current/past company reference date or
an explicitly permitted Finance-verified hypothetical scenario. No external rates
are fetched and no currency/rate records are written.

Each conversion captures company, source/target currencies, requested date, actual
rate-record IDs/dates/company/technical values, applied ratio and method. Scenario
rates record verifier, context and external reference and are visibly hypothetical.
A single scenario quote supports common-rate comparison only, not date-specific
attribution. Currency precision and the rounded reporting amount are separate.

Common-rate comparison converts old/new at one selected date to isolate supplier
terms. Date-specific comparison uses the old baseline date and policy-selected new
date. For equal source currencies, decomposition is explicitly
`(new-old)*old_rate + new*(new_rate-old_rate)`. USD10 at90 and USD11 at94 yields
900 ->1034, supplier component90, FX component44, total134. Common-rate94 yields
a94 delta instead. Different source currencies can compare on a common company
basis, but isolated supplier/FX components are marked unavailable. These are unit
price assumptions, not accounting FX profit or realized recovery.

## MOQ, tiers and dates

MOQ is expressed in source units and normalized to the product base unit. Baseline
lookup uses the proposed row's threshold as an explicit comparison quantity;
`batch.resolve_vendor_tier(product_id, quantity, quantity_uom_id, date)` also accepts
an explicit quantity for later consumers. It cannot accept an arbitrary product
outside this batch's current resolved variants and never derives SO/PO demand.

Distinct1/100/500 thresholds remain legitimate. Proposed rows with equal normalized
thresholds and overlapping inclusive periods conflict across units/currencies.
A sorted interval sweep detects overlap clusters without quadratic row-pair work;
related-row previews are bounded. Baseline selection excludes thresholds above the
requested quantity. Within an unambiguous scope, the standard eligible discounted-
price/sequence order is preserved. Nonmonotonic price tables can select an eligible
lower threshold; highest MOQ is not an unconditional rule. The reference decreasing
price table selects1/100/500 at quantities80/120/600, matching standard Odoo20.

Default old as-of date is the day before proposed start; an explicit reviewed old
date must also precede proposed start. Start/end dates are inclusive; proposed end
before start is invalid. PR04 future/backdated/expired-offer policies apply. Historical
proposal evidence requires review and does not authorize backdated application.
Existing future-dated vendor rules overlapping the proposal require commercial
review. Existing open-ended old terms are comparison evidence, never silently closed
or replaced; future application must independently resolve their continuation.

## Baseline selection and history

Bulk-scope supplierinfo to exact vendor, batch company/shared company, resolved
templates and applicable variants. Never expand to a parent vendor. Apply dates,
compatible units and normalized quantity eligibility. APP06 explicitly prefers
company terms before shared terms and variant terms before template fallback. It
then uses eligible normalized discounted price and sequence. Conflicting duplicate
threshold/sequence rules or unresolved equal-ranked alternatives require review;
record ID never decides conflicting economics. Invalid candidate terms are explicit
conflicts. Multi-currency ranking requires guarded baseline-date FX evidence.

Snapshot the chosen supplierinfo ID, company/vendor/template/variant, quantity,
source and net price, discount, currency, UoM factors, inclusive validity, write date,
as-of/observation dates, candidates and selection contract. Accounting cost is never
an old vendor price. Missing baseline leaves a potentially normalized proposal
without verified old price, delta or percentage.

Current records cannot prove historical agreements. Baselines before the observation
date require an independently reviewed, documented historical attestation. This is
an explicit verifier assertion tied to the captured supplier-rule evidence, not
forensic reconstruction or an automatically inferred agreement. Without it the
baseline is unverified/unavailable and no delta is calculated. A subsequent rule
edit/insertion makes that attestation stale and requires a new interpretation.

## Snapshots, current status and security

One immutable result per changed row basis retains version, previous result,
PR06 result and PR07 resolution references, verified context, published policy,
input digest, actor/time, source hash and all commercial evidence. Structured issue
records retain severity/code/message/version/current linkage. Original bytes, raw
cells, corrections and product mapping history remain unchanged. Note-only source
corrections require upstream revalidation but reuse equivalent commercial evidence;
future consumers must capture the current PR06 reference as well as the comparison.

Row statuses are pending_product, pending_validation, commercially_valid, needs_review,
blocked, baseline_unavailable/conflict, fx_rate_missing, uom_invalid, tier_conflict,
date_conflict, stale and excluded. Exactly one status counts per row. Normalized-
proposal counts and issue counts are separately labeled; classification counts
include only currently valid comparisons. Old zero has an undefined percentage,
with new_from_zero/zero_to_zero classifications, not a missing-baseline fallback.

Public create/write/copy/delete cannot forge results, verifiers, companies or audit
history. Mandatory company/active-user rules intersect role permissions. Purchase
and confidential readers gain narrowly scoped read access to published PR04 policy
and its definitions, not draft-policy mutation authority. This permits the same
current status to be assessed by authorized read-only roles. Wizards check linked
batch/context access and company, including context defaults and nested alias edits.
Stored supplier costs are company scoped. Baseline references are immutable integer
identities plus snapshots, avoiding live related-price traversals. Moved-product
current labels are masked and related exports guarded; original authorized snapshots
are retained. Standard export privilege and formula-prefix output escaping remain.

## Transactions, bounds and handoff

Validation locks company then batch and read-locks existing product, supplier, UoM,
currency and rate evidence through transaction end. Savepoints publish complete row
sets or retain a safe failed/retry state. Serialization/deadlock errors require a
fresh transaction; business methods never commit intermediate work. Current getters
recompute fingerprints and do not trust cached historical statuses. New phantom
master records are detected in a fresh transaction; existing-row locks do not freeze
all master inserts or external services.

Bulk candidate evidence is capped at10,000 per type, aliases 100, overlapping-row
previews 40, and global status searches 20,000 authorized rows. Overflow requires
review rather than arbitrary truncation. PR07's existing5000 identity-candidate bound
still applies upstream;10000 source rows need not represent10000 distinct products.
The 500-row workload is measured; larger workload sizes/peak memory are not claimed
as measured without corresponding evidence. Manual browser UAT is not claimed.

PR09/PR14 must call `get_commercially_valid_rows()` immediately before consumption
and retain exact variant/company/vendor, current PR06/PR07 references, commercial
snapshot/version/digest, common UoM, normalized prices/currency/rates, quantity tier,
effective/as-of dates and explicit unresolved cases. Keep consumption in the same
transaction, recheck after relevant edits, and supply actual quantity/date context
before resolving tiers. A per-unit delta is not demand, total exposure, realized
benefit, gross margin, approval or authorization to apply a price.

Stop after PR08. No supply allocation or later financial/application engine exists.
