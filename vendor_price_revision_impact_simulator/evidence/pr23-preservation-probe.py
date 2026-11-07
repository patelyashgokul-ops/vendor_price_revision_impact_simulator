"""Exact original source and native data after the actual PR22 -> PR23 update."""
import hashlib
import json
from odoo import api
from odoo.addons.vendor_price_revision_impact_simulator.models.execution import EXEC
assert env.cr.dbname.startswith('codex_vpr_pr23_')
sample=json.loads(env['ir.config_parameter'].get_str('app06.pr23.sample'))
for name,old in sample['preservation'].items():
 model=env[name];values=json.loads(json.dumps(model.with_context(active_test=False).search([],order='id').read(old['fields'],load=None),default=str))
 for row in values:
  for k in old['fields']:
   if model._fields[k].type in ('many2many','one2many'):row[k]=sorted(row[k])
 actual=hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()
 assert actual==old['sha256'],name+' changed during PR23 update'
actor=api.Environment(env.cr,sample['operator_id'],{'allowed_company_ids':[sample['company_id']]})
e=actor[EXEC].browse(sample['execution_id'])
assert e.state=='VERIFIED' and e.evidence==sample['original_evidence'] and e.fingerprint==sample['original_fingerprint']
assert e.plan_id.fingerprint==sample['original_plan_fingerprint']
raw=e.batch_id.attachment_id.raw.content
assert raw and len(raw)==e.batch_id.evidence_id.file_size
assert hashlib.sha256(raw).hexdigest()==sample['source_attachment_sha256']==e.batch_id.evidence_id.sha256_digest
print('PR23_CASE UPGRADE_ALL_ORIGINAL_MODELS=PASS',flush=True)
print('PR23_CASE ORIGINAL_RECEIPT_AND_SOURCE_BYTES=PASS',flush=True)
print('PR23_PRESERVED_MODELS='+str(len(sample['preservation'])),flush=True)
print('PR23_PROBE=PASS',flush=True)
