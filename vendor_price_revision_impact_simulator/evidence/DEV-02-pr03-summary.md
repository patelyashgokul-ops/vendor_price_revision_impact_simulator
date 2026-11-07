# APP 06 — PR-03 / DEV-02 final report

PR-03 is VERIFIED. PR-04 remains NOT_STARTED.

## A — Environment

Odoo Community 20.0 final; Python 3.14.6; addon `vendor_price_revision_impact_simulator`.
Dependencies remain `base` and `product`. Tests ran against newly created UTF-8
databases on a dedicated PostgreSQL 18.4 cluster bound to 127.0.0.1:55434.
Fresh database: `codex_vpr_pr03_fresh_4_20261028`. Upgrade database:
`codex_vpr_pr03_upgrade_1_20261028`. Cluster, databases, filestores, baseline
checkout, and private configs were removed after clean shutdown. No existing
development or production database was used.

## B — Files changed

- [vendor_price_revision.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/models/vendor_price_revision.py) — Ownership/parent-child guards, ID-only read/export checks, confidential field groups, Odoo 20 UoM reference compatibility repair.
- [vendor_revision_security.xml](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/security/vendor_revision_security.xml) — Nine business roles, technical reader, least-privilege grants and global company/active-user restrictions.
- [vendor_revision_menus.xml](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/views/vendor_revision_menus.xml) — Role-aware root and existing child navigation.
- [vendor_revision_views.xml](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/views/vendor_revision_views.xml) — Role-aware existing action.
- [test_security_roles.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/tests/test_security_roles.py) — Effective role, context, ownership, export, aggregate, evidence and business-safety security regression.
- [test_module_foundation.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/tests/test_module_foundation.py) — Preserved navigation regression with the new explicit role groups.
- [__init__.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/tests/__init__.py) — Register focused security tests.
- [seed_pr02.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/tests/upgrade/seed_pr02.py) — Create retained PR-02 data and confirm the original broad grant in an isolated DB.
- [verify_pr03.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/tests/upgrade/verify_pr03.py) — Read-only data/write-date/price preservation and corrected legacy permission assertions.
- [SECURITY_MATRIX.md](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/docs/SECURITY_MATRIX.md) — Permissions, group composition, standard-model exposure and future service contracts.
- [README.md](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/README.md) — Current security scope and verification.
- [TESTING_SETUP.md](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/TESTING_SETUP.md) — Actual clean-install and baseline upgrade procedure.
- [DEVELOPMENT_PROGRESS.md](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/DEVELOPMENT_PROGRESS.md) — PR-03 verified, PR-04 not started.
- [TEST_REPORT.json](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/TEST_REPORT.json) — Real execution history, scopes, counts and limitations.

## C — Role-based access

The legacy Purchase User ID/membership is preserved and its broad PR-02 grants are
replaced with own-record reads and own-draft edits. Purchase Managers manage scoped
drafts and ownership. Finance, Director, Auditor, and Pricing Operator receive only
confidential company-scoped reads. Sales and Configuration roles receive no raw
pricing access. Revision/evidence deletion is denied; draft line deletion is scoped
to preparers/managers. No role implies global system or accounting administration.
Roles compose additively; an Auditor with a separate preparer role may edit only as
that independently assigned role permits. Full matrix: [SECURITY_MATRIX.md](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/docs/SECURITY_MATRIX.md).

## D — Multi-company and ownership

Ungrouped Odoo 20 `ir.access` restrictions intersect all grants with authorized,
selected companies and active-user status. Shared product/vendor records remain
usable; company-specific relations retain ORM consistency checks. Parent/child
mutations, nested commands, owner assignment, copies, direct writes and mixed
recordsets enforce the draft/ownership policy before mutation. All scoped
cross-company tests passed, including authorized two-company creation and forged
company contexts. Copies receive fresh identities/current ownership and leave
source lines/evidence on the original.

## E — Confidentiality and residual boundaries

Sales-only users cannot read raw prices/references; sensitive fields also use
server-side groups. Explicit read/export checks cover ID-only requests. The
standard export privilege is independent and does not bypass APP authorization.
Evidence is metadata-only with no attachment/download endpoint; chatter/activity
mixins are absent. Their future file/message security tests are NOT_RUN, not PASS.
Standard Odoo internal users can still read otherwise permitted
`product.supplierinfo` prices; a test demonstrates this separate exposure.
No core product/Purchase/Sales security was rewritten. True technical superusers
retain inherent framework privileges; no business approval/application authority
is inferred from those privileges. License/publisher release decisions remain as
documented by PR-01.

The review also repaired the retained draft UoM constraint: installed Odoo 20 uses
reference-unit hierarchies, not the removed category field. Compatible and
incompatible source units now receive meaningful regression coverage; no
normalization or conversion engine was introduced.

## F — Actual automated results

| Execution | Level | Result | Passed | Failed | Evidence |
|---|---|---|---:|---:|---|
| Final clean install | QUICK | PASS | 39 | 0 | [odoo-pr03-fresh-install.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/odoo-pr03-fresh-install.log) |
| Focused security | TARGETED | PASS | 18 | 0 | [odoo-pr03-security-targeted.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/odoo-pr03-security-targeted.log) |
| Actual PR-02 upgrade regression | MILESTONE | PASS | 37 | 0 | [odoo-pr03-upgrade-milestone.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/odoo-pr03-upgrade-milestone.log) |
| PR-02 baseline preparation | QUICK | PASS | 4 | 0 | [odoo-pr03-pr02-baseline-install.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/odoo-pr03-pr02-baseline-install.log) |
| Upgrade preservation probe | TARGETED | PASS | Not counted | 0 | [pr03-upgrade-verify_pr03-20261028T122427Z.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr03-upgrade-verify_pr03-20261028T122427Z.log) |
| QUICK static | QUICK | PASS | 17 | 0 | [DEV-02-pr03-static-validation.txt](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/DEV-02-pr03-static-validation.txt) |

Fresh install ran `2026-10-28T12:18:05+00:00` to `2026-10-28T12:20:46+00:00`. The final
upgrade regression ran `2026-10-28T12:24:02+00:00` to `2026-10-28T12:24:23+00:00`.
The fresh total includes Odoo server-wide posttests; the focused suite contains
18 addon test methods with additional role-combination subtests.
Executed commands and method names are retained in [TEST_REPORT.json](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/TEST_REPORT.json).

Original PR-02 source archive: [pr02-source-baseline.zip](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr02-source-baseline.zip).
SHA-256: `cfebec99716af697abb3d7e68ea3c98cea9d64ce2bd3bd221e57187c0fc0fce4`. Its baseline was installed before seeding, with the
pre-upgrade broad write permission explicitly observed. The current source was
then loaded with `-u` and a MILESTONE module test selection. The read-only probe
confirmed retained IDs, references, companies, owners, notes, line/evidence values
and write dates, unchanged supplier price/write date, one sequence, and the
corrected legacy grant. Probe: [pr03-upgrade-verify_pr03-20261028T122427Z.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr03-upgrade-verify_pr03-20261028T122427Z.log).

Earlier domain/fixture/export-boundary failures and their logs remain in history;
the final runs above pass. No FULL unrelated business suite or browser UAT was run.

## G — Business safety

No approval, application, financial simulation, import, or reporting engine was
implemented. Representative supplier price, product cost, and list-price data
were verified unchanged. Purchase, sales, stock, and accounting models were not
installed in these test databases; tests against posted/confirmed operational
documents are NOT_RUN. No live price updates or external notifications occurred.

## H — Progress

PR-03 VERIFIED; no outstanding critical issue in this implemented scope.
[DEVELOPMENT_PROGRESS.md](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/DEVELOPMENT_PROGRESS.md) and [TEST_REPORT.json](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/TEST_REPORT.json) record actual outcomes
and residual limitations. Static evidence: [DEV-02-pr03-static-validation.txt](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/DEV-02-pr03-static-validation.txt). Verified source
hashes: [pr03-verified-source-sha256.json](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr03-verified-source-sha256.json). PostgreSQL shutdown log:
[pr03-postgres-final.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr03-postgres-final.log).

## I — PR-04 handoff

Use the explicit Configuration Administrator identity for future company-owned
configuration permissions. Grant no commercial approval, price application,
global user/group administration, or additional company authority by implication.
Preserve the global company boundary, role unions, owner/child guards, protected
states, evidence confidentiality, and standard-model exposure distinction.
Current role assignment remains with existing Odoo access-right administrators.
PR-04 has not been started.
