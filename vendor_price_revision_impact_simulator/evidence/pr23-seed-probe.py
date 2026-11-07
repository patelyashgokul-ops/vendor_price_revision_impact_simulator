"""Synthetic fixture setup only: genuine original approval and actual PR22 commit."""
from pathlib import Path
import json
import hashlib
from odoo import api
from odoo.addons.vendor_price_revision_impact_simulator.models.execution import EXEC
assert env.cr.dbname.startswith('codex_vpr_pr23_')
root=Path.cwd()
source=(root/'evidence/pr22-operational-safety-probe.py').read_text(encoding='utf-8')
setup_source=source.split('# Prove UPDATE does not reprice')[0].replace('codex_vpr_pr22_','codex_vpr_pr23_')
scope={'env':env};exec(setup_source,scope)
s=scope['setup'](1,update=True)
cr=env.registry.cursor()
try:
 actor=api.Environment(cr,s['mid'],s['ctx']);p=actor[s['plan']._name].browse(s['plan'].id)
 receipt=p.action_apply_approved_vendor_prices(True,p.fingerprint)
 assert receipt.state=='PENDING_COMMIT'
 eid=receipt.id
 cr.commit()
finally:cr.close()
s['clock_patch'].stop()
with env.registry.cursor() as cr:
 actor=api.Environment(cr,s['mid'],s['ctx']); receipt=actor[EXEC].browse(eid)
 assert receipt.state=='VERIFIED' and receipt.line_ids.observed_after_values['price']=='109.0'
 sample=dict(execution_id=eid,company_id=s['company_id'],operator_id=s['mid'],target_id=receipt.line_ids.target_id,
  source_operator_id=s['uid'],original_evidence=receipt.evidence,original_fingerprint=receipt.fingerprint,
  original_plan_fingerprint=receipt.plan_id.fingerprint)
 # Capture exact scalar stored fields for every original durable APP06 model,
 # together with positively populated commercial/stock/accounting masters.
 observer=api.Environment(cr,env.uid,s['ctx']);snap={}
 names=[name for name in observer.registry.models if name.startswith('vendor.price.revision.')]
 names+=list(s['models'])
 for name in sorted(set(names)):
  model=observer[name]
  if model._abstract or model._transient or not model._auto:continue
  keys=sorted(k for k,f in model._fields.items() if f.store and f.type not in ('one2many','many2many','binary') and not f.company_dependent)
  rows=model.with_context(active_test=False).search([],order='id').read(keys,load=None)
  snap[name]=dict(fields=keys,rows=rows)
 sample['preservation']=snap
 sample['source_attachment_sha256']=hashlib.sha256(observer['vendor.price.revision.import.batch'].browse(receipt.batch_id.id).attachment_id.raw.content).hexdigest()
 observer['ir.config_parameter'].set_str('app06.pr23.sample',json.dumps(sample,default=str,sort_keys=True))
 cr.commit()
print('PR23_CASE COMMITTED_109_BASELINE=PASS',flush=True)
print('PR23_CASE ORIGINAL_SOURCE_CAPTURE=PASS',flush=True)
print('PR23_PROBE=PASS',flush=True)
