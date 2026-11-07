# APP06 PR20 / DEV10 approval decisions - verified handoff

## A - Environment

Odoo20.0 Community FINAL, Python3.14.6, PostgreSQL18.4 on Windows. Technical addon vendor_price_revision_impact_simulator; dependencies base, product, purchase_stock, sale_stock, mail. Existing20.0 baseline retained after development-start verification against https://nightly.odoo.com/. All runtime fixtures were synthetic in an allowlisted disposable loopback55451 cluster; HTTP and cron disabled; no external services.

## B - Implementation

Authenticated Approve/Reject/Return actions enforce ordered mandatory stages and distinct represented principals plus actual actors. Every decision and finalization rechecks current PR16 reconciliation, PR17 assumptions, PR18 options, frozen policy, source and exact commercial payload. Required reasons, immutable decisions/final artifact, independently authorized company/type/role/time-bound delegation, half-open UTC validity and governed new versions preserve history. Rejection/return cancel future stages; votes never transfer. Internal activities archive with retained references; completion is not approval. Historical APPROVED is separate from current authority. Native JSON encoding and equal-membership M2M order are checked without rewriting old signed PR19 evidence. Same-second revocation retains causal prior-vote IDs under the request lock.

## C - Files changed

Five old integration files: [__manifest__.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/__manifest__.py), [models/__init__.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/models/__init__.py), [tests/__init__.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/tests/__init__.py), [models/approval_engine.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/models/approval_engine.py) (routing policy hook only), [models/approval.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/models/approval.py) (activity message only). All other111 previous files, including every old test, are byte-identical to the actual116-file PR19 archive.

New files: [models/approval_decision_math.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/models/approval_decision_math.py) (UTC/local expiry); [models/approval_decision_policy.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/models/approval_decision_policy.py) (explicit company policy); [models/approval_decisions.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/models/approval_decisions.py) (workflow/evidence/delegation); [models/approval_decision_ui.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/models/approval_decision_ui.py) (guarded wizards/documents/actions); [security/approval_decision_security.xml](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/security/approval_decision_security.xml); [views/approval_decision_views.xml](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/views/approval_decision_views.xml); [tests/test_approval_decisions.py](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/tests/test_approval_decisions.py) (50 meaningful methods). Design: [docs/APPROVAL_DECISION_ENGINE.md](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/docs/APPROVAL_DECISION_ENGINE.md). Executable probes, raw logs, archived baseline and static ledger are in evidence/pr20-*.

## D - Actual fixture reference results

| Reference | Executed result |
|---|---|
| A | Exposure INR1500; single Purchase stage, one actor, exact final artifact; native price unchanged. |
| B | Exposure INR150000; Purchase then Finance then Director; exactly3 decisions and1 final artifact. |
| C | Finance quorum2: first vote partial; duplicate denied; second distinct person finalizes. |
| D | Finance rejects after Purchase approval; Purchase evidence retained, Director cancelled, no final authorization. |
| E | Return retains original evidence; linked successor starts with zero votes; rejection terminal. |
| F | Submitted INR109 changes to112: Finance blocked, old vote retained as history, source recalculation/new submission/new votes required. |
| G | Maker with Purchase/Finance/Director and full source grants still cannot approve. |
| H | Exact valid-until boundary blocks strict downstream getter; historical approved status retained. |

These assertions and PR20_REFERENCE_A-H markers are in the update milestone log below; they are synthetic fixture results, not customer approvals.

## E - Approval integrity

The submitted source revision, baseline, scenario/recommendation/option versions, full row commercial snapshots, currency/UoM/quantity/MOQ/date semantics and separate decision policy are frozen with hashes. Quorum counts only immutable approved votes of currently eligible distinct principals/actors. No stage skips or zero quorum. Finalization independently reconstructs the chain and exact payload; database uniqueness plus request/source/user locks and savepoints prevent duplicate votes/artifacts and partial success. Source, permission, policy or time drift removes current authority without erasing old decisions. No default lifetime is invented: source-only or explicitly configured elapsed days/local date. Finalization failure and deadline crossing roll back the new vote.

## F - Security

Global active selected-company and exact source warehouse/native-order rules protect headers and financial detail, grouping and exports. Original-user source permissions apply; no eligibility sudo. The sole new sudo identifies protected attachment metadata following the existing intake guard; actual content/read/stream checks restore the requesting user. Private binary request attachments cannot gain public tokens, be reassigned, replaced or deleted. Direct ORM create/write/delete of immutable decisions/artifacts and fabricated actor/context/stage IDs are denied. Delegation cannot elevate roles or bypass maker/creator/submitter/contributor exclusion; an independent configured governor authorizes it. Tests cover foreign-company manager grouping, lost source grants/roles, portal/public and activity forgery.

## G - Executed verification

| Gate | Result / actual count | Evidence |
|---|---|---|
| FRESH | PASS 11 | [evidence/pr20-fresh-install-20261101T061428+0000_milestone.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr20-fresh-install-20261101T061428+0000_milestone.log) |
| HELPERS_VERIFY | PASS 9 | [evidence/pr20-helpers_verify-update-20261101T062223+0000_quick.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr20-helpers_verify-update-20261101T062223+0000_quick.log) |
| REPAIRS | PASS 3 | [evidence/pr20-repairs-update-20261101T061305+0000_targeted.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr20-repairs-update-20261101T061305+0000_targeted.log) |
| UPGRADE | PASS 182 | [evidence/pr20-upgrade_resume-update-20261101T062700+0000_milestone.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr20-upgrade_resume-update-20261101T062700+0000_milestone.log) |
| UPGRADE-PRESERVATION | PASS 1 | [evidence/pr20-upgrade-preservation-20261101T065828Z.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr20-upgrade-preservation-20261101T065828Z.log) |
| CONCURRENCY | PASS 9 | [evidence/pr20-concurrency-20261101T062050Z.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr20-concurrency-20261101T062050Z.log) |
| OPERATIONAL-SAFETY | PASS 2 | [evidence/pr20-operational-safety-20261101T062200Z.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr20-operational-safety-20261101T062200Z.log) |
| PERFORMANCE | PASS 4 | [evidence/pr20-performance-20261101T065931Z.log](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr20-performance-20261101T065931Z.log) |

Static 804 PASS; source 329c8c594280e4f9a372b6f8c0452c2d02d60fbcfcfb959f722ef038b3822ae6. Actual archived PR19 install/seed/cold capture precedes the update milestone; preservation compares88 captured registered models (including legitimately empty history tables), all old stored business values, relation membership, original source bytes, pending request route/evidence/activities and no automatic decisions. Relevant financial PR16-19 and old PR19 tests run during update. Eight real two-session races cover quorum, duplicate click, approve/reject, vote/revoke, reviewer role/company loss, deadline expiry and native source change. A ninth separate company-isolation assertion group uses fresh sessions following the races.

Earlier genuine failures remain in TEST_REPORT.json, including an out-of-window synthetic delegation probe and a cold-capture evidence marker mismatch corrected before the actual schema update and an unsupported nonempty scenario-event fixture assertion replaced by exact captured baseline cardinality: native JSON hash encoding, native M2M reload ordering, archived activity relation context and same-second delegation revocation were corrected. Two synthetic test fixture errors (missing manager ACL and immutable grant identity write) were corrected without weakening business assertions. The initial full fresh run executed54 tests:51 passed and3 clock fixtures failed because their hard-coded06:00 clock preceded native cost records once the suite ran after06:00. Only these three new test clocks were corrected to follow native fixture creation; boundary assertions and application code were unchanged. The affected fresh-install selection then reruns with math/foundation checks, and the complete new business suite runs in the actual upgrade milestone. Final gates supersede those failures on the frozen source.

Measured workloads (fixture setup excluded from actual cycles):

```json
[
  {
    "company_policy_lookup_api_calls": 16800,
    "decision_seconds_max": 3.4228,
    "decision_seconds_median": 2.4185,
    "decision_seconds_p95": 3.102,
    "decision_seconds_total": 243.882,
    "decision_sql_queries": 245305,
    "measurement_scope": "warm sequential actual prepare+submit+approve+strict getter+governance invalidate, one Finance stage, exact same source, activities disabled; fixture preparation excluded",
    "observed_rss_peak_bytes": 240013312,
    "quorum_display_read_seconds_total": 218.2626,
    "requests": 100,
    "rss_sampling": "after each full cycle; not intra-call peak",
    "rss_start_bytes": 202031104,
    "sample_authorization_json_utf8_bytes": 10701,
    "sample_decision_json_utf8_bytes": 938,
    "seconds": 774.571,
    "sql_queries": 854042
  },
  {
    "company_policy_lookup_api_calls": 84000,
    "decision_seconds_max": 7.3867,
    "decision_seconds_median": 2.3169,
    "decision_seconds_p95": 3.1109,
    "decision_seconds_total": 1195.109,
    "decision_sql_queries": 1226505,
    "measurement_scope": "warm sequential actual prepare+submit+approve+strict getter+governance invalidate, one Finance stage, exact same source, activities disabled; fixture preparation excluded",
    "observed_rss_peak_bytes": 395956224,
    "quorum_display_read_seconds_total": 1155.302,
    "requests": 500,
    "rss_sampling": "after each full cycle; not intra-call peak",
    "rss_start_bytes": 202031104,
    "sample_authorization_json_utf8_bytes": 10701,
    "sample_decision_json_utf8_bytes": 938,
    "seconds": 5948.105,
    "sql_queries": 4270043
  },
  {
    "fixture_seed_seconds": 54.288,
    "historical_decisions": 10000,
    "historical_requests": 2000,
    "measurement_scope": "explicitly seeded inactive history with full-sized fixture-labelled decision JSON, no authorizations; not 2000 executed submissions or 10000 actual votes; three 80-row header and decision pages plus exact authorized counts",
    "paginated_read_seconds": 60.254,
    "rss_bytes": 466718720,
    "sql_queries": 128
  }
]
```

Limits: Performance PASS means workload/count/safety assertions completed, not a latency/query/RSS SLA; Host scheduling/load and pauses are not controlled; timings describe this local run; Browser UAT NOT_RUN; FULL release NOT_RUN; Production/cold/parallel RPC capacity NOT_MEASURED; Performance uses one warm synthetic transaction, one source and sequential versions; activities disabled; 2000 history headers and 10000 decision rows are explicitly seeded fixture records, not actual executed submissions/votes; no authority artifacts.

## H - Business safety

During PR20 services,22 monitored native models and27 upstream analytical models remain unchanged. Supplierinfo/customer prices, confirmed SO/PO, reservations, stock values, posted accounting and mail/cron were compared before/after. The valued receipt3500, confirmed orders and posted entry were created only during synthetic fixture setup before safety snapshots. No supplier/customer messages, application, jobs, consent, pricelist rewriting, inventory valuation or accounting posting are performed by this feature. APPROVED means internal authorization only.

## I - Progress

PR20 VERIFIED for the documented scope. TEST_REPORT.json.pr20_handoff and DEVELOPMENT_PROGRESS.md updated with actual evidence; prior history preserved. No open mandatory blocker. Disposable cluster stopped with status3; seven exact owned runtime paths, including database cluster, filestore and reproduction configuration, are retained under TESTING_POLICY.md:51 (no database deletion). Runtime disposition evidence and PostgreSQL log are retained. PR21 NOT_STARTED. Browser UAT and FULL release remain NOT_RUN.

## J - PR21 read-only handoff

The exact synthetic sample is [evidence/pr20-authorization-sample.json](C:/PycharmProjects/odoo20/custom_addons/vendor_price_revision_impact_simulator/evidence/pr20-authorization-sample.json): request 16, artifact 5, company 7, type vendor_revision. It was valid at capture, then explicitly invalidated in the safety exercise; the disposable fixture is not usable operational authority. The sample contains source revision, payload references/full row snapshots, scenario/recommendation versions, reconciliation ID, source/submission/payload hashes, policy/version, actor/principal decision chain, mandatory route/quorum, exclusions, approved/expiry instants and normalized currency/UoM/MOQ/effective dates.

PR21 must call get_current_approval() under original-user selected-company permissions; a historical approved state is insufficient. It must independently verify current source/hash/version/time/type and exact authorized scope, required external consent and currency/UoM/date/tier normalization, then implement its separately authorized dry-run, application idempotency, concurrent-change guards, transactional all-or-nothing rollback/retry and immutable before/after audit. An application must never include unapproved prices or cross-company scope. None of these application operations are implemented or executed by PR20. STOP after PR20.
