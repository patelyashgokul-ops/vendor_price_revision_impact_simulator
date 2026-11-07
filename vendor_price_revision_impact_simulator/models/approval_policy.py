"""Opt-in routing definitions on the existing published PR04 configuration."""
from odoo import api,fields,models
from odoo.exceptions import ValidationError
from .approval_math import TYPES,METRICS,ROLES

MODULE='vendor_price_revision_impact_simulator.'
def pairs(values):return [(v,v.replace('_',' ').title()) for v in values]
TRIGGERS=('always','high_risk','critical_risk','negative_profit','contract_review','cost_decrease')

class WorkflowConfig(models.Model):
    _inherit='vendor.price.revision.config'
    workflow_enabled=fields.Boolean(string='Enable management review routing (no decisions)',default=False)
    workflow_types=fields.Json(default=list,string='Enabled request types (explicit list)')
    workflow_role_order=fields.Json(default=lambda self:list(ROLES))
    workflow_assignment=fields.Selection(pairs(('deterministic','manual')),default='deterministic',required=True)
    workflow_exclude_contributors=fields.Boolean(default=True)
    workflow_manager_withdrawal=fields.Boolean(default=False)
    workflow_activities=fields.Boolean(default=False,string='Create internal first-stage activities (no email)')
    workflow_due_days=fields.Integer(default=3)
    workflow_submitter_group_ids=fields.Many2many('res.groups',relation='vpr_ap_submit_group_rel',default=lambda s:s.env.ref(MODULE+'group_vpr_finance_manager'))
    workflow_high_group_ids=fields.Many2many('res.groups',relation='vpr_ap_high_group_rel')
    workflow_critical_group_ids=fields.Many2many('res.groups',relation='vpr_ap_critical_group_rel')
    workflow_contract_group_ids=fields.Many2many('res.groups',relation='vpr_ap_contract_group_rel')

    def _workflow_errors(self):
        self.ensure_one();errors=[]
        if not self.workflow_enabled:return errors
        supported=self.env['res.groups'].concat(*(self.env.ref(MODULE+r) for r in ROLES))
        if not isinstance(self.workflow_types,list) or not self.workflow_types or any(not isinstance(t,str) or t not in TYPES for t in self.workflow_types) or len(set(self.workflow_types))!=len(self.workflow_types):return ['Explicit supported unique request types required.']
        if not isinstance(self.workflow_role_order,list) or any(not isinstance(v,str) for v in self.workflow_role_order) or len(self.workflow_role_order)!=len(ROLES) or set(self.workflow_role_order)!=set(ROLES):errors.append('Order every supported authority exactly once.')
        for name in ('workflow_submitter_group_ids','workflow_high_group_ids','workflow_critical_group_ids','workflow_contract_group_ids'):
            if not self[name] or self[name]-supported:errors.append('Explicit supported roles required: '+name)
        if self.env.ref(MODULE+'group_vpr_finance_manager') not in self.workflow_critical_group_ids:errors.append('Critical/negative-profit routing must include Finance under PR04 negative margin policy.')
        if not 0<=self.workflow_due_days<=365:errors.append('Activity due days must be0..365.')
        rows=self.approval_ids.filtered('active')
        for category in set(rows.mapped('category')):
            group=rows.filtered(lambda r:r.category==category)
            defs={(tuple(sorted(r.workflow_types or [])),r.workflow_metric,r.workflow_trigger) for r in group}
            if len(defs)!=1:errors.append('Category types, metric and trigger must be coherent across its complete amount scale: '+category)
            if any(r.workflow_types and (not isinstance(r.workflow_types,list) or any(t not in TYPES for t in r.workflow_types) or len(set(r.workflow_types))!=len(r.workflow_types)) for r in group):errors.append('Unsupported or duplicate rule request types.')
            if any(r.required_independent_approvers>32 for r in group):errors.append('Quorum exceeds bounded32-identity route.')
        for typ in self.workflow_types or []:
            categories={'finance_exposure'} if typ in TYPES[:2] else {'customer_repricing'}
            if typ=='commercial_package':categories.add('finance_exposure')
            for cat in categories:
                matching=rows.filtered(lambda r:r.category==cat and typ in (r.workflow_types or []) and r.workflow_trigger=='always')
                if not matching:errors.append('Missing unconditional complete primary category '+cat+' for '+typ)
        return errors

    def _setup_errors(self):
        return super()._setup_errors()+self._workflow_errors()

class WorkflowRule(models.Model):
    _inherit='vendor.price.revision.approval.policy'
    workflow_types=fields.Json(default=list,string='Routing request types (empty disables this category)')
    workflow_metric=fields.Selection(pairs(METRICS),default='cost_increase',required=True)
    workflow_trigger=fields.Selection(pairs(TRIGGERS),default='always',required=True)
    workflow_named_reviewer_ids=fields.Many2many('res.users',relation='vpr_ap_named_user_rel')

    @api.constrains('workflow_types','workflow_named_reviewer_ids')
    def _workflow_definition(self):
        for r in self:
            if r.workflow_types and (not isinstance(r.workflow_types,list) or any(v not in TYPES for v in r.workflow_types) or len(set(r.workflow_types))!=len(r.workflow_types)):raise ValidationError('Use a supported unique request-type list.')
            if any(not u.active or u.share or r.company_id not in u.company_ids for u in r.workflow_named_reviewer_ids):raise ValidationError('Named reviewers must be active internal members of the policy company; source and role rights are rechecked during routing.')
