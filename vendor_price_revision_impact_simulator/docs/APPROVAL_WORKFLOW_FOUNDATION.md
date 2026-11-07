# Management review routing foundation (PR19 / DEV10)

PR19 creates review requests and immutable evidence/routes. It cannot approve,
reject, return, accept supplier terms, grant customer amendment rights or apply
prices. PR20 must separately implement decisions. Operational SO/PO, pricelists,
stock, valuation and accounting remain outside every routing service.

## Sources and request types

- `vendor_revision`: exact current confirmed PR16 reconciliation; no alternative.
- `supplier_scenario`: exact baseline and current financially verified PR17 result.
- `customer_repricing`: complete current PR18 recommendation and its exact eligible
  customer option. Protected/no-eligible customer prices cannot acquire permission.
- `commercial_package`: explicitly selected combined PR18 option with the matching
  current PR17 alternative, same baseline/revision/company. Standalone benefits
  are never added together.

Draft creation checks source relationships, financial read access, selected company
and manager authority. The accountable maker is derived from the revision owner;
it cannot be supplied as a convenient different user. Creator and submitter are
separate recorded identities. The maker must remain an active internal member of
the source company. Only a reason can be edited by the draft creator. Source edits
use a controlled new version, not direct reassignment of submitted authority.

Submission reruns the PR16 current getter and requires ready-for-financial-review,
no blocking critical controls, exact current PR17/18 inputs and complete money.
Readiness is analytical suitability for review, not GL verification, accepted
procurement cost, approval or realized benefit. Governed documented projections
remain projections. Missing costs, revenue, scope or FX do not become zero.

## PR04 company policy reuse

No second policy registry is introduced. Published PR04 configurations and approval
amount-scale rows are extended. Existing configurations default to
`workflow_enabled=False`; upgrading never silently activates approval authority.
An administrator must explicitly publish enabled request types, submitter roles,
authority ordering, amount rules and high/critical/contract-review role sets.
Critical/negative-profit review includes Finance under the existing PR04 negative
margin policy. Configuration does not grant native source or reviewer rights.

PR04 interval semantics stay `[minimum, maximum)`, with a final open-ended tier.
For an illustrative INR-cent policy ending inclusively at10000.00, use exclusive
maximum10000.01; the next tier starts10000.01. These are fixture examples, never
production financial defaults. Currency rounding precedes money comparisons;
margin-erosion rules retain percentage-point precision. Policy dates are inclusive
and use the submission date, with company currency checked again at runtime.

Each category has one coherent request-type list, metric and trigger across its
complete scale. Vendor/scenario requests require an unconditional finance-exposure
category; customer requests require customer-repricing; a combined package requires
both. Optional categories add requirements when their explicit trigger applies.
Conflicts, uncovered categories/ranges, unsupported types/currency and missing roles
block publication or routing; there is no Administrator fallback.

Metric names are explicit: cost increase, cost reduction, absolute cost change,
profit reduction, revenue increase or margin erosion. Original signed deltas are
retained. A negative cost change maps to zero *cost increase* only under that
declared metric; it never silently becomes a positive cost increase. Separate cost
reduction/absolute rules can require their own reviews. Source money is already
normalized by the financial snapshots; routing never supplies fallback FX.

Financial metrics compare the selected projected outcome to original baseline cost
and revenue. A109 supplier scenario on the reference data has900 cost increase
versus the original100 baseline, and600 hypothetical improvement versus proposal115;
these are separate values. Customer revenue recovery and cost reduction stay
distinct, with source eligibility and residual gaps retained in the chosen option.

## Routing, SoD and quorum

Every applicable mandatory category and risk/contract escalation contributes its
authority. Equivalent role stages merge with all reasons; no weakest-rule wins.
Role order is explicitly configured from Purchase/Sales/Finance/Director roles.
The source and selected risk levels are conservatively combined; unknown risk
requires high-risk review. Negative projected/constituent profit requires critical
review. Protected or unknown customer terms retain separate commercial review.

Reviewer resolution is company-bound and checks active internal identity, actual
group membership, allowed companies, native order/line read access and analytical
source scope. No role assignment automatically grants Sales/Purchase/Accounting
administrator privileges or financial warehouse grants. Candidates without exact
source access are excluded, rather than receiving unrestricted sudo projections.

Creator, accountable maker and submitter are always excluded. Stronger configured
SoD also excludes recorded source preparers/collectors, scenario input/result
actors, recommendation author and commercial interpretation contributors. Superuser
ID1 is never a reviewer fallback. Separate sessions/logins do not create identity
independence. A multi-role person can occupy only one route slot.

Deterministic augmenting-path matching finds a complete independent assignment;
it does not greedily consume a multi-role reviewer needed by a later stage.
Named reviewer restrictions are validated and intersected when requirements merge.
Configured manual assignment requires every exact stage/quorum to be supplied
through `action_set_assignments`; arbitrary user IDs and self-assignment fail.
Quorum feasibility is checked before submission, bounded to32 distinct identities.
Single-role quorum uses multiple distinct assigned reviewers in that level;
additional multi-role quorum retains its own explicit requirement. No votes or
completion are evaluated. Only the first level is ready; later levels wait for
predecessor decisions that do not exist until PR20. Parallel routing is not inferred.

## Immutable submission and lifecycle

Global sequence references identify requests without implying approval. An exact
source identity has one active key, enforced by PostgreSQL uniqueness and company/
batch/request serialization. Repeated preparation returns the existing active
request; repeated current submission returns it without new stages, evidence,
activities or events. Source relationships are rechecked on every attempt.

Draft -> ready-to-submit (optional validation) -> awaiting-review is the successful
foundation path. Explicit validation stores actionable blockers without producing
a route. Publication failures roll back the entire submission savepoint, preserving
the prior state; they never return success. Reasons and errors remain history.

Submission freezes source IDs/versions/fingerprints, original file hash, normalized
money, risk, scope, assumptions, chosen option, policy definition/version, excluded
identities, candidates, assignments, quorum, ordering, reasons and actor/time.
Financial and route evidence is an immutable package, not merely a dynamic link.
Underlying source records are already immutable snapshots; their references remain
historically traceable without cloning unrelated financial line data repeatedly.

`get_current_request` revalidates sources/policy and every assigned reviewer's
current membership/access/independence. Stored candidate lists are historical
eligibility evidence, not permanent authority. Source/policy/reviewer changes disable
current readiness. `current_state` and stage effective status expose this; the
explicit refresh action records stale invalidation and archives linked activities.
My Pending Reviews filters assigned first stages through the current getter, not
only a stale stored awaiting-review flag. Historical lists show stored lifecycle;
they do not imply current authority. Inbox validation is bounded to500 active stages.

Withdrawal is available before decisions to maker/creator/submitter or an explicitly
allowed manager. It retains evidence, records reason/actor/time and cancels stage
readiness without a decision. Stale/withdrawn requests require fresh sources and a
new linked version. Superseding preserves old evidence and withdrawal/stale events.
No old decision or authorization is carried forward.

## Internal activities and confidentiality

Activities are opt-in per published company policy. Only the first stage's validated
assigned users receive a generic request-reference activity; future levels receive
none. Native Odoo20 `mail_activity_quick_update` suppresses assignment email.
Approval records do not acquire followers or permit chatter/external notification.
Activity create/write/unlink is protected for this model through a private service
token; untrusted RPC context cannot forge it. Withdrawal/staleness archives the
activity rather than deleting history. Creation is recorded, never claimed delivered.
PR20 must govern activity completion and decision effects separately.

All request/child evidence, group/search/export and related views require active
selected company, all allocation/supply/cost/customer grants and native order rights.
Pure Sales/Purchase and portal/public roles gain no financial projection. Auditors
are read-only; independently added authority roles are evaluated normally. Native
attachment resource checks use the same protected request/evidence access; no
public URLs or new public financial attachments are created. Source drilldown
checks read permission again. Direct state/policy/route/actor/child/evidence writes,
cross-company source links and nested commands cannot forge readiness.

## Verification and PR20 handoff

TEST_REPORT.json and the PR19 A-J handoff report actual tests, failures, upgrade
preservation, races, side effects and measured performance. No successful process
exit or empty test selection is coverage. No FULL release or manual browser UAT
is inferred from scoped backend tests.

PR20 must consume only current requests with frozen evidence, exact stage plan,
candidate/assigned identities, company policy, roles, SoD/quorum and source versions.
It must add server-side approve/reject/return transitions, decision evidence,
predecessor/quorum checks, immutable decision identities, current authority,
concurrency/rollback, invalidation and activity lifecycle. Every decision still
prohibits supplier/customer pricing application, PO/SO/stock or accounting changes.
STOP after PR19. PR20 NOT_STARTED.


### Measured workload boundaries

PR19 performance verification distinguishes 100/500 actual sequential request
versions (prepare, submit, withdraw on one verified source) from explicitly seeded
inactive history (2,000 headers, 10,000 cancelled stages). Seeded history has no
submitted financial evidence, assignments, decisions or active authority. Pagination
measurements are not a claim that 2,000 submissions executed. Fixture creation is
reported separately. No production or cold capacity guarantee is inferred.

Manual assignment uses the request's Assign Draft Reviewers wizard. It offers only
current eligible candidates for a selected published policy level. Partial draft
choices may be saved one level at a time; submission requires every level, exact
quorum and globally distinct independent identities. Deterministic policies reject
manual overrides. New-version publication is atomic even if an internal caller
catches an audit failure.


### PR19 hardening before verification

A real negative probe reproduced activity creation through native
`default_res_model` context. The boundary now resolves both model defaults and
recognizes native tuple/recordset/ID forms before create/write side effects. Tests
also retain normal create/write/unlink delegation for other activity models.
Critical risk adds its authority to every applicable high-risk authority; it cannot
replace or drop a separately configured Sales/Finance level. A genuine failing
four-role reference is retained before correction. Calculation contract v2 makes
all older v1 submitted request packages stale rather than silently reusing a weaker
route. No business decisions or live pricing application were added.


The 100/500 workload uses one warm synthetic transaction and rolls it back after
assertions. It does not measure independent RPC transactions, simultaneous active
inboxes or independent financial source creation. Observed RSS is sampled after
each completed withdrawal, not continuously inside each service call.
