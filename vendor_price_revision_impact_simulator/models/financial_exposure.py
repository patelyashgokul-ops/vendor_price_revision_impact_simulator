"""Comparable financial scenarios over existing PR10/11/12/13 evidence.

No source allocation, procurement, valuation, revenue, margin or approval actions.
Amounts are projected scenario references, never recognized expenses or savings.
"""
from collections import defaultdict
from decimal import Decimal, localcontext

from odoo import fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .import_intake import BATCH, PURCHASE_USER
from .import_validation import PREFIX as IMPORT_PREFIX
from .allocation_policy import authorized as cost_authorized
from .sales_exposure import authorized as sales_authorized
from .commercial_engine import CommercialEngine, supplier_snapshot
from .commercial_math import number, rounded, decomposition
from .product_resolution import company_lock
from .structural_validation import digest

PREFIX = 'vendor.price.revision.financial.'
HEADER, LINE, ISSUE = [PREFIX+s for s in ('snapshot', 'line', 'issue')]
VERSION = 'pr14_same_allocation_independent_old_tier_explicit_fx_nullable_cost_v1'
STATES = ('fully_verified', 'verified_incremental_only', 'partially_verified', 'estimated', 'scenario_only', 'incomplete')
FINANCE = 'vendor_price_revision_impact_simulator.group_vpr_finance_manager'
LIMIT = 10000


def cost_direction(delta):
    if delta is None:
        return 'not_calculable'
    value = number(delta)
    return 'cost_increase' if value > 0 else 'potential_cost_reduction' if value < 0 else 'unchanged'


def calculate(quantity, baseline, revised, unchanged=False):
    """38-digit signed arithmetic. Unchanged unknown is delta-only, not zero cost."""
    with localcontext() as ctx:
        ctx.prec = 38
        q = number(quantity, True)
        b = number(baseline, True) if baseline is not None else None
        r = number(revised, True) if revised is not None else None
        be, re = q*b if b is not None else None, q*r if r is not None else None
        delta = re-be if be is not None and re is not None else Decimal(0) if unchanged else None
        unit = r-b if b is not None and r is not None else Decimal(0) if unchanged else None
        result = {k: str(v) if v is not None else None for k, v in dict(
            baseline_unit_cost=b, revised_unit_cost=r, baseline_extended_cost=be,
            revised_extended_cost=re, incremental_unit_cost=unit, incremental_extended_cost=delta).items()}
        result['direction'] = cost_direction(delta)
        return result


def prepare_allowed(batch):
    batch.ensure_one()
    batch.check_access('read')
    env = batch.env
    if not env.su and (not env.user.active or not (env.user.has_group(PURCHASE_USER) or env.user.has_group(FINANCE))):
        raise AccessError('An authorized purchase preparer or Finance Manager is required.')
    if batch.state != 'extracted' or batch.revision_id.state != 'draft':
        raise UserError('Financial simulation requires an extracted editable draft revision.')
    if not env.su and env.user.has_group(PURCHASE_USER):
        batch._check_review_access()


class FinancialEngine:
    def __init__(self, batch, cost_id, sales_id, confirmed_id=0, fx_method='same_rate'):
        if any(type(v) is not int or v < 0 for v in (cost_id, sales_id, confirmed_id)) or not cost_id or not sales_id:
            raise ValidationError('Select exact cost and sales snapshots and one optional confirmed financial baseline.')
        if fx_method not in ('same_rate', 'date_specific'):
            raise ValidationError('Choose the explicit common-rate or separate-date FX methodology.')
        self.batch, self.env = batch, batch.env
        self.scope = dict(cost_id=cost_id, sales_id=sales_id, confirmed_id=confirmed_id, fx_method=fx_method)
        self.cost = self.env['vendor.price.revision.cost.snapshot'].browse(cost_id).exists()
        self.sales = self.env['vendor.price.revision.sales.snapshot'].browse(sales_id).exists()
        if not self.cost or not self.sales:
            raise UserError('Both upstream snapshots must exist.')
        self.cost.check_access('read')
        self.sales.check_access('read')
        self.a = self.cost.allocation_id
        self.company = batch.company_id
        if self.cost.batch_id != batch or self.sales.batch_source_id != batch.id or self.sales.allocation_source_id != self.a.id or self.sales.company_id != self.company:
            raise AccessError('Financial inputs must belong to the same exact batch/company/allocation.')
        self.wh = cost_authorized(batch, self.a.warehouse_ids.ids, True)
        sales_authorized(self.env, self.company, self.wh, self.sales.order_ids)
        self.lines, self.issues, self.baseline_cache = [], [], {}

    def issue(self, entry_id, code, message):
        self.issues.append(dict(allocation_entry_id=entry_id, code=code, message=message))

    def build(self):
        with localcontext() as ctx:
            ctx.prec = 38
            return self._build()

    def _build(self):
        if self.batch.get_current_costs(**self.cost.scope) != self.cost:
            raise UserError('Cost attribution is superseded.')
        if self.a.get_current_sales_terms(self.sales.fx_date) != self.sales:
            raise UserError('Sales classification is superseded.')
        self.commercial = CommercialEngine(self.batch)
        self.rows = self.batch.get_commercially_valid_rows()
        self.proposals = [(r.id, r.commercial_result_id.id, r.commercial_result_id.snapshot) for r in self.rows]
        if len(self.cost.line_ids) > LIMIT:
            raise UserError('Narrow the financial scenario before calculating.')
        if set(self.cost.line_ids.mapped('allocation_entry_id').ids) != set(self.a.entry_ids.ids) or len(self.cost.line_ids) != len(self.a.entry_ids):
            raise ValidationError('Cost evidence must cover every allocation entry exactly once.')
        self.classification = {r.allocation_demand_source_id: r for r in self.sales.line_ids}
        if set(self.classification) != set(self.a.demand_ids.ids):
            raise ValidationError('Every exact demand needs a current PR11 classification.')
        for d in self.a.demand_ids:
            sl = self.classification[d.id]
            if sl.sale_line_id.id != d.sale_line_id or sl.product_id.id != d.product_id or sl.demand_type != d.demand_type or sl.comparison_uom_id != d.uom_id or (d.outstanding and sl.outstanding_qty and number(d.outstanding) != number(sl.outstanding_qty)):
                raise ValidationError('Demand identity, classification, quantity or comparison UoM differs between sources.')
        self.quantity_unresolved = [d.id for d in self.a.demand_ids if d.status == 'unresolved' or not d.outstanding]
        for did in self.quantity_unresolved:
            self.issue(0, 'QUANTITY_UNVERIFIED', 'Demand '+str(did)+' has unresolved quantity; totals cannot be complete.')
        for cost in self.cost.line_ids.sorted(lambda l: l.allocation_entry_id.id):
            self.line(cost)
        self.aggregate()
        self.confirmed = self.env[HEADER]
        self.conditional_effect = None
        if self.a.scenario != 'confirmed_baseline':
            self.confirmed = self.env[HEADER].browse(self.scope['confirmed_id']).exists()
            if not self.confirmed:
                raise UserError('A quotation scenario needs its current confirmed financial baseline; alternatives are not additive.')
            self.confirmed.check_access('read')
            c = self.confirmed
            if c.batch_id != self.batch or c.cost_id.allocation_id != self.a.baseline_id or c.fx_method != self.scope['fx_method'] or c.cost_id.scope['procurement_date'] != self.cost.scope['procurement_date'] or set(c.warehouse_ids.ids) != set(self.wh.ids):
                raise ValidationError('Conditional difference requires identical company, confirmed scope, date and FX assumptions.')
            if self.batch.get_current_financial_exposure(**c.scope) != c:
                raise UserError('Confirmed financial baseline is stale.')
            if self.delta_complete and c.delta_complete:
                self.conditional_effect = str(number(self.totals['incremental_total'])-number(c.incremental_total))
        elif self.scope['confirmed_id']:
            raise ValidationError('A confirmed baseline cannot contain a quotation/alternative financial reference.')
        # Explicitly protect all current vendor terms, including tiers that were
        # ineligible at the PR08 row MOQ but eligible at this PR10 entry quantity.
        self.supplier_evidence = [supplier_snapshot(r) for r in self.commercial.suppliers]
        self.fingerprint = digest(dict(version=VERSION, scope=self.scope, cost=self.cost.fingerprint,
            sales=self.sales.fingerprint, confirmed=self.confirmed.fingerprint if self.confirmed else None,
            policy=self.cost.provenance['policy'], suppliers=self.supplier_evidence,
            lines=self.lines, issues=self.issues, totals=self.totals, groups=self.groups,
            conditional_effect=self.conditional_effect, unresolved_demands=self.quantity_unresolved))
        self.env.flush_all()
        if self.commercial.suppliers:
            self.env.cr.execute('SELECT id FROM product_supplierinfo WHERE id IN %s ORDER BY id FOR SHARE', [tuple(self.commercial.suppliers.ids)])
        cost_authorized(self.batch, self.wh.ids, True)
        sales_authorized(self.env, self.company, self.wh, self.sales.order_ids)
        return self

    def baseline(self, cost):
        entry = cost.allocation_entry_id
        date = self.cost.scope['procurement_date']
        evidence = dict(quantity_basis='same_single_PR10_entry_no_cross_demand_consolidation', quantity=cost.quantity,
            planning_date=date, fx_method=self.scope['fx_method'], counterfactual='pre_revision_terms_without_accepting_proposal', buying_quantity_hypothetical=True)
        if not date:
            return None, None, dict(evidence, reason='PROCUREMENT_DATE_UNCERTAIN')
        candidates = [v for v in self.proposals if v[2]['proposal']['product_id'] == cost.product_id]
        selected = [v for v in candidates if v[1] == cost.evidence.get('commercial_result_id')]
        before = bool(candidates and date < min(v[2]['proposal']['effective_date'] for v in candidates))
        if not selected and before:
            selected = [min(candidates, key=lambda v: (v[2]['proposal']['effective_date'], v[0]))]
        if len(selected) != 1:
            return None, None, dict(evidence, reason='REVISED_PRICE_APPLICABILITY_UNVERIFIED')
        row_id, result_id, snap = selected[0]
        baseline_date = fields.Date.to_date(date if before else snap['baseline_date'])
        planning_date = fields.Date.to_date(date)
        policy = self.commercial.policy(planning_date)
        evidence.update(row_id=row_id, commercial_result_id=result_id, comparison_uom_id=cost.comparison_uom_id.id,
            proposal=snap['proposal'], verified_row_baseline=snap['baseline'], baseline_date=str(baseline_date),
            timing='before_revision_effective_date' if before else 'after_revision_effective_date',
            historical_attestation=self.commercial.settings.get('historical_attestation'))
        if not policy or not self.commercial.context_valid or snap['baseline'].get('status') != 'selected':
            return None, None, dict(evidence, reason='VENDOR_BASELINE_NOT_VERIFIED')
        if baseline_date < self.commercial.today and not self.commercial.settings.get('historical_attestation'):
            return None, None, dict(evidence, reason='HISTORICAL_BASELINE_NOT_ATTESTED')
        key = (cost.product_id, cost.quantity, cost.comparison_uom_id.id, str(baseline_date), policy.id)
        if key not in self.baseline_cache:
            product = self.commercial.product_records.browse(cost.product_id)
            self.baseline_cache[key] = self.commercial.tier(product, cost.quantity, cost.comparison_uom_id, baseline_date, policy)
        tier = self.baseline_cache[key]
        evidence['applicable_old_tier'] = tier
        if tier['status'] != 'selected':
            return None, None, dict(evidence, reason=tier.get('code') or 'BASELINE_COST_MISSING')
        try:
            currency = self.env['res.currency'].browse(tier['selected']['currency_id'])
            common_date = fields.Date.to_date(cost.evidence.get('fx_date') or
                (str(policy.currency_reference_date) if policy.currency_rate_policy == 'company_reference_date' else date))
            old_date = fields.Date.to_date(snap['baseline'].get('fx', {}).get('requested_date') or baseline_date) if self.scope['fx_method'] == 'date_specific' and not before else common_date
            old_fx = self.commercial.fx(currency, old_date, policy)
            old = number(tier['net_comparable'], True)*number(old_fx['rate'], True)
            evidence.update(old_fx=old_fx, old_fx_date=str(old_date), source_currency_id=currency.id,
                source_old_unit=tier['net_comparable'], comparison_currency_id=self.company.currency_id.id,
                baseline_currency_rounding=str(self.company.currency_id.rounding))
        except ValueError as exc:
            return None, None, dict(evidence, reason=str(exc))
        if before:
            evidence.update(effect='proposal_not_yet_applicable', changed_assumptions=False)
            return str(old), str(old), evidence
        revised = cost.unit_cost if cost.unit_cost else None
        evidence.update(new_fx=cost.evidence.get('fx'), revised_cost_source=cost.evidence,
            changed_assumptions=self.scope['fx_method'] == 'date_specific', buying_quantity_hypothetical=True)
        if revised is None:
            evidence['reason'] = 'REVISED_COST_MISSING'
        return str(old), revised, evidence

    def line(self, cost):
        entry = cost.allocation_entry_id
        d = entry.demand_id
        if cost.quantity != entry.quantity or cost.comparison_uom_id != d.uom_id or cost.currency_id != self.company.currency_id:
            raise ValidationError('Source quantity, UoM or currency does not match exact cost attribution.')
        kind = cost.allocation_type
        b = r = cost.unit_cost if cost.unit_cost else None
        evidence = dict(cost_evidence=cost.evidence, cost_snapshot_version=self.cost.version,
            sales_classification_id=self.classification[d.id].id, sales_snapshot_version=self.sales.version)
        unchanged = kind in ('existing_reserved_for_demand', 'eligible_free_stock')
        confidence = cost.confidence
        price_effect = fx_effect = None
        method = 'unchanged_existing_accounting_source' if unchanged else 'protected_existing_commitment'
        if kind == 'new_procurement_requirement':
            b, r, basis = self.baseline(cost)
            evidence['pricing'] = basis
            unchanged = bool(basis.get('timing') == 'before_revision_effective_date' and b is not None)
            confidence = 'unavailable' if b is None or r is None else 'scenario_assumption'
            method = 'common_rate_supplier_price_reference' if self.scope['fx_method'] == 'same_rate' else 'combined_supplier_price_and_fx_reference'
            if b is not None and r is not None:
                old_fx, new_fx = basis['old_fx'], basis.get('new_fx') or basis['old_fx']
                if unchanged:
                    price_effect = fx_effect = '0'
                elif basis['source_currency_id'] == basis['proposal']['source_currency_id']:
                    parts = decomposition(basis['source_old_unit'], basis['proposal']['net_comparable'], old_fx['rate'], new_fx['rate'])
                    price_effect = str(number(parts['supplier_component'])*number(cost.quantity))
                    fx_effect = str(number(parts['fx_component'])*number(cost.quantity))
                    evidence['decomposition'] = parts
                else:
                    method = 'changed_source_currency_terms_comparable_total_only'
        elif kind in ('protected_incoming_po', 'incoming_cost_unverified'):
            unchanged = cost.confidence == 'verified_commercial_basis' and b is not None
            if not unchanged:
                b = r = None
                method = 'unverified_incoming_po_not_accepted_amendment'
        elif kind == 'unresolved':
            b = r = None
            unchanged = False
            method = 'unresolved_source'
        if d.id in self.quantity_unresolved:
            b = r = None
            unchanged = False
        result = calculate(cost.quantity, b, r, unchanged)
        complete = b is not None and r is not None
        delta_known = result['incremental_extended_cost'] is not None
        verified_delta = bool(delta_known and unchanged)
        if unchanged:
            price_effect = fx_effect = '0'
        status = 'fully_verified' if complete and confidence == 'verified_commercial_basis' else 'estimated' if complete and confidence == 'supported_estimate' else 'scenario_only' if complete else 'verified_incremental_only' if verified_delta else 'incomplete'
        codes = []
        if not complete:
            code = evidence.get('pricing', {}).get('reason') or ('PO_PROTECTION_UNVERIFIED' if kind in ('protected_incoming_po', 'incoming_cost_unverified') else 'COST_ATTRIBUTION_INCOMPLETE')
            codes.append(code)
            self.issue(entry.id, code, 'Known allocation is retained. Unavailable costs are not zero; inspect source evidence.')
        reported = {k: rounded(result[k], self.company.currency_id.rounding) if result[k] is not None else None
            for k in ('baseline_extended_cost', 'revised_extended_cost', 'incremental_extended_cost')}
        if price_effect is not None and fx_effect is not None and delta_known:
            if abs(number(price_effect)+number(fx_effect)-number(result['incremental_extended_cost'])) > number(self.company.currency_id.rounding):
                raise ValidationError('TOTAL_RECONCILIATION_MISMATCH: explicit price/FX components do not reconcile.')
        self.lines.append(dict(batch_id=self.batch.id, allocation_entry_id=entry.id, cost_line_id=cost.id,
            demand_source_key=entry.demand_source_key, sale_line_id=d.sale_line_id, sale_order_id=d.sale_order_id,
            order_name=d.order_name, product_name=d.product_name,
            product_id=cost.product_id, vendor_id=self.batch.vendor_id.id, warehouse_id=d.warehouse_id.id,
            comparison_uom_id=cost.comparison_uom_id.id, currency_id=cost.currency_id.id, quantity=cost.quantity,
            demand_type=d.demand_type, source_type=kind, capacity_key=entry.capacity_key,
            **result, status=status, cost_complete=complete, delta_complete=delta_known, verified_delta=verified_delta,
            cost_confidence=confidence, delta_method=method, supplier_price_component=price_effect, fx_component=fx_effect,
            reported_values=reported, evidence=evidence, issue_codes=codes))

    def aggregate(self):
        if len({l['allocation_entry_id'] for l in self.lines}) != len(self.lines):
            raise ValidationError('ALLOCATION_DUPLICATE: a source entry cannot contribute twice.')
        cost_quantities = {c.allocation_entry_id.id: number(c.quantity) for c in self.cost.line_ids}
        if any(number(l['quantity']) != cost_quantities[l['allocation_entry_id']] for l in self.lines):
            raise ValidationError('Financial quantities must exactly reconcile to PR10/PR13.')
        groups = defaultdict(list)
        for line in self.lines:
            groups[(line['product_id'], line['warehouse_id'], line['comparison_uom_id'], line['demand_type'])].append(line)
        self.groups = []
        for (pid, wid, uid, demand), lines in sorted(groups.items()):
            q = sum((number(l['quantity']) for l in lines), Decimal(0))
            complete = all(l['cost_complete'] for l in lines)
            b = sum((number(l['baseline_extended_cost']) for l in lines), Decimal(0)) if complete else None
            r = sum((number(l['revised_extended_cost']) for l in lines), Decimal(0)) if complete else None
            self.groups.append(dict(product_id=pid, warehouse_id=wid, uom_id=uid, demand_type=demand, quantity=str(q),
                incomplete_quantity=str(sum((number(l['quantity']) for l in lines if not l['cost_complete']), Decimal(0))),
                baseline_total=str(b) if b is not None else None, revised_total=str(r) if r is not None else None,
                baseline_weighted_unit=str(b/q) if b is not None and q else None,
                revised_weighted_unit=str(r/q) if r is not None and q else None,
                allocation_entry_ids=[l['allocation_entry_id'] for l in lines]))
        self.cost_complete = not self.quantity_unresolved and all(l['cost_complete'] for l in self.lines)
        self.delta_complete = not self.quantity_unresolved and all(l['delta_complete'] for l in self.lines)
        self.totals = {}
        for name, field in (('baseline_total', 'baseline_extended_cost'), ('revised_total', 'revised_extended_cost'), ('incremental_total', 'incremental_extended_cost')):
            complete = self.delta_complete if name == 'incremental_total' else self.cost_complete
            self.totals[name] = str(sum((number(l[field]) for l in self.lines), Decimal(0))) if complete else None
        self.totals['partial_comparable_delta'] = str(sum((number(l['incremental_extended_cost']) for l in self.lines if l['delta_complete']), Decimal(0))) if any(l['delta_complete'] for l in self.lines) else None
        self.totals['verified_partial_delta'] = str(sum((number(l['incremental_extended_cost']) for l in self.lines if l['verified_delta']), Decimal(0))) if any(l['verified_delta'] for l in self.lines) else None
        if self.cost_complete:
            residual = number(self.totals['revised_total'])-number(self.totals['baseline_total'])-number(self.totals['incremental_total'])
            if abs(residual) > number(self.company.currency_id.rounding):
                raise ValidationError('TOTAL_RECONCILIATION_MISMATCH: no balancing line is permitted.')
        else:
            residual = None
        self.rounding = {}
        quantum = number(self.company.currency_id.rounding)
        for key, field in (('baseline_total', 'baseline_extended_cost'), ('revised_total', 'revised_extended_cost'), ('incremental_total', 'incremental_extended_cost')):
            raw = self.totals[key]
            reported = rounded(raw, quantum) if raw is not None else None
            line_sum = sum((number(l['reported_values'][field]) for l in self.lines), Decimal(0)) if raw is not None else None
            difference = number(reported)-line_sum if reported is not None else None
            if difference is not None and abs(difference) > quantum*(len(self.lines)+1)/2:
                raise ValidationError('ROUNDING_DIFFERENCE_EXCESSIVE: inspect raw values; no adjustment is created.')
            self.rounding[key] = dict(raw=raw, reported=reported, sum_reported_lines=str(line_sum) if line_sum is not None else None,
                reporting_residual=str(difference) if difference is not None else None)
        self.reconciliation = dict(allocation_entries=len(self.a.entry_ids), cost_entries=len(self.cost.line_ids),
            financial_entries=len(self.lines), quantity_groups=self.groups, quantities_reconciled=True,
            raw_cost_identity_residual=str(residual) if residual is not None else None, rounding=self.rounding,
            unresolved_demand_ids=self.quantity_unresolved, alternatives_additive=False, no_eligible_demand=not self.a.demand_ids)
        if self.cost_complete:
            self.state = 'scenario_only' if any(l['status'] == 'scenario_only' for l in self.lines) else 'estimated' if any(l['status'] == 'estimated' for l in self.lines) else 'fully_verified'
        else:
            self.state = 'verified_incremental_only' if self.delta_complete and all(l['verified_delta'] for l in self.lines) else 'partially_verified' if any(l['delta_complete'] for l in self.lines) else 'incomplete'


class FinancialSnapshot(models.Model):
    _name = HEADER
    _inherit = IMPORT_PREFIX+'review.guard'
    _description = 'Immutable Projected Financial Exposure (not expense, savings or margin)'
    _order = 'id desc'
    _unique = models.Constraint('UNIQUE(batch_id,scope_key,version)', 'One financial version per exact source scenario.')
    name = fields.Char(required=True)
    warehouse_ids = fields.Many2many('stock.warehouse', required=True)
    order_ids = fields.Many2many('sale.order')
    cost_id = fields.Many2one('vendor.price.revision.cost.snapshot', required=True, ondelete='restrict')
    sales_id = fields.Many2one('vendor.price.revision.sales.snapshot', required=True, ondelete='restrict')
    confirmed_id = fields.Many2one(HEADER, ondelete='restrict')
    scenario = fields.Char(required=True)
    fx_method = fields.Char(required=True)
    currency_id = fields.Many2one('res.currency', required=True, ondelete='restrict')
    scope = fields.Json(required=True)
    scope_key = fields.Char(required=True, index=True)
    version = fields.Integer(required=True)
    previous_id = fields.Many2one(HEADER, ondelete='restrict')
    fingerprint = fields.Char(required=True, index=True)
    policy_version = fields.Char(required=True)
    collected_at = fields.Datetime(required=True)
    collected_by = fields.Many2one('res.users', required=True)
    state = fields.Selection([(s, s.replace('_', ' ').title()) for s in STATES], required=True)
    cost_complete = fields.Boolean()
    delta_complete = fields.Boolean()
    line_count = fields.Integer()
    complete_cost_line_count = fields.Integer()
    incomplete_cost_line_count = fields.Integer()
    baseline_total = fields.Char(string='Comparable scenario baseline; blank = unavailable')
    revised_total = fields.Char(string='Comparable scenario revised; blank = unavailable')
    incremental_total = fields.Char(string='Projected signed scenario delta; blank = unavailable')
    direction = fields.Char(required=True)
    partial_comparable_delta = fields.Char(string='Known subset projected delta; never full total')
    verified_partial_delta = fields.Char(string='Verified unchanged subset delta; never full total')
    conditional_incremental_delta = fields.Char(string='Scenario delta minus confirmed delta; not additive')
    reconciliation = fields.Json(required=True)
    provenance = fields.Json(required=True)
    line_ids = fields.One2many(LINE, 'snapshot_id')
    issue_ids = fields.One2many(ISSUE, 'snapshot_id')
    freshness = fields.Selection([('current', 'Current'), ('stale', 'Stale / authorization unavailable')], compute='_freshness')

    def _current(self):
        self.ensure_one()
        self.check_access('read')
        e = FinancialEngine(self.batch_id, **self.scope).build()
        latest = self.search([('batch_id', '=', self.batch_id.id), ('scope_key', '=', self.scope_key)], limit=1)
        return latest == self and e.fingerprint == self.fingerprint

    def _freshness(self):
        cache = {}
        for rec in self:
            key = (rec.batch_id.id, rec.scope_key)
            if key not in cache:
                try:
                    rec.check_access('read')
                    e = FinancialEngine(rec.batch_id, **rec.scope).build()
                    latest = self.search([('batch_id', '=', rec.batch_id.id), ('scope_key', '=', rec.scope_key)], limit=1)
                    cache[key] = (e.fingerprint, latest.id)
                except (AccessError, UserError, ValidationError):
                    cache[key] = (None, 0)
            fingerprint, latest_id = cache[key]
            rec.freshness = 'current' if latest_id == rec.id and fingerprint == rec.fingerprint else 'stale'

    def action_check_current(self):
        if not self._current():
            raise UserError('Financial sources changed or access was revoked. Revalidate upstream evidence before recalculation.')
        return dict(type='ir.actions.client', tag='display_notification', params=dict(message='Current financial references; inspect completeness and scenario assumptions', type='success'))


class FinancialLine(models.Model):
    _name = LINE
    _inherit = IMPORT_PREFIX+'review.guard'
    _description = 'One Exact Allocation Financial Contribution'
    _unique = models.Constraint('UNIQUE(snapshot_id,allocation_entry_id)', 'One contribution per allocation, never duplicate exposure.')
    snapshot_id = fields.Many2one(HEADER, required=True, ondelete='restrict', index=True)
    allocation_entry_id = fields.Many2one('vendor.price.revision.allocation.entry', required=True, ondelete='restrict')
    cost_line_id = fields.Many2one('vendor.price.revision.cost.line', required=True, ondelete='restrict')
    demand_source_key = fields.Char(required=True)
    sale_line_id = fields.Integer(required=True)
    sale_order_id = fields.Integer(required=True)
    order_name = fields.Char(required=True)
    product_name = fields.Char(required=True)
    product_id = fields.Integer(required=True)
    vendor_id = fields.Integer(required=True)
    warehouse_id = fields.Many2one('stock.warehouse', required=True)
    comparison_uom_id = fields.Many2one('uom.uom', required=True)
    currency_id = fields.Many2one('res.currency', required=True, ondelete='restrict')
    quantity = fields.Char(required=True)
    demand_type = fields.Selection([('confirmed', 'Confirmed commitment'), ('conditional', 'Conditional quotation')], required=True)
    source_type = fields.Char(required=True)
    capacity_key = fields.Char(required=True)
    baseline_unit_cost = fields.Char()
    revised_unit_cost = fields.Char()
    baseline_extended_cost = fields.Char()
    revised_extended_cost = fields.Char()
    incremental_unit_cost = fields.Char()
    incremental_extended_cost = fields.Char()
    direction = fields.Char(required=True)
    status = fields.Selection([(s, s.replace('_', ' ').title()) for s in STATES], required=True)
    cost_complete = fields.Boolean()
    delta_complete = fields.Boolean()
    verified_delta = fields.Boolean()
    cost_confidence = fields.Char(required=True)
    delta_method = fields.Char(required=True)
    supplier_price_component = fields.Char()
    fx_component = fields.Char()
    reported_values = fields.Json(required=True)
    evidence = fields.Json(required=True)
    issue_codes = fields.Json()

    def action_open_demand(self):
        self.ensure_one()
        self.check_access('read')
        return self.cost_line_id.action_open_source()

    def action_open_cost_source(self):
        self.ensure_one()
        self.check_access('read')
        return self.cost_line_id.action_open_cost_source()


class FinancialIssue(models.Model):
    _name = ISSUE
    _inherit = IMPORT_PREFIX+'review.guard'
    _description = 'Retained Financial Completeness Exception'
    snapshot_id = fields.Many2one(HEADER, required=True, ondelete='restrict', index=True)
    allocation_entry_id = fields.Integer()
    code = fields.Char(required=True, index=True)
    message = fields.Text(required=True)


class BatchFinancial(models.Model):
    _inherit = BATCH

    def action_calculate_financial_exposure(self, cost_id, sales_id, confirmed_id=0, fx_method='same_rate'):
        self.ensure_one()
        prepare_allowed(self)
        e = FinancialEngine(self, cost_id, sales_id, confirmed_id, fx_method)
        company_lock(self.env, self.company_id)
        self._lock()
        with self.env.cr.savepoint():
            e.build()
            key = digest(e.scope)
            previous = self.env[HEADER].search([('batch_id', '=', self.id), ('scope_key', '=', key)], limit=1)
            if previous and previous.fingerprint == e.fingerprint:
                return previous
            result = self.env[HEADER]._record(dict(batch_id=self.id, name='Projected financial exposure / '+str(e.a.id),
                warehouse_ids=[(6, 0, e.wh.ids)], order_ids=[(6, 0, e.sales.order_ids.ids)], cost_id=cost_id, sales_id=sales_id,
                confirmed_id=confirmed_id, scenario=e.a.scenario, fx_method=fx_method, currency_id=e.company.currency_id.id,
                scope=e.scope, scope_key=key, version=previous.version+1 if previous else 1, previous_id=previous.id,
                fingerprint=e.fingerprint, policy_version=VERSION, collected_at=fields.Datetime.now(), collected_by=self.env.uid,
                state=e.state, cost_complete=e.cost_complete, delta_complete=e.delta_complete, line_count=len(e.lines),
                complete_cost_line_count=sum(l['cost_complete'] for l in e.lines), incomplete_cost_line_count=sum(not l['cost_complete'] for l in e.lines),
                **e.totals, direction=cost_direction(e.totals['incremental_total']),
                conditional_incremental_delta=e.conditional_effect, reconciliation=e.reconciliation,
                provenance=dict(cost_snapshot_id=cost_id, cost_version=e.cost.version, cost_fingerprint=e.cost.fingerprint,
                    sales_snapshot_id=sales_id, sales_version=e.sales.version, sales_fingerprint=e.sales.fingerprint,
                    allocation_id=e.a.id, allocation_version=e.a.version, allocation_fingerprint=e.a.fingerprint,
                    supply_snapshot_id=e.a.supply_snapshot_id.id, purchase_snapshot_id=e.cost.purchase_id.id,
                    policy=e.cost.provenance['policy'], supplier_terms=e.supplier_evidence,
                    assumptions='Same physical allocation, per-entry hypothetical procurement, net commercial replacement; no future charges or realized outcome.',
                    no_eligible_demand=not e.a.demand_ids)))
            for row in e.lines:
                self.env[LINE]._record(dict(row, snapshot_id=result.id))
            for issue in e.issues:
                self.env[ISSUE]._record(dict(issue, batch_id=self.id, snapshot_id=result.id))
            return result

    def get_current_financial_exposure(self, cost_id, sales_id, confirmed_id=0, fx_method='same_rate'):
        self.ensure_one()
        e = FinancialEngine(self, cost_id, sales_id, confirmed_id, fx_method).build()
        result = self.env[HEADER].search([('batch_id', '=', self.id), ('scope_key', '=', digest(e.scope))], limit=1)
        if not result or result.fingerprint != e.fingerprint:
            raise UserError('Financial snapshot is missing or stale; recalculate from current verified source evidence.')
        return result


class CostFinancialAction(models.Model):
    _inherit = 'vendor.price.revision.cost.snapshot'

    def action_open_financial_calculation(self):
        self.ensure_one()
        self.check_access('read')
        prepare_allowed(self.batch_id)
        return dict(type='ir.actions.act_window', res_model=PREFIX+'wizard', view_mode='form', target='new',
            context=dict(default_batch_id=self.batch_id.id, default_cost_source_id=self.id))


class FinancialWizard(models.TransientModel):
    _name = PREFIX+'wizard'
    _inherit = 'vendor.price.revision.purchase.wizard.boundary'
    _description = 'Financial Calculation Source Inputs'
    batch_id = fields.Many2one(BATCH, required=True)
    company_id = fields.Many2one(related='batch_id.company_id', store=True)
    cost_source_id = fields.Integer(required=True, string='Cost-attribution snapshot ID')
    sales_source_id = fields.Integer(required=True, string='Sales-classification snapshot ID')
    confirmed_source_id = fields.Integer(string='Confirmed financial baseline ID for quotation scenarios')
    fx_method = fields.Selection([('same_rate', 'Common rate: supplier price reference'), ('date_specific', 'Separate dates: price and FX reference')], required=True, default='same_rate')

    def action_run(self):
        self.ensure_one()
        self.check_access('read')
        result = self.batch_id.action_calculate_financial_exposure(self.cost_source_id, self.sales_source_id, self.confirmed_source_id, self.fx_method)
        return dict(type='ir.actions.act_window', res_model=HEADER, res_id=result.id, view_mode='form')
