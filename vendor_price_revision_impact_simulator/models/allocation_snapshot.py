"""Immutable quantity evidence; all public writes reject forged outcomes."""
from odoo import fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .import_intake import BATCH
from .import_validation import PREFIX as IMPORT_PREFIX
from .product_resolution import company_lock
from .allocation_policy import PREFIX, authorized
from .allocation_engine import AllocationEngine, HEADER, DEMAND, LEDGER, ISSUE


class AllocationSnapshot(models.Model):
    _name=HEADER
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Analytical Demand Allocation Snapshot (not operational reservation)'
    _order='id desc'
    _unique=models.Constraint('UNIQUE(batch_id,scope_key,version)','One immutable version per analytical scope.')
    warehouse_ids=fields.Many2many('stock.warehouse',required=True)
    contains_costs=fields.Boolean()
    supply_snapshot_id=fields.Many2one('vendor.price.revision.supply.snapshot',required=True,ondelete='restrict')
    baseline_id=fields.Many2one(HEADER,ondelete='restrict',string='Independent confirmed baseline')
    scenario=fields.Selection([(s,s.replace('_',' ').title()) for s in ('confirmed_baseline','single_quotation','quotation_portfolio')],required=True)
    scope_key=fields.Char(required=True,index=True)
    scope=fields.Json(required=True)
    version=fields.Integer(required=True)
    previous_id=fields.Many2one(HEADER,ondelete='restrict')
    fingerprint=fields.Char(required=True,index=True)
    collected_at=fields.Datetime(required=True)
    collected_by=fields.Many2one('res.users',required=True)
    state=fields.Selection([('allocated','Analytically allocated'),('review_required','Review required')],required=True)
    totals=fields.Json()
    source_capacities=fields.Json()
    provenance=fields.Json(required=True)
    demand_ids=fields.One2many(DEMAND,'snapshot_id')
    entry_ids=fields.One2many(LEDGER,'snapshot_id')
    issue_ids=fields.One2many(ISSUE,'snapshot_id')
    freshness=fields.Selection([('current','Current source evidence'),('stale','Stale / superseded')],compute='_compute_freshness',search='_search_freshness')

    def _current(self):
        self.ensure_one();self.check_access('read')
        s=self.scope
        engine=AllocationEngine(self.batch_id,s['warehouses'],s['costs'],s['horizon'],s['confirmed_ids'],s['quote_ids'],s['portfolio_reason']).build()
        latest=self.search([('batch_id','=',self.batch_id.id),('scope_key','=',self.scope_key)],limit=1)
        return engine.fingerprint==self.fingerprint and latest==self

    def _compute_freshness(self):
        # Bounded list pages; one current-scope check per scope on that page.
        cache={}
        for rec in self:
            key=(rec.batch_id.id,rec.scope_key,rec.fingerprint)
            if key not in cache:
                try:cache[key]=rec._current()
                except (UserError,ValidationError,AccessError):cache[key]=False
            rec.freshness='current' if cache[key] else 'stale'

    def _search_freshness(self,operator,value):
        if operator not in ('=','!=') or value not in ('current','stale'):return [('id','=',0)]
        records=self.search([],limit=1001)
        if len(records)>1000:raise UserError('Narrow the allocation history before searching current source status.')
        ids=[r.id for r in records if r.freshness==value]
        return [('id','in' if operator=='=' else 'not in',ids)]

    def action_check_current(self):
        current=self._current()
        return {'type':'ir.actions.client','tag':'display_notification','params':{'title':'Allocation freshness',
            'message':'Current analytical evidence' if current else 'STALE: collect current supply and revalidate allocation',
            'type':'success' if current else 'warning','sticky':True}}


class DemandLine(models.Model):
    _name=DEMAND
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Exact Sales Line Quantity Evidence'
    _order='priority,id'
    _unique=models.Constraint('UNIQUE(snapshot_id,source_key)','One source demand line per scenario.')
    snapshot_id=fields.Many2one(HEADER,required=True,ondelete='restrict',index=True)
    source_key=fields.Char(required=True,index=True)
    sale_line_id=fields.Integer(required=True,index=True,string='Sales line ID')
    sale_order_id=fields.Integer(required=True,string='Sales order ID')
    order_name=fields.Char(required=True)
    customer_id=fields.Integer(string='Customer source ID')
    product_id=fields.Integer(required=True,index=True,string='Exact variant ID')
    product_name=fields.Char(required=True)
    warehouse_id=fields.Many2one('stock.warehouse',required=True)
    uom_id=fields.Many2one('uom.uom',required=True)
    demand_type=fields.Selection([('confirmed','Confirmed commitment'),('conditional','Conditional quotation')],required=True)
    ordered=fields.Char()
    delivered=fields.Char()
    outstanding=fields.Char(string='Outstanding (blank = unknown)')
    required_date=fields.Datetime()
    date_basis=fields.Char()
    confirmation_date=fields.Datetime()
    reserved=fields.Char(string='Actual reservation-backed quantity')
    free_stock=fields.Char(string='Simulated free-stock allocation')
    incoming=fields.Char(string='Simulated incoming allocation')
    protected_incoming=fields.Char(string='Protected incoming subset')
    new_procurement=fields.Char(string='Additional procurement required')
    unresolved=fields.Char(string='Unresolved (blank = quantity unknown)')
    priority=fields.Integer()
    issues=fields.Json()
    source_fingerprint=fields.Char(required=True)
    status=fields.Selection([(s,s.replace('_',' ').title()) for s in ('fully_covered','partially_covered','uncovered','unresolved')],required=True)
    entry_ids=fields.One2many(LEDGER,'demand_id')

    def action_open_source(self):
        self.ensure_one();self.check_access('read')
        authorized(self.batch_id,self.snapshot_id.warehouse_ids.ids,self.snapshot_id.contains_costs)
        source=self.env['sale.order.line'].browse(self.sale_line_id).exists()
        if not source:raise UserError('Sales source no longer exists.')
        source.check_access('read')
        if source.company_id!=self.company_id or source.order_id.warehouse_id!=self.warehouse_id:
            raise AccessError('Current source is outside the recorded authorized scope.')
        return {'type':'ir.actions.act_window','res_model':'sale.order','res_id':source.order_id.id,'view_mode':'form'}


class AllocationEntry(models.Model):
    _name=LEDGER
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Unique Analytical Supply Consumption Ledger'
    _unique=models.Constraint('UNIQUE(snapshot_id,demand_id,capacity_key)','A source contributes once to a demand in one scenario.')
    snapshot_id=fields.Many2one(HEADER,required=True,ondelete='restrict',index=True)
    demand_id=fields.Many2one(DEMAND,required=True,ondelete='restrict',index=True)
    demand_source_key=fields.Char(required=True)
    capacity_key=fields.Char(required=True,index=True)
    supply_bucket_id=fields.Many2one('vendor.price.revision.supply.bucket',ondelete='restrict')
    allocation_type=fields.Selection([(s,s.replace('_',' ').title()) for s in ('existing_reserved_for_demand',
        'eligible_free_stock','protected_incoming_po','incoming_cost_unverified','new_procurement_requirement','unresolved')],required=True)
    quantity=fields.Char(required=True)
    available_date=fields.Datetime()
    required_date=fields.Datetime()
    source_evidence=fields.Json(required=True)
    cost_confidence=fields.Char(required=True)


class AllocationIssue(models.Model):
    _name=ISSUE
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Retained Allocation Quantity Exception'
    snapshot_id=fields.Many2one(HEADER,required=True,ondelete='restrict',index=True)
    code=fields.Char(required=True,index=True)
    source_key=fields.Char(required=True)
    severity=fields.Char(required=True)
    message=fields.Text(required=True)


class BatchAllocation(models.Model):
    _inherit=BATCH
    allocation_snapshot_ids=fields.One2many(HEADER,'batch_id',readonly=True)

    def action_run_allocation(self,warehouse_ids,costs=True,horizon=None,confirmed_order_ids=None,quotation_ids=None,portfolio_reason=None):
        self.ensure_one();authorized(self,warehouse_ids,costs,prepare=True)
        company_lock(self.env,self.company_id);self._lock()
        with self.env.cr.savepoint():
            engine=AllocationEngine(self,warehouse_ids,costs,horizon,confirmed_order_ids,quotation_ids,portfolio_reason).build()
            previous=self.env[HEADER].search([('batch_id','=',self.id),('scope_key','=',engine.scope_key)],limit=1)
            if previous and previous.fingerprint==engine.fingerprint:return previous
            baseline=self.env[HEADER]
            if engine.quotes:
                baseline=self.action_run_allocation(warehouse_ids,costs,horizon,confirmed_order_ids)
                # Confirmed baseline coverage must remain identical across scenarios.
                fields_compare=('source_key','reserved','free_stock','incoming','protected_incoming','new_procurement','unresolved')
                expected=[{k:(None if r[k] is False else r[k]) for k in fields_compare} for r in baseline.demand_ids]
                actual=[{k:r[k] for k in fields_compare} for r in engine.lines if r['demand_type']=='confirmed']
                if expected!=actual:raise ValidationError('Conditional scenario changed confirmed baseline coverage.')
            snapshot=self.env[HEADER]._record(dict(batch_id=self.id,warehouse_ids=[(6,0,engine.wh.ids)],contains_costs=costs,
                supply_snapshot_id=engine.supply.id,baseline_id=baseline.id,scenario=engine.scenario,scope_key=engine.scope_key,
                scope=engine.scope,version=previous.version+1 if previous else 1,previous_id=previous.id,
                fingerprint=engine.fingerprint,collected_at=fields.Datetime.now(),collected_by=self.env.uid,
                state='review_required' if engine.issues else 'allocated',totals=engine.totals,
                source_capacities=engine.capacities,provenance=dict(sources=engine.reader.sources,policy=engine.policy,
                    source_supply_id=engine.supply.id,source_supply_digest=engine.supply.input_digest,
                    semantics='Analytical allocation only. Separate conditional scenarios cannot be added together.')))
            demand={}
            for row in engine.lines:
                rec=self.env[DEMAND]._record(dict(row,batch_id=self.id,snapshot_id=snapshot.id));demand[row['source_key']]=rec
            for row in engine.entries:
                self.env[LEDGER]._record(dict(row,batch_id=self.id,snapshot_id=snapshot.id,demand_id=demand[row['demand_source_key']].id))
            for issue in engine.issues:self.env[ISSUE]._record(dict(issue,batch_id=self.id,snapshot_id=snapshot.id))
            return snapshot

    def get_current_allocation(self,warehouse_ids,costs=True,horizon=None,confirmed_order_ids=None,quotation_ids=None,portfolio_reason=None):
        self.ensure_one();authorized(self,warehouse_ids,costs)
        engine=AllocationEngine(self,warehouse_ids,costs,horizon,confirmed_order_ids,quotation_ids,portfolio_reason).build()
        snapshot=self.env[HEADER].search([('batch_id','=',self.id),('scope_key','=',engine.scope_key)],limit=1)
        if not snapshot or snapshot.fingerprint!=engine.fingerprint:
            raise UserError('Allocation snapshot is missing or stale. Revalidate current supply and analytical allocation.')
        return snapshot

    def action_open_allocation(self):
        self._check_review_access()
        return {'type':'ir.actions.act_window','res_model':PREFIX+'wizard','view_mode':'form','target':'new',
            'context':{'default_batch_id':self.id}}


class AllocationWizard(models.TransientModel):
    _name=PREFIX+'wizard'
    _description='Run Analytical Demand / Conditional Quotation Allocation'
    batch_id=fields.Many2one(BATCH,required=True)
    company_id=fields.Many2one(related='batch_id.company_id',store=True)
    warehouse_ids=fields.Many2many('stock.warehouse',required=True)
    costs=fields.Boolean(default=True)
    horizon=fields.Datetime()
    confirmed_order_ids=fields.Char(string='Confirmed order IDs (comma-separated; blank = all affected in scope)')
    quotation_ids=fields.Char(string='Explicit quotation IDs (comma-separated)')
    candidate_sources=fields.Json(readonly=True)
    portfolio_reason=fields.Char()

    def action_preview_sources(self):
        self.ensure_one();self.check_access('read')
        authorized(self.batch_id,self.warehouse_ids.ids,self.costs,prepare=True)
        # Explicit grant permits only this fixed, warehouse/product quantity-free
        # candidate projection. Native SO permissions are not broadened.
        from .supply_engine import SupplyEngine
        reader=SupplyEngine(self.batch_id,self.warehouse_ids.ids,self.costs).build()
        records=reader.read('sale.order',[('company_id','=',self.company_id.id),
            ('warehouse_id','in',self.warehouse_ids.ids),('state','in',['sale','draft','sent']),
            ('order_line.product_id','in',reader.product_ids)],
            ['name','state','warehouse_id','commitment_date','validity_date'])
        self.candidate_sources=list(records.values())
        return {'type':'ir.actions.act_window','res_model':self._name,'res_id':self.id,'view_mode':'form','target':'new'}

    def action_run(self):
        self.ensure_one();self.check_access('read')
        def ids(value):
            try:return sorted(set(int(v.strip()) for v in value.split(',') if v.strip())) if value else []
            except ValueError:raise ValidationError('Use comma-separated source order IDs from the authorized preview.')
        result=self.batch_id.action_run_allocation(self.warehouse_ids.ids,self.costs,self.horizon,
            ids(self.confirmed_order_ids) if self.confirmed_order_ids else None,ids(self.quotation_ids),self.portfolio_reason)
        return {'type':'ir.actions.act_window','res_model':HEADER,'res_id':result.id,'view_mode':'form'}
