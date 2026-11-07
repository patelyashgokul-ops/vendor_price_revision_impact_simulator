# APP06 PR17 / DEV09 - implementation, testing and PR18 handoff

## A - Environment

Odoo20.0 Community FINAL, Python3.14.6, PostgreSQL18.4, Windows. Addon
vendor_price_revision_impact_simulator. Existing major version preserved; no
Enterprise dependencies or version conversion. Official [Community builds](https://nightly.odoo.com/)
and local release/source evidence checked at development start. PR00-16 retained
PASS references and the exact95-file PR16 source ledger were checked before edits;
see pr17-predevelopment-audit.json. All database execution uses owned allowlisted
synthetic databases in a disposable loopback55448 cluster; no production clone,
production credentials, HTTP, cron, outgoing mail, real payments or external writes.
Actual database names/invocations/timestamps appear in TEST_REPORT.json and logs.

## B - Implementation

Immutable scenario identity, versioned input/line records, result/detail snapshots
and append-only analytical selection events preserve the exact PR16 baseline.
Clones receive new identities, independent assumptions and no copied result or
verification. Public ORM history create/write/unlink/copy is denied. Omitted products
inherit their correct original proposal; product/PO overrides stay exact.

Explicit negotiated price, fixed per-source-unit reduction, percentage discount
with explicit proposal/old base and exact verified PR08 MOQ tier modes cannot be
silently compounded. Missing/nonfinite/negative prices, contradictory inputs,
wrong currencies/UoM/vendor/product and invented surplus buying are rejected or
retained as blocked/incomplete. Explicit consolidation groups only same-cohort
residual new procurement by company/vendor/product/UoM/warehouse. No PO creation.

Common-FX price-only, combined price/FX and FX-only are labeled. Governed positive
hypothetical rates use company currency per1 source currency with an explicit
date. Old-rate-first price/FX decomposition reconciles. Commercial effective-date
changes use explicit hypothetical commitment timing/evidence, not delivery dates.
Unknown timing stays incomplete; physical supply timing/reallocation is out of
scope and requires a new upstream cohort. No currency-rate or operational dates
are changed. Exact protected PO amendments are separate unapproved hypotheses,
changing only their already allocated open source quantities in that alternative.

A separate governed scenario_landed_policy preserves the original PR13 net-price
baseline while allowing optional future components. Default excludes them. Unique
future components require the dated published permission, nonrecoverable/
not-already-included assertions and company-currency per comparison-unit evidence.
No existing stock cost or capitalized charge is counted again. Missing source cost
or unavailable original proposal remains incomplete; PR16 cannot be bypassed.

PR08 normalization and PR13 replacement tier eligibility are reused. PR14 calculate
and aggregate services operate on isolated dictionaries, not new live financial
sources. PR15 profitability, risk and amount-ratio aggregation are reused, with
unchanged exact PR11 revenue and current PR04 policy reasons. PR16 Reconciler reruns
source/quantity/cost/revenue/policy controls; independent profit/risk equations and
readiness checks validate each alternative. No divergent replacement financial
engine or context flag overrides readiness. FINANCIALLY_VERIFIED is reproducible
hypothetical analytical evidence, never commercial acceptance or actual costs.

Comparisons require the exact same baseline cohort and current complete reconciled
results. Alternatives are never additive or an opaque commercial recommendation.
Changed price/FX/date/tier/PO/landed dimensions remain disclosed. Incomplete results
cannot rank as definitively superior. Preferred-for-review is analytical selection
only; input/source changes require revalidation and history remains immutable.
Company/batch/scenario serialization and upstream native source locks prevent mixed
versions. Failed detail publication rolls back atomically; fresh retries do not
duplicate unchanged results. No business commits or sudo disclosure.

## C - Relevant files

- __manifest__.py
- models/__init__.py
- models/scenario_engine.py
- models/scenario_math.py
- models/scenario_wizard.py
- models/vendor_scenario.py
- security/scenario_security.xml
- tests/__init__.py
- tests/test_reconciliation.py
- tests/test_vendor_scenarios.py
- views/scenario_views.xml

docs/WHAT_IF_VENDOR_PRICE_SCENARIOS.md describes the contract. TESTING_SETUP.md,
DEVELOPMENT_PROGRESS.md and TEST_REPORT.json retain execution/status. Earlier
business engines/security definitions remain unchanged. One prior reconciliation
atomicity test now preserves all existing stored run/check/exception/review values
and rejects leaked results for its own batch; all other existing tests are unchanged.
pr16-source-baseline.zip is an exact checksum-verified archive, not a reconstructed
approximation. pr17-* scripts/logs retain synthetic probes and real results.

## D - Executed reference results

Same confirmed200 units, unchanged revenue INR28000, existing60@100 and protected
incoming40@100, new procurement100, old eligible price100:

| Hypothesis | Old baseline | Projected cost | Incremental vs old | Potential improvement vs proposal | Projected profit | Margin |
|---|---:|---:|---:|---:|---:|---:|
| Original115 |20000|21500|1500|0|6500|23.21428571%|
| Negotiate112 |20000|21200|1200|300|6800|24.28571429%|
| Negotiate109 |20000|20900|900|600|7100|25.35714286%|
| Negotiate105 |20000|20500|500|1000|7500|26.78571429%|

Actual fresh log markers assert all four. Fixed3 discount matches112; ten percent
from115 yields103.50 and cost20350. Old-base5 percent yields95 and negative500
incremental. MOQ100 tier109 is eligible for100 residual, while surplus500 is blocked.
Explicit40+60 buying group preserves distinct demand identities. Box/piece unit
conversion is tested once. FX90->94 on USD10->11 gives90 price +44 FX =134 per unit;
see actual PR17_FX marker for the observed rate. Protected40@100->115 in a separate
hypothesis is600 extra (total22100), with actual PO price unchanged. Missing FIFO
stock cost stays unknown; complete profit/margin and proposal improvement stay blank.
Future freight3 and nonrecoverable duty2 remain explicit hypothetical components,
never accepted landed valuation; actual gating/limitations are described below.

## E - Assumption completeness

Source baseline requires current PR16 readiness. Default strict_verified evidence
does not turn estimated stock/scenario procurement into actual accounting cost.
documented_projection permits complete projected review only. Assumptions remain
hypothetical and all source confidence is retained. Missing negotiated price, FX,
stock/PO basis, uncertain timing, ineligible MOQ or unconsumed product overrides
block complete verified results. Missing data never becomes zero or a favorable
rank. Incomparable baseline/quotation cohorts cannot be combined. Source/header
versions, original proposal, old baseline and every changed dimension remain in
provenance and immutable input/result evidence. No management/supplier acceptance
is certified. Landed policy and inherited PR13 attribution limitations cannot be
bypassed through hypothetical inputs; inspect each result's controls/issues.

## F - Security

Only scoped Finance edits/calculates/selects. Scoped confidential readers/auditors
are read-only. Company isolation, all selected warehouse cost/supply/demand grants,
customer-commercial and native-order rights protect headers and all child history.
Sales-only/Purchase-only receive no derived cost/margin or customer-contract bypass.
Direct ORM mutations, forged state/context, cross-company records, exports and
revoked source grants are tested. Public/portal cannot read scenario result/detail.
Global scope rules apply to search/group access as well. Source drilldown checks
read authority; selection grants no new source permissions. No unrestricted sudo.

## G - Actual automated verification

| Gate | Matching-source result | Evidence |
|---|---|---|
| FRESH | PASS 8 tests | evidence/pr17-fresh-install-20261031T022513+0000_milestone.log |
| HELPERS_VERIFY | PASS 7 tests | evidence/pr17-helpers_verify-update-20261031T022821+0000_quick.log |
| TARGETED | PASS 28 tests | evidence/pr17-targeted-update-20261031T022845+0000_targeted.log |
| UPGRADE | PASS 56 tests | evidence/pr17-upgrade_verify-update-20261031T023218+0000_milestone.log |
| UPGRADE-PRESERVATION | PASS 1 probe groups | evidence/pr17-upgrade-preservation-20261031T023826Z.log |
| CONCURRENCY | PASS 11 probe groups | evidence/pr17-concurrency-20261031T024010Z.log |
| OPERATIONAL-SAFETY | PASS 1 probe groups | evidence/pr17-operational-safety-20261031T024039Z.log |

35 new test methods. All final gates bind to source f377aa420b1cf28e459df5b20f7607df42b8dc33ed1d4ba0c4109e2625faecf8.
The broader actual PR16 update executed263 tests:262 passed,1 old reconciliation
atomicity test assumed globally empty tables despite deliberately retained PR16
history. The FAIL log is retained, never called263 PASS. Its stronger seed-aware
assertions are executed in the final-source follow-up. The application changes
after that broad run are an explicit rejection of the wrong common-FX label on a
two-date baseline, its regression test, and a readonly wizard source price/currency/
UoM/quantity display with four additional assertions. Existing wizard publication
behavior is AST-identical. An earlier complete39-test cold install passed on the
FX-guard source; the final UI cold install selects eight actual reference/wizard/
foundation tests. Every new scenario case executes in the final-source upgrade
follow-up; no39-test PASS is claimed for the eight-test final cold UI selection. Exact source archives, AST
checks and unchanged-file hashes prove this narrow delta. All new scenario cases,
related FX cases and the PR16 lifecycle class run again on the final-source update;
unchanged upstream tests are not unnecessarily repeated. Broader source reference:
evidence/pr17-upgrade_resume-update-20261031T015724+0000_milestone.log (1a6509588ae4635cc9ebaf26f7dd1766a53b5d5bd53d8d8e771465625e157f11).
Exact archived PR16 code was installed; operational records/source bytes plus
commercial/supply/allocation/sales/purchase/cost/financial/margin/reconciliation/
exception-review evidence were committed and cold-captured before PR17 schema.
After actual update every retained field and byte was compared. No automatic
scenario acceptance or creation. 11 real two-session races: COLLECT, PRICE, RECEIPT, VALUE, PROPOSAL, SALES_PRICE, POLICY_PUBLICATION, ASSUMPTIONS, FX, GRANT, QUOTE_CONFIRMATION.
Native22-model and upstream17-model before/after probes PASS. Ten alternatives
measured 9.470s after baseline preparation,30 exact allocation contributions.
50/100 scenarios,500/2000 product lines,10000 result references, peak memory and
query-count benchmark NOT_MEASURED. Manual browser UAT NOT_RUN. No release FULL
claim. Prior failed/interrupted attempts remain history (null counts are not PASS):

- FAIL: None passed; None failed; evidence/pr17-fresh-install-20261031T012323+0000_milestone.log
- FAIL: 27 passed; 8 failed; evidence/pr17-allocation-update-20261031T012825+0000_targeted.log
- FAIL: 8 passed; 1 failed; evidence/pr17-repairs-update-20261031T013537+0000_targeted.log
- FAIL: None passed; None failed; evidence/pr17-upgrade-seed-20261031T015504Z.log
- FAIL: None passed; None failed; evidence/pr17-upgrade-seed-20261031T015547Z.log
- FAIL: 262 passed; 1 failed; evidence/pr17-upgrade_resume-update-20261031T015724+0000_milestone.log

The initial fresh run was intentionally stopped after repeated required-empty-
JSON storage failures. Odoo20 treats an empty list as SQL NULL; issue evidence now
uses an explicit object with an items list. The focused diagnostic run exposed an archive guard reading cached display state;
the guard now reads the latest event directly. Policy/permission fixture corrections
preserve exact missing-input and real pure-role denial assertions. Upgrade setup
first hit the Finance-only guard with its retained Purchase actor, then required
explicit owner/selected-company context when resumed. Both failed setup logs are
retained; Finance authorization and company guards were unchanged. Successful
seed/cold capture preceded the actual update. Other failure details remain in
exact logs and TEST_REPORT.json; no passing assertion was weakened.

## H - Business safety

No supplierinfo application, supplier acceptance, actual PO/SO changes, customer
repricing, stock reservations/moves/revaluation, landed-cost posting, accounting
entry/bill or management approval occurs in PR17. Native writes in probes are
explicit synthetic setup or controlled competing changes. Only APP06 analytical
scenario/input/result/detail/event records are published. Owned runtime removed
after confirmed PostgreSQL shutdown. Prior upstream records remain immutable.

## I - Progress and limitations

PR17 VERIFIED for the documented isolated analytical scope; the exact ledger
contains 102 source files, SHA256 f377aa420b1cf28e459df5b20f7607df42b8dc33ed1d4ba0c4109e2625faecf8. DEV00 report and
progress updated only after matching-source gates and cleanup. Warehouse/lot FIFO
lineage, future acquisition timing, surplus buying optimization, cross-vendor
sourcing and unsupported source adjustments remain incomplete/out of scope.
Hypotheses are not accounting truth. Browser UAT/larger loads/memory are unverified.
No blocker for the documented tested scope. STOP after PR17; PR18 NOT_STARTED.

## J - PR18 handoff

Consume current authorized get_current_scenario results, not stored status alone.
Retain exact PR16 baseline, source IDs/versions/fingerprints, input identity,
product/vendor mappings, confirmed or conditional affected demand, protected stock/
PO and new procurement quantities, original and hypothetical source price, units,
FX/date/tier/landed/amendment assumptions, unchanged revenue/customer protection,
old/proposed/scenario cost and margins, potential improvements/pp changes, current
company thresholds, risk reasons, completeness and independent control outcomes.
Preferred-for-review, if selected, remains hypothetical. Future repricing proposals
need their own missing-input, target-margin, commercial protection, company and
derived-cost confidentiality controls; never mutate baseline or native sources.
No recommendations, approval routing, decisions or application implemented.
PR18 remains NOT_STARTED.
