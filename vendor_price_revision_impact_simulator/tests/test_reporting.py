"""PR24 genuine format parsing, retained-source integration and access gates."""
import csv
import io
from pathlib import Path
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import unquote, urlsplit
import mimetypes
from datetime import date
from decimal import Decimal as D

import openpyxl
from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import file_path

from ..models import reporting_data as data
from ..models.reporting import CATALOG, MODULE, WIZARD, utc_window
from .test_profitability import MarginFixtures


@contextmanager
def native_pdf_assets(env, engine, wizard):
    """Serve genuine native CSS/fonts on an isolated ephemeral loopback port.

    The test runner disables Odoo HTTP. Public assets are materialized under
    the test cursor before serving immutable bytes; the server never uses an
    ORM cursor or serves business records. PDF generation remains native.
    """
    html, _ = engine._render_qweb_html(MODULE+'.financial_audit_pdf', wizard.ids)
    report = engine._get_report(MODULE+'.action_financial_audit_pdf')
    report._prepare_html(html, report_model=WIZARD)
    for bundle in ('web.report_assets_common', 'web.report_assets_pdf'):
        env['ir.qweb']._get_asset_bundle(bundle, css=True, js=False, autoprefix=True).css()
    assets = {record.url: (record.raw.content, record.mimetype) for record in env['ir.attachment'].search([
        ('url', '=like', '/web/assets/%'), ('public', '=', True)])}
    assert assets, 'Real native report assets must exist'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            path = unquote(urlsplit(self.path).path)
            item = assets.get(path)
            parts = path.strip('/').split('/')
            if not item and len(parts) > 2 and parts[0] in ('web', 'base') and parts[1] == 'static' and '..' not in parts:
                try:
                    resource = Path(file_path('/'.join(parts)))
                    item = (resource.read_bytes(), mimetypes.guess_type(str(resource))[0] or 'application/octet-stream')
                except (FileNotFoundError, ValueError):
                    pass
            if not item:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', item[1])
            self.send_header('Content-Length', str(len(item[0])))
            self.end_headers()
            self.wfile.write(item[0])

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env['ir.config_parameter'].set_str('report.url', 'http://127.0.0.1:'+str(server.server_port))
    try:
        yield
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def sample():
    row = dict(source_model='fixture.line', source_id=1, snapshot_id=1,
        company_id=1, currency_id=1, scenario='confirmed', demand_type='confirmed',
        net_revenue='28000', baseline_cost='20000', revised_cost='21500', text='00123')
    return dict(metadata={'basis': 'retained'},
        columns=[{'key': k, 'label': k, 'numeric': k in ('net_revenue', 'baseline_cost', 'revised_cost')} for k in row],
        rows=[row], totals=data.totals([row]), issues=['Projected; not realized'])


@tagged('post_install', '-at_install')
class TestReportingQuick(TransactionCase):
    def test_catalog_matches_real_schema(self):
        self.assertEqual(len(CATALOG), 17)
        for key, spec in CATALOG.items():
            source = self.env[spec[1]]
            self.assertIn(spec[4], source._fields, key)
            detail = self.env[source._fields[spec[2]].comodel_name] if spec[2] else source
            for name in spec[3].split():
                self.assertIn(name, detail._fields, (key, name))

    def test_reference_and_negotiated_profit(self):
        dataset = sample()
        total = dataset['totals'][0]
        self.assertEqual((D(total['baseline_gross_profit']), D(total['revised_gross_profit'])), (8000, 6500))
        self.assertAlmostEqual(float(total['margin_erosion_points']), 5.3571428571, places=8)
        dataset['rows'][0]['revised_cost'] = '20900'
        negotiated = data.totals(dataset['rows'])[0]
        self.assertEqual(D(negotiated['revised_gross_profit']), 7100)
        self.assertEqual(D(negotiated['revised_gross_profit'])-D(total['revised_gross_profit']), 600)

    def test_missing_not_zero_and_duplicates_fail(self):
        rows = sample()['rows']
        rows[0]['revised_cost'] = None
        total = data.totals(rows)[0]
        self.assertIsNone(total['revised_gross_profit'])
        self.assertEqual(total['excluded_count'], 1)
        with self.assertRaises(ValueError):
            data.totals(rows+rows)

    def test_company_currency_snapshot_scenario_demand_partition(self):
        original = sample()['rows'][0]
        rows = [original]
        for index, key in enumerate(('company_id', 'currency_id', 'snapshot_id', 'scenario', 'demand_type'), 2):
            row = dict(original, source_id=index)
            row[key] = 'different' if key in ('scenario', 'demand_type') else 2
            rows.append(row)
        self.assertEqual(len(data.totals(rows)), 6)

    def test_aggregate_uses_ratio_of_sums(self):
        first = dict(sample()['rows'][0], net_revenue='10000', baseline_cost='7000', revised_cost='7000')
        second = dict(first, source_id=2, net_revenue='90000', baseline_cost='81000', revised_cost='81000')
        self.assertEqual(D(data.totals([first, second])[0]['revised_margin_percent']), 12)

    def test_csv_formula_controls_quoting_and_negative_numeric(self):
        dataset = sample()
        dataset['rows'][0]['text'] = ' \t\r=HYPERLINK("bad")\n,quoted'
        dataset['rows'][0]['revised_cost'] = '-12'
        parsed = list(csv.DictReader(io.StringIO(data.csv_bytes(dataset).decode('utf-8-sig'))))
        self.assertTrue(parsed[0]['text'].startswith("'"))
        self.assertEqual(parsed[0]['revised_cost'], '-12')
        for prefix in ('=', '+', '-', '@', '\t=', '\x00@', '\ufeff=', '\u00a0=', '\u200b@', '\u2028+'):
            self.assertTrue(data.safe_text(prefix+'payload').startswith("'"))

    def test_xlsx_numbers_text_and_no_external_links(self):
        dataset = sample()
        dataset['rows'][0]['text'] = '=1+1'
        workbook = openpyxl.load_workbook(io.BytesIO(data.xlsx_bytes(dataset)), data_only=False)
        self.assertEqual(workbook.sheetnames, ['Details', 'Totals', 'Metadata', 'Issues', 'Exact values'])
        sheet = workbook['Details']
        columns = {cell.value: cell.column for cell in sheet[1]}
        self.assertEqual(sheet.cell(2, columns['revised_cost']).value, 21500)
        self.assertEqual(sheet.cell(2, columns['text']).data_type, 's')
        self.assertFalse(workbook._external_links)
        self.assertFalse(any(cell.data_type == 'f' or cell.hyperlink for row in sheet for cell in row))

    def test_dst_window_is_local_calendar_days(self):
        start, end = utc_window(date(2026, 3, 8), date(2026, 3, 8), 'America/New_York')
        self.assertEqual((end-start).total_seconds(), 23*3600)
        start, end = utc_window(date(2026, 11, 1), date(2026, 11, 1), 'America/New_York')
        self.assertEqual((end-start).total_seconds(), 25*3600)

    def test_cost_grouping_and_missing_incremental_is_not_zero(self):
        row = dict(sample()['rows'][0], product_id=1, baseline_extended_cost='20000',
            revised_extended_cost='21500', incremental_extended_cost='1500')
        total = data.cost_totals([row], ('product_id',))[0]
        self.assertEqual(total['incremental_extended_cost'], '1500')
        row['incremental_extended_cost'] = None
        total = data.cost_totals([row])[0]
        self.assertIsNone(total['incremental_extended_cost'])
        self.assertEqual(total['incremental_extended_cost_excluded_count'], 1)

    def test_incomplete_source_cannot_become_complete_total(self):
        row = dict(sample()['rows'][0], complete=False)
        self.assertFalse(data.totals([row])[0]['complete'])
        self.assertIsNone(data.totals([row])[0]['revised_gross_profit'])

    def test_excel_oversized_text_rejected(self):
        dataset = sample()
        dataset['rows'][0]['text'] = 'x'*32768
        with self.assertRaisesRegex(ValueError, 'Excel limit'):
            data.xlsx_bytes(dataset)


@tagged('post_install', '-at_install')
class TestReportingSources(MarginFixtures, TransactionCase):
    def _wizard24(self, source, role='finance', **values):
        settings = dict(
            report_type='GROSS_PROFIT_MARGIN', company_ids=[Command.set(self.a.ids)],
            source_ids_text=str(source.id))
        settings.update(values)
        return self.env[WIZARD].with_user(self.users[role]).with_context(allowed_company_ids=self.a.ids).create(settings)

    def test_real_reference_formats_html_and_no_native_changes(self):
        source = self._reference15()
        native = self.env['product.supplierinfo'].search([])
        before = native.read(['price', 'min_qty', 'currency_id', 'uom_id', 'date_start', 'date_end', 'write_date'])
        wizard = self._wizard24(source)
        dataset = wizard._dataset()
        total = dataset['totals'][0]
        self.assertEqual((D(total['net_revenue']), D(total['baseline_cost']), D(total['revised_cost'])), (28000, 20000, 21500))
        self.assertEqual(dataset['metadata']['freshness'], 'NOT_CHECKED')
        self.assertEqual(dataset['metadata']['dataset_fingerprint'], wizard._dataset()['metadata']['dataset_fingerprint'])
        workbook = openpyxl.load_workbook(io.BytesIO(wizard.download.content))
        self.assertEqual(workbook['Details'].max_row, 2)
        html, kind = self.env['ir.actions.report'].with_user(self.users['finance']).with_context(allowed_company_ids=self.a.ids)._render_qweb_html(
            MODULE+'.financial_audit_pdf', wizard.ids)
        self.assertIn(b'28,000.00', html)
        self.assertIn(b'21,500.00', html)
        self.assertEqual(native.read(['price', 'min_qty', 'currency_id', 'uom_id', 'date_start', 'date_end', 'write_date']), before)

    def test_owner_role_and_company_revocation(self):
        source = self._reference15()
        wizard = self._wizard24(source)
        with self.assertRaises(AccessError):
            wizard.with_user(self.users['auditor'])._dataset()
        manager = self._wizard24(source, role='manager')
        with self.assertRaises(AccessError):
            manager._dataset()
        with self.assertRaises(AccessError):
            wizard.with_context(allowed_company_ids=self.b.ids)._dataset()

    def test_actual_native_pdf_bytes_and_pages(self):
        from pypdf import PdfReader
        source = self._reference15()
        wizard = self._wizard24(source)
        engine = self.env['ir.actions.report'].with_user(self.users['finance']).with_context(
            allowed_company_ids=self.a.ids, force_report_rendering=True)
        with native_pdf_assets(self.env, engine, wizard):
            content, kind = engine._render_qweb_pdf(MODULE+'.financial_audit_pdf', wizard.ids)
        self.assertEqual(kind, 'pdf')
        self.assertTrue(content.startswith(b'%PDF-'))
        reader = PdfReader(io.BytesIO(content))
        self.assertGreaterEqual(len(reader.pages), 1)
        text = '\n'.join(page.extract_text() for page in reader.pages)
        self.assertIn('28,000.00', text)
        self.assertIn('21,500.00', text)
        path = Path(__file__).resolve().parents[1]/'evidence/pr24-reference.pdf'
        path.write_bytes(content)

    def test_source_selection_validation_and_explicit_empty_date_filter(self):
        source = self._reference15()
        wizard = self._wizard24(source)
        for invalid in ('1); DROP TABLE x', '1,1', '0', '-1'):
            wizard.source_ids_text = invalid
            with self.assertRaises(ValidationError):
                wizard._dataset()
        wizard.write(dict(source_ids_text=str(source.id), date_from='1900-01-01', date_to='1900-01-02'))
        dataset = wizard._dataset()
        self.assertEqual(dataset['rows'], [])
        self.assertEqual(dataset['totals'], [])

    def test_restricted_sales_profile_and_source_revocation(self):
        source = self._reference15()
        user = self.users['sales']
        user.write({'group_ids': [Command.link(self.env.ref(MODULE+'.group_vpr_sales_manager').id)]})
        wizard = self._wizard24(source.sales_id, role='sales', report_type='SALES_ORDER_EXPOSURE')
        dataset = wizard._dataset()
        self.assertEqual(dataset['metadata']['role_contract'], 'RESTRICTED_COMMERCIAL')
        self.assertEqual(dataset['metadata']['source_model'], 'vendor.price.revision.sales.snapshot')
        keys = {column['key'] for column in dataset['columns']}
        self.assertFalse(keys & set(('baseline_cost', 'revised_cost', 'baseline_gross_profit', 'revised_margin_percent', 'incremental_cost')))
        self.assertEqual(dataset['totals'], [])
        self.assertEqual(D(dataset['rows'][0]['company_sales_value']), 28000)
        from ..models.sales_exposure import GRANT
        grants = self.env[GRANT].search([('user_id', '=', user.id)])
        grants.write({'active': False, 'reason': 'PR24 source revocation test'})
        self.env['ir.access']._clear_caches()
        with self.assertRaises(AccessError):
            wizard._dataset()
        with self.assertRaises(AccessError):
            wizard.with_env(wizard.env(su=True))._dataset()

    def test_filters_grouped_totals_and_download_reauthorization(self):
        source = self._reference15()
        wizard = self._wizard24(source, group_by='product_id', product_ids=[Command.set(self.red.ids)])
        dataset = wizard._dataset()
        self.assertEqual(dataset['totals'][0]['product_id'], self.red.id)
        self.assertEqual(D(dataset['totals'][0]['revised_gross_profit']), 6500)
        self.assertTrue(wizard.download.content.startswith(b'PK'))
        wizard.output_format = 'csv'
        self.assertTrue(wizard.filename.endswith('.csv'))
        self.assertTrue(wizard.download.content.startswith(b'\xef\xbb\xbf'))
        from odoo.tools.misc import limited_field_access_token
        token = limited_field_access_token(wizard, 'download', scope='binary')
        user = self.users['finance']
        user.write({'group_ids': [Command.unlink(self.env.ref(MODULE+'.group_vpr_finance_manager').id)]})
        self.env['ir.access']._clear_caches()
        with self.assertRaises(AccessError):
            wizard.read(['download'])
        binary = wizard.env['ir.binary']
        transport_record = binary._find_record(res_model=WIZARD, res_id=wizard.id, field='download', access_token=token)
        self.assertTrue(transport_record.env.su)
        transport_record.invalidate_recordset(['download'])
        with self.assertRaises(AccessError):
            binary._get_stream_from(transport_record, 'download', filename='report.csv', filename_field=None)
