# PR-08 / DEV-04 commercial validation implementation and handoff

PR-08 **VERIFIED** on Odoo Community 20.0. PR-09 remains **NOT_STARTED**.

## A — Environment and prerequisite evidence

Odoo Community 20.0 final, Python 3.14.6, addon vendor_price_revision_impact_simulator.
The actual local release, UoM, supplierinfo, currency/rate and RFQ source APIs were
inspected. No repository/version migration occurred. Base/product and existing
openpyxl/lxml dependencies remain unchanged. PR00–PR07 retained results and frozen
PR07 source hashes were checked; the exact 47-source PR07 archive is retained.

Verification uses new dedicated disposable PostgreSQL 18.4 databases on loopback
55439 with exact allowlists and disabled external side effects. A separate operational
fixture database installs sale_stock,purchase_stock,stock_account. Synthetic posted
entries/orders/stock moves are test fixtures, never live accounting or business data.
Final cleanup is recorded after the test server stops.

## B — Implementation

The engine consumes current PR06 structural and PR07 variant gates. Explicit
independently verified context captures supplier UoM aliases, net tax-exclusive
basis/discount, old reference date, optional inclusive end date, FX method and
historical/scenario evidence. Ordinary context needs a different Purchase Manager;
scenario FX requires a different Finance Manager plus enabled PR04 policy. This is
interpretation verification, not commercial price approval.

Odoo20 has reference-hierarchy units and no uom.category. Compatible active UoM
ancestors/factors are checked before inverse quantity/price conversions. Decimal
calculations use 38 significant digits with explicit numeric bounds and separate
reporting rounding. Unsupported/missing/nonfinite/negative inputs never become
zero. Source/canonical values and factors remain traceable.

Currencies resolve by exact active code. Guarded company/root/shared rate lookup
mirrors verified Odoo20 strict before-date selection and target/source ratio while
refusing earliest/1/future-forecast fallbacks. Common-rate and date-specific methods
remain distinct, with actual rate-record/date references or visibly hypothetical
Finance-verified scenario quotes. No external fetch or master rate mutation occurs.

MOQs normalize to the variant base unit. Legitimate distinct tiers remain separate;
equal normalized thresholds with overlapping inclusive periods conflict. A read-only
explicit-quantity tier helper prepares later consumers without querying demand.
Vendor baseline candidates are bulk scoped to exact vendor/company/shared terms,
variant/template, compatible units, dates and eligible quantities. APP06 deliberately
prefers company and variant specificity, then standard eligible discounted price
and sequence; duplicate or unresolved economic ties require review. No ID tie,
accounting cost or recent PO becomes an invented baseline.

Historical terms require a documented independent attestation tied to captured
supplier evidence. This is an explicit verifier assertion, not automatic historical
reconstruction. Edits/inserts invalidate that attestation. Missing/unverified old
price leaves a potentially normalized proposal without a verified delta/percentage.
Tax-inclusive/unknown basis, unsupported charges and invalid discounts stay incomplete.

Immutable row snapshots/issues retain versions, previous result, actor/time, source
hash, current material source/correction basis, PR06/PR07 references, published PR04
policy, supplier rule details/candidates, UoM/FX, dates, tiers and formulas. Notes-only
corrections can reuse equivalent commercial decisions after upstream revalidation.
Getters recheck freshness; history never becomes a current result merely by existing.

Validation is atomic/idempotent. Company/batch and existing evidence locks serialize
workflow changes and master edits. Failures retain safe retry state and no partial
new result set; serialization requires a fresh transaction. Business methods never
commit. Plain UI columns distinguish company-basis and supplier-currency percentages,
FX basis and hypothetical assumptions. Human-readable explanations accompany detailed
provenance and issue/filter drill-downs; no Apply Price action exists.

## C — Actual relevant files

- models/commercial_math.py: bounded Decimal quantity/price/FX/net/rounding/delta math.
- models/commercial_engine.py: bulk scoped policy/UoM/FX/tier/baseline resolution,
  dates, conflicts, decomposition, snapshots and material fingerprints.
- models/commercial_validation.py: retained interpretation/result/issue models,
  independent verification, batch/row current interfaces, counts, guarded wizard,
  human-readable explanations and protected exports.
- security/commercial_validation_security.xml: mandatory company/active-user rules,
  own/company/confidential-reader roles and narrow published-policy reads.
- views/commercial_validation_views.xml: review, interpretation and comparison views.
- Manifest and model/test initializers: registration/description; version/deps retained.
- models/product_resolution.py: relevant integration fix includes description-only
  source identity and rejects changed row-only mapping context. Existing coded
  mappings retain their identity semantics; historical one-row description mappings
  needing renewed verification are conservatively stale, without rewriting evidence.
- tests/test_product_resolution.py: fixture supports an existing unique company policy;
  no assertions removed or weakened. Preservation verifies seed policy unchanged.
- tests/test_commercial_validation.py:47 new methods across six classes.
- tests/upgrade/seed_pr07.py, verify_pr08.py, verify_concurrent_commercial.py,
  verify_commercial_operations.py and verify_pr08_static.py: genuine upgrade,
  independent-session, operational and source/evidence audits.
- Commercial guide, README, security/testing setup, progress/report, hashes/logs/driver.

## D — Actual financial reference results

Executed controlled fixtures assert and log:

| Reference | Result |
|---|---|
| INR 1000/Box10 -> 1150/Box10 | Old 100/Piece, proposed 115/Piece, delta 15/Piece, +15% |
| USD 10 at90 -> USD 11 at94 | Old 900, proposed 1034, delta 134 |
| Explicit decomposition convention | Supplier 90 + FX 44 =134 |
| Common selected94 rate | Supplier unit delta 94, FX component 0 |
| Eligible MOQ 1/100/500 | Quantities 80/120/600 select1/100/500, matching standard Odoo20 |
| 12 Boxes of 10 requested | 120 Pieces, eligible100-unit tier |
| Missing supplier baseline | Normalized proposal may exist; old/delta/percentage absent |
| Old zero | New-from-zero/zero-to-zero; percentage undefined, no division by zero |
| 500 synthetic rows | 500 valid comparisons and 500 current results; bulk search bound asserted |

These are per-unit comparisons, not allocated business quantities, exposure, profit
or realized recovery. Actual baseline/product IDs, rate dates and reference outputs
are in retained logs and snapshots. Final clean-install workload: **5.700 seconds**, **3 bulk supplier
searches** for 500 valid rows. This is one local synthetic fixture, not a general
throughput claim. Exact executed identifier traces:

```text
PR08_REFERENCE old_per_piece=100.00 proposed_per_piece=115 delta=15.00 percent=15.00 baseline_id=1 product_id=2
PR08_FX_REFERENCE old=900 proposed=1034 total=134 supplier=90 fx=44 method=supplier_at_old_rate_then_fx_on_proposed_price
PR08_TIER_REFERENCE quantities=80,120,600 selected_thresholds=1,100,500; boxes12=pieces120
```

## E — Security

Mandatory company/active-user rules intersect all new roles. Own-draft preparers
and company managers validate; confidential roles read without automatic mutation
rights. A shared product does not broaden supplier cost scope. Direct read/export/
grouped/RPC/ORM, role unions, multi-company context, wizard defaults/nested aliases,
state/company/result forgery, self-verification and protected lifecycle calls are
negatively tested. Public history mutation/copy/delete is denied.

Published PR04 definitions become readable to preparers/confidential readers for
correct current computation; draft read/write and policy/threshold mutation remain
restricted. Supplier/FX price retrieval is not elevated. Stored baseline IDs plus
immutable evidence avoid live related-price traversal. Current moved-product labels
and nested exports remain protected; original authorized evidence remains. Source
attachments/download guards, standard export privilege and formula-prefix output
escaping are preserved. Standard supplierinfo access outside APP06 is not rewritten.

## F — Automated tests and evidence

| Scope | Actual final result | Evidence |
|---|---|---|
| QUICK final helpers / operational addon update | PASS (5 tests) | [pr08-operations_verify-update-20261028T163855+0000_quick.log](pr08-operations_verify-update-20261028T163855+0000_quick.log) |
| QUICK final clean installation | PASS (195 tests) | [pr08-fresh-install-20261028T163222+0000_quick.log](pr08-fresh-install-20261028T163222+0000_quick.log) |
| TARGETED commercial + PR04/PR05/PR06/PR07 regression | PASS (113 tests) | [pr08-targeted-update-20261028T164226+0000_targeted.log](pr08-targeted-update-20261028T164226+0000_targeted.log) |
| MILESTONE actual PR07 update | PASS (195 tests) | [pr08-upgrade_verify-update-20261028T164441+0000_milestone.log](pr08-upgrade_verify-update-20261028T164441+0000_milestone.log) |
| TARGETED real-session concurrency | PASS (9 probes) | [pr08-concurrency-20261028T164004Z.log](pr08-concurrency-20261028T164004Z.log) |
| TARGETED existing operational safety | PASS (1 assertion probe) | [pr08-operational-safety-20261028T163944Z.log](pr08-operational-safety-20261028T163944Z.log) |
| QUICK static/source/cleanup | PASS (106 checks) | [DEV-04-pr08-static-validation.txt](DEV-04-pr08-static-validation.txt) |
| Actual PR07 preservation | PASS (assertion probe; no fabricated count) | [pr08-upgrade_verify-preservation-20261028T164725Z.log](pr08-upgrade_verify-preservation-20261028T164725Z.log) |

All final Odoo summaries are nonempty with zero failures/errors. The 58-source
[final ledger](pr08-verified-source-sha256.json),
[exact local driver](pr08-verification-driver.py) and
[static audit](DEV-04-pr08-static-validation.txt) bind evidence to actual source.
Targeted/update/probes use per-run hashes; the fresh test log proves all final
runtime/test files predate addon import at 2026-10-28 16:33:19.176 UTC.
Earlier failures remain
in TEST_REPORT.json: empty required JSON evidence, overlapping published-policy
fixture setup, an intended-decrease fixture that was still an increase, existing
company-policy fixture setup, and JSON tuple/list representation in preservation.
The related fixes do not remove or weaken passing tests. Any candidate spanning a
source edit is distinguished from final source-qualified evidence.

## G — Business safety

The dedicated operational probe creates actual confirmed SO/PO, a completed valued
stock move with value 3,500 and positive quants, and a posted balanced journal entry
before comparison. It snapshots 15 models including master prices, documents/lines,
quantities/reservations, stock.move.value, accounting lines, rates and notifications.
Repeated comparison must leave exact values, IDs, write dates and counts unchanged.
Odoo20 in this source stores valuation on stock.move; stock.valuation.layer is absent
and is not falsely claimed as tested. Basic fixture regressions separately preserve
source bytes/hash/cells, product costs/prices/UoM, supplier terms and revision state.

No supplier rule is applied/created/deleted by the engine. No SO/PO repricing,
stock valuation recalculation, accounting entry, approval event, application cron,
financial exposure total, margin calculation or supply allocation is implemented.
Fixture preparation is explicitly separate from tested validation side effects.

## H — Progress and limits

PR08 is VERIFIED. TEST_REPORT.json and DEVELOPMENT_PROGRESS.md record actual final
evidence. Disposable cluster/databases/filestores/configs/baseline checkout were
removed after clean shutdown; the database log is retained. M1 is passed for the
implemented intake/product/commercial foundation. PR09 remains NOT_STARTED. Missing data remains incomplete, never zero exposure. Other known
limits: manual browser UAT not run; only the intentional 500-row commercial workload
is measured, not10/100/2000/10000 benchmarks or peak memory. No claim of general
throughput follows from supported bounded file sizes. Evidence caps and upstream
PR07 candidate bounds are documented. Existing row locks cannot prevent phantom
master inserts; a fresh transaction detects them. Historical attestation is a human
assertion tied to observed terms, not an imported ledger reconstruction. Unsupported
tax-inclusive/charge calculations stay review-required. Publisher/license release
decisions remain as previously recorded.

## I — PR-09 / PR-14 handoff and strict stop

Call get_commercially_valid_rows() immediately before consumption and use actual
resolved variants, exact company/vendor, normalized comparison UoM, old/proposed
company/source prices, quantity thresholds, FX method/dates/records/hypothetical
flag, effective/as-of dates, unit delta/percentage and snapshot/version/digest.
Retain current PR06/PR07 references alongside immutable comparison evidence, source
hash/positions and corrections. Exclude stale/unverified/ambiguous/missing-baseline
rows explicitly. Future quantity/date consumers use resolve_vendor_tier with actual
context; never apply a high-quantity tier to a smaller requirement.

Future supply allocation must reconcile demand/supply separately, preserve company
and cost confidentiality, recheck snapshot freshness and independently enforce
approval/application gates. Unit-price change is not total exposure or realized
benefit. No stock/order allocation, margin/risk/approval/application engine follows
automatically. STOP after PR08; PR09 remains NOT_STARTED.
