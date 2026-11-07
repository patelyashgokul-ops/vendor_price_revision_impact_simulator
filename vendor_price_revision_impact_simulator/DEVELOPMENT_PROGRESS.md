# Development Progress



## Environment baseline



- Master baseline at DEV-00 start: Odoo Community 20.0 final, confirmed in the local source `odoo/release.py` and against the official Odoo release notes (September 2026).

- Project directory: `C:\PycharmProjects\odoo20\custom_addons\vendor_price_revision_impact_simulator` (Windows).

- At DEV-00 baseline, no addon manifest or business implementation existed in this project directory. PR-01/PR-02 have since established the addon foundation and revision core models. The Odoo Community source and Python 3.14.6 environment exist in the parent development tree.

- PR-01 install/update verification used a disposable PostgreSQL 18.4 cluster on loopback and a dedicated temporary database. The cluster was stopped and the database/data directory removed after verification; there is no persistent PR-01 test database.



## Prompt roadmap and evidence ledger



Status values: `IN_PROGRESS`, `VERIFIED`, `BLOCKED`, `NOT_STARTED`. Each row tracks the requested prompt scope, tests executed, evidence, known issues, blockers, completion date, and next dependency.



| Prompt | Phase and scope | Status | Tests executed | Evidence | Known issues | Blockers | Completion date | Next dependency |

|---|---|---|---|---|---|---|---|---|

| PR-00 | M0 testing and governance foundation | VERIFIED | Static infrastructure checks PASS; runner safety guards PASS; Odoo business tests NOT_RUN | `evidence/DEV-00-validation.txt`; `TEST_REPORT.json` | Scope was testing infrastructure; no business addon existed at that stage | A disposable database was not configured during DEV-00; later PR-01/PR-02 runs used temporary isolated clusters | 2026-10-28 | M0 verified |

| PR-01 | DEV-01 Odoo module foundation | VERIFIED | QUICK static checks PASS; fresh install PASS (6 tests, including 4 addon tests and 2 Odoo web posttests); targeted update PASS (4 addon TransactionCase tests) | `evidence/DEV-01-install-update.txt`; `evidence/odoo-pr01-fresh-install.log`; `evidence/odoo-pr01-module-update.log`; `TEST_REPORT.json` | License release decision is pending; Odoo currently defaults omitted license to LGPL-3 | None for DEV-01 | 2026-10-28 | DEV-01 verified |

| PR-02 | DEV-01 vendor revision core models and lifecycle foundation | VERIFIED | QUICK fresh install PASS (20 Odoo runner-counted tests, 0 failures); TARGETED update PASS (19 tests, 0 failures); QUICK static checks PASS (13 checks) | `evidence/DEV-01-pr02-summary.txt`; `evidence/DEV-01-pr02-static-validation.txt`; `evidence/odoo-pr02-fresh-install.log`; `evidence/odoo-pr02-module-update.log`; `TEST_REPORT.json` | Evidence is metadata-only; no attachment upload/download. One initial app group only; expanded role separation is PR-03. Lifecycle choices are reserved but only Draft is available. | None for PR-02 | 2026-10-28 | PR-02 verified |

| PR-03 | DEV-02 advanced security and multi-company isolation | VERIFIED | Fresh install PASS (39); TARGETED security PASS (18); MILESTONE actual PR-02 upgrade regression PASS (37); preservation probe PASS; QUICK static PASS | `docs/SECURITY_MATRIX.md`; `evidence/DEV-02-pr03-summary.md`; `TEST_REPORT.json` | Standard Odoo supplierinfo access is independent; evidence is metadata-only; no chatter; Configuration role reserved for PR-04 | None for PR-03 | 2026-10-28 | PR-03 verified |

| PR-04 | DEV-02 company business and financial policy foundation | VERIFIED | Final QUICK fresh install PASS (56); focused TARGETED PASS (37); final MILESTONE update PASS (56); PR-03 preservation probe PASS; QUICK static PASS | `docs/CONFIGURATION_GUIDE.md`; `evidence/DEV-02-pr04-summary.md`; `TEST_REPORT.json` | Configuration definitions only; no simulation/approval/application engine. Operational SO/PO/stock/accounting tests NOT_RUN (models absent) | None for PR-04 | 2026-10-28 | PR-05 verified separately below |

| PR-05 | DEV-03 secure CSV/XLSX source intake and raw extraction | VERIFIED | Final fresh install PASS (88); focused TARGETED PASS (50); final actual PR04 update MILESTONE PASS (88); preservation and concurrent extraction/cancellation PASS; static PASS | `docs/IMPORT_ARCHITECTURE.md`; `evidence/DEV-03-pr05-summary.md`; `TEST_REPORT.json` | Raw extraction only; operational SO/PO/stock/account tests NOT_RUN; 500-row fixture measured, larger load/peak memory NOT_MEASURED | None for PR05 | 2026-10-28 | PR06 verified separately below |

| PR-06 | DEV-03 column mapping, structural validation, corrections and revalidation | VERIFIED | Fresh install PASS (115); focused TARGETED PASS (35); actual PR05 update MILESTONE PASS (115); preservation and four concurrency probes PASS; QUICK static PASS | `docs/IMPORT_VALIDATION_GUIDE.md`; `evidence/DEV-03-pr06-summary.md`; `TEST_REPORT.json` | Structural readiness only; operational SO/PO/stock/account tests NOT_RUN; large-load/peak memory NOT_MEASURED | None for PR06 | 2026-10-28 | PR07 verified separately below |

| PR-07 | DEV-04 exact product and vendor mapping | VERIFIED | Final fresh install 148, focused 47, actual PR06 update 148, preservation, five concurrency probes and static 78 PASS | docs/PRODUCT_MAPPING_GUIDE.md; evidence/DEV-04-pr07-summary.md; TEST_REPORT.json | Identity only; operational/browser UAT NOT_RUN; larger loads/peak memory NOT_MEASURED | None for PR07 | 2026-10-28 | PR08 remains NOT_STARTED |

| PR-08 | DEV-04 commercial normalization and vendor baseline | VERIFIED | QUICK 5, fresh 195, targeted 113, actual PR07 update 195, preservation, operational safety, nine concurrency probes and static 106 PASS | docs/COMMERCIAL_PRICE_VALIDATION.md; evidence/DEV-04-pr08-summary.md; TEST_REPORT.json | Unit comparisons only; browser UAT NOT_RUN; larger workloads/peak memory NOT_MEASURED | None for PR08 | 2026-10-28 | PR09 remains NOT_STARTED |

| PR-09 | DEV-05 read-only stock and incoming supply foundation | VERIFIED | Fresh 247, targeted 165, actual PR08 update 247, preservation, eight concurrency probes, 16-model operational safety and static 91 PASS | docs/SUPPLY_FOUNDATION.md; evidence/DEV-05-pr09-summary.md; TEST_REPORT.json | No demand allocation; conservative review routes; browser UAT NOT_RUN; supply loads/peak memory NOT_MEASURED | None for PR09 | 2026-10-29 | PR10 verified separately below |

| PR-10 | DEV-05 confirmed demand and unique analytical allocation | VERIFIED | QUICK2; targeted 235; fresh 318; actual PR09 update 318; preservation, eight concurrency probes, 18-model safety and static 106 PASS; 100-order workload measured | docs/DEMAND_ALLOCATION.md; evidence/DEV-05-pr10-summary.md; TEST_REPORT.json | Quantity allocation only; explicit review routes; browser UAT NOT_RUN; larger loads/peak memory NOT_MEASURED | None for PR10 | 2026-10-29 | PR11 NOT_STARTED |

| PR-11 | DEV-06 sales commercial exposure foundation | VERIFIED | QUICK9; targeted15; fresh67; actual PR10 update385; preservation, six concurrency probes and20-model safety PASS | docs/SALES_EXPOSURE_FOUNDATION.md; evidence/DEV-06-pr11-summary.md; TEST_REPORT.json | Sales references only; browser UAT NOT_RUN; larger loads/peak memory NOT_MEASURED | None for PR11 | 2026-10-29 | PR12 NOT_STARTED |

| PR-12 | DEV-06 RFQ/PO purchase commitment evidence | VERIFIED | QUICK11; targeted41; fresh66; actual PR11 update126; preservation, six real-session races and20-model safety PASS | docs/PURCHASE_COMMITMENT_EXPOSURE.md; evidence/DEV-06-pr12-summary.md; TEST_REPORT.json | Commercial references only; browser UAT NOT_RUN; larger stress/memory NOT_MEASURED | None for PR12 | 2026-10-29 | PR13 NOT_STARTED |

| PR-13 | DEV-07 inventory and replacement cost attribution | VERIFIED | QUICK7; TARGETED118; fresh44; actual PR12 update114; preservation, six races and operational safety PASS | evidence/DEV-07-pr13-summary.md; TEST_REPORT.json | FIFO warehouse/lot lineage incomplete; net replacement only; browser UAT NOT_RUN; larger loads NOT_MEASURED | None for conservative PR13 foundation | 2026-10-29 | STOP after PR13; PR14 NOT_STARTED |

| PR-14 | DEV-07 projected financial exposure engine | VERIFIED | QUICK9; TARGETED120; fresh57; actual PR13 update157; preservation, seven races and 22-model safety PASS | evidence/DEV-07-pr14-summary.md; TEST_REPORT.json | Explicit scenario/estimated/incomplete costs; browser UAT NOT_RUN; larger loads/memory NOT_MEASURED | None for documented PR14 scope | 2026-10-29 | STOP after PR14; PR15 NOT_STARTED |

| PR-15 | DEV-08 projected profitability and margin risk | VERIFIED | QUICK25; TARGETED96; fresh59; actual PR14 update112; preservation, nine races, 22-native/nine-upstream safety PASS | evidence/DEV-08-pr15-summary.md; TEST_REPORT.json | Projected affected scope; browser UAT NOT_RUN; larger loads/memory NOT_MEASURED | None for documented scope | 2026-10-29 | STOP after PR15; PR16 NOT_STARTED |

| PR-16 | DEV-08 independent financial reconciliation and review readiness | VERIFIED | QUICK14; TARGETED33; fresh6; actual PR15 update60; preservation, nine races and22-native/13-upstream safety PASS | evidence/DEV-08-pr16-summary.md; TEST_REPORT.json | Projected review only; browser UAT NOT_RUN; larger loads/memory NOT_MEASURED | None for documented scope | 2026-10-31 | STOP after PR16; PR17 NOT_STARTED |

| PR-17 | DEV-09 isolated vendor what-if scenarios | VERIFIED | QUICK7; TARGETED28; fresh8; actual PR16 update56; preservation,11 races and22-native/17-upstream safety PASS | evidence/DEV-09-pr17-summary.md; TEST_REPORT.json | Hypothetical only; browser UAT NOT_RUN; larger loads/memory NOT_MEASURED | None for documented scope | 2026-10-31 | STOP after PR17; PR18 NOT_STARTED |

| PR-18 | DEV-09 customer repricing recommendations | VERIFIED | QUICK10; TARGETED63; fresh43; actual PR17 broad update283 (pre-fix), final follow-up15; preservation,12 races,22-native/23-upstream safety;500/2000 lines and10000 stage references measured | evidence/DEV-09-pr18-summary.md; TEST_REPORT.json | Analytical only; browser UAT/FULL NOT_RUN; production capacity NOT_MEASURED | None for documented scope | 2026-10-31 | STOP after PR18; PR19 NOT_STARTED |

| PR-19 | DEV-10 approval routing foundation and maker-checker | VERIFIED | Source-bound fresh/QUICK/TARGETED/actual upgrade/preservation/races/safety/performance PASS | evidence/DEV-10-pr19-summary.md; TEST_REPORT.json | Routing only; browser UAT/FULL NOT_RUN; production capacity NOT_MEASURED | None for documented scope | 2026-10-31 | STOP after PR19; PR20 NOT_STARTED |

| PR-20 | DEV-10 approval decisions, quorum, delegation and validity | VERIFIED | Source-bound fresh/QUICK/TARGETED/PR16-19 milestone/actual PR19 upgrade/preservation/races/safety/performance PASS | evidence/DEV-10-pr20-summary.md; TEST_REPORT.json | Approval only; FULL/browser UAT NOT_RUN; production capacity NOT_MEASURED | None for documented scope | 2026-11-01 | STOP after PR20; PR21 NOT_STARTED |

| PR-21 | DEV-11 approved vendor application planning and read-only dry-run | VERIFIED | Final-source fresh/QUICK/TARGETED/PR19-20 milestone/actual PR20 update/preservation/races/no-write/performance PASS | evidence/DEV-11-pr21-summary.md; TEST_REPORT.json | Read-only planning; FULL/browser UAT NOT_RUN; cold/parallel RPC capacity NOT_MEASURED | None for documented scope | 2026-11-01 | STOP after PR21; PR22 NOT_STARTED |

| PR-22 | DEV-11 transactional approved vendor price application | VERIFIED | Final-source fresh/QUICK/TARGETED, actual PR21 upgrade MILESTONE/preservation, races, commit/replay and scale PASS | evidence/DEV-11-pr22-summary.md; TEST_REPORT.json | Synthetic only;2k apply63.68min/setup91.85min; browser/FULL NOT_RUN; no production capacity qualification | None for documented functional scope | 2026-11-02 | STOP after PR22; PR23 NOT_STARTED |

| PR-23 | DEV-12 post-application monitoring and operational integrity | VERIFIED | Final-source QUICK/TARGETED/security/races/successor/performance/MILESTONE/fresh and actual PR22-data preservation PASS | evidence/DEV-12-pr23-summary.md; TEST_REPORT.json | Read-only scope; bounded benchmark coverage; supplierinfo archive N/A; FULL/browser NOT_RUN | None for documented functional scope | 2026-11-02 | STOP after PR23; PR24 NOT_STARTED |

| PR-24 | DEV-12 advanced financial and audit reporting | IN_PROGRESS | QUICK11, TARGETED17, earlier-source fresh MILESTONE40; actual upgrade/preservation and seven report output groups PASS (source hashes explicit) | evidence/DEV-12-pr24-summary.md; TEST_REPORT.json | 17 retained-fact adapters; 21 validated output files; 100 original models/16 source files preserved | Full chronology, confidence/issues, remaining category fixtures and report concurrency pending | 2026-11-03 | PR25 NOT_STARTED |

| PR-25 | Reports, exports, and audit traceability | NOT_STARTED | â€” | â€” | â€” | â€” | â€” | Previous prompt verified |

| PR-26 | Financial and approval notifications | NOT_STARTED | â€” | â€” | â€” | â€” | â€” | Previous prompt verified |

| PR-27 | Scheduled monitoring and duplicate prevention | NOT_STARTED | â€” | â€” | â€” | â€” | â€” | Previous prompt verified |

| PR-28 | End-to-end automated business testing | NOT_STARTED | â€” | â€” | â€” | â€” | â€” | Previous prompt verified |

| PR-29 | Security, financial, and performance hardening | NOT_STARTED | â€” | â€” | â€” | â€” | â€” | Previous prompt verified |

| PR-30 | Odoo Apps Store packaging | NOT_STARTED | â€” | â€” | â€” | â€” | â€” | Previous prompt verified |

| PR-31 | Master release validation | NOT_STARTED | â€” | â€” | â€” | â€” | â€” | Previous prompt verified |

| PR-32 | Older version compatibility conversion | NOT_STARTED | â€” | â€” | â€” | â€” | â€” | Previous prompt verified |

| PR-33 | Final multi-version regression and release packages | NOT_STARTED | â€” | â€” | â€” | â€” | â€” | Previous prompt verified |



## Milestone gates



| Gate | Scope | State |

|---|---|---|

| M0 | Testing foundation | PASSED |

| M1 | Import, mapping, currency/UoM validation | PASSED (PR05â€“PR08 integration verified) |

| M2 | Sales, purchase, inventory, supply allocation | IN_PROGRESS (PR09â€“PR13 foundations verified; broader workflow/browser UAT not claimed) |

| M3 | Financial exposure, margin, what-if | PR14-17 documented analytical scope VERIFIED; broader UAT not claimed |

| M4 | Approval and maker-checker governance | NOT_STARTED |

| M5 | Safe price application, recovery, concurrency | NOT_STARTED |

| M6 | Financial, security, UAT, and performance regression | NOT_STARTED |

| M7 | Master Community release validation | NOT_STARTED |

| M8 | Individually verified additional Odoo versions | NOT_STARTED |



PR-00 verified the reusable infrastructure, not Odoo business behavior. PR-01 and PR-02 are verified on Odoo Community 20.0 with disposable-database install/update evidence. PR-03 is verified with fresh installation, focused security, and actual PR-02 upgrade/preservation evidence. PR-04 is VERIFIED with final fresh-install and actual PR-03 update evidence; PR-05 is VERIFIED with CSV/XLSX/attachment/security/install/update evidence. PR-06 is VERIFIED; PR-07 and PR-08 are VERIFIED; PR-09 remains NOT_STARTED.





## PR-04 completion and handoff



Implemented persistent company policy versions, margin overrides, risk intervals,

approval definitions and append-only configuration audit. Configuration

Administrators write only within authorized selected companies; authorized

manager/finance/director/auditor roles read only. Published versions and their

children are immutable; direct, nested, context and copy paths are guarded.

Company currency is captured per version. Publication requires complete risk and

finance approval scales plus a default margin. Future dated versions cannot

overlap published inclusive periods. Company-row mutation serialization protects

concurrent policy edits/publication.



The retrieval contract returns dated published policy records and child provenance

without financial calculations, approval decisions, operational writes or

notifications. Draft inspection is distinct from published operational retrieval.

Nineteen configuration test methods cover constraints, hierarchy, role/company

boundaries, nested commands, history, defaults and dependencies. Existing

foundation/core/security suites remain in the final 56-test regression. The

focused 37-test run was followed by the final whole-addon MILESTONE regression.



Earlier failed attempts remain in the evidence history; their four runtime issues

were corrected. Final install and update runs have zero failures. Operational

SO/PO/stock/accounting tests and browser UAT are NOT_RUN, accurately separated

from supplier/product/revision/cron preservation checks. Temporary databases,

cluster, filestores, baseline checkout and private configs were removed after

clean shutdown. No existing project or production database was used.



PR-05 consumes these policy contracts only for source intake; financial behavior remains deferred. No financial engine,

approval workflow or controlled application readiness is claimed.





## PR-05 completion and handoff



Added secure upload wizard, import batch, immutable raw rows, immutable extraction

attempt history and company-specific technical resource limits. Original CSV/XLSX

bytes are retained once in protected evidence attachments, with authentic SHA256,

uploader/time/company/vendor/revision provenance. CSV encoding/delimiter selection

is explicit; XLSX requires safe archive/XML structure and explicit selection for

multiple worksheets. Formulas remain untrusted raw content. Header order, duplicate

names, leading zeros, blank/zero distinctions and source positions are preserved.



Company/role protection covers direct ORM, nested commands, context defaults,

read/export/grouped queries and HTTP content downloads. Duplicate sources retain

evidence in duplicate_review without staging. Failed attempts retain safe errors,

source bytes and history; corrected settings allow atomic/idempotent retries.

Two independent-session probes verified extraction/extraction and

extraction/cancellation serialization without duplicate rows or false success.



Final fresh/update suites each ran 88 tests; focused intake/security ran 50.

Actual PR04 upgrade preserves revisions, lines, manual evidence, supplier price,

published policy values/write dates and audit identities. Earlier failed test

attempts and a corrected audit-order probe remain in TEST_REPORT.json. Final

checks pass; temporary cluster/databases/filestores/configs were removed after

clean shutdown. No existing or production database was used.



PR06 must consume immutable raw_cells/headers, source sheet/logical/physical

positions, formula markers, duplicate_review and safe technical failures, while

adding separate business validation results. No product matching, currency/UoM

normalization, financial engine, approval execution or price application was

implemented. PR06 remains NOT_STARTED.





## PR-06 completion and handoff



Extended PR05 batches/rows with explicit ordinal-based mappings, lexical validation,

immutable run/results/issues, correction/exclusion history and review-input events.

Raw source rows, original files and fingerprints remain unchanged. Mapping/settings,

correction, exclusion/reinstatement and inherited-date changes invalidate current

ready results and counters immediately. Pending counts also reconcile existing

PR05 batches without rewriting raw rows/write dates.



Structural readiness is separate from extraction, product resolution and commercial

price validity. Exact duplicate groups include effective mapped terms, quantities,

currency and dates; no random winner is selected. Decimal/date conventions and

revision currency/date inheritance are explicit and provenance is snapshotted.

No automatic product, UoM, currency/FX, price comparison or financial work occurs.



27 new test methods plus prior regression executed: final fresh installation 115,

focused structural/security 35, final actual PR05 upgrade 115. Preservation verifies

existing batches, attachments/bytes/hashes, raw cells/IDs/write dates, revisions,

policies and audit identities. Four two-session probes cover validation competing

with validation/mapping/correction/cancellation. Initial SQL conflict messaging and

an interrupted-upload test's empty-database assumption and inactive mapping

visibility on reactivation were corrected; failed

attempts remain in history. No tests were removed or weakened. Disposable database,

cluster, filestores, baseline checkout and configs were removed after clean shutdown.



The synthetic 500-row reference reconciles 480 structurally ready, 12 blocked and

8 review-required rows. Operational SO/PO/stock/accounting tests are NOT_RUN because

those models are absent; other load benchmarks and peak memory are NOT_MEASURED.

PR07 must consume only current structurally-ready rows and snapshot provenance,

then perform its own product resolution. PR08 must independently verify commercial

currency/UoM/quantity/date applicability. At the PR06 handoff neither phase had

started; subsequent PR07 completion is recorded below.





## PR-07 completion and handoff



Exact company/vendor identity matching resolves current structurally-ready rows to

existing product.product variants using authorized supplier references, configured

internal SKU/barcode rules and unchanged independently verified registry evidence.

No fuzzy/name or arbitrary template-variant choice occurs. Explicit company policy,

versioned reusable/one-row mappings, independent Purchase Manager verification,

retained audits/resolutions, current status counters, bounded candidates and stale

checks preserve PR06 source/correction provenance. Public ORM/context forgery,

foreign wizard links and related current foreign-product labels are protected.



33 new methods plus earlier regression executed. Final clean installation 148,

focused product/PR06/PR05 security 47, actual PR06 update 148, preservation probe,

five independent-session probes and static 78 checks all PASS. Earlier freshness,

encoding, configuration-only cache refresh and duplicate-source fixture failures,

and sandbox PostgreSQL startup BLOCKED evidence remain retained. No tests weakened.

The 500-row fixture resolves 500 distinct products in 2.307 seconds on the final clean

install; bulk product search bound is asserted. This is not a general load guarantee.



Disposable cluster/databases/filestores/configs/baseline checkout removed after

clean shutdown. No existing database or production data was used. Operational

SO/PO/stock/accounting fixtures and browser UAT remain NOT_RUN; larger benchmarks

and peak memory NOT_MEASURED. Exact baseline and frozen final source hashes,

logs, driver, complete A-I report and operator guide are retained in evidence/docs.



PR08 must call get_product_resolved_rows(), retain current PR06 and PR07 evidence,

use actual variant IDs and exact company/vendor context, then independently

validate current product/source UoM, currency, MOQ/quantity/date applicability and

commercial baseline. Identity mapping is not commercial approval. No FX/UoM

conversion, financial simulation, vendor-price application or repricing occurred.

STOP after PR07; PR08 remains NOT_STARTED.





## PR-08 completion and handoff



Implemented explicit independently verified commercial context, Decimal UoM/FX/net

normalization, normalized quantity tiers, effective-date rules, scoped vendor

baseline selection, old/proposed per-unit deltas and immutable snapshots/issues.

Historical agreements require documented independent attestation tied to captured

supplier evidence. Missing baseline/FX/UoM/tax basis remains incomplete. Common-

rate and date-specific effects are distinct; hypothetical FX is Finance governed.

No supplier, SO/PO, stock or accounting record is changed by validation.



Relevant integration fixes make description-only row mappings stale after source

identity changes and let test fixtures retain an already existing company identity

policy. No assertions removed or weakened. Earlier JSON/setup, fixture expectation,

upgrade fixture and probe representation failures remain in actual report history.



47 new methods across six classes executed. Final helpers 5, fresh 195, targeted 113,

actual PR07 update 195, preservation, nine real-session races, existing operational

safety and static 106 checks PASS. The operational database held actual confirmed

SO/PO, valued done stock.move(value3500), positive quants and a posted balanced

entry before comparison; exact 15-model snapshots remain unchanged. Odoo20 valuation

is stock.move.value here; absent stock.valuation.layer is not falsely claimed.



The final 500-row fixture gives 500 valid comparisons/current snapshots in 5.700 seconds,

with 3 bulk supplier searches. Larger benchmarks/peak memory NOT_MEASURED; manual

browser UAT NOT_RUN. All temporary cluster/databases/filestores/configs/baseline

checkout removed after clean shutdown. Exact PR07 archive, 58-source final hashes,

source-qualified logs, driver and complete A-I report are retained in evidence/docs.



PR09/PR14 must call get_commercially_valid_rows(), retain current PR06/PR07 and

comparison version/digest, use exact company/vendor/variant, common UoM, normalized

prices, explicit FX/date/tier assumptions and unresolved states. Actual quantity/

date consumers use resolve_vendor_tier(); unit delta is not total exposure, margin,

realized benefit or price approval. No allocation, approval/application or later

financial engine implemented. STOP after PR08; PR09 remains NOT_STARTED.





## PR-09 completion and handoff



Read-only current stock and supplier-unreceived PO evidence is implemented for

current PR08 exact variants. Explicit audited company/warehouse/cost grants and

exact location classifications gate a bounded analytical service. Native source

ACLs are not globally broadened. Immutable versioned snapshots/buckets/issues

separate physical, reserved, eligible free, received-pending-putaway, incoming,

verified firm terms and nonadditive transfers. Quant reservation is deducted once;

PO backorders/returns/short-closing and receipt steps reconcile without duplication.

Missing/inconsistent quantities and costs remain explicit. Standard/AVCO are

accounting references; exact FIFO quant cost is unavailable.



Independent terms review is tied to original PO evidence and UoM definitions.

Redirected physical receipts/returns cannot disclose unselected warehouse evidence.

Current source digests, app serialization and existing-row locks protect the

read-only handoff; no demand reservation/allocation or price application occurs.



52 new methods; final fresh 247, targeted 165, actual PR08 update 247,

preservation, eight real-session probes, 16-model operational safety and static

91 checks PASS on the frozen source. Earlier field/fixture/short-close/permission

expectation failures and upgrade fixture/representation failures remain in history.

Existing absence assertions were replaced with operational preservation assertions

for the new Community purchase_stock dependency; passing business assertions were

not removed or weakened. Exact source bytes, corrections, product/commercial

evidence, policies, prices and existing confirmed/valued/posted records survive

the actual PR08 upgrade; ordinary update creates zero supply snapshots.



The disposable PostgreSQL cluster/databases, filestores, configs and baseline

checkout were removed after verified shutdown. Browser UAT is NOT_RUN; the supply

100/500/2000-product, 10000-source benchmark matrix and peak memory are NOT_MEASURED.

Known review routes and the service trust boundary are documented in

docs/SUPPLY_FOUNDATION.md; complete A-I evidence is in evidence/DEV-05-pr09-summary.md.



PR10 must call get_current_supply() in a fresh authorized transaction, check

per-variant/warehouse/UoM completeness and cost confidence, retain version/digest

and source keys, and subtract reservations only once. Protected incoming is a

subset of incoming, not additional supply; transfer references are nonadditive.

PR10 must add unique demand attribution/claims and its own concurrency guarantees.

STOP after PR09. PR10 remains NOT_STARTED; M2 is not yet complete.





## PR-10 completion and handoff

Read-only confirmed sales demand and independent conditional quotation scenarios
consume only current PR09 supply. Explicit audited customer-demand opt-in on each
warehouse grant protects customer/order projections separately from cost access.
No native operational administration ACL is added. Exact sales lines, delivery
boundaries, partial/backorders/short-close and return review prevent duplicate
demand. Exact quant/move-line dimensions and downstream sale/procurement lineage
preserve reservations and direct incoming ownership. Only confirmed owners receive
reservation-backed coverage; draft-linked reservations remain unavailable/reviewed.

A stable versioned policy allocates actual reservations/direct links/free/timely
incoming with a unique remaining-capacity ledger. Input ETA requires an explicit
documented Input-to-saleable planning delay; quality/staging/transit and ambiguous
inputs remain unresolved. Same-warehouse/date rules, residual procurement and
mutually exclusive uncertainty reconcile each line and source. Confirmed priority
is preserved across independent quote/portfolio scenarios. No monetary exposure,
actual reservation, repricing, approval execution or vendor-price application occurs.

71 new methods across seven core classes plus one workload class executed.
Final QUICK2, targeted235, fresh318, actual PR09 update318, preservation,
eight real-session races, 18-model operational safety and static106 checks PASS
on the frozen68-file source. References A/B/C yield new procurement100/80/50;
D keeps baseline200/new100 separate from conditional270/new170. The measured
100-order/100-line workload allocates free100 from demand200, leaving new100, in
0.848s with one sales-line bulk projection and 3 bulk movement projections.
This is one synthetic workload, not a larger-load or peak-memory guarantee.

Earlier draft-view/ISO datetime/empty-JSON/export fixture and multistep automatic
reservation setup failures remain in history. Existing passing business assertions
were not weakened. Ordinary PR09 update preserves original source bytes,
corrections, identity/commercial history, policies, existing supply snapshots and
confirmed/reserved/valued/posted records; it creates no allocations and enables
no demand grants automatically. Temporary cluster/databases, filestores, private
configs and baseline checkout were removed after confirmed shutdown.

Browser UAT is NOT_RUN; 500-order/2000-line/10000-source stress and peak memory
are NOT_MEASURED. Review/permission/normalization/source-lock limits and complete
Aâ€“I evidence are in docs/DEMAND_ALLOCATION.md and evidence/DEV-05-pr10-summary.md.

PR11 must call get_current_allocation() in a fresh authorized transaction, retain
allocation/supply versions/digests/scenario and exact sales/source identities,
inspect unresolved quantities/cost provenance, and preserve all company/warehouse/
role/cost controls. Reservations are already accounted for; protected incoming
is a subset, and standalone scenarios cannot be summed. Contract selling-price
context and detailed monetary exposure remain future work. STOP after PR10.
PR11 remains NOT_STARTED; M2 is not marked complete.

## PR-11 completion and handoff

Immutable customer sales terms consume only current PR10 allocation. Exact SO lines,
actual recorded prices, Decimal discount/native tax-excluded basis, partial quantity,
UoM/FX provenance and separate confirmed/conditional scenarios preserve commercial
meaning. Global adjustments remain order-only review; missing data is not zero.
Documented Sales Manager protection assessments retain historical evidence without
authorizing repricing. Separate audited grants plus native Sales/company/warehouse/
source-order rules protect customer terms and prevent supplier-cost traversal.

67 new methods; final QUICK9, targeted15,
fresh67, actual PR10 update385, preservation,
six real-session races and20-model operational safety PASS. The100-line
workload measured1.159s after upstream preparation; no larger-load or memory
guarantee is claimed. Static/source/UTF8/cleanup evidence is retained. Earlier draft
and sandbox failures remain in report history; passing assertions were not weakened.
No operational customer/vendor price, order, stock, valuation or accounting change
occurs. Actual prior PR10 source/allocation evidence survives upgrade. All disposable
runtime resources were removed after verified shutdown.

Browser UAT is NOT_RUN; larger500/2000/10000-demand and peak-memory measurements are
NOT_MEASURED. Read docs/SALES_EXPOSURE_FOUNDATION.md and evidence/DEV-06-pr11-summary.md
for trust boundaries, source-lock/limit/freshness assumptions and complete Aâ€“J evidence.

PR12 must consume fresh get_current_sales_terms(fx_date), exact line/scenario/currency/
UoM/price/quantity and allocation IDs, independent protection/value/FX statuses and
unresolved issues. It must independently verify purchase commitments/amendments/
supplier protection. No final margin, financial aggregation, repricing recommendations,
approval or price application is implemented. STOP after PR11; PR12 NOT_STARTED.

## PR-12 completion and handoff

Exact recorded RFQ/PO commercial terms reuse PR09 authoritative incoming quantities
and optional current PR10 scenario attribution. Conditional RFQs, source-currency
open commitment references and disputed amendment scenarios remain separate.
Independent supplier assessments preserve dates/references/current terms without
approving PO edits. Optional native-authorized bill/credit references never replace
receipt quantities. Company/cost/native-billing/demand scope and immutable evidence
protect confidentiality. No operational purchase/stock/accounting mutation occurs.

66 new methods; final QUICK11, targeted41,
fresh66, actual PR11 update126, preservation,
six real-session races and20-model operational safety PASS.100-line scoped
refresh/collection measured1.158s; larger workloads/peak memory NOT_MEASURED,
browser UAT NOT_RUN. Exact72-file PR11 archive and frozen76-source final
ledger identify real evidence. Earlier ISO/fixture/stale-expectation failures are
retained; no passing business/security assertion was weakened. Prior PR11 sales
snapshots/reviews, source bytes, mappings, commercial/supply/allocation evidence and
actual confirmed/reserved/valued/posted records survive update. Disposable runtime
resources removed after confirmed shutdown.

Read docs/PURCHASE_COMMITMENT_EXPOSURE.md and evidence/DEV-06-pr12-summary.md for
complete Aâ€“J evidence, trust boundaries and source limits. PR13 must call fresh
get_current_purchase_terms(...) and retain exact bucket/line/entry IDs, quantity,
currency/UoM/date/tier/FX, agreed/protected/proposed/request distinctions and every
independent completeness/evidence status. It must independently verify inventory
cost sources and landed/replacement basis. No PR13 cost attribution, final exposure,
margin, repricing, approval execution or price application is implemented.
STOP after PR12; PR13 remains NOT_STARTED.


## PR-13 initial verification history

PR12 baseline 76-file ledger verified and archived before edits (archive SHA256
58e17a7d296ca9ad61d19f4abe16af35d1ef8ef95b85760c3ab1df27a66b6618).
Read-only cost snapshot/entry/issue service, scoped access and review UI implemented.
Initial fresh-install failures retained; incorrect PR12 scope argument corrected,
and native documented zero is tested separately from unevidenced default zero.
Those gates were pending at this initial checkpoint; final evidence and status follow below.
No PR14 financial engine, approval, price application or operational mutation added.


## PR-13 completion and handoff

Read-only cost snapshots/lines/issues attach one result to every current PR10
entry. Standard/AVCO company references, reconciled native FIFO remaining-move
pools, exact current PR12 protected terms and PR08 per-entry replacement/MOQ/date/
FX scenarios preserve separate cost confidence and quantity authority. Historical
landed charges are never added twice. Unknown cost remains null; physical FIFO
warehouse/lot lineage and future unevidenced components remain incomplete.

Final source: 80 files, SHA256 fb13e236dc1fd115500baf88a603743dc10d37f2429970eff4576ea1dbb3c264. 44 new tests; final QUICK
7, TARGETED 118, fresh
44, actual PR12 update 114, cold
preservation, six real-session races and 20-model operational safety PASS.
Prior failures remain history. 100-entry collection 0.770s; larger loads/
memory NOT_MEASURED, manual browser UAT and posted landed-cost fixture NOT_RUN.
Runtime removed after confirmed shutdown. No operational financial/stock changes.

See docs/COST_ATTRIBUTION_FOUNDATION.md and evidence/DEV-07-pr13-summary.md for
complete Aâ€“J evidence and strict fresh-getter/source reconciliation/security
contract. No consolidated exposure, profitability, approval or price application.
STOP after PR13. PR14 remains NOT_STARTED.


## PR-14 verification checkpoint

Core financial snapshot/line/issue service and secure read-only UI are implemented.
Initial three completed fresh runs and their failures are retained in TEST_REPORT:
53/54 (upstream decimal fixture),55/57 (native confirmed-pricelist/export fixture),
56/57 (source-currency versus company-FX assertion). An interrupted fourth attempt
had no completed result and is not PASS evidence. The current source also keeps
before-effective-date hypothetical procurement labeled scenario-only. Mandatory
fresh/targeted/upgrade/preservation/concurrency/operational checks remain pending
until actual final-source results are recorded. PR15 remains NOT_STARTED.


## PR-14 completion and PR15 handoff

Financial snapshot/line/issue models consume fresh PR08â€“13 sources without a second
allocation engine. Source-specific baseline/revised costs preserve owned stock and
protected PO terms; independent old tiers use actual per-entry procurement quantity.
Signed deltas, explicit common/separate-date FX, UoM, grouped weighted cost and
raw/report rounding reconcile. Confirmed and conditional scenarios remain separate.
Unknown costs stay null; total-cost completeness differs from delta completeness.
Numeric completeness never upgrades estimates or hypothetical buying/FX to actuals.
Company/cost/demand/customer/native scope and immutable evidence protect results.

Final84-source ledger:db8d737af1d9655e4d3accdd6d41141529b19b90ff07ce0f39561af431e59f28; 53 new methods. QUICK
9, TARGETED120, fresh
57, actual PR13 update157, cold
preservation, seven real-session races, 22-native-model and six-upstream-
model safety PASS. Earlier fixture errors remain history.100-entry financial
collection measured2.598s; other loads/peak memory NOT_MEASURED; manual
browser UAT NOT_RUN. Dedicated runtime removed after confirmed shutdown.

See docs/FINANCIAL_EXPOSURE_ENGINE.md and evidence/DEV-07-pr14-summary.md for Aâ€“J
results, limitations and strict fresh-getter/reconciliation/security contract.
PR15 needs current compatible PR11 selling values, complete cost basis and governed
risk thresholds; no margin/risk/approval/application/customer repricing implemented.
STOP after PR14. PR15 remains NOT_STARTED.


## PR15 development verification checkpoint

Exact PR14 84-source archive and retained PR00â€“14 evidence verified before edits.
Projected profitability/risk service, secure line/aggregate/reason views and governed
PR04 erosion/negative-profit dimensions are implemented. First fresh run54/55:
one revocation test retrieved child relations after access had been revoked; the
test now captures references first and asserts denial for every model. A second
attempt was intentionally stopped to correct an expired-quotation fixture before
claiming results. Corrected candidate fresh58/58 PASS is development evidence only:
final highest-line severity and readable aggregate labels were added during that
run, so its source_changed flag excludes it from final verification. Final-source
QUICK/TARGETED/upgrade/preservation/races/safety and repeat fresh gates are pending.
PR16 remains NOT_STARTED; no repricing, approval or application implemented.


## PR15 completion and PR16 handoff

Projected profit, margin, signed change/reduction and pp erosion reuse exact PR11/14
sources. Governed PR04 margin/exposure policies and added erosion/negative-profit
dimensions classify baseline/revised risk with independent confidence/completeness.
Exact sales lines and amount-sum order/product/customer/company groups preserve
confirmed/conditional scopes. Immutable, versioned, current-source snapshots protect
derived cost confidentiality. No native commercial/stock/accounting mutations.

See evidence/DEV-08-pr15-summary.md for complete AÃ¢â‚¬â€œJ actual evidence and limitations.
Final source ce5b7dfb34f95217fadc6b80284bb6ea56983b9023f93e88e1984c272a50173f. Runtime removed after confirmed shutdown.
PR16 full-source reconciliation/sign-off, repricing, approvals and application are
not implemented. STOP after PR15. PR16 remains NOT_STARTED.


## PR16 development checkpoint

Exact90-source PR15 baseline archived before edits; retained PR00-15 PASS evidence
and native20.0 Community source checked. Independent equations, typed check evidence,
coverage/readiness, immutable exception review and scoped UI are implemented.
Initial fresh45 tests:14 passed,31 errors from a revision/evidence link assumption.
Focused reference then identified removed uom.rounding; corrected to native Odoo20
Product Unit decimal precision. Focused full financial reference now PASS. Complete
PR16 focused suite is running with added real reservations/partial receipts and
controlled exception/source-access tests. Final mandatory gates remain pending;
no PR16 verification or PR17 implementation claimed at this checkpoint.


## PR16 focused repair checkpoint

Focused49 tests:39 passed,2 failed and8 errors. Empty source-capacity JSON is now
handled as an empty pool; exact later PR12 protection is checked even under an
older PR10 unverified label. New fixtures now use a real alternate variant and the
actual other-company user; Purchase-only grouped reads assert zero authorized
records while direct record reads/exports stay denied. Ten formerly failing cases
PASS. Final source also retains explicit numeric currency/UoM, hides unknown numeric
cells, counts explicit exclusions and supports legitimate stock-only no-PO scope.
Frozen final95-source hash8f3b611ea9c6c24c6cfcbc40f7180174d06b486e753db439a9f6b02797af31cf.
Mandatory final-source install/integration/upgrade/race/safety gates are running.
PR17 NOT_STARTED; no approval/sign-off/application authority added.


## PR16 completion and PR17 handoff

Independent named source/quantity/revenue/cost/exposure/profit/risk checks retain
exact evidence, duplicate controls, completeness counts and strict review readiness.
Immutable versioned runs and append-only exceptions/reviews cannot grant approval.
Governed strict/default versus documented-projection readiness preserves confidence.
Actual final-source gates and limitations are in evidence/DEV-08-pr16-summary.md.
Final source a5dcea405b6f3406ece4fea569b5decdb74e3b4008bef2335facaaf7d8d71eb1. Runtime removed after confirmed shutdown.
No native source or upstream analytical mutation. No sign-off/application.
STOP after PR16. PR17 remains NOT_STARTED.


## PR17 implementation and focused verification checkpoint

Exact95-source PR16 baseline archive and PR00-16 retained evidence checked before
changes. Scenario headers, immutable input/product-PO line revisions, immutable
result/details and append-only selection events use existing company/cost/customer
boundaries. Shared PR08/13/14/15 services and independent PR16 controls preserve
baseline source quantities, costs and customer revenue. Separate governed optional
scenario landed policy preserves the original net-price baseline. No PR18 work.

Initial fresh installation loaded models/security/views, then was stopped after
repeated empty-required-JSON issues. Explicit issue containers corrected that
Odoo20 behavior. Focused four-alternative reference PASS. First complete focused
selection:27 passed,8 failed/error of35 (including four failing permission subtests).
Archive guard used a cached display status; it now reads latest immutable event
server-side. A duplicate policy fixture publication and incorrect permission test
actors were corrected; pure Purchase/Sales remain denied while combined explicitly
granted manager read access remains intentional. A missing-source-charge fixture
now asserts the upstream commercial blocker rather than fabricating a baseline.
Current repair subset and all security cases are running. Final source gates have
not passed yet; PR17 remains IN_PROGRESS and PR18 NOT_STARTED.


## PR17 frozen-source fresh-install checkpoint

Final102-source ledger1a6509588ae4635cc9ebaf26f7dd1766a53b5d5bd53d8d8e771465625e157f11.
Fresh installation PASS38/38 (34 new methods plus4 foundation), source unchanged
through execution. Four complete numerical alternatives, USD90/44 decomposition,
exact protected-PO600 hypothesis, positive governed future landed sensitivity,
explicit grouping, partial-product inheritance, quotation portfolio, immutable
versions and all scoped security cases passed. Final QUICK/TARGETED/archived PR16
upgrade-preservation/race/safety gates remain pending. No VERIFIED claim until
those gates and cleanup pass. PR18 remains NOT_STARTED.


PR17 final-source QUICK7/7 and TARGETED52/52 PASS after fresh38/38. Actual PR16
archive installation PASS4 foundation tests; synthetic seed/cold capture PASS after
explicit Finance actor and retained owner/company context setup corrections.
Those two failed setup logs remain history. Broader actual-update regression and
preservation are running. Source102-file hash remains unchanged.


## PR17 final FX boundary and retained-history atomicity checkpoint

Actual PR16 upgrade executed263 tests:262 PASS,1 FAIL,0 errors. The old PR16
atomicity test assumed globally empty reconciliation tables although the upgrade
intentionally retains PR16 runs/checks/exceptions/reviews. Its assertions now
compare every prior stored value before/after failure and forbid leaked records for
its own batch, preserving the original empty-database case and adding seeded-data
protection. No passing assertion is weakened. The broad FAIL log is retained.

Review additionally identified a method-label boundary: price-only common FX must
use a common-rate baseline, rather than silently retaining a two-date FX effect.
A narrow input guard and real two-date90/94 regression were added; explicit combined
10.9@95 remains supported. The pre-guard102-source archive and ledger retain the
broad attempt. AST/unchanged-file checks will prove the exact narrow delta; all new
scenario/FX cases and the prior lifecycle class rerun on final source. No unchanged
upstream full-suite repeat is claimed. New frozen hash:
a5adff47c3028765f925f2a26c4d980371b829bee8e43136a129f4d1714a5bb0.
Final fresh/QUICK/TARGETED/update-follow-up/preservation/races/safety are pending.
PR17 IN_PROGRESS; PR18 NOT_STARTED.


## PR17 completion and PR18 handoff

Isolated immutable assumptions and results preserve exact PR16 baselines.
Shared PR08/13/14/15 services and independent PR16 controls preserve missing-data,
source-confidence and protected supply/revenue invariants. Real final-source gates
and limitations are recorded in evidence/DEV-09-pr17-summary.md.
Source f377aa420b1cf28e459df5b20f7607df42b8dc33ed1d4ba0c4109e2625faecf8. Owned runtime removed after confirmed shutdown.
No supplier acceptance, operational repricing, approval or application.
STOP after PR17; PR18 remains NOT_STARTED.


## PR18 implementation and focused repair checkpoint

PR17 prerequisite audit and exact 102-file archive verified before edits. PR18
implements immutable customer targets/options/reviews and native tax/discount
inversion with source currency/UoM, eligibility and supplier ceilings. Initial
fresh registry failure (long generated M2M relation) and subsequent 37/41 run
are retained in TEST_REPORT.json. Focused four-case repairs PASS4: new menu
expectation, Decimal-context test, tax fixture names and actual PR16 empty JSON
risk-reason handling. The latter preserves undefined-margin review behavior.
A new foreign USD/box10 test initially hit native confirmed-order pricelist
protection during setup; moving fixture setup before confirmation PASS1.
No production guard was bypassed. Exact PR17 file/AST preservation and syntax
checks PASS324. Frozen final 108-file source hash:
527ee0680052c95a55510ff87cc540063d6e2c381fe740208a99edb067f688eb.
Fresh install, QUICK/TARGETED, actual PR17 upgrade/preservation,12 races and
operational safety remain pending. PR18 IN_PROGRESS; PR19 NOT_STARTED.


## PR18 final-source gate checkpoint

Source527ee0680052c95a55510ff87cc540063d6e2c381fe740208a99edb067f688eb:
fresh42/42, QUICK10/10, TARGETED62/62 PASS with nonzero actual Odoo summaries
and unchanged source hashes. Reference/partial/tax/foreign-USD-box10 markers
execute. Observed100-line generation3.291s;10 repeated generations9.122s with
one header. These are synthetic observations, not production capacity.
Actual archived PR17 installation PASS4; retained-data seed and cold capture
PASS before PR18 schema registration. Broad actual upgrade still running.
Required remaining gates: update regression, exact retained-history preservation,
12 separate-session races,22-native/23-upstream safety, representative500/2000
native-price workloads with10000 five-stage financial references and runtime/
query/sampled-RSS measurements, then stopped-runtime cleanup. No pending gate
is represented as PASS. PR18 IN_PROGRESS; PR19 NOT_STARTED.


## PR18 final-review rounding finding (investigation pending)

A constructed partial-quantity USD/discount case indicates that proportionally
splitting original rounded revenue can differ from a native rounded unchanged
subtotal. Pending real regression:3 units atUSD3.35 less10%, rate90, scenario
cost619.86, target826.48; unchanged2-unit native subtotalUSD6.03. A candidate must
be validated against that native unchanged portion, not only a proportional share.
The draft test is retained in evidence/pr18-partial-rounding-regression.txt, outside
active source while the original broad upgrade run finishes. Exact108-file source
archive/ledger retained as pr18-prerounding-*; current source not changed mid-run.
This finding and remaining runtime gates block PR18 completion. PR19 NOT_STARTED.


## PR18 broad update PASS and native partial rounding correction

Actual PR17-to-PR18 update PASS283/283, preservation PASS across77 retained
models/source bytes/native states, source527ee0680052c95a55510ff87cc540063d6e2c381fe740208a99edb067f688eb unchanged during run.
The new partial USD/10% discount regression then reproduced actual native margin
24.97458243% below25 although proportional forecast claimed target reached.
Correction uses native original-price remaining quantity subtotal, source/company
currency rounding, true native net unit basis for percentage caps, calculationv2.
Focused regression PASS1, strengthened restrictive-cap assertion PASS1: candidate
USD3.51 =>827.10 reaches target; USD3.50 cap =>826.20 leaves0.28 residual.
Exact108-file pre-fix archive and AST prove only customer_line/calculationversion
and one new test changed;38 earlier tests unchanged. Static PASS442.
Final frozen108-file ledger: evidence/pr18-verified-source-sha256.json
Final-source fresh/QUICK/TARGETED/focused actual update/preservation,12 races,
native safety and500/2000-line performance remain pending. Earlier283-pass
broad evidence retains its exact pre-fix source; no final-source283 rerun claim.
PR18 IN_PROGRESS; PR19 NOT_STARTED.


## PR18 corrected-source verification checkpoint

Frozen ae4bc60390222ee1f6c7e273f1c9a56a4405c43fd4e5634b8c21731c55dcf2dc:
fresh43/43, QUICK10/10, TARGETED63/63 PASS; source unchanged in each run.
Fresh includes the actual native partial USD/discount/capped residual regression.
Observed100-line generation3.686s;10 repeated generations10.911s, one header.
Actual-upgrade focused follow-up and original77-model preservation now running.
Pre-fix actual broad283/283 remains separately bound to its exact source archive;
static442 checks constrain the precise subsequent method/version/new-test delta.
Races, native safety, representative performance and cleanup pending.
PR18 IN_PROGRESS; PR19 NOT_STARTED.

## PR18 completion and PR19 handoff

Immutable recommendations and native pricing references verified on frozen source ae4bc60390222ee1f6c7e273f1c9a56a4405c43fd4e5634b8c21731c55dcf2dc.
Actual source-bound gates and limitations: evidence/DEV-09-pr18-summary.md.
Financial completeness, commercial feasibility and risk remain separate. No live
repricing, acceptance or management approval. Disposable runtime removed after
verified shutdown. STOP after PR18; PR19 remains NOT_STARTED.


## PR19 initial implementation and QUICK checkpoint

Exact108-file PR18 source/evidence audited and archived before edits. Odoo20
Community remains the verified target; official nightly release and local release
hash checked at start. New approval request/stage/evidence/event/issue models,
opt-in PR04 policy extensions, explicit amount/risk routing, independent matching,
source/role/company guards, immutable submission, controlled lifecycle and protected
first-stage internal activities implemented. No decision or price application.
Initial QUICK11/11 PASS. First reference run found the actual source scope key is
confirmed_baseline (fixed); second exposed native required-JSON empty-dict NULL
semantics (nonempty audit envelope fixed). Third INR1500 real-source reference
PASS1: one independent Purchase Manager stage ready, no decision/native price change.
All new workflow/security cases are now running. Initial failures retained in
TEST_REPORT.json. Final freeze/install/update/preservation/races/safety/performance
still pending. PR19 IN_PROGRESS; PR20 NOT_STARTED.


## PR19 fresh-install checkpoint

Final initial freeze 2a4eabcd5c33bd83f0ef5b0bee3418ee6349acbe948e1df7be9f67bbdd591f74:
116 source files; fresh41/41 PASS, source unchanged during run. Static666 PASS
proves exact104 old files unchanged and four explicitly extended integration files.
Focused manual/quorum/decrease/source-grant repairs7/7 PASS before final freeze;
all included in fresh41. New-version publication rollback regression included.
Native/upstream safety, actual PR18 upgrade, real races and representative workload
measurements remain pending. PR19 IN_PROGRESS; PR20 NOT_STARTED.


## PR19 concurrency and safety checkpoint

Frozen source unchanged. Actual8/8 two-session races PASS:
evidence/pr19-concurrency-20261031T133156Z.log. Duplicate prepare/submit,
source sales price, future policy publication, scenario assumptions, source cost
grant, reviewer role and reviewer company races retain serialization/retry and
currentness assertions. Operational22-native/27-upstream preservation and protected
attachment negative checks PASS. Initial synthetic fixture failures remain visible.
QUICK/update TARGETED/actual PR18 upgrade-preservation/performance running
sequentially; PR19 remains IN_PROGRESS. PR20 NOT_STARTED.


## PR19 v2 hardening checkpoint

Reproduced native activity default-context bypass and missing additive high-risk
Sales authority. Both corrected, with4 focused actual regression tests PASS.
Native create/write target forms now guarded before side effects; unrelated
activities retain standard lifecycle. Critical/high authorities both accumulate.
Versionv2 invalidates v1 source packages. Final116-file source frozen:
1da64b4b50e82db5e8e1355d83435b854d166130d134705bb1c827eb1464d77e.
Static829 PASS, including exact pre-hardening116-file archive/AST constraints;
old assertions preserved. Hardened activity-guard/native safety probe PASS2.
Final fresh/update/upgrade/preservation/races/performance still running. Prior
source-bound PASS records remain separate; PR19 IN_PROGRESS; PR20 NOT_STARTED.


## PR19 final-source install/update/upgrade checkpoint

Frozen1da64b4b50e82db5e8e1355d83435b854d166130d134705bb1c827eb1464d77e:
fresh42, QUICK11, focused TARGETED11, actual PR18 update MILESTONE132 PASS.
Cold81-model preservation/source bytes PASS; no automatic approval requests.
Final8 races and operational22-native/27-upstream snapshots plus injected v1
contract drift PASS. Source unchanged during each gate. Activity forms guard PASS2.
Performance100/500 actual request services and explicitly seeded2000 headers/
10000 stages running. Additional serializable-token forgery probe will run afterward;
final evidence script hashes must match actual latest runs. PR19 IN_PROGRESS;
PR20 NOT_STARTED. No decisions or pricing application.


## PR19 verified handoff

Source 1da64b4b50e82db5e8e1355d83435b854d166130d134705bb1c827eb1464d77e; actual gates/counts/logs and measured workload limits in evidence/DEV-10-pr19-summary.md and TEST_REPORT.json.pr19_handoff. Old104 business/test files byte-identical; only4 integration files extended. No decisions or price application. STOP after PR19; PR20 NOT_STARTED.


## PR20 pre-development audit

PR00-19 actual PASS references and final116-file PR19 source verified before edits; exact archive evidence/pr19-source-baseline.zip. Installed20.0 Community FINAL and official stable branch verified2026-11-01; existing baseline retained. PR19 engine/immutability/scoped ACL/activity APIs inspected. Implement only decisions, quorum, delegation, validity and evidence; no operational pricing/application. PR20 IN_PROGRESS; PR21 NOT_STARTED.


## PR20 implementation checkpoint

Actual decisions, distinct actor/principal quorum, sequential stages, scoped independently authorized delegation, exact payload artifacts, validity and governed rework implemented. PR19 native JSON codec/M2M ordering compatibility preserves old signed hashes. Archived activity references and same-second delegation revocation use retained causal evidence. Static804 PASS on123 files, source03a7aced6d7733257fa17d162a040f0c64bd44d7495011a0306de73197d96526. Focused failures and corrections retained in TEST_REPORT.json. Fresh install, PR16-19 milestone/actual PR19 upgrade preservation, real races, safety and measured load remain in progress. PR20 IN_PROGRESS; PR21 NOT_STARTED.


## PR20 full fresh / deterministic clock correction

Initial actual fresh54:51 PASS,2 FAIL,1 ERROR; all three affected expiry fixtures used fixed06:00 UTC before native class-level cost records created after06:00. Source freshness correctly failed closed. Only the three new test clocks changed to native now+1day; boundary assertions and application logic retained. Focused TARGETED3 PASS: evidence/pr20-repairs-update-20261101T061305+0000_targeted.log. New123-file ledger329c8c594280e4f9a372b6f8c0452c2d02d60fbcfcfb959f722ef038b3822ae6; static804 PASS. Affected fresh selection with math/foundation running; complete new suite and old PR16-19 coverage remain scheduled for actual PR19 update. PR20 IN_PROGRESS; PR21 NOT_STARTED.


## PR20 runtime integrity checkpoint

Final ledger329c8c594280e4f9a372b6f8c0452c2d02d60fbcfcfb959f722ef038b3822ae6 unchanged. Affected fresh11 PASS, QUICK9 PASS, focused TARGETED3 PASS. Eight actual two-session races plus separate company-isolation assertion PASS9 groups (evidence/pr20-concurrency-20261101T062050Z.log); initial out-of-window synthetic delegation fixture rejection retained and corrected without changing guards. Operational22-native/27-upstream preservation PASS2 (evidence/pr20-operational-safety-20261101T062200Z.log), with exact synthetic authorization sample. Actual archived PR19 installation/seed/cold capture/update milestone/preservation now running; measured100/500/2000/10000 workload still pending. PR20 IN_PROGRESS; PR21 NOT_STARTED.


## PR20 actual upgrade and preservation checkpoint

Actual archived PR19 install/seed/cold capture then PR20 update MILESTONE182/182 PASS,0 failures/errors: evidence/pr20-upgrade_resume-update-20261101T062700+0000_milestone.log. Exact preservation88 registered models (some legitimately empty), source bytes and original PR19 pending/blocked requests/routes/evidence/activities PASS: evidence/pr20-upgrade-preservation-20261101T065828Z.log; zero automatic decisions/authorizations. Initial preservation probe incorrectly assumed nonempty scenario-event fixture; replaced by exact captured baseline cardinality, with all old-record/field assertions retained. No application code changes. Last mandatory100/500 actual approval cycles plus2000-header/10000-decision history performance run now in progress. PR20 IN_PROGRESS; PR21 NOT_STARTED.


## PR20 measured100 checkpoint (500/history still running)

Actual warm single-source prepare/submit/approve/quorum-display/strict-getter/governance-invalidate100 cycles: 774.571s, 854042 SQL; approval median2.4185s, p953.102s; 245305 approval SQL, 16800 company-policy API calls. Quorum display reads 218.2626s total. Activities disabled, one transaction, one Finance stage; no RPC/production capacity claim. Live log evidence/pr20-performance-20261101T065931Z.log. Overall performance gate remains IN_PROGRESS until500 cycles and2000-header/10000-decision history assertions complete. Source329c8c594280e4f9a372b6f8c0452c2d02d60fbcfcfb959f722ef038b3822ae6 unchanged. PR21 NOT_STARTED.


## PR20 runtime retention policy

TESTING_POLICY.md:51 prohibits database deletion. The planned prior-prompt cleanup pattern will not be executed for PR20. After verification, pg_ctl status3 will confirm stopped state; the seven exact owned runtime paths, database cluster, filestore and reproduction configuration will be retained, with evidence/pr20-runtime-disposition.json and a PostgreSQL log copy. No databases will be deleted. This changes only test-runtime disposition, not application code or verification scope. Performance500/history gate still running; PR21 NOT_STARTED.


## PR20 verified handoff

Final123-file source 329c8c594280e4f9a372b6f8c0452c2d02d60fbcfcfb959f722ef038b3822ae6; actual gates/counts, A-H references, failed-run history, measured workload limits and exact disposable authorization sample are in evidence/DEV-10-pr20-summary.md and TEST_REPORT.json.pr20_handoff. Old111 files including all old tests byte-identical; only5 integration files changed. No application implemented or executed. STOP after PR20; PR21 NOT_STARTED.


## PR21 frozen planning implementation checkpoint

Final130-file source64652ce881656f2589b033ac5f3c044ff72e63263c4d88ae11fbe3461d0f598d; static593 checks PASS. Exact preapproval operational intent, company calendar, original-currency/UoM/MOQ/date resolver, complete analytical after-state tier analysis, immutable current/superseded plans and scoped read-only UI implemented. All120 old nonintegration files/tests byte-identical. Earlier-source fresh31 and calendar-focused fresh14 PASS are retained separately, not relabelled final-source. Genuine archivedPR20 seed with decisions/delegation/revocation and cold capture PASS; final-source update milestone running. Final fresh/QUICK/TARGETED/races/no-write/performance pending. PR21 IN_PROGRESS; no operational supplier mutation; PR22 NOT_STARTED.


## PR21 actual PR20 upgrade checkpoint

Final source64652ce881656f2589b033ac5f3c044ff72e63263c4d88ae11fbe3461d0f598d: archivedPR20 install/real decisions/delegated Finance/revocation/cold capture then actualPR21 update MILESTONE123/123 PASS,0 failures/errors (evidence/pr21-upgrade-update-20261101T132217+0000_milestone.log). Exact92-model preservation including old security semantics and source bytes PASS; original approved artifact remains current; zero automatic plans (evidence/pr21-upgrade-preservation-20261101T140041Z.log). Source unchanged throughout final-code gates. A-J reference cases actually executed. Final focused fresh/QUICK/TARGETED, operational safety/concurrency/performance still pending. PR21 IN_PROGRESS; PR22 NOT_STARTED.


## PR21 integrity and scale checkpoint

Final source64652ce881656f2589b033ac5f3c044ff72e63263c4d88ae11fbe3461d0f598d: fresh16, QUICK14, focusedTARGETED3, upgradeMILESTONE123 and92-model preservation PASS. Four real races (duplicate/phantom/target/governance invalidation) plus separate company isolation PASS; initial external-edit injector lacked native create permission and was changed only to test-admin fixture actor, preserving unprivileged planner. Native create/write/unlink tripwires,22-native/27-upstream unchanged snapshots PASS. Warm synthetic matching10/100/500/2000 with10000 native references PASS;2000 matching0.4664s is not full-source planning latency. Added genuine2000-row source/import/commercial/financial/reconciliation setup551.160s; revenue450/profit240 no double counting. Genuine approved10-line subset dry-run127.281s/3229SQL, source gate once; approval setup619.818s. Genuine100/500/2000 subsets still running. Omitted commercial-validation fixture step was corrected without application changes; failed attempts retained. PR21 IN_PROGRESS until these last measurements and stopped-runtime handoff complete; PR22 NOT_STARTED.


## PR21 verified handoff

Final130-file source 64652ce881656f2589b033ac5f3c044ff72e63263c4d88ae11fbe3461d0f598d; actual gates, A-J cases, original PR20 approval/delegation preservation, concurrency, positive native no-write snapshots and measured resolver limits in evidence/DEV-11-pr21-summary.md and TEST_REPORT.json.pr21_handoff. All120 old nonintegration source files/tests unchanged. No supplier price application; runtime retained stopped. STOP after PR21; PR22 NOT_STARTED.


## PR22 application verification checkpoint

Transactional exact UPDATE/CREATE/NO_CHANGE, original-user native permissions,
optional company separation controls, versioned native-writer scope barriers,
immutable receipts, actual selector verification, explicit future closure/create,
and deferred commit-time target/authority checks are implemented. Earlier-source
QUICK9/9 PASS; TARGETED12 had11 PASS and one bad test fixture identity (corrected).
Actual operational probes verified only the exact supplierinfo addition with21
other native and27 analytical models unchanged. Fresh-cursor and separate-process
replay PASS. Ten-line deferred commit corruption rolled back all prices/receipt;
a safe fresh retry committed. Evidence retains initial Odoo20 UoM precision and
None/False normalization failures plus corrections.

A real two-actor CREATE race produced one rule/receipt and serialization retry.
The full race suite is not yet PASS: negotiated-price scenario fixtures need actual
residual procurement and the correct source actor; neither financial nor access
checks was relaxed. Review found optional approver separation referenced stale
actor/principal field names; this must be corrected and tested before verification.
Current extended control suite is running. Archived PR21 upgrade/preservation,
final-source fresh/QUICK/TARGETED/MILESTONE, full races, scale measurements and
stopped-runtime handoff remain pending. PR22 IN_PROGRESS; PR23 NOT_STARTED.


## PR22 frozen-source final gate start

Source acb4227273383db76be15d25f7970ec0e489217d2c700a8ed7e5d58e660f86c1:
443 static checks PASS;125 prior files unchanged, five legacy integration files
changed, nine new files; every prior test case remains byte-identical. Extended
controls had15/16 PASS, with the sole approver field-name error subsequently fixed
in gateway/UI/test. Final-source focused approver separation plus deliberate owner
confirmation execution2/2 PASS (pr22-separation-update-20261102T054457+0000_targeted.log).
All remaining gates are serial on the same frozen business source. The complete
race fixture is still being corrected without relaxing access/financial gates:
new demand requires refreshed Sales visibility and financially supported stock/
procurement; the deliberately unverified amendment-pending test PO is canceled
before this separate source is rebuilt. Earlier failed attempts remain in reports.
PR22 IN_PROGRESS; actual PR21 upgrade, full races, fresh/QUICK/MILESTONE, final
operational UPDATE/CREATE safety, replay, scale and runtime retention are pending.
PR23 NOT_STARTED.


## PR22 final source and native-storage correction

2026-11-02T06:55:17.170772+00:00: source771c6bd7d24b99108635ef5bc747bc17c4518f895b710f211aed356f95daa01f;
450 static checks PASS. Genuine concurrent UPDATE exposed SQL-NULL discount versus
ORM-zero comparison at actual commit. Guard corrected with numeric-only zero
normalization; relational identities remain strict and unrelated native NULL
metadata is not rewritten. Actual column query confirms discount/price/sequence
nullable, delay/MOQ NOT NULL (pr22-native-nullability.json). Regression exercises
actual deferred constraint with unchanged NULL discount. Initial incorrect delay
injection and SQL syntax attempt remain in failed-run history.

Earlier source0c212fed passed QUICK10, focused2, five real transaction races and
fresh-install10. Review then added explicit target-UoM/ancestor locks before full
financial reconstruction; no further architecture changes planned. Current final
source771c6bd7 passes QUICK10 and focused2. Six-case source-bound concurrency suite
is running, including independent target factor20->30 serialization before financial
build. Fresh attempt5, actual archived PR21 upgrade/preservation, operational exact
UPDATE/CREATE safety, cold replay, actual committed1/10/100/500/2000 scale and stopped
runtime retention remain pending. PR22 IN_PROGRESS; PR23 NOT_STARTED.

## PR22 verified handoff

Final source 771c6bd7d24b99108635ef5bc747bc17c4518f895b710f211aed356f95daa01f; exact gates/counts, A-K cases, actual PR21 preservation, committed synthetic execution, no-unrelated-write snapshots, races, scale limits and retained failures are in evidence/DEV-11-pr22-summary.md and TEST_REPORT.json.pr22_handoff. No production application. Runtime retained stopped; no databases deleted. STOP after PR22; PR23 NOT_STARTED.

## PR23 verification checkpoint

PR23 / DEV12 is IN_PROGRESS. The 139-file verified PR22 baseline was archived
before changes; nine new business files and three integration imports/manifest
changes implement read-only monitoring, incident review and analytical correction
planning. Existing business and test files otherwise remain byte-identical.
Official Odoo20 Community stable baseline and installed native selector/schema
were checked. Source 1ab4acf7eb2a945b78b734bbf1cd53e4da7c9c799c0b1b2c82d48f5d0f8a91bc
passes 834 static checks. Earlier-source genuine committed match/drift/lifecycle,
role/company security, four transaction races and an independently approved
109-to112 successor passed. Original PR22/native data and source bytes survived
actual synthetic database upgrade. Final-source gates are running; do not infer
verification from the earlier-source passes. Retained failures include empty JSON
normalization and CREATE before-null versus ORM-False history comparison, plus
corrected synthetic successor setup errors. No monitoring price writes and no
production application. PR24 remains NOT_STARTED.


## PR23 verified handoff

Final source b8f35fd9a0f67b4a8b684120c37cd473a61f6356947ad39106cdc2dfc28910ff; 835 static checks and exact source-bound gates are recorded in TEST_REPORT.json.pr23_handoff and evidence/DEV-12-pr23-summary.md. Monitoring never changes operational prices; synthetic setup and separately authorized PR22 fixture applications are distinguished. Benchmark partial coverage is explicitly retained. Both owned clusters stopped; all databases retained. STOP after PR23; PR24 NOT_STARTED.

## PR24 implementation checkpoint (2026-11-03)

The verified 148-file PR23 baseline remains archived. Five new reporting files and
four integration/menu-test changes implement the canonical retained-fact service,
seventeen adapters, explicit company/product/vendor/customer/demand/date filters,
financial grouping, restricted Sales columns, PDF/HTML and secure CSV/XLSX output.
No operational engine was refactored. Original 144 other files remain identical.
Earlier-source TARGETED passed 17 actual tests, including native PDF output. A
broader milestone executed 53 tests: 51 passed, two PDF/HTML formatter errors were
retained and corrected. That run also spans a subsequent reporting-security change
and is not final-source verification. A fresh final-source milestone is running.
Formatter-only benchmarks parsed every row at 100/500/2000/10000/50000; their source
hash and limitations are explicit. Actual PR23 upgrade, source-byte preservation,
final output inspection and remaining report acceptance are pending. PR24 remains
IN_PROGRESS; do not infer VERIFIED from syntax checks or earlier-source passes.
PR25 has not started.

## PR24 tested subset handoff

Current source dd210be29e46fa8cbd7c57103485a1eaaa051e96d2268666ced0ab03f83639f5 has 153 source files; 144 prior files remain identical.
Final-source QUICK11, seven genuine report/output groups and original-data/source-byte
preservation pass. TARGETED17 and fresh MILESTONE40 pass on their explicitly recorded
source versions; later presentation/precision changes have separate runtime evidence.
Actual PR23 upgrade preserves 100 stored models and all16 original vendor files
(114956 bytes; nonempty SHA256/native SHA1/size checks). Seven report types produced
21 validated PDF/XLSX/CSV files; original data hashes remain identical afterward.
Both owned clusters are stopped; no databases deleted. Required remaining scope is
listed in TEST_REPORT.json.pr24_handoff.remaining_acceptance and the A-J summary.
PR24 remains IN_PROGRESS. PR25 NOT_STARTED.
