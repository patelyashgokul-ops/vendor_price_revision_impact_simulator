"""PR24 format-independent, bounded reporting over retained source facts.

Decimal values remain strings in the canonical contract. Exporters explicitly
choose numeric cells; untrusted text never becomes a spreadsheet formula.
"""
import csv
import hashlib
import io
import json
import unicodedata
from datetime import date, datetime
from collections import Counter, defaultdict
from decimal import Decimal, localcontext

from .profitability_math import profitability

VERSION = 'pr24_retained_facts_v1'
MAX_ROWS = 50000
PDF_ROWS = 500
AMOUNTS = ('net_revenue', 'baseline_cost', 'revised_cost')


def canonical(value):
    def encode(item):
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        raise TypeError('Unsupported canonical report value: '+type(item).__name__)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False, default=encode)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def audit_summary(context):
    """Readable PDF appendix; full structured evidence remains in the dataset.

    Passing controls are counted, not reproduced as pages of JSON. Exceptions
    retain their full fields. Large provenance is explicitly referenced by its
    digest and size, never presented as a complete printed forensic record.
    """
    rows = []

    def walk(value, path):
        label = ' / '.join(str(part).replace('_', ' ').title() for part in path)
        if path and path[-1] == 'controls' and isinstance(value, list):
            counts = Counter(str(control.get('status', 'unknown')) for control in value)
            rows.append((label+' (recorded checks)', ', '.join('%s: %s' % pair for pair in sorted(counts.items())) or 'No recorded controls'))
            for index, control in enumerate(value, 1):
                if control.get('status') not in ('pass', 'not_applicable'):
                    walk(control, path+['Exception '+str(index)])
            rows.append((label+' evidence', 'Full control details are retained in the canonical dataset and XLSX metadata. SHA256 '+fingerprint(value)))
        elif path and path[-1] == 'provenance':
            rows.append((label+' evidence', 'Full provenance is retained in the canonical dataset and XLSX metadata. SHA256 '+fingerprint(value)))
        elif isinstance(value, dict):
            for key, item in value.items():
                walk(item, path+[key])
        elif isinstance(value, list) and any(isinstance(item, dict) for item in value):
            for index, item in enumerate(value, 1):
                walk(item, path+[str(index)])
        else:
            text = 'Unavailable' if value is None or value is False else value.isoformat() if isinstance(value, (date, datetime)) else canonical(value) if isinstance(value, list) else str(value)
            rows.append((label, text))

    walk(context, [])
    return rows


def safe_text(value):
    text = '' if value is None else str(value)
    # Ignore every leading control/space character when detecting formulas.
    index = 0
    while index < len(text) and (text[index].isspace() or unicodedata.category(text[index]) in ('Cc', 'Cf')):
        index += 1
    leading = text[index:]
    return "'" + text if leading.startswith(('=', '+', '-', '@')) else text


def totals(rows, dimensions=()):
    """Only exact disjoint lines of ONE snapshot contribute to a total.

    Versions, alternative scenarios, currencies, companies and conditional
    demand never share a bucket. Missing constituent amounts null the total;
    verified subsets are disclosed separately. Quantities are not aggregated.
    """
    if set(dimensions) - {'product_id', 'customer_id', 'sale_order_id', 'vendor_id', 'warehouse_id'}:
        raise ValueError('Unsupported grouping dimension.')
    partition = ('company_id', 'currency_id', 'snapshot_id', 'scenario', 'demand_type') + tuple(dimensions)
    groups = defaultdict(list)
    seen = set()
    for row in rows:
        identity = (row['source_model'], row['source_id'])
        if identity in seen:
            raise ValueError('Duplicate source line; report would double-count.')
        seen.add(identity)
        key = tuple(row.get(k) for k in partition)
        groups[key].append(row)
    result = []
    with localcontext() as ctx:
        ctx.prec = 38
        for key, lines in sorted(groups.items(), key=lambda item: canonical(item[0])):
            complete = [r for r in lines if r.get('complete', True) and all(r.get(a) is not None for a in AMOUNTS)]
            partial = {a: str(sum((Decimal(r[a]) for r in complete), Decimal(0))) if complete else None for a in AMOUNTS}
            values = partial if len(complete) == len(lines) else dict.fromkeys(AMOUNTS)
            result.append(dict(zip(partition, key),
                line_count=len(lines), excluded_count=len(lines)-len(complete),
                complete=len(complete)==len(lines), verified_subset=partial,
                **profitability(values['net_revenue'], values['baseline_cost'], values['revised_cost'])))
    return result


def cost_totals(rows, dimensions=()):
    partition = ('company_id', 'currency_id', 'snapshot_id', 'scenario', 'demand_type') + tuple(dimensions)
    groups = defaultdict(list)
    seen = set()
    for row in rows:
        identity = (row['source_model'], row['source_id'])
        if identity in seen:
            raise ValueError('Duplicate financial source line.')
        seen.add(identity)
        groups[tuple(row.get(k) for k in partition)].append(row)
    result = []
    with localcontext() as ctx:
        ctx.prec = 38
        for key, lines in sorted(groups.items(), key=lambda item: canonical(item[0])):
            total = dict(zip(partition, key), line_count=len(lines))
            for amount in ('baseline_extended_cost', 'revised_extended_cost', 'incremental_extended_cost'):
                known = [r[amount] for r in lines if r.get(amount) is not None]
                subtotal = str(sum((Decimal(v) for v in known), Decimal(0))) if known else None
                total[amount] = subtotal if len(known) == len(lines) else None
                total[amount+'_verified_subset'] = subtotal
                total[amount+'_excluded_count'] = len(lines)-len(known)
            result.append(total)
    return result


def csv_bytes(dataset):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\r\n')
    columns = dataset['columns']
    metadata_columns = ('source_mode', 'freshness', 'date_basis', 'timezone', 'dataset_fingerprint')
    writer.writerow([c['label'] for c in columns] + list(metadata_columns) + ['limitations'])
    for row in dataset['rows']:
        writer.writerow([row.get(c['key']) if c['numeric'] else safe_text(row.get(c['key'])) for c in columns]
            + [safe_text(dataset['metadata'].get(key)) for key in metadata_columns]
            + [safe_text(' | '.join(dataset['issues']))])
    return stream.getvalue().encode('utf-8-sig')


def xlsx_bytes(dataset):
    import xlsxwriter
    stream = io.BytesIO()
    book = xlsxwriter.Workbook(stream, {'in_memory': True, 'strings_to_formulas': False, 'strings_to_urls': False})
    header = book.add_format({'bold': True, 'bg_color': '#17324D', 'font_color': '#FFFFFF'})
    numeric = book.add_format({'num_format': '#,##0.00########;[Red]-#,##0.00########'})
    def write_text(sheet, row, column, value, style=None):
        if len(value) > 32767:
            raise ValueError('Cell exceeds Excel limit; narrow the report.')
        sheet.write_string(row, column, value, style)
    metadata_rows = []
    for key, value in dataset['metadata'].items():
        text = canonical(value)
        chunks = [text[index:index+30000] for index in range(0, len(text), 30000)] or ['']
        metadata_rows.extend({'key': key+(' [part %s/%s]' % (index+1, len(chunks)) if len(chunks)>1 else ''), 'value': chunk} for index, chunk in enumerate(chunks))
    total_numeric = set(AMOUNTS) | {'baseline_gross_profit', 'revised_gross_profit', 'baseline_margin_percent', 'revised_margin_percent',
        'gross_profit_change', 'gross_profit_reduction', 'margin_erosion_points', 'profit_reduction_percent', 'relative_margin_decline_percent',
        'baseline_extended_cost', 'revised_extended_cost', 'incremental_extended_cost', 'line_count', 'excluded_count'}
    for name, columns, rows in (
        ('Details', dataset['columns'], dataset['rows']),
        ('Totals', [{'key': k, 'label': k, 'numeric': k in total_numeric} for k in (list(dataset['totals'][0]) if dataset['totals'] else ['status'])], dataset['totals']),
        ('Metadata', [{'key': 'key', 'label': 'Property', 'numeric': False}, {'key': 'value', 'label': 'Value', 'numeric': False}],
            metadata_rows),
        ('Issues', [{'key': 'message', 'label': 'Limitation', 'numeric': False}], [{'message': v} for v in dataset['issues']]),
    ):
        sheet = book.add_worksheet(name)
        sheet.freeze_panes(1, 0)
        for col, spec in enumerate(columns):
            write_text(sheet, 0, col, spec['label'], header)
            sheet.set_column(col, col, 24)
        for index, row in enumerate(rows, 1):
            for col, spec in enumerate(columns):
                value = row.get(spec['key'])
                if value is None:
                    sheet.write_blank(index, col, None)
                elif spec['numeric']:
                    number = Decimal(str(value))
                    if not number.is_finite():
                        raise ValueError('Non-finite financial amount.')
                    # Excel uses IEEE doubles; exact values are also retained as text.
                    sheet.write_number(index, col, float(number), numeric)
                else:
                    write_text(sheet, index, col, canonical(value) if isinstance(value, (dict, list)) else str(value))
        if columns:
            sheet.autofilter(0, 0, len(rows), len(columns)-1)
    exact = book.add_worksheet('Exact values')
    write_text(exact, 0, 0, 'Canonical decimal strings; authoritative precision', header)
    for index, row in enumerate(dataset['rows'], 1):
        # Individual cells avoid Excel's 32,767 character truncation limit.
        for col, spec in enumerate(dataset['columns']):
            value = row.get(spec['key'])
            text = '' if value is None else str(value)
            if len(text) > 32767:
                raise ValueError('Cell exceeds Excel limit; narrow the report.')
            write_text(exact, index, col, text)
    book.close()
    return stream.getvalue()
