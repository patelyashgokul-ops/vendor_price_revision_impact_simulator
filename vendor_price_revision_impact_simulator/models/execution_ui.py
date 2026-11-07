"""Deliberate owner-bound confirmation; result read happens after RPC commit."""
from odoo import api, fields, models
from odoo.exceptions import AccessError
from .execution import EXEC, LINE, OPERATOR, operator
from .application_plan import PLAN


class ExecutionConfirmation(models.TransientModel):
    _name = 'vendor.price.revision.application.confirmation'
    _description = 'Confirm One Exact Operational Vendor Price Application'
    plan_id = fields.Many2one(PLAN, required=True, readonly=True)
    company_id = fields.Many2one(related='plan_id.company_id', readonly=True)
    request_id = fields.Many2one(related='plan_id.request_id', readonly=True)
    vendor_id = fields.Many2one(related='plan_id.batch_id.vendor_id', readonly=True)
    expected_fingerprint = fields.Char(required=True, readonly=True)
    scope = fields.Json(related='plan_id.evidence', readonly=True)
    confirmation = fields.Boolean(string='I authorize this exact operational Vendor Pricelist change')

    @api.model_create_multi
    def create(self, vals_list):
        clean = self.with_context({k:v for k,v in self.env.context.items() if not k.startswith('default_')})
        prepared = []
        for vals in vals_list:
            if set(vals)-{'plan_id','confirmation'}:
                raise AccessError('Confirmation metadata is server-owned.')
            plan = self.env[PLAN].browse(vals.get('plan_id'))
            operator(plan)
            prepared.append(dict(plan_id=plan.id,expected_fingerprint=plan.fingerprint,confirmation=False))
        return super(ExecutionConfirmation,clean).create(prepared)

    def write(self, vals):
        if set(vals)-{'confirmation'} or any(w.create_uid != self.env.user for w in self):
            raise AccessError('Only the owner may confirm; plan metadata cannot be reassigned.')
        return super().write(vals)

    def action_confirm(self):
        self.ensure_one(); self.check_access('write')
        if self.create_uid != self.env.user:
            raise AccessError('Confirmation belongs to its authenticated creator.')
        receipt = self.plan_id.action_apply_approved_vendor_prices(self.confirmation,self.expected_fingerprint)
        # Standard Odoo RPC commits before delivering this action. The next form
        # read computes VERIFIED only when the originating transaction committed.
        return dict(type='ir.actions.act_window',res_model=EXEC,res_id=receipt.id,view_mode='form')


class ExecutionNavigation(models.Model):
    _inherit = PLAN
    can_execute22 = fields.Boolean(compute='_can_execute22')

    @api.depends_context('uid','allowed_company_ids')
    def _can_execute22(self):
        for plan in self:
            try:
                operator(plan)
                native=self.env['product.supplierinfo']
                for action,op in (('create','CREATE_CANDIDATE'),('write','UPDATE_CANDIDATE')):
                    if any(v['operation']==op for v in plan.evidence.get('lines',[])):native.check_access(action)
                request=plan.request_id;policy=request.policy_id
                distinct=(not policy.application_distinct_maker or self.env.user not in (request.maker_id|request.requested_by))
                distinct=distinct and (not policy.application_distinct_approver or self.env.user not in (request.decision_ids.acting_user_id|request.decision_ids.reviewer_id))
                plan.can_execute22=bool(distinct and request.state=='approved' and not request.approval_invalidated_at and
                    (not request.approval_valid_until or fields.Datetime.now()<request.approval_valid_until) and
                    plan.historical_readiness=='READY_FOR_FUTURE_APPLICATION')
            except AccessError:
                plan.can_execute22=False

    def action_open_execution_confirmation(self):
        self.ensure_one(); operator(self)
        wizard = self.env['vendor.price.revision.application.confirmation'].create({'plan_id':self.id})
        return dict(type='ir.actions.act_window',res_model=wizard._name,res_id=wizard.id,view_mode='form',target='new')


class ExecutionDocument(models.Model):
    _inherit = 'ir.attachment'

    def _protected_sources(self):
        return super()._protected_sources() | self.sudo().filtered(lambda a:a.res_model in (EXEC,LINE)).with_env(self.env)

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get('default_res_model') in (EXEC,LINE) or any(v.get('res_model') in (EXEC,LINE) for v in vals_list):
            raise AccessError('Execution evidence is immutable; extra attachments are not supported.')
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('res_model') in (EXEC,LINE):
            raise AccessError('Files cannot be reassigned to immutable execution evidence.')
        return super().write(vals)
