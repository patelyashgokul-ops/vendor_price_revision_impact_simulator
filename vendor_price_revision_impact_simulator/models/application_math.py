"""Pure deterministic PR21 matching. No operational ORM mutations."""
from .commercial_math import number, price, quantity

OPERATIONS = ('UPDATE_CANDIDATE', 'CREATE_CANDIDATE', 'NO_CHANGE', 'BLOCKED', 'MANUAL_REVIEW', 'UNSUPPORTED')
MATERIAL = ('partner_id', 'product_tmpl_id', 'product_id', 'company_id', 'min_qty', 'price',
            'currency_id', 'uom_id', 'date_start', 'date_end', 'discount', 'delay',
            'sequence', 'product_code', 'product_name')
NUMERIC = ('min_qty', 'price', 'discount')
IDENTITY = ('partner_id', 'product_tmpl_id', 'product_id', 'company_id', 'min_qty',
            'currency_id', 'uom_id', 'date_start', 'date_end')


def overlap(a, b):
    return (not a.get('date_end') or not b.get('date_start') or a['date_end'] >= b['date_start']) and (
        not b.get('date_end') or not a.get('date_start') or b['date_end'] >= a['date_start'])


def identity(values):
    return tuple(number(values[k]) if k == 'min_qty' else values.get(k) or False for k in IDENTITY)


def same(a, b, keys=MATERIAL):
    return all(number(a[k]) == number(b[k]) if k in NUMERIC else (a.get(k) or False) == (b.get(k) or False) for k in keys)


def converted_terms(amount, moq, source_factor, target_factor):
    return str(price(amount, source_factor, target_factor)), str(quantity(moq, source_factor, target_factor))


def classify(desired, candidates, intent, today):
    """Rows already scoped by caller; return classification, target and codes."""
    relevant = [v for v in candidates if v['partner_id'] == desired['partner_id'] and
                v['product_tmpl_id'] == desired['product_tmpl_id'] and
                (not v['product_id'] or v['product_id'] == desired['product_id']) and
                overlap(v, desired)]
    exact = [v for v in relevant if identity(v) == identity(desired)]
    if len(exact) > 1:
        return 'MANUAL_REVIEW', None, ['AMBIGUOUS_TARGET']
    if any(not v['company_id'] for v in relevant):
        return 'BLOCKED', None, ['SHARED_RECORD_SCOPE_CONFLICT']
    if any(not v['product_id'] for v in relevant):
        return 'BLOCKED', None, ['TEMPLATE_VARIANT_SCOPE_CONFLICT']
    if intent.get('operation') == 'update':
        observed = next((v for v in candidates if v['id'] == intent.get('target_id')), None)
        if not observed:
            return 'BLOCKED', None, ['TARGET_DELETED_OR_INACCESSIBLE']
        if not exact or exact[0]['id'] != observed['id']:
            return 'BLOCKED', observed, ['TARGET_IDENTITY_CHANGED']
        if not same(observed, intent['before']):
            return 'BLOCKED', observed, ['TARGET_CHANGED_SINCE_APPROVAL']
        if same(observed, desired):
            return 'NO_CHANGE', observed, []
        if observed.get('date_start') and observed['date_start'] < today:
            return 'MANUAL_REVIEW', observed, ['HISTORICAL_PERIOD_REWRITE']
        if not observed.get('date_start'):
            return 'MANUAL_REVIEW', observed, ['OPEN_ENDED_HISTORICAL_SCOPE']
        return 'UPDATE_CANDIDATE', observed, []
    if intent.get('operation') != 'create':
        return 'MANUAL_REVIEW', exact[0] if exact else None, ['EXPLICIT_APPLICATION_INTENT_REQUIRED']
    if exact:
        return ('NO_CHANGE', exact[0], []) if same(exact[0], desired) else ('BLOCKED', exact[0], ['CREATE_TARGET_ALREADY_EXISTS'])
    return 'CREATE_CANDIDATE', None, []


def effective_conflicts(lines, targets):
    """Compare the complete analytical after-state, without virtual ORM records.

    Replace approved updates together before evaluating tiers. A blocked change
    never hides an existing rule. Equal prices at different tiers are harmless;
    exact duplicate identities are handled separately by the planner.
    """
    from collections import defaultdict
    eligible = [v for v in lines if v['operation'] in ('UPDATE_CANDIDATE', 'CREATE_CANDIDATE', 'NO_CHANGE')]
    replaced = {v['target_id'] for v in eligible if v['operation'] == 'UPDATE_CANDIDATE'}
    groups = defaultdict(list)
    def key(v):
        return tuple(v.get(k) for k in ('partner_id', 'product_tmpl_id', 'product_id', 'company_id'))
    for target in targets:
        if target['id'] not in replaced:
            groups[key(target)].append((None, target))
    for line in eligible:
        if line['operation'] != 'NO_CHANGE':
            groups[key(line['after'])].append((line['row_id'], line['after']))
    conflicts = {}
    for line in eligible:
        desired = line['after']; codes = set()
        for reference, other in groups[key(desired)]:
            if reference == line['row_id'] or (reference is None and other.get('id') == line.get('target_id')):
                continue
            if not overlap(other, desired):
                continue
            if other['currency_id'] != desired['currency_id'] or other['uom_id'] != desired['uom_id']:
                codes.add('CURRENCY_OR_UOM_RULE_CONFLICT'); continue
            if number(other['min_qty']) <= number(desired['min_qty']):
                other_net = number(other['price']) * (1 - number(other['discount']) / 100)
                desired_net = number(desired['price']) * (1 - number(desired['discount']) / 100)
                if other_net < desired_net:
                    codes.add('OVERLAPPING_EFFECTIVE_RULE')
        if codes:
            conflicts[line['row_id']] = sorted(codes)
    return conflicts
