"""Original-user company, role, source scope, aggregate and export checks."""
import json
import time
from odoo import api, Command
from odoo.exceptions import AccessError,UserError
from odoo.addons.vendor_price_revision_impact_simulator.models.execution import EXEC, LINE, source_watch
from odoo.addons.vendor_price_revision_impact_simulator.models.monitor_models import RUN,CHECK,INCIDENT,EVENT,CORRECTION
from odoo.addons.vendor_price_revision_impact_simulator.models.monitor_policy import POLICY
assert env.cr.dbname.startswith('codex_vpr_pr23_')
sample=json.loads(env['ir.config_parameter'].get_str('app06.pr23.sample'))
cid,uid,eid=sample['company_id'],sample['operator_id'],sample['execution_id'];module='vendor_price_revision_impact_simulator.'
with env.registry.cursor() as cr:
 admin=api.Environment(cr,env.uid,{'allowed_company_ids':[cid]})
 a=api.Environment(cr,uid,{'allowed_company_ids':[cid]});e=a[EXEC].browse(eid);line=e.line_ids
 before=source_watch(e.request_id)
 run=e.action_check_applied_price_integrity();check=run.check_ids
 assert source_watch(e.request_id)==before
 foreign=admin[EXEC].search([('company_id','!=',cid)],order='id',limit=1)
 assert foreign
 b=api.Environment(cr,foreign.operator_id.id,{'allowed_company_ids':foreign.company_id.ids})
 foreign_run=b[EXEC].browse(foreign.id)._monitor23(line_ids=foreign.line_ids[:1].ids)
 for name,ids in ((RUN,foreign_run.ids),(CHECK,foreign_run.check_ids.ids)):
  protected=a[name].browse(ids)
  for method in (lambda:protected.read(['id']),lambda:protected.export_data(['id'])):
   try:method()
   except AccessError:pass
   else:raise AssertionError('Cross-company direct read/export '+name)
  assert not a[name].search([('id','in',ids)])
  assert not a[name]._read_group([('id','in',ids)],['company_id'],['__count'])
 try:e._monitor23(line_ids=foreign.line_ids[:1].ids)
 except AccessError:pass
 else:raise AssertionError('Foreign line injection')
 print('PR23_CASE COMPANY_READ_SEARCH_GROUP_EXPORT_AND_SOURCE_INJECTION=PASS',flush=True)
 target=admin['product.supplierinfo'].browse(line.target_id);target.price+=3;target.flush_recordset()
 check=e.action_check_applied_price_integrity().check_ids
 incident=a[INCIDENT].search([('execution_line_id','=',line.id),('code','=','PRICE_DRIFT')])
 try:incident.action_review('assign','Foreign owner rejected','synthetic-case',foreign.operator_id.id)
 except AccessError:pass
 else:raise AssertionError('Foreign-company-only owner assigned')
 print('PR23_CASE CROSS_COMPANY_OWNER_DENIED=PASS',flush=True)
 roles=[('sales','group_vpr_sales_user'),('purchase','group_vendor_price_revision_user'),('auditor','group_vpr_auditor')]
 # Actual role IDs are taken from this installed module, never guessed aliases.
 roles=[(label,role) for label,role in roles if admin.ref(module+role,raise_if_not_found=False)]
 assert len(roles)==3
 users={}
 for label,role in roles:
  user=admin['res.users'].with_context(no_reset_password=True).create(dict(name='PR23 '+label,login='pr23-'+label+str(time.time_ns())+'@example.invalid',
    company_id=cid,company_ids=[Command.set([cid])],group_ids=[Command.set(admin.ref(module+role).ids)]))
  users[label]=user
  if label!='auditor':
   for name,ids in ((RUN,run.ids),(CHECK,check.ids),(INCIDENT,incident.ids)):
    try:a[name].with_user(user).browse(ids).read(['id'])
    except AccessError:pass
    else:raise AssertionError('Unrestricted supplier cost role '+label)
  try:e.with_user(user).action_check_applied_price_integrity()
  except AccessError:pass
  else:raise AssertionError('Read-only role ran monitor '+label)
 # Explicit source grants permit the auditor's read, while review remains denied.
 auditor=users['auditor'];warehouses=e.plan_id.request_id.baseline_id.warehouse_ids
 auditor.group_ids=[Command.link(admin.ref('sales_team.group_sale_salesman_all_leads').id)]
 for name,extra in [('vendor.price.revision.supply.grant',dict(allow_cost=True,allow_demand=True)),('vendor.price.revision.sales.grant',{})]:
  admin[name].create(dict(company_id=cid,user_id=auditor.id,warehouse_ids=[Command.set(warehouses.ids)],reason='Explicit synthetic auditor source scope',**extra))
 admin['ir.access']._clear_caches()
 assert check.with_user(auditor).read(['observed'])
 try:incident.with_user(auditor).action_review('investigate','Auditor cannot edit','synthetic-reference')
 except AccessError:pass
 else:raise AssertionError('Auditor wrote incident')
 for user in (admin.ref('base.public_user'),admin['res.users'].with_context(no_reset_password=True).create(dict(name='PR23 portal',login='pr23portal'+str(time.time_ns())+'@example.invalid',group_ids=[Command.set(admin.ref('base.group_portal').ids)]))):
  try:check.with_user(user).read(['observed'])
  except AccessError:pass
  else:raise AssertionError('Public or portal exposure')
 print('PR23_CASE SALES_PURCHASE_PORTAL_PUBLIC_DENIED_AUDITOR_READ_ONLY=PASS',flush=True)
 # Forged source and monitoring fingerprints cannot create clean observations.
 cr.execute('UPDATE '+e._table+' SET fingerprint=%s WHERE id=%s',['forged',e.id]);e.invalidate_recordset()
 bad=e.action_check_applied_price_integrity().check_ids
 assert bad.status=='BLOCKED' and bad.codes==['HISTORICAL_EVIDENCE_INTEGRITY'] and not bad.expected
 assert e.fingerprint=='forged'
 print('PR23_CASE CORRUPT_HISTORICAL_SOURCE_BLOCKED=PASS',flush=True)
 cr.rollback()
print('PR23_PROBE=PASS',flush=True)
