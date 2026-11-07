"""Cold original PR22 committed fixtures, before PR23 schema migration."""
import hashlib
import json
from odoo import api
from odoo.addons.vendor_price_revision_impact_simulator.models.execution import EXEC
assert env.cr.dbname.startswith('codex_vpr_pr23_')
assert 'vendor.price.revision.application.monitor.run' not in env
param=env['ir.config_parameter'].get_str('vendor_price_revision_impact_simulator.pr22_commit_probe')
sample=json.loads(param) if param else json.loads(env['ir.config_parameter'].get_str('app06.pr23.sample'))
updates=env[EXEC].search([('update_count','=',1)],order='id',limit=100)
actual109=updates.filtered(lambda e:len(e.line_ids)==1 and float(e.line_ids.observed_after_values['price'])==109 and e.state=='VERIFIED')
if actual109:
 selected=actual109[0]
 sample=dict(execution_id=selected.id,company_id=selected.company_id.id,operator_id=selected.operator_id.id)
company=sample['company_id'];uid=sample['operator_id'];eid=sample['execution_id']
actor=api.Environment(env.cr,uid,{'allowed_company_ids':[company]})
receipt=actor[EXEC].browse(eid);assert receipt.state=='VERIFIED'
assert receipt.line_ids and receipt.evidence
models={name for name in env.registry.models if name.startswith('vendor.price.revision.')}
models.update(['product.supplierinfo','purchase.order','purchase.order.line','sale.order','sale.order.line',
 'product.pricelist','product.pricelist.item','product.product','product.template','stock.quant','stock.move',
 'stock.move.line','stock.picking','stock.valuation.layer','stock.landed.cost','account.move','account.move.line','res.currency.rate'])
result={}
for name in sorted(models):
 if name not in env:continue
 model=env[name]
 if model._abstract or model._transient or not model._auto:continue
 keys=sorted(k for k,f in model._fields.items() if f.store and f.type!='binary' and not f.company_dependent)
 records=model.with_context(active_test=False).search([],order='id')
 values=json.loads(json.dumps(records.read(keys,load=None),default=str))
 for row in values:
  for k in keys:
   if model._fields[k].type in ('many2many','one2many'):row[k]=sorted(row[k])
 result[name]=dict(fields=keys,count=len(values),sha256=hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest())
sample.update(original_evidence=receipt.evidence,original_fingerprint=receipt.fingerprint,
 target_id=receipt.line_ids.target_id,original_plan_fingerprint=receipt.plan_id.fingerprint,preservation=result)
raw=receipt.batch_id.attachment_id.raw.content
assert raw and len(raw)==receipt.batch_id.evidence_id.file_size,'Original source filestore must be present before cold capture'
sample['source_attachment_sha256']=hashlib.sha256(raw).hexdigest()
assert sample['source_attachment_sha256']==receipt.batch_id.evidence_id.sha256_digest
env['ir.config_parameter'].set_str('app06.pr23.sample',json.dumps(sample,sort_keys=True,default=str))
env.cr.commit()
print('PR23_CASE COLD_PR22_SOURCE_CAPTURE=PASS',flush=True)
print('PR23_CAPTURE_COUNTS='+json.dumps({k:v['count'] for k,v in result.items()},sort_keys=True),flush=True)
print('PR23_PROBE=PASS',flush=True)
