# APP06 PR21 / DEV11 — verified read-only vendor application foundation

## A — Environment

Odoo20.0 Community FINAL, Python3.14.6, PostgreSQL18.4. Existing major version retained; official stable baseline checked at development start (https://nightly.odoo.com/). Addon: vendor_price_revision_impact_simulator. Dedicated locally created allowlisted databases on loopback55452, role codex_vpr_pr21; no HTTP, cron or external operational integration. Controlled price-planning business date is2026-10-28; actual runtime/approval timestamps are recorded separately. Production planning uses the frozen company calendar and current date. Runtime retained stopped, no database deletion.

Native supplierinfo has company/variant-or-template/vendor/currency/UoM/MOQ/inclusive dates/price/discount/delay/sequence/vendor code/name. Native selector uses UoM quantity conversion, applicable dates, vendor hierarchy and discounted comparable price, then sequence/id. Odoo20 selector returns a mapping; Purchase may fall back to a last confirmed PO. Field precision and selector implementation fingerprints are checked. Financial normalized cost is never substituted for the original-currency operational price.

## B — Implementation

Immutable application.plan, .line and .issue store exact source rows, observed material target values, planned after-values, classifications, allowlisted changes, issues and source/target/authority/schema hashes. PR20 get_current_approval() remains the complete source/financial/decision gate. Explicit vendor application intent is captured before approval and frozen inside the payload; existing legacy approvals stay byte-compatible and cannot invent application authority.

Target discovery is one bounded batched original-user search for exact approved variants, vendor hierarchy conflicts and company-or-shared references. Exact identities include vendor, variant/template, company, MOQ, currency, UoM and dates. Shared/template/hierarchy broadening and ambiguity block. Metadata is preserved; only price/explicit discount may change on updates. Creation and metadata require explicit approval. Source-unit price and quantity conversion are exact and native precision checked. Company calendar is frozen; caller timezone cannot rewrite historical boundaries. Historical periods require safe new dated rules. All approved changes are evaluated together in a complete analytical after-state.

Unchanged dry-runs reuse the latest immutable version; changed evidence creates a linked version. Strict getter/current status rebuild current evidence; older versions are superseded. Expiry at completion and date rollover block. No stored READY plan is execution authority. See [docs/APPROVED_VENDOR_PRICE_APPLICATION_FOUNDATION.md](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/docs/APPROVED_VENDOR_PRICE_APPLICATION_FOUNDATION.md).

## C — Files changed

- [models/application_math.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/models/application_math.py): deterministic identity, classification, UoM conversion and effective after-state tier analysis.
- [models/application_engine.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/models/application_engine.py): approved payload resolution, bounded target discovery, conflicts and current evidence.
- [models/application_plan.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/models/application_plan.py): preapproval intent, immutable plans/currentness/projections and protected attachments.
- [models/application_ui.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/models/application_ui.py): creator-bound explicit intent wizard and read-only navigation.
- [security/application_security.xml](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/security/application_security.xml): company/source scope and role permissions.
- [views/application_views.xml](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/views/application_views.xml): read-only plan/line/issue displays and explicit declaration wizard.
- [tests/test_application_planning.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/tests/test_application_planning.py): meaningful approval/financial/security/identity/currentness/no-write regression.
- [__manifest__.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/__manifest__.py): append planning security/views.
- [models/__init__.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/models/__init__.py): append application modules.
- [tests/__init__.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/tests/__init__.py): append application tests.
- [docs/APPROVED_VENDOR_PRICE_APPLICATION_FOUNDATION.md](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/docs/APPROVED_VENDOR_PRICE_APPLICATION_FOUNDATION.md): architecture, scope, limits and future handoff.
- [TEST_REPORT.json](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/TEST_REPORT.json): genuine source-bound runtime evidence/history.
- [DEVELOPMENT_PROGRESS.md](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/DEVELOPMENT_PROGRESS.md): PR21 status and stop boundary.

All120 other prior source files, including all old test files, are byte-identical to archived PR20. Only3 old integration files extended. Seven new application source files; final130-file hash 64652ce881656f2589b033ac5f3c044ff72e63263c4d88ae11fbe3461d0f598d. Evidence drivers/probes/static ledger and reproduction logs are retained under evidence/.

## D — Controlled actual reference dry-runs

| Case | Actual asserted result |
|---|---|
| A | INR100 → frozen approved INR109, exact MOQ100: UPDATE_CANDIDATE, unchanged native row |
| B | New MOQ100 tier with lower MOQ1 preserved: CREATE_CANDIDATE, no native creation |
| C | Exact approved109 already present: NO_CHANGE |
| D | Shared company-less row: BLOCKED |
| E | Template-wide rule against variant-only approval: BLOCKED |
| F | Expired approval, including exact end boundary: BLOCKED; old snapshot retained |
| G | Approved109, current scenario112: frozen109 retained and BLOCKED;112 never planned |
| H | Target changed100 →105: current before105, conflict/BLOCKED; original100 history retained |
| I | Old100 through Oct31, new109 from Nov1: explicit creation preview preserves history |
| J | Genuine customer-repricing approval: wrong vendor authority, BLOCKED |

Each case is logged PR21_REFERENCE_A–J inside [evidence/pr21-upgrade-update-20261101T132217+0000_milestone.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr21-upgrade-update-20261101T132217+0000_milestone.log). Package integration also verifies an explicitly selected approved vendor component without changing customer prices.

## E — Conflicts

Ambiguous exact targets, duplicate approved identities, shared records, template scope, vendor hierarchy changes, wrong company/vendor/product, overlapping cheaper MOQ tiers, currency/UoM competition, changed/deleted native targets, stale source/approval/policy/schema, missing intent and unsupported precision block readiness. Warehouse/PO conditional terms, hypothetical FX/landed adjustments, tax-inclusive representation and ambiguous discounted scenario gross-price representation are unsupported. Missing evidence never becomes zero exposure or guessed eligibility.

## F — Security

Purchase/Finance managers may prepare in their authorized selected company and native source scopes. Director/Auditor roles read subject to the same source scope. Sales-only, portal/public and foreign-company read/export/group/prepare attempts are denied. Public ORM create/write/unlink/copy cannot forge plans, lines, readiness or actors. Source access and protected attachment guards remain original-user enforced; mutable plan attachments/reassignment are denied. The sole metadata-only attachment sudo is inherited-pattern identification, never price discovery.

## G — Testing

| Gate | Actual passed units | Evidence |
|---|---:|---|
| FRESH | 16 Odoo selected tests | [evidence/pr21-fresh-install-20261101T140138+0000_milestone.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr21-fresh-install-20261101T140138+0000_milestone.log) |
| HELPERS_VERIFY | 14 Odoo selected tests | [evidence/pr21-helpers_verify-update-20261101T141430+0000_quick.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr21-helpers_verify-update-20261101T141430+0000_quick.log) |
| TARGETED | 3 Odoo selected tests | [evidence/pr21-targeted-update-20261101T142155+0000_targeted.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr21-targeted-update-20261101T142155+0000_targeted.log) |
| UPGRADE | 123 Odoo selected tests | [evidence/pr21-upgrade-update-20261101T132217+0000_milestone.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr21-upgrade-update-20261101T132217+0000_milestone.log) |
| UPGRADE-PRESERVATION | 1 probe_assertion_groups | [evidence/pr21-upgrade-preservation-20261101T140041Z.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr21-upgrade-preservation-20261101T140041Z.log) |
| CONCURRENCY | 6 probe_assertion_groups | [evidence/pr21-concurrency-20261101T141136Z.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr21-concurrency-20261101T141136Z.log) |
| OPERATIONAL-SAFETY | 2 probe_assertion_groups | [evidence/pr21-operational-safety-20261101T140651Z.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr21-operational-safety-20261101T140651Z.log) |
| PERFORMANCE | 5 probe_assertion_groups | [evidence/pr21-performance-20261101T141251Z.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr21-performance-20261101T141251Z.log) |
| APPROVED-PERFORMANCE | 5 probe_assertion_groups | [evidence/pr21-approved-performance-20261101T142837Z.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr21-approved-performance-20261101T142837Z.log) |

Static 593 checks PASS: [evidence/pr21-static-checks.json](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr21-static-checks.json). Actual archived PR20 install/real approvals, delegated Finance vote and subsequent revocation, cold capture, update and exact preservation of 92 registered prior models; some models legitimately empty. Old original approval remains valid; no automatic plans. No old business fields or security grants waived. Baseline preparation records may note edits in the unrelated current PR21 working tree; the executed archived123-file PR20 source is separately hash verified and untouched.

Concurrency uses independent real database cursors for duplicate planning, future-rule phantom insertion, native target edits and governed approval invalidation, with fresh-transaction serialization retries and strict stale checks. Separate company-isolation assertions are labelled separately. New discovery introduces no native target write locks; existing PR20 financial baseline share locks remain.

Measured local performance:

| Synthetic DTO lines | Actual native references | Seconds | SQL |
|---|---:|---:|---:|
| 10 | 50 | 0.0076 | 3 |
| 100 | 500 | 0.0402 | 2 |
| 500 | 2500 | 0.1459 | 2 |
| 2000 | 10000 | 0.4664 | 2 |

Each scale workload uses one batched discovery. Actual10000 native fixture references are compared before/after. These are warm discovery/matching benchmarks, not full approved planning. The separately measured one-row dry-run from a genuine approval is {"lines": 1, "scope": "One actual approved source row; complete current-source reconciliation and immutable plan persistence", "seconds": 1.392159900000479, "source_gate_calls": 1, "sql": 1222}.

Genuine approved planning (real import, independent decisions and full dry-run persistence):

| Approved plan lines | Dry-run seconds | SQL | Source gate calls | Approval setup seconds |
|---|---:|---:|---:|---:|
| 10 | 127.281 | 3229 | 1 | 619.818 |
| 100 | 108.001 | 3317 | 1 | 543.062 |
| 500 | 111.672 | 3725 | 1 | 540.222 |
| 2000 | 148.252 | 5255 | 1 | 547.78 |

The genuine2000-row import/commercial/financial/reconciliation setup took 551.16s. Projected revenue450 and baseline/revised profit240 remain unchanged across2000 proposal tiers (no demand/cost double counting). All four independently approved subsets retain the fixed2000-row financial source; one product with distinct MOQ tiers, warm same-transaction caches. This differs from2000 distinct products and cold/parallel RPC capacity. RSS and sampled existing selectors are retained in TEST_REPORT.json. Source revalidation dominates these full planning timings; matching-only figures cannot substitute for full dry-run latency. All native22-model snapshots and native create/write/unlink tripwires passed.

Prior failed attempts retained without relabelling:
- FAIL [evidence/pr21-helpers-install-20261101T121028+0000_quick.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr21-helpers-install-20261101T121028+0000_quick.log)
- FAIL [evidence/pr21-concurrency-20261101T140849Z.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr21-concurrency-20261101T140849Z.log)
- FAIL [evidence/pr21-approved-performance-20261101T142429Z.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr21-approved-performance-20261101T142429Z.log)

Initial new numeric-string assertion and menu nesting regressions were corrected; old passing tests were preserved. The first concurrency probe used the restricted planner as its external native-change injector; native create access was correctly denied. Only that fixture injector was switched to an authorized test admin, retaining the original unprivileged application planner and all race/currentness assertions. The first genuine-scale setup omitted action_validate_commercial_prices() after context verification; the fixture was corrected to execute that real required stage, preserving all2000-row assertions. Actual failed attempts and reruns remain visible in TEST_REPORT.json history.

- Browser UAT NOT_RUN; FULL release NOT_RUN
- Production/cold/parallel RPC capacity NOT_MEASURED
- Synthetic matching benchmark runs after all10000 native references are read for the safety snapshot: warm ORM cache. It excludes source/UoM resolution, native selector sampling and plan persistence; genuine approved planning measured separately
- Actual10/100/500/2000-line plans use independently approved subsets of one genuine2000-row, single-product quantity-tier source; fixed full source gate cost retained for all subsets; warm single transaction, no RPC/cold capacity claim
- Native existing-only selector samples maximum20 contexts; no hypothetical future RFQ winner guarantee
- Performance PASS means assertion/count/no-mutation checks completed; no latency/query/RSS SLA
- Immutable previews describe a coherent transaction snapshot; future execution must revalidate and lock exact targets/creation scope

## H — Business safety

Application service created0, updated0 and deleted0 product.supplierinfo records. Actual native create/write/unlink tripwires surround dry-run/current getter/repeat/revalidation. Exact22-model native counts/values/write_dates plus27 upstream analytical models and approval business fields are preserved on positive synthetic confirmed SO/PO, valued stock receipt3500, reservations and posted journal entry fixtures. No vendor/customer pricelist application, PO/SO repricing, stock valuation or accounting posting is performed by planning. Native records are created/edited only by explicit isolated test-fixture setup and concurrent-change injectors, before analytical safety snapshots or as documented race inputs.

## I — Progress

PR21 VERIFIED for the documented read-only foundation. TEST_REPORT.json.pr21_handoff and DEVELOPMENT_PROGRESS.md contain genuine evidence and failed-run history. Runtime stopped/status3, seven owned paths retained under TESTING_POLICY.md:51. Browser UAT/FULL remain NOT_RUN; production/cold/parallel RPC capacity is NOT_MEASURED. PR22 NOT_STARTED. No operational application implemented or executed.

## J — PR22 handoff

Exact synthetic disposable sample: [evidence/pr21-plan-sample.json](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr21-plan-sample.json), request 6, authorization 5, plan 6. Full immutable evidence contains request/version, current-at-capture validity/expiry, approved payload hash, company/vendor/product identities, observed target IDs, original currency/UoM/MOQ/dates, explicit operation and metadata, before/after fields, conflicts and source/target/approval/schema hashes. The operational sample is CREATE_CANDIDATE USD11/Unit MOQ10 from approved USD110/Box10; financial INR1034 is not a native price. The probe rolled back its final planning transaction; IDs are evidence references, not usable operational authority.

PR22 must obtain separate execution authorization and the native supplierinfo permissions required for each create/write operation; this foundation adds no native pricing rights. It must revalidate latest plan/current approval, complete approved payload/source/financial reconciliation, company and original-user native scope immediately before writes. Lock exact update targets, compare all approved material before-values, serialize creation scope/phantoms, enforce exact dates/tiers/currency/UoM and field allowlists, and never substitute current unapproved prices. Use an idempotency key and transaction-wide all-or-nothing rollback; failed application is never success. Fresh retries must revalidate authority and prevent duplicate creates. Verify exact post-write native values and retain before/after, actor/principal, source supplier evidence, approvals and failure audit; corrections append history. PO/customer amendments, external consent and accounting/valuation remain separate authorized workflows. STOP after PR21; do not begin PR22.
