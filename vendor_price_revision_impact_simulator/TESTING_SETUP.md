# Testing Setup



## Discovered environment



- Project root: `C:\PycharmProjects\odoo20\custom_addons\vendor_price_revision_impact_simulator`.

- This directory had no files, module manifest, tests, test runner, CI configuration, or Git metadata at DEV-00 inspection.

- A separate sibling custom addon directory named `supplier_shortage_claim_reconciliation` exists under the shared `custom_addons` parent; it is outside this project scope and was not changed. DEV-01 provides the APP 06 module foundation only.

- A sibling Community source tree exists at `C:\PycharmProjects\odoo20\odoo-20.0`; its `odoo/release.py` declares version 20.0 final. The Odoo executable is `C:\PycharmProjects\odoo20\odoo-20.0\odoo-bin` and the local virtualenv Python is `C:\PycharmProjects\odoo20\.venv\Scripts\python.exe` (Python 3.14.6).

- Importing the local Odoo package succeeded as version 20.0. Its release module specifies Python 3.12–3.14 support, which includes the detected interpreter. This verifies import-time dependencies only, not database connectivity or every optional dependency.

- The existing Odoo config is `C:\PycharmProjects\odoo20\odoo-20.0\odoo.conf`; its addon paths include the Odoo core `addons` directory and `C:\PycharmProjects\odoo20\custom_addons`. It does not identify a dedicated APP 06 test database.

- Odoo Community 20 is the latest stable major at this development start (the [official release notes](https://www.odoo.com/page/release-notes) and [nightly builds](https://nightly.odoo.com/) say released September 2026). Existing version policy: do not upgrade repositories automatically.

- Odoo source and a Python environment are present. PR-01 fresh install/update and PR-02 fresh install/targeted update passed against dedicated disposable databases on an isolated PostgreSQL 18.4 loopback cluster. Those clusters and temporary data were removed after verification. PostgreSQL `pg_isready` is not on PATH; the runner supports the verified executable path in `postgres.pg_isready`. APP 06 now includes revision/security, company policy definitions, secure source intake, structural/product resolution and commercial validation. Financial exposure, approval execution and application remain deferred.

- The project folder itself is not a Git checkout. Inspection of the parent source tree's Git state was denied by the environment; no claim is made about that working tree.

- Host is Windows; runner uses the Python standard library and argument arrays, and supports Windows and POSIX paths.



## First-time setup



1. Create a private local JSON config using `scripts/test-runner.example.json` as a schema example. Set the active prompt ID/phase, absolute paths, actual module name, installed-vs-new action, Odoo config, and test tags that exist in the target module. Keep the local config outside version control; it may refer to credentials in a protected Odoo config file, but must not embed passwords.

2. Provision or select a dedicated disposable test database. Confirm its role independently, set `database_role` to `dedicated_test`, and list the exact name in `allowed_test_databases`. Explicitly set every `side_effects` control to `false`. The name alone is not a safety check.

3. Install PostgreSQL client utilities and ensure `pg_isready` can reach the configured server and database. Put it on `PATH` or set its verified absolute path in `postgres.pg_isready`. Use a test-only Odoo config with isolated mail, external API, payment, accounting, and cron settings.

4. Ensure the module is discoverable on Odoo's addons path, has a manifest, and contains tests.

5. Run `python scripts/run_tests.py --help`, then `python scripts/run_tests.py --mode quick --config <LOCAL_CONFIG>`.



The runner does not create, clone, or delete databases. It checks `pg_isready` before Odoo invocation. It requires a test result summary with at least one executed test; otherwise it records NO_TESTS/BLOCKED/FAIL as appropriate. PR-01 evidence is recorded in `evidence/DEV-01-install-update.txt`; PR-02 implementation and install/update evidence is in `evidence/DEV-01-pr02-summary.txt` and the `odoo-pr02-*.log` files. No persistent PR-01/PR-02 test database remains.



## Odoo 20 command templates



Use these only after replacing every placeholder with verified local values, checking that the module is on the addons path and that the database is dedicated and allowlisted. Odoo 20 test tags imply test enablement.



Initial install:



```powershell

& '<PYTHON>' '<ODOO_BIN>' -c '<ODOO_CONF>' -d '<DEDICATED_TEST_DB>' -i '<MODULE>' --test-tags '<VERIFIED_TAGS>' --stop-after-init --log-level=test

```



Installed-module update:



```powershell

& '<PYTHON>' '<ODOO_BIN>' -c '<ODOO_CONF>' -d '<DEDICATED_TEST_DB>' -u '<MODULE>' --test-tags '<VERIFIED_TAGS>' --stop-after-init --log-level=test

```



Example tag shapes (only use when the class/method really exists): `/<MODULE>`, `/<MODULE>:<TEST_CLASS>`, `/<MODULE>:<TEST_CLASS>.<TEST_METHOD>`. Do not infer installation state or copy a database/module name from an example. Review `TEST_REPORT.json` after each run.



## PR-03 security verification



PR-03 used newly created UTF-8 databases on a separate loopback PostgreSQL 18.4 cluster. A final clean installation ran all module tests. A focused TARGETED selection ran `/vendor_price_revision_impact_simulator:TestRevisionSecurity`. An actual PR-02 package from `evidence/pr02-source-baseline.zip` was installed and seeded via `tests/upgrade/seed_pr02.py`, then the current addon was updated with a MILESTONE module selection and checked with `tests/upgrade/verify_pr03.py`. The original source archive has a SHA-256 file alongside it. The runner did not create or delete these databases; the surrounding disposable verification setup did. All temporary database clusters, filestores, and local configs were removed after clean shutdown. The evidence directory retains the executed logs and driver source for reproducibility.





## PR-04 configuration verification



PR-04 retains the exact pre-change source in `evidence/pr03-source-baseline.zip`.

Every archived source entry covered by the PR-03 verified-source hash ledger was

checked for an exact hash match. Dedicated test databases use a newly initialized

PostgreSQL 18.4 cluster bound only to 127.0.0.1:55435; no existing database is used.

The runner still requires exact allowlists and disabled external side effects.



Focused selector: `/vendor_price_revision_impact_simulator:TestCompanyConfiguration,

/vendor_price_revision_impact_simulator:TestRevisionSecurity` (one string without

the displayed line break). Fresh installation and actual PR-03 upgrade use the

whole addon selector. Upgrade probes are `tests/upgrade/seed_pr03.py` and

`tests/upgrade/verify_pr04.py`. The seed checks that least privilege already exists

in PR-03; the verification asserts retained references, values, ownership, write

dates, supplier price, group memberships, company restrictions and single menu/

sequence identities after upgrade. Final results are in TEST_REPORT.json.





## PR-05 intake verification



The exact PR-04 source is preserved in `evidence/pr04-source-baseline.zip` with

SHA-256 metadata. Tests use new dedicated databases in a disposable PostgreSQL

18.4 cluster on 127.0.0.1:55436, exact runner allowlists and disabled external side

effects. New classes are TestImportParser, TestImportIntake, TestImportSecurity

and TestImportDownload. Focused selection also includes TestRevisionSecurity.

Fresh installation explicitly selects all eight addon classes. Actual PR-04

upgrade installs the archive, seeds revisions/lines/manual evidence/supplier price

and a future published policy, updates current source, then verifies preserved

values, identities, write dates, roles and audit history. Probes are

`tests/upgrade/seed_pr04.py` and `tests/upgrade/verify_pr05.py`.



`tests/upgrade/verify_concurrent_intake.py` runs through Odoo shell only on these

disposable databases. It commits synthetic fixtures so two independent sessions

can race extraction and cancellation. Business intake methods never commit.

The probes check serialization retry, idempotency and no duplicate rows/attempts.

HTTP tests use HttpCase for standard content requests. No supplier messages or

external requests are sent. Actual results and workload timing are retained in

TEST_REPORT.json and evidence logs.





## PR-06 structural review verification



The pre-change source is retained as `evidence/pr05-source-baseline.zip`; all

entries match the PR-05 verified-source hash ledger. New tests cover structural

helpers, mapping, validation, corrections and validation security. The focused

selection also runs PR-05 attachment/download security. Fresh-install selection

explicitly includes all addon classes. A dedicated disposable PostgreSQL 18.4

cluster is bound only to 127.0.0.1:55437, with exact database allowlists and isolated

side effects. No existing database is used.



Actual PR-05 update verification installs the archive, seeds existing revisions,

manual evidence, a published policy and an extracted source batch, updates the

current addon and verifies original bytes/hashes/raw rows/write dates and security.

Scripts: `tests/upgrade/seed_pr05.py`, `tests/upgrade/verify_pr06.py`.

`verify_concurrent_validation.py` commits only synthetic disposable fixtures and

uses two independent sessions to race validation with validation, mapping edits,

corrections and cancellation. Business actions never commit intermediate states.

Final results and measurements are retained in TEST_REPORT.json and evidence.





## PR-07 identity verification



Use four new classes TestProductExactMatching, TestVendorProductRegistry,

TestProductResolutionFreshness and TestProductResolutionSecurity. Focused selection

also runs TestImportValidationSecurity, TestImportSecurity and TestImportDownload.

Actual PR06 upgrade uses evidence/pr06-source-baseline.zip, seed_pr06.py and

verify_pr07.py. The seed retains original bytes, mappings, two corrections and three

validation runs. verify_concurrent_products.py uses independent sessions with only

committed synthetic disposable fixtures. Port 55438 is loopback only; exact database

allowlists and external-side-effect disables are mandatory. The 500-row synthetic

identity workload is timed and guards bulk product search count; other benchmark

sizes and peak memory are NOT_MEASURED. Operational document fixtures and browser

UAT remain NOT_RUN. Business workflow methods never commit.





## PR-08 commercial verification



Six new classes cover Decimal math, normalization, FX, vendor baseline/tier/date

selection, snapshots and security. QUICK helper selection is TestCommercialMath;

TARGETED adds all commercial classes, TestCompanyConfiguration, PR07 identity

classes and PR06/PR05 validation/source/download security. Fresh/install milestone

explicitly selects all addon classes. Actual PR07 upgrade installs the frozen

47-source baseline, seeds PR06 corrections and PR07 verified identity evidence,

updates the addon and verifies exact retained source/policy/mapping identities.



Disposable PostgreSQL 18.4 listens on127.0.0.1:55439 only, with exact runner allowlists

and disabled side effects. Tests/upgrade/verify_concurrent_commercial.py commits

synthetic fixtures for nine real-session races. An additional dedicated database

installs sale_stock,purchase_stock,stock_account and runs

verify_commercial_operations.py against confirmed SO/PO, quants, a valued done

stock move and a posted entry. Odoo20 valuation is stock.move.value here; no

stock.valuation.layer model exists. Fixture preparation creates these records;

comparison itself must preserve every snapshot and count. No real messages,

payments or external mutations are authorized. Final evidence/report records actual

results; manual browser UAT and larger workloads/peak memory are not implied.





## PR-09 supply verification



`evidence/pr09-verification-driver.py` uses a newly initialized PostgreSQL18.4

cluster on loopback port55440, an exact allowlisted database per run, isolated

filestores and disabled outgoing/cron/payment/API/accounting side effects. Its

`fresh`, `supply`, `targeted`, `concurrency`, `upgrade` and `operations` phases

retain runner evidence. Local `.pr09_*` configs contain disposable runtime state

and are removed after verification; no existing database is selected. The driver

starts/stops its own cluster and must not be run concurrently with itself.



The upgrade phase installs the exact `evidence/pr08-source-baseline.zip`, seeds

real preserved commercial/identity/correction/source/policy evidence in a separate

fixture company, updates PR09, runs the addon milestone tests and checks retained

values/IDs/bytes and zero automatic supply snapshots. Eight independent-session

probes cover collection, reservation, receipt, cancellation, price, UoM, relocation

and grant revocation. The upgrade fixture installs purchase_stock/sale_stock while PR08 code is active,

then preserves existing confirmed SO/PO, reservations, valued stock and a posted

entry through update. After preservation it runs the operational safety probe

around supply analysis/terms review. The optional operations phase offers the

same probe in a separate database. Sales integration remains test-only.



Supply tests are in `tests/test_supply_foundation.py`; they are business integrity

tests, not a measured 100/500/2,000-product or 10,000-source load benchmark. Report

manual browser UAT and unexecuted workloads explicitly. The frozen source ledger

and per-run digest identify exactly which code a PASS applies to.





## PR-10 demand/allocation verification



`evidence/pr10-verification-driver.py` creates its own PostgreSQL18.4 cluster on

127.0.0.1:55441, explicitly allowlisted disposable databases and isolated filestores.

External side effects and cron remain disabled through the DEV00 runner. The

`helpers`, `allocation`, `targeted`, `fresh`, `upgrade`, `upgrade_verify` and

`concurrency` phases retain source-qualified logs. Never run two driver phases

concurrently; each starts and stops the same dedicated cluster.



The PR09 baseline is the exact retained62-source archive. Its upgrade fixture

installs standard sale_stock while PR09 code is active, preserves source bytes,

corrections, identity/commercial evidence, policies and actual PR09 supply snapshots,

as well as confirmed SO/PO, reservations, valued stock and a posted entry. A second

PR09 process captures committed stored values from a cold registry before the

PR10 allocation table exists, avoiding stale preparation-transaction log-access

caches. The post-update comparison still checks every stored field, including

write UID/date; no metadata field is ignored or restored. PR10

update must not create allocations or automatically enable customer-demand grants.

Operational safety compares all source/master/mail/cron/package records around

allocation; concurrency uses independent real sessions and only synthetic fixtures.



Run the seven core classes in `tests/test_demand_allocation.py` for focused PR10

cases; the eighth class measures the 100-order workload on install/milestone runs.

escalate to PR09/commercial/source-security regressions and a fresh/actual-upgrade

milestone. Late and unknown ETA, unresolved lineage and conditional alternatives

must not become definite coverage. No PR14 monetary engine tests are claimed.

Record browser UAT and the remaining500-order/2000-line/10000-source/peak-memory

workload matrix as NOT_RUN/NOT_MEASURED unless actually executed.


## PR11 sales commercial verification

`evidence/pr11-verification-driver.py` uses a new PostgreSQL18.4 cluster on
127.0.0.1:55442, exact disposable database allowlists, isolated filestores, disabled
cron/email/external/payment/live-accounting effects and the DEV00 runner. Do not
run phases concurrently. `helpers_verify` selects discount/tax checks, `allocation`
selects all PR11 classes, `targeted` selects the final changed customer-security boundary; `fresh` installs
the PR11 classes, and the actual-upgrade milestone selects the complete addon
regression including PR10, source security and supply security. An earlier broad
167-test targeted run is retained separately from final source-qualified gates. `upgrade` installs the exact
68-file PR10 archive, seeds real supply/allocation and operational history, captures
committed evidence from a separate cold PR10 process before any sales table exists,
then updates and runs the module milestone and preservation probe. No existing
user database is selected. Runtime `.pr11_*` resources are removed after shutdown.

Eight new classes in tests/test_sales_exposure.py cover native SO/quote identity,
discount/tax semantics, authoritative partial quantities, source UoM, sales FX,
protection assessments, immutable history/freshness and direct ORM confidentiality.
Dedicated probes test independent-session commercial collection/source races and
preserve actual posted/valued/confirmed/reserved records around PR11 analysis.
The 100-line workload records timing only after upstream preparation. Larger
500/2000/10000-demand tests and peak memory remain NOT_MEASURED unless actually
executed. Manual browser UAT remains NOT_RUN unless recorded separately.


## PR12 purchase commitment verification

`evidence/pr12-verification-driver.py` owns a disposable PostgreSQL18.4 cluster on
127.0.0.1:55443 and private `.pr12_*` runtime files. Each phase starts/stops the same
cluster; never run phases concurrently. Exact database allowlists and disabled
external/email/cron/payment/live-accounting effects remain mandatory. No existing
user database is selected. The runner records actual nonzero test summaries.

Eight PR12 classes in tests/test_purchase_commitment.py cover recorded PO terms,
RFQ separation, receipt/backorder/return boundaries, independent maker-checker
assessments, date/tier/FX/tax normalization, native bill discrepancies, source
idempotency and company/cost/billing access. `allocation` selects all PR12 classes;
`helpers_verify` selects normalization; `targeted` adds dependent supply/allocation
integrity and commercial security. `fresh` installs the PR12 selection. `upgrade`
installs the exact72-file PR11 archive, seeds actual supplier source/corrections,
commercial/supply/allocation and customer sales snapshots/reviews, captures cold
committed evidence before any purchase snapshot table exists, then updates and
runs the complete addon milestone and preservation comparison. Real-session probes
race collection, price, receipt, bill, RFQ confirmation and grant changes. Safety
uses actual confirmed/reserved/valued/posted synthetic fixtures. Larger500/2000/
10000-source benchmarks, peak memory and manual browser UAT remain unmeasured/
unexecuted unless recorded separately. Runtime files are removed after shutdown;
source-qualified logs and reproducible probes remain in evidence.


The first complete PR12 upgrade run executed451 tests:448 passed and3 failed.
The final upgrade verification selects all PR12 cases, the affected PR11 protection/
snapshot classes, supply/allocation integrity, commercial/revision security and
module/view loading. It verifies the repaired metadata denial and exact-source
history assertions while reusing unchanged earlier regression evidence. The failed
full attempt remains FAIL in history; the focused follow-up is reported with its
own actual count, never relabeled as a451-test PASS.


## PR13 / DEV07 reproducible isolated verification

The frozen source ledger is `evidence/pr13-verified-source-sha256.json`. The exact
76-file PR12 baseline is `evidence/pr12-source-baseline.zip`, with its SHA256 file.
`evidence/pr13-native-api-audit.json` identifies the inspected Odoo20 valuation APIs.

Use `evidence/pr13-verification-driver.py` only for the owned disposable loopback
PostgreSQL18 cluster on 55444. It initializes its own cluster and allowlisted test
databases and disables cron, HTTP, outgoing email and external mutations. It does
not operate on an existing production database. Do not run phases concurrently.
The driver uses the DEV00 runner, explicit existing test-class selectors and
nonzero parsed Odoo test counts; each run is bound to the source hash.

`python evidence/pr13-verification-sequence.py` runs final fresh installation,
QUICK precision/unknown-zero tests, TARGETED PR08–13 integration, actual archived
PR12 installation and cold retained-record capture before PR13 update, source
preservation, six real-session races and operational safety. The driver phase
arguments permit focused repairs without repeating unaffected gates. Preserve
failed-run history and do not reuse evidence from a different source ledger.

Races exercise duplicate collection, PO price, receipt, valuation value, FX and
scope revocation; each changed-source getter is checked before the next mutation.
The operational fixture includes a confirmed PO/SO, reservation, valued done move,
posted journal entry and portal/public negative access checks. Fixture writes are
synthetic preparation, never business-service actions. Evidence remains locally
under `evidence/pr13-*`; there are no stored production credentials.

After all drivers finish, `evidence/pr13-cleanup.ps1` requires stopped-server
status and verifies seven exact workspace targets before deleting only the owned
runtime. `python evidence/pr13-finalize.py` then verifies frozen code, exact PR12
archive, unchanged earlier business tests, native source hashes, mandatory real
runtime gates and cleanup before creating the A–J handoff and final status.
Optional posted landed-cost fixtures, larger workloads, peak memory and manual
browser UAT must remain explicitly NOT_RUN/NOT_MEASURED unless actually executed.
PR14 is not part of these selectors or this handoff.


## PR14 financial exposure verification

`evidence/pr14-verification-driver.py` runs isolated PR14 fresh, QUICK, TARGETED,
actual archived PR13 update/preservation, concurrency and operational-safety phases.
Only its exact allowlisted disposable databases on loopback port55445 are used.
Run phases sequentially; never concurrently. `TEST_REPORT.json` retains actual
counts, source fingerprints, timestamps, failures and evidence paths. An interrupted
run with no Odoo summary is not passing evidence. Prior test failures are retained.

The financial tests cover comparable signed costs, tiers, dates, FX, UoM, missing
costs, alternative quotation scopes, confidentiality, immutability and freshness.
Seven real-session races and a native/upstream immutability probe supplement ORM
regressions. Actual archived PR13 source and retained cost snapshots are checked
before update. See the final handoff for executed results; this setup description
alone is not proof of success. Larger loads, memory and browser UAT remain
NOT_MEASURED/NOT_RUN unless independently recorded.

After successful gates, `evidence/pr14-cleanup.ps1` verifies stopped-server status
and exact workspace-owned targets. `evidence/pr14-finalize.py` refuses verification
unless all mandatory gates match the final source ledger and runtime is removed.
PR15 is outside this scope.


## PR15 / DEV08 projected profitability verification

The PR15 driver owns a disposable PostgreSQL18 cluster on127.0.0.1:55446 and exact
allowlisted synthetic databases; `.pr15_*` files are local runtime only. Never run
phases concurrently. No existing user database or production credential is used.
The safe DEV00 runner captures real nonzero Odoo test counts and full logs bound
to the source ledger. Interrupted or failed runs remain history, never PASS.

`evidence/pr15-verification-driver.py` supports fresh, helpers_verify, targeted,
actual archived PR14 upgrade/cold capture/preservation, concurrency and operations.
The targeted selectors include PR11/14/15 financial/security and governed company
configuration regressions. No unrelated release-wide FULL result is claimed.
Nine race probes exercise duplicate calculation, source cost/receipt/valuation/FX,
proposal correction, native selling price, scope revocation and governed future
policy publication. Relevant current-policy changes have separate staleness tests.
The future-policy race also verifies unrelated-period publication does not stale
current policy. Native22-model and upstream-nine-model before/after captures prove
no operational or upstream mutation from profitability calculation.

The exact archived84-file PR14 source is installed and actual financial snapshots
are committed/cold-captured before PR15 schema exists. Preservation compares source
bytes and all retained stored fields. Cleanup verifies stopped-server status and
seven exact workspace targets; the finalizer rejects missing/mismatched-source
mandatory evidence. Real results are in TEST_REPORT.json and the A–J handoff.
500/2000/10000 inputs, peak memory and browser UAT remain NOT_MEASURED/NOT_RUN unless
separately executed. PR16 is outside these selectors and remains NOT_STARTED.


## PR16 / DEV08 independent controls and review readiness

`evidence/pr16-verification-driver.py` owns a new PostgreSQL18 cluster at
127.0.0.1:55447, private `.pr16_*` runtime and exact allowlisted synthetic databases.
Run phases sequentially. Native production records/credentials are not used.
The established DEV00 runner captures real nonempty Odoo summaries and source-bound
logs; failures and diagnostic smoke runs remain history. `allocation` is the full
PR16 focused suite; `smoke` is the single full-reference diagnostic. QUICK selects
independent math/gates plus foundation; TARGETED includes PR11/14/15/16 integrity,
security and company-policy dependencies. MILESTONE actual-upgrade selection covers
relevant PR08 through PR16 integration without claiming release-wide FULL coverage.

Actual PR15 archive (90 verified source files) is installed, synthetic operational
and all analytical evidence including profitability/risk is seeded and cold-captured
before any reconciliation schema exists, then PR16 update/preservation is checked.
Nine independent-session races cover duplicate run, PO price, receipt, valuation,
proposal correction, sales price, policy publication, FX and grant changes. Current
reconciliation must reject stale evidence; competing source changes cannot mix
versions. The operational probe compares22 native and13 upstream analytical models.

The first fresh attempt hit a wrong revision/batch-link lookup; the focused reference
then found an obsolete uom.rounding assumption. Both are retained failures; the
implementation now verifies the evidence's revision/batch link and the installed
Odoo20 native Product Unit decimal precision. Later actual results belong in
TEST_REPORT.json and evidence/DEV-08-pr16-summary.md, never inferred from this setup.

After all required gates pass, cleanup verifies stopped-server status and seven
exact owned workspace targets. The finalizer refuses verification unless every
mandatory gate matches the frozen source ledger, earlier tests/sources are unchanged,
actual nonzero counts/logs exist and runtime is removed. Larger loads/memory and
manual browser UAT remain NOT_MEASURED/NOT_RUN unless actually executed. PR17 is
outside this prompt; no sign-off, approval or application is performed.


PR16 final UI boundary verification uses fresh attempt4 with the complete controlled
reference, empty-optional-field review-wizard action and module foundation (six
actual tests when all execute). Final TARGETED selects exception lifecycle/security
and company-policy governance; full PR08-16 milestone still executes every PR16
class plus the relevant source integration. Earlier complete50-test fresh evidence
is retained with its own source; only matching final-source results establish final
verification. No fifty-test PASS is claimed for the six-test cold UI selection.


PR16 broad actual-upgrade attempt executed348 tests:347 passed,1 old atomicity
fixture failed because it assumed globally empty margin tables despite retained
PR15 snapshots. The failure remains history. That test now snapshots every stored
header/line/risk field before injection, asserts exact preservation afterward and
asserts no result for its own batch. The original empty-table case is still covered;
existing upgrade evidence is additionally protected. No passing business/security
assertion is relaxed. Final focused upgrade_verify reruns every PR16 class and the
PR15 snapshot class on the already-updated database, then preservation. Business
sources and all other tests are identical to the broad attempt; their ledger is
retained in pr16-business-milestone-source-sha256.json. Broad348 is never called PASS.


PR16 resumed verification (2026-10-31): preservation computed-status assertion uses
the original date retained in the commercial validation snapshot; stored-field and
source-byte comparisons remain exact. The previous live-date failure is retained.
Operational probe Finance-role setup now precedes native before-capture. Native
Odoo group changes create a res.users audit mail.message, identified in the retained
probe log. No messages/models are excluded from the final22-model comparison;
two failed setup attempts remain history. Application sources are unchanged.


## PR17 / DEV09 isolated scenario verification

The PR17 driver owns loopback127.0.0.1:55448, a fresh disposable PostgreSQL18
cluster and exact allowlisted synthetic databases. HTTP/cron/outgoing mail,
external mutations, real payments and live accounting are disabled. Run phases
sequentially. It reuses DEV00 nonzero-summary reporting and binds actual logs to
an exact source ledger; diagnostic failures/interrupted runs remain history.

fresh installs the scenario models/security/views and all new focused tests;
allocation updates an existing disposable database with the focused suite;
smoke executes the four-alternative numerical reference only; helpers_verify
selects pure scenario math/foundation; targeted adds relevant PR14/15/16 financial,
lifecycle and security regressions. Actual upgrade installs the exact95-file PR16
archive, seeds real reconciliation checks/exceptions/review and all upstream/native
fixtures, cold-captures storage, updates PR17, runs the broader selected PR08-17
milestone and compares every retained field and source byte. No production clone.

Real separate-session races cover duplicate calculation, assumption edits,
PO price/receipt/valuation, proposal correction, customer price, FX, policy and
grant changes. Native22-model and upstream17-model probes prepare authorization
before the before-capture; Odoo group-change mail audit is fixture setup, never
excluded from analytical before/after comparisons. Scenario probes never accept
commercial terms or create operational records outside explicit synthetic setup.

The first PR17 fresh run was intentionally stopped after repeated empty-required-
JSON issues: Odoo20 converts[] toSQL NULL. The retained log is FAIL without a
completed test count; it is not a partial PASS. Scenario issue evidence now uses
an explicit object containing an items list. Only executed final-source tests
establish verification. Larger loads/peak memory/manual browser UAT stay
NOT_MEASURED/NOT_RUN unless separately recorded. STOP after PR17; PR18 NOT_STARTED.

PR17 upgrade seed initially attempted reconciliation with the retained Purchase
actor and correctly hit the Finance-only guard. The synthetic manager now receives
the explicit Finance role before cold capture and initiates reconciliation through
that actor. The failed setup log remains history; application permissions and all
final-source fresh/QUICK/TARGETED evidence are unchanged. upgrade_resume continues
the already installed exact PR16 database, not a new production or reconstructed
baseline.


PR17 actual broad update:263 tests,262 passed and one old reconciliation atomicity
fixture failed on retained PR16 rows. The sole modified prior test now captures all
stored run/check/exception/review values, asserts their exact preservation and no
leak for its own batch, then verifies retry. That FAIL is never relabeled PASS.
The only further application change rejects price-only common-FX assumptions on a
two-date baseline; a new real FX regression checks explicit combined-rate support.
The exact pre-guard source archive and AST comparison constrain these deltas.
Final upgrade_verify reruns every new scenario test, related PR14 FX cases and the
PR16 lifecycle class against the already-updated database, followed by original
pre-upgrade preservation. Final fresh installation and scoped QUICK/TARGETED also
run. Unchanged upstream broad cases retain their own exact-source evidence.
The real concurrency probe now includes an eleventh selected-quotation confirmation
race in addition to the original ten mutation/idempotency cases.


Final PR17 UI-source freeze includes a readonly original net supplier price,
currency/UoM/eligible quantity display. fresh attempt4 selects four scenario cases
(full reference, two-date FX guard, governed landed sensitivity, real wizard basis)
plus four foundation methods:8 actual tests. The earlier full39-method cold install
belongs to its own pre-display source. All35 new scenario methods run in the final
upgrade_verify alongside related PR14 FX and PR16 lifecycle cases, then exact
pre-upgrade preservation. Final TARGETED selects FX boundary, scenario security,
related pricing and reconciliation lifecycle/security. No39-test final cold UI
claim. Final-source hashf377aa420b1cf28e459df5b20f7607df42b8dc33ed1d4ba0c4109e2625faecf8.


## PR18 customer repricing verification

Only the active PR18 analytical scope is implemented. Driver:
`evidence/pr18-verification-driver.py <phase> <attempt>` using Python3.14.6 and
Odoo20.0 Community FINAL, PostgreSQL18.4. The owned `.pr18_pgdata` cluster binds
127.0.0.1:55449 with dedicated synthetic role codex_vpr_pr18. HTTP and cron are
disabled; no external messages/payments or production data. Only one driver phase
may run at once. All temporary paths are workspace-local and explicitly removed
by `evidence/pr18-cleanup.ps1` after stopped-server verification.

Frozen108-file source ledger `evidence/pr18-verified-source-sha256.json` binds every
final runtime gate. `evidence/pr18-static.py` independently checks exact102-file
PR17 archive, unchanged old source/tests, precise optional-baseline-revenue AST
compatibility, one empty-JSON guard and one additional implemented-menu assertion.
New PR18 files must parse and contain no native CRUD/elevation/commit calls.
`evidence/pr18-finalize.py` refuses VERIFIED if mandatory current-source gates or
cleanup evidence are absent. Runtime success requires nonzero actual Odoo test
counts; shell probes require their explicit assertions and all expected markers.

Phases: fresh selects every new recommendation class and foundation on a clean
install; helpers_verify is QUICK math/foundation; targeted covers recommendations,
native taxes/discount/FX/UoM, lifecycle/security and dependent PR15/16 equations.
Upgrade first installs the exact PR17 archive, seeds native operational and PR08-17
analytical history, then cold-captures persisted data before PR18 schema exists.
Actual update runs relevant PR11-18 financial/security/lifecycle regression.
Preservation compares every retained stored nonbinary/nonrelated field, native
states, source bytes and attachments, with zero auto-generated recommendations.
The retained setup actor/company and original commercial as-of date are explicit;
these do not certify current-date freshness. Concurrency uses real separate
transactions for12 source/rights/terms/quotation/assumption/idempotency races.
Operations snapshots22 native models plus23 upstream analytical models before/
after generation/review, including existing confirmed SO/PO, valued stock move,
posted journal and portal/public negative access. Synthetic setup mutations are
outside the measured application boundary. Performance measures10 repeated
generations and100 real affected lines; no production capacity claim.

Initial fresh registry attempt failed because autogenerated M2M relation exceeded
PostgreSQL63 characters; explicit short relation fixed it. Second fresh run37/41
exposed the new menu expectation, Decimal test context, duplicate tax fixture name
and PR16 empty JSON risk reasons. Focused repair selection PASS4. Added USD/box10
fixture initially attempted native forbidden confirmed-order pricelist mutation;
it was corrected to configure currency before confirmation, then PASS1. All failed
attempts remain in TEST_REPORT.json. Any later setup/probe corrections are appended
below and final actual counts/evidence belong in evidence/DEV-09-pr18-summary.md.

Manual browser UAT and FULL release NOT_RUN. Production/cold capacity and larger
independent-order/detail-row workloads NOT_MEASURED. Measured500/2000-line,
10000-stage-reference, SQL and sampled-RSS results are in the final PR18 handoff.
PR19 NOT_STARTED.


PR18 additional representative performance gate: `performance` runs
pr18-performance-probe.py after the mandatory source-bound regressions. Real500
and2000 affected lines comprise N-1 eligible draft lines and1 protected confirmed
line; native source-currency/tax prices are calculated without changing orders.
The2000-line cohort binds2000 records per PR11/13/14/15/17 stage (10000 relevant
financial references across five models, not10000 independent orders/detail rows).
It measures elapsed generation time, SQL cursor queries,20ms sampled process RSS
peak/growth; current-source validation and immutable publication are included,
fixture setup excluded. Single-product/shared-currency/tax warm-process results
cannot certify diverse production/cold concurrency capacity. Gate remains pending
until actual assertions/markers PASS; final handoff records genuine measurements.


Actual archived PR17 update PASS283/283 on pre-rounding source527ee0680052c95a55510ff87cc540063d6e2c381fe740208a99edb067f688eb;
exact retained history/source bytes/native states across77 models PASS. Final
review added a real failing partial USD/discount rounding regression, retained in
pr18-repairs-update-20261031T082825+0000_targeted.log. Native margin24.97458243%
exposed the proportional-remainder error. Native unchanged-quantity rounding and
normalized native percentage-cap basis corrected it; calculationversionv2.
Focused correction PASS1, strengthened capped residual assertion PASS1. Exact
108-file pre-rounding archive/ledger and AST constrain the delta to customer_line,
calculation version and one additional test, preserving38 earlier tests. Final
fresh/QUICK/TARGETED rerun on corrected source. upgrade_verify selects all7 native
tax/discount/FX methods,3 related partial/cap/order cases,2 lifecycle cases and3
security methods (15 expected; only actual summary proves counts), followed by
original preservation. The broad283 source remains separately labeled; unchanged
old methods are not needlessly rerun. Final frozen hash:
ae4bc60390222ee1f6c7e273f1c9a56a4405c43fd4e5634b8c21731c55dcf2dc.


Initial PR18 concurrency probe failed during setup because newly created PR17
scenarios had not calculated their required result before recommendation collection.
The missing/stale source guard correctly rejected them. Fixture setup now explicitly
calculates each scenario before starting races, including fresh grant/quotation
fixtures. Source application remains unchanged; all12 required race assertions and
expected serialization/currentness outcomes remain. Failure log retained.


PR18 final completion: fresh43, QUICK10, TARGETED63, focused actual-upgrade15,
77-model preservation,12 real races,22-native/23-upstream safety PASS on frozen
source ae4bc60390222ee1f6c7e273f1c9a56a4405c43fd4e5634b8c21731c55dcf2dc.
Broad283 PASS retains its exact pre-rounding source with constrained two-file
compatibility proof. Final static/evidence checks485 PASS. Representative warm
generation500 lines26.976s/3593 SQL;2000 lines267.067s/6608 SQL,10000 five-stage
source references;22 native snapshots unchanged in both, including partial pricing.
Sampled RSS peaks408502272/925515776 bytes; growth55525376/171413504 bytes.
Fixture/source creation excluded;20ms process sampling, not whole-system peak.
2000-line generation is slow; no interactive latency SLA or production/cold capacity
certification. Historical setup failures retained. Seven owned temporary paths
removed after stopped-server verification. A-J report: evidence/DEV-09-pr18-summary.md.
PR18 VERIFIED; STOP. PR19 NOT_STARTED.


## PR19 fresh-install checkpoint

Final initial freeze 2a4eabcd5c33bd83f0ef5b0bee3418ee6349acbe948e1df7be9f67bbdd591f74:
116 source files; fresh41/41 PASS, source unchanged during run. Static666 PASS
proves exact104 old files unchanged and four explicitly extended integration files.
Focused manual/quorum/decrease/source-grant repairs7/7 PASS before final freeze;
all included in fresh41. New-version publication rollback regression included.
Native/upstream safety, actual PR18 upgrade, real races and representative workload
measurements remain pending. PR19 IN_PROGRESS; PR20 NOT_STARTED.


PR19 operational safety first failed: negative baseline profit made PR16 relative
profit/margin decline ratios undefined (not zero). Projection policy does not waive
missing ratios. Second diagnostic retained exact blocked control records. Safety
fixture now uses explicit native1500/box at setup, revenue450/cost210/profit240;
no application source change or weakened financial guard. Third run PASS:
evidence/pr19-operational-safety-20261031T132337Z.log. Verified real sequential
route/idempotent submission/withdrawal, protected portal/public attachment access,
22 native model snapshots and27 upstream model snapshots unchanged.


PR19 concurrency fixture failures retained. Existing PR18 recommendation race setup
permitted incomplete review references; PR19 submission correctly did not. Fixture
now explicitly verifies fixed PO terms, recollects purchase evidence afterward,
and writes company-dependent standard stock cost under the fixture company rather
than the default company. Each baseline is asserted ready before any race. No
financial/application source or assertion is weakened to accommodate the fixture.


PR19 hardening findings reproduced after initial source2a4eabcd fresh41/QUICK11/
TARGETED49/races8/safety passed. Exact116-file pre-hardening archive retained.
Activity negative probe failed on native default_res_model context:
evidence/pr19-activity-guard-20261031T134110Z.log. New critical/high-risk authority
regression failed because Sales was dropped:
evidence/pr19-repairs-update-20261031T134249+0000_targeted.log.
Guard now recognizes defaults and supported ORM target forms before native side
effects. Critical and high risk accumulate. Contractv2 invalidates old submissions.
Prior PASS records remain bound to their own source, not relabeled final. Final
source install/focused update/upgrade/preservation/races/safety/performance required.


## PR19 final verified results

Frozen source 1da64b4b50e82db5e8e1355d83435b854d166130d134705bb1c827eb1464d77e; static829 PASS.
FRESH: PASS42; evidence/pr19-fresh-install-20261031T134721+0000_milestone.log
HELPERS_VERIFY: PASS11; evidence/pr19-helpers_verify-update-20261031T135722+0000_quick.log
TARGETED: PASS11; evidence/pr19-targeted-update-20261031T135747+0000_targeted.log
UPGRADE: PASS132; evidence/pr19-upgrade-update-20261031T140250+0000_milestone.log
UPGRADE-PRESERVATION: PASS1; evidence/pr19-upgrade-preservation-20261031T141807Z.log
CONCURRENCY: PASS8; evidence/pr19-concurrency-20261031T142140Z.log
OPERATIONAL-SAFETY: PASS2; evidence/pr19-operational-safety-20261031T143300Z.log
ACTIVITY-GUARD: PASS2; evidence/pr19-activity-guard-20261031T134716Z.log
PERFORMANCE: PASS4; evidence/pr19-performance-20261031T143156Z.log
Actual performance measurements and workload boundaries: evidence/DEV-10-pr19-summary.md. Seven owned runtime paths removed after verified stopped server. Browser UAT/FULL NOT_RUN; production/cold capacity NOT_MEASURED. PR19 VERIFIED; PR20 NOT_STARTED.
