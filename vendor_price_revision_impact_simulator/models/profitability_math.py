"""Decimal projected profitability; percentages and percentage points are distinct."""
from decimal import Decimal, localcontext
from .commercial_math import number, rounded

AMOUNTS = ('net_revenue', 'baseline_cost', 'revised_cost', 'baseline_gross_profit',
    'revised_gross_profit', 'baseline_margin_percent', 'revised_margin_percent',
    'gross_profit_change', 'gross_profit_reduction', 'margin_erosion_points',
    'profit_reduction_percent', 'relative_margin_decline_percent')
RANK = {'normal': 0, 'warning': 1, 'high': 2, 'critical': 3}


def profitability(revenue, baseline, revised, baseline_revenue=None):
    with localcontext() as ctx:
        ctx.prec = 38
        n = number(revenue) if revenue is not None else None
        before = number(baseline_revenue) if baseline_revenue is not None else n
        b = number(baseline, True) if baseline is not None else None
        r = number(revised, True) if revised is not None else None
        bp = before-b if before is not None and b is not None else None
        rp = n-r if n is not None and r is not None else None
        bm = bp/before*100 if bp is not None and before > 0 else None
        rm = rp/n*100 if rp is not None and n > 0 else None
        change = rp-bp if bp is not None and rp is not None else None
        erosion = bm-rm if bm is not None and rm is not None else None
        vals = dict(net_revenue=n, baseline_cost=b, revised_cost=r, baseline_gross_profit=bp,
            revised_gross_profit=rp, baseline_margin_percent=bm, revised_margin_percent=rm,
            gross_profit_change=change, gross_profit_reduction=-change if change is not None else None,
            margin_erosion_points=erosion, profit_reduction_percent=-change/bp*100 if change is not None and bp > 0 else None,
            relative_margin_decline_percent=erosion/bm*100 if erosion is not None and bm > 0 else None)
        return {k: str(v) if v is not None else None for k, v in vals.items()}


def assess(values, policy, exposure_rules, confidence, complete, protection=()):
    """Inclusive minimum/target boundaries; preserve all reasons independently."""
    reasons = []
    def flag(code, severity, actual=None, threshold=None, stage='revised'):
        reasons.append(dict(code=code, severity=severity, actual=actual, threshold=threshold,
            stage=stage, basis=confidence, policy_id=policy.get('id') if policy else None))
    if not complete:
        flag('FINANCIAL_BASIS_INCOMPLETE', 'review_required')
    if not policy:
        flag('RISK_POLICY_MISSING', 'review_required')
    levels = {}
    for stage in ('baseline', 'revised'):
        margin = values[stage+'_margin_percent']
        profit = values[stage+'_gross_profit']
        level = 'normal'
        if policy and margin is not None and profit is not None:
            if number(profit) < 0 and policy['negative_profit_critical']:
                level = 'critical'; flag('NEGATIVE_GROSS_PROFIT', 'critical', profit, '0', stage)
            if number(margin) <= number(policy['minimum']):
                level = 'critical'; flag('CRITICAL_'+stage.upper()+'_MARGIN', 'critical', margin, policy['minimum'], stage)
            elif number(margin) <= number(policy['target']):
                level = max((level, 'warning'), key=RANK.get)
                flag('LOW_'+stage.upper()+'_MARGIN', 'warning', margin, policy['target'], stage)
        else:
            level = 'review_required'
        levels[stage] = level
    erosion = values['margin_erosion_points']
    if policy and policy['erosion_enabled'] and erosion is not None and number(erosion) > 0 and number(erosion) >= number(policy['erosion_points']):
        flag('MATERIAL_MARGIN_EROSION', 'warning', erosion, policy['erosion_points'])
    reduction = values['gross_profit_reduction']
    if reduction is not None and number(reduction) > 0:
        for band in exposure_rules:
            amount = number(reduction)
            if amount >= number(band['minimum']) and (band['maximum'] is None or amount < number(band['maximum'])):
                severity = {'low':'normal', 'medium':'warning', 'high':'high', 'critical':'critical'}[band['level']]
                if severity != 'normal':
                    flag('LARGE_INCREMENTAL_COST', severity, reduction, band['minimum'])
                    flag('MATERIAL_PROFIT_REDUCTION', severity, reduction, band['minimum'])
    for p in sorted(set(protection)):
        if p == 'fixed_price_verified' and reduction is not None and number(reduction) > 0:
            flag('FIXED_CUSTOMER_PRICE', 'warning')
        elif p not in ('fixed_price_verified', 'price_adjustment_allowed_verified', 'not_applicable'):
            flag('CUSTOMER_PRICE_PROTECTION_UNKNOWN', 'review_required')
    if not complete or not policy or values['revised_margin_percent'] is None or not exposure_rules:
        severity = 'review_required'
        transition = 'undetermined'
    else:
        severity = max([levels['revised']]+[v['severity'] for v in reasons if v['stage']=='revised' and v['severity'] in RANK], key=RANK.get)
        b, r = levels['baseline'], levels['revised']
        e = number(erosion)
        if e < 0: transition = 'risk_improved'
        elif b == 'critical' and r == 'critical' and e > 0: transition = 'existing_critical_worsened'
        elif b == 'warning' and r == 'critical': transition = 'warning_to_critical'
        elif b == 'normal' and r == 'critical': transition = 'new_critical'
        elif b == 'normal' and r == 'warning': transition = 'new_warning'
        elif b != 'normal': transition = 'existing_risk_unchanged'
        else: transition = 'no_new_margin_risk'
    return dict(baseline_risk=levels['baseline'], revised_risk=levels['revised'], risk_status=severity,
        revision_effect=transition, risk_reasons=reasons)


def reported(values, currency_rounding):
    return {k: rounded(v, '0.01' if 'percent' in k or 'points' in k else currency_rounding) if v is not None else None for k, v in values.items()}
