"""Independent Decimal control equations, not an allocation/pricing publisher.

Controls consume frozen evidence. They never call the upstream profit/risk helpers.
Canonical decimal strings in JSON accompany typed UI numeric values.
"""
from collections import Counter, defaultdict
from decimal import Decimal, localcontext
from .commercial_math import number

VERSION = 'pr16_independent_equations_unique_lineage_explicit_projection_review_v1'
STATUSES = ('pass','fail','blocked','not_applicable','not_run','stale')


def metric(numerator, denominator, scope):
    n, d = number(numerator), number(denominator)
    return dict(numerator=str(n), denominator=str(d), percent=str(n/d*100) if d > 0 else None,
        scope=scope, unit='count or homogeneous quantity; never monetary confidence')


def readiness(checks, has_demand):
    required=[c for c in checks if c['required']]
    counts=dict(Counter(c['status'] for c in checks))
    if any(c['status']=='fail' and c['severity']=='critical' for c in required):
        state, ready='blocked','blocked'
    elif any(c['status']=='stale' for c in required): state,ready='stale','not_ready'
    elif not has_demand: state,ready='no_eligible_demand','not_ready'
    elif not required or any(c['status'] not in ('pass','not_applicable') for c in required):
        state='partially_reconciled' if any(c['status']=='pass' for c in required) else 'incomplete'
        ready='not_ready'
    else: state,ready='fully_reconciled','ready_for_financial_review'
    return dict(state=state,readiness=ready,check_counts=counts)


class Controls:
    def __init__(self): self.checks=[]

    def record(self,code,category,source,status,expected=None,observed=None,tolerance='0',
               severity='critical',message='',unit='identity',required=True):
        numeric=unit in ('quantity','currency','percentage_points','percent','count')
        known=numeric and expected is not None and observed is not None
        difference=str(number(observed)-number(expected)) if known else None
        key=code+'|'+source
        self.checks.append(dict(check_key=key,code=code,category=category,source_key=source,
            status=status,required=required,severity=severity,unit=unit,numeric_known=known,
            expected_numeric=float(expected) if known else 0,observed_numeric=float(observed) if known else 0,
            difference=float(difference) if known else 0,tolerance=float(tolerance),
            values=dict(expected=expected,observed=observed,difference=difference,tolerance=str(tolerance)),
            message=message or code.replace('_',' ').capitalize()))

    def equation(self,code,category,source,expected,observed,tolerance,unit='currency',severity='critical'):
        if expected is None or observed is None: status='blocked'
        else: status='pass' if abs(number(observed)-number(expected))<=number(tolerance) else 'fail'
        self.record(code,category,source,status,expected,observed,tolerance,severity,unit=unit)

    def truth(self,code,category,source,condition,expected=True,observed=None,**kw):
        self.record(code,category,source,'pass' if condition else 'fail',expected,condition if observed is None else observed,**kw)

    def unique(self,code,category,source,values):
        self.equation(code,category,source,len(set(values)),len(values),'0',unit='count')


def independent_profit(n,b,r,baseline_revenue=None):
    n=number(n) if n is not None else None
    before=number(baseline_revenue) if baseline_revenue is not None else n
    b=number(b) if b is not None else None
    r=number(r) if r is not None else None
    bp=before-b if before is not None and b is not None else None
    rp=n-r if n is not None and r is not None else None
    bm=bp/before*100 if bp is not None and before>0 else None
    rm=rp/n*100 if rp is not None and n>0 else None
    change=rp-bp if bp is not None and rp is not None else None
    erosion=bm-rm if bm is not None and rm is not None else None
    return {k:str(v) if v is not None else None for k,v in dict(net_revenue=n,baseline_cost=b,revised_cost=r,
        baseline_gross_profit=bp,revised_gross_profit=rp,baseline_margin_percent=bm,revised_margin_percent=rm,
        gross_profit_change=change,gross_profit_reduction=-change if change is not None else None,
        margin_erosion_points=erosion,profit_reduction_percent=-change/bp*100 if change is not None and bp>0 else None,
        relative_margin_decline_percent=erosion/bm*100 if erosion is not None and bm>0 else None).items()}


def independent_risk(v,policy,bands,complete,protections):
    """Independent thresholds/precedence, compared to stored PR15 risk outcomes."""
    rank={'normal':0,'warning':1,'high':2,'critical':3}
    stages={};codes=[];extra=[]
    for stage in ('baseline','revised'):
        margin=v[stage+'_margin_percent'];profit=v[stage+'_gross_profit']
        if not policy or margin is None: stages[stage]='review_required';continue
        level='normal'
        if profit is not None and number(profit)<0 and policy['negative_profit_critical']:
            codes.append(('NEGATIVE_GROSS_PROFIT',stage));level='critical'
        if number(margin)<=number(policy['minimum']):
            codes.append(('CRITICAL_'+stage.upper()+'_MARGIN',stage));level='critical'
        elif number(margin)<=number(policy['target']):
            codes.append(('LOW_'+stage.upper()+'_MARGIN',stage));level=max((level,'warning'),key=rank.get)
        stages[stage]=level
    if policy and policy['erosion_enabled'] and v['margin_erosion_points'] is not None and number(v['margin_erosion_points'])>0 and number(v['margin_erosion_points'])>=number(policy['erosion_points']):
        codes.append(('MATERIAL_MARGIN_EROSION','revised'));extra.append('warning')
    reduction=v['gross_profit_reduction']
    if reduction is not None and number(reduction)>0:
        for band in bands:
            if number(reduction)>=number(band['minimum']) and (band['maximum'] is None or number(reduction)<number(band['maximum'])):
                level={'low':'normal','medium':'warning','high':'high','critical':'critical'}[band['level']]
                if level!='normal':
                    extra.append(level);codes.extend([('LARGE_INCREMENTAL_COST','revised'),('MATERIAL_PROFIT_REDUCTION','revised')])
    if 'fixed_price_verified' in protections and reduction is not None and number(reduction)>0:
        codes.append(('FIXED_CUSTOMER_PRICE','revised'));extra.append('warning')
    if not complete:codes.append(('FINANCIAL_BASIS_INCOMPLETE','revised'))
    if not policy:codes.append(('RISK_POLICY_MISSING','revised'))
    if any(p not in ('fixed_price_verified','price_adjustment_allowed_verified','not_applicable') for p in protections):
        codes.append(('CUSTOMER_PRICE_PROTECTION_UNKNOWN','revised'))
    primary='review_required' if not complete or not policy or v['revised_margin_percent'] is None or not bands else max([stages['revised']]+extra,key=rank.get)
    b,r=stages['baseline'],stages['revised'];erosion=v['margin_erosion_points']
    if primary=='review_required': transition='undetermined'
    elif number(erosion)<0:transition='risk_improved'
    elif b==r=='critical' and number(erosion)>0:transition='existing_critical_worsened'
    elif b=='warning' and r=='critical':transition='warning_to_critical'
    elif b=='normal' and r=='critical':transition='new_critical'
    elif b=='normal' and r=='warning':transition='new_warning'
    elif b!='normal':transition='existing_risk_unchanged'
    else:transition='no_new_margin_risk'
    return dict(baseline_risk=b,revised_risk=r,risk_status=primary,revision_effect=transition),sorted(set(codes))
