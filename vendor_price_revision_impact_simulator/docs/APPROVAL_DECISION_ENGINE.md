# Approval decision engine (PR20)

APPROVED DOES NOT MEAN APPLIED.

## Scope and boundaries

PR20 reuses PR19 requests, stage plans, financial source validation, immutable
submitted evidence, actor exclusions, company grants and protected internal
activities. It adds authenticated approve/reject/return decisions, exact final
management authorization, independent delegation and current authority validity.
PR21 is NOT_STARTED. No supplierinfo, SO/PO, customer pricing, inventory, valuation,
accounting or supplier/customer messaging operation belongs to this engine.

## Explicit company opt-in and migration

Decision controls extend the existing PR04 published policy. Existing policies have
decision_enabled=False; an addon update creates no votes or final approvals. The
new decision-policy fields are excluded only from the PR19 routing snapshot, so
adding schema fields does not silently rewrite historical routing fingerprints.
The full PR04 before/after configuration audit still includes all fields. A new
decision-enabled submission freezes decision policy separately, along with the exact
commercial subject. Older routing-only packages cannot authorize a decision without
a governed newly submitted decision contract and current policy/source validation.

Approval justification is required by default and can be explicitly made optional
for approve only. Reject/return always require reasons. Zero review hours means no
fixed review deadline; it never waives source freshness. There is no invented global
approval lifetime. Source-only validity, elapsed days or an explicit local expiry
date must follow the published policy. Governance groups are explicit.

## State transitions and historical versus current validity

Draft/blocked/ready_to_submit -> awaiting_review on existing controlled submission.
An effective approve leaves the current stage partial until its distinct quorum is
satisfied. A completed stage activates exactly one successor. The overall request
is partially_approved until every mandatory stage passed. Only then is one immutable
final authorization created and historical state set approved.

Any authorized reject at the active stage terminates the request as rejected; return
terminates it as returned_for_revision. Later stages are cancelled, completed prior
stages and all votes remain historical, and activities are archived. No majority-vote
exception or vote carry-forward is implemented. Rework creates a new source-bound
version linked to the terminal predecessor, with no inherited votes. Original reject,
return and approved historical states are retained.

Approved history remains approved after expiry/invalidation. current_validity is
separate from that history. Protected getters evaluate time and current evidence on
every call; they do not depend on cron. Authorized revalidation can persist expiry or
invalidation, archive obsolete activities and append audit evidence. Explicit
invalidation requires published company governance authority and a reason.

## Decision identity, order and quorum

The real acting user is always env.user. A caller cannot supply reviewer_id or an
actor identity. Request maker, creator, submitter and configured PR19 source
contributors are excluded, even with multiple manager roles. UID1 is never a fallback
reviewer. An actual user and a represented principal cannot be reused to satisfy
independent slots. Database uniqueness backs both identities per request version.
A duplicate or conflicting retry returns a controlled ALREADY_DECIDED error, with
no new vote, stage activation, final artifact or activity.

Only the first uncompleted mandatory stage is active. The engine reconciles every
stage to its frozen code, sequence, groups, candidates, assignments, plan and positive
quorum. It reconstructs current valid approvals from immutable decision rows, not
mail, comments or activity completion. A stored stage status cannot substitute for
its decision chain. Missing/zero/inconsistent quorum or stage skipping fails closed.

## Financial, policy and exact payload revalidation

Before every decision, use current PR16 reconciliation and P0 controls, current
PR14/15 values, exact PR17 assumptions/results and relevant PR18 option eligibility.
Compare source, submitted package, decision policy and exact commercial payload
fingerprints. Recheck actor and assigned reviewer role, activity, company and native
source access under locks. Repeat source/proof validation at final authorization.
Changed109/112 assumptions cannot use one another's submitted votes. Stale findings
create retained blockers and invalidate current review; immutable evidence survives.

The subject includes company/vendor/revision/batch/file SHA, exact source commercial
row versions/snapshots (product/currency/UoM/quantity tier/effective dates), source
references, selected scenario assumptions and recommendation option. Original CSV
prices are provenance and cannot override a negotiated scenario. Four review types
remain distinct. Approval is internal authorization, not external acceptance.

A controlled review_display_note is the explicitly cosmetic field. Its edits are
audited and do not change commercial payload fingerprints. Commercial source fields,
financial versions, mapping, native pricing basis and governed policy remain material.
Unrelated arbitrary native metadata is not silently declared cosmetic.

## Delegation

Delegation is opt-in, exact request/stage/type/company/role scoped and time-bound.
The assigned principal proposes; a separately configured independent governance user
authorizes. Proposed records provide no authority. Both principal and delegate must
have current independent role/company/source eligibility. The delegate must be a
frozen candidate, meet named constraints and have no other reserved slot. One active
delegation per principal slot and per delegate/request prevents artificial quorum.
No sudo impersonation is used in eligibility/decisions.

Delegation provides an alternative eligible actor for one slot; it does not add an
extra vote. Principal and delegate cannot both consume that slot. Both represented
and authenticated identities are considered for global independence. Windows are
UTC [start,end), with actual authorization time retained. Revocation stops future
use. Past valid votes retain their original authorization snapshot and are not erased
merely because delegation was later revoked; current actor role/company/source
eligibility is still rechecked before final/current authorization.

## Approval time rules

Odoo datetime fields store naive UTC instants. Review deadline is submitted_at plus
explicit hours. Elapsed-day validity is approved_at plus24-hour days. Date validity
ends at exclusive next local midnight in the policy IANA timezone, converted to UTC.
Ambiguous/nonexistent local expiry boundaries are rejected instead of guessed.
Exact end is expired; start is included. There is no automatic reactivation or
extension. A new governed authorization/version is needed after invalidity.

## Activities and evidence security

Only explicit policy-enabled internal review activities are created. Each current
unvoted principal and eligible authorized alternative can receive a generic reference
activity. Existing rows are retained and archived on vote/terminal transitions; next
stage activities are created once under the same request lock. Native quick-update
suppresses assignment email. Direct activity target/context forgery remains denied.
Activity completion never creates a decision.

Supporting documents must be private binary attachments of the exact request and
company, with no public flag or access token. Metadata-only identification extends
the existing supplier-source attachment guard; actual content/stream/read/export
permission uses the original user. Files cannot be replaced, reassigned, copied,
deleted or publicly shared. Decision rows freeze selected document checksum/size
references; further unrelated attachments cannot change a recorded decision.

All new decision, authorization and delegation models inherit immutable review guards
and active-selected-company plus exact source warehouse/native-order rules. Auditor
is read-only; pure sales/purchase and portal/public gain no cost visibility. Input
wizards are creator-bound and expose no analytical source traversal/export surface.

## Atomicity, concurrency and recovery

Company, batch, request and relevant user/group rows serialize workflow changes.
Source collectors retain their existing source locks. Database uniqueness protects
one represented slot, one actual actor and one final artifact per request version.
Decision, stage/request changes, activities, final evidence and audit are inside
savepoints. Failures do not leave a submitted-looking partial decision. Serialization
conflicts require a fresh transaction retry, never an arbitrary business-method
commit. P0 provides single-request actions, not bulk approval.

## PR21 handoff

Use get_current_approval(), not state == approved. The immutable artifact identifies
request/version/company/type, exact commercial payload and fingerprints, source
reconciliation/evidence, policy/version, complete decisions and quorums, maker-checker
basis, approved/valid instants and original stage route. PR21 must independently
recheck current validity and source/payload/company/type, normalize currency/UoM/MOQ/
effective dates, verify any required supplier/customer consent, run its dry-run and
scope checks, provide application idempotency/concurrency/rollback and retain before/
after audit. PR20 has no application method or job.

## Verification status

PR20 VERIFIED for the documented approval-only scope. Actual source-bound runtime gates, failure history, measured100/500 cycles and seeded2000-header/10000-decision workload, actual PR19 upgrade preservation and limitations are in TEST_REPORT.json.pr20_handoff and evidence/DEV-10-pr20-summary.md. Browser UAT/FULL release NOT_RUN; production capacity NOT_MEASURED.
STOP after PR20; PR21 NOT_STARTED.


### PR19 hash encoding compatibility

PR19 hashes pre-JSON source packages. Odoo's JSON encoder formats datetime values
at second resolution, while the original digest's str(datetime) retains SQL
microseconds. PR20 preserves the original evidence and hashes: it reconstructs
current raw source data with the frozen route, proves the original source/package/
evidence digests, then compares its exact native JSON encoding to stored evidence.
A separate stored-JSON hash is frozen for decision-enabled submissions. Many2many
membership order may differ after a native cache reload; only identical membership
sets can be represented in their original signed order, and all original hashes must
still verify. Configured stage order is never sorted or weakened. No old hash or
stored evidence is silently rewritten.
