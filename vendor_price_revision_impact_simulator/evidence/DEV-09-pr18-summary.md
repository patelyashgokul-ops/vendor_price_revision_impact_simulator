# APP06 PR18 / DEV09 - implementation, testing and PR19 handoff

## A - Environment and prerequisites

Odoo20.0 Community FINAL, Python3.14.6, PostgreSQL18.4, Windows. Existing major
version preserved. Official [Community builds](https://nightly.odoo.com/) and
local release/source checked at development start; see pr18-predevelopment-audit.json.
PR00-17 supporting evidence and exact102-file PR17 source archive verified before
edits. All execution used owned allowlisted synthetic databases on loopback55449,
HTTP/cron/external writes disabled. No production credentials or data. Actual
invocations, databases and timestamps appear in TEST_REPORT.json and retained logs.

## B - Implemented behavior

Immutable recommendations, exact-line evidence, comparable alternatives and
append-only review records consume current PR17 scenarios, PR16 readiness, PR11
sales, PR14 cost and PR15 risk with frozen governed PR04 policy. Gross-margin
inversion is C/(1-m), with finite0<=m<100, upward currency rounding, signed gap
and separate nonnegative recovery. Missing cost/revenue/policy remains unavailable.
Optional explicit baseline revenue in shared PR15 and independent PR16 equations
preserves genuine before/after profit when customer revenue changes; exact AST
checks prove all previous three-argument behavior identical. PR16 empty risk JSON
now accepts its native False representation as an empty list, with readiness strict.

Independent exact-line targets are default. Explicit published same-order policy
permits deterministic eligible-original-revenue proportional recovery within one
order with one coherent target. Different orders and conditional quotations never
inherit another confirmed-book gap. Delivered quantity is excluded. Eligible,
protected and review quantities reconcile to outstanding; conditional quantity is
a separate dimension, not additional demand. Fixed commitments stay protected,
unknown adjustment rights require review. Unsent drafts permit analytical review
only under policy. Sent valid or expired offers remain review unless current
verified rights and recorded notice/amendment conditions support review; expiration
does not grant rights. Confirmation/cancellation/source changes invalidate evidence.

Native Odoo20 tax base-line semantics invert excluded/included/fixed/group taxes,
discounts and negative-discount surcharges. Candidate display price remains in
original sales currency/UoM, separate from net comparison-unit/company-currency
financial reference. Source FX/UoM conversion is explicit, discount applied once.
Affine/positive-slope probe, directional rounding and native forward recomputation
check the actual eligible subtotal. Zero/100% discounts, unsupported/nonlinear
pricing, global unallocated discount or missing basis remain review/incomplete.
For partial repricing the unchanged portion also uses native original-price/
discount/tax/quantity forward calculation, source-currency rounding and company
FX rounding. Its disclosed difference from proportional revenue is included in
the projected total. Percentage caps use actual normalized native net unit price.
Calculation version advances to v2; former recommendations require revalidation.

Published maximum net uplift and exact-line source-currency/UoM floors/caps are
restrictive documented assumptions, never invented customer permission. Caps round
down, required prices round up, residual gap remains visible. Already-satisfied
targets keep existing price. Customer revenue recovery and supplier cost reduction
stay separate. A single linear same-FX/single-product/proposal supplier ceiling
uses N*(1-m), unchanged supply cost and eligible new procurement only. Multiple
tiers, FX/landed/date/PO alterations, multiple products, zero procurement and missing
cost instead require explicit current PR17 alternatives. Already-good costs are
never raised to the ceiling. Combined outcomes recompute revenue/cost/profit/risk;
separate benefits are never simply added. Financial completeness, commercial
feasibility and risk remain separate, with explainable review priority.

Fingerprints bind sources, versions, date, target policy, assumptions, prices,
eligibility and controls. Unchanged retries reuse the same record; changes require
revalidation and linked history. Failed option publication rolls back all PR18
rows. Review/preference/archive events do not approve/apply; archive regeneration
creates a new version. Company/batch/scenario and upstream source locks serialize
generation with concurrent business/policy/terms changes; fresh retries reject
stale or revoked source access. No business commits or privilege elevation.

## C - Actual changed files and purposes

- __manifest__.py
- models/__init__.py
- models/profitability_math.py
- models/recommendation.py
- models/recommendation_engine.py
- models/recommendation_math.py
- models/reconciliation.py
- models/reconciliation_controls.py
- security/recommendation_security.xml
- tests/__init__.py
- tests/test_module_foundation.py
- tests/test_recommendations.py
- views/recommendation_views.xml

recommendation_math.py supplies target/rounding/eligibility equations;
recommendation_engine.py integrates frozen sources, native pricing and alternatives;
recommendation.py supplies governed policy, immutable models and Finance wizards.
Security XML protects all headers/children/wizards; Community views provide readonly
registers, source drilldown and analytical review. Manifest/imports register them.
test_recommendations.py adds 39 meaningful cases; foundation expectation adds
the one implemented submenu while preserving all previous assertions. Shared math
changes and empty-JSON guard are precisely checked against the old archive; every
other prior business/security/test file is byte-identical. Documentation:
docs/CUSTOMER_REPRICING_RECOMMENDATIONS.md, TESTING_SETUP.md, progress/report and
pr18-* synthetic verification scripts/logs. Source108-file ledger: ae4bc60390222ee1f6c7e273f1c9a56a4405c43fd4e5634b8c21731c55dcf2dc.

## D - Executed financial references

| Measure | Actual asserted result |
|---|---:|
| Current net revenue | INR28000 |
| Revised cost | INR21500 |
| Current gross profit | INR6500 |
| Current margin |23.21428571%|
| Target margin |25%|
| Required net revenue before rounding |28666.666666...|
| Rounded-up aggregate requirement |INR28666.67|
| Additional net revenue required |INR666.67|
| Supplier total cost ceiling |INR21000|
| Unchanged60 stock +40 protected PO cost |INR10000|
| Eligible new procurement |100 units|
| Hypothetical supplier unit ceiling |INR110|
| Alternative cost reduction |INR500|

All200 fixed-price SO units stay protected with no candidate display price. A
separate verified-adjustable100-of200 example requires INR146.67 on eligible units
and yields INR667 extra after unit rounding; unchanged quantity retains original
revenue. Unsent draft100 has its own INR1333.34 gap and price153.34, independent
of the confirmed-book gap. Sent valid offers without amendment rights stay review.
Actual10% discount candidate170.38, included18% tax candidate180.94; grouped/fixed
tax and negative-discount cases execute native forward checks. USD90 conversion
with box10 sales UoM yields USD17.04/box on100 comparison units and reaches25%.
100% discount and missing FIFO/global-discount cases stay incomplete/review.
The new partial-FX regression reproduces a real pre-fix miss:3 units atUSD3.35
less10%, rate90, original revenue814.50, scenario cost619.86, required826.48.
Native unchanged2-unit subtotalUSD6.03 gives542.70. USD3.50 on1 eligible unit
would total826.20 and margin24.97458243%, despite the former proportional forecast
claiming826.50. Corrected candidateUSD3.51 yields827.10 and margin above25%.
A restrictive USD3.15 net cap correctly leaves candidateUSD3.50, total826.20 and
visible INR0.28 residual; it is cap-constrained, never target-reached. Source prices
and discounts remain unchanged. Failed reproduction and passing regression retained.
Delivered40/open60 quantity is checked. A1% cap produces141.40 with visible residual;
floor/cap conflict is not verified. Supplier110 gives total21000/margin25%; explicit
combined alternatives recompute margin with actual candidate revenue.

## E - Commercial interpretation and limitations

Candidate prices are analytical review references, not amendments or authority.
Fixed confirmed prices and uncertain contracts stay protected/review; quote
opportunities have exact cohorts and validity evidence. Unrecovered gaps, caps,
conditions, risk and missing inputs remain visible. Supplier ceiling is a financial
bound, not a feasible/accepted offer. Hypothetical recovery is never realized
profit/cash. No elasticity, probability, competitor data or invented cap. Current
PR16 strict readiness and PR17 completeness cannot be waived by assumptions.
Documented projections remain projected, not accounting valuation or actual cost.

## F - Security

Only source-scoped Finance can generate/review. Confidential readers/auditors are
read-only. Active selected company, warehouse supply/demand/cost grants, customer
commercial grants and native sales rights protect all related derived pricing and
supplier costs, searches/groups/exports and direct ORM access. Sales/Purchase alone
cannot read or calculate derived cost/margin recommendations. Foreign-company,
forged context, direct create/write/unlink, revoked customer grant, auditor mutation
and portal/public negatives execute. Native source drilldown checks access. Global
rules remain in force; no sudo financial disclosure or approval bypass.

## G - Real automated evidence

| Gate | Result | Evidence |
|---|---|---|
| Actual PR17 upgrade, pre-rounding source | PASS 283 tests | evidence/pr18-upgrade-update-20261031T073120+0000_milestone.log |
| FRESH | PASS 43 tests | evidence/pr18-fresh-install-20261031T084250+0000_milestone.log |
| HELPERS_VERIFY | PASS 10 tests | evidence/pr18-helpers_verify-update-20261031T085411+0000_quick.log |
| TARGETED | PASS 63 tests | evidence/pr18-targeted-update-20261031T085513+0000_targeted.log |
| UPGRADE | PASS 15 tests | evidence/pr18-upgrade_verify-update-20261031T090312+0000_milestone.log |
| UPGRADE-PRESERVATION | PASS 1 probe groups | evidence/pr18-upgrade-preservation-20261031T090637Z.log |
| CONCURRENCY | PASS 12 probe groups | evidence/pr18-concurrency-20261031T091150Z.log |
| OPERATIONAL-SAFETY | PASS 1 probe groups | evidence/pr18-operational-safety-20261031T091247Z.log |
| PERFORMANCE | PASS 3 probe groups | evidence/pr18-performance-20261031T095036Z.log |

Actual PR17 archive installed with4 foundation tests, seeded/cold-captured before
PR18 schema existed, then updated with the integrated PR11-18 regression. Exact
stored history/source bytes and native states retained across 77 models;
no automatic recommendations created on upgrade. Static preservation/syntax/safety
checks: 485 PASS. Twelve real separate-session races cover duplicate
generation, PO price, receipt, valued move, FX, grant revocation, proposal, sales
price, policy publication, scenario assumptions, customer terms and quotation
confirmation. Ten repeated generations: 10.911 seconds, one header.
100 real affected lines: 3.686 seconds,100 recommendation lines, cost11500.
These are observed synthetic timings, not production capacity or a latency SLA.
The283-test broad update belongs to exact pre-rounding source 527ee0680052c95a55510ff87cc540063d6e2c381fe740208a99edb067f688eb.
After that run, only customer_line native remainder/cap basis, its calculation
version and one additional regression method changed. Exact108-file archives and
AST checks prove every other application method and all38 earlier recommendation
tests unchanged. Final-source fresh/QUICK/TARGETED and the focused actual-update
UPGRADE gate above cover the correction; preservation reruns on final source.
No claim that all283 tests reran on the later source.

Separate warm same-process generation (fixture preparation excluded), with actual
native tax/price candidates on N-1 unsent draft lines plus1 protected confirmed
line, including1 partially eligible two-unit draft line with one unchanged-price
unit, produced the following measured workload results:

| Affected lines | Seconds | SQL queries | Sampled RSS peak MiB | RSS growth MiB | Financial source references |
|---:|---:|---:|---:|---:|---:|
| 500 | 26.976 | 3593 | 389.58 | 52.95 | 2500 |
| 2000 | 267.067 | 6608 | 882.64 | 163.47 | 10000 |

The2000-line cohort binds exactly2000 records each from PR11 sales, PR13 costs,
PR14 financial, PR15 margin and PR17 detail:10000 relevant stage references, not
10000 independent orders or10000 detail rows in one model. Native confirmed/quote
prices, quantities, discounts and states remained unchanged, with22 native model
snapshots also equal before/after each eligible-pricing workload. RSS samples every20ms
measure this process, not a whole-system or fixture-build peak. These single-product,
shared-currency/tax synthetic cohorts do not certify diverse production capacity.

Historical failed attempts are retained:
- FAIL: None passed; None failed; evidence/pr18-fresh-install-20261031T064938+0000_milestone.log
- FAIL: 37 passed; 4 failed; evidence/pr18-fresh-install-20261031T065311+0000_milestone.log
- FAIL: 0 passed; 1 failed; evidence/pr18-repairs-update-20261031T071046+0000_targeted.log
- FAIL: 0 passed; 1 failed; evidence/pr18-repairs-update-20261031T082825+0000_targeted.log
- FAIL: None passed; None failed; evidence/pr18-concurrency-20261031T090825Z.log

Initial generated relation name exceeded PostgreSQL63 characters; explicit short
M2M relation repaired. Fresh37/41 exposed four issues repaired and focused PASS4:
new submenu expectation, Decimal test context, unique tax fixture names, real
PR16 empty-JSON handling. Foreign-currency fixture initially attempted a confirmed
order pricelist change; native protection held. Fixture setup moved before
confirmation and focused PASS1, without bypassing native safeguards. Any additional
probe/setup corrections appear in retained logs and TESTING_SETUP.md.

Manual browser UAT and FULL release regression NOT_RUN. Greater workloads,
10000 independent orders/detail rows, cold/production concurrency capacity and
whole-system peak memory NOT_MEASURED. Mandatory PR18 scoped gates above PASS.

## H - Business safety

Actual snapshots compare all22 native model record counts/values before/after
recommendation/review: customer/vendor prices, SO/PO, stock/reservations, valuation,
FX/cost/master data, posted journal and outgoing communication records unchanged.
23 upstream analytical model snapshots unchanged. Existing confirmed orders,
posted journal and valued done stock move retained. Fixture setup/concurrent
mutation exists only in owned synthetic probes, not application behavior. No
customer/supplier message, operational reservation, inventory revaluation,
accounting posting, management approval or live price application by PR18.
Owned runtime shut down and seven exact temporary paths removed after all gates.

## I - Progress

PR18 VERIFIED for the documented analytical scope. TEST_REPORT.json retains real
attempts and source-bound final gates; DEVELOPMENT_PROGRESS.md updated. No known
mandatory scoped failure remains. Limitations above remain explicit. This is not
a FULL release or manual UAT sign-off. STOP after PR18; PR19 NOT_STARTED.

## J - PR19 handoff, no implementation

Consume get_current_recommendation, original vendor revision and exact company/
warehouse/demand scope, verified PR16 baseline/readiness, selected current PR17
scenario/result/input versions, frozen PR04 target policy and PR11/14/15 evidence.
Retain recommendation line/option/review IDs and fingerprints, eligible/protected/
review/conditional quantities, customer protection/contract conditions, native
price/tax/discount/FX/UoM references, supplier alternatives, proposed conditional
benefit, residual gap, financial completeness, independent controls, risk reasons
and commercial feasibility. Financial sign-off requires current complete sources
and no unresolved critical financial controls; commercial feasibility is separate.

Future Sales/Purchase commercial review, Finance financial sign-off and governed
Director authority limits need exact company/currency/amount/role policies. Future
maker-checker must separate preparer from approver and revalidate authority,
conflicts, stale inputs, contract consent and approval scope on the server. PR18
preferred-for-review events confer no authority. No automatic approval routing,
approve/reject execution, customer/vendor price application, quotation rewriting,
sending, PO amendment, valuation/accounting or executive dashboard implemented.
PR19 remains NOT_STARTED and requires its own active prompt.
