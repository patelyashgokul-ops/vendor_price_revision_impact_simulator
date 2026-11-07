"""PR20 controlled decisions. APPROVED never means operationally APPLIED."""
import json
from datetime import timedelta
from odoo import api, fields, models, Command
from odoo.exceptions import AccessError, UserError, ValidationError
from .approval import (HEADER, STAGE, EVIDENCE, EVENT, ISSUE, SOURCE_FIELDS,
                       ACTIVITY_TOKEN, authority, INACTIVE)
from .import_validation import PREFIX as IMPORT_PREFIX, ImmutableReview
from .approval_engine import MODULE
from .approval_decision_math import within, expiry
from .scenario_math import text
from .structural_validation import digest

DECISION = 'vendor.price.revision.approval.decision'
AUTHORIZATION = 'vendor.price.revision.approval.authorization'
DELEGATION = 'vendor.price.revision.approval.delegation'
PENDING = ('awaiting_review', 'partially_approved')
NEW_TERMINAL = ('returned_for_revision', 'rejected', 'approval_expired', 'approval_invalidated')
DECISION_TYPES = [('approve', 'Approve'), ('reject', 'Reject'), ('return', 'Return for Revision')]
CONTRACT = 'pr20_exact_payload_distinct_actor_and_principal_no_application_v1'


class DecisionEvidenceChanged(UserError):
    def __init__(self, message, expired=False):
        super().__init__(message)
        self.expired = expired


def safe_json(value):
    return json.loads(json.dumps(value, default=str, sort_keys=True))


class ApprovalDecision(models.Model):
    _name = DECISION
    _inherit = IMPORT_PREFIX + 'review.guard'
    _description = 'Immutable Authenticated Management Decision'
    _order = 'id'
    _principal = models.Constraint('UNIQUE(request_id,reviewer_id)', 'A represented reviewer can decide only once in a request version.')
    _actor = models.Constraint('UNIQUE(request_id,acting_user_id)', 'One authenticated person cannot satisfy independent review slots.')
    request_id = fields.Many2one(HEADER, required=True, ondelete='restrict', index=True)
    stage_id = fields.Many2one(STAGE, required=True, ondelete='restrict', index=True)
    decision_type = fields.Selection(DECISION_TYPES, required=True)
    reviewer_id = fields.Many2one('res.users', required=True, string='Assigned principal')
    acting_user_id = fields.Many2one('res.users', required=True, string='Authenticated decision actor')
    delegation_id = fields.Many2one(DELEGATION, ondelete='restrict')
    decided_at = fields.Datetime(required=True)
    reason = fields.Text()
    evidence_reference = fields.Text()
    attachment_ids = fields.Many2many('ir.attachment', relation='vpr_decision_attachment_rel')
    source_fingerprint = fields.Char(required=True)
    submission_fingerprint = fields.Char(required=True)
    policy_version = fields.Char(required=True)
    request_version = fields.Integer(required=True)
    stage_sequence = fields.Integer(required=True)
    evidence = fields.Json(required=True)
    fingerprint = fields.Char(required=True)
    resulting_stage_status = fields.Char(required=True)


class ApprovalAuthorization(models.Model):
    _name = AUTHORIZATION
    _inherit = IMPORT_PREFIX + 'review.guard'
    _description = 'Immutable Exact Management Authorization - NOT Price Application'
    _one = models.Constraint('UNIQUE(request_id)', 'Only one final authorization exists for an immutable request version.')
    request_id = fields.Many2one(HEADER, required=True, ondelete='restrict', index=True)
    approved_at = fields.Datetime(required=True)
    final_actor_id = fields.Many2one('res.users', required=True)
    valid_from = fields.Datetime(required=True)
    valid_until = fields.Datetime()
    request_type = fields.Char(required=True)
    policy_version = fields.Char(required=True)
    source_fingerprint = fields.Char(required=True)
    submission_fingerprint = fields.Char(required=True)
    payload_fingerprint = fields.Char(required=True)
    decision_ids = fields.Many2many(DECISION, relation='vpr_authorization_decision_rel')
    evidence = fields.Json(required=True)
    fingerprint = fields.Char(required=True)


class DecisionRequest(models.Model):
    _inherit = HEADER
    _description = 'Management Approval Request and Historical Authorization'
    state = fields.Selection([(v, v.replace('_', ' ').title()) for v in
        ('draft', 'ready_to_submit', 'blocked') + PENDING + INACTIVE + NEW_TERMINAL + ('approved',)], required=True, default='draft', index=True)
    decision_ids = fields.One2many(DECISION, 'request_id')
    delegation_ids = fields.One2many(DELEGATION, 'request_id')
    authorization_id = fields.Many2one(AUTHORIZATION, ondelete='restrict')
    decision_policy = fields.Json()
    decision_policy_fingerprint = fields.Char()
    decision_evidence_fingerprint = fields.Char(string='Stored submitted JSON integrity fingerprint')
    submitted_payload = fields.Json()
    payload_fingerprint = fields.Char()
    review_deadline = fields.Datetime()
    approved_at = fields.Datetime()
    approved_by = fields.Many2one('res.users')
    approval_valid_from = fields.Datetime()
    approval_valid_until = fields.Datetime()
    approval_invalidated_at = fields.Datetime()
    approval_expired_at = fields.Datetime()
    approval_invalidation_reason = fields.Text()
    superseded_by_id = fields.Many2one(HEADER, ondelete='restrict')
    current_validity = fields.Char(compute='_compute_validity20')
    can_decide = fields.Boolean(compute='_can_decide20')
    review_display_note = fields.Text(string='Internal display note (not commercial terms)')

    def _lock20(self):
        self._lock()
        self.invalidate_recordset()
        self.stage_ids.invalidate_recordset()

    def _payload20(self, engine):
        rows = self.batch_id.row_ids.filtered(lambda r: not r.excluded and r.commercial_result_id)
        if len(rows) > 10000:
            raise UserError('Narrow the governed proposal; exact authorization is bounded to10000 source rows.')
        return safe_json(dict(contract=CONTRACT, company_id=self.company_id.id,
            vendor_id=self.batch_id.vendor_id.id, revision_id=self.batch_id.revision_id.id,
            batch_id=self.batch_id.id, file_sha256=self.batch_id.sha256_digest,
            request_type=self.request_type, baseline_id=self.baseline_id.id,
            scenario_id=self.scenario_id.id or None, recommendation_id=self.recommendation_id.id or None,
            option_id=self.option_id.id or None, source_refs=engine.source_refs,
            source_rows=[dict(row_id=r.id, commercial_result_id=r.commercial_result_id.id,
                commercial_version=r.commercial_result_id.version, snapshot=r.commercial_result_id.snapshot) for r in rows],
            scenario_assumptions=engine.package['scenario_assumptions'],
            recommendation_option=engine.package['recommendation_option'],
            interpretation='Source rows are provenance, not permission to substitute original proposed prices for approved scenario assumptions. Supplier/customer acceptance and PR21 validation remain separate.',
            permitted_subject=self.request_type, applied=False))

    def action_submit_for_review(self):
        if self.state in ('partially_approved', 'approved'):
            raise UserError('This version has already entered decision execution; it cannot be submitted again.')
        with self.env.cr.savepoint():
            result = super().action_submit_for_review()
            if self.policy_id.decision_enabled and not self.decision_policy_fingerprint:
                engine = self._builder(route=False)
                snapshot = safe_json(engine.policy._decision_snapshot())
                payload = self._payload20(engine)
                deadline = self.submitted_at + timedelta(hours=engine.policy.decision_review_hours) if engine.policy.decision_review_hours else False
                self._update(dict(decision_policy=snapshot, decision_policy_fingerprint=digest(snapshot),
                    decision_evidence_fingerprint=digest(self.evidence_id.data),
                    submitted_payload=payload, payload_fingerprint=digest(payload), review_deadline=deadline))
                self._event('decision_contract_frozen', 'Exact commercial subject and explicit decision policy frozen; nothing applied',
                    dict(payload_fingerprint=self.payload_fingerprint, policy_fingerprint=self.decision_policy_fingerprint), self.state)
        return result

    def _source20(self):
        self.ensure_one(); self.check_access('read')
        if self.state not in PENDING + ('approved',):
            raise UserError('This request version is not active for review or final authorization.')
        engine = self._builder(route=False)
        data = self.evidence_id.data
        if not data or self.evidence_id.request_id != self or self.evidence_id.batch_id != self.batch_id:
            raise UserError('Submitted evidence integrity failed.')
        # Many2many membership is a set. Native cache and SQL reload can expose
        # different iteration orders. Preserve the exact original signed order
        # only after proving the current membership is identical; all original
        # hashes and JSON bytes must still verify below.
        frozen_policy = data.get('policy', {})
        for name, field in engine.policy._fields.items():
            if field.type == 'many2many' and name in engine.package['policy'] and name in frozen_policy:
                current_ids = engine.package['policy'][name]
                frozen_ids = frozen_policy[name]
                if set(current_ids or []) == set(frozen_ids or []):
                    engine.package['policy'][name] = frozen_ids
        engine.source_fingerprint = digest(engine.package)
        if engine.source_fingerprint != self.source_fingerprint or self.currency_id != self.company_id.currency_id:
            raise UserError('Submitted source/policy changed; a new financial package and routing are required.')
        # PR19 hashes its pre-JSON package. Native Odoo JSON converts datetime
        # objects to second-resolution strings, while digest(default=str) retains
        # SQL microseconds. Preserve both original bytes and original hashes:
        # reconstruct and verify their raw source contract, then compare the
        # exact native JSON encoding instead of pretending the two encodings match.
        package = dict(engine.package, route=data.get('route', []))
        original = dict(package, activities=data.get('activities', []))
        if digest(package) != self.submission_fingerprint or digest(original) != self.evidence_id.fingerprint:
            raise UserError('Submitted routing package differs from its immutable fingerprint.')
        native_json = self.evidence_id._fields['data'].convert_to_cache(original, self.evidence_id)
        if native_json != data or (self.decision_evidence_fingerprint and digest(data) != self.decision_evidence_fingerprint):
            raise UserError('Stored submitted JSON differs from its original verified source encoding.')
        route = data.get('route', [])
        stages = self.stage_ids.sorted('sequence')
        if len(route) != len(stages) or not stages or len(stages) > 32:
            raise UserError('Mandatory route stages are missing or duplicated.')
        used = set()
        for index, (stage, spec) in enumerate(zip(stages, route), 1):
            groups = self.env['res.groups'].concat([self.env.ref(MODULE + role) for role in spec['roles']])
            if (stage.sequence != index or stage.code != spec['code'] or stage.plan != spec or
                    stage.quorum <= 0 or stage.quorum != spec['quorum'] or
                    set(stage.assigned_ids.ids) != set(spec['assigned']) or
                    set(stage.candidate_ids.ids) != set(spec['candidates']) or set(stage.required_group_ids.ids) != set(groups.ids) or
                    len(stage.assigned_ids) != stage.quorum):
                raise UserError('Frozen stage authority/quorum does not match the submitted route.')
            for user in stage.assigned_ids:
                if user.id in used or not engine.eligible(user, spec['roles']):
                    raise UserError('An independent assigned reviewer lost current company, role or source eligibility.')
                used.add(user.id)
        return engine

    def get_current_request(self):
        self._source20()
        return self

    def _contract20(self):
        engine = self._source20()
        if not engine.policy.decision_enabled or not self.decision_policy_fingerprint or not self.decision_evidence_fingerprint:
            raise UserError('Decision execution was not explicitly enabled and frozen for this request version. Prepare a governed new version.')
        policy = safe_json(engine.policy._decision_snapshot())
        if digest(policy) != self.decision_policy_fingerprint or policy != self.decision_policy:
            raise UserError('Decision policy changed; reauthorization requires a new version.')
        if not self.submitted_payload or digest(self.submitted_payload) != self.payload_fingerprint or self._payload20(engine) != self.submitted_payload:
            raise UserError('The exact commercial payload changed; old votes cannot authorize different pricing.')
        return engine

    def _governance20(self):
        authority(self.env); self.check_access('read')
        policy = self.policy_id or self.env['vendor.price.revision.config'].get_company_revision_config(self.company_id, fields.Date.today())
        groups = policy.decision_governance_group_ids
        if not groups or not any(self.env.user.has_group(g.get_external_id()[g.id]) for g in groups):
            raise AccessError('Explicit company governance authority is required.')
        return policy

    def _archive20(self, stages):
        stages.activity_ids.with_context(_vpr_approval_activity=ACTIVITY_TOKEN, mail_activity_quick_update=True).write({'active': False})

    def _issue20(self, message, event='decision_blocked'):
        self.env[ISSUE]._record(dict(batch_id=self.batch_id.id, request_id=self.id,
            code=event.upper(), severity='critical', description=message,
            resolution='Correct exact source/policy/eligibility; prepare a new governed request version. Historical votes never transfer.',
            actor_id=self.env.uid, recorded_at=fields.Datetime.now()))
        self._event(event, message, {}, self.state)

    def _invalidate20(self, reason, expired=False):
        now = fields.Datetime.now()
        if self.state == 'approved':
            if self.approval_invalidated_at or self.approval_expired_at:
                return
            values = {'approval_expired_at': now} if expired else {'approval_invalidated_at': now}
            values.update(active_key=False, approval_invalidation_reason=reason)
            self._update(values)
            self._event('approval_expired' if expired else 'approval_invalidated', reason,
                dict(authorization_id=self.authorization_id.id), self.state)
        else:
            state = 'approval_expired' if expired else 'approval_invalidated'
            for stage in self.stage_ids.filtered(lambda s: s.stage_status != 'approved'):
                stage._update({'stage_status': 'invalidated'})
            self._update(dict(state=state, active_key=False, approval_invalidation_reason=reason,
                              approval_invalidated_at=now if not expired else False,
                              approval_expired_at=now if expired else False))
            self._event(state, reason, {}, state)
        self._archive20(self.stage_ids)

    def write(self, values):
        if set(values) == {'review_display_note'}:
            authority(self.env)
            for request in self:
                request._lock20()
                if request.requested_by != self.env.user:
                    request._governance20()
                note = values['review_display_note'] or ''
                if not isinstance(note, str) or len(note) > 4000:
                    raise ValidationError('A display note is at most4000 characters and cannot contain commercial authority fields.')
                before = request.review_display_note
                request._update(values)
                request._event('display_note_changed', 'Cosmetic note only; no price or authority changed', dict(before=before, after=note), request.state)
            return True
        return super().write(values)

    def _lock_people20(self, extra=()):
        ids = sorted(set(self.stage_ids.assigned_ids.ids + list(extra) + self.decision_ids.acting_user_id.ids))
        if ids:
            self.env.cr.execute('SELECT id FROM res_users WHERE id IN %s ORDER BY id FOR SHARE', [tuple(ids)])
        groups = self.env['res.groups'].concat([self.env.ref(MODULE + r) for r in ('group_vpr_purchase_manager', 'group_vpr_sales_manager', 'group_vpr_finance_manager', 'group_vpr_director')])
        self.env.cr.execute('SELECT id FROM res_groups WHERE id IN %s ORDER BY id FOR SHARE', [tuple(sorted(groups.ids))])

    def _votes20(self):
        return self.env[DECISION].search([('request_id', '=', self.id)], order='id')

    def _active_stage20(self):
        for stage in self.stage_ids.sorted('sequence'):
            if stage.stage_status != 'approved':
                if stage.stage_status not in ('ready_for_review', 'partially_approved'):
                    raise UserError('The next mandatory stage is not active; it cannot be skipped.')
                return stage
        raise UserError('No active mandatory stage remains.')

    def _attachments20(self, ids):
        if not isinstance(ids, list) or len(ids) > 20 or any(type(i) is not int or i <= 0 for i in ids) or len(set(ids)) != len(ids):
            raise ValidationError('Provide at most20 distinct exact supporting attachment IDs.')
        files = self.env['ir.attachment'].browse(sorted(ids)).exists()
        if len(files) != len(ids):
            raise AccessError('Supporting evidence is missing or unavailable.')
        files.check_access('read')
        data = []
        for file in files:
            if file.public or file.access_token or file.type != 'binary' or file.res_model != HEADER or file.res_id != self.id or file.company_id != self.company_id:
                raise AccessError('Decision documents must be private immutable binary attachments of this exact company request.')
            data.append(dict(id=file.id, checksum=file.checksum, file_size=file.file_size, company_id=file.company_id.id,
                             res_model=file.res_model, res_id=file.res_id))
        return files, data

    def _actor20(self, engine, stage, delegation_id=None):
        actor = self.env.user
        authority(self.env)
        if actor.id in engine.excluded or not engine.eligible(actor, stage.plan['roles']):
            raise AccessError('MAKER_CHECKER_CONFLICT: current independent actor/company/role/source eligibility required.')
        delegation = self.env[DELEGATION]
        principal = actor
        if delegation_id:
            if type(delegation_id) is not int:
                raise ValidationError('Use an exact delegation ID, never another reviewer identity.')
            delegation = self.env[DELEGATION].browse(delegation_id).exists()
            delegation.check_access('read')
            if not delegation or delegation.request_id != self or delegation.stage_id != stage or delegation.delegate_id != actor:
                raise AccessError('Delegation must identify this authenticated actor and exact request/stage.')
            delegation._check20(engine, fields.Datetime.now(), current=True)
            principal = delegation.principal_id
            if actor in self.stage_ids.assigned_ids:
                raise AccessError('A delegate cannot consume another independently reserved reviewer slot.')
        if principal not in stage.assigned_ids:
            raise AccessError('Only the assigned principal or an explicitly authorized eligible delegate may decide.')
        if principal.id in engine.excluded or not engine.eligible(principal, stage.plan['roles']):
            raise AccessError('The represented principal must remain independently eligible.')
        if principal in self._votes20().reviewer_id:
            raise UserError('ALREADY_DECIDED: this represented slot already has an immutable decision.')
        return actor, principal, delegation

    def _proof20(self, engine):
        votes = self._votes20(); used = set(); by_stage = {s.id: [] for s in self.stage_ids}
        for vote in votes:
            stage = vote.stage_id
            if stage.id not in by_stage or vote.batch_id != self.batch_id or vote.request_version != self.version or vote.stage_sequence != stage.sequence:
                raise UserError('Decision references an incompatible request/stage/version.')
            if vote.fingerprint != digest(vote.evidence) or vote.source_fingerprint != self.source_fingerprint or vote.submission_fingerprint != self.submission_fingerprint:
                raise UserError('Immutable decision evidence/source integrity failed.')
            evidence = vote.evidence
            if (evidence.get('actor_id') != vote.acting_user_id.id or evidence.get('principal_id') != vote.reviewer_id.id or
                    evidence.get('decision_type') != vote.decision_type or evidence.get('stage_id') != stage.id or
                    evidence.get('policy_fingerprint') != self.decision_policy_fingerprint or
                    evidence.get('stage_plan_fingerprint') != digest(stage.plan)):
                raise UserError('Decision identity or policy does not match its immutable evidence.')
            identities = {vote.reviewer_id.id, vote.acting_user_id.id}
            if used & identities or identities & engine.excluded or vote.reviewer_id not in stage.assigned_ids:
                raise UserError('Decision chain violates independent actor/principal or maker-checker requirements.')
            for user in vote.reviewer_id | vote.acting_user_id:
                if not engine.eligible(user, stage.plan['roles']):
                    raise UserError('A prior voting identity lost current required eligibility; fresh review is required.')
            if vote.delegation_id:
                vote.delegation_id._check20(engine, vote.decided_at, current=False, decision=vote)
                if evidence.get('delegation') != vote.delegation_id._snapshot20(at_decision=True):
                    raise UserError('Delegated decision does not retain its exact authorized scope.')
            elif vote.reviewer_id != vote.acting_user_id:
                raise UserError('Unexplained reviewer impersonation is not a decision.')
            _, attachments = self._attachments20(vote.attachment_ids.ids)
            if attachments != evidence.get('attachments', []):
                raise UserError('Supporting decision documents changed.')
            used.update(identities); by_stage[stage.id].append(vote)
        incomplete = False
        for stage in self.stage_ids.sorted('sequence'):
            stage_votes = by_stage[stage.id]
            if len(stage_votes) > stage.quorum or any(v.decision_type != 'approve' for v in stage_votes):
                raise UserError('A conflicting/terminal decision cannot satisfy an approval quorum.')
            if stage_votes and incomplete:
                raise UserError('A later stage contains a vote before all predecessors passed.')
            count = len(stage_votes)
            if count == stage.quorum:
                if stage.stage_status != 'approved':
                    raise UserError('Satisfied quorum and stage state disagree.')
            else:
                incomplete = True
                expected = 'partially_approved' if count else 'waiting_predecessor'
                if stage == self.stage_ids.sorted('sequence').filtered(lambda s: s.stage_status != 'approved')[:1]:
                    expected = 'partially_approved' if count else 'ready_for_review'
                if stage.stage_status != expected:
                    raise UserError('The sequential stage state is inconsistent with its decision count.')
        return votes, by_stage

    def _sync_activities20(self, engine):
        if not self.policy_id.workflow_activities:
            return
        if self.state not in PENDING:
            self._archive20(self.stage_ids); return
        active = self._active_stage20()
        voted = set(self._votes20().filtered(lambda v: v.stage_id == active).reviewer_id.ids)
        desired = set(active.assigned_ids.ids) - voted
        for delegation in self.delegation_ids.filtered(lambda d: d.stage_id == active and d.principal_id.id not in voted and d.state == 'active'):
            try:
                delegation._check20(engine, fields.Datetime.now(), current=True)
            except (AccessError, UserError, ValidationError):
                continue
            desired.add(delegation.delegate_id.id)
        for stage in self.stage_ids:
            for activity in stage.activity_ids.filtered('active'):
                if stage != active or activity.user_id.id not in desired:
                    activity.with_context(_vpr_approval_activity=ACTIVITY_TOKEN, mail_activity_quick_update=True).write({'active': False})
        existing = set(active.activity_ids.filtered('active').user_id.ids)
        for uid in sorted(desired - existing):
            activity = self.env['mail.activity'].with_context(_vpr_approval_activity=ACTIVITY_TOKEN, mail_activity_quick_update=True).create(dict(
                res_model_id=self.env['ir.model']._get_id(HEADER), res_id=self.id,
                activity_type_id=self.env.ref('mail.mail_activity_data_todo').id, user_id=uid,
                summary='Management approval review: ' + self.name,
                note='Open the authorized request to record a decision. Activity completion is not approval; prices are not applied.',
                date_deadline=fields.Date.today() + timedelta(days=self.policy_id.workflow_due_days)))
            active._update({'activity_ids': [Command.link(activity.id)]})

    def _finish20(self):
        try:
            engine = self._contract20()  # independent final-stage revalidation
            votes, by_stage = self._proof20(engine)
        except (UserError, ValidationError) as exc:
            raise DecisionEvidenceChanged(str(exc)) from exc
        if any(s.stage_status != 'approved' or len(by_stage[s.id]) != s.quorum for s in self.stage_ids):
            raise UserError('Every mandatory stage and distinct-person quorum must pass before final authorization.')
        now = fields.Datetime.now()
        if self.review_deadline and not within(now, self.submitted_at, self.review_deadline):
            raise DecisionEvidenceChanged('Review window expired before final authorization.', expired=True)
        policy = self.decision_policy
        end = expiry(now, policy['decision_validity_mode'], policy['decision_valid_days'],
                     fields.Date.to_date(policy['decision_valid_date']) if policy['decision_valid_date'] else None,
                     policy['decision_timezone'] or None)
        if end and end <= now:
            raise DecisionEvidenceChanged('The configured final approval validity has already ended.', expired=True)
        data = safe_json(dict(contract=CONTRACT, request_id=self.id, request_version=self.version,
            company_id=self.company_id.id, request_type=self.request_type, approved_at=now,
            final_actor_id=self.env.uid, valid_from=now, valid_until=end,
            payload=self.submitted_payload, payload_fingerprint=self.payload_fingerprint,
            source_fingerprint=self.source_fingerprint, submission_fingerprint=self.submission_fingerprint,
            financial_reconciliation_id=self.baseline_id.id, evidence_id=self.evidence_id.id,
            evidence_fingerprint=self.evidence_id.fingerprint, policy_id=self.policy_id.id,
            policy_version=self.policy_version, decision_policy=self.decision_policy,
            decision_ids=votes.ids, decision_fingerprints={str(v.id): v.fingerprint for v in votes},
            route=self.evidence_id.data['route'], exclusion_ids=sorted(engine.excluded),
            meaning='Internal management authorization for the exact subject only. Not supplier/customer acceptance and NOT price application. PR21 must perform its separate dry-run, consent, scope, idempotency and transaction checks.'))
        artifact = self.env[AUTHORIZATION]._record(dict(batch_id=self.batch_id.id, request_id=self.id,
            approved_at=now, final_actor_id=self.env.uid, valid_from=now, valid_until=end or False,
            request_type=self.request_type, policy_version=self.policy_version,
            source_fingerprint=self.source_fingerprint, submission_fingerprint=self.submission_fingerprint,
            payload_fingerprint=self.payload_fingerprint, decision_ids=[Command.set(votes.ids)], evidence=data, fingerprint=digest(data)))
        self._update(dict(state='approved', authorization_id=artifact.id, approved_at=now,
            approved_by=self.env.uid, approval_valid_from=now, approval_valid_until=end or False))
        self._archive20(self.stage_ids)
        self._event('final_management_authorization', 'All exact mandatory stages/quorums completed; APPROVED DOES NOT MEAN APPLIED',
            dict(authorization_id=artifact.id, fingerprint=artifact.fingerprint, decision_ids=votes.ids), 'approved')

    def _decide20(self, kind, reason='', evidence_reference='', stage_id=None, delegation_id=None, attachment_ids=None):
        self.ensure_one(); self._lock20(); authority(self.env)
        if kind not in dict(DECISION_TYPES):
            raise ValidationError('Select an explicit supported decision.')
        if self.env.user in (self.maker_id | self.requested_by | self.submitted_by):
            raise AccessError('Maker, request creator and submitter cannot decide their own request.')
        if self._votes20().filtered(lambda d: d.acting_user_id == self.env.user):
            raise UserError('ALREADY_DECIDED: the authenticated person has an immutable decision; no duplicate/conflicting vote was recorded.')
        if self.state not in PENDING:
            raise UserError('This request is not awaiting a decision. Terminal history cannot be resumed.')
        if not self.decision_policy_fingerprint or not self.policy_id.decision_enabled:
            raise UserError('Decision execution is not enabled for this routing-only version; prepare a governed new submission.')
        self._lock_people20([self.env.uid])
        try:
            engine = self._contract20()
            now = fields.Datetime.now()
            if self.review_deadline and not within(now, self.submitted_at, self.review_deadline):
                self._issue20('The explicit review window expired.', 'review_expired')
                self._invalidate20('The explicit review window expired.', expired=True)
                return False
            self._proof20(engine)
        except (UserError, ValidationError) as exc:
            self._issue20(str(exc)); self._invalidate20(str(exc)); return False
        stage = self._active_stage20()
        if stage_id is not None and (type(stage_id) is not int or stage_id != stage.id):
            raise AccessError('Only the exact current mandatory stage may be decided; later stages cannot be skipped.')
        actor, principal, delegation = self._actor20(engine, stage, delegation_id)
        used = set(self._votes20().reviewer_id.ids + self._votes20().acting_user_id.ids)
        if {actor.id, principal.id} & used:
            raise AccessError('Independent reviewer identities cannot be reused across slots or stages.')
        if kind != 'approve' or self.decision_policy['decision_require_reason']:
            text(reason, 'Decision justification')
        if not isinstance(reason, str) or not isinstance(evidence_reference, str) or len(reason) > 8000 or len(evidence_reference) > 4000:
            raise ValidationError('Bound plain decision reason/evidence reference required.')
        files, file_data = self._attachments20(attachment_ids or [])
        with self.env.cr.savepoint():
            count = len(self._votes20().filtered(lambda d: d.stage_id == stage and d.decision_type == 'approve')) + (kind == 'approve')
            status = ('approved' if count == stage.quorum else 'partially_approved') if kind == 'approve' else ('rejected' if kind == 'reject' else 'returned')
            data = safe_json(dict(contract=CONTRACT, request_id=self.id, request_version=self.version, stage_id=stage.id,
                stage_sequence=stage.sequence, decision_type=kind, actor_id=actor.id, principal_id=principal.id,
                decided_at=now, reason=reason, evidence_reference=evidence_reference, attachments=file_data,
                source_fingerprint=self.source_fingerprint, submission_fingerprint=self.submission_fingerprint,
                policy_fingerprint=self.decision_policy_fingerprint, evidence_id=self.evidence_id.id,
                evidence_fingerprint=self.evidence_id.fingerprint, policy_version=self.policy_version,
                stage_plan_fingerprint=digest(stage.plan), excluded_reviewers=sorted(engine.excluded),
                delegation=delegation._snapshot20(at_decision=True) if delegation else None))
            decision = self.env[DECISION]._record(dict(batch_id=self.batch_id.id, request_id=self.id, stage_id=stage.id,
                decision_type=kind, reviewer_id=principal.id, acting_user_id=actor.id, delegation_id=delegation.id or False,
                decided_at=now, reason=reason, evidence_reference=evidence_reference, attachment_ids=[Command.set(files.ids)],
                source_fingerprint=self.source_fingerprint, submission_fingerprint=self.submission_fingerprint,
                policy_version=self.policy_version, request_version=self.version, stage_sequence=stage.sequence,
                evidence=data, fingerprint=digest(data), resulting_stage_status=status))
            stage._update({'stage_status': status})
            if kind != 'approve':
                state = 'rejected' if kind == 'reject' else 'returned_for_revision'
                for pending in self.stage_ids.filtered(lambda s: s != stage and s.stage_status != 'approved'):
                    pending._update({'stage_status': 'cancelled'})
                self._update(dict(state=state, active_key=False))
                self._archive20(self.stage_ids)
                self._event('decision_' + kind, reason, dict(decision_id=decision.id, stage_id=stage.id), state)
            else:
                self._update({'state': 'partially_approved'})
                self._event('decision_approve', reason or 'Approval justification not required by explicit company policy',
                    dict(decision_id=decision.id, stage_id=stage.id), self.state)
                if status == 'approved':
                    self._archive20(stage)
                    following = self.stage_ids.filtered(lambda s: s.sequence == stage.sequence + 1)
                    if following:
                        if following.stage_status != 'waiting_predecessor':
                            raise UserError('Next stage was already activated or is inconsistent.')
                        following._update({'stage_status': 'ready_for_review'})
                        self._event('stage_activated', 'Predecessor distinct quorum completed', dict(stage_id=following.id), self.state)
                    else:
                        self._finish20()
                self._sync_activities20(engine)
        return decision

    def action_approve(self, reason='', evidence_reference='', stage_id=None, delegation_id=None, attachment_ids=None):
        with self.env.cr.savepoint():
            try:
                return self._decide20('approve', reason, evidence_reference, stage_id, delegation_id, attachment_ids)
            except DecisionEvidenceChanged as exc:
                self._issue20(str(exc)); self._invalidate20(str(exc), expired=exc.expired); return False

    def action_reject(self, reason, evidence_reference='', stage_id=None, delegation_id=None, attachment_ids=None):
        with self.env.cr.savepoint():
            return self._decide20('reject', reason, evidence_reference, stage_id, delegation_id, attachment_ids)

    def action_return_for_revision(self, reason, evidence_reference='', stage_id=None, delegation_id=None, attachment_ids=None):
        with self.env.cr.savepoint():
            return self._decide20('return', reason, evidence_reference, stage_id, delegation_id, attachment_ids)

    def _validity20(self, strict=False):
        if self.state != 'approved':
            if self.state in PENDING:
                if self.review_deadline and fields.Datetime.now() >= self.review_deadline:
                    return 'expired'
                try:
                    self._source20()
                except (AccessError, UserError, ValidationError):
                    return 'invalidated'
                return 'pending' if self.decision_policy_fingerprint else 'decisions_not_enabled'
            return 'expired' if self.state == 'approval_expired' else 'invalidated' if self.state == 'approval_invalidated' else 'not_approved'
        if self.approval_invalidated_at:
            return 'invalidated'
        if self.approval_expired_at or not within(fields.Datetime.now(), self.approval_valid_from, self.approval_valid_until or None):
            return 'expired'
        try:
            engine = self._contract20()
            votes, counts = self._proof20(engine)
            artifact = self.authorization_id
            if (not artifact or artifact.request_id != self or artifact.fingerprint != digest(artifact.evidence) or
                    artifact.payload_fingerprint != self.payload_fingerprint or artifact.source_fingerprint != self.source_fingerprint or
                    artifact.submission_fingerprint != self.submission_fingerprint or artifact.approved_at != self.approved_at or
                    artifact.valid_from != self.approval_valid_from or artifact.valid_until != self.approval_valid_until or
                    set(artifact.decision_ids.ids) != set(votes.ids) or
                    artifact.evidence.get('decision_fingerprints') != {str(v.id): v.fingerprint for v in votes} or
                    any(s.stage_status != 'approved' or len(counts[s.id]) != s.quorum for s in self.stage_ids)):
                raise UserError('Final authorization does not reconcile to exact source, validity and mandatory decision evidence.')
        except (AccessError, UserError, ValidationError):
            if strict:
                raise
            return 'invalidated'
        return 'valid'

    def get_current_approval(self):
        """The sole PR21 read-only handoff. A stored APPROVED flag is insufficient."""
        self.ensure_one(); self.check_access('read')
        if self._validity20(strict=True) != 'valid':
            raise UserError('No current valid final approval authority exists; expiration/invalidation requires fresh authorization.')
        return self.authorization_id

    @api.depends_context('uid', 'allowed_company_ids')
    def _compute_validity20(self):
        for request in self:
            request.current_validity = request._validity20()

    def _effective_state(self):
        for request in self:
            if request.state == 'approved':
                request.current_state = 'approved_' + request._validity20()
            elif request.state in PENDING:
                try:
                    request._source20()
                    request.current_state = request.state if not request.review_deadline or fields.Datetime.now() < request.review_deadline else 'review_expired'
                except (AccessError, UserError, ValidationError):
                    request.current_state = 'stale_or_unauthorized'
            else:
                request.current_state = request.state

    @api.depends_context('uid', 'allowed_company_ids')
    def _can_decide20(self):
        for request in self:
            request.can_decide = False
            if request.state not in PENDING or (request.review_deadline and fields.Datetime.now() >= request.review_deadline):
                continue
            try:
                engine = request._contract20(); stage = request._active_stage20()
                if request._votes20().filtered(lambda v: v.acting_user_id == self.env.user):
                    continue
                if self.env.user in stage.assigned_ids:
                    request._actor20(engine, stage); request.can_decide = True
                else:
                    for delegation in request.delegation_ids.filtered(lambda d: d.stage_id == stage and d.delegate_id == self.env.user and d.state == 'active'):
                        request._actor20(engine, stage, delegation.id); request.can_decide = True; break
            except (AccessError, UserError, ValidationError):
                continue

    def action_revalidate_approval(self):
        self._lock20(); authority(self.env)
        with self.env.cr.savepoint():
            validity = self._validity20()
            if validity in ('expired', 'invalidated') and self.state in PENDING + ('approved',):
                if self.state == 'approved' and ((validity == 'expired' and self.approval_expired_at) or
                                                 (validity == 'invalidated' and self.approval_invalidated_at)):
                    return validity
                self._issue20('Current approval authority is ' + validity, 'authority_' + validity)
                self._invalidate20('Revalidation found ' + validity + ' source/policy/reviewer/time authority.', expired=validity == 'expired')
            elif self.state in PENDING and self.decision_policy_fingerprint:
                engine = self._contract20(); self._sync_activities20(engine)
        return validity

    def action_refresh_readiness(self):
        if self.state in PENDING + ('approved',) and self.decision_policy_fingerprint:
            return self.action_revalidate_approval()
        return super().action_refresh_readiness()

    def action_invalidate_approval(self, reason):
        self._lock20(); self._governance20(); text(reason, 'Governance invalidation reason')
        if self.state not in PENDING + ('approved',):
            raise UserError('Only current pending/final authority may be invalidated.')
        with self.env.cr.savepoint():
            self._invalidate20(reason)
        return self

    def _deactivate(self, state, reason):
        if not self.decision_ids:
            return super()._deactivate(state, reason)
        text(reason, 'Lifecycle reason')
        for stage in self.stage_ids.filtered(lambda s: s.stage_status != 'approved'):
            stage._update({'stage_status': 'cancelled' if state == 'withdrawn' else 'invalidated'})
        self._archive20(self.stage_ids)
        self._event(state, reason, dict(historical_decision_ids=self.decision_ids.ids), state)
        self._update(dict(state=state, active_key=False, stale_reason=reason))

    def action_withdraw_request(self, reason):
        if self.state != 'partially_approved':
            return super().action_withdraw_request(reason)
        self._lock20(); authority(self.env); text(reason, 'Withdrawal reason')
        if self.env.user not in (self.maker_id | self.requested_by | self.submitted_by):
            permitted = any(self.env.user.has_group(MODULE + role) for role in ('group_vpr_purchase_manager', 'group_vpr_finance_manager'))
            if not self.policy_id.workflow_manager_withdrawal or not permitted:
                raise AccessError('Only an authorized source owner or explicitly permitted manager may withdraw pending review.')
        with self.env.cr.savepoint():
            self._deactivate('withdrawn', reason)
        return self

    def action_new_version(self, values, reason):
        if self.state not in NEW_TERMINAL + ('approved',):
            return super().action_new_version(values, reason)
        self._lock20(); authority(self.env); text(reason, 'Governed rework reason')
        if self.state == 'approved':
            validity = self.action_revalidate_approval()
            if validity == 'valid':
                raise UserError('A current valid final authorization must first be explicitly invalidated by company governance.')
        if self.superseded_by_id:
            raise UserError('A governed successor already exists; use that exact version.')
        if not isinstance(values, dict) or set(values) - set(SOURCE_FIELDS):
            raise ValidationError('Provide only explicit current source links and reason.')
        if values.get('request_type', self.request_type) != self.request_type:
            raise ValidationError('A governed successor preserves its commercial review type.')
        source = {k: ((self[k].id or 0) if self._fields[k].type == 'many2one' else self[k]) for k in SOURCE_FIELDS}
        source.update(values, reason=reason)
        with self.env.cr.savepoint():
            successor = self._prepare(source, previous=self)
            if successor.batch_id.revision_id != self.batch_id.revision_id:
                raise AccessError('A successor must preserve the original revision and company.')
            self._update({'superseded_by_id': successor.id})
            self._event('governed_successor_created', reason, dict(successor_id=successor.id, retained_decision_ids=self.decision_ids.ids), self.state)
        return successor

    @api.model
    def action_my_pending_reviews(self):
        assigned = self.env[STAGE].search([('assigned_ids', 'in', [self.env.uid]), ('stage_status', 'in', ['ready_for_review', 'partially_approved']), ('request_id.state', 'in', PENDING)], limit=501)
        delegated = self.env[DELEGATION].search([('delegate_id', '=', self.env.uid), ('state', '=', 'active'), ('stage_id.stage_status', 'in', ['ready_for_review', 'partially_approved']), ('request_id.state', 'in', PENDING)], limit=501).stage_id
        stages = assigned | delegated
        if len(stages) > 500:
            raise UserError('Narrow selected companies; at most500 current stages are evaluated per inbox.')
        eligible = self.env[STAGE]
        for stage in stages:
            if not stage.request_id.decision_policy_fingerprint and self.env.user in stage.assigned_ids:
                try:
                    stage.request_id.get_current_request(); eligible |= stage
                except (AccessError, UserError, ValidationError):
                    pass
            elif stage.request_id.can_decide:
                eligible |= stage
        return dict(type='ir.actions.act_window', name='My Current Approval Reviews', res_model=STAGE, view_mode='list,form', domain=[('id', 'in', eligible.ids)])


class DecisionStage(models.Model):
    _inherit = STAGE
    _description = 'Sequential Management Review Stage and Independent Quorum'
    stage_status = fields.Selection([(v, v.replace('_', ' ').title()) for v in (
        'ready_for_review', 'waiting_predecessor', 'partially_approved', 'approved', 'rejected', 'returned', 'invalidated', 'cancelled')], required=True, index=True)
    decision_ids = fields.One2many(DECISION, 'stage_id')
    activity_ids = fields.Many2many('mail.activity', relation='vpr_ap_stage_activity_rel', context={'active_test': False})
    historical_approval_count = fields.Integer(compute='_counts20')
    current_approval_count = fields.Integer(compute='_counts20')
    remaining_approval_count = fields.Integer(compute='_counts20')

    def _counts20(self):
        cache = {}
        for stage in self:
            request = stage.request_id
            stage.historical_approval_count = len(stage.decision_ids.filtered(lambda v: v.decision_type == 'approve'))
            if request.id not in cache:
                try:
                    engine = request._contract20(); _, counts = request._proof20(engine)
                    cache[request.id] = counts if request._validity20() not in ('expired', 'invalidated') else {}
                except (AccessError, UserError, ValidationError):
                    cache[request.id] = {}
            stage.current_approval_count = len(cache[request.id].get(stage.id, []))
            stage.remaining_approval_count = max(0, stage.quorum - stage.current_approval_count)

    def _effective_status(self):
        for stage in self:
            state = stage.request_id.current_state
            stage.effective_status = stage.stage_status if state in PENDING + ('approved_valid',) else 'historical_' + stage.stage_status


class ApprovalDelegation(models.Model):
    _name = DELEGATION
    _inherit = IMPORT_PREFIX + 'review.guard'
    _description = 'Explicit Stage/Role/Company Time-Bound Review Delegation'
    _slot = models.Constraint('UNIQUE(active_slot)', 'Only one active delegation scope may occupy a principal slot.')
    _actor = models.Constraint('UNIQUE(active_actor_key)', 'A delegate cannot represent independent slots within one request.')
    request_id = fields.Many2one(HEADER, required=True, ondelete='restrict', index=True)
    stage_id = fields.Many2one(STAGE, required=True, ondelete='restrict')
    principal_id = fields.Many2one('res.users', required=True)
    delegate_id = fields.Many2one('res.users', required=True)
    permitted_group_id = fields.Many2one('res.groups', required=True)
    request_type = fields.Char(required=True)
    effective_from = fields.Datetime(required=True)
    effective_until = fields.Datetime(required=True)
    reason = fields.Text(required=True)
    proposed_by = fields.Many2one('res.users', required=True)
    proposed_at = fields.Datetime(required=True)
    authorized_by = fields.Many2one('res.users')
    authorized_at = fields.Datetime()
    revoked_by = fields.Many2one('res.users')
    revoked_at = fields.Datetime()
    revocation_reason = fields.Text()
    revocation_decision_ids = fields.Many2many(DECISION, relation='vpr_delegation_prior_vote_rel', string='Votes already persisted before revocation')
    state = fields.Selection([('proposed', 'Proposed'), ('active', 'Authorized'), ('revoked', 'Revoked')], required=True)
    policy_fingerprint = fields.Char(required=True)
    active_slot = fields.Char()
    active_actor_key = fields.Char()

    def _update20(self, values):
        self.check_access('write')
        return super(ImmutableReview, self).write(values)

    def _snapshot20(self, at_decision=False):
        self.ensure_one()
        data = {name: self[name].id if self._fields[name].type == 'many2one' else self[name] for name in (
            'request_id', 'stage_id', 'principal_id', 'delegate_id', 'permitted_group_id', 'request_type',
            'effective_from', 'effective_until', 'reason', 'proposed_by', 'proposed_at', 'authorized_by', 'authorized_at', 'policy_fingerprint')}
        data['id'] = self.id
        # Revocation is a later audit event, not a rewrite of the authorization
        # that existed at a past valid decision instant.
        if not at_decision:
            data.update(state=self.state, revoked_by=self.revoked_by.id, revoked_at=self.revoked_at,
                        prior_decision_ids=self.revocation_decision_ids.ids)
        return safe_json(data)

    def _check20(self, engine, instant, current=True, decision=None):
        self.ensure_one(); self.check_access('read')
        request = self.request_id; stage = self.stage_id
        if not request.decision_policy.get('decision_delegation_enabled') or self.policy_fingerprint != request.decision_policy_fingerprint:
            raise AccessError('This exact company policy/version does not permit the delegation.')
        if (stage.request_id != request or self.company_id != request.company_id or self.request_type != request.request_type or
                self.principal_id not in stage.assigned_ids or self.principal_id == self.delegate_id or
                self.permitted_group_id not in stage.required_group_ids or self.delegate_id not in stage.candidate_ids or
                self.delegate_id in request.stage_ids.assigned_ids):
            raise AccessError('Delegation cannot expand company, role, candidate, review type or independent identity scope.')
        if not self.authorized_at or self.authorized_at > instant or not self.authorized_by:
            raise AccessError('Delegation requires prior explicit independent governance authorization.')
        if self.authorized_by in (self.principal_id | self.delegate_id | request.maker_id | request.requested_by | request.submitted_by):
            raise AccessError('Delegation authorization is not independent of the represented parties or source owner.')
        if not within(instant, self.effective_from, self.effective_until):
            raise AccessError('Delegation is outside its explicit UTC [start,end) window.')
        if current:
            approver = self.authorized_by.with_user(self.authorized_by).with_context(allowed_company_ids=request.company_id.ids)
            if not approver.active or approver.share or request.company_id not in approver.company_ids or not any(
                    approver.has_group(group.get_external_id()[group.id]) for group in request.policy_id.decision_governance_group_ids):
                raise AccessError('The delegation governance authorizer lost current company/role eligibility.')
            request.with_user(approver).with_context(allowed_company_ids=request.company_id.ids).check_access('read')
        prior_vote = not current and decision and decision in self.revocation_decision_ids
        if (current and self.state != 'active') or (self.revoked_at and self.revoked_at <= instant and not prior_vote):
            raise AccessError('The delegation is revoked or inactive at the decision instant.')
        role_xml = self.permitted_group_id.get_external_id()[self.permitted_group_id.id]
        for user in self.principal_id | self.delegate_id:
            if user.id in engine.excluded or not engine.eligible(user, stage.plan['roles']) or not user.with_user(user).has_group(role_xml):
                raise AccessError('Both delegation parties must independently retain the exact role/company/source authority.')
        return True

    def action_authorize(self):
        self.ensure_one(); request = self.request_id
        request._lock20(); request._governance20()
        self.invalidate_recordset()
        if self.state == 'revoked':
            raise UserError('A revoked delegation cannot be silently reactivated.')
        if self.state == 'active':
            self._check20(request._contract20(), fields.Datetime.now()); return self
        if request.state not in PENDING or self.stage_id.stage_status not in ('waiting_predecessor', 'ready_for_review', 'partially_approved'):
            raise UserError('Only an uncompleted mandatory stage can receive delegated review responsibility.')
        if self.principal_id in request._votes20().reviewer_id:
            raise UserError('A principal that already decided cannot activate a replacement delegation.')
        if self.env.user in (self.principal_id | self.delegate_id | request.maker_id | request.requested_by | request.submitted_by):
            raise AccessError('An independently authorized company governance user must authorize delegation.')
        request._lock_people20((self.principal_id | self.delegate_id | self.env.user).ids)
        engine = request._contract20()
        if fields.Datetime.now() >= self.effective_until:
            raise UserError('An already expired delegation cannot be authorized.')
        with self.env.cr.savepoint():
            self._update20(dict(state='active', authorized_by=self.env.uid, authorized_at=fields.Datetime.now(),
                active_slot=str(self.stage_id.id) + ':' + str(self.principal_id.id),
                active_actor_key=str(request.id) + ':' + str(self.delegate_id.id)))
            # A future start is allowed; validate all authority at its start,
            # then enforce the real current instant for each actual decision.
            self._check20(engine, max(fields.Datetime.now(), self.effective_from))
            request._event('delegation_authorized', self.reason, self._snapshot20(), request.state)
            request._sync_activities20(engine)
        return self

    def action_revoke(self, reason):
        self.ensure_one(); request = self.request_id
        request._lock20(); authority(self.env); text(reason, 'Delegation revocation reason')
        if self.env.user != self.principal_id:
            request._governance20()
        self.invalidate_recordset()
        if self.state == 'revoked':
            return self
        with self.env.cr.savepoint():
            # Native Datetime.now is second-resolution. Retain causal database
            # order explicitly when a legitimate vote and its later revocation
            # share the same UTC second; never fabricate a later timestamp.
            prior = request._votes20().filtered(lambda d: d.delegation_id == self)
            self._update20(dict(state='revoked', revoked_by=self.env.uid, revoked_at=fields.Datetime.now(),
                revocation_reason=reason, revocation_decision_ids=[Command.set(prior.ids)],
                active_slot=False, active_actor_key=False))
            request._event('delegation_revoked', reason, self._snapshot20(), request.state)
            if request.state in PENDING:
                request._sync_activities20(request._contract20())
        return self


class DelegationRequest(models.Model):
    _inherit = HEADER

    def action_propose_delegation(self, stage_id, delegate_id, permitted_group_id, effective_from, effective_until, reason):
        self._lock20(); authority(self.env); text(reason, 'Delegation reason')
        if self.state not in PENDING:
            raise UserError('Delegation is available only for pending review.')
        if any(type(i) is not int or i <= 0 for i in (stage_id, delegate_id, permitted_group_id)):
            raise ValidationError('Use exact stage/delegate/role IDs, not an acting reviewer parameter.')
        stage = self.env[STAGE].browse(stage_id).exists(); stage.check_access('read')
        delegate = self.env['res.users'].browse(delegate_id).exists()
        if not stage or stage.request_id != self or self.env.user not in stage.assigned_ids:
            raise AccessError('Only the exact assigned principal may propose a stage delegation.')
        engine = self._contract20()
        if not self.decision_policy['decision_delegation_enabled']:
            raise AccessError('Delegation is not enabled by this company decision policy.')
        if stage.stage_status not in ('waiting_predecessor', 'ready_for_review', 'partially_approved') or self._votes20().filtered(lambda d: d.reviewer_id == self.env.user):
            raise UserError('A completed principal slot cannot be delegated.')
        group = self.env['res.groups'].browse(permitted_group_id).exists()
        if not group or group not in stage.required_group_ids or delegate == self.env.user or delegate not in stage.candidate_ids or delegate in self.stage_ids.assigned_ids:
            raise AccessError('The delegate must be an independent frozen candidate for this exact role, with no other reserved slot.')
        role_xml = group.get_external_id()[group.id]
        for user in self.env.user | delegate:
            if user.id in engine.excluded or not engine.eligible(user, stage.plan['roles']) or not user.with_user(user).has_group(role_xml):
                raise AccessError('Delegation never grants missing roles, company scope or maker-checker exceptions.')
        try:
            start = fields.Datetime.to_datetime(effective_from); end = fields.Datetime.to_datetime(effective_until)
        except (ValueError, TypeError) as exc:
            raise ValidationError('Use explicit server-format UTC delegation instants.') from exc
        if (start and start.tzinfo) or (end and end.tzinfo):
            raise ValidationError('Delegation instants must use Odoo naive UTC storage semantics.')
        if not start or not end or end <= start or end <= fields.Datetime.now() or (self.review_deadline and end > self.review_deadline):
            raise ValidationError('Explicit increasing UTC delegation instants within the request review window are required.')
        self._lock_people20([delegate.id, self.env.uid])
        record = self.env[DELEGATION]._record(dict(batch_id=self.batch_id.id, request_id=self.id, stage_id=stage.id,
            principal_id=self.env.uid, delegate_id=delegate.id, permitted_group_id=group.id, request_type=self.request_type,
            effective_from=start, effective_until=end, reason=reason, proposed_by=self.env.uid,
            proposed_at=fields.Datetime.now(), policy_fingerprint=self.decision_policy_fingerprint, state='proposed'))
        self._event('delegation_proposed', reason, record._snapshot20(), self.state)
        return record
