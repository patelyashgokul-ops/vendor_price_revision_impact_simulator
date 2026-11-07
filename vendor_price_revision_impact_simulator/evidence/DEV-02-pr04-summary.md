# PR-04 / DEV-02 implementation and handoff

PR-04 **VERIFIED** on Odoo Community 20.0 final / Python 3.14.6 / disposable
PostgreSQL 18.4. Dependencies remain base and product. PR-05 is NOT_STARTED.

## Implementation

- `vendor.price.revision.config`: company/version/captured currency, finite
  effective dates, readiness, cost/FX/UoM/tax/missing-data/date governance,
  maker-checker and notification definitions.
- `vendor.price.revision.margin.policy`: explicit percentage points,
  product → exact category → company precedence; scope/company/duplicate checks.
- `vendor.price.revision.risk.rule`: company-currency [minimum, maximum) intervals,
  finite nonnegative values, no overlaps, complete scale required for publication.
- `vendor.price.revision.approval.policy`: additive categories, multiple required
  supported roles, distinct approvers, complete intervals; no grants/actions.
- `vendor.price.revision.config.audit`: immutable before/after values and actor/time.
- Company-scoped Administrator writes; manager/finance/director/auditor reads.
  Direct/ID-only/export/grouped reads, nested commands, copies, reparenting and
  context defaults retain authorization. Standard settings views reuse the root.
- Publication validates configuration only. Published definitions and dates cannot
  mutate. Company-row serialization protects competing policy mutations; no
  two-session concurrency stress test is claimed.

## Evidence

| Selection | Result | Passed | Failed | Log |
|---|---|---:|---:|---|
| Final fresh install, all addon classes | PASS | 56 | 0 | `evidence/pr04-fresh-install-20261028T125443+0000_quick.log` |
| Focused configuration and security | PASS | 37 | 0 | `evidence/pr04-targeted-update-20261028T124559+0000_targeted.log` |
| Final actual PR03 update, MILESTONE | PASS | 56 | 0 | `evidence/pr04-upgrade_verify-update-20261028T125634+0000_milestone.log` |
| Final preservation probe | PASS | not counted | 0 | `evidence/pr04-upgrade_verify-preservation-20261028T125719Z.log` |
| QUICK static assertions | PASS | 18 | 0 | `evidence/DEV-02-pr04-static-validation.txt` |

The final complete suite covers all 19 configuration methods and the existing
foundation/core/security tests. The focused run preceded final numeric input
hardening; the final fresh/update suites also cover that correction. An additional
clean run passed 58 runner-counted tests including Odoo's two web posttests.
Initial four runtime failures and their logs remain in history; relevant final
tests pass. Existing navigation assertions now require the new menu and role
exactly; no test was removed or weakened.

The archived PR03 source matches every earlier verified-source hash. It was
installed before seeding revisions, lines, evidence, users and a supplier price.
Post-upgrade probes verify unchanged IDs, values, ownership, write dates and
price, retained least privilege, one sequence/root, and no automatic policy data.
Source hashes, probes, driver and shutdown logs are retained in evidence. All
temporary clusters/databases, filestores, baseline checkout and private configs
were removed after clean shutdown. No existing or production database was used.

## Boundaries and handoff

Supplier/product prices, revision state, cron count, retained evidence and
company/role access were tested. SO/PO/stock/accounting models were not installed;
their document/valuation side-effect tests are NOT_RUN. Browser UAT and two-session
concurrency stress tests are NOT_RUN. No financial, approval, application, import
or notification engine is claimed ready. License/publisher decisions remain
release prerequisites.

Use `docs/CONFIGURATION_GUIDE.md` for setup and retrieval contracts. Future
consumers resolve a published policy with explicit company/date, capture its
version/provenance and revalidate approval eligibility after changes. Draft
inspection is distinct from operational retrieval. Plan finite periods before
immutable publication. PR-05 may consume these contracts when explicitly requested;
it has not started.
