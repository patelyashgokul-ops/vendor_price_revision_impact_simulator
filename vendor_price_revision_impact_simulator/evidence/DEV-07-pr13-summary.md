# PR13 / DEV07 — Inventory and replacement cost attribution

## A — Environment

Odoo 20.0 Community FINAL, Python 3.14.6, PostgreSQL 18.4, Windows. Addon
`vendor_price_revision_impact_simulator`. Owned disposable loopback cluster 55444;
no production credentials or databases. Native valuation uses stock.move.value,
product.value and the read-only product FIFO stack, not stock.valuation.layer.
Native source hashes: evidence/pr13-native-api-audit.json.

## B — Implementation

Immutable cost.snapshot, cost.line and cost.issue models attach exactly one result
to every current PR10 entry. Standard and AVCO retain company accounting references,
with supported-estimate allocation confidence. Reserved/free remain distinct.
FIFO preserves remaining native move portions and a reconciled company-product
pool once; warehouse/demand acquisition tracing stays incomplete. No invented
layer allocation or Standard Cost fallback. Current exact PR12 protected terms
can supply incoming costs; disputed/pending amendments retain both alternatives
without selecting a final protected price. PR08 proposals supply hypothetical
replacement costs using explicit date and per-entry buying quantity, guarded
FX/UoM and highest eligible unique MOQ. No cross-demand tier consolidation.
Native existing costs already include capitalized adjustments; nothing is added
again. Net replacement references explicitly exclude future unevidenced charges.
Quantity/cost confidence is separate; unknown value is null, documented zero is
numeric. Decimal precision 38 and separate currency rounding are retained.

Savepoint publication, company/batch serialization, shared source locks, complete
fingerprints, strict fresh getters and immutable previous versions protect audit
history and idempotence. Native source drilldowns retain ordinary native ACLs.

## C — Files changed

- __manifest__.py
- models/__init__.py
- models/cost_attribution.py
- security/cost_attribution_security.xml
- tests/__init__.py
- tests/test_cost_attribution.py
- tests/test_module_foundation.py
- views/cost_attribution_views.xml

Architecture and PR14 contract: docs/COST_ATTRIBUTION_FOUNDATION.md. Verification
drivers/probes, native audit, baseline archive, full logs and frozen ledger are
retained under evidence/. DEVELOPMENT_PROGRESS.md and TEST_REPORT.json record
the actual status. Earlier implementation and financial/security test bodies are unchanged. The
foundation exact-menu assertion includes the new menu and preserves duplicate/root checks.

## D — Executed reference results

| Controlled fixture | Actual reference result |
|---|---|
| Standard Cost | 60 units at INR 100, reference 6,000; proposal 115 does not revalue stock |
| AVCO actual native receipts | 10 at 90 plus 10 at 110: company-product reference 100 |
| FIFO actual native receipts | 30 at 90 plus 30 at 100: company pool 60, value 5,700, weighted 95; warehouse selected cost unavailable |
| FIFO partial native consumption | Remaining portions 20 at 90 plus 30 at 100: 50, value 4,800 |
| Exact PR12 protected PO | 40 at 100, reference 4,000; proposal 115 not applied |
| New procurement | Explicit single-entry 100 at proposed 115, scenario reference 11,500 |
| MOQ 100 | Explicit single-entry buying scenario 100 selects 109; separate 60-unit entries each stay at 115 |
| Landed no-double-counting | Configured recorded-cost reference 105 remains 105, never 110; no landed posting claimed |
| Combined scenario | Demand 200 = stock 60 at 100 + protected incoming 40 at 100 + new procurement 100 at 115; distinct sources, no gross margin |

## E — Confidence and limitations

Accounting source verification differs from physical acquisition proof. Standard/
AVCO attribution is a supported estimate; protected PO is a verified commercial
basis; replacement/MOQ is a hypothetical scenario, not an actual buying guarantee.
Missing date/FX/tier, default zero, unreconciled FIFO, lot-valuated lineage and
pending/disputed PO protection remain unavailable/review. FIFO company pool is
never another source-consumption ledger. Optional Community landed-cost source
integration is statically inspected; a real posted landed-cost fixture was
NOT_RUN. The 105 no-addition reference test is controlled configured-cost evidence,
not proof of a real landed-cost posting. Verified future freight/duty components
and exact lot/warehouse FIFO tracing are unsupported. Net references are not
fully landed costs. No missing cost contributes a false numeric zero.

## F — Security

Global company and all demand/supply/cost warehouse scopes apply to headers and
children; own-revision preparer role rules still apply. Sales-only, public and
portal raw-cost reads are denied. Auditors read only and cannot collect or forge
results. Direct ORM write/copy/delete, nested commands, context forgery, exports,
group reads, revoked grants and foreign selected-company access are covered.
Native cost-source opening needs native source permission. Fixed read projections
are exact company/product bound; optional landed evidence is company bound.

## G — Actual automated tests

| Gate | Source-validated result | Evidence |
|---|---|---|
| FRESH | 44 tests PASS | evidence/pr13-fresh-install-20261029T092118+0000_milestone.log |
| HELPERS_VERIFY | 7 tests PASS | evidence/pr13-helpers_verify-update-20261029T093646+0000_quick.log |
| TARGETED | 118 tests PASS | evidence/pr13-targeted-update-20261029T092529+0000_targeted.log |
| UPGRADE | 114 tests PASS | evidence/pr13-upgrade_verify-update-20261029T093706+0000_milestone.log |
| UPGRADE-PRESERVATION | 1 assertion groups PASS | evidence/pr13-upgrade-preservation-20261029T094055Z.log |
| CONCURRENCY | 6 assertion groups PASS | evidence/pr13-concurrency-20261029T094129Z.log |
| OPERATIONAL-SAFETY | 1 assertion groups PASS | evidence/pr13-operational-safety-20261029T094150Z.log |

44 new PR13 test methods. Initial fresh-install run: 29 passed, 3 failed
(PR12 scope argument mapping and a documented-zero fixture expectation); retained
FAIL history, corrected and superseded by passing final-source gates. Earlier
passing intermediate runs remain history; source compatibility is explicitly checked below.
Actual PR12 source is verified against its 76-file archive before installing it,
seeding retained records, cold capture, PR13 update and preservation comparison.
The first upgrade run had 113 passed and 1 failed: its exact root-menu assertion
omitted the newly implemented cost menu. That expected-menu set was extended;
no duplicate/root checks or business assertions were relaxed. The corrected
foundation QUICK and repeated upgrade milestone pass. Fresh44 and TARGETED118
remain valid evidence for unchanged application/selected test sources: the exact
pre-correction ledger e33036f7c8a6e082405ad3a1cac9e769b3e38c1b918056447e80f838dddaa19a
is retained as pr13-runtime-e330-source-sha256.json. The final ledger differs only
in tests/test_module_foundation.py, which those two runs did not select. This
compatibility is asserted, not retroactively relabeled as an exact-ledger run.
Six actual two-session races exercise collection,
PO price, receipt, valuation value, FX and grant changes. Retries serialize rather
than duplicate results; changed sources are rejected by fresh consumers.
Operational safety compares 20 native/master models including confirmed
PO/SO, reservations, done valued move and posted entry. Public/portal direct reads
are checked additionally. Full logs and actual commands are retained.

100 demand entries reconciled; collection measured 0.770s in the final
fresh fixture. 500/2,000/10,000 loads and peak memory NOT_MEASURED; manual browser
UAT NOT_RUN. Registered XML views/actions load on install/update. No release-wide
FULL claim or future PR14 functionality is asserted.

## H — Business safety

No product cost change, inventory revaluation, landed posting, PO/SO modification,
supplier rule change, accounting posting, customer repricing, procurement,
commercial approval/application, consolidated exposure or gross margin occurs
from PR13. Operational/posting writes in fixture scripts prepare synthetic test
records only. Business service has no commits or native create/write/delete calls.
Disposable runtime resources were removed after confirmed PostgreSQL shutdown.

## I — Progress

PR13 VERIFIED for this conservative attribution foundation. TEST_REPORT.json and
DEVELOPMENT_PROGRESS.md contain actual evidence, retained failures and limits.
Final 80-source ledger SHA256: fb13e236dc1fd115500baf88a603743dc10d37f2429970eff4576ea1dbb3c264.
PR12 archive SHA256: 58e17a7d296ca9ad61d19f4abe16af35d1ef8ef95b85760c3ab1df27a66b6618.
No critical mandatory failure remains. Unsupported cases stay visibly incomplete.

## J — PR14 handoff

Consume only get_current_costs(allocation_id, purchase_id, procurement_date), with
fresh upstream PR10/PR12/PR08 evidence. Retain exact entry/capacity IDs, original
base quantities/UoMs, source/company currency, FX/date/policy and snapshot versions.
Use separate accounting/PO/replacement semantics and per-source confidence. Keep
reserved/free/incoming/new procurement quantities separate. Reconcile every entry
and segment; never add independent scenarios, amendment alternatives or company
FIFO pool references as extra stock. Missing cost, unresolved lot/FIFO/FX/landed
inputs and unverified protection must remain unresolved, not zero exposure.
Recheck company/role/warehouse/native-source authorization at use time. Potential
scenario reference is not realized financial outcome. PR14 remains NOT_STARTED;
no financial exposure, profitability, approval or application engine is implemented.

Completed from real evidence at 2026-10-29T09:43:04+00:00.
