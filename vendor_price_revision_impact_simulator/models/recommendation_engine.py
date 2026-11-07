"""PR18 analytical customer/supplier alternatives over exact current PR17 evidence."""
from collections import defaultdict
from decimal import Decimal,localcontext
from odoo import fields
from odoo.exceptions import AccessError,UserError,ValidationError
from .commercial_math import number,price,quantity,rounded
from .financial_exposure import calculate
from .profitability_math import AMOUNTS,profitability,assess
from .profitability import nullable
from .reconciliation_controls import Controls,independent_profit,independent_risk
from .scenario_math import text
from .recommendation_math import target,upward,downward,eligibility,supplier_ceiling
from .structural_validation import digest

VERSION='pr18_exact_line_or_explicit_order_scope_native_tax_inverse_native_partial_remainder_v2'

def native_tax(source,display,qty=1):
    line=source.sale_line_id;line.check_access('read')
    base=line._prepare_base_line_for_taxes_computation(quantity=float(qty),price_unit=float(display),discount=float(source.source_discount_percent))
    source.env['account.tax']._add_tax_details_in_base_line(base,source.company_id)
    details=base['tax_details']
    return number(details['raw_total_excluded_currency']),number(details['raw_total_included_currency'])

def native_inverse(source,desired,eligible,cap=None,floor=None):
    """Probe native affine behavior, solve, round directionally, then recalculate."""
    fx=number(source.fx_evidence.get('rate'),True)
    if fx<=0:raise ValueError('SALES_FX_MISSING')
    a0,_=native_tax(source,0);a1,_=native_tax(source,1);a2,_=native_tax(source,2)
    slope=a1-a0
    if slope<=0 or abs(a2-a1-slope)>number('0.00000001'):raise ValueError('DISCOUNT_OR_NONAFFINE_TAX_REVIEW')
    src=source.source_uom_id;cmp=source.comparison_uom_id
    def to_source(company_unit):return price(number(company_unit)/fx,cmp.factor,src.factor)
    increment=number(source.sales_currency_id.rounding)
    value=upward((to_source(desired)-a0)/slope,increment)
    minimum=upward((to_source(floor)-a0)/slope,increment) if floor is not None else None
    maximum=downward((to_source(cap)-a0)/slope,increment) if cap is not None else None
    value=max(value,number(source.source_unit_price),minimum or number(0))
    if maximum is not None:
        if maximum<number(source.source_unit_price) or (minimum is not None and minimum>maximum):raise ValueError('PRICE_FLOOR_CAP_CONFLICT')
        value=min(value,maximum)
    net,total=native_tax(source,value)
    actual=price(net,src.factor,cmp.factor)*fx
    if cap is not None and actual>number(cap)+number('0.00000001'):raise ValueError('NATIVE_PRICE_EXCEEDS_NET_CAP')
    source_qty=quantity(eligible,cmp.factor,src.factor)
    subtotal,total=native_tax(source,value,source_qty)
    if abs(subtotal-net*source_qty)>increment:raise ValueError('NATIVE_QUANTITY_TAX_BASIS_REVIEW')
    source_net=rounded(subtotal,increment);source_total=rounded(total,increment)
    company_net=rounded(number(source_net)*fx,source.company_id.currency_id.rounding)
    return dict(display_price_unit=str(value),net_unit_source_uom=str(net),net_unit_company_comparison=str(actual),
        expected_tax_excluded_subtotal=source_net,expected_customer_total=source_total,
        expected_tax_amount=str(number(source_total)-number(source_net)),eligible_source_qty=str(source_qty),
        eligible_company_revenue=company_net,discount=source.source_discount_percent,fx=source.fx_evidence,
        sales_currency_id=source.sales_currency_id.id,sales_uom_id=src.id,comparison_uom_id=cmp.id,
        method='native_Odoo20_tax_base_line_affine_probe_directional_rounding_forward_recalculation')

class RecommendationEngine:
    def __init__(self,scenario,assumptions=None,objective='line_targets',alternative_ids=None):
        scenario.ensure_one();scenario.check_access('read')
        self.s=scenario;self.env=scenario.env;self.batch=scenario.batch_id;self.company=scenario.company_id
        self.rs=scenario.get_current_scenario();self.base=scenario.baseline_id;self.m=self.base.margin_id
        self.sales=self.m.sales_id;self.policy=self.env['vendor.price.revision.config'].browse(self.m.provenance['risk_policy']['id'])
        self.policy.check_access('read');self.today=fields.Date.today().isoformat();self.quantum=str(self.company.currency_id.rounding)
        if objective not in ('line_targets','same_order_targets'):raise ValidationError('Choose independent line targets or explicitly governed same-order recovery.')
        if objective=='same_order_targets' and self.policy.recommendation_recovery_scope!='same_order':raise ValidationError('Published company policy must permit same-order recovery; unrelated orders/quotes never share a gap.')
        self.objective=objective;self.controls=Controls();self.rows=[];self.options=[];self.issues=[]
        if assumptions is None:assumptions=[]
        if not isinstance(assumptions,list) or len(assumptions)>1000:raise ValidationError('Bound exact sales-line assumptions.')
        self.inputs={};ids=set(self.sales.line_ids.sale_line_id.ids)
        for raw in assumptions:
            if not isinstance(raw,dict) or set(raw)-{'sale_line_id','eligible_qty','max_net_source_unit','min_net_source_unit','conditions','reason'}:raise ValidationError('Unsupported commercial override; customer permission cannot be supplied as a context flag.')
            lid=raw.get('sale_line_id')
            if type(lid) is not int or lid not in ids or lid in self.inputs:raise AccessError('Use one exact authorized sales line in the selected cohort.')
            value=dict(raw);text(value.get('reason'),'Commercial assumption')
            for key in ('eligible_qty','max_net_source_unit','min_net_source_unit'):
                if key in value:
                    try:value[key]=str(number(value[key],True))
                    except ValueError as exc:raise ValidationError(str(exc)) from None
            if 'conditions' in value:text(value['conditions'],'Verified notice/customer-acceptance conditions for review')
            self.inputs[lid]=value
        alternative_ids=alternative_ids or []
        if not isinstance(alternative_ids,list) or len(alternative_ids)>20 or any(type(v) is not int or v<=0 for v in alternative_ids) or len(set(alternative_ids))!=len(alternative_ids):raise ValidationError('Select bounded exact alternative scenario IDs.')
        self.alternatives=self.env[self.s._name].browse(sorted(alternative_ids)).exists();self.alternatives.check_access('read')
        if len(self.alternatives)!=len(alternative_ids) or any(a.baseline_id!=self.base for a in self.alternatives):raise ValidationError('Commercial alternatives must share the exact PR16 baseline, demand and revenue cohort.')
        self.scope=dict(scenario_id=scenario.id,objective=objective,assumptions=[self.inputs[k] for k in sorted(self.inputs)],alternative_ids=sorted(alternative_ids))

    def build(self):
        with localcontext() as ctx:
            ctx.prec=38
            return self._build()

    def _build(self):
        c=self.controls;self.source_ok=self.rs.state=='financially_verified' and self.rs.complete
        c.record('CURRENT_RECONCILED_VENDOR_SCENARIO','financial_completeness','header','pass' if self.source_ok else 'blocked',message='PR16 readiness and current PR17 financial verification are mandatory; no assumption can waive them.')
        self.rules=self.m.provenance['risk_policy']['rules'];self.money=self.rs.profit
        company_policy=next((v for v in self.m.provenance['risk_policy']['margins'] if v['scope']=='company'),None)
        self.company_policy=company_policy
        n=self.money.get('net_revenue');cost=self.money.get('revised_cost')
        self.summary=target(cost,n,company_policy['target'],self.quantum) if company_policy else target(None,None,'0',self.quantum)
        self.summary.update(current_revenue=n,scenario_cost=cost,current_profit=self.money.get('revised_gross_profit'),current_margin=self.money.get('revised_margin_percent'),objective=self.objective,target_margin=company_policy['target'] if company_policy else None)
        c.equation('TARGET_REVENUE_INVERSION','financial_cost','header',cost,str(number(self.summary['required_raw'])*(1-number(company_policy['target'])/100)) if self.summary['required_raw'] is not None else None,self.quantum)
        by_sale=defaultdict(list)
        for detail in self.rs.detail_ids:by_sale[detail.allocation_entry_id.demand_id.sale_line_id].append(detail.values)
        margin={v.sale_line_id.id:v for v in self.m.line_ids}
        for source in self.sales.line_ids:
            q=number(source.outstanding_qty) if source.outstanding_qty else None;spec=self.inputs.get(source.sale_line_id.id,{})
            status=eligibility(source.source_order_state,source.price_protection,source.source_terms.get('validity_date'),self.today,self.policy.recommendation_draft_policy,bool(spec.get('conditions')))
            eligible=q if q is not None and status.startswith('eligible_') else number(0)
            if 'eligible_qty' in spec:
                selected=number(spec['eligible_qty'])
                if q is None or selected>q or (selected and not status.startswith('eligible_')):raise ValidationError('Eligible quantity cannot exceed verified outstanding or bypass customer protection/offer review.')
                eligible=selected
            values=by_sale[source.sale_line_id.id]
            complete=bool(values) and all(v['cost_complete'] for v in values) and source.valuation_status=='verified' and nullable(source.company_sales_value) is not None
            line_cost=str(sum((number(v['revised_extended_cost']) for v in values),number(0))) if complete else None
            policy=margin[source.sale_line_id.id].policy_evidence
            required=target(line_cost,nullable(source.company_sales_value),policy['target'],self.quantum) if policy else target(None,None,'0',self.quantum)
            row=dict(sale_line_id=source.sale_line_id.id,sale_order_id=source.sale_order_id.id,customer_id=source.customer_id.id,product_id=source.product_id.id,
                source_sales_line_id=source.id,comparison_uom_id=source.comparison_uom_id.id,sales_uom_id=source.source_uom_id.id,sales_currency_id=source.sales_currency_id.id,
                outstanding_qty=str(q) if q is not None else None,delivered_qty=source.delivered_qty,conditional_qty=str(q) if source.demand_type=='conditional' and q is not None else '0',
                eligible_qty=str(eligible),protected_qty=str(q) if q is not None and status=='protected_not_eligible' else '0',
                review_qty=str(q-eligible) if q is not None and status!='protected_not_eligible' else '0',eligibility=status,protection=source.price_protection,
                source_terms=source.source_terms,protection_evidence=source.protection_evidence,assumptions=spec,policy=policy,cost=line_cost,revenue=nullable(source.company_sales_value),
                current_net_source_comparison=nullable(source.net_sales_unit_price),discount=source.source_discount_percent,source_price_unit=source.source_unit_price,
                target=required,complete=complete,required_gap=required['additional_required'],native_price=None,issues=[])
            row['financial_net_unit_reference']=str(number(required['required_raw'])/q) if required['required_raw'] is not None and q else None
            self.rows.append(row)
            c.equation('OPEN_QTY_DISPOSITION','quantity_integrity',str(source.id),str(q) if q is not None else None,str(eligible+number(row['protected_qty'])+number(row['review_qty'])),'0','quantity')
        if self.objective=='same_order_targets':self.order_recovery()
        for row in self.rows:
            self.customer_line(row)
            row['outcome']=profitability(row.get('projected_revenue'),row['cost'],row['cost'],baseline_revenue=row['revenue'])
            row['risk']=assess(row['outcome'],row['policy'],self.rules,'scenario_only',row['complete'],[row['protection']])
        self.options.append(self.option('keep_existing_customer_price',n,cost,'not_applicable','Current selected vendor scenario; no customer price change'))
        customer_n=str(sum((number(v['projected_revenue']) for v in self.rows),number(0))) if self.rows and all(v.get('projected_revenue') is not None for v in self.rows) else None
        self.options.append(self.option('customer_eligible_price_review',customer_n,cost,'commercially_eligible_for_review' if any(number(v['eligible_qty'])>0 for v in self.rows) else 'customer_repricing_not_available','Only documented eligible quantities; line targets do not recover unrelated fixed-order gaps'))
        self.supplier_option()
        for alternative in self.alternatives:
            result=alternative.get_current_scenario()
            if result.state!='financially_verified' or not result.complete:raise UserError('Incomplete vendor alternative cannot become a financially verified commercial option.')
            self.options.append(self.option('supplier_scenario_'+str(alternative.id),result.profit['net_revenue'],result.profit['revised_cost'],'hypothetical_only','Current exact-baseline PR17 alternative; not accepted supplier terms',dict(scenario_id=alternative.id,result_id=result.id,fingerprint=result.fingerprint)))
            # Recalculate combined outcome on alternative costs; never add two
            # separately reported benefits. Source revenue/eligibility stay exact.
            combined_cost=result.profit['revised_cost']
            self.options.append(self.option('combined_customer_and_supplier_'+str(alternative.id),customer_n,combined_cost,'hypothetical_only','Customer candidate prices paired with this exact supplier scenario; recomputed profit/risk, not additive benefits'))
        c.unique('UNIQUE_SALES_LINE','quantity_integrity','all',[r['sale_line_id'] for r in self.rows])
        self.complete=self.source_ok and bool(self.rows) and all(v['complete'] and not v['issues'] for v in self.rows) and all(v['status'] in ('pass','not_applicable') for v in c.checks)
        self.state='financially_verified' if self.complete else 'review_required'
        self.provenance=dict(version=VERSION,scenario_id=self.s.id,scenario_result_id=self.rs.id,scenario_fingerprint=self.rs.fingerprint,
            baseline_id=self.base.id,margin_id=self.m.id,sales_id=self.sales.id,financial_id=self.m.financial_id.id,
            source_versions=self.rs.provenance,policy_id=self.policy.id,policy_version=self.policy.policy_version,
            constraints=dict(draft=self.policy.recommendation_draft_policy,recovery_scope=self.policy.recommendation_recovery_scope,max_uplift_percent=self.policy.recommendation_max_uplift_percent or None),
            alternatives_additive=False,benefits='projected conditional references; never realized income/cash/accepted terms',today=self.today)
        self.fingerprint=digest(dict(scope=self.scope,provenance=self.provenance,rows=self.rows,options=self.options,summary=self.summary,controls=c.checks))
        return self

    def order_recovery(self):
        groups=defaultdict(list)
        for row in self.rows:groups[row['sale_order_id']].append(row)
        for rows in groups.values():
            targets={v['policy']['target'] for v in rows if v['policy']}
            if len(targets)!=1 or any(not v['complete'] for v in rows):raise ValidationError('Same-order target requires complete costs and one coherent target; otherwise select independent lines.')
            total_cost=sum((number(v['cost']) for v in rows),number(0));revenue=sum((number(v['revenue']) for v in rows),number(0))
            gap=number(target(total_cost,revenue,next(iter(targets)),self.quantum)['additional_required'])
            weights={v['sale_line_id']:max(number(v['revenue']),number(0))*number(v['eligible_qty'])/number(v['outstanding_qty']) for v in rows if number(v['eligible_qty'])>0}
            denominator=sum(weights.values(),number(0))
            if denominator:
                for row in rows:row['required_gap']=str(gap*weights.get(row['sale_line_id'],0)/denominator)

    def customer_line(self,row):
        source=self.sales.line_ids.filtered(lambda v:v.id==row['source_sales_line_id']);q=number(row['eligible_qty']);n=row['revenue']
        row['projected_revenue']=n
        if not row['complete'] or n is None:
            row['issues'].append('SOURCE_COST_REVENUE_INCOMPLETE');return
        gap=number(row['required_gap']) if row['required_gap'] is not None else None
        if gap is None:row['issues'].append('TARGET_POLICY_MISSING');return
        if gap<=0:row['action']='keep_current_price_no_uplift_for_selected_objective';return
        if not q:row['action']='preserve_price_contract_or_offer_review';return
        full_q=number(row['outstanding_qty']);spec=row['assumptions'];cap=None;floor=None
        fx=number(source.fx_evidence.get('rate'),True)
        if self.policy.recommendation_max_uplift_percent:
            native_current,_=native_tax(source,source.source_unit_price)
            current=price(native_current,source.source_uom_id.factor,source.comparison_uom_id.factor)*fx
            cap=current*(1+number(self.policy.recommendation_max_uplift_percent)/100)
        for key in ('max_net_source_unit','min_net_source_unit'):
            if key in spec:
                converted=price(spec[key],source.source_uom_id.factor,source.comparison_uom_id.factor)*fx
                if key.startswith('max'):cap=min(cap,converted) if cap is not None else converted
                else:floor=converted
        try:
            unchanged=number(0)
            if q<full_q:
                remaining=quantity(full_q-q,source.comparison_uom_id.factor,source.source_uom_id.factor)
                native_remaining,_=native_tax(source,source.source_unit_price,remaining)
                source_remaining=rounded(native_remaining,source.sales_currency_id.rounding)
                unchanged=number(rounded(number(source_remaining)*fx,self.quantum))
                proportional=number(n)*(full_q-q)/full_q
                row['unchanged_price_evidence']=dict(comparison_qty=str(full_q-q),source_qty=str(remaining),
                    original_source_price=source.source_unit_price,discount=source.source_discount_percent,
                    net_source_subtotal=source_remaining,company_revenue=str(unchanged),
                    previous_proportional_company_revenue=str(proportional),rounding_difference=str(unchanged-proportional),
                    method='native_original_price_discount_tax_remaining_quantity_source_then_company_currency_rounding_no_write')
            desired=(number(n)+gap-unchanged)/q
            candidate=None
            for attempt in range(4):
                candidate=native_inverse(source,desired,q,cap,floor)
                proposed=unchanged+number(candidate['eligible_company_revenue'])
                if proposed>=number(n)+gap or (cap is not None and number(candidate['net_unit_company_comparison'])>=cap-number('0.00000001')):break
                if cap is not None and desired>=cap:break
                desired+=(number(n)+gap-proposed+number(self.quantum)/2)/q
            row['native_price']=candidate;row['projected_revenue']=str(proposed)
            row['additional_revenue']=str(proposed-number(n));row['remaining_gap']=str(max(number(n)+gap-proposed,number(0)))
            row['action']='price_cap_constrained' if number(row['remaining_gap'])>0 and cap is not None else 'customer_price_review'
            if number(row['remaining_gap'])>0 and cap is None:raise ValueError('NATIVE_ROUNDING_TARGET_NOT_REACHED')
            self.controls.equation('ELIGIBLE_RECOVERY_EXTENSION','sales_revenue',str(source.id),str(proposed-number(n)),row['additional_revenue'],self.quantum)
        except (ValueError,KeyError) as exc:
            row['issues'].append(str(exc));row['action']='discount_tax_commercial_review';row['projected_revenue']=None

    def option(self,kind,revenue,cost,feasibility,reason,extra=None):
        v=profitability(revenue,nullable(self.money.get('revised_cost')),cost,baseline_revenue=self.money.get('net_revenue'))
        # The baseline option uses unchanged original revenue and cost. For an
        # actual revenue-changing option compare against original profit explicitly.
        baseline_profit=nullable(self.money.get('revised_gross_profit'))
        improvement=str(number(v['revised_gross_profit'])-number(baseline_profit)) if v['revised_gross_profit'] is not None and baseline_profit is not None else None
        risk=assess(v,self.company_policy,self.rules,'scenario_only',revenue is not None and cost is not None,[r['protection'] for r in self.rows])
        expected=independent_profit(revenue,nullable(self.money.get('revised_cost')),cost,baseline_revenue=self.money.get('net_revenue'))
        expected_risk,_=independent_risk(v,self.company_policy,self.rules,revenue is not None and cost is not None,[r['protection'] for r in self.rows])
        self.controls.truth('OPTION_RISK_RECALCULATED','risk_classification',kind,all(expected_risk[k]==risk[k] for k in expected_risk))
        for field in AMOUNTS:
            if expected[field] is None and v[field] is None and ('percent' in field or 'points' in field):
                self.controls.record('OPTION_'+field.upper(),'margin_integrity',kind,'not_applicable',message='Ratio mathematically undefined; not substituted with zero')
            else:self.controls.equation('OPTION_'+field.upper(),'margin_integrity',kind,expected[field],v[field],'0.00000001' if 'percent' in field or 'points' in field else self.quantum)
        required=target(cost,revenue,self.company_policy['target'],self.quantum) if self.company_policy else target(None,None,'0',self.quantum)
        if revenue is None or cost is None or not self.source_ok:feasibility='source_evidence_incomplete'
        elif kind=='customer_eligible_price_review' and any(r.get('action')=='price_cap_constrained' for r in self.rows):feasibility='price_cap_constrained'
        priority='10_eligible_financial_review' if feasibility=='commercially_eligible_for_review' else '20_hypothetical_supplier_review' if feasibility=='hypothetical_only' else '90_incomplete' if feasibility=='source_evidence_incomplete' else '30_commercial_or_contract_review'
        return dict(kind=kind,feasibility=feasibility,priority=priority,reason=reason,values=v,risk=risk,
            additional_net_revenue=str(number(revenue)-number(self.money['net_revenue'])) if revenue is not None and self.money.get('net_revenue') is not None else None,
            reduced_procurement_cost=str(number(self.money['revised_cost'])-number(cost)) if cost is not None and self.money.get('revised_cost') is not None else None,
            projected_profit_improvement=improvement,remaining_target_gap=required['additional_required'],source=extra or {},approved=False,applied=False)

    def supplier_option(self):
        details=[v.values for v in self.rs.detail_ids];new=[v for v in details if v['source_type']=='new_procurement_requirement']
        assumptions=[v.values for v in self.s._inputs().line_ids]
        tier_products=[r.resolved_product_id.id for r in self.batch.row_ids if not r.excluded and r.commercial_result_id and r.commercial_result_id.snapshot.get('proposal')]
        supported=(self.source_ok and self.m.financial_id.fx_method=='same_rate' and new and len({(v['product_id'],v['comparison_uom_id']) for v in new})==1
            and tier_products.count(new[0]['product_id'])==1
            and all(not any(k in a for k in ('row_id','grouped','landed','effective_date','po_line_id')) and a.get('fx_method','price_only_common_fx')=='price_only_common_fx' for a in assumptions))
        unchanged=sum((number(v['revised_extended_cost']) for v in details if v not in new),number(0)) if supported else None
        q=sum((number(v['quantity']) for v in new),number(0)) if supported else None
        ceiling=supplier_ceiling(self.summary['max_cost'],unchanged,q)
        self.summary.update(supplier_unit_ceiling_company=ceiling,unchanged_cost=str(unchanged) if unchanged is not None else None,new_procurement_qty=str(q) if q is not None else None)
        if ceiling is None:
            self.options.append(self.option('supplier_negotiation_review',self.money.get('net_revenue'),self.money.get('revised_cost'),'contract_review_required','No single defensible unit ceiling: zero procurement, incomplete/nonlinear/multiple-product/FX/landed assumptions; evaluate explicit PR17 alternatives'))
        else:
            unit=calculate(str(q),ceiling,ceiling)
            total=str(min(number(self.money['revised_cost']),unchanged+number(unit['revised_extended_cost'])))
            self.options.append(self.option('supplier_unit_ceiling',self.money.get('net_revenue'),total,'hypothetical_only','Financial ceiling in company currency per comparison unit; not a supplier offer. Evaluate source-currency/tier feasibility in PR17',dict(unit_ceiling=ceiling,quantity=str(q),unchanged_cost=str(unchanged))))
