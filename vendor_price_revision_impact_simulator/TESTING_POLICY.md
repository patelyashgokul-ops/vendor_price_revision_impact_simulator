# Testing Policy

This policy applies to APP 06, Odoo Community only. Read it with `AGENTS.md` and `DEVELOPMENT_PROGRESS.md`. Test evidence belongs in `TEST_REPORT.json`; no empty selection or successful process exit alone proves coverage.

## Testing levels

| Level | Purpose and selection | Completion rule |
|---|---|---|
| QUICK | Smallest meaningful test set directly related to a change, such as a changed field, validation rule, calculation, access rule, or view. | Run relevant available tests and record evidence. Do not use it to ignore known failures. |
| TARGETED | The changed feature and dependent workflows, including relevant financial and security regressions. Use after substantial feature or integration changes. | Correct relevant failures before completion. |
| MILESTONE | Tests needed by the acceptance criteria of an integrated workstream, cross-feature dependencies, and critical regression coverage. | Block the milestone on unresolved critical failures or missing mandatory evidence. |
| FULL | Release-level regression: applicable addon tests, financial invariants, company isolation, approval, application/idempotency, recovery, install/upgrade, performance, and frontend coverage where applicable. | Required for final release candidates, major version conversion, final security review, major migration, or critical architecture changes. |

Run load/stress tests at planned milestones or when performance-sensitive code changes, not on every prompt. Never mark work VERIFIED while a mandatory relevant test fails. Use `NOT_RUN` or `BLOCKED` when execution is unavailable.

## Risk-based escalation

| Change | Minimum selection |
|---|---|
| Small UI/view change | QUICK static/view checks |
| Product matching | QUICK mapping; TARGETED affected price calculations |
| Currency, UoM, or quantity normalization | TARGETED normalization and financial reference regressions |
| Supply allocation | TARGETED SO/PO/stock reconciliation and double-counting |
| Gross margin formula | TARGETED financial calculations and reference cases |
| Approval | TARGETED authorization, self-approval, authority limits, and company isolation |
| Price application | TARGETED or MILESTONE application, idempotency, concurrency, history protection |
| Security model | Relevant permission tests and wider affected security regression |
| Database migration | Migration and relevant full data-integrity verification |
| Final release | FULL |

Expand selection when dependencies, risk, or acceptance criteria require it; do not use token or time limits to omit mandatory financial or security checks. Do not rerun unchanged evidence for identical code and environment unless a milestone or dependency change requires it. Invalidate stale evidence when code, dependencies, Odoo version, configuration, or business assumptions change.

## Odoo test conventions

Follow the actual target Odoo version's testing APIs ([Odoo 20 backend testing reference](https://www.odoo.com/documentation/20.0/developer/reference/backend/testing.html)). Use a module `tests/` package with imports in `tests/__init__.py`, `test_*.py` files, `TransactionCase` for ORM/business logic, `HttpCase` for HTTP/browser integration, and `tagged()` where helpful. Use isolated fixtures, company-specific users, and deterministic expected financial values. Keep tests narrow and name them by concern (for example, `test_currency_uom.py`, `test_supply_allocation.py`, `test_financial_exposure.py`, `test_approval_security.py`, and `test_idempotency.py`). Never remove or weaken a passing test to make a suite green. Examples are conventions, not claims that those tests already exist.

## Runner and commands

Use `python scripts/run_tests.py --help` for the runner interface. Configure a local JSON file based on `scripts/test-runner.example.json`, then invoke `python scripts/run_tests.py --mode quick --config <LOCAL_CONFIG>`. Modes are `quick`, `targeted`, `milestone`, and `full`; each requires an explicit configured Odoo tag expression. The runner requires an existing addon with a manifest and Python tests, an explicit installed/update action, an explicit `dedicated_test` database role, an exact database allowlist match, and `pg_isready` confirmation before invoking Odoo. It never deletes or clones databases.

Odoo 20 supports `--test-tags`; it implies test enablement. After verifying the local paths, addon state, and tags, the corresponding command shape is:

```text
<PYTHON> <ODOO_BIN> -c <ODOO_CONF> -d <DEDICATED_TEST_DB> <-i| -u> <MODULE> --test-tags <VERIFIED_TAGS> --stop-after-init --log-level=test
```

Use `-i` for initial installation and `-u` for an installed addon. Use only a dedicated test database that is explicitly allowlisted; never infer safety from a database name containing “test”. Verify addon discovery and selected tags against the installed Odoo version. Do not treat exit code zero as proof that tests ran: the runner requires a nonzero test count in Odoo's result summary before reporting PASS. Until addon tests exist, test selection is `NO_TESTS`, not PASS.

## Database and side-effect safety

Never run tests against production. Do not use production credentials, clone production automatically, delete databases, or perform destructive recovery. The runner refuses execution unless the configured role is `dedicated_test`, the exact database appears in `allowed_test_databases`, outgoing email/external API mutation/cron/real payment/live accounting are explicitly disabled in config, the Odoo executable/config/module/tests/tag expression are present, and PostgreSQL reports that database ready. If any safety check fails, no Odoo process is started and the result is BLOCKED. A database name is not proof of safety; the operator must explicitly attest its role and side-effect controls in local configuration.

Use isolated mail, API, cron, payment, and accounting settings for tests. Do not send real supplier/customer messages, mutate live external APIs, run uncontrolled cron work, or create real payment/accounting transactions. Avoid placing secrets in this repository, command arguments, logs, or reports. Keep local runner config untracked and restrict access to Odoo configuration credentials.

## Reporting and milestones

Every run records prompt, environment/version, addon, level, invocation reference, start/end times, actual exit status, known counts (otherwise `null`), status, evidence path, and blocking reason in `TEST_REPORT.json`. Allowed outcomes include PASS, FAIL, BLOCKED, NOT_RUN, and NO_TESTS. Preserve actual history; never fabricate timestamps or counts.

Milestone gates M0–M8 cover, in order: testing foundation; import/mapping/normalization; sales/purchase/inventory allocation; exposure/margin/scenarios; approval/maker-checker; safe application/recovery/concurrency; financial/security/UAT/performance hardening; master Community release; individually verified additional versions. A gate passes only with its mandatory evidence. A generated implementation or a green process exit without verified test execution is insufficient.
