"""Immutable analytical dry-runs. No application/execution pathway exists here."""
import pytz
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from .approval import HEADER
from .approval_decisions import safe_json
from .scenario_math import text
from .structural_validation import digest
from .application_engine import ApplicationEngine, planner, snapshot, schema
from .application_math import OPERATIONS, MATERIAL
from .commercial_engine import uom_snapshot
from .commercial_math import number

PLAN = 'vendor.price.revision.application.plan'
LINE = PLAN + '.line'
ISSUE = PLAN + '.issue'
MODELS = (PLAN, LINE, ISSUE)


class ApprovalPlanningScope(models.Model):
    _inherit = HEADER
    vendor_application_scope = fields.Json(readonly=True)
    application_plan_ids = fields.One2many(PLAN, 'request_id')

    def _payload20(self, engine):
        payload = super()._payload20(engine)
        # Legacy PR20 artifacts remain byte-compatible when no intent was approved.
        if self.vendor_application_scope:
            payload['vendor_application_scope'] = self.vendor_application_scope
        return safe_json(payload)

    def action_set_vendor_application_scope(self, lines, reason, vendor_component=False, calendar_timezone=None):
        self.ensure_one(); self._lock20(); planner(self.env); text(reason, 'Explicit vendor rule intent')
        if self.state not in ('draft', 'blocked', 'ready_to_submit') or self.requested_by != self.env.user:
            raise AccessError('Only the draft creator can declare vendor-rule intent before independent approval.')
        if self.request_type == 'customer_repricing':
            raise ValidationError('Customer-only approval cannot acquire vendor price authority.')
        company_zone=self.company_id.partner_id.tz or False
        calendar_timezone=calendar_timezone or company_zone
        if not isinstance(calendar_timezone,str) or calendar_timezone not in pytz.all_timezones_set or (company_zone and calendar_timezone != company_zone):
            raise ValidationError('Declare the exact company planning calendar timezone before approval; no caller timezone fallback.')
        if not isinstance(lines, list) or not lines or len(lines) > 10000 or type(vendor_component) is not bool:
            raise ValidationError('Provide bounded explicit approved row intents.')
        allowed = {'row_id', 'operation', 'target_id', 'target_uom_id', 'create_values', 'allow_discount_change'}
        saved = []; seen = set()
        for spec in lines:
            if not isinstance(spec, dict) or set(spec) - allowed or type(spec.get('row_id')) is not int:
                raise ValidationError('Only declared row/rule intent fields are accepted; prices come from the commercial source.')
            rid = spec['row_id']
            if rid in seen or rid not in self.batch_id.row_ids.ids:
                raise ValidationError('Every exact batch row can have one explicit application intent.')
            seen.add(rid); row = self.batch_id.row_ids.browse(rid)
            if not row.commercial_result_id or row.excluded:
                raise ValidationError('A current eligible commercial source row is required.')
            p = row.commercial_result_id.snapshot['proposal']; product = self.env['product.product'].browse(p['product_id'])
            product.check_access('read')
            unit = spec.get('target_uom_id', p['source_uom_id'])
            if type(unit) is not int or unit <= 0 or type(spec.get('allow_discount_change', False)) is not bool:
                raise ValidationError('Exact target unit ID and explicit discount permission required.')
            self.env['uom.uom'].browse(unit).check_access('read')
            product_scope=dict(id=product.id, template_id=product.product_tmpl_id.id, company_id=product.company_id.id, active=product.active, purchase_ok=product.purchase_ok)
            value = dict(product_scope=product_scope, row_id=rid, operation=spec.get('operation'), target_uom_id=unit,
                         allow_discount_change=spec.get('allow_discount_change', False),
                         target_uom=uom_snapshot(self.env['uom.uom'].browse(unit)))
            if value['operation'] == 'update':
                target_id = spec.get('target_id')
                if type(target_id) is not int or target_id <= 0:
                    raise ValidationError('An exact existing target is required for an update intent.')
                target = self.env['product.supplierinfo'].browse(target_id).exists(); target.check_access('read')
                if (not target or target.company_id != self.company_id or target.partner_id != self.batch_id.vendor_id or
                        target.product_id != product or target.product_tmpl_id != product.product_tmpl_id):
                    raise AccessError('A company-specific exact variant/vendor target is required; shared/template scopes cannot be expanded.')
                value.update(target_id=target.id, before=snapshot(target)[0])
            elif value['operation'] == 'create':
                supplied = spec.get('create_values')
                if (not isinstance(supplied, dict) or set(supplied) != {'delay','sequence','product_code','product_name'} or
                        any(type(supplied[k]) is not int or not 0 <= supplied[k] <= 2147483647 for k in ('delay', 'sequence')) or
                        any(not (isinstance(supplied[k], str) or supplied[k] is False) or len(str(supplied[k])) > 256 for k in ('product_code', 'product_name'))):
                    raise ValidationError('Creation needs explicit delay, sequence, vendor code and name; no guessed defaults.')
                if spec.get('target_id'):
                    raise ValidationError('A planned new row has no existing target ID.')
                value['create_values'] = supplied
            else:
                raise ValidationError('Choose explicit update or creation intent.')
            saved.append(value)
        vendor=self.batch_id.vendor_id
        vendor_identity=dict(id=vendor.id,company_id=vendor.company_id.id,parent_id=vendor.parent_id.id,commercial_partner_id=vendor.commercial_partner_id.id,active=vendor.active)
        data = safe_json(dict(contract='pr21_preapproval_vendor_intent_v1', schema=schema(self.env), vendor_identity=vendor_identity, vendor_component=vendor_component, calendar_timezone=calendar_timezone, company_timezone_setting=company_zone,
                              declared_by=self.env.uid, reason=reason, lines=sorted(saved, key=lambda v: v['row_id'])))
        with self.env.cr.savepoint():
            self._update({'vendor_application_scope': data})
            self._event('vendor_application_scope_declared', reason, dict(scope_fingerprint=digest(data)), self.state)
        return self

    def action_run_application_dry_run(self):
        self.ensure_one(); self.check_access('write'); planner(self.env)
        if self.company_id not in self.env.companies or self.company_id not in self.env.user.company_ids:
            raise AccessError('Exact selected authorized planning company required.')
        # No-op APP06 identity epoch forces a fresh retry for concurrent RR snapshots.
        # Business approval fields/write_date are unchanged; supplierinfo is never updated.
        # Serialize only our approval/planning identity, not discovered supplierinfo rows.
        self.env.cr.execute('UPDATE vendor_price_revision_approval_request SET id=id WHERE id=%s', [self.id])
        self.invalidate_recordset()
        data = ApplicationEngine(self).build(); signature = digest(data)
        previous = self.env[PLAN].search([('request_id', '=', self.id)], order='version desc,id desc', limit=1)
        if previous and previous.fingerprint == signature:
            return previous
        with self.env.cr.savepoint():
            plan = self.env[PLAN]._record(dict(batch_id=self.batch_id.id, request_id=self.id,
                name='PLAN-' + str(self.id) + '-' + str(previous.version + 1 if previous else 1),
                version=previous.version + 1 if previous else 1, previous_id=previous.id or False,
                prepared_by=self.env.uid, prepared_at=fields.Datetime.now(), evidence=data, fingerprint=signature,
                source_fingerprint=digest({k:data[k] for k in ('authorization_id','payload_fingerprint','approval_fingerprint','valid_until')}),
                target_fingerprint=digest(data['targets']), historical_readiness=data['readiness']))
            self.env[LINE]._record([dict(batch_id=self.batch_id.id, plan_id=plan.id, row_id=v['row_id'],
                product_id=v.get('product_id') or False, target_id=v.get('target_id') or False,
                operation=v['operation'], before_values=v['before'], planned_after_values=v['after'],
                changed_fields=v['changed_fields'], conflicts=v['conflicts'], evidence=v,
                source_fingerprint=v['source_fingerprint'], target_fingerprint=v['target_fingerprint']) for v in data['lines']])
            self.env[ISSUE]._record([dict(batch_id=self.batch_id.id, plan_id=plan.id, code=v['code'],
                row_id=v['row_id'] or False, severity=v['severity'], description='Planning blocked: ' + v['code']) for v in data['issues']])
        return plan

    def action_open_application_dry_run(self):
        plan = self.action_run_application_dry_run()
        return dict(type='ir.actions.act_window', res_model=PLAN, res_id=plan.id, view_mode='form')


class ApplicationPlan(models.Model):
    _name = PLAN
    _inherit = 'vendor.price.revision.import.review.guard'
    _description = 'Immutable Vendor Application Dry-Run - NOT Applied'
    _order = 'id desc'
    _version = models.Constraint('UNIQUE(request_id,version)', 'One coherent planning version per request.')
    name = fields.Char(required=True)
    request_id = fields.Many2one(HEADER, required=True, ondelete='restrict', index=True)
    version = fields.Integer(required=True)
    previous_id = fields.Many2one(PLAN, ondelete='restrict')
    prepared_by = fields.Many2one('res.users', required=True)
    prepared_at = fields.Datetime(required=True)
    historical_readiness = fields.Char(required=True)
    current_readiness = fields.Char(compute='_current')
    evidence = fields.Json(required=True)
    fingerprint = fields.Char(required=True)
    source_fingerprint = fields.Char(required=True)
    target_fingerprint = fields.Char(required=True)
    line_ids = fields.One2many(LINE, 'plan_id')
    issue_ids = fields.One2many(ISSUE, 'plan_id')

    @api.depends_context('uid', 'allowed_company_ids')
    def _current(self):
        cache = {}
        for plan in self:
            try:
                if plan.request_id.id not in cache:
                    latest=self.search([('request_id','=',plan.request_id.id)], order='version desc,id desc', limit=1)
                    cache[plan.request_id.id] = (digest(ApplicationEngine(plan.request_id).build()),latest.id)
                current, latest_id = cache[plan.request_id.id]
                plan.current_readiness = ('SUPERSEDED' if latest_id != plan.id else plan.historical_readiness if plan.fingerprint == digest(plan.evidence) and current == plan.fingerprint else 'STALE')
            except (UserError, ValidationError, AccessError):
                plan.current_readiness = 'STALE_OR_UNAUTHORIZED'

    def get_current_application_plan(self):
        self.ensure_one(); self.check_access('read')
        latest=self.search([('request_id','=',self.request_id.id)], order='version desc,id desc', limit=1)
        if latest != self:
            raise UserError('A newer immutable plan version exists; review the latest version.')
        if self.fingerprint != digest(self.evidence) or digest(ApplicationEngine(self.request_id).build()) != self.fingerprint:
            raise UserError('Plan source/authority/targets changed. Preserve this history and run a fresh dry-run.')
        if self.historical_readiness != 'READY_FOR_FUTURE_APPLICATION':
            raise UserError('Blocking plan issues require review. Planning never authorizes a write by itself.')
        return self

    def action_revalidate_application_plan(self):
        self.ensure_one(); self.check_access('read'); planner(self.env)
        plan = self.request_id.action_run_application_dry_run()
        return dict(type='ir.actions.act_window', res_model=PLAN, res_id=plan.id, view_mode='form')


class ApplicationLine(models.Model):
    _name = LINE
    _inherit = 'vendor.price.revision.import.review.guard'
    _description = 'Frozen Supplier Rule Before/After Preview'
    plan_id = fields.Many2one(PLAN, required=True, ondelete='restrict', index=True)
    row_id = fields.Many2one('vendor.price.revision.import.row', required=True, ondelete='restrict')
    product_id = fields.Many2one('product.product', ondelete='restrict')
    # Do not constrain operational deletion: immutable JSON retains the old target ID.
    target_id = fields.Integer(string='Observed Supplierinfo ID')
    current_price = fields.Char(compute='_comparison')
    approved_price = fields.Char(compute='_comparison')
    price_delta = fields.Char(compute='_comparison')
    approved_moq = fields.Char(compute='_comparison')
    current_currency_id = fields.Many2one('res.currency',compute='_comparison')
    approved_currency_id = fields.Many2one('res.currency',compute='_comparison')
    current_uom_id = fields.Many2one('uom.uom',compute='_comparison')
    approved_uom_id = fields.Many2one('uom.uom',compute='_comparison')
    effective_start = fields.Char(compute='_comparison')
    effective_end = fields.Char(compute='_comparison')
    operation = fields.Selection([(s,s.replace('_',' ').title()) for s in OPERATIONS], required=True)
    before_values = fields.Json()
    planned_after_values = fields.Json()
    changed_fields = fields.Json()
    conflicts = fields.Json()
    evidence = fields.Json(required=True)
    source_fingerprint = fields.Char(required=True)
    target_fingerprint = fields.Char(required=True)


    @api.depends('before_values','planned_after_values')
    def _comparison(self):
        for line in self:
            old=line.before_values or {};new=line.planned_after_values or {}
            line.current_price=old.get('price') or ''
            line.approved_price=new.get('price') or ''
            line.approved_moq=new.get('min_qty') or ''
            line.current_currency_id=old.get('currency_id') or False
            line.approved_currency_id=new.get('currency_id') or False
            line.current_uom_id=old.get('uom_id') or False
            line.approved_uom_id=new.get('uom_id') or False
            line.effective_start=new.get('date_start') or ''
            line.effective_end=new.get('date_end') or ''
            line.price_delta=(str(number(new['price'])-number(old['price'])) if old and new and old.get('currency_id')==new.get('currency_id') and old.get('uom_id')==new.get('uom_id') else '')


class ApplicationIssue(models.Model):
    _name = ISSUE
    _inherit = 'vendor.price.revision.import.review.guard'
    _description = 'Immutable Application Planning Conflict'
    plan_id = fields.Many2one(PLAN, required=True, ondelete='restrict', index=True)
    row_id = fields.Many2one('vendor.price.revision.import.row', ondelete='restrict')
    code = fields.Char(required=True, index=True)
    severity = fields.Char(required=True)
    description = fields.Text(required=True)


class PlanningDocument(models.Model):
    _inherit = 'ir.attachment'

    def _protected_sources(self):
        # Metadata recognition only; inherited guards use original-user source access.
        return super()._protected_sources() | self.sudo().filtered(lambda a:a.res_model in MODELS).with_env(self.env)

    @api.model_create_multi
    def create(self, vals_list):
        target = self.env.context.get('default_res_model')
        if target in MODELS or any(v.get('res_model') in MODELS for v in vals_list):
            raise AccessError('Planning evidence is immutable; attachments are not supported on planning snapshots.')
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('res_model') in MODELS:
            raise AccessError('Attachments cannot be reassigned to immutable planning evidence.')
        return super().write(vals)
