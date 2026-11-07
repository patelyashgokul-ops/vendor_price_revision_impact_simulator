"""A second independently approved PR22 transaction, not a fabricated receipt."""
import ast
import json
import re
import time
from datetime import date
from pathlib import Path
from unittest.mock import patch
from odoo import api, Command, fields
from odoo.addons.vendor_price_revision_impact_simulator.models.execution import EXEC
assert env.cr.dbname.startswith('codex_vpr_pr23_')
root=Path.cwd();sample=json.loads(env['ir.config_parameter'].get_str('app06.pr23.sample'))
old=env[EXEC].browse(sample['execution_id']);target=env['product.supplierinfo'].browse(old.line_ids.target_id)
assert len(old.line_ids)==1 and target.price==109
source=(root/'evidence/pr22-operational-safety-probe.py').read_text(encoding='utf-8')
setup_source=source.split('# Prove UPDATE does not reprice')[0].replace('codex_vpr_pr22_','codex_vpr_pr23_')
# Only the new test fixture's independently approved negotiated price changes.
setup_source=setup_source.replace("value='109'","value='112'")
scope={'env':env};exec(setup_source,scope)
tree=ast.parse(scope['PREFIX'])
token=hex(time.time_ns())[-3:].upper()
replacements={
 'company':"env['res.company'].browse("+str(old.company_id.id)+")",
 'vendor':"env['res.partner'].browse("+str(target.partner_id.id)+")",
 'policy':"env['vendor.price.revision.config'].browse("+str(old.request_id.policy_id.id)+")",
 'rates':"env['res.currency.rate'].search([('company_id','=',company.id),('name','=','2026-10-27')])",
 'product':"env['product.product'].browse("+str(target.product_id.id)+")",
 'box':"env['uom.uom'].browse("+str(target.uom_id.id)+")",
 'rule':"env['product.supplierinfo'].browse("+str(target.id)+")",
 'warehouse':"ops['stock.warehouse'].create({'name':'Independent successor source','code':'S"+token+"W','company_id':company.id})",
}
class Fixture(ast.NodeTransformer):
 def visit_Constant(self,node):
  if isinstance(node.value,str) and node.value in ('P8C','P8D','P8J','P8W'):
   node.value='S'+token+node.value[-1]
  return node
 def visit_Assign(self,node):
  if len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in replacements:
   node.value=ast.parse(replacements[node.targets[0].id],mode='eval').body
  if len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='purchase':
   values=node.value.args[0]
   values.keys.append(ast.Constant('picking_type_id'))
   values.values.append(ast.parse('warehouse.in_type_id.id',mode='eval').body)
  return self.generic_visit(node)
 def visit_Expr(self,node):
  code=ast.unparse(node)
  if code=='policy.action_publish()' or "['vendor.price.revision.product.policy']" in code:
   return ast.Pass()
  return self.generic_visit(node)
tree=ast.fix_missing_locations(Fixture().visit(tree))
text=ast.unparse(tree)
text=re.sub(r'(?m)^(\s*[A-Za-z_][A-Za-z_0-9]*) = ',r'\1=',text)
# Distinct supplier evidence, while preserving its declared USD/Box normalization.
text=text.replace('{n}\\n','successor-{n}\\n')
scope['PREFIX']=text
prepared=env['vendor.price.revision.application.plan.line'].search([('target_id','=',target.id)],order='id desc').filtered(
 lambda l:float((l.planned_after_values or {}).get('price',0))==112 and
 l.plan_id.historical_readiness=='READY_FOR_FUTURE_APPLICATION' and not l.plan_id.execution_ids)
if prepared:
 plan=prepared[0].plan_id;warehouse=plan.request_id.baseline_id.warehouse_ids
 warehouse.ensure_one()
 clock=patch.object(fields.Date,'context_today',return_value=date(2026,10,28));clock.start()
 s=dict(plan=plan,mid=plan.create_uid.id,ctx={'allowed_company_ids':old.company_id.ids},warehouse=warehouse,
   GRANT='vendor.price.revision.supply.grant',SALES_GRANT='vendor.price.revision.sales.grant',clock_patch=clock)
else:
 s=scope['setup'](1,update=True)
assert s['plan'].line_ids.target_id==target.id
assert float(s['plan'].line_ids.planned_after_values['price'])==112
# Grant the old monitoring manager explicit access to the new source warehouse;
# shared vendor/product identity alone grants no access to the new approval.
for model in (s['GRANT'],s['SALES_GRANT']):
 grants=env[model].search([('company_id','=',old.company_id.id),('user_id','=',sample['operator_id'])])
 assert grants
 grants.write({'warehouse_ids':[Command.link(s['warehouse'].id)],'reason':'Explicit successor audit warehouse access for original monitoring manager'})
env['ir.access']._clear_caches();env.cr.commit()
old_cr=env.registry.cursor()
try:
 old_actor=api.Environment(old_cr,sample['operator_id'],{'allowed_company_ids':[sample['company_id']]})
 prior=old_actor[EXEC].browse(old.id).action_check_applied_price_integrity().check_ids
 assert float(prior.observed['price'])==109
 with env.registry.cursor() as cr:
  a=api.Environment(cr,s['mid'],s['ctx']);plan=a[s['plan']._name].browse(s['plan'].id)
  successor=plan.action_apply_approved_vendor_prices(True,plan.fingerprint);new_id=successor.id
  assert successor.state=='PENDING_COMMIT';cr.commit()
 assert float(prior.observed['price'])==109,'Mixed observation across a new application commit'
 old_cr.commit()
finally:old_cr.close()
s['clock_patch'].stop()
with env.registry.cursor() as cr:
 a=api.Environment(cr,sample['operator_id'],{'allowed_company_ids':[sample['company_id']]})
 e=a[EXEC].browse(old.id);new=a[EXEC].browse(new_id)
 native=type(a['product.supplierinfo'])
 with patch.object(native,'write',side_effect=AssertionError('MONITOR_RESTORED_OLD_PRICE')),patch.object(native,'create',side_effect=AssertionError('MONITOR_CREATED_PRICE')),patch.object(native,'unlink',side_effect=AssertionError('MONITOR_DELETED_PRICE')):
  run=e.action_check_applied_price_integrity()
 check=run.check_ids
 assert check.status=='EXPECTED_CHANGE',(check.status,check.codes,check.classification)
 assert check.classification=='AUTHORIZED_SUCCESSOR' and check.successor_line_id==new.line_ids
 assert float(check.expected['price'])==112 and float(check.observed['price'])==112
 assert e.evidence==sample['original_evidence'] and e.line_ids.observed_after_values['price']=='109.0'
 cr.commit()
print('PR23_CASE C_GENUINE_INDEPENDENT_APPROVED_112_SUCCESSOR=PASS',flush=True)
print('PR23_CASE OLD_109_RECEIPT_PRESERVED=PASS',flush=True)
print('PR23_CASE NEW_PR22_APPLICATION_DURING_COHERENT_MONITOR=PASS',flush=True)
print('PR23_PROBE=PASS',flush=True)
