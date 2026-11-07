"""Gross-margin inversion, explicit commercial eligibility and directional rounding."""
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, localcontext
from .commercial_math import number

def upward(value,increment):
    with localcontext() as ctx:
        ctx.prec=38
        q=number(increment,True)
        if q<=0:raise ValueError('Positive pricing increment required')
        return (number(value)/q).to_integral_value(rounding=ROUND_CEILING)*q

def downward(value,increment):
    q=number(increment,True)
    if q<=0:raise ValueError('Positive pricing increment required')
    return (number(value)/q).to_integral_value(rounding=ROUND_FLOOR)*q

def target(cost,revenue,margin,increment):
    with localcontext() as ctx:
        ctx.prec=38
        m=number(margin)
        if m<0 or m>=100:raise ValueError('Conventional target must satisfy0 <= margin <100')
        if cost is None or revenue is None:
            return dict(required_raw=None,required_rounded=None,signed_gap=None,additional_required=None,max_cost=None,cost_reduction=None)
        c=number(cost,True);n=number(revenue);required=c/(1-m/100);ceiling=n*(1-m/100)
        rounded=upward(required,increment)
        return {k:str(v) for k,v in dict(required_raw=required,required_rounded=rounded,signed_gap=required-n,
            additional_required=max(rounded-n,Decimal(0)),max_cost=ceiling,cost_reduction=max(c-ceiling,Decimal(0))).items()}

def supplier_ceiling(max_cost,unchanged,quantity):
    if any(v is None for v in (max_cost,unchanged,quantity)):return None
    q=number(quantity,True)
    if not q:return None
    result=(number(max_cost)-number(unchanged,True))/q
    return str(result) if result>=0 else None

def eligibility(state,protection,validity,today,draft_policy,conditions=False):
    """Eligibility for analytical review, never authority to execute a price change."""
    if state=='cancel':return 'cancelled_not_eligible'
    if protection=='fixed_price_verified':return 'protected_not_eligible'
    if state in ('draft','sent') and validity and validity<today:return 'expired_offer_review'
    if state=='draft':return 'eligible_unsent_quote_review' if draft_policy=='review' else 'draft_policy_review'
    if state=='sent':return 'eligible_offer_amendment_review' if protection=='price_adjustment_allowed_verified' and conditions else 'offer_validity_review'
    if state=='sale':return 'eligible_contract_amendment_review' if protection=='price_adjustment_allowed_verified' and conditions else 'customer_contract_review'
    return 'unsupported_state_review'
