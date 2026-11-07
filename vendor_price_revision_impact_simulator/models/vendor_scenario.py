"""Immutable PR17 input/result revisions and authorized analytical actions."""
from copy import deepcopy
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from .import_intake import BATCH
from .import_validation import PREFIX as IMPORT_PREFIX
from .reconciliation import HEADER as BASE, Reconciler, finance_allowed
from .product_resolution import company_lock
from .structural_validation import digest
from .scenario_math import MODES, decimal, text
from .scenario_engine import ScenarioEngine

PREFIX='vendor.price.revision.scenario'
HEADER=PREFIX
INPUT,LINE,RESULT,DETAIL,EVENT=[PREFIX+'.'+s for s in ('input','line','result','detail','event')]
KEYS={'product_id','mode','value','discount_base','currency_id','uom_id','row_id','grouped','group_reason',
      'buying_quantity','fx_method','fx_rate','fx_date','effective_date','commitment_date','timing_evidence',
      'po_line_id','po_evidence','landed','reason'}

def iso_date(value):
    try:return fields.Date.to_date(value).isoformat()
    except (ValueError,TypeError,AttributeError):raise ValidationError('An explicit ISO commercial date is required.') from None

class ScenarioPolicy(models.Model):
    _inherit='vendor.price.revision.config'
    scenario_landed_policy=fields.Selection([('exclude','Exclude future scenario landed components'),
        ('evidenced_nonrecoverable_charges','Permit documented incremental nonrecoverable scenario charges')],
        default='exclude',required=True,help='Hypothetical future components only. Existing stock/protected PO costs and PR13 net-price attribution remain unchanged.')

class Scenario(models.Model):
    _name=HEADER
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Hypothetical Vendor Alternative (not accepted, approved or applied)'
    _order='id desc'
    name=fields.Char(required=True)
    baseline_id=fields.Many2one(BASE,required=True,ondelete='restrict')
    parent_id=fields.Many2one(HEADER,ondelete='restrict')
    vendor_id=fields.Many2one(related='batch_id.vendor_id')
    currency_id=fields.Many2one(related='baseline_id.currency_id')
    input_ids=fields.One2many(INPUT,'scenario_id')
    result_ids=fields.One2many(RESULT,'scenario_id')
    event_ids=fields.One2many(EVENT,'scenario_id')
    current_state=fields.Char(compute='_current_state')
    selection_status=fields.Char(compute='_selection_status')

    def _inputs(self):
        self.ensure_one();return self.env[INPUT].search([('scenario_id','=',self.id)],limit=1)

    def _edit(self):
        self.ensure_one();self.check_access('read');finance_allowed(self.batch_id)
        company_lock(self.env,self.company_id);self.batch_id._lock()
        self.env.cr.execute('SELECT id FROM vendor_price_revision_scenario WHERE id=%s FOR UPDATE',[self.id])
        last=self.env[EVENT].search([('scenario_id','=',self.id)],limit=1)
        if last.event=='archived':raise UserError('Archived history is retained; clone into a new identity.')

    def action_set_assumptions(self,lines,reason):
        self._edit();reason=text(reason,'Assumption change')
        if not isinstance(lines,list) or len(lines)>1000:raise ValidationError('Provide a bounded list of exact product assumptions.')
        canonical=[];seen=set();product_ids=set(self.baseline_id.margin_id.financial_id.line_ids.mapped('product_id'))
        for raw in lines:
            if not isinstance(raw,dict) or set(raw)-KEYS:raise ValidationError('Unsupported or contradictory assumption fields.')
            v=deepcopy(raw);pid=v.get('product_id');po=v.get('po_line_id',0)
            if type(pid) is not int or pid not in product_ids or type(po) is not int or po<0:raise ValidationError('Select an exact baseline product/PO identity.')
            if (pid,po) in seen:raise ValidationError('One active price method per product/PO hypothesis.')
            seen.add((pid,po));text(v.get('reason'),'Commercial assumption');mode=v.get('mode','original')
            if mode not in MODES:raise ValidationError('Unsupported price method.')
            if mode in ('explicit','fixed_discount','percent_discount'):
                v['value']=str(decimal(v.get('value')))
                if mode=='percent_discount' and decimal(v['value'])>100:raise ValidationError('Discount exceeds100 percent.')
            elif 'value' in v:raise ValidationError('Original/tier method cannot contain a negotiated value.')
            if v.get('discount_base','proposal') not in ('proposal','old'):raise ValidationError('Unsupported discount base.')
            if mode=='tier':
                if type(v.get('row_id')) is not int:raise ValidationError('Select the exact verified PR08 tier row.')
                row=self.env['vendor.price.revision.import.row'].browse(v['row_id']).exists();row.check_access('read')
                if row.batch_id!=self.batch_id or row.resolved_product_id.id!=pid:raise ValidationError('Tier must belong to this vendor, batch and product.')
            elif 'row_id' in v or v.get('grouped') or 'buying_quantity' in v:raise ValidationError('Buying quantity/grouping belongs only to tier mode.')
            if 'grouped' in v and type(v['grouped']) is not bool:raise ValidationError('Choose explicit grouping or per-entry buying.')
            if v.get('grouped'):text(v.get('group_reason'),'Company/product/UoM/warehouse consolidation')
            if 'buying_quantity' in v:v['buying_quantity']=str(decimal(v['buying_quantity'],True))
            method=v.get('fx_method','price_only_common_fx')
            if method not in ('price_only_common_fx','combined_price_and_fx','fx_only_sensitivity'):raise ValidationError('Unsupported FX method.')
            if method=='price_only_common_fx' and not po and self.baseline_id.margin_id.financial_id.fx_method!='same_rate':
                raise ValidationError('Price-only common FX requires a common-rate financial baseline. Select that coherent baseline or document an explicit combined FX assumption.')
            if method=='fx_only_sensitivity' and mode!='original':raise ValidationError('FX-only holds original commercial price constant.')
            if method!='price_only_common_fx':v['fx_rate']=str(decimal(v.get('fx_rate'),True));v['fx_date']=iso_date(v.get('fx_date'))
            elif 'fx_rate' in v or 'fx_date' in v:raise ValidationError('Common-FX price-only has no alternate exchange rate.')
            for field in ('effective_date','commitment_date'):
                if field in v:v[field]=iso_date(v[field])
            if 'commitment_date' in v:text(v.get('timing_evidence'),'Commercial commitment timing; not delivery timing')
            if po:
                matches=self.baseline_id.margin_id.financial_id.line_ids.filtered(lambda l:l.cost_line_id.evidence.get('po_line_id')==po and l.product_id==pid)
                if not matches:raise ValidationError('PO hypothesis must reference an exact allocated baseline PO line.')
                text(v.get('po_evidence'),'Unapproved PO amendment hypothesis')
            for field in ('currency_id','uom_id'):
                if field in v and (type(v[field]) is not int or v[field]<=0):raise ValidationError('Use exact positive currency/UoM IDs.')
            landed=v.get('landed',[])
            if not isinstance(landed,list) or len(landed)>20:raise ValidationError('Bound future landed components.')
            codes=set()
            for component in landed:
                if not isinstance(component,dict) or set(component)!={'code','amount','evidence','nonrecoverable','not_included','currency_id','uom_id'}:raise ValidationError('Landed components need exact amount/unit/currency and evidence.')
                code=text(component['code'],'Component identity')
                if code in codes or component['nonrecoverable'] is not True or component['not_included'] is not True:raise ValidationError('Duplicate, recoverable or included cost unsupported.')
                codes.add(code);component['amount']=str(decimal(component['amount']));text(component['evidence'],'Future nonrecoverable component')
                units=set(self.baseline_id.margin_id.financial_id.line_ids.filtered(lambda l:l.product_id==pid).mapped('comparison_uom_id').ids)
                if component['currency_id']!=self.currency_id.id or units!={component['uom_id']}:raise ValidationError('Charge must use company currency per exact comparison unit.')
            canonical.append(v)
        canonical.sort(key=lambda v:(v['product_id'],v.get('po_line_id',0)))
        previous=self._inputs();fp=digest(canonical)
        if previous and previous.fingerprint==fp:return previous
        with self.env.cr.savepoint():
            result=self.env[INPUT]._record(dict(batch_id=self.batch_id.id,scenario_id=self.id,version=previous.version+1 if previous else 1,previous_id=previous.id,fingerprint=fp,reason=reason,actor_id=self.env.uid,recorded_at=fields.Datetime.now()))
            for v in canonical:self.env[LINE]._record(dict(batch_id=self.batch_id.id,input_id=result.id,product_id=v['product_id'],po_line_id=v.get('po_line_id',0),mode=v.get('mode','original'),values=v))
            return result

    def action_calculate_scenario(self):
        self._edit()
        with self.env.cr.savepoint():
            e=ScenarioEngine(self).build();previous=self.env[RESULT].search([('scenario_id','=',self.id)],order='id desc',limit=1)
            if previous and previous.fingerprint==e.fingerprint:return previous
            result=self.env[RESULT]._record(dict(batch_id=self.batch_id.id,scenario_id=self.id,input_id=e.input.id,version=previous.version+1 if previous else 1,
                previous_id=previous.id,fingerprint=e.fingerprint,collected_at=fields.Datetime.now(),actor_id=self.env.uid,state=e.state,complete=e.complete,
                profit=e.profit,financial=e.financial,controls=e.controls.checks,issues={'items':e.issues},provenance=e.provenance,
                improvement_vs_proposal=e.improvement,margin_improvement_points=e.margin_improvement,cost_known=e.profit['revised_cost'] is not None,
                projected_cost=float(e.profit['revised_cost']) if e.profit['revised_cost'] is not None else 0,
                projected_profit=e.profit['revised_gross_profit'],projected_margin=e.profit['revised_margin_percent'],risk_status=e.profit['risk_status']))
            for row in e.lines:self.env[DETAIL]._record(dict(batch_id=self.batch_id.id,result_id=result.id,allocation_entry_id=row['allocation_entry_id'],values=row))
            return result

    def get_current_scenario(self):
        self.ensure_one();e=ScenarioEngine(self).build();result=self.env[RESULT].search([('scenario_id','=',self.id)],order='id desc',limit=1)
        if not result or result.fingerprint!=e.fingerprint or not e.source_current:raise UserError('Scenario missing/stale; revalidate sources or create a new baseline scenario.')
        if self.env[EVENT].search([('scenario_id','=',self.id)],limit=1).event=='archived':raise UserError('Archived scenario is historical only.')
        return result

    def _current_state(self):
        for r in self:
            try:r.current_state=r.get_current_scenario().state
            except (AccessError,UserError,ValidationError):r.current_state='stale_or_not_calculated'

    @api.depends('event_ids','event_ids.event','event_ids.result_id','input_ids',
        'baseline_id.margin_id.sales_id.order_ids.order_line.price_unit')
    def _selection_status(self):
        for r in self:
            event=self.env[EVENT].search([('scenario_id','=',r.id)],limit=1)
            status=event.event if event and (event.event=='archived' or event.result_id.input_id==r._inputs()) else 'not_selected'
            if status in ('shortlisted','preferred_for_review'):
                try:
                    current=Reconciler(r.batch_id,r.baseline_id.margin_id.id).build()
                    if current.fingerprint!=event.result_id.provenance['upstream_fingerprint'] or current.outcome['readiness']!='ready_for_financial_review':status='historical_selection_requires_revalidation'
                except (AccessError,UserError,ValidationError):status='historical_selection_requires_revalidation'
            r.selection_status=status

    def action_select_for_review(self,event,reason):
        self._edit();reason=text(reason,'Analytical selection')
        if event not in ('not_selected','shortlisted','preferred_for_review','archived'):raise ValidationError('Selection is never accepted, approved or applied.')
        result=self.get_current_scenario() if event!='archived' else self.env[RESULT]
        if event in ('shortlisted','preferred_for_review') and result.state!='financially_verified':raise UserError('Only current reconciled analytical results may be preferred.')
        last=self.env[EVENT].search([('scenario_id','=',self.id)],limit=1)
        if last and last.event==event and last.reason==reason and last.result_id==result:return last
        return self.env[EVENT]._record(dict(batch_id=self.batch_id.id,scenario_id=self.id,result_id=result.id,event=event,reason=reason,actor_id=self.env.uid,recorded_at=fields.Datetime.now()))

    def action_clone_scenario(self,name):
        self.ensure_one();self.check_access('read');finance_allowed(self.batch_id)
        clone=self.batch_id.action_create_vendor_scenario(self.baseline_id.id,text(name,'Scenario name'),self.id)
        clone.action_set_assumptions([deepcopy(r.values) for r in self._inputs().line_ids],'Cloned assumptions; fresh calculation required')
        return clone

    def action_compare_scenarios(self):
        self.check_access('read')
        if not self or len(self)>100:raise ValidationError('Select between1 and100 alternatives.')
        if len(self.mapped('baseline_id'))!=1:raise ValidationError('Incomparable baseline cohorts: exact demand, revenue and source versions required.')
        results=self.env[RESULT]
        for r in self:results|=r.get_current_scenario()
        if any(r.state!='financially_verified' or not r.complete for r in results):raise UserError('Incomplete/stale alternatives cannot be ranked as superior.')
        return dict(type='ir.actions.act_window',name='Hypothetical alternatives - never additive',res_model=RESULT,view_mode='list,form',domain=[('id','in',results.ids)])

    def action_open_inputs(self):
        self._edit();return dict(type='ir.actions.act_window',res_model=PREFIX+'.wizard',view_mode='form',target='new',context=dict(default_scenario_id=self.id))

    def action_calculate_view(self):
        r=self.action_calculate_scenario()
        return dict(type='ir.actions.act_window',res_model=RESULT,res_id=r.id,view_mode='form')

    def action_open_clone(self):
        self.ensure_one();self.check_access('read');finance_allowed(self.batch_id)
        return dict(type='ir.actions.act_window',res_model=PREFIX+'.create.wizard',view_mode='form',target='new',context=dict(default_baseline_id=self.baseline_id.id,default_parent_id=self.id))

    def action_open_selection(self):
        self._edit();return dict(type='ir.actions.act_window',res_model=PREFIX+'.selection.wizard',view_mode='form',target='new',context=dict(default_scenario_id=self.id))

    def action_open_baseline(self):
        self.ensure_one();self.check_access('read');self.baseline_id.check_access('read')
        return dict(type='ir.actions.act_window',res_model=BASE,res_id=self.baseline_id.id,view_mode='form')

class ScenarioInput(models.Model):
    _name=INPUT
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Immutable Scenario Input Version'
    _order='id desc'
    _unique=models.Constraint('UNIQUE(scenario_id,version)','One input version per scenario.')
    scenario_id=fields.Many2one(HEADER,required=True,ondelete='restrict')
    version=fields.Integer(required=True)
    previous_id=fields.Many2one(INPUT,ondelete='restrict')
    fingerprint=fields.Char(required=True)
    reason=fields.Text(required=True)
    actor_id=fields.Many2one('res.users',required=True)
    recorded_at=fields.Datetime(required=True)
    line_ids=fields.One2many(LINE,'input_id')

class ScenarioLine(models.Model):
    _name=LINE
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Exact Product or PO Scenario Assumption'
    input_id=fields.Many2one(INPUT,required=True,ondelete='restrict')
    product_id=fields.Many2one('product.product',required=True)
    po_line_id=fields.Integer(string='Exact hypothetical PO line ID')
    mode=fields.Char(required=True)
    values=fields.Json(required=True)

class ScenarioResult(models.Model):
    _name=RESULT
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Immutable Hypothetical Result - Alternatives Not Additive'
    _order='id desc'
    _unique=models.Constraint('UNIQUE(scenario_id,version)','One calculation version per scenario.')
    scenario_id=fields.Many2one(HEADER,required=True,ondelete='restrict')
    input_id=fields.Many2one(INPUT,required=True,ondelete='restrict')
    currency_id=fields.Many2one(related='scenario_id.currency_id')
    version=fields.Integer(required=True)
    previous_id=fields.Many2one(RESULT,ondelete='restrict')
    fingerprint=fields.Char(required=True)
    collected_at=fields.Datetime(required=True)
    actor_id=fields.Many2one('res.users',required=True)
    state=fields.Char(required=True,index=True)
    complete=fields.Boolean()
    cost_known=fields.Boolean()
    projected_cost=fields.Float(string='Projected supply cost (only when known)',aggregator=False)
    projected_profit=fields.Char(string='Projected gross profit (blank unavailable)')
    projected_margin=fields.Char(string='Projected margin (%) (blank unavailable)')
    improvement_vs_proposal=fields.Char(string='Potential improvement vs proposal (not realized)')
    margin_improvement_points=fields.Char(string='Margin improvement vs proposal (pp)')
    risk_status=fields.Char(required=True)
    financial=fields.Json(required=True)
    profit=fields.Json(required=True)
    provenance=fields.Json(required=True)
    controls=fields.Json(required=True)
    issues=fields.Json(required=True)
    detail_ids=fields.One2many(DETAIL,'result_id')

class ScenarioDetail(models.Model):
    _name=DETAIL
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Exact Scenario Allocation Contribution'
    result_id=fields.Many2one(RESULT,required=True,ondelete='restrict')
    allocation_entry_id=fields.Many2one('vendor.price.revision.allocation.entry',required=True,ondelete='restrict')
    values=fields.Json(required=True)

class ScenarioEvent(models.Model):
    _name=EVENT
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Append-Only Analytical Selection - Not Approval'
    _order='id desc'
    scenario_id=fields.Many2one(HEADER,required=True,ondelete='restrict')
    result_id=fields.Many2one(RESULT,ondelete='restrict')
    event=fields.Char(required=True)
    reason=fields.Text(required=True)
    actor_id=fields.Many2one('res.users',required=True)
    recorded_at=fields.Datetime(required=True)

class BatchScenario(models.Model):
    _inherit=BATCH
    def action_create_vendor_scenario(self,baseline_id,name,parent_id=0):
        self.ensure_one();finance_allowed(self);text(name,'Scenario name')
        if type(baseline_id) is not int or baseline_id<=0 or type(parent_id) is not int or parent_id<0:raise ValidationError('Use exact source IDs.')
        base=self.env[BASE].browse(baseline_id).exists();base.check_access('read')
        if not base or base.batch_id!=self:raise AccessError('Baseline must belong to this exact company/revision.')
        Reconciler(self,base.margin_id.id)
        parent=self.env[HEADER].browse(parent_id).exists() if parent_id else self.env[HEADER]
        parent.check_access('read')
        if parent and parent.baseline_id!=base:raise ValidationError('Cloning preserves the exact frozen baseline.')
        company_lock(self.env,self.company_id);self._lock()
        with self.env.cr.savepoint():
            result=self.env[HEADER]._record(dict(batch_id=self.id,baseline_id=base.id,name=name.strip(),parent_id=parent.id))
            result.action_set_assumptions([],'Original vendor proposal inherited for every unchanged product')
            return result

class BaselineScenarioAction(models.Model):
    _inherit=BASE
    def action_open_vendor_scenario(self):
        self.ensure_one();self.check_access('read');finance_allowed(self.batch_id)
        return dict(type='ir.actions.act_window',res_model=PREFIX+'.create.wizard',view_mode='form',target='new',context=dict(default_baseline_id=self.id))
