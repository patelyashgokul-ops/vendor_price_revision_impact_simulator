"""Projected affected-demand profitability over exact PR11 and PR14 sources."""
from collections import defaultdict
from decimal import Decimal, localcontext

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .import_intake import BATCH
from .import_validation import PREFIX as IMPORT_PREFIX
from .financial_exposure import HEADER as FINANCIAL, prepare_allowed, LIMIT
from .product_resolution import company_lock
from .structural_validation import digest
from .commercial_math import number
from .profitability_math import AMOUNTS, RANK, profitability, assess, reported

PREFIX = 'vendor.price.revision.margin.'
HEADER, LINE, AGGREGATE, RISK = [PREFIX+s for s in ('snapshot','line','aggregate','risk')]
VERSION = 'pr15_exact_sales_line_same_revenue_affected_scope_decimal_risk_v1'


def nullable(value):
    return value if value is not False and value is not None else None


def policy_values(row):
    return dict(id=row.id, minimum=str(row.minimum_margin_percent), target=str(row.target_margin_percent),
        erosion_enabled=row.erosion_enabled, erosion_points=str(row.erosion_warning_points),
        negative_profit_critical=row.negative_profit_critical, scope=row.scope)


class MarginEngine:
    def __init__(self, batch, financial_id, confirmed_id=0):
        if type(financial_id) is not int or financial_id <= 0 or type(confirmed_id) is not int or confirmed_id < 0:
            raise ValidationError('Select an exact financial snapshot and optional confirmed profitability baseline.')
        batch.ensure_one(); batch.check_access('read')
        self.batch, self.env = batch, batch.env
        self.f = self.env[FINANCIAL].browse(financial_id).exists()
        if not self.f: raise UserError('Financial snapshot is missing.')
        self.f.check_access('read')
        if self.f.batch_id != batch: raise AccessError('Financial source must belong to this exact revision batch.')
        self.sales = self.f.sales_id
        self.company = batch.company_id
        self.scope = dict(financial_id=financial_id, confirmed_id=confirmed_id)
        self.lines, self.aggregates = [], []
        self.policy_cache = {}

    def build(self):
        with localcontext() as ctx:
            ctx.prec = 38
            return self._build()

    def _build(self):
        f = self.f
        if self.batch.get_current_financial_exposure(**f.scope) != f:
            raise UserError('Financial snapshot is stale.')
        # The financial getter already verifies exact current PR11, allocation,
        # source identity, native rights and every selected warehouse grant.
        self.sales.check_access('read')
        self.a = f.cost_id.allocation_id
        if len(self.sales.line_ids) > LIMIT: raise UserError('Narrow the profitability scope.')
        self.policy = self.env['vendor.price.revision.config']
        self.rules, self.policy_issue = [], None
        try:
            self.policy = self.policy.get_company_revision_config(self.company, self.sales.fx_date or fields.Date.context_today(self.batch))
            self.rules = [dict(id=r.id, minimum=str(r.minimum_amount), maximum=None if r.open_ended else str(r.maximum_amount), level=r.risk_level) for r in self.policy.get_applicable_risk_rules()]
        except UserError as exc:
            self.policy_issue = str(exc)
        self.env.flush_all()
        if self.policy:
            for records in (self.policy, self.policy.margin_ids, self.policy.risk_ids):
                if records:
                    self.env.cr.execute('SELECT id FROM '+records._table+' WHERE id IN %s ORDER BY id FOR SHARE', [tuple(records.ids)])
        by_demand = defaultdict(list)
        for row in f.line_ids: by_demand[row.allocation_entry_id.demand_id.id].append(row)
        consumed = set()
        for source in self.sales.line_ids.sorted('id'):
            costs = by_demand[source.allocation_demand_source_id]
            consumed.update(c.id for c in costs)
            q = sum((number(c.quantity) for c in costs), Decimal(0))
            attrs = source.allocation_values or []
            exact = {c.allocation_entry_id.id for c in costs}
            if source.outstanding_qty and q != number(source.outstanding_qty):
                raise ValidationError('Sales quantity and financial allocation quantity differ.')
            if source.valuation_status == 'verified' and {v['entry_id'] for v in attrs} != exact:
                raise ValidationError('Revenue attribution must cover the same exact financial entries.')
            if any(c.sale_line_id != source.sale_line_id.id or c.product_id != source.product_id.id or c.demand_type != source.demand_type or c.comparison_uom_id != source.comparison_uom_id or c.currency_id != self.company.currency_id for c in costs):
                raise ValidationError('Revenue and cost company/order/line/product/UoM/classification mismatch.')
            revenue = nullable(source.company_sales_value) if source.valuation_status == 'verified' else None
            b = str(sum((number(c.baseline_extended_cost) for c in costs), Decimal(0))) if costs and all(c.cost_complete for c in costs) else None
            r = str(sum((number(c.revised_extended_cost) for c in costs), Decimal(0))) if b is not None else None
            values = profitability(revenue, b, r)
            complete = revenue is not None and b is not None and not f.reconciliation['unresolved_demand_ids']
            confidence = 'scenario_only' if any(c.status == 'scenario_only' for c in costs) else 'estimated' if any(c.status == 'estimated' for c in costs) else 'fully_verified'
            state = confidence if complete else 'incomplete'
            if not complete:
                confidence = 'incomplete'
            entry_delta = str(sum((number(c.incremental_extended_cost) for c in costs), Decimal(0))) if costs and all(c.delta_complete for c in costs) else None
            if values['gross_profit_change'] is not None and (entry_delta is None or abs(number(values['gross_profit_change'])+number(entry_delta)) > number(self.company.currency_id.rounding)):
                raise ValidationError('Profit change must equal the negative exact PR14 cost change.')
            policy = self.margin_policy(source.product_id)
            risks = assess(values, policy, self.rules, confidence, complete, [source.price_protection])
            self.lines.append(dict(batch_id=self.batch.id, sale_order_id=source.sale_order_id.id, sale_line_id=source.sale_line_id.id,
                customer_id=source.customer_id.id, product_id=source.product_id.id, warehouse_id=source.warehouse_id.id,
                sales_line_id=source.id, quantity=str(q), comparison_uom_id=source.comparison_uom_id.id,
                demand_type=source.demand_type, currency_id=self.company.currency_id.id, state=state, complete=complete,
                policy_evidence=policy, source_financial_line_ids=[c.id for c in costs], incremental_cost=entry_delta,
                price_protection=source.price_protection, source_evidence=dict(source_terms=source.source_terms,
                    protection=source.protection_evidence, sales_fx=source.fx_evidence, source_issues=source.issue_codes,
                    financial_issues={str(c.id):c.issue_codes for c in costs}, policy_issue=self.policy_issue,
                    revenue_basis='PR11 company-currency rounded outstanding tax-excluded value; same in both scenarios',
                    assumptions='Affected remaining product scope only; not entire order or realized accounting profit'),
                reported_values=reported(values, self.company.currency_id.rounding), **values, **risks))
        if consumed != set(f.line_ids.ids): raise ValidationError('Every financial contribution must be consumed exactly once.')
        labels = {dimension:{v.id:v.display_name for v in records} for dimension,records in (
            ('company',self.company),('order',self.sales.line_ids.sale_order_id),
            ('product',self.sales.line_ids.product_id),('customer',self.sales.line_ids.customer_id))}
        for dimension, key in (('company',None),('order','sale_order_id'),('product','product_id'),('customer','customer_id')):
            groups = defaultdict(list)
            for line in self.lines: groups[(line[key] if key else self.company.id, line['demand_type'])].append(line)
            for (identity, demand), lines in sorted(groups.items()):
                self.aggregates.append(dict(dimension=dimension, source_id=identity, source_name=labels[dimension][identity], demand_type=demand,
                    **self.aggregate(lines, self.margin_policy(self.env['product.product'].browse(identity)) if dimension=='product' else self.margin_policy())))
        self.totals = self.aggregate(self.lines, self.margin_policy())
        if not self.lines:
            self.totals.update(state='no_eligible_demand', complete=False, risk_status='not_evaluated')
        self.conditional_profit = None
        self.confirmed = self.env[HEADER]
        if f.scenario != 'confirmed_baseline':
            self.confirmed = self.env[HEADER].browse(self.scope['confirmed_id']).exists()
            c = self.confirmed
            if not c or c.financial_id != f.confirmed_id or c.batch_id != self.batch:
                raise ValidationError('A conditional scenario requires its exact current confirmed profitability baseline.')
            c.check_access('read')
            if self.batch.get_current_profitability(**c.scope) != c: raise UserError('Confirmed profitability is stale.')
            if self.totals['complete'] and c.complete:
                self.conditional_profit = str(number(self.totals['revised_gross_profit'])-number(c.revised_gross_profit))
        elif self.scope['confirmed_id']:
            raise ValidationError('Confirmed scenarios cannot reference another profitability baseline.')
        self.policy_evidence = dict(id=self.policy.id, version=self.policy.policy_version if self.policy else None,
            date=str(self.sales.fx_date or fields.Date.context_today(self.batch)), margins=[policy_values(r) for r in self.policy.margin_ids.filtered('active')],
            rules=self.rules, issue=self.policy_issue, negative_margin_policy=self.policy.negative_margin_policy if self.policy else None)
        self.fingerprint = digest(dict(version=VERSION, financial=f.fingerprint, financial_id=f.id, sales=self.sales.fingerprint,
            policy=self.policy_evidence, lines=self.lines, aggregates=self.aggregates, totals=self.totals,
            confirmed=self.confirmed.fingerprint if self.confirmed else None))
        return self

    def margin_policy(self, product=None):
        key = product.id if product else 0
        if key not in self.policy_cache:
            row = self.policy.get_applicable_margin_policy(product) if self.policy and product else self.policy.margin_ids.filtered(lambda r:r.active and r.scope=='company') if self.policy else None
            self.policy_cache[key] = policy_values(row) if row and len(row)==1 else None
        return self.policy_cache[key]

    def aggregate(self, lines, policy):
        complete = bool(lines) and all(l['complete'] for l in lines)
        def total(key):
            return str(sum((number(l[key]) for l in lines), Decimal(0))) if lines and all(l[key] is not None for l in lines) else None
        values = profitability(total('net_revenue'), total('baseline_cost'), total('revised_cost'))
        confidence = 'scenario_only' if any(l['state']=='scenario_only' for l in lines) else 'estimated' if any(l['state']=='estimated' for l in lines) else 'fully_verified'
        state = confidence if complete else 'verified_partial' if any(l['complete'] for l in lines) else 'incomplete'
        if not complete:
            confidence = state
        partial = [l for l in lines if l['complete']]
        partial_amounts = {k:str(sum((number(l[k]) for l in partial),Decimal(0))) if partial else None for k in ('net_revenue','baseline_cost','revised_cost','baseline_gross_profit','revised_gross_profit')}
        risks = assess(values, policy, self.rules, confidence, complete, [l['price_protection'] for l in lines])
        highest = max((l['risk_status'] for l in lines if l['risk_status'] in RANK), key=RANK.get,
            default='review_required' if lines else 'not_evaluated')
        # Baseline/revised amounts may be known individually; a full verified
        # profitability total still requires all exact line quantities and bases.
        return dict(**values, **risks, highest_line_risk=highest, state=state, complete=complete, line_count=len(lines),
            incomplete_line_count=sum(not l['complete'] for l in lines), partial_amounts=partial_amounts,
            policy_evidence=policy, reported_values=reported(values,self.company.currency_id.rounding))


class MarginAmounts(models.AbstractModel):
    _name = PREFIX+'amounts'
    _description = 'Nullable exact projected profitability and explainable risk'
    for _field in AMOUNTS:
        locals()[_field] = fields.Char(string=_field.replace('_',' ').capitalize()+' (blank = unavailable)')
    del _field
    state = fields.Char(required=True, index=True)
    complete = fields.Boolean()
    baseline_risk = fields.Char(required=True)
    revised_risk = fields.Char(required=True)
    risk_status = fields.Char(required=True, index=True)
    highest_line_risk = fields.Char(string='Highest known constituent line severity')
    revision_effect = fields.Char(required=True, index=True)
    risk_reasons = fields.Json()
    policy_evidence = fields.Json()
    reported_values = fields.Json()
    baseline_margin_display = fields.Char(string='Baseline gross margin (%)', compute='_display_percentages')
    revised_margin_display = fields.Char(string='Revised gross margin (%)', compute='_display_percentages')
    erosion_display = fields.Char(string='Margin erosion (pp)', compute='_display_percentages')

    @api.depends('reported_values')
    def _display_percentages(self):
        for rec in self:
            values = rec.reported_values or {}
            rec.baseline_margin_display = values.get('baseline_margin_percent')
            rec.revised_margin_display = values.get('revised_margin_percent')
            rec.erosion_display = values.get('margin_erosion_points')


class MarginSnapshot(models.Model):
    _name = HEADER
    _inherit = [IMPORT_PREFIX+'review.guard', PREFIX+'amounts']
    _description = 'Immutable Projected Affected-Demand Profitability'
    _order = 'id desc'
    _unique = models.Constraint('UNIQUE(batch_id,scope_key,version)', 'One profitability version per exact source scope.')
    name = fields.Char(required=True)
    financial_id = fields.Many2one(FINANCIAL,required=True,ondelete='restrict')
    sales_id = fields.Many2one('vendor.price.revision.sales.snapshot',required=True,ondelete='restrict')
    allocation_id = fields.Many2one('vendor.price.revision.allocation.snapshot',required=True,ondelete='restrict')
    confirmed_id = fields.Many2one(HEADER,ondelete='restrict')
    warehouse_ids = fields.Many2many('stock.warehouse')
    order_ids = fields.Many2many('sale.order')
    currency_id = fields.Many2one('res.currency',required=True)
    scenario = fields.Char(required=True,index=True)
    scope = fields.Json(required=True)
    scope_key = fields.Char(required=True,index=True)
    fingerprint = fields.Char(required=True)
    version = fields.Integer(required=True)
    previous_id = fields.Many2one(HEADER,ondelete='restrict')
    collected_at = fields.Datetime(required=True)
    collected_by = fields.Many2one('res.users',required=True)
    policy_version = fields.Char(required=True)
    provenance = fields.Json(required=True)
    line_count = fields.Integer()
    incomplete_line_count = fields.Integer()
    partial_amounts = fields.Json()
    conditional_incremental_profit = fields.Char(string='Scenario revised profit minus confirmed revised profit; not additive')
    line_ids = fields.One2many(LINE,'snapshot_id')
    aggregate_ids = fields.One2many(AGGREGATE,'snapshot_id')
    risk_ids = fields.One2many(RISK,'snapshot_id')
    freshness = fields.Selection([('current','Current sources'),('stale','Stale/review required')], compute='_freshness', search='_search_freshness')

    def _current(self):
        self.ensure_one();self.check_access('read')
        e = MarginEngine(self.batch_id,**self.scope).build()
        return self.search([('batch_id','=',self.batch_id.id),('scope_key','=',self.scope_key)],limit=1)==self and e.fingerprint==self.fingerprint

    def _freshness(self):
        cache = {}
        for rec in self:
            key=(rec.batch_id.id,rec.scope_key)
            if key not in cache:
                try:
                    e=MarginEngine(rec.batch_id,**rec.scope).build()
                    latest=self.search([('batch_id','=',rec.batch_id.id),('scope_key','=',rec.scope_key)],limit=1)
                    cache[key]=(e.fingerprint,latest.id)
                except (AccessError,UserError,ValidationError): cache[key]=(None,0)
            rec.freshness='current' if cache[key]==(rec.fingerprint,rec.id) else 'stale'

    def _search_freshness(self, operator, value):
        if operator not in ('=','!=') or value not in ('current','stale'): raise UserError('Use a current/stale equality filter.')
        rows=self.search([],limit=1001)
        if len(rows)>1000: raise UserError('Narrow historical profitability scope before freshness search.')
        ids=rows.filtered(lambda r:r.freshness==value).ids
        return [('id','in' if operator=='=' else 'not in',ids)]

    def action_check_current(self):
        if not self._current(): raise UserError('Profitability sources or risk policy changed; revalidate upstream and recalculate.')
        return dict(type='ir.actions.client',tag='display_notification',params=dict(message='Current projected profitability; inspect confidence and scope',type='success'))


class MarginLine(models.Model):
    _name = LINE
    _inherit = [IMPORT_PREFIX+'review.guard', PREFIX+'amounts']
    _description = 'Exact Sales Line Projected Profitability'
    _unique = models.Constraint('UNIQUE(snapshot_id,sale_line_id)', 'An exact sales line contributes once.')
    snapshot_id = fields.Many2one(HEADER,required=True,ondelete='restrict',index=True)
    sale_order_id = fields.Many2one('sale.order',required=True,ondelete='restrict')
    sale_line_id = fields.Many2one('sale.order.line',required=True,ondelete='restrict')
    sales_line_id = fields.Many2one('vendor.price.revision.sales.line',required=True,ondelete='restrict')
    customer_id = fields.Many2one('res.partner',required=True)
    product_id = fields.Many2one('product.product',required=True)
    warehouse_id = fields.Many2one('stock.warehouse',required=True)
    quantity = fields.Char(required=True)
    comparison_uom_id = fields.Many2one('uom.uom',required=True)
    currency_id = fields.Many2one('res.currency',required=True)
    demand_type = fields.Char(required=True,index=True)
    source_financial_line_ids = fields.Json(required=True)
    incremental_cost = fields.Char()
    price_protection = fields.Char(required=True)
    source_evidence = fields.Json(required=True)

    def action_open_source(self):
        self.ensure_one();self.check_access('read')
        return self.sales_line_id.action_open_source()


class MarginAggregate(models.Model):
    _name = AGGREGATE
    _inherit = [IMPORT_PREFIX+'review.guard', PREFIX+'amounts']
    _description = 'Affected Scope Amount-Sum Profitability Aggregate'
    _unique = models.Constraint('UNIQUE(snapshot_id,dimension,source_id,demand_type)', 'One aggregate for each exact dimension and demand class.')
    snapshot_id = fields.Many2one(HEADER,required=True,ondelete='restrict',index=True)
    dimension = fields.Selection([(v,v.title()) for v in ('company','order','product','customer')],required=True)
    source_id = fields.Integer(required=True)
    source_name = fields.Char(required=True, string='Affected company, order, variant or customer')
    demand_type = fields.Char(required=True)
    line_count = fields.Integer()
    incomplete_line_count = fields.Integer()
    partial_amounts = fields.Json()


class MarginRisk(models.Model):
    _name = RISK
    _inherit = IMPORT_PREFIX+'review.guard'
    _description = 'Frozen Explainable Profitability Risk Reason (not approval)'
    snapshot_id = fields.Many2one(HEADER,required=True,ondelete='restrict',index=True)
    line_id = fields.Many2one(LINE,ondelete='restrict')
    aggregate_id = fields.Many2one(AGGREGATE,ondelete='restrict')
    code = fields.Char(required=True,index=True)
    severity = fields.Char(required=True,index=True)
    stage = fields.Char(required=True)
    actual = fields.Char()
    threshold = fields.Char()
    basis = fields.Char(required=True)
    policy_id = fields.Integer()
    explanation = fields.Char(required=True)


class BatchProfitability(models.Model):
    _inherit = BATCH

    def action_calculate_profitability(self, financial_id, confirmed_id=0):
        self.ensure_one();prepare_allowed(self)
        e=MarginEngine(self,financial_id,confirmed_id)
        company_lock(self.env,self.company_id);self._lock()
        with self.env.cr.savepoint():
            e.build();key=digest(e.scope)
            previous=self.env[HEADER].search([('batch_id','=',self.id),('scope_key','=',key)],limit=1)
            if previous and previous.fingerprint==e.fingerprint: return previous
            result=self.env[HEADER]._record(dict(batch_id=self.id,name='Projected affected profitability / '+str(e.a.id),
                financial_id=e.f.id,sales_id=e.sales.id,allocation_id=e.a.id,confirmed_id=confirmed_id,
                warehouse_ids=[(6,0,e.f.warehouse_ids.ids)],order_ids=[(6,0,e.sales.order_ids.ids)],currency_id=e.company.currency_id.id,
                scenario=e.f.scenario,scope=e.scope,scope_key=key,fingerprint=e.fingerprint,version=previous.version+1 if previous else 1,
                previous_id=previous.id,collected_at=fields.Datetime.now(),collected_by=self.env.uid,policy_version=VERSION,
                provenance=dict(financial_version=e.f.version,financial_fingerprint=e.f.fingerprint,sales_version=e.sales.version,
                    sales_fingerprint=e.sales.fingerprint,allocation_version=e.a.version,risk_policy=e.policy_evidence,
                    scope='Affected selected remaining product demand; not whole-order/accounting profit',alternatives_additive=False),
                conditional_incremental_profit=e.conditional_profit,**e.totals))
            def publish(model,row):
                rec=self.env[model]._record(dict(row,batch_id=self.id,snapshot_id=result.id))
                for reason in row['risk_reasons']:
                    self.env[RISK]._record(dict(reason,batch_id=self.id,snapshot_id=result.id,
                        line_id=rec.id if model==LINE else False,aggregate_id=rec.id if model==AGGREGATE else False,
                        explanation=reason['code'].replace('_',' ').capitalize()+'; '+reason['stage']+'; projected '+reason['basis']))
            for row in e.lines: publish(LINE,row)
            for row in e.aggregates: publish(AGGREGATE,row)
            return result

    def get_current_profitability(self, financial_id, confirmed_id=0):
        self.ensure_one()
        e=MarginEngine(self,financial_id,confirmed_id).build()
        result=self.env[HEADER].search([('batch_id','=',self.id),('scope_key','=',digest(e.scope))],limit=1)
        if not result or result.fingerprint!=e.fingerprint: raise UserError('Profitability snapshot is missing/stale; recalculate current sources.')
        return result


class FinancialMarginAction(models.Model):
    _inherit = FINANCIAL
    def action_open_profitability(self):
        self.ensure_one();self.check_access('read');prepare_allowed(self.batch_id)
        return dict(type='ir.actions.act_window',res_model=PREFIX+'wizard',view_mode='form',target='new',
            context=dict(default_batch_id=self.batch_id.id,default_financial_source_id=self.id))


class MarginWizard(models.TransientModel):
    _name = PREFIX+'wizard'
    _inherit = 'vendor.price.revision.purchase.wizard.boundary'
    _description = 'Projected Profitability Source Inputs'
    batch_id = fields.Many2one(BATCH,required=True)
    company_id = fields.Many2one(related='batch_id.company_id',store=True)
    financial_source_id = fields.Integer(required=True)
    confirmed_source_id = fields.Integer(string='Exact confirmed profitability baseline ID for conditional scenarios')
    def action_run(self):
        self.ensure_one();self.check_access('read')
        r=self.batch_id.action_calculate_profitability(self.financial_source_id,self.confirmed_source_id)
        return dict(type='ir.actions.act_window',res_model=HEADER,res_id=r.id,view_mode='form')
