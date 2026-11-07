# PR12 / DEV06 — Purchase commitment commercial foundation

## A — Environment

Odoo20.0 Community FINAL, Python3.14.6 and PostgreSQL18.4. Addon:
`vendor_price_revision_impact_simulator`; existing base/product/purchase_stock/
sale_stock dependencies and repository major preserved. Local native source audit
retains12 hashes and actual fields/state/tax/billing contracts. PR00–PR11 evidence
was inspected; exact72-file PR11 source matched its verified ledger before changes
and was archived with a checksum. No existing user database or production data was
used. Loopback55443 disposable databases, exact runner allowlists, isolated filestores
and disabled external/email/cron/payment/live-accounting effects govern testing.

## B — Implementation

Immutable purchase snapshot/line/issue and reference-only supplier evidence models
capture exact RFQ/PO line identity, actual recorded source prices, discounts, taxes,
currency/UoM, confirmation/arrival dates and supplier references. Draft/sent/to-approve
remain conditional; purchase is confirmed, locked is a Boolean, cancelled excluded.
Core Purchase supplier-offer validity is unavailable, never invented.

Current PR09 supply buckets govern open/received/cancelled quantities, backorders,
returns and supplier receipt boundaries. PR12 does not rebuild that engine or infer
receipt from bills. Optional current PR10 exact single-scenario ledger links preserve
allocated and remaining open quantities without creating another supply allocation.
Unknown quantity is blank, not zero. Fully received/short-closed verified zero is
distinct. Supplier route/ownership uncertainty remains in PR09/PR10 evidence.

Native Odoo purchase tax base-lines plus Decimal discount input provide tax-excluded
goods references; PR08 validates UoM pairs. Source/company currencies and traceable
guarded FX are separate. Missing rates never become1:1. Original ordered quantity,
exact variant and effective interval select the current PR08 proposal tier; no
cross-order pooling occurs. Existing PO price is not replaced with supplierinfo.
Unallocated charges/services/negative adjustment lines block invented product values.

Confirmed open commercial values, conditional RFQ values and conditional proposal/
amendment differences remain distinctly labeled. Mixed currency totals are separated;
incomplete totals are null with known subtotal/count. A documented request120 and
general proposal115 remain separate scenarios. No disputed difference is accepted
payable, posted expense, realized loss or final financial exposure.

Maker-checker supplier evidence binds exact current commercial terms, reference,
reason, classification, reviewer and effective date basis/interval. Confirmation
alone is not fixed-price evidence. Latest unknown/stale evidence never revives older
favorable protection. Pending requests do not overwrite valid fixed rights. An
accepted-recorded assessment must match current PO price; it does not execute an
amendment. Existing compatible PR09 firm attestations are reused with provenance.

Optional linked bill/credit evidence uses native Accounting read permissions with
no sudo. Exact bill and bill-line record rules also restrict stored snapshots.
Comparable differences are read-only evidence; credit notes do not amend POs and
billed quantities do not substitute for physical receipt. Source/version/policy/
assessment changes make snapshots stale; unchanged inputs are idempotent. Historical
observations remain retained without inventing an original legal price. Atomic
savepoints, company/batch serialization and shared existing-source locks protect
publication. No business method commits.

## C — Files changed

- models/purchase_commitment.py — focused analytical models, bounded source service,
  normalization, source-current getters, independent evidence reviews and wizards.
- security/purchase_commitment_security.xml — company, cost warehouse, ownership,
  billing-detail/native exact-bill access and optional customer-demand scope rules.
- views/purchase_commitment_views.xml — collection/review forms, immutable histories,
  source detail, filters and optional billing evidence; no operational repricing.
- __manifest__.py, models/__init__.py, tests/__init__.py — register PR12 feature/tests.
- tests/test_purchase_commitment.py — 66 business/security/safety/workload tests.
- tests/test_module_foundation.py — exact additive menu identities.
- tests/test_sales_exposure.py — retain exact2-review/1-current-snapshot assertions
  scoped to their own source IDs, allowing preserved PR11 upgrade history. No
  business/security assertion is relaxed.
- docs/PURCHASE_COMMITMENT_EXPOSURE.md, README.md, TESTING_SETUP.md,
  DEVELOPMENT_PROGRESS.md, TEST_REPORT.json — trust contract, scope and honest evidence.
- evidence/pr12-* and evidence/pr11-source-baseline.* — exact baseline, source audit,
  reproducible verification/probes, frozen source hashes, logs and this report.

## D — Actual fixture reference results

| Reference | Actual executed result |
|---|---|
| A |100 ordered /40 received /60 open at INR100; full10,000, received4,000, open6,000; independently protected100; proposal115 does not reprice PO|
| B |Open60 at100 =6,000; hypothetical115 =6,900; conditional disputed900, never accepted payable|
| C |Supplier baseline100, negotiated PO95, proposal115; unit difference20 and conditional40-unit difference800; no substitute PO100|
| D |Draft RFQ70 at115 =8,050 conditional; no confirmed incoming, protected delivery or automatic confirmation|
| E |Billed60, received50, ordered100; PR09 open50; draft bill115 vs PO100 mismatch15; bill remains draft and PO unchanged|

Other executed cases cover backorders, fully received/short-close, returns, Input-to-
Stock nonadditive putaway, Box10 price/quantity conversion, negative discounts,
included taxes, guarded FX and missing FX, original quantity100 tier109 with open60,
request120 versus general proposal115, immutable earlier prices and exact company/
variant/warehouse isolation. Markers remain in the final clean-install log.

## E — Commercial protection and limitations

Supplier agreement references support fixed/adjustable/unknown and pending/disputed/
already-recorded amendment assessments. A different active Purchase Manager verifies
source-current proposed evidence, with a reason and scoped authority. Retained source
and validity digests prevent stale or expired protection. No supplier acknowledgement,
contract or legal original price is fabricated. Confirmation before effective date
plus arrival after it creates review, never automatic supplier price acceptance.
Legacy PR09 firm status and PR12 review evidence remain separately traceable; PR12
does not silently rewrite supply or allocation. Future consumers must inspect both.

No optional Purchase Agreement dependency is added. Core supplier-offer expiry is
not recorded. Reference-only documents are not copied into broadly accessible
attachments; original evidence keeps its existing ACL. Landed-cost/nonrecoverable
tax attribution belongs to later cost phases. Current tax-excluded goods price is
not claimed as complete inventory acquisition or payable cost.

## F — Security

Existing roles, mandatory selected company and every warehouse cost grant protect
headers/children/evidence. Purchase preparer ownership remains restricted; managers
review authorized drafts, auditors remain read-only, and Sales/portal/configuration
do not acquire confidential supplier terms. Optional PR10 customer quantities also
require demand grants. Native source opening independently checks PO access and
current company/warehouse. No broad operational administrator group is introduced.

Billing detail requires native account.move/account.move.line model authority AND
access to every exact source bill/line under native record rules. Detail-free scopes
remain separate. Revocation hides search/read/group/export history. Input wizards
permit only source identity labels and cannot export/nest/filter into confidential
native source fields. Computed user bill-ID metadata is self-user only, with acting-UID-dependent
cache keys; another user or forged context UID cannot enumerate another reviewer
bill scope. Public create/write/copy/unlink/nested ownership/context flags
cannot forge protected or verified results. Evidence verification enforces role,
company, current terms and independent checker server-side.

Executed negative tests include genuine CompanyB combined roles, CompanyA source
read/export/review denial, company and warehouse grants, Sales/portal/employee roles,
bill-model revocation, exact native bill-record rules, aggregation, direct ORM,
forged states, nested commands, untrusted context and wizard alternate traversal.

## G — Automated evidence

| Selection | Actual result | Retained evidence |
|---|---|---|
| HELPERS_VERIFY | 11 tests PASS | evidence/pr12-helpers_verify-update-20261029T084735+0000_quick.log |
| TARGETED | 41 tests PASS | evidence/pr12-targeted-update-20261029T083931+0000_targeted.log |
| FRESH | 66 tests PASS | evidence/pr12-fresh-install-20261029T084218+0000_milestone.log |
| UPGRADE | 126 tests PASS | evidence/pr12-upgrade_verify-update-20261029T084822+0000_milestone.log |
| UPGRADE-PRESERVATION | 1 assertion groups PASS | evidence/pr12-upgrade-preservation-20261029T085340Z.log |
| CONCURRENCY | 6 assertion groups PASS | evidence/pr12-concurrency-20261029T085455Z.log |
| OPERATIONAL-SAFETY | 1 assertion groups PASS | evidence/pr12-operational-safety-20261029T085517Z.log |

The first complete upgrade attempt ran451 tests (448 PASS,3 failures); it remains
FAIL in history. Final upgrade verification selects all PR12 tests, affected PR11
protection/snapshot cases, supply/allocation integrity, commercial/revision security
and module/view loading. The final selection has its own actual count in the table;
it is not represented as a451-test PASS. No unchanged earlier financial regression
is silently discarded.

All final gates match frozen76-file source **cda4df218cf1769f14aebcffb2e5d85d1346527a4e285358875ce8a65235782a** and record
no source changes during execution. Earlier draft ISO/Odoo datetime adapter and
fixture failures remain in report history. Native putaway transfers are selected
by exact company/product/Input/Stock source rather than assuming PO picking links;
native note field, role-first rejection and upstream-stale assertions are corrected
without weakening source quantities or permissions. Upgrade tests retain actual
PR11 history, so previous sales global-empty-table assumptions were corrected to
assert exactly2 reviews/1 current snapshot for the same source line/allocation.
Metadata impersonation is explicitly denied; no unrelated Accounting permission
is granted to return an empty relation. Maker-checker testing includes
a manager attempting to verify their own evidence. No passing assertion was removed. A final native user-model review also closed
a metadata impersonation path by making operational bill scope self-user-only.
Detail-free snapshots avoid empty native bill relation writes, which otherwise
incorrectly require Accounting ACLs.

The100-line workload measured **1.158s** for scoped refresh/collection after
fixture preparation; conditional value10,000 reconciles. Larger500/2000/10000-source
and peak memory: NOT_MEASURED. Manual browser UAT: NOT_RUN. Views/ACL/actions/models
loaded in actual installation/update. Future PR13/14 financial tests: NOT_RUN and
outside PR12 scope. Static/source/UTF8/cleanup validation is retained separately.

## H — Business safety

The dedicated safety probe starts with confirmed SO/PO, physical package stock50,
reserved3/free47, mixed-unit delivery demand3, valued done stock move3500 and a posted
balanced entry. PR12 repeated collection/current getters and supplier request
assessment preserve all original values/IDs/write dates/counts across **20
operational/master/mail/cron/package models**. No PO/SO price/quantity/state change,
supplierinfo/product cost write, receipt/reservation mutation, bill posting/payment,
stock valuation change or accounting entry occurs from analytical actions.
Odoo20 stock.move.value is the native valuation source; absent stock.valuation.layer
is not falsely claimed tested. No final exposure/margin/repricing/application or
operational amendment-approval engine is implemented.

Actual PR11 update preserves source attachment bytes, corrections/mappings,
commercial/supply/allocation snapshots and customer sales snapshots/reviews, policies
and existing operational records. Ordinary update creates no purchase snapshots.
The cold baseline was captured before PR12 schema registration. Disposable runtime
resources were removed after confirmed shutdown; retained logs remain.

## I — Progress

PR12 is VERIFIED; TEST_REPORT.json and DEVELOPMENT_PROGRESS.md retain actual evidence.
M2 remains IN_PROGRESS for inventory cost work. Source/evidence/history bounds10000
fail without partial publication; freshness filtering caps1000 histories. Native
billing scope over10000 sources fails closed. Existing-row locks do not permanently
freeze future inserts; fresh authorized transactions and serialization retry are
required. Browser UAT/larger stress/memory remain explicitly unexecuted/unmeasured.
PR13 stays NOT_STARTED. The next stage requires a separate instruction after
this PR12 handoff.

## J — PR13 handoff

Use `batch.get_current_purchase_terms(warehouse_ids, include_rfqs, allocation_id,
include_bills, fx_date, comparison_date)` in a fresh authorized transaction. Retain
snapshot/version/digest, exact vendor/company/variant/PO line, PR09 bucket and receipt
boundary IDs, quantities/source-comparison UoM, recorded/protected/proposed/request
price distinctions, currency/common FX date/rate IDs, date/tier/policy evidence and
independent quantity/value/protection/amendment/billing statuses. PR10 references
represent one scenario; protected incoming is a subset, not extra supply. Missing
cost or quantity is not zero. Pending disputes do not alter fixed rights or authorize
payable increases. Never sum independent amendment or quotation alternatives.

PR13 must independently establish inventory cost method, valuation confidence,
landed-cost assumptions, replacement-source applicability and source-level quantity/
cost reconciliation. Respect company, cost warehouse, native source/accounting,
exact-bill and customer-demand grant boundaries. PR12 references are not stock
valuation or final financial exposure. Stop after PR12; PR13 NOT_STARTED.
