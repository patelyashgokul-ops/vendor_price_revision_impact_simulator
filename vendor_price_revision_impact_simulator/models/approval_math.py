"""Deterministic review routing; no decision, currency fallback or price action."""
from decimal import Decimal,localcontext
from .commercial_math import number,rounded

TYPES=('vendor_revision','supplier_scenario','customer_repricing','commercial_package')
METRICS=('cost_increase','cost_reduction','absolute_cost_change','profit_reduction','revenue_increase','margin_erosion')
ROLES=('group_vpr_purchase_manager','group_vpr_sales_manager','group_vpr_finance_manager','group_vpr_director')

def metrics(old_cost,cost,old_revenue,revenue,quantum):
    with localcontext() as ctx:
        ctx.prec=38
        if any(v is None for v in (old_cost,cost,old_revenue,revenue)):raise ValueError('FINANCIAL_READINESS_MISSING: missing money is not zero')
        b,c,n,r=[number(v) for v in (old_cost,cost,old_revenue,revenue)]
        if b<0 or c<0 or n<=0 or r<=0:raise ValueError('FINANCIAL_READINESS_MISSING: positive comparable revenue and nonnegative costs required')
        delta=c-b;loss=(n-b)-(r-c);erosion=((n-b)/n-(r-c)/r)*100
        values=dict(signed_cost_change=str(delta),signed_profit_reduction=str(loss),signed_revenue_change=str(r-n),signed_margin_erosion=str(erosion),
            cost_increase=str(max(delta,0)),cost_reduction=str(max(-delta,0)),absolute_cost_change=str(abs(delta)),
            profit_reduction=str(max(loss,0)),revenue_increase=str(max(r-n,0)),margin_erosion=str(max(erosion,0)),
            original_revenue=str(n),projected_revenue=str(r),baseline_cost=str(b),projected_cost=str(c),projected_profit=str(r-c),projected_margin=str((r-c)/r*100))
        return values

def select_rules(rules,request_type,amounts,flags,quantum):
    primary={'finance_exposure'} if request_type in TYPES[:2] else {'customer_repricing'}
    if request_type=='commercial_package':primary.add('finance_exposure')
    by={}
    for rule in rules:
        if request_type in rule['types']:by.setdefault(rule['category'],[]).append(rule)
    if primary-set(by):raise ValueError('APPROVAL_MATRIX_GAP: missing primary request category')
    selected=[]
    for category,rows in sorted(by.items()):
        definitions={(r['metric'],r['trigger']) for r in rows}
        if len(definitions)!=1:raise ValueError('APPROVAL_MATRIX_OVERLAP: incoherent category metric/trigger')
        metric,trigger=next(iter(definitions))
        if category in primary and trigger!='always':raise ValueError('APPROVAL_MATRIX_GAP: primary authority cannot be conditional')
        if trigger!='always' and not flags.get(trigger):continue
        value=number(amounts[metric]);value=number(rounded(value,quantum)) if metric!='margin_erosion' else value
        matches=[r for r in rows if value>=number(r['minimum']) and (r['maximum'] is None or value<number(r['maximum']))]
        if len(matches)!=1:raise ValueError('APPROVAL_MATRIX_GAP_OR_OVERLAP: no unique comparable interval')
        selected.append(dict(matches[0],observed=str(value)))
    return selected

def plan(selected,escalations,order,minimum):
    stages={};extra=[]
    for rule in selected:
        for role in rule['roles']:
            if role not in stages:stages[role]=dict(code=role,roles=[role],quorum=1,reasons=[],named_sets=[])
            stages[role]['reasons'].append(dict(rule_id=rule['id'],category=rule['category'],metric=rule['metric'],observed=rule['observed'],minimum=rule['minimum'],maximum=rule['maximum']))
            if rule.get('named'):stages[role]['named_sets'].append(rule['named'])
        extra.append(rule)
    for reason,roles in escalations:
        if not roles:raise ValueError('APPROVAL_POLICY_MISSING: required risk/contract authority is undefined')
        for role in roles:
            if role not in stages:stages[role]=dict(code=role,roles=[role],quorum=1,reasons=[],named_sets=[])
            stages[role]['reasons'].append(dict(policy_condition=reason))
    result=sorted(stages.values(),key=lambda s:order.index(s['roles'][0]))
    for rule in extra:
        covered=sum(s['quorum'] for s in result if set(s['roles'])<=set(rule['roles']))
        missing=rule['quorum']-covered
        if missing>0:
            if len(rule['roles'])==1:
                stage=stages[rule['roles'][0]];stage['quorum']+=missing
                stage['reasons'].append(dict(rule_id=rule['id'],distinct_quorum=rule['quorum']))
            else:result.append(dict(code='quorum_rule_'+str(rule['id']),roles=rule['roles'],quorum=missing,reasons=[dict(rule_id=rule['id'],distinct_quorum=rule['quorum'])],named_sets=[rule['named']] if rule.get('named') else []))
    if sum(s['quorum'] for s in result)<minimum:raise ValueError('QUORUM_NOT_SATISFIABLE: route below company distinct minimum')
    if not result or sum(s['quorum'] for s in result)>32:raise ValueError('QUORUM_NOT_SATISFIABLE: bound route to1..32 distinct identities')
    result.sort(key=lambda s:(max(order.index(r) for r in s['roles']),len(s['roles'])>1,s['code']))
    return result

def assign(stages,manual=None):
    """Augmenting-path matching avoids greedy multi-role allocation failures."""
    slots=[(s['code'],i,list(s['candidates'])) for s in stages for i in range(s['quorum'])]
    if manual is not None:
        if set(manual)!={s['code'] for s in stages}:raise ValueError('NO_ELIGIBLE_APPROVER: manual assignment required for every exact stage')
        used=set();result={}
        for s in stages:
            ids=manual[s['code']]
            if not isinstance(ids,list) or len(ids)!=s['quorum'] or len(set(ids))!=len(ids) or any(type(v) is not int or v not in s['candidates'] or v in used for v in ids):raise ValueError('MAKER_CHECKER_CONFLICT: invalid, repeated or ineligible manual reviewer')
            used.update(ids);result[s['code']]=ids
        return result
    occupied={};matched={}
    def visit(slot,seen):
        for uid in sorted(slots[slot][2]):
            if uid in seen:continue
            seen.add(uid)
            if uid not in occupied or visit(occupied[uid],seen):occupied[uid]=slot;matched[slot]=uid;return True
        return False
    for i in sorted(range(len(slots)),key=lambda i:(len(slots[i][2]),i)):
        if not visit(i,set()):raise ValueError('DISTINCT_REVIEWER_UNAVAILABLE: no complete independent matching/quorum')
    return {s['code']:[matched[i] for i,v in enumerate(slots) if v[0]==s['code']] for s in stages}
