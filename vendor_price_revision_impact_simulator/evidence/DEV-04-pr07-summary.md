# PR-07 / DEV-04 implementation, verification and handoff

PR-07 **VERIFIED** on Odoo Community 20.0. PR-08 remains **NOT_STARTED**.

## A — Inspection and baseline

Preserved Odoo Community 20.0 and existing base/product dependencies. Inspected
AGENTS.md, TESTING_POLICY.md, TESTING_SETUP.md, DEVELOPMENT_PROGRESS.md, prior test
reports, PR06 architecture/security/correction flows and local Odoo product/variant,
supplier-reference, access and transaction APIs. Prior PR00–PR06 evidence was
verified. The exact PR06 baseline archive matches its verified SHA256 ledger.
No version migration, pre-existing database use or unrelated refactor occurred.

## B — Implemented behavior

Exact variant identity uses authorized batch-company/shared products and the exact
vendor partner. Verified mapping evidence, supplier references, configured internal
codes and explicitly enabled barcode input are checked for conflict. No arbitrary
first candidate, fuzzy/name matching or implicit parent-vendor expansion occurs.
Multiple template variants remain ambiguous. Ineligible products never resolve.
Policies are explicit company configuration with reasoned versions and audit.

Manual proposals select existing variants only. A separate Purchase Manager must
verify unchanged eligible evidence; self-verification, overlapping key periods and
contradictory exact evidence are rejected. Reusable company/vendor/key/date mappings
and one-row mappings retain superseded/rejected versions. Product/source/reference/
policy changes invalidate stale evidence. Note-only overlays retain identity after
PR06 revalidation. Current getters and immutable history remain distinct.

Matching is bulk, atomic, idempotent and bounded. Existing master identity rows are
read locked; company/batch locks serialize competing workflow mutations. Fresh
transactions retry serialization conflicts. No business action commits mid-work.

## C — Files changed

- models/product_resolution.py: policy, immutable registry/audit/resolution, matching,
  freshness, batch/row status counts, guarded handoff, proposal/review wizard.
- security/product_resolution_security.xml: Odoo20 unified access grants plus global
  company/active-user restrictions for all five new models.
- views/product_resolution_views.xml: batch/row evidence review, status filters,
  policy/registry menus and proposal/verification dialogs.
- __manifest__.py, models/__init__.py, tests/__init__.py: registration/description;
  version and dependencies retained.
- tests/test_product_resolution.py: 33 new methods in four classes, including bulk
  workload, midpoint rollback, company/role/context/export and freshness cases.
- tests/upgrade/seed_pr06.py, verify_pr07.py, verify_concurrent_products.py and
  verify_pr07_static.py: actual upgrade preservation, five independent-session
  probes and final source/evidence/cleanup audit.
- docs/PRODUCT_MAPPING_GUIDE.md, README.md, docs/SECURITY_MATRIX.md,
  TESTING_SETUP.md, DEVELOPMENT_PROGRESS.md, TEST_REPORT.json and retained evidence.

Existing PR06 business sources, original tests, security and views were preserved.
The baseline hash comparison shows only registration/manifest changes to prior
implementation files. No passing test was removed or weakened.

## D — Security

Purchase Users prepare own authorized drafts; managers manage company drafts and
verify another actor's proposal. Confidential Finance/Director/Pricing/Auditor roles
read company evidence without mutation rights. Configuration-only users manage
policy without gaining supplier-source access. Mandatory company and active-user
rules intersect role grants. Multi-company selection never broadens a batch's
product candidates. Normal business operations use no sudo.

Public ORM/context calls cannot forge results, audit actors, verified state or
company links. Wizard create/write validates linked record access/company, including
context defaults. Current labels of products moved to another company are masked
in history reads and protected in related-product exports. Source attachment and
HTTP download regressions remain. Formula-like export strings are escaped while
stored supplier evidence stays exact. Standard Odoo export privilege is required.

## E — Automated verification

| Level / scope | Actual result | Retained evidence |
|---|---|---|
| QUICK final fresh install | PASS (148 tests) | [pr07-fresh-install-20261028T151947+0000_quick.log](pr07-fresh-install-20261028T151947+0000_quick.log) |
| TARGETED product/structural/source security | PASS (47 tests) | [pr07-targeted-update-20261028T152355+0000_targeted.log](pr07-targeted-update-20261028T152355+0000_targeted.log) |
| MILESTONE actual PR06 update | PASS (148 tests) | [pr07-upgrade_verify-update-20261028T151703+0000_milestone.log](pr07-upgrade_verify-update-20261028T151703+0000_milestone.log) |
| TARGETED two-session concurrency | PASS (5 probes) | [pr07-concurrency-20261028T152517Z.log](pr07-concurrency-20261028T152517Z.log) |
| QUICK static/source/cleanup | PASS (78 checks) | [DEV-04-pr07-static-validation.txt](DEV-04-pr07-static-validation.txt) |
| Actual PR06 preservation | PASS (assertion probe; no fabricated count) | [pr07-upgrade_verify-preservation-20261028T151922Z.log](pr07-upgrade_verify-preservation-20261028T151922Z.log) |

All final Odoo suites report zero failed/error tests with nonempty selections.
Full source ledger: [pr07-verified-source-sha256.json](pr07-verified-source-sha256.json).
Reproducible local driver: [pr07-verification-driver.py](pr07-verification-driver.py).
Early failed and blocked attempts remain in TEST_REPORT.json. Earlier issues fixed: manual-selection
freshness digest, a Windows source encoding error, Configuration Administrator
cache refresh access, and duplicate-source rejection during concurrency fixture setup.
No process exit alone is used as evidence.

## F — Fixture-based reference results

| Current outcome | Six-row variant scenario |
|---|---:|
| Source rows | 6 |
| Structurally eligible rows | 6 |
| Automatic matches | 3 |
| Manually verified matches | 0 |
| Ambiguous | 1 |
| Unmatched | 1 |
| Ineligible | 1 |
| Stale | 0 |
| Excluded | 0 |
| Distinct matched products | 2 |

LED-12W-RED and LED-12W-WHT resolve to their exact attribute variants. The third
LED-12W template reference is ambiguous. UNKNOWN-001 is unmatched; OLD-SKU-01 is
archived/ineligible. The additional quantity row resolves to the red variant without
merging its source terms. Separate fixtures verify manual resolution, stale evidence,
exclusions, two vendors and two companies. The 500-row workload creates 500 distinct
products and confirms 500 automatic rows/results with bounded bulk product searches.
Final clean-install measurement: **2.307 seconds** for matching 500 rows;
product search count is asserted at most six, independent of row count. This is
one synthetic local fixture, not a throughput guarantee. Larger loads and peak
memory are NOT_MEASURED.

## G — Business safety

Identity workflow regression confirms unchanged source bytes/hash/raw cells,
supplier prices/write dates, product SKU/barcode/cost/list price/write date, product
and supplier record counts, customer pricelist counts, revision state/write date,
mail/messages/activities and cron counts. Test setup intentionally creates synthetic
master records and selected freshness tests intentionally modify them; those are
fixture actions, never resolver side effects.

No financial simulation, FX/UoM conversion, commercial baseline/quantity tier
validation, price approval, supplier-price application or customer repricing exists.
Operational SO/PO/stock/accounting fixtures are NOT_RUN because those modules are
absent in this base/product environment; no claim of operational-fixture execution.
Manual browser UAT is NOT_RUN; ORM view/action and HTTP source download checks run.

## H — Progress and limits

PR07 is VERIFIED; TEST_REPORT.json and DEVELOPMENT_PROGRESS.md reflect actual final
evidence. All temporary cluster/databases/filestores/baseline/config files were
removed after clean shutdown. M1 remains open pending PR08. License/publisher
release decisions remain as previously documented. Candidate evidence is bounded
at 5,000 records per type and previews at 40; overflow requires review. Global
status filtering requires narrowing after 20,000 authorized rows. Product freshness
is checked on matching/getter/new UI request, not by replacing standard Odoo master
write methods. Existing row locks cannot prevent new phantom reference inserts;
the next fresh-transaction check detects those. Keep handoff consumption in the same
transaction and recheck immediately before use.

## I — PR-08 handoff and strict stop

Use batch.get_product_resolved_rows() for current structurally-ready matched rows,
then actual resolved_product_id product.product variants. Retain company/exact vendor,
current validation run/result, immutable resolution, mapping version/verifier/time,
source attachment/hash/positions, original/effective identifier and correction history.
Preserve unresolved stale/ambiguous/unmatched/ineligible/excluded states explicitly.

Product snapshots include base UoM ID for context. PR08 must independently inspect
current product UoM/packagings and effective source UoM, currency, MOQ/quantity and
date text/provenance, then implement commercial normalization and applicable baseline
validation. PR07 identity dates are registry identity periods only. Existing supplier
reference commercial dates/tiers/prices were not used to select a price baseline.
Regression dependencies: exact variants, all reference conflicts, scoped reusable
keys, maker-checker, fresh structural gate, stale evidence, idempotency/rollback,
protected source attachments, no master-price writes and two-session concurrency.

STOP after PR07. PR08 and later engines are NOT_STARTED.
