"""Pure analytical adapters over PR08/13/14/15 with PR16 control equations."""
from collections import defaultdict
from copy import deepcopy
from decimal import Decimal, localcontext
from types import SimpleNamespace
from odoo.exceptions import AccessError, ValidationError
from .commercial_engine import CommercialEngine
from .commercial_math import number, price, rounded, decomposition
from .cost_attribution import CostEngine
from .financial_exposure import FinancialEngine, calculate
from .profitability import MarginEngine, nullable
from .profitability_math import AMOUNTS, profitability, assess
from .reconciliation import Reconciler
from .reconciliation_controls import Controls, readiness, independent_profit, independent_risk
from .scenario_math import decimal, negotiated
from .structural_validation import digest

VERSION='pr17_frozen_cohort_shared_financial_margin_independent_controls_v1'

class ScenarioEngine:
    def __init__(self,scenario):
        scenario.ensure_one();scenario.check_access('read')
        self.scenario=scenario;self.env=scenario.env;self.batch=scenario.batch_id
        self.base=scenario.baseline_id;self.base.check_access('read')
        if self.base.batch_id!=self.batch:raise AccessError('Scenario requires the exact baseline batch/company.')
        self.m=self.base.margin_id;self.f=self.m.financial_id;self.cost=self.f.cost_id;self.a=self.cost.allocation_id
        self.company=scenario.company_id;self.input=scenario._inputs();self.controls=Controls()
        self.lines=[];self.issues=[];self.margin_lines=[]

    def build(self):
        with localcontext() as ctx:
            ctx.prec=38
            return self._build()

    def _build(self):
        c=self.controls
        upstream=Reconciler(self.batch,self.m.id).build()
        self.source_current=upstream.fingerprint==self.base.fingerprint
        c.truth('EXACT_CURRENT_BASELINE','snapshot_freshness','baseline',self.source_current)
        c.record('BASELINE_READINESS','financial_completeness','baseline',
            'pass' if upstream.outcome['readiness']=='ready_for_financial_review' else 'blocked',
            expected='ready_for_financial_review',observed=upstream.outcome['readiness'],severity='high')
        self.policy=self.env['vendor.price.revision.config'].browse(self.m.provenance['risk_policy']['id'])
        self.policy.check_access('read');self.rules=self.m.provenance['risk_policy']['rules']
        self.commercial=CommercialEngine(self.batch)
        self.proposals=[(r.id,r.commercial_result_id.id,deepcopy(r.commercial_result_id.snapshot)) for r in self.batch.get_commercially_valid_rows()]
        self.specs={(r.product_id.id,r.po_line_id or 0):r.values for r in self.input.line_ids}
        self.used=set()
        for source in self.f.line_ids.sorted('id'):self.line(source)
        c.truth('ALL_ASSUMPTIONS_CONSUMED','scenario_consistency','inputs',self.used==set(self.specs))
        helper=SimpleNamespace(lines=self.lines,cost=self.cost,a=self.a,company=self.company,
            quantity_unresolved=list(self.f.reconciliation['unresolved_demand_ids']))
        FinancialEngine.aggregate(helper)
        self.financial=dict(totals=helper.totals,groups=helper.groups,reconciliation=helper.reconciliation)
        self.margin()
        self.outcome=readiness(c.checks,bool(self.a.demand_ids))
        self.complete=helper.cost_complete and self.profit['complete'] and not self.issues
        self.state='financially_verified' if self.outcome['readiness']=='ready_for_financial_review' and self.complete else 'stale' if not self.source_current else 'blocked' if self.outcome['readiness']=='blocked' else 'incomplete'
        proposed=nullable(self.m.revised_cost);revised=self.profit['revised_cost']
        self.improvement=str(number(proposed)-number(revised)) if proposed is not None and revised is not None and self.complete else None
        original_margin=nullable(self.m.revised_margin_percent);new_margin=self.profit['revised_margin_percent']
        self.margin_improvement=str(number(new_margin)-number(original_margin)) if original_margin is not None and new_margin is not None and self.complete else None
        self.provenance=dict(version=VERSION,baseline_id=self.base.id,baseline_fingerprint=self.base.fingerprint,
            upstream_fingerprint=upstream.fingerprint,assumption_fingerprint=self.input.fingerprint,
            sources=self.base.provenance,source_versions=self.m.provenance,price_accepted=False,
            fx_convention='supplier_at_old_rate_then_fx_on_proposed_price',alternatives_additive=False,
            confidence='hypothetical scenario; source estimates retain original confidence',
            changed_assumptions=[r.values for r in self.input.line_ids],risk_policy=self.m.provenance['risk_policy'])
        self.provenance['scenario_landed_policy']=self.policy.scenario_landed_policy
        self.fingerprint=digest(dict(version=VERSION,input=self.input.fingerprint,input_id=self.input.id,baseline=self.base.fingerprint,scenario_landed_policy=self.policy.scenario_landed_policy,
            source=upstream.fingerprint,lines=self.lines,profit=self.profit,checks=c.checks,issues=self.issues))
        return self

    def issue(self,source,message):
        code='SCENARIO_ASSUMPTION_UNRESOLVED';key='entry:'+str(source.allocation_entry_id.id)
        self.issues.append(dict(entry_id=source.allocation_entry_id.id,code=code,message=message))
        self.controls.record(code,'commercial_pricing',key,'blocked',message=message,severity='high')

    def line(self,source):
        c=self.controls;entry=source.allocation_entry_id;kind=source.source_type
        b=nullable(source.baseline_unit_cost);r=nullable(source.revised_unit_cost)
        p=source.product_id;po=source.cost_line_id.evidence.get('po_line_id',0)
        key=(p,po) if po and (p,po) in self.specs else (p,0)
        spec=self.specs.get(key) if kind=='new_procurement_requirement' or (po and key[1]) else None
        evidence=dict(source_financial_line_id=source.id,source_cost_line_id=source.cost_line_id.id,
            original_cost_confidence=source.cost_confidence,original_evidence=source.evidence)
        parts=None
        if spec is not None:
            self.used.add(key);evidence['assumptions']=spec
            try:r,parts=self.resolve(source,spec)
            except (ValueError,ValidationError) as exc:r=None;self.issue(source,str(exc))
        if kind!='new_procurement_requirement' and b is None:r=None
        unchanged=spec is None and kind!='new_procurement_requirement'
        values=calculate(source.quantity,b,r,unchanged)
        row=dict(source_financial_line_id=source.id,allocation_entry_id=entry.id,product_id=p,warehouse_id=source.warehouse_id.id,
            comparison_uom_id=source.comparison_uom_id.id,currency_id=source.currency_id.id,demand_type=source.demand_type,
            quantity=source.quantity,source_type=kind,capacity_key=source.capacity_key,cost_confidence=source.cost_confidence,
            cost_complete=b is not None and r is not None,delta_complete=values['incremental_extended_cost'] is not None,
            verified_delta=bool(unchanged and values['incremental_extended_cost'] is not None),status='scenario_only' if b is not None and r is not None else 'incomplete',
            reported_values={k:rounded(values[k],self.company.currency_id.rounding) if values[k] is not None else None for k in ('baseline_extended_cost','revised_extended_cost','incremental_extended_cost')},
            evidence=evidence,decomposition=parts,**values)
        self.lines.append(row);k='entry:'+str(entry.id)
        c.equation('SOURCE_QUANTITY','quantity_integrity',k,entry.quantity,row['quantity'],'0','quantity')
        c.equation('BASELINE_PRESERVED','financial_cost',k,nullable(source.baseline_extended_cost),values['baseline_extended_cost'],str(self.company.currency_id.rounding))
        if unchanged:c.equation('PROTECTED_COST_UNCHANGED','financial_cost',k,nullable(source.revised_extended_cost),values['revised_extended_cost'],str(self.company.currency_id.rounding))
        c.equation('SCENARIO_COST_EXTENSION','financial_cost',k,str(number(r)*number(source.quantity)) if r is not None else None,values['revised_extended_cost'],str(self.company.currency_id.rounding))
        if parts:c.equation('PRICE_FX_DECOMPOSITION','financial_cost',k,str(number(parts['total'])*number(source.quantity)),values['incremental_extended_cost'],str(self.company.currency_id.rounding))

    def resolve(self,source,spec):
        po=spec.get('po_line_id',0)
        if po:
            basis=source.cost_line_id.evidence
            if basis.get('po_line_id')!=po or source.cost_confidence!='verified_commercial_basis':
                raise ValidationError('Exact current verified open PR12 protection required for a PO hypothesis.')
            proposal=basis.get('recorded_source_unit_cost');old=proposal
            currency=basis.get('source_currency_id');uid=source.comparison_uom_id.id
            old_fx=number(basis['recorded_company_unit_cost'])/number(old) if old and number(old) else Decimal(1) if currency==self.company.currency_id.id else None
            if old_fx is None:raise ValidationError('Verified PO FX basis is unavailable.')
            source_factor=target_factor=source.comparison_uom_id.factor
        else:
            basis=source.evidence.get('pricing',{})
            offer=basis.get('proposal') or source.cost_line_id.evidence.get('proposal')
            if not offer:raise ValidationError('Original proposed commercial basis is missing.')
            if basis.get('source_currency_id')!=offer['source_currency_id']:
                raise ValidationError('Changed-source-currency negotiation requires a separately supported comparison basis.')
            currency=offer['source_currency_id'];uid=offer['source_uom_id']
            source_factor=self.env['uom.uom'].browse(uid).factor;target_factor=source.comparison_uom_id.factor
            proposal=str(number(offer['net_comparable'])*number(source_factor)/number(target_factor))
            old_comparable=basis.get('source_old_unit')
            old=str(number(old_comparable)*number(source_factor)/number(target_factor)) if old_comparable is not None else None
            old_fx=number(basis['old_fx']['rate']) if basis.get('old_fx') else None
            if old_fx is None:raise ValidationError('Original verified FX is missing.')
        if spec.get('currency_id',currency)!=currency or spec.get('uom_id',uid)!=uid:
            raise ValidationError('Use the exact original source currency and purchase UoM.')
        mode=spec.get('mode','original')
        if mode=='tier':
            if po:raise ValidationError('A PO amendment cannot select a procurement MOQ tier.')
            q=number(source.quantity)
            if spec.get('grouped'):
                group=[v for v in self.f.line_ids if v.source_type=='new_procurement_requirement' and v.product_id==source.product_id and v.warehouse_id==source.warehouse_id and v.comparison_uom_id==source.comparison_uom_id]
                q=sum((number(v.quantity) for v in group),Decimal(0))
            if 'buying_quantity' in spec and number(spec['buying_quantity'])!=q:raise ValidationError('Surplus/invented buying quantity unsupported; exact residual scope only.')
            ce=SimpleNamespace(scope=self.cost.scope,proposals=self.proposals,batch=self.batch,company=self.company,policy=self.policy,commercial=self.commercial,env=self.env)
            proxy=SimpleNamespace(quantity=str(q),demand_id=source.allocation_entry_id.demand_id)
            unit,confidence,tier=CostEngine.replacement(ce,proxy)
            if unit is None or tier.get('row_id')!=spec.get('row_id'):raise ValidationError('Selected PR08 tier ineligible, expired or ambiguous for actual residual procurement.')
            chosen=tier['proposal']
            if chosen['source_currency_id']!=currency:raise ValidationError('Changed-currency tier comparison unsupported.')
            amount=number(chosen['net_comparable']);fx=number(tier['fx']['rate'])
        else:
            amount=price(negotiated(proposal,old,mode,spec.get('value'),spec.get('discount_base','proposal')),source_factor,target_factor)
            fx=old_fx if po or self.f.fx_method=='same_rate' else number(basis.get('new_fx',{}).get('rate',old_fx))
        if spec.get('fx_method','price_only_common_fx') in ('combined_price_and_fx','fx_only_sensitivity'):
            if self.policy.fx_override_policy!='finance_governed':raise ValidationError('Published policy must permit Finance-governed hypothetical FX.')
            if currency==self.company.currency_id.id:raise ValidationError('Same-currency costs cannot use a hypothetical exchange rate.')
            fx=decimal(spec.get('fx_rate'),True)
        if spec.get('effective_date'):
            if po:raise ValidationError('Protected PO dates preserved; use a specific price amendment only.')
            timing=spec.get('commitment_date')
            if not timing:raise ValidationError('Commercial commitment timing uncertain; delivery/planning date alone insufficient.')
            if timing<spec['effective_date']:
                if old is None:raise ValidationError('Old commercial price unavailable before the effective date.')
                amount=price(old,source_factor,target_factor)
        if old is None:raise ValidationError('Old comparable commercial price missing.')
        parts=decomposition(price(old,source_factor,target_factor),amount,old_fx,fx)
        landed=spec.get('landed',[])
        if landed:
            if po or self.policy.scenario_landed_policy!='evidenced_nonrecoverable_charges':raise ValidationError('Future landed components require governed scenario nonrecoverable-charge policy and new procurement.')
            extra=sum((number(v['amount']) for v in landed),Decimal(0));parts=None
        else:extra=Decimal(0)
        return str(amount*fx+extra),parts

    def margin(self):
        c=self.controls;by_demand=defaultdict(list)
        for row in self.lines:by_demand[self.env['vendor.price.revision.allocation.entry'].browse(row['allocation_entry_id']).demand_id.id].append(row)
        for original in self.m.line_ids:
            rows=by_demand[original.sales_line_id.allocation_demand_source_id]
            complete=bool(rows) and all(v['cost_complete'] for v in rows)
            b=str(sum((number(v['baseline_extended_cost']) for v in rows),Decimal(0))) if complete else None
            r=str(sum((number(v['revised_extended_cost']) for v in rows),Decimal(0))) if complete else None
            revenue=nullable(original.net_revenue);v=profitability(revenue,b,r);ok=complete and revenue is not None
            policy=original.policy_evidence;risk=assess(v,policy,self.rules,'scenario_only',ok,[original.price_protection])
            independent=independent_profit(revenue,b,r)
            for field in AMOUNTS:c.equation('MARGIN_'+field.upper(),'margin_integrity','sale_line:'+str(original.sale_line_id.id),independent[field],v[field],'0.00000001' if 'percent' in field or 'points' in field else str(self.company.currency_id.rounding))
            expected,_=independent_risk(v,policy,self.rules,ok,[original.price_protection])
            c.truth('RISK_RECALCULATED','risk_classification','sale_line:'+str(original.sale_line_id.id),all(expected[k]==risk[k] for k in expected))
            self.margin_lines.append(dict(sale_line_id=original.sale_line_id.id,product_id=original.product_id.id,demand_type=original.demand_type,
                quantity=original.quantity,comparison_uom_id=original.comparison_uom_id.id,price_protection=original.price_protection,
                state='scenario_only' if ok else 'incomplete',complete=ok,**v,**risk))
        c.unique('NO_DUPLICATE_ALLOCATION','quantity_integrity','all',[v['allocation_entry_id'] for v in self.lines])
        c.truth('EXACT_ENTRY_COVERAGE','quantity_integrity','all',{v['allocation_entry_id'] for v in self.lines}==set(self.a.entry_ids.ids))
        policy=next((v for v in self.m.provenance['risk_policy']['margins'] if v['scope']=='company'),None)
        self.profit=MarginEngine.aggregate(SimpleNamespace(company=self.company,rules=self.rules),self.margin_lines,policy)
        independent=independent_profit(self.profit['net_revenue'],self.financial['totals']['baseline_total'],self.financial['totals']['revised_total'])
        for field in AMOUNTS:c.equation('TOTAL_'+field.upper(),'margin_integrity','all',independent[field],self.profit[field],'0.00000001' if 'percent' in field or 'points' in field else str(self.company.currency_id.rounding))
