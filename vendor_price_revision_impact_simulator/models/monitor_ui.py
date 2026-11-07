"""Community review input; private files cannot be attached to monitoring evidence."""
import json
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from .monitor_models import INCIDENT, READ_MODELS, authority
from .import_intake import clean_defaults

WIZARD='vendor.price.revision.application.monitor.review.wizard'


class IncidentNavigation(models.Model):
    _inherit = INCIDENT

    def action_open_monitor_review(self):
        self.ensure_one(); authority(self)
        return dict(type='ir.actions.act_window',res_model=WIZARD,view_mode='form',target='new',
            context=dict(default_incident_id=self.id))

    def action_open_monitor_revalidation(self):
        run=self.action_revalidate_incident()
        return dict(type='ir.actions.act_window',res_model=run._name,res_id=run.id,view_mode='form')


class MonitorReviewWizard(models.TransientModel):
    _name = WIZARD
    _description = 'Document Incident Review — No Price Changes'
    incident_id = fields.Many2one(INCIDENT,required=True)
    operation = fields.Selection([(v,v.replace('_',' ').title()) for v in
        ('assign','investigate','await_evidence','reopen','close_verified','prepare_correction')],required=True,default='investigate')
    assigned_user_id = fields.Many2one('res.users')
    reason = fields.Text(required=True)
    evidence_reference = fields.Text(required=True)
    proposed_terms_json = fields.Text(string='Hypothetical Proposed Terms (JSON; optional)')

    @api.model_create_multi
    def create(self, vals_list):
        allowed={'incident_id','operation','assigned_user_id','reason','evidence_reference','proposed_terms_json'}
        for values in vals_list:
            if set(values)-allowed:
                raise AccessError('Review identity and provenance are server-owned.')
            incident=self.env[INCIDENT].browse(values.get('incident_id'))
            authority(incident)
        return super(MonitorReviewWizard,clean_defaults(self)).create(vals_list)

    def write(self,values):
        if set(values)-{'operation','assigned_user_id','reason','evidence_reference','proposed_terms_json'}:
            raise AccessError('Review input cannot be reassigned to another incident.')
        for wizard in self:
            if wizard.create_uid!=self.env.user:
                raise AccessError('Review input belongs to its authenticated creator.')
            authority(wizard.incident_id)
        return super().write(values)

    def action_submit(self):
        self.ensure_one(); self.check_access('write')
        if self.create_uid!=self.env.user:
            raise AccessError('Review input belongs to its authenticated creator.')
        incident=self.incident_id; authority(incident)
        if self.operation=='close_verified':
            incident.action_close_incident(self.reason,self.evidence_reference)
        elif self.operation=='prepare_correction':
            try:
                terms=json.loads(self.proposed_terms_json) if self.proposed_terms_json else None
            except ValueError as exc:
                raise UserError('Proposed terms require a JSON object.') from exc
            plan=incident.action_prepare_correction_plan(self.reason,self.evidence_reference,terms)
            return dict(type='ir.actions.act_window',res_model=plan._name,res_id=plan.id,view_mode='form')
        else:
            incident.action_review(self.operation,self.reason,self.evidence_reference,self.assigned_user_id.id)
        return dict(type='ir.actions.act_window',res_model=INCIDENT,res_id=incident.id,view_mode='form')


class MonitorDocument(models.Model):
    _inherit='ir.attachment'

    def _protected_sources(self):
        return super()._protected_sources() | self.sudo().filtered(lambda a:a.res_model in READ_MODELS).with_env(self.env)

    @api.model_create_multi
    def create(self,vals_list):
        if self.env.context.get('default_res_model') in READ_MODELS or any(v.get('res_model') in READ_MODELS for v in vals_list):
            raise AccessError('Monitoring observations are immutable; use retained protected source evidence references.')
        return super().create(vals_list)

    def write(self,values):
        if values.get('res_model') in READ_MODELS:
            raise AccessError('Files cannot be reassigned to monitoring evidence.')
        return super().write(values)
