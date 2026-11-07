"""PR08 commercial comparison only. Never apply a supplier price."""
from collections import Counter
from copy import deepcopy
from datetime import datetime

from psycopg2 import DatabaseError
from psycopg2.errors import SerializationFailure, DeadlockDetected

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from .commercial_engine import CommercialEngine, MATERIAL, supplier_snapshot, uom_snapshot
from . import commercial_math as money
from .import_intake import BATCH, ROW, clean_defaults, PURCHASE_MANAGER
from .import_validation import PREFIX, ImmutableReview
from .product_resolution import company_lock, protect_product_labels, check_product_export, escape_export
from .structural_validation import digest

CONTEXT = 'vendor.price.revision.commercial.context'
RESULT = 'vendor.price.revision.commercial.validation'
ISSUE = 'vendor.price.revision.commercial.issue'
WIZARD = PREFIX + 'commercial.wizard'
ALIAS_WIZARD = WIZARD + '.alias'
FINANCE = 'vendor_price_revision_impact_simulator.group_vpr_finance_manager'
STATUSES = [(s, s.replace('_', ' ').title()) for s in (
    'pending_product', 'pending_validation', 'commercially_valid', 'needs_review', 'blocked',
    'baseline_unavailable', 'baseline_conflict', 'fx_rate_missing', 'uom_invalid',
    'tier_conflict', 'date_conflict', 'stale', 'excluded')]
CLASSIFICATIONS = [(s, s.replace('_', ' ').title()) for s in (
    'increase', 'decrease', 'unchanged', 'new_from_zero', 'zero_to_zero')]
ASSUMPTIONS = {'uom_aliases', 'price_basis', 'discount_percent', 'baseline_mode', 'baseline_date',
    'end_date', 'comparison_mode', 'scenario_rates', 'scenario_reference', 'historical_attestation'}


def lock_commercial(engine):
    """Read-lock existing evidence; serialization errors require fresh retry."""
    from .product_resolution import lock_identity_evidence
    lock_identity_evidence(engine.env, list(engine.product_plans.values()))
    for table, records in (('uom_uom', engine.uoms), ('res_currency', engine.currencies),
                           ('res_currency_rate', engine.rates), ('product_supplierinfo', engine.suppliers)):
        if records:
            # Table names are fixed program constants, not user inputs.
            engine.env.cr.execute('SELECT id FROM ' + table + ' WHERE id IN %s ORDER BY id FOR SHARE',
                                  [tuple(sorted(set(records.ids)))])


def invalidate_commercial(env):
    env[ROW].invalidate_model(['commercial_status', 'commercial_classification', 'commercial_summary',
        'commercial_old_price', 'commercial_new_price', 'commercial_delta', 'commercial_percent',
        'commercial_unit', 'commercial_currency', 'commercial_min_qty', 'commercial_effective_date',
        'commercial_fx_method', 'commercial_supplier_percent', 'commercial_fx_assumption'])
    env[BATCH].invalidate_model(['commercial_counts'])


class CommercialContext(models.Model):
    _name = CONTEXT
    _inherit = PREFIX + 'review.guard'
    _description = 'Independently Verified Commercial Interpretation (not price approval)'
    _order = 'id desc'
    assumptions = fields.Json(required=True)
    source_digest = fields.Char(required=True)
    uom_evidence = fields.Json()
    baseline_evidence = fields.Json()
    proposed_by = fields.Many2one('res.users', required=True)
    proposed_at = fields.Datetime(required=True)
    reason = fields.Char(required=True)
    state = fields.Selection([(s, s.title()) for s in ('proposed', 'verified', 'retired')], required=True)
    verified_by = fields.Many2one('res.users')
    verified_at = fields.Datetime()
    verification_reason = fields.Char()
    retired_by = fields.Many2one('res.users')
    retired_at = fields.Datetime()
    retirement_reason = fields.Char()
    interpretation_summary = fields.Text(compute='_compute_interpretation_summary')

    @api.depends('assumptions', 'uom_evidence', 'state')
    def _compute_interpretation_summary(self):
        for record in self:
            a = record.assumptions or {}
            lines = ['Interpretation state: ' + record.state,
                'Price basis: ' + a.get('price_basis', 'unknown'),
                'Proposed discount %: ' + a.get('discount_percent', '0'),
                'FX comparison: ' + a.get('comparison_mode', 'same_rate'),
                'Old price date: ' + (a.get('baseline_date') or 'Day before proposed start'),
                'Proposed end: ' + (a.get('end_date') or 'Open ended')]
            for alias, uid in a.get('uom_aliases', {}).items():
                evidence = (record.uom_evidence or {}).get(str(uid), {})
                uom = record.env['uom.uom'].browse(uid).exists()
                name = evidence.get('name') or (uom.with_context(lang=None).name if uom else 'Unavailable unit ID ' + str(uid))
                lines.append('Supplier unit ' + alias + ' = ' + name)
            if a.get('scenario_rates'):
                lines.append('HYPOTHETICAL finance scenario: ' + str(a['scenario_rates']) + '; ' + a.get('scenario_reference', ''))
            if a.get('historical_attestation'):
                lines.append('Historical evidence assertion: ' + a['historical_attestation'])
            record.interpretation_summary = '\n'.join(lines)

    def export_data(self, fields_to_export):
        check_product_export(self.batch_id.commercial_result_ids, fields_to_export)
        return super().export_data(fields_to_export)

    def action_verify_context(self, reason):
        self.ensure_one()
        self.check_access('write')
        if not self.env.user.active or not self.env.user.has_group(FINANCE if self.assumptions.get('scenario_rates') else PURCHASE_MANAGER):
            raise AccessError(_('Independent Purchase Manager verification is required; scenario FX requires Finance Manager verification.'))
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
            raise ValidationError(_('Supply a verification reason of 1–1000 characters.'))
        company_lock(self.env, self.company_id)
        batch = self.batch_id
        batch.check_access('read')
        batch._lock()
        if batch.revision_id.state != 'draft' or self.state != 'proposed' or self.proposed_by == self.env.user:
            raise AccessError(_('A different authorized verifier must review a proposed context on a draft revision.'))
        if batch.current_commercial_context_id != self or self.source_digest != batch._commercial_scope_digest():
            raise UserError(_('Source/product context changed; propose a new commercial interpretation.'))
        engine = CommercialEngine(batch)
        lock_commercial(engine)
        if self.assumptions.get('scenario_rates'):
            for product_row in batch.get_product_resolved_rows():
                date = fields.Date.to_date(product_row.current_result_id.parsed_candidates['effective_date_raw'])
                policy = engine.policy(date)
                if not policy or policy.currency_rate_policy != 'authorized_scenario_rate' or policy.fx_override_policy != 'finance_governed':
                    raise UserError(_('The published PR04 policy must explicitly authorize finance-governed scenario rates.'))
        evidence_ids = set(self.assumptions.get('uom_aliases', {}).values())
        ancestors = {int(i) for uid in evidence_ids for i in (engine.by_uom[uid].parent_path or '').split('/') if i}
        evidence = {str(i): uom_snapshot(engine.by_uom[i]) for i in sorted(ancestors | evidence_ids)}
        super(ImmutableReview, self).write({'state': 'verified', 'verified_by': self.env.uid,
            'verified_at': fields.Datetime.now(), 'verification_reason': reason.strip(), 'uom_evidence': evidence,
            'baseline_evidence': [supplier_snapshot(s) for s in engine.suppliers] if self.assumptions.get('historical_attestation') else []})
        invalidate_commercial(self.env)
        return True

    def action_retire_context(self, reason):
        self.check_access('write')
        if not self.env.user.active or not (self.env.user.has_group(PURCHASE_MANAGER) or self.env.user.has_group(FINANCE)):
            raise AccessError(_('An authorized commercial verifier must retire context evidence.'))
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000:
            raise ValidationError(_('A retirement reason is required.'))
        company_lock(self.env, self.company_id)
        for record in self:
            record.batch_id._lock()
            if record.state not in ('proposed', 'verified') or record.batch_id.revision_id.state != 'draft':
                raise UserError(_('Only proposed/verified draft context can be retired.'))
            super(ImmutableReview, record).write({'state': 'retired', 'retired_by': self.env.uid,
                'retired_at': fields.Datetime.now(), 'retirement_reason': reason.strip()})
        invalidate_commercial(self.env)
        return True


class CommercialResult(models.Model):
    _name = RESULT
    _inherit = PREFIX + 'review.guard'
    _description = 'Immutable Commercial Comparison Snapshot'
    _order = 'row_id, version desc, id desc'
    _version_unique = models.Constraint('UNIQUE(row_id, version)', 'Commercial row versions must be unique.')
    row_id = fields.Many2one(ROW, required=True, ondelete='restrict', index=True)
    context_id = fields.Many2one(CONTEXT, ondelete='restrict')
    structural_result_id = fields.Many2one(PREFIX + 'validation.result', required=True, ondelete='restrict')
    product_resolution_id = fields.Many2one(PREFIX + 'product.resolution', required=True, ondelete='restrict')
    product_id = fields.Many2one('product.product', ondelete='restrict')
    version = fields.Integer(required=True)
    previous_id = fields.Many2one(RESULT, ondelete='restrict')
    input_digest = fields.Char(required=True, index=True)
    snapshot = fields.Json(required=True)
    status = fields.Selection(STATUSES, required=True, index=True)
    classification = fields.Selection(CLASSIFICATIONS, index=True)
    proposal_normalized = fields.Boolean()
    actor_id = fields.Many2one('res.users', required=True)
    validated_at = fields.Datetime(required=True)
    issue_ids = fields.One2many(ISSUE, 'result_id', readonly=True)
    is_current = fields.Boolean(compute='_compute_current')
    calculation_explanation = fields.Text(compute='_compute_explanation')

    @api.depends('snapshot')
    def _compute_explanation(self):
        for record in self:
            s = record.snapshot or {}
            p, b, c = s.get('proposal', {}), s.get('baseline', {}), s.get('comparison', {})
            lines = ['Historical snapshot version ' + str(record.version) + ': ' + record.status,
                'Old price as of: ' + str(s.get('baseline_date', 'Unavailable')),
                'Proposed start: ' + str(s.get('effective_date', 'Unavailable')),
                'Comparison unit: ' + p.get('uom', {}).get('comparison', {}).get('name', 'Unresolved'),
                'Comparison currency: ' + p.get('company_currency_code', 'Unresolved'),
                'Quantity in comparison unit: ' + p.get('normalized_min_qty', 'Unresolved'),
                'Proposed source price: ' + p.get('source_price', 'Unresolved') + ' ' + p.get('source_currency_code', ''),
                'Proposed company unit price: ' + p.get('company_price', 'Unavailable'),
                'Old company unit price: ' + b.get('company_price', 'Unavailable'),
                'Old supplier rule ID: ' + str(b.get('selected', {}).get('id', 'Unavailable')),
                'Baseline selection: ' + b.get('precedence', 'No verified applicable rule'),
                'FX comparison method: ' + c.get('method', 'Incomplete'),
                'Company-basis unit delta: ' + c.get('delta', 'Unavailable'),
                'Company-basis change %: ' + str(c.get('percent') if c.get('percent') is not None else 'Undefined / unavailable')]
            for label, terms in (('Old', b), ('Proposed', p)):
                fx = terms.get('fx', {})
                if fx:
                    lines.append(label + ' FX: ' + fx['rate'] + ' on basis ' + fx['requested_date'] + '; ' + fx['method'])
            parts = c.get('decomposition', {})
            if parts:
                lines.append('Supplier/FX decomposition convention: ' + parts['method'])
                lines.append('Supplier component: ' + str(parts.get('supplier_component')) + '; FX component: ' + str(parts.get('fx_component')))
            lines.extend(issue['code'] + ': ' + issue['message'] for issue in s.get('issues', []))
            record.calculation_explanation = '\n'.join(lines)

    def _compute_current(self):
        for record in self:
            record.is_current = record.row_id.commercial_result_id == record and record.row_id.commercial_status not in ('stale', 'pending_product', 'excluded')

    def read(self, fields=None, load='_classic_read'):
        return protect_product_labels(self, super().read(fields=fields, load=load))

    def export_data(self, fields_to_export):
        check_product_export(self, fields_to_export)
        return super().export_data(fields_to_export)


class CommercialIssue(models.Model):
    _name = ISSUE
    _inherit = PREFIX + 'review.guard'
    _description = 'Retained Commercial Validation Issue'
    result_id = fields.Many2one(RESULT, required=True, ondelete='restrict', index=True)
    row_id = fields.Many2one(related='result_id.row_id', store=True, readonly=True)
    code = fields.Char(required=True, index=True)
    severity = fields.Selection([(s, s.title()) for s in ('error', 'review_required', 'info')], required=True)
    message = fields.Char(required=True)
    version = fields.Integer(related='result_id.version', readonly=True)
    is_current = fields.Boolean(related='result_id.is_current', readonly=True)

    def export_data(self, fields_to_export):
        check_product_export(self.result_id, fields_to_export)
        return super().export_data(fields_to_export)


class BatchCommercial(models.Model):
    _inherit = BATCH
    commercial_context_ids = fields.One2many(CONTEXT, 'batch_id', readonly=True)
    current_commercial_context_id = fields.Many2one(CONTEXT, readonly=True, copy=False, ondelete='restrict')
    commercial_result_ids = fields.One2many(RESULT, 'batch_id', readonly=True)
    commercial_processing_state = fields.Selection([(s, s.replace('_', ' ').title()) for s in ('not_started', 'complete', 'failed')], default='not_started', readonly=True, copy=False)
    commercial_error = fields.Char(readonly=True, copy=False)
    commercial_counts = fields.Json(compute='_compute_commercial_counts')

    def _commercial_scope_digest(self):
        self.ensure_one()
        _, products = self._product_plans()
        return digest({'company': self.company_id.id, 'vendor': self.vendor_id.id,
            'rows': [{'id': r.id, 'excluded': r.excluded,
                'inputs': {k: r.effective_values.get(k) for k in MATERIAL},
                'product': products[r.id]['fingerprint']} for r in self.row_ids]})

    def action_propose_commercial_context(self, assumptions, reason):
        self.ensure_one()
        self._check_review_access()
        company_lock(self.env, self.company_id)
        self._lock()
        if not self.get_product_resolved_rows():
            raise UserError(_('Resolve current structurally-ready product rows before proposing commercial context.'))
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 1000 or not isinstance(assumptions, dict) or set(assumptions) - ASSUMPTIONS:
            raise ValidationError(_('Supply documented supported commercial assumptions and a reason of 1–1000 characters.'))
        settings = dict(price_basis='unknown', discount_percent='0', baseline_mode='day_before',
            comparison_mode='same_rate', uom_aliases={}, scenario_rates={}, **{})
        settings.update(deepcopy(assumptions))
        if settings['price_basis'] not in ('net_exclusive', 'tax_inclusive', 'unknown') or settings['baseline_mode'] not in ('day_before', 'explicit') or settings['comparison_mode'] not in ('same_rate', 'date_specific'):
            raise ValidationError(_('Choose supported price, baseline date and FX comparison bases.'))
        if not isinstance(settings['uom_aliases'], dict) or len(settings['uom_aliases']) > 100 or not isinstance(settings['scenario_rates'], dict) or len(settings['scenario_rates']) > 100:
            raise ValidationError(_('Use bounded explicit UoM aliases and scenario currency rates.'))
        for name, uid in settings['uom_aliases'].items():
            if not isinstance(name, str) or not 1 <= len(name) <= 128 or name != name.strip() or type(uid) is not int or not 1 <= uid <= 2147483647:
                raise ValidationError(_('Aliases require exact source text and an existing UoM ID.'))
            uom = self.env['uom.uom'].browse(uid).exists()
            uom.check_access('read')
            if not uom or not uom.active or money.number(uom.factor) <= 0:
                raise ValidationError(_('Alias UoM must exist and have an active positive factor.'))
        try:
            discount = money.number(settings['discount_percent'], True)
            if discount > 100:
                raise ValueError('discount')
            settings['discount_percent'] = str(discount)
            for code, rate in settings['scenario_rates'].items():
                if not isinstance(code, str) or len(code) != 3 or money.number(rate) <= 0:
                    raise ValueError('scenario')
                settings['scenario_rates'][code] = str(money.number(rate))
            for field in ('baseline_date', 'end_date'):
                if settings.get(field):
                    settings[field] = fields.Date.to_date(settings[field]).isoformat()
        except (ValueError, TypeError):
            raise ValidationError(_('Use finite nonnegative prices/discounts, positive FX rates and valid ISO dates.')) from None
        if settings['baseline_mode'] == 'explicit' and not settings.get('baseline_date'):
            raise ValidationError(_('An explicit baseline date is required.'))
        if settings['scenario_rates'] and not settings.get('scenario_reference'):
            raise ValidationError(_('Scenario rates require a documented reference.'))
        if settings['scenario_rates'] and settings['comparison_mode'] != 'same_rate':
            raise ValidationError(_('A scenario quote supports the common-rate method only; dated actual rates are required for date-specific decomposition.'))
        for field in ('historical_attestation', 'scenario_reference'):
            if settings.get(field) and (not isinstance(settings[field], str) or len(settings[field]) > 2000):
                raise ValidationError(_('Evidence references must be bounded text.'))
            if settings.get(field):
                settings[field] = settings[field].strip()
        context = self.env[CONTEXT]._record({'batch_id': self.id, 'assumptions': settings,
            'source_digest': self._commercial_scope_digest(), 'uom_evidence': {},
            'proposed_by': self.env.uid, 'proposed_at': fields.Datetime.now(),
            'reason': reason.strip(), 'state': 'proposed'})
        self._set({'current_commercial_context_id': context.id})
        invalidate_commercial(self.env)
        return context

    def action_validate_commercial_prices(self):
        self.ensure_one()
        self._check_review_access()
        company_lock(self.env, self.company_id)
        self._lock()
        self.get_structurally_ready_rows()
        try:
            with self.env.cr.savepoint():
                engine = CommercialEngine(self)
                lock_commercial(engine)
                plans = engine.plans()
                for row in self.row_ids:
                    if row.id not in engine.products:
                        continue
                    plan = plans[row.id]
                    old = row.commercial_result_id
                    if old and old.input_digest == plan['fingerprint']:
                        continue
                    result = self.env[RESULT]._record({'batch_id': self.id, 'row_id': row.id,
                        'context_id': self.current_commercial_context_id.id,
                        'structural_result_id': row.current_result_id.id,
                        'product_resolution_id': row.product_resolution_id.id,
                        'product_id': engine.products[row.id].id, 'version': old.version + 1 if old else 1,
                        'previous_id': old.id, 'input_digest': plan['fingerprint'], 'snapshot': plan,
                        'status': plan['status'], 'classification': plan.get('comparison', {}).get('classification') if plan['status'] == 'commercially_valid' else False,
                        'proposal_normalized': plan.get('proposal_normalized', False),
                        'actor_id': self.env.uid, 'validated_at': fields.Datetime.now()})
                    for issue in plan['issues']:
                        self.env[ISSUE]._record(dict(issue, batch_id=self.id, result_id=result.id))
                    row._review_set({'commercial_result_id': result.id})
                self._set({'commercial_processing_state': 'complete', 'commercial_error': False})
        except (SerializationFailure, DeadlockDetected):
            raise
        except (DatabaseError, ValueError, TypeError, RuntimeError, ArithmeticError):
            self._set({'commercial_processing_state': 'failed', 'commercial_error': 'Commercial comparison failed atomically; no partial results were retained. Authorized retry is available.'})
            return False
        invalidate_commercial(self.env)
        return True

    def action_revalidate_commercial_prices(self):
        return self.action_validate_commercial_prices()

    def get_commercially_valid_rows(self):
        self.ensure_one()
        self.check_access('read')
        ready = self.get_product_resolved_rows()
        engine = CommercialEngine(self)
        lock_commercial(engine)
        plans = engine.plans()
        invalidate_commercial(self.env)
        return ready.filtered(lambda r: r._commercial_outcome(plans[r.id]) == 'commercially_valid')

    def resolve_vendor_tier(self, product_id, quantity, quantity_uom_id, date):
        """Read-only explicit-quantity interface; never infer live demand."""
        self.ensure_one()
        self.check_access('read')
        ready = self.get_product_resolved_rows()
        product = self.env['product.product'].browse(product_id)
        product.check_access('read')
        if product not in ready.resolved_product_id or (product.company_id and product.company_id != self.company_id):
            raise AccessError(_('Tier lookup requires this batch\'s current authorized resolved variant.'))
        uom = self.env['uom.uom'].browse(quantity_uom_id)
        uom.check_access('read')
        date = fields.Date.to_date(date)
        engine = CommercialEngine(self)
        extra_ids = {int(i) for i in (uom.parent_path or '').split('/') if i} | set(uom.ids)
        extra = self.env['uom.uom'].browse(sorted(extra_ids))
        engine.uoms |= extra
        engine.by_uom.update({record.id: record for record in extra})
        policy = engine.policy(date)
        if not policy:
            raise UserError(_('A complete published PR04 company policy is required.'))
        lock_commercial(engine)
        return engine.tier(product, quantity, uom, date, policy)

    @api.depends('row_ids.commercial_result_id', 'current_commercial_context_id.state',
                 'current_run_id', 'review_version', 'row_ids.product_resolution_id', 'row_ids.excluded')
    def _compute_commercial_counts(self):
        for batch in self:
            engine = CommercialEngine(batch)
            plans = engine.plans()
            counts = Counter({state: 0 for state, label in STATUSES})
            counts.update(total_rows=len(batch.row_ids), product_eligible_rows=len(engine.products),
                          normalized_proposals=0, issues=0)
            for row in batch.row_ids:
                status = row._commercial_outcome(plans[row.id])
                counts[status] += 1
                if status not in ('stale', 'pending_product', 'excluded') and row.commercial_result_id:
                    result = row.commercial_result_id
                    counts['normalized_proposals'] += int(result.proposal_normalized)
                    counts['issues'] += len(result.issue_ids)
                    if status == 'commercially_valid':
                        counts[result.classification] += 1
            batch.commercial_counts = dict(counts)

    def action_review_commercial_prices(self):
        self.ensure_one()
        self.check_access('read')
        return {'type': 'ir.actions.act_window', 'name': _('Commercial Price Review'), 'res_model': ROW,
            'view_mode': 'list,form', 'views': [(self.env.ref('vendor_price_revision_impact_simulator.view_commercial_rows').id, 'list'), (False, 'form')],
            'search_view_id': self.env.ref('vendor_price_revision_impact_simulator.view_commercial_rows_search').id,
            'domain': [('batch_id', '=', self.id)], 'context': {'commercial_review_batch_id': self.id}}

    def action_open_commercial_context(self):
        self._check_review_access()
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': _('Propose Commercial Interpretation'),
            'res_model': WIZARD, 'view_mode': 'form', 'target': 'new',
            'context': {'default_batch_id': self.id, 'default_company_id': self.company_id.id}}

    def export_data(self, fields_to_export):
        check_product_export(self.commercial_result_ids, fields_to_export)
        return super().export_data(fields_to_export)


class RowCommercial(models.Model):
    _inherit = ROW
    commercial_result_id = fields.Many2one(RESULT, readonly=True, copy=False, ondelete='restrict')
    commercial_status = fields.Selection(STATUSES, compute='_compute_commercial', search='_search_commercial_status')
    commercial_classification = fields.Selection(CLASSIFICATIONS, compute='_compute_commercial', search='_search_commercial_classification')
    commercial_summary = fields.Json(compute='_compute_commercial')
    commercial_old_price = fields.Char(string='Old comparable unit price', compute='_compute_commercial')
    commercial_new_price = fields.Char(string='Proposed comparable unit price', compute='_compute_commercial')
    commercial_delta = fields.Char(string='Verified unit delta', compute='_compute_commercial')
    commercial_percent = fields.Char(string='Company-basis change %', compute='_compute_commercial')
    commercial_supplier_percent = fields.Char(string='Supplier-currency change %', compute='_compute_commercial')
    commercial_fx_method = fields.Char(string='FX comparison basis', compute='_compute_commercial')
    commercial_fx_assumption = fields.Char(string='FX evidence type', compute='_compute_commercial')
    commercial_unit = fields.Char(string='Comparison unit', compute='_compute_commercial')
    commercial_currency = fields.Char(string='Comparison currency', compute='_compute_commercial')
    commercial_min_qty = fields.Char(string='MOQ in comparison unit', compute='_compute_commercial')
    commercial_effective_date = fields.Char(string='Proposed start date', compute='_compute_commercial')

    def _commercial_outcome(self, plan):
        if self.excluded:
            return 'excluded'
        old = self.commercial_result_id
        if old and old.input_digest != plan['fingerprint']:
            return 'stale'
        if plan['status'] == 'pending_product':
            return 'pending_product'
        return old.status if old else 'pending_validation'

    @api.depends('commercial_result_id', 'batch_id.current_run_id', 'batch_id.review_version',
                 'batch_id.current_commercial_context_id.state', 'product_resolution_id', 'excluded')
    def _compute_commercial(self):
        for batch in self.batch_id:
            plans = CommercialEngine(batch).plans()
            for row in self.filtered(lambda r: r.batch_id == batch):
                status = row._commercial_outcome(plans[row.id])
                row.commercial_status = status
                current = row.commercial_result_id if status not in ('stale', 'pending_product', 'excluded') else self.env[RESULT]
                row.commercial_classification = current.classification if current else False
                row.commercial_summary = {k: current.snapshot.get(k) for k in ('proposal', 'baseline', 'comparison', 'issues')} if current else {}
                proposal = current.snapshot.get('proposal', {}) if current else {}
                baseline = current.snapshot.get('baseline', {}) if current else {}
                comparison = current.snapshot.get('comparison', {}) if current and status == 'commercially_valid' else {}
                row.commercial_old_price = baseline.get('company_price') if baseline.get('status') == 'selected' else False
                row.commercial_new_price = proposal.get('company_price')
                row.commercial_delta = comparison.get('delta')
                row.commercial_percent = comparison.get('percent')
                row.commercial_supplier_percent = comparison.get('source_currency_comparison', {}).get('percent')
                row.commercial_fx_method = {'same_rate': 'Common selected FX date', 'date_specific': 'Date-specific: supplier and FX'}.get(comparison.get('method'))
                row.commercial_fx_assumption = ('Hypothetical scenario' if proposal.get('fx', {}).get('hypothetical') else 'Observed reference / same currency') if proposal.get('fx') else False
                row.commercial_unit = proposal.get('uom', {}).get('comparison', {}).get('name')
                row.commercial_currency = proposal.get('company_currency_code')
                row.commercial_min_qty = proposal.get('normalized_min_qty')
                row.commercial_effective_date = proposal.get('effective_date')

    @api.model
    def _commercial_search(self, operator, value, classification=False):
        if operator not in ('=', '!=', 'in', 'not in'):
            return NotImplemented
        values = set(value if operator in ('in', 'not in') else [value])
        scope = [('batch_id', '=', self.env.context['commercial_review_batch_id'])] if self.env.context.get('commercial_review_batch_id') else []
        rows = self.search(scope, limit=20001)
        if len(rows) > 20000:
            raise UserError(_('Open a batch before filtering commercial results.'))
        found = []
        for batch in rows.batch_id:
            plans = CommercialEngine(batch).plans()
            for row in rows.filtered(lambda r: r.batch_id == batch):
                status = row._commercial_outcome(plans[row.id])
                actual = row.commercial_result_id.classification if classification and status == 'commercially_valid' else False if classification else status
                if actual in values:
                    found.append(row.id)
        return [('id', 'not in' if operator in ('!=', 'not in') else 'in', found)]

    @api.model
    def _search_commercial_status(self, operator, value):
        return self._commercial_search(operator, value)

    @api.model
    def _search_commercial_classification(self, operator, value):
        return self._commercial_search(operator, value, True)

    def export_data(self, fields_to_export):
        check_product_export(self.commercial_result_id, fields_to_export)
        return super().export_data(fields_to_export)


class CommercialWizard(models.TransientModel):
    _name = WIZARD
    _inherit = 'vendor.price.revision.intake.read.guard'
    _description = 'Commercial Context Verification (not price approval)'
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    batch_id = fields.Many2one(BATCH, required=True)
    context_id = fields.Many2one(CONTEXT)
    interpretation_summary = fields.Text(related='context_id.interpretation_summary', readonly=True, compute_sudo=False)
    operation = fields.Selection([('propose', 'Propose'), ('verify', 'Verify interpretation'), ('retire', 'Retire interpretation')], default='propose', required=True)
    reason = fields.Char(required=True)
    price_basis = fields.Selection([('unknown', 'Unknown / Review'), ('net_exclusive', 'Supplier net price excluding recoverable taxes'), ('tax_inclusive', 'Tax inclusive / Review')], default='unknown', required=True)
    discount_percent = fields.Char(default='0', required=True)
    baseline_mode = fields.Selection([('day_before', 'Day before proposed start'), ('explicit', 'Explicit old-price date')], default='day_before', required=True)
    baseline_date = fields.Date()
    end_date = fields.Date(string='Proposed inclusive end date')
    comparison_mode = fields.Selection([('same_rate', 'Common selected FX date'), ('date_specific', 'Old baseline FX date and selected proposed FX date')], default='same_rate', required=True)
    alias_ids = fields.One2many(ALIAS_WIZARD, 'wizard_id')
    scenario_currency_id = fields.Many2one('res.currency')
    scenario_rate = fields.Char(string='Company currency per source unit')
    scenario_reference = fields.Char()
    historical_attestation = fields.Text(help='Independent evidence that captured supplier rules represent agreed terms at the historical old-price date. Blank means no historical baseline claim.')

    def export_data(self, fields_to_export):
        check_product_export(self.batch_id.commercial_result_ids, fields_to_export)
        return escape_export(super().export_data(fields_to_export))

    @api.model
    def _check_links(self, values):
        company = self.env['res.company'].browse(values.get('company_id'))
        batch = self.env[BATCH].browse(values.get('batch_id'))
        batch.check_access('read')
        if not batch or company not in self.env.companies or batch.company_id != company:
            raise AccessError(_('Commercial wizard company must match an authorized batch.'))
        if values.get('context_id'):
            context = self.env[CONTEXT].browse(values['context_id'])
            context.check_access('read')
            if context.batch_id != batch:
                raise AccessError(_('Review context must belong to this batch.'))

    @api.model_create_multi
    def create(self, vals_list):
        defaults = self.default_get(['company_id', 'batch_id', 'context_id'])
        prepared = [dict(defaults, **v) for v in vals_list]
        for vals in prepared:
            self._check_links(vals)
            if vals.get('alias_ids') and any(c[0] != 0 for c in vals['alias_ids']):
                raise AccessError(_('Create new alias rows in this wizard.'))
        return super().create(prepared)

    def write(self, vals):
        self.check_access('write')
        for wizard in self:
            links = {k: wizard[k].id for k in ('company_id', 'batch_id', 'context_id')}
            self._check_links(dict(links, **{k: v for k, v in vals.items() if k in links}))
            for command in vals.get('alias_ids', []):
                if command[0] == 0:
                    continue
                if command[0] not in (1, 2, 3) or self.env[ALIAS_WIZARD].browse(command[1]).wizard_id != wizard:
                    raise AccessError(_('Alias edits must belong to this wizard.'))
        return super().write(vals)

    def action_submit(self):
        self.ensure_one()
        self.check_access('write')
        self._check_links({k: self[k].id for k in ('company_id', 'batch_id', 'context_id')})
        if self.operation == 'verify':
            self.context_id.action_verify_context(self.reason)
        elif self.operation == 'retire':
            self.context_id.action_retire_context(self.reason)
        else:
            if len(self.alias_ids.mapped('source_text')) != len(self.alias_ids):
                raise ValidationError(_('Each exact supplier UoM alias can be specified once.'))
            assumptions = {k: self[k] for k in ('price_basis', 'discount_percent', 'baseline_mode', 'comparison_mode', 'scenario_reference', 'historical_attestation')}
            assumptions.update(uom_aliases={r.source_text.strip(): r.uom_id.id for r in self.alias_ids},
                baseline_date=fields.Date.to_string(self.baseline_date), end_date=fields.Date.to_string(self.end_date),
                scenario_rates={self.scenario_currency_id.name: self.scenario_rate} if self.scenario_currency_id else {})
            self.batch_id.action_propose_commercial_context(assumptions, self.reason)
        return {'type': 'ir.actions.act_window_close'}


class CommercialAliasWizard(models.TransientModel):
    _name = ALIAS_WIZARD
    _inherit = 'vendor.price.revision.intake.read.guard'
    _description = 'Explicit Source UoM Interpretation'
    wizard_id = fields.Many2one(WIZARD, required=True, ondelete='cascade')
    company_id = fields.Many2one(related='wizard_id.company_id', store=True, readonly=True)
    source_text = fields.Char(required=True)
    uom_id = fields.Many2one('uom.uom', required=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if set(vals) - {'wizard_id', 'source_text', 'uom_id'}:
                raise AccessError(_('Alias ownership is derived from its wizard.'))
            wizard = self.env[WIZARD].browse(vals.get('wizard_id'))
            wizard.check_access('write')
            if not wizard:
                raise AccessError(_('Select an authorized parent wizard.'))
        return super().create(vals_list)

    def write(self, vals):
        self.wizard_id.check_access('write')
        if set(vals) - {'source_text', 'uom_id'}:
            raise AccessError(_('Alias ownership cannot be reassigned.'))
        return super().write(vals)


class ContextWizardActions(models.Model):
    _inherit = CONTEXT

    def action_open_context_review(self):
        self.ensure_one()
        self.check_access('read')
        return {'type': 'ir.actions.act_window', 'name': _('Verify Commercial Interpretation'),
            'res_model': WIZARD, 'view_mode': 'form', 'target': 'new',
            'context': {'default_batch_id': self.batch_id.id, 'default_context_id': self.id,
                'default_company_id': self.company_id.id, 'default_operation': 'verify'}}
