# PR19 / DEV10 - Management approval routing foundation

## A. Environment

Odoo 20.0 Community FINAL; addon vendor_price_revision_impact_simulator. Dependencies: base, product, purchase_stock, sale_stock, mail. Python3.14.6, PostgreSQL18.4, isolated allowlisted synthetic loopback cluster55450; no HTTP, cron, external APIs, mail transport or real payments. Existing target retained. Prerequisite evidence: pr19-predevelopment-audit.json.

## B. Implementation

Four exact review types: vendor revision, negotiated supplier scenario, eligible customer repricing, explicit compatible combined package. PR04 published policy extends its existing complete half-open currency-normalized amount scales with risk/contract escalation and ordered roles. No policy fallback. Active internal reviewers must have exact company, role, source and native order access. Maker, creator, submitter and configured contributors are excluded. Augmenting-path matching enforces distinct identities and quorum; optional manual wizard uses the same eligibility. Only first stage is ready; later stages wait. Exact current PR16/17/18 evidence gates submission. Submitted package and route are immutable; controlled withdrawal/staleness/new versions preserve history. Optional internal first-stage activities are idempotent, contain no cost details, create no email, and are archived on invalidation. New-version/audit and submission failures roll back safely.

## C. Files changed

Four new models files: models/approval_math.py (metrics/matching), approval_policy.py (PR04 extensions), approval_engine.py (source/eligibility/route), approval.py (models/services/wizards/activities). New security/approval_security.xml, data/approval_data.xml, views/approval_views.xml, tests/test_approval.py, docs/APPROVAL_WORKFLOW_FOUNDATION.md. Existing integration-only changes: __manifest__.py, models/__init__.py, tests/__init__.py, tests/test_module_foundation.py. All other104 prior source files byte-identical. Evidence probes and reports accompany this change.

## D. Actual reference routes

A: INR1500 -> independent Purchase Manager, ready. B: INR50000 -> Purchase then Finance. C: INR150000 -> Purchase, Finance, Director. D: maker/creator with manager roles excluded. E: missing eligible independent checker blocks, then safely retries after real grant. F: FIFO/unsupported financial readiness blocks submission. G: hypothetical supplier109 -> signed cost increase900 versus original cost, improvement600 versus proposed115; no acceptance. Executed test names and source-bound logs are retained in fresh/targeted/upgrade evidence. Decrease95 remains signed-500, cost_increase0. Critical negative profit adds configured Finance/Director even below amount thresholds.

## E. Frozen evidence

Evidence includes source model/ID/version/fingerprint, PR16 readiness/provenance, company/currency, supplier bytes SHA, signed and explicitly positive metrics, normalized financial scope, scenario assumptions and improvement, exact recommendation option, policy audit/version, matched category/metric/interval/reasons, excluded users, eligible candidates, actual distinct assignments and planned stage statuses. Header submission_fingerprint hashes financial+route package; evidence fingerprint additionally includes actual created activity IDs. Actual synthetic request IDs, source snapshots, policy version, signed values, frozen route, excluded/eligible/assigned identities, submission/evidence fingerprints and retained audit IDs: pr19-submitted-evidence-sample.json (same executed performance/safety probe, not an invented reference). Append-only created/validated/blocked/submitted/routed/lifecycle events retain actor and time. Failed validations remain issues; corrections do not erase them.

## F. Security

Global active selected-company and exact source/native-order rules cover header, stages, evidence, events, issues, grouping and export. Scoped auditor is read-only. Portal/public and pure sales/purchase cannot obtain financial detail. Direct ORM forged states/actors/routes/child commands, cross-company reads/exports, source grant revocation, private activity token forgery and external chatter are denied. Protected native resource attachment reads are tested separately. Reviewer current eligibility is checked again; source/role/company changes invalidate authority without rewriting submitted evidence.

## G. Automated testing

- FRESH: PASS 42; evidence/pr19-fresh-install-20261031T134721+0000_milestone.log
- HELPERS_VERIFY: PASS 11; evidence/pr19-helpers_verify-update-20261031T135722+0000_quick.log
- TARGETED: PASS 11; evidence/pr19-targeted-update-20261031T135747+0000_targeted.log
- UPGRADE: PASS 132; evidence/pr19-upgrade-update-20261031T140250+0000_milestone.log
- UPGRADE-PRESERVATION: PASS 1; evidence/pr19-upgrade-preservation-20261031T141807Z.log
- CONCURRENCY: PASS 8; evidence/pr19-concurrency-20261031T142140Z.log
- OPERATIONAL-SAFETY: PASS 2; evidence/pr19-operational-safety-20261031T143300Z.log
- ACTIVITY-GUARD: PASS 2; evidence/pr19-activity-guard-20261031T134716Z.log
- PERFORMANCE: PASS 4; evidence/pr19-performance-20261031T143156Z.log

Static: PASS 829 actual checks; exact116-file ledger 1da64b4b50e82db5e8e1355d83435b854d166130d134705bb1c827eb1464d77e. Initial scope-key/required-JSON and fixture ACL/optional-zero failures remain in TEST_REPORT history. Actual activity context bypass and dropped high-risk Sales authority were reproduced, fixed and tested; contract v2 invalidates v1 submissions. Exact116-file pre-hardening archive plus AST checks constrain the delta to three files and preserve every earlier passing assertion. The listed final-source gates supersede separately retained pre-hardening fresh41/QUICK11/TARGETED49/races8/safety evidence. No process-only or empty-selection PASS. Real pre-PR19 PR18 archive installed, synthetic history captured cold, then actual addon update and81-model preservation tested. Concurrency uses two real PostgreSQL sessions, safe retries and currentness checks.

Performance (actual measured values; warm process, synthetic only):

```json
{"measurement_scope": "warm sequential actual prepare+submit+withdraw, exact same financial source, activities disabled; fixture preparation excluded", "observed_rss_peak_bytes": 214962176, "requests": 100, "rss_sampling": "after each withdrawal; not intra-call peak", "rss_start_bytes": 205426688, "seconds": 107.906, "sql_queries": 116400}
```

```json
{"measurement_scope": "warm sequential actual prepare+submit+withdraw, exact same financial source, activities disabled; fixture preparation excluded", "observed_rss_peak_bytes": 246697984, "requests": 500, "rss_sampling": "after each withdrawal; not intra-call peak", "rss_start_bytes": 205426688, "seconds": 534.825, "sql_queries": 582000}
```

```json
{"fixture_seed_seconds": 11.049, "historical_requests": 2000, "historical_stages": 10000, "measurement_scope": "explicitly seeded inactive history, not 2000 executed submissions; three 80-row header pages and three 80-row stage pages plus exact scoped counts", "paginated_read_seconds": 13.067, "rss_bytes": 285691904, "sql_queries": 130}
```


## H. Business safety

Synthetic fixture setup creates explicit historical confirmed SO/PO, valued stock and posted journal solely in the disposable database. Before/after snapshots across22 monitored native models around PR19 services prove no supplierinfo/customer pricing, SO/PO, stock quantity/reservation/valuation, accounting, mail/cron changes. The27 monitored upstream analytical models remain unchanged. No Approve/Reject/Return decision, supplier/customer acceptance, final authorization or live application exists. No production data was accessed.

## I. Progress and limitations

PR19 VERIFIED for the documented scoped backend evidence. TEST_REPORT.json and DEVELOPMENT_PROGRESS.md updated. Manual browser UAT NOT_RUN; FULL release NOT_RUN; Production/cold capacity NOT_MEASURED; History load is explicitly seeded inactive fixture, not 2000 executed submissions; Performance uses one warm synthetic transaction and sequential versions on one source; independent RPC, active inbox and independent-source capacity NOT_MEASURED. Seven owned disposable runtime paths removed only after stopped-server verification; cleanup evidence: pr19-runtime-cleanup.json. No blocker for this scope. Historical load is clearly labeled fixture-only, without submitted evidence, decisions or active authority.

## J. PR20 handoff

Consume current awaiting_review requests, frozen evidence and sequential stage plans; draft/ready_to_submit/blocked are not approval authority, and withdrawn/stale/invalidated/superseded are inactive. Add explicit server-side approve/reject/return decisions with exact role/company/source access, current financial readiness, maker/creator/submitter exclusions, risk-sensitive authority, distinct reviewers, predecessor and final quorum checks. Retain immutable decision actors, reasons, timestamps and before/after audit. Recheck sources/policy/eligibility under locks; stale/conflicting approvals require explicit review and new versions, never silent refresh. Handle activity completion/archive transactionally with rollback and retry. Protect direct ORM, child/evidence/export/attachment paths and all concurrency invariants. Decision methods still prohibit supplierinfo, SO/PO, customer pricing, stock valuation or accounting application. PR20 NOT_STARTED. STOP AFTER PR19.
