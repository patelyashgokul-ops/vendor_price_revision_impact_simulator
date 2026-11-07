"""Immutable supply evidence and server-authorized analytical actions."""
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from .import_intake import BATCH, PURCHASE_MANAGER, clean_defaults
from .import_validation import PREFIX as IMPORT_PREFIX, ImmutableReview
from .product_resolution import company_lock
from .structural_validation import digest
from .supply_governance import PREFIX, authorize
from .supply_engine import SupplyEngine, SNAPSHOT, BUCKET, ISSUE, TERMS


class Snapshot(models.Model):
    _name = SNAPSHOT
    _inherit = IMPORT_PREFIX + 'review.guard'
    _description = 'Current-Time Supply Evidence Snapshot (not allocation)'
    _order = 'id desc'
    _unique = models.Constraint('UNIQUE(batch_id,scope_key,version)', 'Supply versions must be unique within a scope.')
    warehouse_ids = fields.Many2many('stock.warehouse', required=True)
    contains_costs = fields.Boolean(required=True)
    scope_key = fields.Char(required=True, index=True)
    version = fields.Integer(required=True)
    previous_id = fields.Many2one(SNAPSHOT, ondelete='restrict')
    input_digest = fields.Char(required=True, index=True)
    collected_at = fields.Datetime(required=True)
    collected_by = fields.Many2one('res.users', required=True)
    state = fields.Selection([('collected', 'Collected'), ('review_required', 'Review required')], required=True)
    quantity_verified = fields.Boolean()
    cost_state = fields.Selection([('not_requested', 'Not requested'), ('reference_only', 'Accounting/agreed references only'),
        ('incomplete', 'Incomplete cost references')], required=True)
    totals = fields.Json(required=True)
    provenance = fields.Json(required=True)
    bucket_ids = fields.One2many(BUCKET, 'snapshot_id')
    issue_ids = fields.One2many(ISSUE, 'snapshot_id')

    def action_check_current(self):
        self.ensure_one(); self.check_access('read')
        engine = SupplyEngine(self.batch_id, self.warehouse_ids.ids, self.contains_costs).build()
        latest = self.search([('batch_id', '=', self.batch_id.id), ('scope_key', '=', self.scope_key)], limit=1)
        current = latest == self and self.input_digest == engine.input_digest
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': 'Supply freshness', 'message': 'Current source evidence' if current else 'STALE or superseded: collect a new snapshot',
            'type': 'success' if current else 'warning', 'sticky': True}}


class SupplyBucket(models.Model):
    _name = BUCKET
    _inherit = IMPORT_PREFIX + 'review.guard'
    _description = 'Non-overlapping Supply Source Bucket'
    _order = 'product_id,warehouse_id,id'
    _unique = models.Constraint('UNIQUE(snapshot_id,source_key)', 'A source contributes only once to a snapshot.')
    snapshot_id = fields.Many2one(SNAPSHOT, required=True, ondelete='restrict', index=True)
    source_key = fields.Char(required=True)
    product_id = fields.Integer(required=True, index=True, string='Exact variant ID')
    product_name = fields.Char(required=True, string='Frozen variant label')
    uom_id = fields.Many2one('uom.uom', required=True, string='Quantity / cost reference unit')
    warehouse_id = fields.Many2one('stock.warehouse', required=True)
    kind = fields.Char(required=True, index=True)
    physical = fields.Char(string='Physical base units')
    reserved = fields.Char(string='Reserved base units')
    unreserved = fields.Char(string='Unreserved base units')
    eligible_free = fields.Char(string='Eligible free base units')
    incoming = fields.Char(string='Supplier-unreceived base units (blank = unknown)')
    protected = fields.Char(string='Verified firm incoming base units')
    contributes_quantity = fields.Boolean()
    quantity_verified = fields.Boolean()
    cost_basis = fields.Char()
    unit_cost_reference = fields.Char(string='Company-currency unit cost reference (blank = unavailable)')
    confidence = fields.Char()
    evidence = fields.Json(required=True)

    def action_open_source(self):
        self.ensure_one(); self.check_access('read')
        authorize(self.batch_id, self.snapshot_id.warehouse_ids.ids, self.snapshot_id.contains_costs)
        prefix, value = self.source_key.split(':')
        model = {'quant': 'stock.quant', 'po_line': 'purchase.order.line', 'transfer': 'stock.move'}.get(prefix)
        if not model: raise UserError(_('Source type cannot be opened.'))
        source = self.env[model].browse(int(value)).exists()
        if not source: raise UserError(_('Source is no longer available.'))
        source.check_access('read')
        if source.company_id != self.company_id: raise AccessError(_('Source company has changed.'))
        # Current projection must still contain the same source in this scope.
        current = SupplyEngine(self.batch_id, self.snapshot_id.warehouse_ids.ids, self.snapshot_id.contains_costs).build()
        if not any(b['source_key'] == self.source_key for b in current.buckets):
            raise AccessError(_('Source is no longer within the approved analytical scope.'))
        return {'type': 'ir.actions.act_window', 'res_model': model, 'res_id': source.id, 'view_mode': 'form'}


class SupplyIssue(models.Model):
    _name = ISSUE
    _inherit = IMPORT_PREFIX + 'review.guard'
    _description = 'Retained Supply Inconsistency'
    snapshot_id = fields.Many2one(SNAPSHOT, required=True, ondelete='restrict', index=True)
    code = fields.Char(required=True, index=True)
    source_key = fields.Char(required=True)
    message = fields.Text(required=True)
    quantity_blocking = fields.Boolean()


class SupplyTerms(models.Model):
    _name = TERMS
    _inherit = IMPORT_PREFIX + 'review.guard'
    _description = 'Independent Incoming Purchase Price Terms Attestation'
    _order = 'id'
    warehouse_id = fields.Many2one('stock.warehouse', required=True)
    po_line_id = fields.Integer(required=True, string='Purchase line ID')
    terms_digest = fields.Char(required=True)
    terms_evidence = fields.Json(required=True)
    classification = fields.Selection([(s, s.replace('_', ' ').title()) for s in
        ('firm', 'unverified', 'disputed', 'amendment_pending')], required=True)
    state = fields.Selection([('proposed', 'Proposed'), ('verified', 'Independently verified')], required=True)
    proposed_by = fields.Many2one('res.users', required=True)
    proposed_at = fields.Datetime(required=True)
    reason = fields.Char(required=True)
    verified_by = fields.Many2one('res.users')
    verified_at = fields.Datetime()
    verification_reason = fields.Char()

    def action_open_verification(self):
        self.ensure_one(); self.check_access('read')
        return {'type': 'ir.actions.act_window', 'res_model': PREFIX+'wizard', 'view_mode': 'form', 'target': 'new',
            'context': {'default_batch_id': self.batch_id.id, 'default_warehouse_ids': [(6, 0, self.warehouse_id.ids)],
                        'default_operation': 'verify', 'default_terms_id': self.id}}

    def action_verify_terms(self, reason=None):
        self.ensure_one(); self.check_access('read')
        if not self.env.user.active or not self.env.user.has_group(PURCHASE_MANAGER):
            raise AccessError(_('Purchase Manager verification required.'))
        if self.proposed_by == self.env.user or self.state != 'proposed' or not reason or not reason.strip():
            raise ValidationError(_('Independent reviewer and verification reason required.'))
        authorize(self.batch_id, self.warehouse_id.ids, True)
        company_lock(self.env, self.company_id); self.batch_id._lock()
        engine = SupplyEngine(self.batch_id, self.warehouse_id.ids, True).build(); engine.lock()
        line = engine.lines.get(self.po_line_id)
        if not line or digest(engine.terms_evidence(line)) != self.terms_digest:
            raise ValidationError(_('PO terms have changed; propose new evidence.'))
        super(ImmutableReview, clean_defaults(self)).write({'state': 'verified', 'verified_by': self.env.uid,
            'verified_at': fields.Datetime.now(), 'verification_reason': reason.strip()})
        return True


class BatchSupply(models.Model):
    _inherit = BATCH
    supply_snapshot_ids = fields.One2many(SNAPSHOT, 'batch_id', readonly=True)

    def action_collect_supply(self, warehouse_ids, costs=True):
        self.ensure_one(); authorize(self, warehouse_ids, costs, prepare=True)
        company_lock(self.env, self.company_id); self._lock()
        # Entire result is transactional. Any source/concurrency failure aborts
        # this savepoint; a failed attempt can never leave a success header.
        with self.env.cr.savepoint():
            engine = SupplyEngine(self, warehouse_ids, costs, prepare=True).build(); engine.lock()
            scope = digest({'warehouses': sorted(set(warehouse_ids)), 'costs': costs})
            previous = self.env[SNAPSHOT].search([('batch_id', '=', self.id), ('scope_key', '=', scope)], limit=1)
            if previous and previous.input_digest == engine.input_digest: return previous
            verified = all(t['quantity_verified'] for t in engine.totals.values())
            cost_incomplete = any(b['evidence'].get('cost', {}).get('state') in ('incomplete', 'unavailable') for b in engine.buckets)
            snapshot = self.env[SNAPSHOT]._record(dict(batch_id=self.id, warehouse_ids=[(6, 0, engine.wh.ids)],
                contains_costs=costs, scope_key=scope, version=(previous.version+1 if previous else 1),
                previous_id=previous.id, input_digest=engine.input_digest, collected_at=fields.Datetime.now(),
                collected_by=self.env.uid, state='review_required' if engine.issues else 'collected',
                quantity_verified=verified, cost_state='not_requested' if not costs else 'incomplete' if cost_incomplete else 'reference_only',
                totals=engine.totals, provenance={'as_of': 'actual current collection time; not historical inventory',
                    'sources': engine.sources, 'reservation_basis': 'quant reserved_quantity subtracted exactly once',
                    'scope': engine.wh.ids, 'normalization': 'exact product base UoM; cost currency is company currency'}))
            for bucket in engine.buckets:
                self.env[BUCKET]._record(dict(bucket, batch_id=self.id, snapshot_id=snapshot.id))
            for issue in engine.issues:
                self.env[ISSUE]._record(dict(issue, batch_id=self.id, snapshot_id=snapshot.id))
            return snapshot

    def get_current_supply(self, warehouse_ids, costs=True):
        self.ensure_one(); authorize(self, warehouse_ids, costs)
        engine = SupplyEngine(self, warehouse_ids, costs).build(); engine.lock()
        scope = digest({'warehouses': sorted(set(warehouse_ids)), 'costs': costs})
        current = self.env[SNAPSHOT].search([('batch_id', '=', self.id), ('scope_key', '=', scope)], limit=1)
        if not current or current.input_digest != engine.input_digest:
            raise UserError(_('Supply snapshot is missing or stale; collect current supply evidence.'))
        return current

    def action_propose_supply_terms(self, warehouse_id, po_line_id, classification, reason):
        self.ensure_one(); authorize(self, [warehouse_id], True, prepare=True)
        if classification not in ('firm', 'unverified', 'disputed', 'amendment_pending') or not reason or not reason.strip():
            raise ValidationError(_('Explicit terms classification and supporting evidence reason required.'))
        company_lock(self.env, self.company_id); self._lock()
        engine = SupplyEngine(self, [warehouse_id], True, prepare=True).build(); engine.lock()
        line = engine.lines.get(po_line_id)
        if not line or engine.orders[line['order_id']]['state'] != 'purchase':
            raise AccessError(_('Only current confirmed PO lines within the approved product/warehouse scope can be attested.'))
        evidence = engine.terms_evidence(line)
        return self.env[TERMS]._record(dict(batch_id=self.id, warehouse_id=warehouse_id, po_line_id=po_line_id,
            terms_digest=digest(evidence), terms_evidence=evidence, classification=classification,
            state='proposed', proposed_by=self.env.uid, proposed_at=fields.Datetime.now(), reason=reason.strip()))

    def action_open_supply_collector(self):
        self._check_review_access()
        return {'type': 'ir.actions.act_window', 'res_model': PREFIX+'wizard', 'view_mode': 'form', 'target': 'new',
            'context': {'default_batch_id': self.id}}


class SupplyWizard(models.TransientModel):
    _name = PREFIX + 'wizard'
    _description = 'Collect Scoped Current Supply / Propose Incoming Terms'
    batch_id = fields.Many2one(BATCH, required=True)
    company_id = fields.Many2one(related='batch_id.company_id', store=True)
    warehouse_ids = fields.Many2many('stock.warehouse', required=True)
    costs = fields.Boolean(default=True)
    operation = fields.Selection([('collect', 'Collect current supply'), ('terms', 'Propose purchase terms'),
        ('verify', 'Independently verify terms')], default='collect', required=True)
    terms_id = fields.Many2one(TERMS)
    po_line_id = fields.Integer(string='Purchase line ID')
    classification = fields.Selection([(s, s.replace('_',' ').title()) for s in ('firm','unverified','disputed','amendment_pending')], default='unverified')
    reason = fields.Char()

    def action_run(self):
        self.ensure_one(); self.check_access('read')
        if self.operation == 'collect':
            result = self.batch_id.action_collect_supply(self.warehouse_ids.ids, self.costs)
        elif self.operation == 'terms':
            self.warehouse_ids.ensure_one()
            result = self.batch_id.action_propose_supply_terms(self.warehouse_ids.id, self.po_line_id, self.classification, self.reason)
        else:
            self.terms_id.ensure_one()
            if self.terms_id.batch_id != self.batch_id:
                raise AccessError(_('Verification must reference this batch.'))
            self.terms_id.action_verify_terms(self.reason)
            result = self.terms_id
        return {'type': 'ir.actions.act_window', 'res_model': result._name, 'res_id': result.id, 'view_mode': 'form'}
