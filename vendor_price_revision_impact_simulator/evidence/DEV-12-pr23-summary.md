# PR23 / DEV12 implementation, testing and handoff

Status: VERIFIED for the documented read-only functional scope. Completed 2026-11-02T16:24:48.878737+00:00.
Final source `b8f35fd9a0f67b4a8b684120c37cd473a61f6356947ad39106cdc2dfc28910ff`; 148 business files; 835 static checks.
PR24 is NOT_STARTED. No production database or production application was used.

## A — Environment

Odoo20.0 Community, retained existing repository; official [stable Community builds](https://nightly.odoo.com/) verified at development start. Python3.14.6, PostgreSQL18.4, existing Community dependencies base/product/purchase_stock/sale_stock/mail and openpyxl/lxml. Final-source dedicated loopback synthetic databases: codex_vpr_pr23_upgrade_4_20261102 (direct PR22 update, file preservation, functional/integration probes) and codex_vpr_pr23_fresh_4_20261102 (fresh installation). Earlier attempts remain retained separately. The exact archived139-file PR22 source and its retained synthetic database supplied genuine committed applications, protected operational history and original source files. Both owned clusters are stopped and all databases retained.

Supplierinfo has the15 PR22 material fields and normal write_uid/write_date; no native active field. Odoo20 returns a dictionary from its pure native supplier selector. Price uses minimum display digits rather than fixed storage rounding; UoM conversion definitions are captured separately from display labels.

## B — Implementation

Immutable source/company-scoped runs, checks, incident events and correction proposals reuse existing guards. Committed receipt/authorization/plan/line fingerprints remain the original authority, independent of current approval expiry. Exact target existence, permissions, company, vendor, variant/template, price, discount, currency, MOQ, dates, units and recorded commercial metadata are checked. Frozen unit factors/hierarchy and product eligibility scope are also compared. Missing and inaccessible targets are distinct; no similar-name substitution occurs.

Native selector comparisons retain exact quantity/date/vendor/product/company/UoM contexts and detect selection drift and duplicate expected identities. Unsupported schema/selector evidence is BLOCKED. Current configuration at a historical reference date is not a full historical reconstruction. write_uid/write_date are supplementary observations, never proof of unauthorized conduct.

Later independently approved committed PR22 events replace compatible expectations while retaining the earlier event. Incidents preserve first detection, latest observations, recurring material changes, reasons and review history. Verified closure needs clean revalidation and a fresh closure check. Repeated anomalies deduplicate; verified-closed recurrence reopens. Source-authorized owners can investigate or plan a correction; proposals never grant price authority or choose the old price automatically.

Old and current observations bind a current anomaly to the verified effective execution line, preventing duplicate active cases across superseded events. Stepwise price/boundary/price comparison is covered by an isolated comparator unit with authorization deliberately assumed valid; it is not a claim of four real approvals. The separate committed two-event successor probe exercises actual independent governance and PR22 execution.

Manual exact/selected observations and owner/company-scoped periodic revalidation are bounded. Scheduler and policy are disabled by default. Progress uses execution-line IDs and cyclic rechecks, not target write_date. No sudo in services, no business commits, no external messages or automatic activities. Overlapping monitor/review operations use nonblocking execution locks, policy progress locks, unique incident keys and versioned ORM writes.

## C — Files changed

Three existing integration files only: __manifest__.py adds security/data/views; models/__init__.py registers monitoring; tests/__init__.py registers new tests. All prior test modules and all other prior business files remain byte-identical.

New business files: models/monitor_math.py (comparisons/classification), monitor_models.py (immutable history and lifecycle), monitor_service.py (read-only source/current checks), monitor_policy.py (bounded scheduling), monitor_ui.py (secure review input/files), security/monitor_security.xml (role/company/source ACLs), data/monitor_cron.xml (inactive cron), views/monitor_views.xml (Community UI/navigation), tests/test_price_monitoring.py (precision/registration/pending-source tests). Supporting reproducible probes, drivers, ledgers and logs live under evidence/. Documentation: [POST_APPLICATION_PRICE_MONITORING.md](../docs/POST_APPLICATION_PRICE_MONITORING.md). Progress and test evidence are in DEVELOPMENT_PROGRESS.md and TEST_REPORT.json.

## D — Actual reference results

| Reference | Actual synthetic result |
|---|---|
| A | Committed109 current109 PASS; original scope is USD per Box10, declared rather than relabelled INR/Piece. |
| B |109 to112: PRICE_DRIFT, +USD3/Box10; no restoration. |
| C | A separate fully approved PR22 application commits112; original109 event retained and current112 recognized as AUTHORIZED_SUCCESSOR. |
| D | A genuine applied MOQ100 Unit rule changed to10: MOQ_DRIFT. |
| E | Genuine USD11/Unit changed to INR11/Unit: CURRENCY_DRIFT; no false numeric equivalence/FX conversion. |
| F | Native supplierinfo archiving is NOT_APPLICABLE on this schema. Archived product eligibility is separately detected; exact missing and inaccessible target cases both pass. |
| G | A real native-selected competing rule with gross115 and90% discount changes the winner; RULE_SELECTION_DRIFT and duplicate identity detected. Odoo20's default price-first selector would not choose undiscounted115 over109 merely because sequence changed. |
| H | Future approved rule before activation remains intact; no unauthorized-change claim. |
| I | Repeated scan keeps one incident per exact anomaly key; changed observations and recurrence retained. |
| J | Unestablished agreement produces EVIDENCE_REQUIRED proposal with no invented target price; fresh approval/dry-run required and no operational write. |

## E — Incidents

Deterministic scope-critical, commercial-high and metadata/unsupported-selection warning categories. Detecting manager initially owns the case; assignment requires existing active company/source authority. No arbitrary monetary threshold or realized-loss inference. Investigation, evidence requests, correction planning, revalidation, verified closure and reopening are server-controlled. Comment-only and proposal-only closure are denied. Documented-exception waiver is unsupported by the implemented policy. Test-created recurring cases remain retained in the synthetic database; their retained state is test evidence, not a production incident claim.

## F — Monitoring and measured performance

At most100 admitted lines per exact window,1–100 schedule batch size,1–168 hour configured frequency, periodic deterministic cursor reset,20-second cooperative observation budget and explicit partial state. A single native operation can exceed that budget. No notification spam is possible because this scope emits no automatic activities or emails.

Warm registry, original-user native selectors, actual committed PR22 data, tracemalloc overhead included, client SQL count only; pages rolled back after measurement. These are observations, not production/RPC throughput qualification.

| Applied lines | Actually observed | Seconds | Coverage | Client SQL |
|---|---|---|---|---|
| 10 | 10 | 3.990 | COMPLETE | 65 |
| 100 | 100 | 53.872 | COMPLETE | 355 |
| 500 | 80 | 194.115 | PARTIAL_REMAINING_NOT_RUN | 363 |
| 2000 | 7 | 192.894 | PARTIAL_REMAINING_NOT_RUN | 119 |

The10000-reference read-only indexed lookup used 2000 distinct real authorized lines repeated to10000 references, in 0.016291s. It is not10000 distinct application events or10000 full integrity checks. No synthetic successful history was forged to fill a benchmark.

## G — Security

Company and all constituent warehouse/cost/customer-order source rules apply to read/search/group/export and drill-down. Public/portal/sales-only/purchase-user access is denied; auditors read only with their independently granted source/native Sales authority and cannot review. Foreign-company ownership and source-line injection fail. Direct evidence CRUD/copy, guessed context capabilities, verified-status forgery and extra monitoring attachments fail. Services never grant native supplierinfo permissions. Cron executes only its original authenticated schedule owner in authorized company scope.

## H — Executed tests and evidence

| Gate | Passed | Level | Evidence |
|---|---|---|---|
| QUICK | 8 | QUICK | [pr23-final-quick-20261102T154126+0000_quick.log](pr23-final-quick-20261102T154126+0000_quick.log) |
| PRESERVATION | 2 | TARGETED | [pr23-final-preservation-pr23-preservation-20261102T154349Z.log](pr23-final-preservation-pr23-preservation-20261102T154349Z.log) |
| SOURCE_FILES | 2 | TARGETED | [pr23-final-source_files-pr23-filestore-20261102T154429Z.log](pr23-final-source_files-pr23-filestore-20261102T154429Z.log) |
| TARGETED | 32 | TARGETED | [pr23-final-targeted-pr23-probe-20261102T154437Z.log](pr23-final-targeted-pr23-probe-20261102T154437Z.log) |
| SECURITY | 4 | TARGETED | [pr23-final-security-pr23-security-20261102T154457Z.log](pr23-final-security-pr23-security-20261102T154457Z.log) |
| CONCURRENCY | 5 | TARGETED | [pr23-final-concurrency-pr23-concurrency-20261102T154527Z.log](pr23-final-concurrency-pr23-concurrency-20261102T154527Z.log) |
| SUCCESSOR | 3 | TARGETED | [pr23-final-successor-pr23-successor-20261102T154546Z.log](pr23-final-successor-pr23-successor-20261102T154546Z.log) |
| SUPERSEDED_DEDUP | 2 | TARGETED | [pr23-final-superseded_dedup-pr23-superseded_dedup-20261102T154731Z.log](pr23-final-superseded_dedup-pr23-superseded_dedup-20261102T154731Z.log) |
| PERFORMANCE | 5 | TARGETED | [pr23-final-performance-pr23-performance-20261102T154744Z.log](pr23-final-performance-pr23-performance-20261102T154744Z.log) |
| MILESTONE | 52 | MILESTONE | [pr23-final-milestone-20261102T155525+0000_milestone.log](pr23-final-milestone-20261102T155525+0000_milestone.log) |
| FRESH | 8 | QUICK | [pr23-final-fresh-20261102T153131+0000_quick.log](pr23-final-fresh-20261102T153131+0000_quick.log) |

Runner test names equal the AST-derived exact selection for QUICK, MILESTONE and FRESH; successful exits alone are not treated as evidence. The actual PR22 database and its original filestore were copied into a dedicated clone, captured under archived PR22 code, directly updated with final PR23 source, and checked against original stored-field/relation hashes and nonempty source bytes. Source-file verification covers all 15 original supplier files / 114871 bytes against immutable source SHA256, native SHA1 and size. 11 earlier FAIL/BLOCKED runs remain in history. Separately, 5 earlier capture/preservation subclaims are explicitly invalidated: the initial database-only clone omitted its filestore and an empty-read comparison did not prove source-byte preservation. Original files were retained;157 original physical files were copied/verified, the harness was corrected and a new direct upgrade/file gate replaced that evidence. Other corrected issues include sandbox TCP/log placement, JSON empty-list/empty-proposal representation, immutable CREATE before-null versus ORM-False comparison and synthetic successor account/warehouse/grant setup. No relevant functional failure remains unresolved. FULL release/browser UAT and10000 distinct historical applications are NOT_RUN.

Reproduce using evidence/pr23-static-check.py and evidence/pr23-verification-driver.py. Invocations and real timestamps, database identities and source/evidence hashes are retained in TEST_REPORT.json.pr23_handoff. Test runner configurations explicitly disable outgoing email, external API mutation, cron processing, real payments and live accounting.

## I — Business safety

Monitoring, incident review, cron and correction planning perform no supplierinfo create/write/unlink, restore or rollback; no PO/RFQ/SO/customer-pricelist mutation; no stock/reservation/valuation changes; no accounting postings or currency/UoM changes; no unapproved application or external messages. Operational CRUD tripwires cover these models in actual monitor/lifecycle tests. Synthetic fixture setup and the separately authorized PR22 successor application are the only intentional test operational changes and are distinct from PR23 feature execution. Production use: none.

## J — Progress and limitations

PR23 VERIFIED for documented functional scope; TEST_REPORT.json and DEVELOPMENT_PROGRESS.md updated from actual evidence. No functional blocker. Coverage and capacity limits, unavailable native archiving, no waiver/notification integration, snapshot-time interpretation and unexecuted release/browser qualification remain explicit. Runtime disposition: [pr23-runtime-disposition.json](pr23-runtime-disposition.json).

## K — PR24 handoff

Use the original approval/plan/execution audit with separate current checks, successor links, incident observations, recurrence, resolution events, correction proposals and schedule versions. Any management totals must reconcile to authorized company/source detail and distinguish clean, drift, blocked and partial coverage. Preserve currency/UoM/quantity basis and confidence; unit-price drift is not realized financial loss. Future audit exports must enforce the same access/attachment/formula boundaries and retention policy. Notification/waiver/correction governance, management analytics, compliance exports, archival policy and release-level integration require separate scope. PR24 has not been started.
