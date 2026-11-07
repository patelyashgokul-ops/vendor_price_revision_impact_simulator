"""Immutable company/source-scoped observations and controlled incident metadata."""
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from .execution import EXEC, LINE
from .import_intake import clean_defaults
from .import_validation import ImmutableReview
from .structural_validation import digest
from .monitor_math import VERSION

PREFIX = 'vendor.price.revision.application.monitor.'
RUN, CHECK, INCIDENT, EVENT, CORRECTION = [PREFIX + n for n in ('run', 'check', 'incident', 'event', 'correction')]
TOKEN = object()
READ_MODELS = (RUN, CHECK, INCIDENT, EVENT, CORRECTION)
MODULE = 'vendor_price_revision_impact_simulator.'


def authority(record):
    record.ensure_one(); record.check_access('read')
    user = record.env.user
    if (not user.active or user.share or not any(user.has_group(MODULE + role) for role in
            ('group_vpr_purchase_manager', 'group_vpr_finance_manager')) or
            record.company_id not in record.env.companies or record.company_id not in user.company_ids):
        raise AccessError('Company-authorized Purchase or Finance Manager required for monitoring review.')
    (record if record._name == EXEC else record.execution_id).check_access('read')


def record(env, model, values):
    return env[model].with_context(_monitor_capability=TOKEN)._record(values)


def update(records, values):
    return super(ImmutableReview, clean_defaults(records)).write(values)


class MonitorGuard(models.AbstractModel):
    _name = PREFIX + 'guard'
    _inherit = 'vendor.price.revision.import.review.guard'
    _description = 'Source Authorized Immutable Monitoring Guard'
    execution_id = fields.Many2one(EXEC, required=True, ondelete='restrict', index=True)

    @api.model
    def _record(self, values):
        if self.env.context.get('_monitor_capability') is not TOKEN:
            raise AccessError('Monitoring evidence requires the authenticated service.')
        for vals in values if isinstance(values, list) else [values]:
            execution = self.env[EXEC].browse(vals['execution_id'])
            authority(execution)
            if vals['batch_id'] != execution.batch_id.id:
                raise AccessError('Monitoring provenance cannot be reassigned.')
        return super()._record(values)

    def action_view_applied_evidence(self):
        self.ensure_one(); self.check_access('read'); self.execution_id.check_access('read')
        return dict(type='ir.actions.act_window', res_model=EXEC, res_id=self.execution_id.id, view_mode='form')


class MonitorRun(models.Model):
    _name = RUN
    _inherit = PREFIX + 'guard'
    _description = 'Bounded Post Application Observation Run'
    _order = 'id desc'
    name = fields.Char(required=True)
    run_type = fields.Char(required=True)
    state = fields.Char(required=True)
    started_at = fields.Datetime(required=True)
    completed_at = fields.Datetime()
    triggered_by = fields.Many2one('res.users', required=True)
    policy_version = fields.Char(required=True, default=VERSION)
    expected_count = fields.Integer(required=True)
    processed_count = fields.Integer(required=True)
    passed_count = fields.Integer(required=True)
    failed_count = fields.Integer(required=True)
    blocked_count = fields.Integer(required=True)
    last_processed_reference = fields.Integer()
    has_more = fields.Boolean()
    error_summary = fields.Char()
    check_ids = fields.One2many(CHECK, 'run_id')


class MonitorCheck(models.Model):
    _name = CHECK
    _inherit = PREFIX + 'guard'
    _description = 'Immutable Applied Versus Current Price Observation'
    _order = 'id desc'
    run_id = fields.Many2one(RUN, required=True, ondelete='restrict', index=True)
    execution_line_id = fields.Many2one(LINE, required=True, ondelete='restrict', index=True)
    target_id = fields.Integer(required=True, index=True)
    successor_line_id = fields.Many2one(LINE, ondelete='restrict')
    checked_at = fields.Datetime(required=True)
    status = fields.Char(required=True)
    classification = fields.Char(required=True)
    expected = fields.Json()
    observed = fields.Json()
    differences = fields.Json()
    codes = fields.Json()
    selection = fields.Json()
    metadata = fields.Json()
    expected_fingerprint = fields.Char(required=True)
    observed_fingerprint = fields.Char(required=True)
    unit_price_difference = fields.Char()
    evidence_fingerprint = fields.Char(required=True)


class MonitorIncident(models.Model):
    _name = INCIDENT
    _inherit = PREFIX + 'guard'
    _description = 'Operational Vendor Pricing Incident — Review Only'
    _order = 'id desc'
    _key_unique = models.Constraint('UNIQUE(incident_key)', 'One retained incident per exact anomaly scope.')
    name = fields.Char(required=True)
    incident_key = fields.Char(required=True, index=True)
    execution_line_id = fields.Many2one(LINE, required=True, ondelete='restrict', index=True)
    target_id = fields.Integer(required=True)
    code = fields.Char(required=True, index=True)
    severity = fields.Char(required=True)
    status = fields.Char(required=True, index=True)
    first_detected_at = fields.Datetime(required=True)
    last_detected_at = fields.Datetime(required=True)
    first_check_id = fields.Many2one(CHECK, required=True, ondelete='restrict')
    latest_check_id = fields.Many2one(CHECK, required=True, ondelete='restrict')
    revalidation_check_id = fields.Many2one(CHECK, ondelete='restrict')
    assigned_user_id = fields.Many2one('res.users')
    resolved_by = fields.Many2one('res.users')
    resolved_at = fields.Datetime()
    resolution_reason = fields.Text()
    event_ids = fields.One2many(EVENT, 'incident_id')
    correction_ids = fields.One2many(CORRECTION, 'incident_id')

    def _locked(self):
        authority(self)
        from .monitor_service import lock
        lock(self.execution_id)
        self.env.cr.execute('SELECT id FROM ' + self._table + ' WHERE id=%s FOR UPDATE', [self.id])
        self.invalidate_recordset()

    def _event(self, action, reason, evidence, check=None):
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 8000:
            raise UserError('A bounded substantive review reason is required.')
        if not isinstance(evidence, str) or not evidence.strip() or len(evidence) > 16000:
            raise UserError('A retained evidence reference is required.')
        return record(self.env, EVENT, dict(batch_id=self.batch_id.id, execution_id=self.execution_id.id,
            incident_id=self.id, action=action, reason=reason, evidence_reference=evidence,
            actor_id=self.env.uid, recorded_at=fields.Datetime.now(), resulting_status=self.status,
            check_id=check.id if check else False))

    def action_review(self, action, reason, evidence_reference, assigned_user_id=False):
        self.ensure_one()
        with self.env.cr.savepoint():
            self._locked()
            if action not in ('assign', 'investigate', 'await_evidence', 'reopen'):
                raise UserError('Unsupported incident review action.')
            if self.status == 'RESOLVED_VERIFIED' and action != 'reopen':
                raise UserError('Reopen the incident before further investigation.')
            vals = dict(status={'assign':'ASSIGNED', 'investigate':'INVESTIGATING',
                'await_evidence':'AWAITING_EVIDENCE', 'reopen':'REOPENED'}[action], revalidation_check_id=False)
            if action == 'assign':
                user = self.env['res.users'].browse(assigned_user_id).exists()
                user.check_access('read')
                if not user or not user.active or user.share or self.company_id not in user.company_ids:
                    raise AccessError('Owner must be active and authorized for this company.')
                # Ownership is not a grant: the assignee must already have source access.
                target = self.with_user(user).with_context(allowed_company_ids=self.company_id.ids)
                authority(target)
                vals['assigned_user_id'] = user.id
            update(self, vals)
            self._event(action, reason, evidence_reference)
        return True

    def action_revalidate_incident(self):
        self.ensure_one(); authority(self)
        run = self.execution_id._monitor23(line_ids=self.execution_line_id.ids, run_type='INCIDENT_REVALIDATION')
        self._locked()
        check = run.check_ids.filtered(lambda c:c.execution_line_id == self.execution_line_id)
        update(self, dict(revalidation_check_id=check.id, latest_check_id=check.id, status='REVALIDATION_REQUIRED'))
        self._event('revalidate', 'Fresh coherent observation; closure still requires review.', 'monitor.check:' + str(check.id), check)
        return run

    def action_close_incident(self, reason, evidence_reference):
        self.ensure_one()
        with self.env.cr.savepoint():
            self._locked()
            check = self.revalidation_check_id
            if not check or check != self.latest_check_id or check.status not in ('PASS', 'EXPECTED_CHANGE'):
                raise UserError('Verified closure requires the latest clean revalidation. Comments and correction plans do not resolve drift.')
            # Re-read current prices now rather than close on a stale clean observation.
            run = self.execution_id._monitor23(line_ids=self.execution_line_id.ids, run_type='CLOSURE_REVALIDATION')
            check = run.check_ids
            if check.status not in ('PASS', 'EXPECTED_CHANGE'):
                raise UserError('Current revalidation is incomplete or still detects an anomaly.')
            update(self, dict(status='RESOLVED_VERIFIED', resolved_by=self.env.uid, resolved_at=fields.Datetime.now(),
                resolution_reason=reason, revalidation_check_id=check.id, latest_check_id=check.id))
            self._event('close_verified', reason, evidence_reference, check)
        return True

    def action_prepare_correction_plan(self, reason, evidence_reference, proposed_values=None):
        self.ensure_one()
        with self.env.cr.savepoint():
            self._locked()
            self.latest_check_id.check_access('read')
            if proposed_values is not None and (not isinstance(proposed_values, dict) or
                    len(str(proposed_values)) > 8000 or set(proposed_values) - set(self.latest_check_id.expected or {})):
                raise UserError('Provide bounded proposed commercial terms only.')
            self._event('prepare_correction', reason, evidence_reference)
            plan = record(self.env, CORRECTION, dict(batch_id=self.batch_id.id, execution_id=self.execution_id.id,
                incident_id=self.id, check_id=self.latest_check_id.id, reason=reason, evidence_reference=evidence_reference,
                proposed_values=proposed_values or {}, status='REQUIRES_NEW_APPROVAL' if proposed_values else 'EVIDENCE_REQUIRED',
                created_by=self.env.uid, created_at=fields.Datetime.now()))
            update(self, dict(status='CORRECTION_PLAN_REQUIRED', revalidation_check_id=False))
        return plan


class MonitorEvent(models.Model):
    _name = EVENT
    _inherit = PREFIX + 'guard'
    _description = 'Immutable Incident Review and Observation History'
    incident_id = fields.Many2one(INCIDENT, required=True, ondelete='restrict', index=True)
    check_id = fields.Many2one(CHECK, ondelete='restrict')
    action = fields.Char(required=True)
    actor_id = fields.Many2one('res.users', required=True)
    recorded_at = fields.Datetime(required=True)
    reason = fields.Text(required=True)
    evidence_reference = fields.Text(required=True)
    resulting_status = fields.Char(required=True)


class CorrectionPlan(models.Model):
    _name = CORRECTION
    _inherit = PREFIX + 'guard'
    _description = 'PLANNED ONLY — NO PRICE CHANGE EXECUTED'
    incident_id = fields.Many2one(INCIDENT, required=True, ondelete='restrict', index=True)
    check_id = fields.Many2one(CHECK, required=True, ondelete='restrict')
    status = fields.Char(required=True)
    proposed_values = fields.Json()
    reason = fields.Text(required=True)
    evidence_reference = fields.Text(required=True)
    created_by = fields.Many2one('res.users', required=True)
    created_at = fields.Datetime(required=True)
    requires_new_approval = fields.Boolean(default=True, readonly=True)
    requires_new_dry_run = fields.Boolean(default=True, readonly=True)
