"""Pure lexical validation. No Odoo products, rates, UoMs or prices are resolved."""
import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

TARGETS = ('vendor_product_code', 'vendor_product_name', 'product_identifier_raw',
    'proposed_price_raw', 'currency_raw', 'purchase_uom_raw', 'min_qty_raw',
    'effective_date_raw', 'supplier_reference_raw', 'notes_raw')
IDENTIFIERS = TARGETS[:3]
REQUIRED = ('proposed_price_raw', 'currency_raw', 'purchase_uom_raw', 'min_qty_raw', 'effective_date_raw')
DATE_FORMATS = {'iso': '%Y-%m-%d', 'dmy': '%d/%m/%Y', 'mdy': '%m/%d/%Y'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def decimal_text(value, style='plain'):
    """Return an exact decimal string, with no financial rounding or conversion."""
    text = str(value).strip()
    patterns = {
        'plain': r'-?\d+(?:\.\d+)?',
        'comma_group': r'-?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?',
        'dot_group': r'-?(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d+)?',
        'space_group': r'-?(?:\d+|\d{1,3}(?: \d{3})+)(?:,\d+)?',
    }
    if style not in patterns or not re.fullmatch(patterns[style], text) or len(text) > 64:
        raise ValueError('numeric syntax')
    if style == 'comma_group':
        text = text.replace(',', '')
    elif style == 'dot_group':
        text = text.replace('.', '').replace(',', '.')
    elif style == 'space_group':
        text = text.replace(' ', '').replace(',', '.')
    try:
        number = Decimal(text)
    except InvalidOperation:
        raise ValueError('numeric syntax') from None
    if not number.is_finite():
        raise ValueError('nonfinite')
    return format(number, 'f')


def validate_values(values, metadata, number_style='plain', date_style='iso'):
    """Return status, normalized lexical candidates and structured issues."""
    issues, parsed = [], {}
    def issue(field, code, message, severity='error'):
        issues.append(dict(field_name=field, code=code, message=message, severity=severity))
    for field, value in values.items():
        if value is None:
            continue
        if not isinstance(value, str) or len(value) > (4000 if field in ('notes_raw', 'vendor_product_name') else 256):
            issue(field, 'EXCESSIVE_FIELD_LENGTH', 'Value exceeds the supported field length or text representation.')
        if any(ord(c) < 32 and c not in '\t\n\r' for c in str(value)):
            issue(field, 'UNSUPPORTED_CELL_VALUE', 'Control characters are not supported in mapped values.')
        kind = metadata.get(field, {}).get('type')
        if kind in ('formula', 'boolean') or (str(value).startswith(('=', '@', '+'))):
            issue(field, 'MANUAL_REVIEW_REQUIRED', 'Untrusted formula-like or boolean source value requires a correction.', 'review_required')
    if not any(values.get(field, '').strip() for field in IDENTIFIERS):
        issue('vendor_product_code', 'MISSING_REQUIRED_VALUE', 'Supply at least one supplier code, description or product identifier.')
    for field in REQUIRED:
        if not values.get(field, '').strip():
            issue(field, 'MISSING_UOM_TEXT' if field == 'purchase_uom_raw' else 'MISSING_REQUIRED_VALUE',
                'A nonblank mapped value or supported explicit inherited context is required.')
    for field, code in [('proposed_price_raw', 'INVALID_PRICE_FORMAT'), ('min_qty_raw', 'INVALID_QUANTITY_FORMAT')]:
        value = values.get(field, '')
        if not value.strip():
            continue
        try:
            number = decimal_text(value, number_style)
            parsed[field] = number
            if Decimal(number) < 0:
                issue(field, 'NEGATIVE_PRICE' if field == 'proposed_price_raw' else code, 'Negative price or quantity candidates are not supported.')
            elif field == 'proposed_price_raw' and Decimal(number) == 0:
                issue(field, 'ZERO_PRICE_REVIEW', 'Explicit zero price requires commercial review; blank is never zero.', 'review_required')
        except ValueError:
            if number_style == 'plain' and re.fullmatch(r'\d[\d., ]*', value.strip()) and any(c in value for c in ', '):
                issue(field, code, 'Select an explicit source numeric separator convention; separators are not guessed.', 'review_required')
            else:
                issue(field, code, 'Supply a finite decimal candidate using the selected numeric convention.')
    currency = values.get('currency_raw', '')
    if currency.strip() and not re.fullmatch(r'[A-Z]{3}', currency):
        issue('currency_raw', 'INVALID_CURRENCY_TEXT', 'Supply exactly three uppercase currency-code letters; availability and FX remain unverified.')
    value = values.get('effective_date_raw', '')
    if value.strip():
        # ISO source typed dates remain unambiguous, irrespective of file text format.
        try:
            fmt = '%Y-%m-%d' if metadata.get('effective_date_raw', {}).get('type') == 'date' else DATE_FORMATS[date_style]
            candidate = value[:10] if metadata.get('effective_date_raw', {}).get('type') == 'date' else value
            parsed['effective_date_raw'] = datetime.strptime(candidate, fmt).date().isoformat()
        except (ValueError, KeyError):
            ambiguous = date_style == 'iso' and re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}', value)
            issue('effective_date_raw', 'AMBIGUOUS_DATE_FORMAT' if ambiguous else 'INVALID_DATE_FORMAT',
                'Select the source date convention and supply a real calendar date.', 'review_required' if ambiguous else 'error')
    status = 'blocked' if any(i['severity'] == 'error' for i in issues) else 'needs_review' if any(i['severity'] == 'review_required' for i in issues) else 'structurally_ready'
    return status, parsed, issues


def duplicate_key(values, parsed):
    # Include every mapped canonical value, including references/terms/notes.
    # Only surrounding whitespace and exact lexical number/date equivalence
    # are ignored; case, punctuation and internal whitespace remain significant.
    normalized = dict(parsed)
    for key in ('proposed_price_raw', 'min_qty_raw'):
        if key in normalized:
            text = format(Decimal(normalized[key]), 'f')
            normalized[key] = text.rstrip('0').rstrip('.') if '.' in text else text
            if Decimal(normalized[key]) == 0:
                normalized[key] = '0'
    return digest({field: normalized.get(field, str(values.get(field, '')).strip()) for field in TARGETS})
