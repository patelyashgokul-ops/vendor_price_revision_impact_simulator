# PR11 / DEV06 — Sales commercial exposure foundation

## A — Environment

Odoo20.0 Community FINAL, Python3.14.6 and isolated PostgreSQL18.4; addon
`vendor_price_revision_impact_simulator`. Existing major/dependencies are preserved.
PR00–PR10 evidence was inspected; the exact68-file PR10 source matched its ledger
before edits and is archived with a checksum. The local native source audit retains
20 relevant source hashes in evidence/pr11-native-source-audit.json. No existing
user database or production credentials/data were used. Disposable loopback port55442,
exact allowlists and disabled external effects governed every database run.

## B — Implementation

New sales snapshot, exact line, exception, immutable protection assessment,
audited scope grant and collection/review wizard models reuse current PR10 demand
and allocation without performing new allocation. Actual customer prices and
source discounts/currency/taxes/UoM/quantity provenance are frozen. Native tax
services produce a tax-excluded basis after Decimal discount preparation; negative
discounts retain surcharge semantics. Partial quantities come from PR10.

Reliable outstanding values and allocation-entry selling values remain distinct
from recognized revenue or vendor-cost impact. Currency rounding residuals are
explicit. Global discounts/downpayments/negative adjustments stay order-only and
block invented product apportionment. Incomplete grouped totals are null with
separate known subtotals and incomplete counts. Shipping/services are not product
demand. Confirmed and conditional currency/scenario groups remain separate.

Snapshot/version/digest/current getters, existing-source locks, company/batch
serialization, atomic savepoints and idempotency preserve history and freshness.
A real-session quote probe exposed native rolling expected_date in PR10 freshness.
Unused volatile dates are now excluded; conditional allocation requires a stored
commitment date, and a versioned date-basis tag makes earlier allocations require
explicit revalidation without overwriting their history. Confirmed native fallback
is retained. Clock-advance and missing-date regressions verify this behavior.
Current tax/price/discount/delivery/state/offer/review/UoM/FX/source changes invalidate
material evidence; unrelated notes do not. Native source permissions also apply.
No financial margin, repricing, approval/application or PR12 engine is implemented.

## C — Files changed

- models/allocation_engine.py — remove irrelevant rolling quote ETA from source
  fingerprints; require a stored conditional commitment date, retain confirmed
  expected-date fallback and version the analytical date-basis contract.
- models/sales_exposure.py — analytical models, native source projection, Decimal/
  tax/UoM/FX basis, current getters, authorization and documented review actions.
- security/sales_exposure_security.xml — role/company/all-warehouse/all-source-order
  permissions; separate audited customer grants; no operational ACL broadening.
- views/sales_exposure_views.xml — allocation collection entry, read-only historical
  sales review, exact line detail, filters, issue/evidence pages and grant controls.
- __manifest__.py, models/__init__.py, tests/__init__.py — register the new feature.
- tests/test_sales_exposure.py — 67 business/security/side-effect/workload methods.
- tests/test_module_foundation.py and tests/test_security_roles.py — exact additive
  Sales navigation expectations; confidential supplier menu assertions remain.
- docs/SALES_EXPOSURE_FOUNDATION.md, README.md, TESTING_SETUP.md,
  DEVELOPMENT_PROGRESS.md, TEST_REPORT.json — current scope, trust boundary and evidence.
- evidence/pr11-* — exact baseline, source ledger, reproducible drivers/probes,
  native audit, source-qualified logs, cleanup and this A–J handoff.

## D — Actual reference fixture results

| Reference | Executed result |
|---|---|
| A |200 × INR140 = INR28,000; free60 =8,400; independently protected incoming40 =5,600; new100 =14,000; categories reconcile28,000|
| B |10% discount: net126; full200 =25,200; delivered50 excluded; outstanding150 =18,900|
| C |Current pricelist160 does not replace recorded SO140; outstanding100 =14,000|
| D |Confirmed200 at140 =28,000; selected conditional70 at150 =10,500; selected what-if38,500 is not confirmed revenue|
| E |Product/service references15,000; global adjustment−1,000; full order14,000; product attribution incomplete, no invented allocation|

Additional executed tests cover actual invoice quantity100 with physical delivery0,
Box10 and sales-only Pack7 normalization, negative discounts, fixed/included/excluded
taxes, returns, reservation-backed uniqueness, unresolved supply selling value,
standalone and portfolio alternatives, FX direction/provenance/missing rates and
immutable source amendments. Reference markers remain in the clean-install log.

## E — Customer protection

Sales Manager assessments require native source access, company/warehouse grant,
traceable reference, classification, reason and valid effective interval. Fixed
and adjustment-allowed verified assessments are bound to exact current source
terms and retain previous assessments. Active batch/draft-revision lifecycle
metadata is checked through a fixed-ID, company-scoped service without supplier
values; cancelled contexts cannot receive a new review. Confirmation alone remains contract review;
missing/expired/inapplicable evidence never creates adjustment rights. Sent offers
receive validity review; PR10 excludes newly selected expired quotes and historical
snapshots become stale as validity changes. This is commercial evidence, not a
legal opinion or authority to change customer prices.

## F — Security

Sales-only readers need native Sales access plus an explicit customer-commercial
warehouse grant. Entire snapshots require every constituent order and warehouse
to be authorized. Native own-sales restrictions cannot disclose a combined snapshot.
Native product permissions are broader than the analytical projection. Nested
export/web specifications, grouping metadata and search/order/aggregate joins
therefore permit only captured fields and native source identity/labels. No raw
supplier cost/provenance/attachment traversal is exposed through this model.
Integer allocation IDs preserve traceability without granting supplier traversal.
Sales-only managers can review customer terms without supplier privileges; full
freshness attestation still requires allocation authority. Purchase User and Pricing
Operator do not gain customer access; broader roles need explicit grant and native
Sales rights. Auditors have immutable historical read access only.

Executed negative tests cover genuine foreign-company users with combined roles,
direct reads, searches, aggregation, exports, grant revocation, narrowed warehouses,
native source permissions, portal/employee roles, forged create/write/copy/unlink,
nested ownership commands and untrusted context. No successful forbidden access
was accepted as verification.

## G — Testing

| Selection | Actual result | Evidence |
|---|---|---|
| HELPERS_VERIFY | 9 tests PASS | evidence/pr11-helpers_verify-update-20261029T065508+0000_quick.log |
| TARGETED | 15 tests PASS | evidence/pr11-targeted-update-20261029T065549+0000_targeted.log |
| FRESH | 67 tests PASS | evidence/pr11-fresh-install-20261029T065039+0000_milestone.log |
| UPGRADE | 385 tests PASS | evidence/pr11-upgrade_verify-update-20261029T065635+0000_milestone.log |
| UPGRADE-PRESERVATION | 1 assertion groups PASS | evidence/pr11-upgrade-preservation-20261029T070507Z.log |
| CONCURRENCY | 6 assertion groups PASS | evidence/pr11-concurrency-20261029T070533Z.log |
| OPERATIONAL-SAFETY | 1 assertion groups PASS | evidence/pr11-operational-safety-20261029T070549Z.log |

The100-line workload took **1.159s** after upstream fixture preparation;
value28,000 reconciles with2 PR11 bulk sales-line projections and1 order projection.
This is a measured synthetic case, not a general throughput guarantee. Larger
500/2000/10000-demand workload matrix and peak memory: NOT_MEASURED. Manual browser
UAT: NOT_RUN. Secure XML/model/ACL/action loading is covered by actual install/update.
Future PR14–16 financial-engine tests: NOT_RUN and out of PR11 scope.

Earlier sandbox loopback denial and draft fixture/float-preparation failures remain
in report history. Fixes preserve authorization/native lifecycle rules, use actual
invoice fixtures, reuse source batches instead of importing duplicate bytes, and
avoid native binary-floating surcharge artifacts by Decimal discount preparation.
No passing financial/security assertion was removed or weakened. Earlier runtime
passes that preceded final projection/audit/lifecycle additions remain retained,
but only exact final-hash runs without source changes satisfy the gates below. Source ledger
**fcf21e244772bbd7fca5e0752e018f8decdb36a9a8420f106e6dfb1e86baa431** covers72 addon/test files for all final runtime gates.

## H — Business safety

Actual confirmed SO/PO, a posted balanced entry, a valued done move3500, physical
package stock50/reserved3/free47 and mixed sales UoM fixtures existed before PR11
analysis. The dedicated probe preserves all values/IDs/write dates/counts across
**20 models** around repeated collection/current checks. PR11 creates
only analytical/review records. No customer/vendor prices, discounts, pricelists,
orders, reservations, receipts/deliveries, valuation, invoices, GL entries, mail or
cron records are changed by analysis. Odoo20 valuation is stock.move.value; absent
stock.valuation.layer is not falsely claimed tested. No margin/consolidated exposure,
approval execution, customer repricing or supplier application is implemented.

The real PR10 upgrade preserves prior source bytes, mappings/corrections, commercial/
supply/allocation snapshots, policies and operational records; ordinary update
creates no sales snapshot or customer-commercial grant. Disposable runtime resources
were removed only after confirmed PostgreSQL shutdown; retained logs remain.

## I — Progress and limitations

PR11 is VERIFIED; progress/report contain source-qualified execution evidence.
PR12 remains NOT_STARTED; M2 remains IN_PROGRESS for subsequent purchase/inventory
work. Source queries cap10000 rows, history-freshness search1000 snapshots. Unknown
custom adjustment conventions require integration review; unallocated standard
adjustments stay incomplete. Historical original prices are unavailable unless
retained in prior snapshots/evidence. Source-row locks do not permanently freeze
future inserts. Fresh authorized transactions and serialization retries are mandatory.
Sales-only readers cannot attest supplier allocation freshness and receive a
conservative stale/access-unavailable indicator. Browser UAT, larger stress and
peak memory remain unexecuted/unmeasured, explicitly recorded above.

## J — PR12 handoff

Use `allocation.get_current_sales_terms(fx_date)` in a fresh authorized transaction.
Keep exact source order/line/customer/company/variant, confirmed-vs-conditional
scenario, net selling price, outstanding quantity, source/comparison UoM and factors,
tax/discount assumptions, source currency, optional sales FX rate/date/IDs, customer
protection evidence and allocation-entry IDs. Retain snapshot/version/digest and
independent value/protection/FX statuses. Never treat stored state as current approval,
missing values as zero, protected incoming as additional supply, or independent quote
scenarios as additive. Do not compare source currencies/UoMs without normalization.

PR12 must independently verify RFQ/PO commitments, supplier evidence, effective
dates/tiers, amendments/disputes and fixed/adjustable purchase terms. PR14–16 may
combine only reconciled, current, authorized inputs. Preserve company, native Sales,
customer-commercial grants, warehouse and supplier-cost confidentiality. Customer
adjustment rights do not permit automatic selling-price changes. Stop after PR11.
