# PR09 / DEV05 — Completion report

## A — Environment

Odoo **20.0 Community FINAL** (`release.py` version_info20.0.0 FINAL), Python in
C:/PycharmProjects/odoo20/.venv and disposable PostgreSQL18.4 on127.0.0.1:55440.
Addon: vendor_price_revision_impact_simulator, manifest20.0.1.0.0. Direct dependency
purchase_stock brings Community purchase/stock/stock_account/account. Sales
integration was test-only. No existing database or repository version was upgraded.
All temporary test runtime resources were removed after clean shutdown.

## B — Implementation

A private bounded analytical service consumes only current PR08 exact variants.
Audited company/user/warehouse/cost grants and exact location classifications
authorize its fixed projections. Quant physical/reserved/free quantities retain
owner/lot/package evidence; reservation is subtracted once. Receiving/quality,
consignment, transit, inactive/untracked and anomalous stock are not silently free.

One PO-line bucket reconciles supplier receipt boundaries, partial deliveries,
backorders, returns and short-closed/cancelled remainder. Internal putaway and
transfers are nonadditive. Confirmed/locked is not guaranteed price protection.
Independent unchanged firm terms, including original units/reference hierarchy,
and complete governed normalization are required. Redirected receipt/return
evidence outside selected internal warehouses is blocked before publication.
Standard/AVCO are accounting references; exact FIFO quant cost remains unavailable.

Snapshots/buckets/issues are immutable, versioned and current-time stamped.
Identical source collection is idempotent; material source changes are rejected
by the current getter. App/company serialization, existing-row read locks and
one publication savepoint prevent partial success without mid-transaction commits.

## C — Relevant files

- __manifest__.py; models/__init__.py: Community integration registration.
- models/supply_governance.py: grants, exact locations and governance audit.
- models/supply_engine.py: scoped projections, quantities/receipts/cost references.
- models/supply_snapshot.py: immutable evidence, current getter, terms and wizard.
- security/supply_security.xml; views/supply_views.xml: roles, global company/all-warehouse rules and analysis/review UI.
- tests/test_supply_foundation.py; tests/__init__.py: 52 new methods across four classes.
- tests/test_module_foundation.py, test_vendor_price_revision.py and test_security_roles.py: dependency expectations and operational-preservation assertions.
- docs/SUPPLY_FOUNDATION.md, README.md, TESTING_SETUP.md, DEVELOPMENT_PROGRESS.md and TEST_REPORT.json: operating guide, real progress and evidence.
- evidence/pr09-* drivers/probes/logs, pr08-source-baseline.zip/.sha256 and pr09-verified-source-sha256.json: reproducible retained evidence.

## D — Actual reference results

All values below were asserted against real Odoo ORM fixtures in the final suite.
Quantities are product base units, separately scoped by warehouse.

| Fixture | Actual result |
|---|---|
| Physical100, reserved30 | Eligible free70 |
| WHA100/30, WHB50/10, WHC20/20 | Free70/40/0; selected authorized company scope110 |
| Physical80, reserved20; PO40 at INR100/unit; proposal INR115/unit | Free60, incoming40, initially protected0 |
| Same PO after independent unchanged firm-terms verification | Protected40; free plus protected100 |
| PO100, first receipt40, backorder | Received40; supplier-unreceived60; one PO-line contribution |
| Same two-step receipt in Input | Physical40 pending putaway; eligible Stock free0; supplier-unreceived60 |
| Full receipt100, return20 without replacement | Physical80; incoming0 |
| Short-close after receiving40 of100 | Incoming0; cancelled/unfulfilled remainder60 |
| Operational package fixture | Physical50/reserved3/free47; one quant bucket retains package ID |

No 200-demand allocation, INR1500 exposure, margin, realized benefit or financial
replacement-cost result was computed.

## E — Security

Company isolation, own-draft/manager scope, all-selected-warehouse access, cost-only
visibility, mixed-warehouse rejection, revocation, direct ORM mutation/copy/create,
context forgery, grouped reads and exports were exercised. Sales/Portal/Configuration-
only cannot collect; Auditor is read-only. Quantity-only output omits PO/accounting
price projections. Native stock.quant read already exists for internal users in
this target; native PO source opening remains separately checked. This service
does not globally change standard source ACLs. The redirected-receipt regression
and UoM reinterpretation regression pass.

## F — Automated verification

| Selection | Actual result | Evidence |
|---|---|---|
| QUICK static/cleanup | 91 checks PASS | evidence/DEV-05-pr09-static-validation.txt |
| Final fresh installation | 247 tests PASS | evidence/pr09-fresh-install-20261029T011347+0000_quick.log |
| TARGETED affected regression | 165 tests PASS | evidence/pr09-targeted-update-20261029T010854+0000_targeted.log |
| Actual PR08 update MILESTONE | 247 tests PASS | evidence/pr09-upgrade_verify-update-20261029T012907+0000_milestone.log |
| PR08 source/commercial/operational preservation | PASS | evidence/pr09-upgrade-preservation-20261029T013318Z.log |
| Eight independent-session races | PASS | evidence/pr09-concurrency-20261029T012745Z.log |
| Sixteen-model operational safety | PASS | evidence/pr09-operational-safety-20261029T013329Z.log |

Final code/test ledger: 62 files; SHA256 `08f2e37ae22b6b2c0ccf1d9f4b6c5f00bcdb7bda1527e446b873c432f8b44875`. All mandatory final
runtime/static records match it and report no source changes during execution.
The exact PR08 source archive and its SHA256 are retained. Earlier failed attempts
remain in TEST_REPORT history: target API field names, missing costing category,
short-close interpretation and native permission expectations, upgrade fixture
warehouse/mapping setup and unordered relation representation were corrected.
All stored business values/IDs/write dates/row ordinals and original bytes remain
checked; unordered relational membership is canonicalized without hiding changes.
No passing business assertion was weakened or failure ignored.

Manual browser UAT: NOT_RUN. Supply 100/500/2000-product and10000-source benchmarks
and peak memory: NOT_MEASURED. These results are not a full release certification.

## G — Business safety

Normal app methods create only app evidence/governance/terms records. They do not
adjust inventory, reserve/unreserve stock, validate pickings, confirm/cancel/reprice
PO/SO, update supplier rules/product costs, revalue inventory, post entries, send
notifications or apply prices. Synthetic fixtures intentionally created confirmed
SO/PO, reserved stock, a valued done move3500 and a posted balanced entry before
comparison. Exact operational/master/mail/cron/package values, IDs, write dates
and counts remain unchanged around collection/current checks/terms review/refresh.
Odoo20 valuation here is stock.move.value; absent stock.valuation.layer is not
claimed as tested. Source-terms verification is not revision price approval.

## H — Progress and limits

PR09 is VERIFIED. TEST_REPORT.json and DEVELOPMENT_PROGRESS.md contain real
source-qualified results. M2 remains IN_PROGRESS; PR10 is NOT_STARTED. Unsupported
replacement-return chains, shared transit attribution, cross-warehouse mapping,
tax-inclusive/extra-charge cost bases and exact FIFO quant attribution take
explicit review/unavailable paths. Existing-row locks do not freeze phantom
inserts or reserve future demand; fresh-transaction consumption remains required.
No supply throughput, memory or browser-UAT result is invented.

## I — PR10 handoff

Use `batch.get_current_supply(warehouse_ids, costs=True)` in a fresh authorized
transaction. Do not rely on a latest snapshot ID alone. Preserve snapshot ID,
version/digest/time, exact company/variant/warehouse/base-UoM dimensions and source
keys (`quant:id`, `po_line:id`, `transfer:id`). Inspect per-scope quantity_verified,
null quantities, cost basis/state/firm evidence and retained issues. Totals and
buckets expose physical/reserved/free, received-pending-putaway, incoming,
protected subset and unverified incoming; source PO/move expected/planned dates
remain separate evidence. Reservations are already deducted; transfers do not add
supply. Original PO-currency firm price is not an FX hedge or realized outcome.
PR10 must implement unique demand attribution/claims, timing, transaction-safe
allocation and reconciliation while preserving company/warehouse/role/cost access.
No PR10 implementation was started.
