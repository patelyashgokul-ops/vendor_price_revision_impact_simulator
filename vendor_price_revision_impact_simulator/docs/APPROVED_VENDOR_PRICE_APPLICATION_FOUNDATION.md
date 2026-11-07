# PR21 approved vendor application planning

PR21 DOES NOT APPLY VENDOR PRICES. PR22 is NOT_STARTED.

## Scope and authority

The service converts a PR20 immutable authorization into an immutable analytical plan. Purchase/Finance managers with exact company/source access can prepare it; Directors and Auditors have scoped read access. It grants no native supplierinfo write permission. Customer-only approvals are blocked. Commercial packages need an explicitly frozen vendor component. PR20 owns current decision chain, maker-checker, quorum, payload, policy and PR16/17/18 freshness validation; the planner calls get_current_approval(), never treats historical APPROVED as present permission.

Old PR20 artifacts remain unchanged. A legacy payload without operational rule intent is blocked for planning rather than guessing creation or historical overwrite authority. To authorize operational rule intent, a draft creator declares exact row/update-target or creation metadata through the creator-bound wizard before independent approval. The optional vendor_application_scope is then part of the existing PR20 payload fingerprint and final authorization. Submitted/approved intent cannot be edited; use governed reauthorization.

## Installed Odoo20 mapping

Native product.supplierinfo has partner_id, product_tmpl_id, optional product_id (unset means all variants), company_id (unset means shared), uom_id, min_qty, price, currency_id, date_start/date_end, discount, sequence, delay, product_code/product_name. Date endpoints are inclusive. min_qty is in seller uom_id, not necessarily product units. Native Float conversion can round MOQ/discount: the planner verifies the actual field conversion without writing. Source/target UoM factors, vendor hierarchy, exact product scope, field precision and selector implementations are frozen in the preapproval intent and checked again.

The native product selector filters dates, quantity, product, company and vendor/parent context and orders by discounted company-converted comparable price, sequence and ID. Purchase extends it with a last-confirmed-PO fallback under its own conditions. An exact matching row is therefore different from an effective selected rule. The planner samples up to20 existing-only native selection contexts (first/last approved rows), reports the existing ID/fallback limitation, and never creates virtual supplierinfo/PO records. It does not guarantee which rule a future RFQ will use.

## Frozen commercial price resolution

Vendor-revision prices come from the approved PR08 source amount/currency/UoM/MOQ/date/discount representation, not company-currency financial exposure. Negotiated scenarios use only frozen global explicit/original/fixed/percentage assumptions and their verified original unit/currency basis. INR109 never becomes an editable INR112. Live FX never substitutes for an approved USD commercial amount. Comparable UoM conversion reuses PR08 Decimal direction: INR1090/Box10 becomes INR109/Unit; MOQ10 Boxes becomes100 Units. Exact native field/float representability is checked; precision loss is blocked.

Warehouse/PO-conditional scenarios, hypothetical FX, landed adjustments, missing assumptions, unsupported tier modes, tax-inclusive operational representation and ambiguous net-scenario discount representation are conservatively blocked/unsupported. They are not inferred into vendor master values. The supported price-only representation retains the approved discount; changing a target discount also requires explicit preapproval permission. Existing delivery time, sequence and vendor code/name are preserved. Creation needs those metadata values explicitly; no defaults are invented by the resolver.

## Discovery and conflicts

A bounded batched search reads at most10000 references under the original user, exact company-or-shared, approved vendor/parent identities and approved product templates and their explicitly approved variants; template-wide references are inspected as conflicts. Other variants are excluded. No unrestricted sudo or first-record target selection is used. Only exact variant/company/vendor/currency/UoM/MOQ/date identities qualify for updates. Shared or template-wide overlapping records block ordinary variant/company plans. Parent vendors are conflicts, not substitutes. Duplicate exact matches, duplicate approved target identities, unsafe overlaps, currency/UoM competition and changed targets are blocking findings. Lower MOQ tiers remain separate; a cheaper competing eligible rule cannot be ignored. Competition is evaluated against the complete analytical after-state, replacing all eligible updates together and including planned creations. Blocked changes never hide current competitors. Explicit package vendor intent selects only its frozen source rows. No virtual native records or after-state winner IDs are fabricated.

An update must match the exact approved target ID and its captured material before-state. Only price and explicitly approved discount can change. Historical/open-start periods are not overwritten; a dated new rule requires explicit creation intent and safe nonoverlap/selection analysis. Source date-boundary changes are never silently added to an old row. A target edited from100 to105 is displayed as105, while the old100 preview remains immutable; stale approval/target findings block readiness. A deleted target is an integer historical reference in JSON, not a supplierinfo FK that would prevent normal operational deletion.

The approval freezes an explicit IANA company calendar (or requires the existing official company timezone). A caller timezone cannot move the historical-period boundary. Changed company timezone settings, a date rollover during planning, or expiry at the exact end boundary block readiness.

## Plans, currentness and idempotency

Models application.plan, .line and .issue inherit the existing immutable review guard. They store exact approved row references, observed targets, after-values, changed/unchanged fields, classifications, issues, source/target/schema hashes and current-authority expiry reference. No APPLIED state, execution timestamp or execution transaction is created.

The stored historical_readiness records the original analytical result. Current readiness and get_current_application_plan() independently rebuild the current evidence; any source, target, schema, policy, approval/time or date-context change prevents using old readiness. Unchanged repeated dry-runs return the same latest version without duplicate issues. Changed results append a linked immutable version.

Planning serializes its own APP06 approval/planning identity with a no-op ID epoch, allowing Odoo Repeatable Read conflicts to retry in a fresh transaction; business approval values and write_date remain unchanged. New discovery never locks supplierinfo rows. Existing mandatory PR20 financial source validation may retain its existing baseline read/share locks; this is not a new target write lock. Target previews describe a coherent transaction snapshot. A later commit can make them stale: no stored plan is indefinite execution authority. PR22 must re-read under its execution actor and lock exact targets/handle creation phantoms immediately before writes.

## Security, UI and documents

Plan/line/issue records have selected-company and all-source-warehouse/native-order access predicates. Public ORM creation, edits, deletion and copies are denied; only authenticated actions create evidence. Sales-only, portal/public and foreign-company users cannot read/export amounts. Auditors cannot prepare/revalidate. Source drill-down uses native access checks. Planning snapshots do not support extra attachments; attempted attachment creation or reassignment is denied, and the existing protected-source content/stream/export guard recognizes planning models using metadata-only identification with original-user authorization.

Navigation is nested under existing management approvals, with read-only plans/conflicts, source approval links, before/after evidence and explicit PLANNED ONLY banners. There is no Apply Prices button.

## PR22 handoff

Use the exact latest valid plan, request/version/company and immutable authorization/payload; current approval validity, source and target hashes and all line conflicts must be rechecked. Reconcile approved source currency/UoM/MOQ/date semantics and explicit allowlists. Execution needs separately authorized operator rights, target/creation concurrency controls, idempotency keys, all-or-nothing transactions, fresh retry handling, post-write exact verification and immutable before/after audit. Customer/vendor consent and PO amendments remain separate. No unapproved line, shared-company expansion or unrelated field may be written.

## Verification

PR21 VERIFIED for the documented read-only scope. Actual source-bound gates, A-J examples, failure history, genuinely approved10/100/500/2000-tier planning, separate10000-reference matching measurements and workload limits are recorded in TEST_REPORT.json.pr21_handoff and evidence/DEV-11-pr21-summary.md. Browser UAT/FULL NOT_RUN; production and cold/parallel RPC capacity NOT_MEASURED. Runtime retained stopped; no database deletion. PR22 NOT_STARTED.
