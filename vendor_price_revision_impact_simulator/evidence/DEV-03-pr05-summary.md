# PR-05 / DEV-03 implementation, validation and handoff

PR-05 **VERIFIED**. PR-06 is NOT_STARTED.

## A — Environment

Odoo Community 20.0 final; Python 3.14.6; addon `vendor_price_revision_impact_simulator`. Dependencies remain
base/product plus declared installed Python parsers openpyxl 3.1.2 and lxml 6.0.2.
No packages or core patches were installed. defusedxml is absent; explicit bounded
XML preflight rejects DTD/entities before openpyxl parsing. Tests use new dedicated
PostgreSQL 18.4 databases on 127.0.0.1:55436. Temporary test environments were
removed after clean shutdown; no existing/live database was used.

## B — Implementation

- Authorized transient upload wizard with company/revision rechecks, CSV options,
  worksheet inspection/selection and idempotent upload action.
- Persistent batch, immutable raw staging rows, attempt history and company limits.
- Original immutable attachment/evidence integration and original-byte SHA256.
- Strict CSV decoding/quoting, Unicode/leading-zero/multiline preservation.
- Bounded XLSX ZIP/XML gate, read-only parser, primitive type/formula metadata and
  workbook cleanup. No formula, macro or external-link execution.
- Company/vendor/hash duplicate candidates stop at duplicate_review. Corrected
  files create new evidence. Atomic row staging, controlled errors and retry retain
  prior failures, with batch uniqueness and transaction locks.

## C — Files

- `models/import_parser.py`: bounded extraction and source fingerprints.
- `models/import_intake.py`: wizard, lifecycle, row/attempt/limit models, evidence,
  revision action and attachment guards.
- `models/vendor_price_revision.py`: accurate legacy filename/checksum help.
- `models/__init__.py`, `__manifest__.py`: registration/dependencies/data.
- `security/import_intake_security.xml`: role grants and global company isolation.
- `views/import_intake_views.xml`: wizard, batches, source rows, limits and menus.
- `tests/test_import_parser.py`, `tests/test_import_intake.py`: 32 new test methods.
- Existing foundation/core/security tests: expanded menu and attachment contracts.
- `tests/upgrade/seed_pr04.py`, `verify_pr05.py`, `verify_concurrent_intake.py`:
  actual baseline preservation and two-session probes.
- `docs/IMPORT_ARCHITECTURE.md`, README, security matrix, testing setup, progress
  and TEST_REPORT.json: implementation, verification and handoff documentation.

## D — Security

Purchase preparers upload only into accessible editable drafts; managers retain
their existing company draft authority. Raw reads follow own/company confidential
scope; sales-only/public/portal/configuration-only/unrelated users cannot read raw
files. Non-superuser direct ORM and HTTP tests verify company/role boundaries.
Source files cannot be overwritten, made public, tokenized, reassigned, copied
to another scope or deleted. Metadata-only elevation identifies protected files;
content access uses the requesting user's real authorization. Standard export
privilege is separate. No approval or global administration grants were added.

## E — Actual test evidence

| Selection | Result | Passed | Failed | Evidence |
|---|---|---:|---:|---|
| Final fresh install | PASS | 88 | 0 | `evidence/pr05-fresh-install-20261028T134423+0000_quick.log` |
| Focused intake/security | PASS | 50 | 0 | `evidence/pr05-targeted-update-20261028T132336+0000_targeted.log` |
| Final actual PR04 update MILESTONE | PASS | 88 | 0 | `evidence/pr05-upgrade_verify-update-20261028T134737+0000_milestone.log` |
| Final PR04 preservation probe | PASS | not counted | 0 | `evidence/pr05-upgrade_verify-preservation-20261028T134829Z.log` |
| Two-session concurrency probes | PASS | 2 | 0 | `evidence/pr05-concurrency-20261028T133410Z.log` |
| QUICK static checks | PASS | 27 | 0 | `evidence/DEV-03-pr05-static-validation.txt` |

All 11 parser, 13 intake, 7 intake-security and 1 HTTP-download methods were
selected, alongside prior foundation/core/company/security regression. Tests cover
CSV/XLSX content, encodings, formulas, archive/resource limits, source evidence,
hash/duplicate behavior, safe failure/rollback/retry, ID/export access and HTTP
downloads. Earlier ACL XML, export fixture and historical attachment assumptions
were corrected. A preservation probe ordering assertion was corrected to compare
the same audit IDs independent of cache ordering. Earlier failures remain in
history; they were not replaced with fabricated passes. Final decompression-error
hardening is covered in the final full addon suites.

500-row synthetic CSV elapsed time in final fresh log: 0.305 seconds.
This is one local fixture, not a production throughput/memory claim. Other benchmark
sizes and peak memory are NOT_MEASURED. Browser UAT is NOT_RUN; ORM views and HTTP
content routes were tested. SO/PO/stock/accounting document tests are NOT_RUN because
those models are not installed in the dedicated base/product environment.

## F — Business safety

Tests preserve supplier price/write date, product cost/list price, customer fixed
pricelist rule/write date, revision state/write date, scheduler and notification
counts. No final revision price lines are created by extraction. No matching,
price comparison, financial calculation, commercial approval or live price
application engine was implemented. No operational side effects are claimed for
uninstalled sale/purchase/stock/accounting models.

## G — Progress

PR05 VERIFIED; reports/progress contain actual evidence and retained failures.
No unresolved critical defect in implemented scope. Parser time limits are
cooperative; external relationships and unsupported workbook structures are
rejected. Standard Odoo superuser powers and separate supplierinfo permissions
remain as documented. License/publisher release decisions remain pending.

## H — PR06 handoff

Consume `vendor.price.revision.import.batch` and immutable
`vendor.price.revision.import.row.raw_cells`, ordered headers, source logical and
physical positions, worksheet name/index, formula columns, technical failure
attempts and duplicate_review state. Build separate business mapping/validation
results; preserve original bytes/digests, raw rows, authorization and historical
errors. Extracted data is never verified price data. PR06 has not started.

Detailed source/resource/security contract: `docs/IMPORT_ARCHITECTURE.md`.
