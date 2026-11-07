"""Decimal price/quantity mathematics using Odoo20 factor and rate dimensions."""
from decimal import Decimal, InvalidOperation, localcontext, ROUND_HALF_UP


def number(value, nonnegative=False):
    text = str(value)
    if len(text) > 128:
        raise ValueError('Numeric input exceeds supported length')
    try:
        result = Decimal(text)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Invalid decimal') from None
    if (not result.is_finite() or (nonnegative and result < 0)
            or len(result.as_tuple().digits) > 38 or abs(result.adjusted()) > 1000):
        raise ValueError('Invalid finite nonnegative decimal')
    return result


def quantity(value, source_factor, target_factor):
    with localcontext() as ctx:
        ctx.prec = 38
        source, target = number(source_factor), number(target_factor)
        if min(source, target) <= 0:
            raise ValueError('Missing positive UoM factor')
        return number(value, True) * source / target


def price(value, source_factor, target_factor):
    # Odoo20 _compute_price: price * to_unit.factor / self.factor.
    return quantity(value, target_factor, source_factor)


def converted(value, rate):
    with localcontext() as ctx:
        ctx.prec = 38
        rate = number(rate)
        if rate <= 0:
            raise ValueError('Missing positive FX rate')
        return number(value, True) * rate


def net_price(value, source_factor, target_factor, discount):
    with localcontext() as ctx:
        ctx.prec = 38
        discount = number(discount, True)
        if discount > 100:
            raise ValueError('Invalid percentage discount')
        return price(value, source_factor, target_factor) * (1 - discount / 100)


def comparison(old, proposed, tolerance='0'):
    with localcontext() as ctx:
        ctx.prec = 38
        old, proposed, tolerance = number(old, True), number(proposed, True), number(tolerance, True)
        delta = proposed - old
        classification = 'increase' if delta > tolerance else 'decrease' if delta < -tolerance else 'unchanged'
        if old == 0:
            classification = 'new_from_zero' if proposed else 'zero_to_zero'
        return {'old': str(old), 'proposed': str(proposed), 'delta': str(delta),
                'percent': str(delta / old * 100) if old else None, 'classification': classification,
                'tolerance': str(tolerance)}


def decomposition(old, proposed, old_rate, new_rate):
    with localcontext() as ctx:
        ctx.prec = 38
        old, proposed, old_rate, new_rate = map(number, (old, proposed, old_rate, new_rate))
        supplier = (proposed - old) * old_rate
        fx = proposed * (new_rate - old_rate)
        return {'method': 'supplier_at_old_rate_then_fx_on_proposed_price',
                'supplier_component': str(supplier), 'fx_component': str(fx),
                'total': str(supplier + fx), 'accounting_outcome': False}


def rounded(value, increment):
    value, increment = number(value), number(increment)
    with localcontext() as ctx:
        # Reporting can need extra trailing zeros beyond arithmetic's 38
        # significant digits. Quantizing must not raise or truncate the integer.
        ctx.prec = max(38, len(value.as_tuple().digits) + max(0, value.adjusted())
                       + max(0, -increment.adjusted()) + 4)
        if increment <= 0:
            raise ValueError('Invalid currency rounding')
        return str((value / increment).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * increment)
