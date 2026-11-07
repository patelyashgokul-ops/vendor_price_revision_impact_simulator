# PR14 / DEV07 — projected financial exposure

## A — Environment

Odoo20.0 Community FINAL, Python3.14.6, PostgreSQL18.4, Windows. Addon
`vendor_price_revision_impact_simulator`. The established 20.0 major is preserved.
Official stable version checked at development start: [release notes](https://www.odoo.com/page/release-notes),
[Community builds](https://nightly.odoo.com/). Local release hash and actual
verification timestamp are in evidence/pr14-version-verification.json.
All test databases belong to an owned disposable loopback cluster on55445;
production databases, credentials and operational records were not used.

## B — Implementation

Immutable financial.snapshot, financial.line and financial.issue models calculate
one contribution per exact PR10 entry from current PR13 costs and PR11 demand
classification. PR08/09/10/12 authorities are reused through their current getters.
Existing stock and protected incoming use the same source costs in baseline and
revised scenarios. Old procurement tiers are independently resolved for each
actual entry quantity using PR08's tier helper; proposed pricing comes from PR13.
No cross-demand consolidation, alternative vendor, Standard Cost or zero fallback.
Explicit procurement dates, current company policies and normalized UoMs apply.

Signed delta is revised minus baseline, using Decimal38. Common-rate and separate-
date FX methods remain distinct, with explicit price/FX decomposition where
source currencies permit. Grouped product/warehouse/UoM/classification weighted
costs are analytical references, never product revaluation. Raw/rounded totals and
rounding residuals reconcile; there is no arbitrary balancing line.

Confirmed and quotation/portfolio scenarios remain separate. A quotation requires
its matching current confirmed financial baseline; its conditional difference is
scenario delta minus confirmed delta, not another total to add. All missing inputs
and quantities remain visible. Full cost completeness is distinct from incremental
delta completeness; unchanged unknown stock may contribute zero delta while total
costs stay unavailable. Numeric completeness never upgrades estimates or hypothetical
buying/FX into verified actual procurement. Savepoints, company/batch serialization,
shared source locks, fingerprints, versioning and fresh getters protect publication.

## C — Actual files changed

- __manifest__.py
- models/__init__.py
- models/financial_exposure.py
- security/financial_exposure_security.xml
- tests/__init__.py
- tests/test_financial_exposure.py
- tests/test_module_foundation.py
- views/financial_exposure_views.xml

The new service/security/UI/tests provide the feature; manifest and package imports
register it. The foundation exact-menu assertion includes the new Financial Analysis
folder without relaxing root/duplicate checks. Earlier business and security tests
remain unchanged. docs/FINANCIAL_EXPOSURE_ENGINE.md defines the financial contract.
Verification drivers/probes, baseline archive, ledger and logs are retained in
evidence/. TESTING_SETUP.md, TEST_REPORT.json and DEVELOPMENT_PROGRESS.md document
actual verification and handoff.

## D — Executed controlled financial references

| Fixture | Baseline | Revised | Projected delta / result |
|---|---:|---:|---|
| A: demand200, stock60@100, protected40@100, new100 old100/new115 | 20,000 | 21,500 | +1,500; weighted revised107.50 |
| B: same scope, eligible single-entry MOQ100 at109 | 20,000 | 20,900 | +900 |
| C: protected negotiated PO95, other terms unchanged | 19,800 | 21,300 | +1,500 |
| D: old price unavailable at planning date | unavailable | comparison unavailable | null delta; quantity100 retained, not zero |
| E: unapproved PO amendment40, recorded100/requested115 | unavailable protected comparison | unavailable | not accepted, quantity/reference alternatives preserved |
| F: confirmed100 plus conditional quote70, old100/new115 | scoped source costs retained | scenario scope170 | confirmed delta1,500; scenario delta2,550; conditional difference1,050; not additive |
| Signed decrease:100 units old115/new109 | 11,500 | 10,900 | -600 potential reduction, not realized savings |
| FX per unit:USD10@90 toUSD11@94 | 900 | 1,034 | +134 = supplier90 + FX44; common-rate alternative kept separate |
| Unknown FIFO stock60, plus new100 | total unavailable | total unavailable | projected delta1,500 may be complete; full cost remains incomplete |

Amounts are INR in these fixtures, under their declared source, date and per-entry
buying assumptions. Fixtures A/B/C are numerically complete scenarios, not proof of
accepted supplier prices, actual acquisition cost, future buying or recognized expense.

## E — Completeness and limitations

Cost, delta and source confidence are separate. Existing Standard/AVCO references
remain estimates; native FIFO company pools do not establish allocated warehouse
costs. Verified unchanged stock delta is not a verified total stock value.
Unprotected/pending/disputed POs, missing dates, old-tier conflicts, unsupported
FX and unresolved quantities stay incomplete. Known subset deltas are labeled
partial and never substituted for a full total. Sales FX/revenue incompleteness
does not prevent an otherwise valid cost calculation; it remains a PR15 input gap.

Future landed components, exact warehouse/lot FIFO tracing, procurement optimization,
explicit adjustable-PO amendment what-if execution and advanced scenarios are not
implemented. Net replacement and documented counterfactual old-price assumptions
remain explicit. No profitability, margin, risk or customer repricing is implemented.
Rounding residuals are visible and bounded; no hidden adjustment fills a gap.

## F — Security

Existing role/company/own-revision controls plus all demand/supply/cost warehouse
grants apply. Native customer-order permission and audited customer-commercial
warehouse scope are additionally required. Purchase-only cannot obtain customer
contracts, and Sales-only cannot obtain raw supplier cost/financial data. Finance
can create authorized analytical results without editing upstream intake. Auditors
remain read-only; public/portal read denial, foreign selected-company denial,
group/export rules, immutable/nested/context forgery, grant revocation and formula
injection protection are exercised. Native source drilldown retains native rights.
The financial service introduces no sudo projection or accounting-admin grant.

## G — Actual automated tests

| Gate | Exact final-source result | Evidence |
|---|---|---|
| FRESH | 57 tests PASS | evidence/pr14-fresh-install-20261029T114430+0000_milestone.log |
| HELPERS_VERIFY | 9 tests PASS | evidence/pr14-helpers_verify-update-20261029T115222+0000_quick.log |
| TARGETED | 120 tests PASS | evidence/pr14-targeted-update-20261029T115257+0000_targeted.log |
| UPGRADE | 157 tests PASS | evidence/pr14-upgrade-update-20261029T115922+0000_milestone.log |
| UPGRADE-PRESERVATION | 1 assertion groups PASS | evidence/pr14-upgrade-preservation-20261029T120653Z.log |
| CONCURRENCY | 7 assertion groups PASS | evidence/pr14-concurrency-20261029T120741Z.log |
| OPERATIONAL-SAFETY | 1 assertion groups PASS | evidence/pr14-operational-safety-20261029T120804Z.log |

53 new financial test methods. Initial fresh run:53 passed/1 fixture error
(price syntax .004 rejected upstream). Second fresh run:55 passed/2 fixture errors
(changing a confirmed pricelist and missing native export permission). Third fresh
run:56 passed/1 failed fixture assertion, corrected to distinguish verified source
currency sales terms from unavailable company FX conversion. An interrupted fourth
attempt produced no completed test result and is not counted as a pass. These FAIL
records remain history. Fixtures were corrected to native supported setup without
relaxing any financial or security assertion. All final-source gates above passed.
The actual PR13 archive contains80 verified source files and real retained PR13
cost snapshots were cold-captured before any financial table existed. Upgrade
preservation compares all retained fields/source bytes, including sales, purchase,
cost, stock, confirmed orders and posted journal evidence. Seven real two-session
races cover duplicate collection, PO price, receipt, valuation value, FX, scope
revocation and proposed-price correction; changed sources are checked individually.
Operational safety compares 22 native/master models and six upstream
analytical models, with real confirmed/reserved/valued/posted synthetic fixtures.

The 100-financial-entry benchmark measured 2.598s in the final fresh run,
reconciling baseline100,000/revised115,000/delta15,000. Other benchmark sizes and
peak memory NOT_MEASURED; manual browser UAT NOT_RUN. XML views/actions load on
fresh installation and update. No release-wide FULL or PR15 test claim is made.

## H — Business safety

No customer repricing, supplierinfo change, PO/SO mutation, stock reservation,
inventory revaluation, accounting/bill posting, approval or vendor-price application
is performed by financial simulation. No gross profit, gross margin or risk scoring
is produced. Native writes in verification scripts prepare synthetic fixtures or
controlled competing source changes only. Business code has no commits or native
create/write/delete calls. Disposable runtime was removed after confirmed shutdown.

## I — Progress

PR14 VERIFIED for the documented projected financial calculation scope. All required
source-integrity, financial/security and installation/update gates passed. Historical
failures and unmeasured work remain explicit in TEST_REPORT.json. Final84-file
ledger SHA256:db8d737af1d9655e4d3accdd6d41141529b19b90ff07ce0f39561af431e59f28. PR15 remains NOT_STARTED. Wider release/UAT and
unsupported input scenarios are not claimed complete.

## J — PR15 handoff

Use only get_current_financial_exposure with fresh authorized PR08–13 sources.
Preserve exact allocation/cost/demand/order/product links, scenario and source
versions, grouped quantity/UoM, target/source currency and explicit FX method,
policy, old/proposed prices, MOQ, date and buying assumptions. Honor complete versus
partial baseline/revised costs, signed incremental totals, separate delta confidence,
conditional differences, raw/reported reconciliation and unknown inputs. Do not add
alternative quote totals or reconsume FIFO/PO/stock quantities. Current PR11 net
selling-value evidence is an additional profitability prerequisite, not something
this engine certifies or calculates into margin. Risk requires governed thresholds.
Estimated, scenario-only, disputed or stale inputs cannot become realized outcomes
or unqualified committed exposure. Recheck role/company/cost/customer scope and
native source permissions. STOP after PR14; no PR15 implementation was started.

Completed from actual evidence at 2026-10-29T12:09:03+00:00.
