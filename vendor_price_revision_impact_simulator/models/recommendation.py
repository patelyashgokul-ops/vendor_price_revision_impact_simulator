"""Immutable analytical commercial recommendation register and controlled review."""
from odoo import api,fields,models
from odoo.exceptions import AccessError,UserError,ValidationError
from .import_validation import PREFIX as IMPORT_PREFIX
from .vendor_scenario import HEADER as SCENARIO
from .reconciliation import finance_allowed
from .recommendation_engine import RecommendationEngine,VERSION
from .product_resolution import company_lock
from .scenario_math import text
from .commercial_math import number
from .structural_validation import digest

PREFIX='vendor.price.revision.recommendation'
HEADER=PREFIX
LINE,OPTION,REVIEW=[PREFIX+'.'+v for v in ('line','option','review')]

class RecommendationPolicy(models.Model):
    _inherit='vendor.price.revision.config'
    recommendation_draft_policy=fields.Selection([('review','Permit analytical unsent quotation review'),('hold','Require commercial review for all quotations')],default='review',required=True)
    recommendation_recovery_scope=fields.Selection([('line','Independent exact sales lines'),('same_order','Permit explicit same-order revenue-proportional recovery')],default='line',required=True)
    recommendation_max_uplift_percent=fields.Char(string='Maximum recommendation net-price uplift (%) (blank unlimited)')
    @api.constrains('recommendation_max_uplift_percent')
    def _recommendation_limits(self):
        for r in self:
            if r.recommendation_max_uplift_percent:
                try:number(r.recommendation_max_uplift_percent,True)
                except ValueError as exc:raise ValidationError(str(exc)) from None

class Recommendation(models.Model):
    _name=HEADER
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Analytical Commercial Recommendation - Not Approval or Price Execution'
    _order='id desc'
    _unique=models.Constraint('UNIQUE(scenario_id,scope_key,version)','One recommendation version per exact analytical scope.')
    name=fields.Char(required=True)
    scenario_id=fields.Many2one(SCENARIO,required=True,ondelete='restrict')
    scenario_result_id=fields.Many2one(SCENARIO+'.result',required=True,ondelete='restrict')
    currency_id=fields.Many2one(related='scenario_id.currency_id')
    scope=fields.Json(required=True)
    scope_key=fields.Char(required=True,index=True)
    version=fields.Integer(required=True)
    previous_id=fields.Many2one(HEADER,ondelete='restrict')
    fingerprint=fields.Char(required=True)
    collected_at=fields.Datetime(required=True)
    actor_id=fields.Many2one('res.users',required=True)
    state=fields.Char(required=True,index=True)
    complete=fields.Boolean(string='Financial inputs and checks complete (not commercial permission)')
    summary=fields.Json(required=True)
    provenance=fields.Json(required=True)
    controls=fields.Json(required=True)
    required_revenue=fields.Char(string='Rounded-up company net revenue target (blank unavailable)')
    revenue_gap=fields.Char(string='Additional net revenue requirement (not cost reduction)')
    supplier_ceiling=fields.Char(string='Hypothetical supplier ceiling in company currency per comparison unit')
    line_ids=fields.One2many(LINE,'recommendation_id')
    option_ids=fields.One2many(OPTION,'recommendation_id')
    review_ids=fields.One2many(REVIEW,'recommendation_id')
    current_state=fields.Char(compute='_current_state')

    def _engine(self):
        self.ensure_one();self.check_access('read')
        scope=dict(self.scope);scope.pop('scenario_id')
        return RecommendationEngine(self.scenario_id,**scope).build()

    def get_current_recommendation(self):
        self.ensure_one();e=self._engine()
        current=self.search([('scenario_id','=',self.scenario_id.id),('scope_key','=',self.scope_key)],limit=1)
        latest=self.env[REVIEW].search([('recommendation_id','=',self.id)],limit=1)
        if current!=self or self.fingerprint!=e.fingerprint or latest.event=='archived':raise UserError('Recommendation stale/archived. Revalidate current source scenario and regenerate; historical prices are not current authority.')
        return self

    def _current_state(self):
        for r in self:
            try:r.current_state=r.get_current_recommendation().state
            except (AccessError,UserError,ValidationError):r.current_state='stale_or_archived'

    def action_record_review(self,event,reason,evidence,option_id=0):
        self.ensure_one();self.check_access('read');finance_allowed(self.batch_id)
        if event not in ('reviewed','preferred_for_review','not_preferred','archived'):raise ValidationError('Only analytical review events; management approval is outside PR18.')
        text(reason,'Review reason');text(evidence,'Commercial review evidence')
        if type(option_id) is not int or option_id<0:raise ValidationError('Select an exact optional recommendation option ID.')
        company_lock(self.env,self.company_id);self.batch_id._lock()
        option=self.env[OPTION].browse(option_id).exists() if option_id else self.env[OPTION];option.check_access('read')
        if option and option.recommendation_id!=self:raise AccessError('Review option must belong to this exact recommendation.')
        if event!='archived':self.get_current_recommendation()
        if event=='preferred_for_review' and (not self.complete or not option):raise UserError('Prefer an exact current financially reconciled option for review; never approve/apply it.')
        latest=self.env[REVIEW].search([('recommendation_id','=',self.id)],limit=1)
        if latest and latest.event==event and latest.reason==reason and latest.evidence==evidence and latest.option_id==option:return latest
        return self.env[REVIEW]._record(dict(batch_id=self.batch_id.id,recommendation_id=self.id,option_id=option.id,event=event,reason=reason,evidence=evidence,actor_id=self.env.uid,collected_at=fields.Datetime.now()))

    def action_compare_options(self):
        self.ensure_one();self.get_current_recommendation()
        return dict(type='ir.actions.act_window',name='Conditional alternatives - do not sum benefits',res_model=OPTION,view_mode='list,form',domain=[('recommendation_id','=',self.id)])

    def action_open_source(self):
        self.ensure_one();self.check_access('read');self.scenario_id.check_access('read')
        return dict(type='ir.actions.act_window',res_model=SCENARIO,res_id=self.scenario_id.id,view_mode='form')

    def action_revalidate(self):
        self.ensure_one();scope=dict(self.scope);scope.pop('scenario_id')
        r=self.scenario_id.action_generate_recommendations(**scope)
        return dict(type='ir.actions.act_window',res_model=HEADER,res_id=r.id,view_mode='form')

    def action_open_review(self):
        self.ensure_one();self.check_access('read');finance_allowed(self.batch_id)
        return dict(type='ir.actions.act_window',res_model=PREFIX+'.review.wizard',view_mode='form',target='new',context=dict(default_recommendation_id=self.id))

class RecommendationLine(models.Model):
    _name=LINE
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Exact Sales Line Target and Commercial Eligibility Evidence'
    recommendation_id=fields.Many2one(HEADER,required=True,ondelete='restrict')
    sale_line_id=fields.Many2one('sale.order.line',required=True,ondelete='restrict')
    product_id=fields.Many2one('product.product',required=True)
    customer_id=fields.Many2one('res.partner',required=True)
    comparison_uom_id=fields.Many2one('uom.uom',required=True)
    sales_currency_id=fields.Many2one('res.currency',required=True)
    sales_uom_id=fields.Many2one('uom.uom',required=True)
    eligibility=fields.Char(required=True)
    eligible_qty=fields.Char()
    recommended_net_price=fields.Char(string='Net company currency per comparison unit (blank unavailable)')
    financial_net_unit_reference=fields.Char(string='Whole-line target net unit reference (not eligibility or Odoo price_unit)')
    display_price_unit=fields.Char(string='Analytical Odoo price_unit reference in sales currency/UoM')
    values=fields.Json(required=True)
    def action_open_source(self):
        self.ensure_one();self.check_access('read');self.sale_line_id.check_access('read')
        return dict(type='ir.actions.act_window',res_model='sale.order',res_id=self.sale_line_id.order_id.id,view_mode='form')

class RecommendationOption(models.Model):
    _name=OPTION
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Separate Commercial Action Alternative - Not Executable or Additive'
    recommendation_id=fields.Many2one(HEADER,required=True,ondelete='restrict')
    kind=fields.Char(required=True)
    feasibility=fields.Char(required=True)
    priority=fields.Char(required=True,string='Explainable review priority')
    projected_profit_improvement=fields.Char(string='Projected profit improvement (not realized)')
    additional_net_revenue=fields.Char()
    reduced_procurement_cost=fields.Char()
    remaining_target_gap=fields.Char()
    risk_status=fields.Char()
    values=fields.Json(required=True)

class RecommendationReview(models.Model):
    _name=REVIEW
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Append-Only Commercial Review Evidence - Not Management Approval'
    _order='id desc'
    recommendation_id=fields.Many2one(HEADER,required=True,ondelete='restrict')
    option_id=fields.Many2one(OPTION,ondelete='restrict')
    event=fields.Char(required=True)
    reason=fields.Text(required=True)
    evidence=fields.Text(required=True)
    actor_id=fields.Many2one('res.users',required=True)
    collected_at=fields.Datetime(required=True)

class ScenarioRecommendation(models.Model):
    _inherit=SCENARIO
    def action_generate_recommendations(self,assumptions=None,objective='line_targets',alternative_ids=None):
        self.ensure_one();self.check_access('read');finance_allowed(self.batch_id)
        company_lock(self.env,self.company_id);self.batch_id._lock()
        self.env.cr.execute('SELECT id FROM vendor_price_revision_scenario WHERE id=%s FOR SHARE',[self.id])
        with self.env.cr.savepoint():
            e=RecommendationEngine(self,assumptions,objective,alternative_ids).build();key=digest(e.scope)
            old=self.env[HEADER].search([('scenario_id','=',self.id),('scope_key','=',key)],limit=1)
            if old and old.fingerprint==e.fingerprint and self.env[REVIEW].search([('recommendation_id','=',old.id)],limit=1).event!='archived':return old
            r=self.env[HEADER]._record(dict(batch_id=self.batch_id.id,name='Commercial recommendation / '+self.name,scenario_id=self.id,scenario_result_id=e.rs.id,
                scope=e.scope,scope_key=key,version=old.version+1 if old else 1,previous_id=old.id,fingerprint=e.fingerprint,collected_at=fields.Datetime.now(),actor_id=self.env.uid,
                state=e.state,complete=e.complete,summary=e.summary,provenance=e.provenance,controls=e.controls.checks,
                required_revenue=e.summary['required_rounded'],revenue_gap=e.summary['additional_required'],supplier_ceiling=e.summary['supplier_unit_ceiling_company']))
            for row in e.rows:
                native=row['native_price'] or {}
                self.env[LINE]._record(dict(batch_id=self.batch_id.id,recommendation_id=r.id,sale_line_id=row['sale_line_id'],product_id=row['product_id'],customer_id=row['customer_id'],
                    comparison_uom_id=row['comparison_uom_id'],sales_currency_id=row['sales_currency_id'],sales_uom_id=row['sales_uom_id'],eligibility=row['eligibility'],eligible_qty=row['eligible_qty'],
                    recommended_net_price=native.get('net_unit_company_comparison'),financial_net_unit_reference=row['financial_net_unit_reference'],display_price_unit=native.get('display_price_unit'),values=row))
            for v in e.options:self.env[OPTION]._record(dict(batch_id=self.batch_id.id,recommendation_id=r.id,kind=v['kind'],feasibility=v['feasibility'],priority=v['priority'],risk_status=v['risk']['risk_status'],
                projected_profit_improvement=v['projected_profit_improvement'],additional_net_revenue=v['additional_net_revenue'],reduced_procurement_cost=v['reduced_procurement_cost'],remaining_target_gap=v['remaining_target_gap'],values=v))
            return r

    def action_open_recommendations(self):
        self.ensure_one();self.check_access('read');finance_allowed(self.batch_id)
        return dict(type='ir.actions.act_window',res_model=PREFIX+'.wizard',view_mode='form',target='new',context=dict(default_scenario_id=self.id))

class RecommendationWizard(models.TransientModel):
    _name=PREFIX+'.wizard'
    _inherit='vendor.price.revision.purchase.wizard.boundary'
    _description='Exact Commercial Recommendation Scope'
    scenario_id=fields.Many2one(SCENARIO,required=True)
    baseline_id=fields.Many2one(related='scenario_id.baseline_id')
    objective=fields.Selection([('line_targets','Independent exact line targets'),('same_order_targets','Governed same-order recovery')],default='line_targets',required=True)
    line_ids=fields.One2many(PREFIX+'.wizard.line','wizard_id')
    alternative_ids=fields.Many2many(SCENARIO,relation='vpr_recommendation_alternative_rel')
    def action_generate(self):
        self.ensure_one();assumptions=[]
        for line in self.line_ids:
            v=dict(sale_line_id=line.sale_line_id.id,reason=line.reason)
            for k in ('eligible_qty','max_net_source_unit','min_net_source_unit','conditions'):
                if line[k]:v[k]=line[k]
            assumptions.append(v)
        r=self.scenario_id.action_generate_recommendations(assumptions,self.objective,self.alternative_ids.ids)
        return dict(type='ir.actions.act_window',res_model=HEADER,res_id=r.id,view_mode='form')

class RecommendationWizardLine(models.TransientModel):
    _name=PREFIX+'.wizard.line'
    _inherit='vendor.price.revision.purchase.wizard.boundary'
    _description='Bounded Commercial Assumption - Cannot Grant Amendment Rights'
    wizard_id=fields.Many2one(PREFIX+'.wizard',required=True,ondelete='cascade')
    sale_line_id=fields.Many2one('sale.order.line',required=True)
    eligible_qty=fields.Char(string='Eligible subset in comparison UoM (blank all permitted outstanding)')
    max_net_source_unit=fields.Char(string='Maximum net price in original sales currency/UoM')
    min_net_source_unit=fields.Char(string='Minimum net price in original sales currency/UoM')
    conditions=fields.Text(string='Verified notice/acceptance conditions for analytical review')
    reason=fields.Text(required=True)

class RecommendationReviewWizard(models.TransientModel):
    _name=PREFIX+'.review.wizard'
    _inherit='vendor.price.revision.purchase.wizard.boundary'
    _description='Record Analytical Commercial Review'
    recommendation_id=fields.Many2one(HEADER,required=True)
    option_id=fields.Many2one(OPTION)
    event=fields.Selection([(v,v.replace('_',' ').title()) for v in ('reviewed','preferred_for_review','not_preferred','archived')],required=True)
    reason=fields.Text(required=True)
    evidence=fields.Text(required=True)
    def action_record(self):
        self.ensure_one();self.recommendation_id.action_record_review(self.event,self.reason,self.evidence,self.option_id.id or 0)
        return dict(type='ir.actions.act_window',res_model=HEADER,res_id=self.recommendation_id.id,view_mode='form')
