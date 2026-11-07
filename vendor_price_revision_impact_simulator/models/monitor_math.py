"""PR23 exact operational comparisons; no currency conversion or invented exposure."""
from decimal import Decimal
from .application_math import MATERIAL, NUMERIC, IDENTITY

VERSION = 'pr23_exact_committed_observation_v1'
CATEGORIES = {
    'price': 'PRICE_DRIFT', 'discount': 'DISCOUNT_DRIFT',
    'currency_id': 'CURRENCY_DRIFT', 'uom_id': 'UOM_DRIFT', 'min_qty': 'MOQ_DRIFT',
    'date_start': 'EFFECTIVE_DATE_DRIFT', 'date_end': 'EFFECTIVE_DATE_DRIFT',
    'partner_id': 'VENDOR_IDENTITY_DRIFT', 'product_id': 'PRODUCT_SCOPE_DRIFT',
    'product_tmpl_id': 'PRODUCT_SCOPE_DRIFT', 'company_id': 'COMPANY_SCOPE_DRIFT',
    'delay': 'COMMERCIAL_METADATA_DRIFT', 'sequence': 'COMMERCIAL_METADATA_DRIFT',
    'product_code': 'COMMERCIAL_METADATA_DRIFT', 'product_name': 'COMMERCIAL_METADATA_DRIFT',
}


def differences(expected, observed):
    # Price has min_display_digits, not storage rounding, in Odoo20. Compare the
    # actual persisted numeric representation, never currency display rounding.
    return {key: {'expected': expected.get(key), 'observed': observed.get(key)}
            for key in MATERIAL if (Decimal(str(expected[key])) != Decimal(str(observed[key]))
            if key in NUMERIC else (expected.get(key) or False) != (observed.get(key) or False))}


def compatible(a, b):
    return not differences(a, b).keys() & set(IDENTITY)


def severity(code):
    if code in ('COMPANY_SCOPE_DRIFT', 'VENDOR_IDENTITY_DRIFT', 'PRODUCT_SCOPE_DRIFT',
                'HISTORICAL_EVIDENCE_INTEGRITY'):
        return 'CRITICAL'
    if code in ('COMMERCIAL_METADATA_DRIFT', 'SELECTION_CHECK_UNAVAILABLE'):
        return 'WARNING'
    return 'HIGH'
