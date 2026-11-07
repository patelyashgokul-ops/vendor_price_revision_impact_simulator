"""Actual committed PR22 fixtures; edits below are isolated test setup, rolled back."""
import json
import hashlib
from contextlib import ExitStack, contextmanager
from datetime import date
from unittest.mock import patch
from odoo import api, Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.addons.vendor_price_revision_impact_simulator.models.execution import EXEC, LINE
from odoo.addons.vendor_price_revision_impact_simulator.models.monitor_models import RUN,CHECK,INCIDENT,EVENT,CORRECTION
from odoo.addons.vendor_price_revision_impact_simulator.models.monitor_policy import POLICY
from odoo.addons.vendor_price_revision_impact_simulator.models import monitor_service as service

assert env.cr.dbname.startswith('codex_vpr_pr23_')
sample=json.loads(env['ir.config_parameter'].get_str('app06.pr23.sample'))
cid,uid,eid=sample['company_id'],sample['operator_id'],sample['execution_id']
MODELS=['product.supplierinfo','purchase.order','purchase.order.line','sale.order','sale.order.line',
 'product.pricelist','product.pricelist.item','product.product','product.template','stock.quant','stock.move',
 'stock.move.line','stock.picking','stock.valuation.layer','stock.landed.cost','account.move','account.move.line','res.currency.rate','uom.uom','res.currency']

@contextmanager
def case():
 with env.registry.cursor() as cr:
  actor=api.Environment(cr,uid,{'allowed_company_ids':[cid],'tz':'UTC'})
  admin=api.Environment(cr,env.uid,{'allowed_company_ids':[cid],'tz':'UTC','tracking_disable':True,'mail_notrack':True})
  receipt=actor[EXEC].browse(eid);line=receipt.line_ids;assert len(line)==1 and receipt.state=='VERIFIED'
  yield actor,admin,receipt,line,admin['product.supplierinfo'].browse(line.target_id)
  cr.rollback()

@contextmanager
def no_operational_writes(actor):
 with ExitStack() as stack:
  for name in MODELS:
   if name not in actor:continue
   for action in ('create','write','unlink'):
    stack.enter_context(patch.object(type(actor[name]),action,side_effect=AssertionError('PR23_OPERATIONAL_MUTATION '+name+'.'+action)))
  yield

def observe(actor,receipt):
 with no_operational_writes(actor):run=receipt.action_check_applied_price_integrity()
 assert run.processed_count==1 and not run.has_more
 return run.check_ids

def marker(name):print('PR23_CASE '+name+'=PASS',flush=True)

with case() as (a,admin,e,line,target):
 check=observe(a,e)
 assert check.status=='PASS',(check.status,check.codes,check.classification)
 assert not a[INCIDENT].search([('execution_line_id','=',line.id)])
 assert check.observed['id']==target.id and check.expected==line.observed_after_values
 assert set(check.selection)>={'at_start','below_moq','above_moq','before_start'}
 assert check.metadata['archive_supported']==('active' in target._fields)
 assert e.evidence==sample['original_evidence']
 marker('A_COMMITTED_MATCH_AND_HISTORY')

with case() as (a,admin,e,line,target):
 old=target.price;target.price=old+3;target.flush_recordset()
 first=observe(a,e)
 assert 'PRICE_DRIFT' in first.codes and first.unit_price_difference=='3.0',first.read()
 assert first.status=='DRIFT_DETECTED' and target.price==old+3
 incidents=a[INCIDENT].search([('execution_line_id','=',line.id)])
 incident=incidents.filtered(lambda r:r.code=='PRICE_DRIFT');assert len(incident)==1
 original_first=incident.first_detected_at
 second=observe(a,e)
 assert a[INCIDENT].search_count([('execution_line_id','=',line.id)])==len(incidents)
 assert incident.first_detected_at==original_first
 target.price=old+6;target.flush_recordset();third=observe(a,e)
 assert first.observed['price']==str(old+3) and third.observed['price']==str(old+6)
 assert incident.latest_check_id==third and len(incident.event_ids)>=2
 with no_operational_writes(a):
  incident.action_review('investigate','Investigate current agreement','source-request:synthetic')
  proposal=incident.action_prepare_correction_plan('Agreement not established','source-request:synthetic')
  assert proposal.status=='EVIDENCE_REQUIRED' and not proposal.proposed_values
  assert proposal.requires_new_approval and proposal.requires_new_dry_run
  try:incident.action_close_incident('Comment alone','synthetic-comment')
  except UserError:pass
  else:raise AssertionError('Comment closed live anomaly')
  incident.action_revalidate_incident()
  try:incident.action_close_incident('Proposal only','synthetic-proposal')
  except UserError:pass
  else:raise AssertionError('Drift revalidation closed incident')
 assert target.price==old+6
 marker('B_PRICE_DELTA_AND_NO_RESTORE');marker('I_DEDUP_AND_RECURRING_OBSERVATIONS');marker('J_HYPOTHETICAL_CORRECTION')
 # External synthetic correction, explicitly outside the monitor and guards.
 target.price=old;target.flush_recordset()
 with no_operational_writes(a):
  incident.action_revalidate_incident()
  assert incident.revalidation_check_id.status=='PASS'
  incident.action_close_incident('Separate synthetic correction verified','synthetic-independent-governed-action')
 assert incident.status=='RESOLVED_VERIFIED' and incident.resolved_by.id==uid
 target.price=old+3;target.flush_recordset();observe(a,e)
 assert incident.status=='REOPENED' and incident.resolution_reason
 marker('REVALIDATE_CLOSE_AND_REOPEN')

for field,value,code in [('min_qty',10,'MOQ_DRIFT'),('currency_id',env.ref('base.INR').id,'CURRENCY_DRIFT'),
 ('date_start','2026-10-01','EFFECTIVE_DATE_DRIFT'),('date_end','2030-01-01','EFFECTIVE_DATE_DRIFT'),
 ('product_id',False,'PRODUCT_SCOPE_DRIFT'),('company_id',False,'COMPANY_SCOPE_DRIFT'),
 ('discount',5,'DISCOUNT_DRIFT'),('sequence',99,'COMMERCIAL_METADATA_DRIFT'),
 ('delay',9,'COMMERCIAL_METADATA_DRIFT'),('product_code','EXTERNAL-CODE','COMMERCIAL_METADATA_DRIFT')]:
 with case() as (a,admin,e,line,target):
  assert target[field]!=value,field+' fixture did not change'
  target.write({field:value});target.flush_recordset()
  check=observe(a,e);assert code in check.codes,(field,check.status,check.codes)
  assert check.status!='PASS'
  if field=='currency_id':assert not check.unit_price_difference
  marker('COMMERCIAL_'+field.upper())

with case() as (a,admin,e,line,target):
 other=admin['res.partner'].create({'name':target.partner_id.name})
 target.partner_id=other;target.flush_recordset()
 check=observe(a,e);assert 'VENDOR_IDENTITY_DRIFT' in check.codes
 marker('VENDOR_IDENTITY_NOT_DISPLAY_NAME')

with case() as (a,admin,e,line,target):
 target.unlink();admin.flush_all();check=observe(a,e)
 assert check.classification=='TARGET_NOT_FOUND_VERIFIED' and 'TARGET_MISSING' in check.codes
 assert line.target_id and line.observed_after_values and e.evidence==sample['original_evidence']
 marker('DELETED_EXACT_ID_NOT_REPLACED')

with case() as (a,admin,e,line,target):
 original=type(target).check_access
 def deny(rec,operation):
  if rec._name=='product.supplierinfo' and rec.env.uid==uid:raise AccessError('Injected target restriction')
  return original(rec,operation)
 with patch.object(type(target),'check_access',deny):check=observe(a,e)
 assert check.status=='BLOCKED' and check.classification=='TARGET_INACCESSIBLE'
 assert check.codes==['MONITORING_ACCESS_FAILURE'] and not check.observed
 marker('ACCESS_DENIED_IS_NOT_DELETION')

with case() as (a,admin,e,line,target):
 with patch.object(service,'schema',return_value={'unsupported':'selector customization'}):
  check=observe(a,e)
 assert check.status=='BLOCKED' and 'SELECTION_CHECK_UNAVAILABLE' in check.codes
 marker('UNSUPPORTED_SELECTOR_NOT_PASS')

with case() as (a,admin,e,line,target):
 unit=target.uom_id
 unit.relative_factor=unit.relative_factor*2;admin.flush_all()
 check=observe(a,e)
 assert 'UOM_DEFINITION_DRIFT' in check.codes and check.status!='PASS'
 assert not check.unit_price_difference
 marker('SAME_UOM_ID_CHANGED_FACTOR_NOT_FALSE_PASS')

with case() as (a,admin,e,line,target):
 unit=target.uom_id;unit.name+=' Cosmetic label';admin.flush_all()
 check=observe(a,e)
 assert check.status=='PASS',check.codes
 marker('COSMETIC_UNIT_LABEL_NOT_COMMERCIAL_DRIFT')

with case() as (a,admin,e,line,target):
 target.uom_id=admin.ref('uom.product_uom_unit');admin.flush_all()
 check=observe(a,e);assert 'UOM_DRIFT' in check.codes and not check.unit_price_difference
 marker('EXACT_PRICING_UNIT_ID_DRIFT')

with case() as (a,admin,e,line,target):
 target.product_id.active=False;admin.flush_all()
 check=observe(a,e);assert 'PRODUCT_SCOPE_DRIFT' in check.codes
 marker('ARCHIVED_PRODUCT_RELATED_SCOPE_NOT_DELETED_TARGET')

with case() as (a,admin,e,line,target):
 # Odoo20 selects by converted discounted price first. A higher numeric price
 # alone cannot force precedence; explicit discount gives a real cheaper winner.
 rival=target.copy(dict(price=115,discount=90,sequence=0))
 admin.flush_all();check=observe(a,e)
 assert not check.differences and 'RULE_SELECTION_DRIFT' in check.codes
 assert 'DUPLICATE_EFFECTIVE_RULE' in check.codes
 assert check.selection['at_start']['selected_id']==rival.id
 marker('G_NATIVE_SELECTOR_CONFLICT_AND_DUPLICATE')

with case() as (a,admin,e,line,target):
 with patch.object(fields.Date,'context_today',return_value=date(2026,10,26)):
  check=observe(a,e)
 assert check.status=='PASS' and check.classification=='EXPECTED_DATE_TRANSITION'
 marker('H_FUTURE_ACTIVATION_NOT_DRIFT')

with case() as (a,admin,e,line,target):
 # The historical event remains valid after present-day source expiry.
 request=e.request_id
 admin.cr.execute('UPDATE '+request._table+" SET approval_valid_until='2020-01-01' WHERE id=%s",[request.id])
 request.invalidate_recordset()
 check=observe(a,e);assert check.status=='PASS',(check.status,check.codes)
 marker('HISTORICAL_APPROVAL_EXPIRY_NOT_REWRITTEN')

with case() as (a,admin,e,line,target):
 target.price+=3;target.flush_recordset();check=observe(a,e)
 incident=a[INCIDENT].search([('execution_line_id','=',line.id),('code','=','PRICE_DRIFT')])
 for model,record_id in [(RUN,check.run_id.id),(CHECK,check.id),(INCIDENT,incident.id)]:
  rec=a[model].browse(record_id)
  for field,value in [('company_id',cid),('execution_id',eid)]:
   try:rec.write({field:value})
   except AccessError:pass
   else:raise AssertionError('Direct immutable metadata write '+model)
  try:rec.copy()
  except AccessError:pass
  else:raise AssertionError('Copied evidence '+model)
  try:rec.unlink()
  except AccessError:pass
  else:raise AssertionError('Deleted evidence '+model)
 for model in (RUN,CHECK,INCIDENT,EVENT,CORRECTION):
  try:a[model].with_context(_monitor_capability=True,default_company_id=cid)._record({})
  except AccessError:pass
  else:raise AssertionError('Forged private evidence capability')
 try:incident.write({'status':'RESOLVED_VERIFIED'})
 except AccessError:pass
 else:raise AssertionError('Forged verified resolution')
 for user in (admin.ref('base.public_user'),):
  try:check.with_user(user).read(['observed'])
  except AccessError:pass
  else:raise AssertionError('Public disclosure')
 try:a['ir.attachment'].create(dict(name='forged',res_model=CHECK,res_id=check.id,raw=b'synthetic'))
 except AccessError:pass
 else:raise AssertionError('Unprotected attachment')
 marker('DIRECT_ORM_AND_ATTACHMENT_GUARDS')

with case() as (a,admin,e,line,target):
 policy=a[POLICY].create(dict(company_id=cid,batch_size=1))
 assert not policy.enabled
 with no_operational_writes(a):
  a[POLICY]._cron_monitor23()
  assert not a[RUN].search([('execution_id','=',eid)])
  runs=policy.action_run_batch()
 assert runs and len(runs)==1
 observed=a[RUN].browse(runs)
 assert observed.processed_count<=1
 assert policy.cursor_line_id or policy.cycle>1
 for fields_ in ({'cursor_line_id':999},{'user_id':1},{'company_id':cid}):
  try:policy.write(fields_)
  except AccessError:pass
  else:raise AssertionError('Forged schedule progress or identity')
 marker('CRON_DISABLED_BOUNDED_AUTHENTICATED_CURSOR')

with case() as (a,admin,e,line,target):
 before=a[RUN].search_count([('execution_id','=',eid)])
 with patch.object(service,'persist_incidents',side_effect=RuntimeError('Injected audit write interruption')):
  try:observe(a,e)
  except RuntimeError:pass
  else:raise AssertionError('Failed monitoring appeared successful')
 assert a[RUN].search_count([('execution_id','=',eid)])==before
 assert observe(a,e).status=='PASS'
 marker('FAILED_BATCH_ROLLBACK_AND_SAFE_RETRY')

# Exact reference D/E values from genuine PR22 Unit-priced bulk applications.
bulk=env[EXEC].search([('verified_line_count','=',100)],order='id desc',limit=1)
assert bulk
reference=bulk.line_ids.filtered(lambda l:float(l.observed_after_values['min_qty'])==100)[:1]
assert reference and float(reference.observed_after_values['price'])==11
with env.registry.cursor() as cr:
 a=api.Environment(cr,bulk.operator_id.id,{'allowed_company_ids':bulk.company_id.ids})
 with no_operational_writes(a):
  check=a[EXEC].browse(bulk.id)._monitor23(line_ids=reference.ids).check_ids
 assert check.status=='PASS',(check.status,check.codes)
 assert not reference.before_values
 marker('COMMITTED_CREATE_NULL_BEFORE_HISTORY_VALID');cr.rollback()
for field,value,code,label in [('min_qty',10,'MOQ_DRIFT','D_REAL_100_TO10_MOQ'),
                              ('currency_id',env.ref('base.INR').id,'CURRENCY_DRIFT','E_REAL_USD11_TO_INR11')]:
 with env.registry.cursor() as cr:
  a=api.Environment(cr,bulk.operator_id.id,{'allowed_company_ids':bulk.company_id.ids})
  admin=api.Environment(cr,env.uid,{'allowed_company_ids':bulk.company_id.ids})
  target=admin['product.supplierinfo'].browse(reference.target_id)
  target.write({field:value});admin.flush_all()
  with no_operational_writes(a):
   check=a[EXEC].browse(bulk.id)._monitor23(line_ids=reference.ids).check_ids
  assert code in check.codes and check.status!='PASS',(label,check.status,check.codes,check.classification)
  assert float(check.expected['min_qty'])==100 and float(check.expected['price'])==11
  assert target[field].id==value if field=='currency_id' else target[field]==value
  marker(label);cr.rollback()

print('PR23_PROBE=PASS',flush=True)
