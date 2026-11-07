"""Community decision forms and private immutable supporting documents."""
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from .approval import HEADER, STAGE, EVIDENCE, EVENT, ISSUE, authority
from .approval_decisions import DECISION, AUTHORIZATION, DELEGATION, DECISION_TYPES, PENDING

PROTECTED_MODELS = (HEADER, STAGE, EVIDENCE, EVENT, ISSUE, DECISION, AUTHORIZATION, DELEGATION)


class DecisionWizard(models.TransientModel):
    _name = 'vendor.price.revision.approval.decision.wizard'
    _inherit = 'vendor.price.revision.purchase.wizard.boundary'
    _description = 'Authenticated Approval Decision and Justification'
    request_id = fields.Many2one(HEADER, required=True)
    stage_id = fields.Many2one(STAGE, required=True)
    decision_type = fields.Selection(DECISION_TYPES, required=True)
    delegation_id = fields.Many2one(DELEGATION)
    reason = fields.Text()
    evidence_reference = fields.Text()
    attachment_ids = fields.Many2many('ir.attachment', relation='vpr_decision_wizard_attachment_rel')

    def action_execute(self):
        self.ensure_one(); self.check_access('write')
        if self.create_uid != self.env.user:
            raise AccessError('Decision input belongs to its authenticated creator.')
        methods = {'approve': self.request_id.action_approve, 'reject': self.request_id.action_reject,
                   'return': self.request_id.action_return_for_revision}
        result = methods[self.decision_type](reason=self.reason or '', evidence_reference=self.evidence_reference or '',
            stage_id=self.stage_id.id, delegation_id=self.delegation_id.id or None, attachment_ids=self.attachment_ids.ids)
        if not result:
            return dict(type='ir.actions.client', tag='display_notification', params=dict(title='Decision blocked',
                message='Current source/policy/time evidence is not valid. The issue and required rework are retained on the request.', type='warning', sticky=True,
                next=dict(type='ir.actions.act_window', res_model=HEADER, res_id=self.request_id.id, view_mode='form')))
        return dict(type='ir.actions.act_window', res_model=HEADER, res_id=self.request_id.id, view_mode='form')


class DelegationWizard(models.TransientModel):
    _name = 'vendor.price.revision.approval.delegation.wizard'
    _inherit = 'vendor.price.revision.purchase.wizard.boundary'
    _description = 'Propose Independently Authorized Stage Delegation'
    request_id = fields.Many2one(HEADER, required=True)
    stage_id = fields.Many2one(STAGE, required=True)
    delegate_id = fields.Many2one('res.users', required=True)
    permitted_group_id = fields.Many2one('res.groups', required=True)
    effective_from = fields.Datetime(required=True)
    effective_until = fields.Datetime(required=True)
    reason = fields.Text(required=True)

    def action_propose(self):
        self.ensure_one(); self.check_access('write')
        if self.create_uid != self.env.user:
            raise AccessError('Delegation input belongs to its authenticated creator.')
        record = self.request_id.action_propose_delegation(self.stage_id.id, self.delegate_id.id, self.permitted_group_id.id,
            self.effective_from, self.effective_until, self.reason)
        return dict(type='ir.actions.act_window', res_model=DELEGATION, res_id=record.id, view_mode='form')


class GovernanceWizard(models.TransientModel):
    _name = 'vendor.price.revision.approval.governance.wizard'
    _inherit = 'vendor.price.revision.purchase.wizard.boundary'
    _description = 'Reasoned Delegation Revocation or Approval Invalidation'
    request_id = fields.Many2one(HEADER, required=True)
    delegation_id = fields.Many2one(DELEGATION)
    operation = fields.Selection([('invalidate', 'Invalidate Current Approval Authority'), ('revoke', 'Revoke Delegation')], required=True)
    reason = fields.Text(required=True)

    def action_execute(self):
        self.ensure_one(); self.check_access('write')
        if self.create_uid != self.env.user:
            raise AccessError('Governance input belongs to its authenticated creator.')
        if self.operation == 'invalidate':
            self.request_id.action_invalidate_approval(self.reason)
        elif not self.delegation_id or self.delegation_id.request_id != self.request_id:
            raise AccessError('Revocation must reference the exact request delegation.')
        else:
            self.delegation_id.action_revoke(self.reason)
        return dict(type='ir.actions.act_window', res_model=HEADER, res_id=self.request_id.id, view_mode='form')


class DecisionActions(models.Model):
    _inherit = HEADER

    def _open_decision20(self, kind):
        self.ensure_one(); self.check_access('read')
        if not self.can_decide:
            raise AccessError('Only a currently eligible independent reviewer can open this decision form.')
        return dict(type='ir.actions.act_window', res_model='vendor.price.revision.approval.decision.wizard', view_mode='form', target='new',
            context=dict(default_request_id=self.id, default_stage_id=self._active_stage20().id, default_decision_type=kind))

    def action_open_approve(self):
        return self._open_decision20('approve')

    def action_open_reject(self):
        return self._open_decision20('reject')

    def action_open_return(self):
        return self._open_decision20('return')

    def action_open_delegation(self):
        self.ensure_one(); self.check_access('read'); authority(self.env)
        if self.state not in PENDING:
            raise UserError('Delegation requires a pending request.')
        return dict(type='ir.actions.act_window', res_model='vendor.price.revision.approval.delegation.wizard', view_mode='form', target='new',
            context=dict(default_request_id=self.id))

    def action_open_invalidation(self):
        self.ensure_one(); self._governance20()
        return dict(type='ir.actions.act_window', res_model='vendor.price.revision.approval.governance.wizard', view_mode='form', target='new',
            context=dict(default_request_id=self.id, default_operation='invalidate'))

    @api.model
    def action_expired_invalidated_reviews(self):
        # Time expiry is evaluated at invocation, not only after a cron/sync.
        return dict(type='ir.actions.act_window', name='Expired / Invalidated Review Authority', res_model=HEADER, view_mode='list,form',
            domain=['|','|','|',('state','in',['approval_expired','approval_invalidated']),
                    ('approval_expired_at','!=',False),('approval_invalidated_at','!=',False),
                    '&',('state','=','approved'),'&',('approval_valid_until','!=',False),
                    ('approval_valid_until','<=',fields.Datetime.now())])


class DelegationActions(models.Model):
    _inherit = DELEGATION

    def action_open_revocation(self):
        self.ensure_one(); self.check_access('read')
        return dict(type='ir.actions.act_window', res_model='vendor.price.revision.approval.governance.wizard', view_mode='form', target='new',
            context=dict(default_request_id=self.request_id.id, default_delegation_id=self.id, default_operation='revoke'))


class ApprovalDocument(models.Model):
    _inherit = 'ir.attachment'

    def _protected_sources(self):
        original = super()._protected_sources()
        # Same existing intake pattern: metadata-only elevation recognizes files
        # for ID/stream attacks. Content and business permission checks run in the
        # original requesting environment through the inherited read/stream guard.
        review = self.sudo().filtered(lambda a: a.res_model in PROTECTED_MODELS).with_env(self.env)
        return original | review

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        defaults = self.default_get(['res_model', 'res_id', 'company_id', 'public', 'access_token', 'type'])
        for vals in vals_list:
            values = dict(vals)
            target = values.get('res_model', defaults.get('res_model'))
            if target in PROTECTED_MODELS:
                if target != HEADER:
                    raise AccessError('Supporting files attach only to the request; frozen decision/evidence records cannot acquire extra files.')
                rid = values.get('res_id', defaults.get('res_id'))
                if type(rid) is not int or rid <= 0:
                    raise ValidationError('An exact authorized request is required for supporting files.')
                request = self.env[HEADER].browse(rid).exists(); request.check_access('write'); authority(self.env)
                if not request or request.state not in ('draft', 'blocked', 'ready_to_submit') + PENDING:
                    raise AccessError('Supporting files may be added only during controlled draft or pending review.')
                if values.get('public', defaults.get('public')) or values.get('access_token', defaults.get('access_token')) or values.get('type', defaults.get('type', 'binary')) != 'binary':
                    raise AccessError('Approval files are private binary evidence with no public URL/access token.')
                company = values.get('company_id', request.company_id.id)
                if company and company != request.company_id.id:
                    raise AccessError('Supporting document company must match its exact request.')
                values.update(company_id=request.company_id.id, public=False, access_token=False)
            prepared.append(values)
        return super().create(prepared)

    def write(self, values):
        if values.get('res_model') in PROTECTED_MODELS:
            raise AccessError('Supporting approval files cannot be reassigned; create a new retained private document.')
        return super().write(values)
