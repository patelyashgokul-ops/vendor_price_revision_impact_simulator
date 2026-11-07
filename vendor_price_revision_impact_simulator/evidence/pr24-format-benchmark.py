"""Measured formatter-only capacity; not ORM/source or production qualification."""
import csv
import hashlib
import importlib
import io
import json
from pathlib import Path
import sys
import time
import tracemalloc
import types
import zipfile
from datetime import datetime, timezone
import openpyxl

ROOT = Path(__file__).resolve().parents[1]
package = types.ModuleType('_pr24_formatter')
package.__path__ = [str(ROOT/'models')]
sys.modules[package.__name__] = package
formats = importlib.import_module(package.__name__+'.reporting_data')
prototype = dict(source_model='synthetic.format.line', source_id=1, company_id=1, currency_id=1,
    snapshot_id=1, scenario='confirmed', demand_type='confirmed', quantity='200', comparison_uom_id=1,
    net_revenue='28000', baseline_cost='20000', revised_cost='21500', supplier_text=' \t=HYPERLINK("invalid")', external_reference='000123')
columns = [dict(key=key, label=key, numeric=key in ('quantity', 'net_revenue', 'baseline_cost', 'revised_cost')) for key in prototype]
names = ['__init__.py', '__manifest__.py'] + [str(p.relative_to(ROOT)).replace('\\', '/') for folder in ('models', 'security', 'views', 'data', 'tests') for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in ('.py', '.xml', '.csv')]
ledger = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sorted(names)}
source_hash = hashlib.sha256(json.dumps(ledger, sort_keys=True).encode()).hexdigest()
started = datetime.now(timezone.utc).isoformat()
results = []
failure = None
try:
    for count in (100, 500, 2000, 10000, 50000):
        rows = [dict(prototype, source_id=index+1) for index in range(count)]
        dataset = dict(metadata=dict(scope='FORMAT_ONLY', source_rows=count, source_hash=source_hash),
            rows=rows, columns=columns, totals=[], issues=['Synthetic formatter benchmark; not native source throughput.'])
        tracemalloc.start()
        start = time.perf_counter()
        csv_data = formats.csv_bytes(dataset)
        csv_seconds = time.perf_counter()-start
        start = time.perf_counter()
        xlsx = formats.xlsx_bytes(dataset)
        xlsx_seconds = time.perf_counter()-start
        start = time.perf_counter()
        parsed = csv.DictReader(io.StringIO(csv_data.decode('utf-8-sig')))
        actual = 0
        for row in parsed:
            actual += 1
            assert row['supplier_text'].startswith("'") and row['external_reference'] == '000123'
        assert actual == count
        with zipfile.ZipFile(io.BytesIO(xlsx)) as archive:
            assert archive.testzip() is None
        workbook = openpyxl.load_workbook(io.BytesIO(xlsx), read_only=True, data_only=False)
        sheet = workbook['Details']
        actual = 0
        for row in sheet.iter_rows(min_row=2):
            actual += 1
            assert all(cell.data_type != 'f' for cell in row)
            assert row[-1].value == '000123'
        assert actual == count
        validation_seconds = time.perf_counter()-start
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        workbook.close()
        result = dict(rows=count, actual_csv_rows=count, actual_xlsx_rows=count, csv_seconds=csv_seconds,
            xlsx_seconds=xlsx_seconds, validation_seconds=validation_seconds, python_traced_peak_bytes=peak,
            csv_bytes=len(csv_data), xlsx_bytes=len(xlsx), status='PASS', scope='FORMAT_ONLY', database_queries=None)
        results.append(result)
        print(json.dumps(result), flush=True)
except Exception as exc:
    failure = type(exc).__name__+': '+str(exc)
    raise
finally:
    payload = dict(source_hash=source_hash, started_at=started, completed_at=datetime.now(timezone.utc).isoformat(),
        results=results, failure=failure, source_build_excluded=True, tracemalloc_overhead_included=True,
        limitation='No ORM/source selection, current-state validation, database query, concurrent export or production capacity qualification.')
    path = ROOT/'evidence/pr24-format-benchmark.json'
    path.write_text(json.dumps(payload, indent=2)+'\n', encoding='utf-8')
    path = ROOT/'TEST_REPORT.json'
    report = json.loads(path.read_text(encoding='utf-8-sig'))
    record = dict(prompt_id='PR-24', phase='DEV-12', module=ROOT.name, odoo_version='20.0',
        test_level='TARGETED', verification_scope='PR24_FORMAT_ONLY_PERFORMANCE',
        invocation='python evidence/pr24-format-benchmark.py', started_at=started, completed_at=payload['completed_at'],
        result_status='PASS' if len(results)==5 and not failure else 'FAIL', passed=len(results), failed=1 if failure else 0,
        skipped=None, exit_status=1 if failure else 0, test_unit='formatter_scale_cases',
        test_names=['FORMAT_ROWS_'+str(row['rows']) for row in results], source_hash=source_hash,
        evidence_reference='evidence/pr24-format-benchmark.json', blocking_reason=failure)
    report['history'].append(record)
    # Do not replace a concurrently running Odoo gate's latest-run evidence.
    path.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
