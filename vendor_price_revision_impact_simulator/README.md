# Vendor Price Revision Impact Simulator



APP 06 foundation for **Odoo Community 20.0**. Technical addon name: `vendor_price_revision_impact_simulator`.



## Foundation



- Addon location: `custom_addons/vendor_price_revision_impact_simulator`.

- Manifest version: `20.0.1.0.0`; category: `Supply Chain/Purchase`; application and installable are enabled.

- Dependencies: `base`, `product`, PR09 `purchase_stock` and PR10 `sale_stock`. The Community integration brings purchase, stock and stock_account/account transitively. Sales-to-stock integration is a Community dependency from PR10 onward.

- PR-01's **Vendor Price Simulator** root and **Price Revisions** action are reused. Purchase roles and authorized confidential readers can open them; Sales-only and Configuration-only roles receive no raw pricing navigation; Configuration Administrators can open Business Settings.

- PR-02 adds `vendor.price.revision` headers, `vendor.price.revision.line` proposed entries, and `vendor.price.revision.evidence` reference records. A revision has a globally unique `VPR/<year>/<number>` reference, company, vendor, currency, received/proposed dates, owner, draft state, notes, line count, lines, and evidence references. Revision numbers use a global `ir.sequence` and database-level uniqueness.

- Draft lines retain unmapped vendor product codes, optional product/UoM references, proposed price, and minimum quantity. `price_is_set` differentiates an unset draft price from an explicitly provided zero. No calculated current price, normalization, FX conversion, or financial totals are shown.

- Company ownership is readonly on headers and derived on lines/evidence. Odoo 20 `ir.access` restrictions require the company to be authorized and selected. Purchase Users read their own records and prepare their own drafts. Purchase Managers can manage drafts and ownership in scope. Finance, Pricing Operator, Director, and Auditor roles read authorized companies; Sales and Configuration roles receive no raw commercial access. Revision/evidence deletion and lifecycle writes are blocked; line deletion is draft-only. See `docs/SECURITY_MATRIX.md` for group composition, assignment governance, and company/ownership rules.

- Evidence supports manual references and immutable uploaded CSV/XLSX sources. PR-05 preserves original bytes in protected attachments, generates SHA-256, and stages raw unvalidated rows with technical attempt history. No public download token is created. See `docs/IMPORT_ARCHITECTURE.md`.

- Only `draft` can be created. Planned lifecycle values are reserved, but validation, submission, approval, cancellation, and application transitions are not exposed.



## Validation and installation



The foundation smoke tests are in `tests/test_module_foundation.py` and run through Odoo's normal addon test selection. Use the DEV-00 runner with a private config based on `scripts/test-runner.example.json`:



```text

python scripts/run_tests.py --mode quick --config <LOCAL_CONFIG>

```



Use a dedicated, explicitly allowlisted test database with isolated side effects. Fresh install uses `action: "install"`; update uses `action: "update"` only after installation on that same test database. See `TESTING_SETUP.md` for preconditions.



PR-01 and PR-02 were verified on Odoo Community 20.0 using disposable PostgreSQL 18.4 loopback test databases. PR-02 fresh install passed 20 runner-counted tests; its final targeted module update passed 19 tests. Coverage includes ORM constraints, sequence/copy behavior, authorized draft creation, lifecycle forgery, company isolation, internal/public/portal access, evidence protection, views/actions, and unchanged product/vendor-price records. Logs and scope notes are in `evidence/DEV-01-pr02-summary.txt`, `evidence/DEV-01-pr02-static-validation.txt`, `evidence/odoo-pr02-fresh-install.log`, and `evidence/odoo-pr02-module-update.log`. Temporary test data was removed after the runs. PostgreSQL's `pg_isready` is installed outside `PATH`; the runner accepts its verified absolute path through `postgres.pg_isready`.



The test package covers foundation, revision core, security and company configuration in `tests/`. Use the DEV-00 runner with a private config based on `scripts/test-runner.example.json` and selected tags that exist in the module.



PR-03 verification: clean install **39 passed**, focused security **18 passed**, and actual PR-02 upgrade MILESTONE regression **37 passed**, with no failed tests in these final runs. The separate preservation probe confirmed unchanged revision/line/evidence records and supplier prices, while correcting the legacy draft-edit grant. See `evidence/DEV-02-pr03-summary.md`.



## Metadata and deferred decisions



No author or publisher/website metadata was approved, so these fields are omitted. The commercial license also remains a release decision. The manifest intentionally omits `license`; Odoo's current loader defaults an omitted license to LGPL-3, so the approved distribution license must be decided and explicitly set before release. No commercial price is embedded in the module.



PR-03 establishes role separation and the future service security contracts. Configuration definitions are implemented in PR-04; import and normalization are PR-05–PR-08; financial analysis is PR-09 onward; approvals, price application, reporting, and packaging remain deferred to their roadmap steps. No financial engine or operational vendor price change exists yet.



APP 06 security does not revoke standard Odoo product supplier-price visibility.

In this installed version, internal users can read permitted `product.supplierinfo`

records through the product module even when APP 06 denies them revision data.

The security matrix documents this boundary and the tests that demonstrate it.





## PR-04 business configuration



Company-owned configuration versions define commercial/accounting cost concepts,

margin hierarchy, risk intervals, approval role requirements, effective-date and

missing-data governance. Drafts are editable by company-authorized Configuration

Administrators; published versions and append-only change history are retained.

Publication validates configuration only. Source intake is implemented separately; financial simulation, commercial

approvals and price application remain unavailable. Setup and retrieval contracts:

[Configuration guide](docs/CONFIGURATION_GUIDE.md).





## PR-05 supplier source intake



Authorized draft preparers can upload CSV/XLSX from a revision or the Import Price

Files menu. Original evidence is immutable; source content, digest and raw rows

remain company/role protected, including standard Odoo content downloads. Bounded

parsing and atomic staging support exact-file duplicate review, safe retry and

immutable attempt history. Extracted rows are unvalidated source data. Company

Configuration Administrators manage technical limits independently of commercial

policy readiness. Python dependencies openpyxl and lxml were already installed.

[Import architecture and PR-06 handoff](docs/IMPORT_ARCHITECTURE.md).





## PR-06 structural import review



Extracted sessions support explicit column mappings, paginated source review,

Decimal-safe lexical checks, duplicate groups, correction overlays, reasoned

exclusion/reinstatement and immutable versioned validation history. Current counts

reconcile to staged rows. Input changes immediately invalidate ready results.

Structurally ready data still requires PR-07 product resolution and PR-08 commercial

validation. No live price, financial or approval engine is included.

[Structural review guide](docs/IMPORT_VALIDATION_GUIDE.md).





## PR-07 exact product identity



Current structurally-ready rows can resolve to eligible existing product variants

using exact vendor references, configured SKU/barcode rules and independently

verified reusable company/vendor mappings. Ambiguous, unmatched and stale evidence

remains explicit. No product/vendor-price master writes or commercial normalization

occur. See [Product mapping guide](docs/PRODUCT_MAPPING_GUIDE.md).





## PR-08 commercial unit-price comparisons



Current product-resolved rows can normalize UoMs, currency/FX and MOQ thresholds,

resolve a scoped effective-dated supplier baseline and retain immutable price-delta

snapshots. Interpretation verification, historical attestation and hypothetical

scenario FX remain explicit. Missing/ambiguous baselines and missing FX stay

incomplete. No supplier-price application, demand allocation or exposure exists.

[Commercial validation guide](docs/COMMERCIAL_PRICE_VALIDATION.md).





## PR-09 supply evidence



Current commercially valid PR08 variants can be analyzed through explicit audited

company/warehouse analytical grants and exact-location classifications. Immutable

snapshots separate physical/reserved/eligible free stock, supplier-unreceived

commitments and nonadditive putaway/transfer evidence. PO confirmation alone never

guarantees price protection: unchanged firm terms need an independent Purchase

Manager review. Quantity and cost completeness remain separate. Standard/AVCO are

accounting references; exact FIFO quant cost remains unavailable. No demand

allocation or financial exposure is calculated. See [Supply foundation and trust

boundary](docs/SUPPLY_FOUNDATION.md) and TEST_REPORT.json for actual verification.





## PR-10 analytical demand allocation



An additional audited customer-demand permission on each warehouse grant enables

confirmed sales quantity collection and independent quotation scenarios. Immutable

allocation ledgers preserve actual reservation ownership, exact warehouse/date

eligibility and direct procurement links while consuming free stock and incoming

receipt capacity once. New procurement and unresolved quantities reconcile to

source sales lines; conditional scenarios preserve confirmed baseline coverage.

The layer does not reserve stock or calculate monetary exposure. See

[Demand allocation and PR11 handoff](docs/DEMAND_ALLOCATION.md) and TEST_REPORT.json

for actual verification. PR11 is not started by this step.


## PR11 customer commercial terms

Current PR10 allocations feed immutable actual customer sales-price, discount,
tax-excluded outstanding-value, quotation and documented protection evidence.
Customer access is separately granted and also requires native Sales permissions.
Foreign conversion needs an explicit sales FX date; global adjustments remain
order-only review context. These values are not recognized revenue or profit.
See [Sales commercial foundation](docs/SALES_EXPOSURE_FOUNDATION.md).
PR12 and later financial/repricing/application engines remain outside this step.


## PR12 purchase commercial commitments

Read-only RFQ/PO snapshots preserve exact recorded prices, authoritative PR09 open
quantities, optional single-scenario PR10 attribution, independent supplier evidence
and amendment references, date/tier/FX context and optional native-authorized bill
mismatch evidence. Conditional differences are not approved payables or final
financial exposure. See [Purchase commitment evidence](docs/PURCHASE_COMMITMENT_EXPOSURE.md).
PR13 cost attribution and later financial/repricing/application engines are deferred.
