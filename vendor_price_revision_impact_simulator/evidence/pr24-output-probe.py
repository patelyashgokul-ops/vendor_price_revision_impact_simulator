"""Real read-only outputs from genuine retained PR23 synthetic workflow facts."""
import csv
import hashlib
import io
import json
from pathlib import Path
from odoo import api, Command
from odoo.exceptions import AccessError
from pypdf import PdfReader
import openpyxl
from odoo.addons.vendor_price_revision_impact_simulator.models.reporting import CATALOG, WIZARD, MODULE
from odoo.addons.vendor_price_revision_impact_simulator.models import reporting_data as formats
from odoo.addons.vendor_price_revision_impact_simulator.tests.test_reporting import native_pdf_assets

assert env.cr.dbname == 'codex_vpr_pr24_upgrade_1_20261103'
ROOT = Path(r'C:\PycharmProjects\odoo20\custom_addons\vendor_price_revision_impact_simulator')
sample = json.loads(env['ir.config_parameter'].get_str('app06.pr23.sample'))
company = sample['company_id']
execution = env['vendor.price.revision.application.execution'].browse(sample['execution_id'])
margin = execution.request_id.baseline_id.margin_id
commercial = execution.batch_id.row_ids.commercial_result_id[:1]
incident = env['vendor.price.revision.application.monitor.incident'].search([('execution_id', '=', execution.id)], limit=1)
assert commercial and incident and execution.state == 'VERIFIED'
source_sets = dict(VENDOR_REVISION_SUMMARY=commercial.ids, FINANCIAL_IMPACT=margin.financial_id.ids,
    GROSS_PROFIT_MARGIN=margin.ids, APPROVAL_COMPLIANCE=execution.request_id.ids,
    APPLIED_PRICE_AUDIT=execution.ids, INCIDENT_ANALYTICS=incident.ids)
scenario_result = execution.request_id.scenario_id.result_ids[:1]
assert scenario_result and scenario_result.cost_known
source_sets['SCENARIO_COMPARISON'] = scenario_result.ids
users = env['res.users'].search([('active', '=', True), ('share', '=', False), ('company_ids', 'in', [company])], order='id')
outputs = []
for kind, ids in source_sets.items():
    chosen = None
    for user in users:
        actor = api.Environment(env.cr, user.id, {'allowed_company_ids': [company]})
        try:
            wizard = actor[WIZARD].create(dict(report_type=kind, company_ids=[Command.set([company])], source_ids_text=','.join(map(str, ids))))
            dataset = wizard._dataset()
        except AccessError:
            continue
        chosen = actor
        break
    assert chosen is not None and dataset['rows'], kind+' requires a genuinely source-authorized reader'
    original_fp = dataset['metadata']['dataset_fingerprint']
    if kind == 'SCENARIO_COMPARISON':
        assert dataset['rows'][0]['projected_cost'] == scenario_result.profit['revised_cost']
    engine = chosen['ir.actions.report'].with_context(force_report_rendering=True)
    with native_pdf_assets(env, engine, wizard):
        pdf, extension = engine._render_qweb_pdf(MODULE+'.financial_audit_pdf', wizard.ids)
    assert extension == 'pdf' and pdf.startswith(b'%PDF-')
    reader = PdfReader(io.BytesIO(pdf))
    assert reader.pages and any(page.extract_text() for page in reader.pages)
    workbook = formats.xlsx_bytes(dataset)
    parsed = openpyxl.load_workbook(io.BytesIO(workbook), read_only=True)
    assert parsed['Details'].max_row == len(dataset['rows'])+1
    csv_data = formats.csv_bytes(dataset)
    assert len(list(csv.DictReader(io.StringIO(csv_data.decode('utf-8-sig'))))) == len(dataset['rows'])
    assert wizard._dataset()['metadata']['dataset_fingerprint'] == original_fp
    artifacts = []
    for extension, content in (('pdf', pdf), ('xlsx', workbook), ('csv', csv_data)):
        path = ROOT/'evidence'/('pr24-'+kind.lower()+'.'+extension)
        path.write_bytes(content)
        artifacts.append(dict(file=path.name, bytes=len(content), sha256=hashlib.sha256(content).hexdigest()))
    outputs.append(dict(report_type=kind, source_ids=ids, reader_id=chosen.uid, row_count=len(dataset['rows']),
        pages=len(reader.pages), fingerprint=original_fp, artifacts=artifacts))
    print('PR24_CASE '+kind+'_THREE_FORMATS=PASS', flush=True)
(ROOT/'evidence/pr24-output-results.json').write_text(json.dumps(outputs, indent=2)+'\n', encoding='utf-8')
print('PR24_OUTPUTS='+json.dumps(outputs), flush=True)
print('PR24_PROBE=PASS', flush=True)
