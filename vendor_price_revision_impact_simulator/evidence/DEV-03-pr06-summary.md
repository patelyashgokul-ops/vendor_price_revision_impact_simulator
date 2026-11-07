# PR-06 / DEV-03 implementation, validation and handoff

PR-06 **VERIFIED**. PR-07 remains NOT_STARTED. No PR-07/08 functionality implemented.

## Environment and prerequisites

Odoo Community 20.0 final; Python 3.14.6; addon `vendor_price_revision_impact_simulator`. Base/product and the
existing installed openpyxl/lxml dependencies are unchanged. PR00–PR05 evidence
was inspected. Archived PR05 source matches every prior verified-source hash.
Tests used new dedicated PostgreSQL 18.4 databases on 127.0.0.1:55437 with exact
allowlists and isolated side effects. All temporary database/cluster/filestore/
baseline/config files were removed after clean shutdown. No production or existing
development database was used; no Odoo version migration occurred.

## Implementation and files

- `models/structural_validation.py`: pure lexical Decimal/date rules, explicit
  canonical targets, issue classification and exact duplicate keys.
- `models/import_validation.py`: batch/row extensions, mapping, immutable validation
  runs/results/issues, corrections/exclusion evidence, review-input version events,
  correction wizard and inherited-date invalidation. Batch locking protects inputs;
  savepoints publish current results only after complete success. No commits/sudo
  in ordinary review business operations.
- `security/import_validation_security.xml`: own/company role grants and mandatory
  company/active-user restrictions on all support models and wizard.
- `views/import_validation_views.xml`: source mapping, explicit assumptions,
  paginated row/status filters, current issues/results, corrections and history.
- `models/__init__.py`, manifest and test package: registration only.
- `tests/test_import_validation.py`: 27 new tests across five classes.
- `tests/test_import_intake.py`: interrupted-upload assertion now checks exact
  preservation of pre-existing batches, supporting actual seeded upgrade testing.
- `tests/upgrade/seed_pr05.py`, `verify_pr06.py`, `verify_concurrent_validation.py`:
  actual source/policy preservation and four two-session probes.
- Import validation guide, README, security/testing setup, progress/report and
  retained source hashes/logs/driver describe the implementation and handoff.

## Behavior and security

Map supplier columns by batch/sheet/one-based ordinal, including duplicate/blank
headers. Unsupported, missing and conflicting mappings fail clearly. Identifier,
price/currency/UoM/MOQ/date presence and syntax are checked without resolving Odoo
products/currencies/UoMs. Explicit revision currency/date inheritance records
provenance; no arbitrary price, quantity or UoM defaults are inserted. Numeric
parsing is Decimal-safe and separator/date conventions are explicit. Blank/zero/
negative/nonfinite/formula cases remain distinct.

Duplicate review uses all mapped effective canonical context, including terms,
tiers, currencies and dates. All duplicate candidates require review; no row is
deleted or silently selected. Corrections and exclusions use immutable overlays
with actual actor/time/reason and old/original/new values. Mapping/settings changes
also preserve input history. Current results clear immediately on input changes;
historical issues remain traceable. Identical revalidation reuses its snapshot.

Purchase preparers correct/revalidate only accessible extracted company drafts;
Purchase Managers retain company scope. Finance/Auditor/Director/Pricing readers
have no automatic edit authority. Sales-only/configuration-only/unrelated/portal/
public users lack confidential review access. Direct ORM, ID-only reads, exports,
grouped queries, role unions and nested ownership are tested. Original source
attachment/download protection remains. Generic review exports escape formula
prefixes at the output boundary without editing stored evidence.

## Actual test results

| Selection | Result | Passed | Failed | Evidence |
|---|---|---:|---:|---|
| Final fresh installation | PASS | 115 | 0 | `evidence/pr06-fresh-install-20261028T142148+0000_quick.log` |
| Focused review/security | PASS | 35 | 0 | `evidence/pr06-targeted-update-20261028T141355+0000_targeted.log` |
| Final actual PR05 update MILESTONE | PASS | 115 | 0 | `evidence/pr06-upgrade_verify-update-20261028T142009+0000_milestone.log` |
| PR05 preservation probe | PASS | not counted | 0 | `evidence/pr06-upgrade_verify-preservation-20261028T142130Z.log` |
| Four two-session concurrency cases | PASS | 4 | 0 | `evidence/pr06-concurrency-20261028T142604Z.log` |
| QUICK static assertions | PASS | 30 | 0 | `evidence/DEV-03-pr06-static-validation.txt` |

All five new classes plus relevant PR05 attachment/download security were selected
in the focused run. The Duplicate-filter Boolean was added afterward and is covered
by both final full addon suites, which supersede the earlier focused evidence for
that assertion. Final complete regressions include the original eight addon classes. Initial SQL-conflict error messaging, a legacy empty-database assertion and
inactive mapping visibility during reactivation were corrected. The Duplicate
filter uses a searchable Boolean marker rather than an unsupported JSON domain; earlier failures remain in history. Tests were not
removed or weakened. Source hashes and executed driver are retained.

The reference fixture produces exactly 500 = 480 ready + 12 blocked + 8 review +
0 excluded. Unknown SKUs and valid-looking `ZZZ` currency prove product/FX work is
deferred. Final fresh local validation duration: 2.529 seconds.
Other benchmark sizes and peak memory are NOT_MEASURED. ORM view/action loading
and HTTP content regression were executed; browser UAT is NOT_RUN.

## Business safety and limitations

Representative supplier/product prices/write dates, revision state/write date,
raw source bytes/hash/cells and notification/activity/cron counts remain unchanged.
Prior PR05 customer-pricelist preservation also ran. No final revision lines,
product matching, normalized prices, financial results, approvals or vendor price
application were created by review. SO/PO/stock/accounting fixtures are NOT_RUN
because those models are not installed; no broader operational coverage is claimed.

Mappings are batch-specific; templates are deferred. Disabled definitions retain
ordinal/target uniqueness; edit the retained definition to remap. Conservative
whole-batch invalidation preserves duplicate correctness. Configuration-only roles
do not gain confidential mapping access. Existing license/publisher decisions and
standard Odoo superuser/supplierinfo boundaries remain.

## PR07/08 handoff

`batch.get_structurally_ready_rows()` checks the current input snapshot, excludes
excluded/unready rows and returns only structural candidates. Read each row's
current immutable result, effective values, parsed lexical strings, provenance,
source/sheet positions and historical review evidence. PR07 must resolve products
and variants separately; PR08 must independently establish UoM/FX/quantity/date
commercial applicability. Preserve source/overlay/history/access contracts. No
structural result is fully validated, approved or ready to apply.

Details: `docs/IMPORT_VALIDATION_GUIDE.md`. PR07 remains NOT_STARTED.
