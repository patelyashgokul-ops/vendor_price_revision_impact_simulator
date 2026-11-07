"""Read-only PR13 cost references for one exact PR10 allocation scenario.

Company accounting references are not physical acquisition tracing. In particular
the native FIFO stack never proves a quant/warehouse/SO-to-move association.
"""
from decimal import Decimal, localcontext

from odoo import fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .import_intake import BATCH
from .import_validation import PREFIX as IMPORT_PREFIX
from .product_resolution import company_lock
from .allocation_policy import authorized
from .supply_engine import SupplyEngine
from .commercial_math import number, rounded
from .commercial_engine import POLICY_FIELDS
from .structural_validation import digest

PREFIX = 'vendor.price.revision.cost.'
HEADER, LINE, ISSUE = [PREFIX+s for s in ('snapshot', 'line', 'issue')]
VERSION = 'pr13_company_accounting_reference_no_physical_fifo_mapping_v1'
LIMIT = 10000


def amount(quantity, unit, rounding):
    """Unknown stays null; verified zero remains a real numeric reference."""
    if unit is None:
        return None, None
    with localcontext() as ctx:
        ctx.prec = 38
        value = number(quantity, True) * number(unit, True)
        return str(value), rounded(value, rounding)


class CostEngine:
    def __init__(self, batch, allocation_id, purchase_id=0, procurement_date=None):
        batch.ensure_one()
        if type(allocation_id) is not int or allocation_id <= 0 or type(purchase_id) is not int or purchase_id < 0:
            raise ValidationError('Use exact allocation and optional purchase snapshot IDs.')
        self.batch, self.env = batch, batch.env
        self.allocation = self.env['vendor.price.revision.allocation.snapshot'].browse(allocation_id).exists()
        if not self.allocation:
            raise UserError('A current PR10 scenario is required.')
        self.allocation.check_access('read')
        self.wh = authorized(batch, self.allocation.warehouse_ids.ids, True)
        if self.allocation.batch_id != batch or not self.allocation.contains_costs:
            raise AccessError('Select a cost-authorized allocation for this exact batch.')
        try:
            date = str(fields.Date.to_date(procurement_date)) if procurement_date else None
        except (TypeError, ValueError):
            raise ValidationError('Procurement planning date must be an explicit ISO date.')
        self.scope = dict(allocation_id=allocation_id, purchase_id=purchase_id, procurement_date=date)
        self.company = batch.company_id
        self.reader = SupplyEngine(batch, self.wh.ids, True)
        self.commercial = self.reader.commercial
        self.lines, self.issues, self.pools = [], [], {}

    def issue(self, entry, code, message):
        self.issues.append(dict(allocation_entry_id=entry.id, code=code, message=message))

    def build(self):
        with localcontext() as ctx:
            ctx.prec = 38
            return self._build()

    def _build(self):
        a = self.allocation
        s = a.scope
        if self.batch.get_current_allocation(s['warehouses'], s['costs'], s['horizon'], s['confirmed_ids'], s['quote_ids'], s['portfolio_reason']) != a:
            raise UserError('Allocation is stale; revalidate its existing sources first.')
        self.purchase = self.env['vendor.price.revision.purchase.snapshot']
        if self.scope['purchase_id']:
            p = self.env['vendor.price.revision.purchase.snapshot'].browse(self.scope['purchase_id']).exists()
            p.check_access('read')
            if not p or p.batch_id != self.batch or p.allocation_source_id != a.id or p.contains_bills or set(p.warehouse_ids.ids) != set(self.wh.ids):
                raise AccessError('Use current PR12 evidence for this exact allocation and warehouse scope, without bill detail.')
            purchase_scope = dict(p.scope)
            purchase_scope['warehouse_ids'] = purchase_scope.pop('warehouses')
            if self.batch.get_current_purchase_terms(**purchase_scope) != p:
                raise UserError('Purchase terms are stale.')
            self.purchase = p
        if len(a.entry_ids) > LIMIT:
            raise UserError('Narrow allocation scope before attributing costs.')
        self.reader.build()
        read = self.reader.read
        cid = self.company.id
        pids = sorted(set(a.demand_ids.mapped('product_id')))
        # Fixed, company-bound projection. No generic valuation RPC or re-costing.
        self.products = read('product.product', [('id', 'in', pids), ('company_id', 'in', [False, cid])],
            ['uom_id', 'cost_method', 'standard_price', 'lot_valuated', 'categ_id', 'active', 'write_date'])
        self.manual = read('product.value', [('company_id', '=', cid), ('product_id', 'in', pids)],
            ['product_id', 'lot_id', 'move_id', 'value', 'date', 'description', 'write_date'])
        self.moves = read('stock.move', [('company_id', '=', cid), ('product_id', 'in', pids), ('state', '=', 'done')],
            ['product_id', 'value', 'quantity', 'uom_id', 'date', 'is_in', 'is_out', 'write_date'])
        # Landed cost modules are optional. Capitalized adjustments are already in
        # native move values and are fingerprinted, never added again.
        if 'stock.valuation.adjustment.lines' in self.reader.service:
            model = self.reader.service['stock.valuation.adjustment.lines']
            names = [n for n in ('move_id', 'cost_id', 'additional_landed_cost', 'write_date') if n in model._fields]
            read(model._name, [('move_id', 'in', list(self.moves)), ('cost_id.company_id', '=', cid)], names)
        self.policy = self.commercial.policy(fields.Date.to_date(self.scope['procurement_date']) if self.scope['procurement_date'] else fields.Date.context_today(self.batch))
        if not self.policy:
            raise UserError('A unique complete published company cost policy is required.')
        self.policy_evidence = {n: str(self.policy[n]) if self.policy._fields[n].type == 'date' else self.policy[n] for n in POLICY_FIELDS}
        self.policy_evidence.update(id=self.policy.id, write_date=str(self.policy.write_date))
        proposals = [(r.id, r.commercial_result_id.id, r.commercial_result_id.snapshot) for r in self.reader.rows]
        self.proposals = proposals
        for pid in pids:
            if pid in self.products:
                self.pools[str(pid)] = self.stock_basis(pid)
        incoming_used = {}
        for entry in a.entry_ids.sorted('id'):
            self.attribute(entry, incoming_used)
        if len(self.lines) != len(a.entry_ids) or len({l['allocation_entry_id'] for l in self.lines}) != len(self.lines):
            raise ValidationError('Every PR10 entry must have exactly one cost result.')
        for line in self.lines:
            if sum((number(v['quantity'], True) for v in line['segments']), Decimal(0)) != number(line['quantity'], True):
                raise ValidationError('Cost segment quantities must reconcile to PR10.')
        self.fingerprint = digest(dict(version=VERSION, scope=self.scope, allocation=a.fingerprint,
            purchase=self.purchase.fingerprint if self.purchase else None, sources=self.reader.sources,
            pools=self.pools, policy=self.policy_evidence, proposals=proposals, lines=self.lines, issues=self.issues))
        self.reader.lock()
        authorized(self.batch, self.wh.ids, True)
        return self

    def stock_basis(self, pid):
        p = self.products[pid]
        method = p['cost_method']
        basis = dict(method=method, product_id=pid, scope='company_product', company_id=self.company.id,
            comparison_uom_id=p['uom_id'], currency_id=self.company.currency_id.id,
            unit_cost=None, confidence='unavailable', source_confidence='unavailable',
            landed_cost='Already embedded in recorded valuation; no additional historical charge', layers=[])
        if p['lot_valuated']:
            # A lot ID alone is insufficient. Dedicated reconciled lot lineage is
            # deliberately unsupported rather than using product cost for a lot.
            basis['reason'] = 'LOT_VALUATION_REQUIRES_RECONCILED_LOT_LINEAGE'
            return basis
        cost = number(p['standard_price'])
        if method in ('standard', 'average'):
            history = sorted((v for v in self.manual.values() if v['product_id'] == pid and
                not v['move_id'] and not v['lot_id'] and v['date'] <= fields.Datetime.now().isoformat()),
                key=lambda v: (v['date'], v['id']), reverse=True)
            explicit_zero = bool(history and number(history[0]['value']) == 0 and history[0]['description'])
            if cost < 0 or (cost == 0 and not explicit_zero):
                basis['reason'] = 'ZERO_OR_NEGATIVE_COST_NOT_EVIDENCED'
                return basis
            basis.update(unit_cost=str(cost), confidence='supported_estimate', source_confidence='verified_accounting_basis',
                zero_evidence=explicit_zero, manual_cost_evidence=history,
                reason='Configured Standard Cost reference, not acquisition history' if method == 'standard' else
                'Current native company/product AVCO reference, not warehouse acquisition cost')
            return basis
        if method != 'fifo':
            basis['reason'] = 'UNSUPPORTED_COST_METHOD'
            return basis
        product = self.reader.service['product.product'].with_context(dict(allowed_company_ids=self.company.ids,
            force_company=self.company.id, active_test=False, prefetch_fields=False)).with_company(self.company).browse(pid)
        stack, first = product._get_fifo_stack()
        if len(stack) > LIMIT:
            raise UserError('FIFO evidence exceeds the supported bound.')
        qty, value = Decimal(0), Decimal(0)
        for index, move in enumerate(stack):
            full = number(move._get_valued_qty())
            remaining = number(first) if index == 0 and first else full
            if move.id not in self.moves or move.company_id != self.company or full <= 0 or remaining <= 0 or remaining > full or number(move.value) < 0:
                basis['reason'] = 'FIFO_SOURCE_INCOMPLETE'
                return basis
            part = number(move.value) * remaining / full
            basis['layers'].append(dict(move_id=move.id, quantity=str(remaining), full_quantity=str(full),
                value=str(part), unit_cost=str(part / remaining), source_value=str(move.value)))
            qty += remaining
            value += part
        native_qty = number(product._with_valuation_context().qty_available)
        if qty <= 0 or qty != native_qty:
            basis.update(reason='FIFO_REMAINING_QUANTITY_NOT_RECONCILED', layers=[])
            return basis
        basis.update(reference_quantity=str(qty), reference_value=str(value), reference_unit_cost=str(value / qty),
            source_confidence='verified_accounting_basis', confidence='review_required',
            reason='Company FIFO stack only; physical warehouse/quant/demand lineage is unproved')
        return basis

    def replacement(self, entry):
        date = self.scope['procurement_date']
        evidence = dict(planning_date=date, quantity_basis='single_PR10_entry_no_cross_demand_consolidation',
            buying_quantity=entry.quantity, price_accepted=False)
        if not date:
            return None, 'unavailable', dict(evidence, reason='EXPLICIT_PROCUREMENT_DATE_REQUIRED')
        eligible = []
        for row_id, result_id, snap in self.proposals:
            p = snap['proposal']
            if p['product_id'] == entry.demand_id.product_id and p['comparison_uom_id'] == entry.demand_id.uom_id.id and p['effective_date'] <= date and (not p.get('end_date') or date <= p['end_date']) and number(p['normalized_min_qty']) <= number(entry.quantity):
                eligible.append((number(p['normalized_min_qty']), row_id, result_id, snap))
        if not eligible:
            return None, 'unavailable', dict(evidence, reason='NO_ELIGIBLE_CURRENT_PROPOSAL_DATE_UOM_MOQ')
        top = max(v[0] for v in eligible)
        selected = [v for v in eligible if v[0] == top]
        if len(selected) != 1:
            return None, 'review_required', dict(evidence, reason='AMBIGUOUS_PROPOSAL_TIER')
        _, row_id, result_id, snap = selected[0]
        p = snap['proposal']
        evidence.update(row_id=row_id, commercial_result_id=result_id, proposal=p, baseline=snap.get('baseline'),
            vendor_id=self.batch.vendor_id.id, company_id=self.company.id, hypothetical_buying_quantity=True)
        try:
            currency = self.env['res.currency'].browse(p['source_currency_id'])
            fx_date = self.policy.currency_reference_date if self.policy.currency_rate_policy == 'company_reference_date' else fields.Date.to_date(date)
            fx = self.commercial.fx(currency, fx_date, self.policy)
            cost = number(p['net_comparable'], True) * number(fx['rate'], True)
            evidence.update(fx=fx, fx_date=str(fx_date), zero_evidence=(cost == 0),
                landed_cost='Excluded by published policy; net commercial reference only')
        except ValueError as exc:
            return None, 'unavailable', dict(evidence, reason=str(exc))
        if self.policy.additional_cost_policy != 'exclude':
            return None, 'unavailable', dict(evidence, reason='FUTURE_NONRECOVERABLE_CHARGES_NOT_EVIDENCED')
        return str(cost), 'scenario_assumption', evidence

    def attribute(self, entry, incoming_used):
        unit, confidence, evidence = None, 'unavailable', {}
        kind = entry.allocation_type
        if kind in ('existing_reserved_for_demand', 'eligible_free_stock'):
            pool_key = str(entry.demand_id.product_id)
            evidence = {k: v for k, v in self.pools.get(pool_key, {}).items()
                if k not in ('layers', 'reference_quantity', 'reference_value', 'reference_unit_cost')}
            evidence['pool_key'] = pool_key
            unit, confidence = evidence.get('unit_cost'), evidence.get('confidence', 'unavailable')
        elif kind in ('protected_incoming_po', 'incoming_cost_unverified'):
            key = entry.supply_bucket_id.source_key if entry.supply_bucket_id else ''
            lid = int(key.split(':')[1]) if key.startswith('po_line:') else 0
            rows = self.purchase.line_ids.filtered(lambda l: l.po_line_id == lid) if self.purchase else self.env['vendor.price.revision.purchase.line']
            confidence = 'review_required'
            evidence = dict(reason='CURRENT_EXACT_PR12_PROTECTION_REQUIRED', po_line_id=lid)
            if len(rows) == 1:
                r = rows
                evidence.update(purchase_snapshot_id=self.purchase.id, purchase_line_id=r.id, protection=r.protection_status,
                    amendment_status=r.amendment_status, recorded_company_unit_cost=r.company_unit_price or None,
                    recorded_source_unit_cost=r.normalized_agreed_unit_price or None, source_currency_id=r.source_currency_id.id,
                    price_evidence=r.price_evidence, amendment_alternatives=r.amendment_evidence,
                    protection_evidence=r.protection_evidence, source_digest=r.source_digest)
                used = incoming_used.get(lid, Decimal(0)) + number(entry.quantity, True)
                incoming_used[lid] = used
                if r.product_id == entry.demand_id.product_id and r.vendor_id == self.batch.vendor_id.id and r.warehouse_id == entry.demand_id.warehouse_id and r.comparison_uom_id == entry.demand_id.uom_id and r.commitment_type == 'confirmed' and r.open_qty and used <= number(r.open_qty) and r.valuation_status == 'verified' and r.protection_status == 'protected_verified' and r.amendment_status not in ('amendment_pending', 'disputed') and r.company_unit_price:
                    unit, confidence = r.company_unit_price, 'verified_commercial_basis'
                    evidence.update(reason='CURRENT_PR12_EXACT_PROTECTED_OPEN_TERMS', zero_evidence=number(unit) == 0)
        elif kind == 'new_procurement_requirement':
            unit, confidence, evidence = self.replacement(entry)
        else:
            evidence = dict(reason='PR10_QUANTITY_OR_SOURCE_UNRESOLVED')
        raw, reported = amount(entry.quantity, unit, self.company.currency_id.rounding)
        if unit is None:
            self.issue(entry, evidence.get('reason', 'COST_BASIS_INCOMPLETE'), 'Quantity retained; final selected cost is unavailable or requires review.')
        self.lines.append(dict(batch_id=self.batch.id, allocation_entry_id=entry.id, allocation_type=kind,
            demand_source_key=entry.demand_source_key, product_id=entry.demand_id.product_id,
            warehouse_id=entry.demand_id.warehouse_id.id, comparison_uom_id=entry.demand_id.uom_id.id,
            currency_id=self.company.currency_id.id,
            quantity=entry.quantity, unit_cost=unit, reference_value=raw, reported_value=reported,
            confidence=confidence, evidence=evidence, segments=[dict(quantity=entry.quantity, unit_cost=unit,
                confidence=confidence, capacity_key=entry.capacity_key)],
            quantity_confidence=entry.cost_confidence, source_evidence=entry.source_evidence))


class CostSnapshot(models.Model):
    _name = HEADER
    _inherit = IMPORT_PREFIX+'review.guard'
    _description = 'Immutable Allocation Cost References (not consolidated financial exposure)'
    _order = 'id desc'
    _unique = models.Constraint('UNIQUE(batch_id,scope_key,version)', 'One cost version per exact scenario.')
    name = fields.Char(required=True)
    warehouse_ids = fields.Many2many('stock.warehouse', required=True)
    allocation_id = fields.Many2one('vendor.price.revision.allocation.snapshot', required=True, ondelete='restrict')
    purchase_id = fields.Many2one('vendor.price.revision.purchase.snapshot', ondelete='restrict')
    scope_key = fields.Char(required=True, index=True)
    scope = fields.Json(required=True)
    version = fields.Integer(required=True)
    previous_id = fields.Many2one(HEADER, ondelete='restrict')
    fingerprint = fields.Char(required=True, index=True)
    collected_at = fields.Datetime(required=True)
    collected_by = fields.Many2one('res.users', required=True)
    state = fields.Selection([('attributed', 'References attributed; inspect confidence'), ('review_required', 'Incomplete / review required')], required=True)
    policy_version = fields.Char(required=True)
    provenance = fields.Json(required=True)
    reconciliation = fields.Json(required=True)
    line_ids = fields.One2many(LINE, 'snapshot_id')
    issue_ids = fields.One2many(ISSUE, 'snapshot_id')
    freshness = fields.Selection([('current', 'Current'), ('stale', 'Stale / authorization unavailable')], compute='_freshness')

    def _current(self):
        self.ensure_one()
        self.check_access('read')
        e = CostEngine(self.batch_id, **self.scope).build()
        latest = self.search([('batch_id', '=', self.batch_id.id), ('scope_key', '=', self.scope_key)], limit=1)
        return latest == self and e.fingerprint == self.fingerprint

    def _freshness(self):
        for rec in self:
            try:
                current = rec._current()
            except (UserError, AccessError, ValidationError):
                current = False
            rec.freshness = 'current' if current else 'stale'

    def action_check_current(self):
        if not self._current():
            raise UserError('Cost sources changed or access was revoked. Revalidate upstream evidence and recollect.')
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'message': 'Current cost references; inspect source confidence', 'type': 'success'}}


class CostLine(models.Model):
    _name = LINE
    _inherit = IMPORT_PREFIX+'review.guard'
    _description = 'One Exact PR10 Allocation Cost Result'
    _unique = models.Constraint('UNIQUE(snapshot_id,allocation_entry_id)', 'An allocation contributes only once.')
    snapshot_id = fields.Many2one(HEADER, required=True, ondelete='restrict', index=True)
    allocation_entry_id = fields.Many2one('vendor.price.revision.allocation.entry', required=True, ondelete='restrict')
    allocation_type = fields.Char(required=True)
    demand_source_key = fields.Char(required=True)
    product_id = fields.Integer(required=True)
    warehouse_id = fields.Many2one('stock.warehouse', required=True)
    comparison_uom_id = fields.Many2one('uom.uom', required=True)
    currency_id = fields.Many2one('res.currency', required=True, ondelete='restrict')
    quantity = fields.Char(required=True)
    quantity_confidence = fields.Char(required=True)
    unit_cost = fields.Char(string='Company currency / comparison UoM; blank = unavailable')
    reference_value = fields.Char(string='Controlled source reference; not financial exposure')
    reported_value = fields.Char()
    confidence = fields.Char(required=True)
    evidence = fields.Json(required=True)
    segments = fields.Json(required=True)
    source_evidence = fields.Json(required=True)

    def action_open_source(self):
        self.ensure_one()
        self.check_access('read')
        authorized(self.batch_id, self.snapshot_id.warehouse_ids.ids, True)
        return self.allocation_entry_id.demand_id.action_open_source()

    def action_open_cost_source(self):
        self.ensure_one()
        self.check_access('read')
        authorized(self.batch_id, self.snapshot_id.warehouse_ids.ids, True)
        if not self.snapshot_id._current():
            raise UserError('Revalidate stale cost references before opening current operational sources.')
        if self.allocation_type in ('existing_reserved_for_demand', 'eligible_free_stock'):
            # Company FIFO evidence is not a particular SO-to-move association.
            pool = self.snapshot_id.provenance['stock_pools'].get(self.evidence.get('pool_key'), {})
            ids = [v['move_id'] for v in pool.get('layers', [])]
            model = 'stock.move' if ids else 'product.product'
            ids = ids or [self.product_id]
        elif self.allocation_type in ('protected_incoming_po', 'incoming_cost_unverified'):
            model, ids = 'purchase.order.line', [self.evidence.get('po_line_id', 0)]
        elif self.evidence.get('commercial_result_id'):
            model, ids = 'vendor.price.revision.commercial.validation', [self.evidence['commercial_result_id']]
        else:
            raise UserError('No supported cost source is available.')
        source = self.env[model].browse(ids).exists()
        if len(source) != len(ids):
            raise UserError('Cost source no longer exists.')
        source.check_access('read')
        if 'company_id' in source._fields and any(r.company_id and r.company_id != self.company_id for r in source):
            raise AccessError('Current source is outside the retained company scope.')
        return dict(type='ir.actions.act_window', name='Native cost source / inspect reference scope',
            res_model=model, domain=[('id', 'in', source.ids)], view_mode='list,form')


class CostIssue(models.Model):
    _name = ISSUE
    _inherit = IMPORT_PREFIX+'review.guard'
    _description = 'Retained Cost Attribution Exception'
    snapshot_id = fields.Many2one(HEADER, required=True, ondelete='restrict', index=True)
    allocation_entry_id = fields.Integer(required=True)
    code = fields.Char(required=True, index=True)
    message = fields.Text(required=True)


class BatchCost(models.Model):
    _inherit = BATCH

    def action_attribute_costs(self, allocation_id, purchase_id=0, procurement_date=None):
        self.ensure_one()
        self._check_review_access()
        e = CostEngine(self, allocation_id, purchase_id, procurement_date)
        authorized(self, e.wh.ids, True, prepare=True)
        company_lock(self.env, self.company_id)
        self._lock()
        with self.env.cr.savepoint():
            e.build()
            key = digest(e.scope)
            previous = self.env[HEADER].search([('batch_id', '=', self.id), ('scope_key', '=', key)], limit=1)
            if previous and previous.fingerprint == e.fingerprint:
                return previous
            result = self.env[HEADER]._record(dict(batch_id=self.id, name='Cost references / '+str(allocation_id),
                warehouse_ids=[(6, 0, e.wh.ids)], allocation_id=allocation_id, purchase_id=purchase_id,
                scope_key=key, scope=e.scope, version=previous.version+1 if previous else 1, previous_id=previous.id,
                fingerprint=e.fingerprint, collected_at=fields.Datetime.now(), collected_by=self.env.uid,
                policy_version=VERSION, state='review_required' if e.issues else 'attributed',
                provenance=dict(stock_pools=e.pools, source_digest=digest(e.reader.sources), policy=e.policy_evidence,
                    allocation_fingerprint=e.allocation.fingerprint, purchase_fingerprint=e.purchase.fingerprint if e.purchase else None,
                    semantics='Separate scenario references, no consolidated exposure or margin; company FIFO pools are not warehouse layer consumption.'),
                reconciliation=dict(allocation_entries=len(e.lines), result_entries=len(e.lines), segments_reconcile=True,
                    unknown_cost_entries=sum(l['unit_cost'] is None for l in e.lines), alternatives_additive=False)))
            for row in e.lines:
                self.env[LINE]._record(dict(row, snapshot_id=result.id))
            for issue in e.issues:
                self.env[ISSUE]._record(dict(issue, batch_id=self.id, snapshot_id=result.id))
            return result

    def get_current_costs(self, allocation_id, purchase_id=0, procurement_date=None):
        self.ensure_one()
        e = CostEngine(self, allocation_id, purchase_id, procurement_date).build()
        result = self.env[HEADER].search([('batch_id', '=', self.id), ('scope_key', '=', digest(e.scope))], limit=1)
        if not result or result.fingerprint != e.fingerprint:
            raise UserError('Cost snapshot is missing or stale; recollect current source evidence.')
        return result


class AllocationCostAction(models.Model):
    _inherit = 'vendor.price.revision.allocation.snapshot'

    def action_open_cost_attribution(self):
        self.ensure_one()
        self.check_access('read')
        authorized(self.batch_id, self.warehouse_ids.ids, True, prepare=True)
        return {'type': 'ir.actions.act_window', 'res_model': PREFIX+'wizard', 'view_mode': 'form', 'target': 'new',
                'context': {'default_batch_id': self.batch_id.id, 'default_allocation_source_id': self.id}}


class CostWizard(models.TransientModel):
    _name = PREFIX+'wizard'
    _inherit = 'vendor.price.revision.purchase.wizard.boundary'
    _description = 'Cost Reference Collection Inputs'
    batch_id = fields.Many2one(BATCH, required=True)
    company_id = fields.Many2one(related='batch_id.company_id', store=True)
    allocation_source_id = fields.Integer(required=True, string='Exact PR10 allocation ID')
    purchase_source_id = fields.Integer(string='Exact PR12 snapshot ID (without bill detail)')
    procurement_date = fields.Date(string='Explicit hypothetical procurement date')

    def action_run(self):
        self.ensure_one()
        self.check_access('read')
        result = self.batch_id.action_attribute_costs(self.allocation_source_id, self.purchase_source_id, self.procurement_date)
        return {'type': 'ir.actions.act_window', 'res_model': HEADER, 'res_id': result.id, 'view_mode': 'form'}
