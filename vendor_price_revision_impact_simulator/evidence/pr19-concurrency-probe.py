"""Real two-session PR19 races, only committed synthetic disposable fixtures."""
import threading
import time
from datetime import date
from unittest.mock import patch
from psycopg2.errors import SerializationFailure
from odoo import Command, api, fields
from odoo.exceptions import UserError
from odoo.tools.binary import BinaryBytes

assert env.cr.dbname.startswith('codex_vpr_pr19_')
clock_patch=patch.object(fields.Date,'context_today',return_value=date(2026,10,28));clock_patch.start()
module='vendor_price_revision_impact_simulator'
company=env['res.company'].with_context(install_demo=True).create({'name':'PR19 Races '+str(time.time_ns()),'currency_id':env.ref('base.INR').id})
ctx={'allowed_company_ids':company.ids}
users=env['res.users'].with_context(no_reset_password=True).create([
 {'name':'PR19 Race '+role,'login':role+str(time.time_ns())+'@example.invalid','company_id':company.id,'company_ids':[Command.set(company.ids)],'group_ids':[Command.set(env.ref(module+'.'+group).ids)]}
 for role,group in [('preparer','group_vendor_price_revision_user'),('manager','group_vpr_finance_manager')]])
preparer,manager=users
manager.group_ids=[Command.link(env.ref(module+'.group_vpr_purchase_manager').id)]
vendor=env['res.partner'].create({'name':'PR19 Race Vendor'})
policy=env['vendor.price.revision.config'].with_company(company).create({'company_id':company.id,'policy_version':'race1','effective_from':'2025-01-01','effective_to':'2030-12-31','change_reason':'Explicit race fixture','currency_rate_policy':'company_reference_date','currency_reference_date':'2026-10-28','reconciliation_basis_policy':'documented_projection',
 'workflow_enabled':True,'workflow_types':['supplier_scenario'],
 'workflow_high_group_ids':[Command.set(env.ref(module+'.group_vpr_finance_manager').ids)],
 'workflow_critical_group_ids':[Command.set(env.ref(module+'.group_vpr_finance_manager').ids)],
 'workflow_contract_group_ids':[Command.set(env.ref(module+'.group_vpr_finance_manager').ids)],
 'margin_ids':[Command.create({'scope':'company','minimum_margin_percent':20,'target_margin_percent':25,'reason':'Fixture'})],
 'risk_ids':[Command.create({'name':'Fixture scale','risk_level':'low','currency_id':company.currency_id.id,'open_ended':True,'reason':'Fixture'})],
 'approval_ids':[Command.create({'name':'Fixture finance','workflow_types':['vendor_revision','supplier_scenario'],'currency_id':company.currency_id.id,'open_ended':True,'reason':'Fixture','required_role_ids':[Command.set(env.ref(module+'.group_vpr_finance_manager').ids)]})]})
policy.action_publish()
env['vendor.price.revision.product.policy'].with_company(company).create({'company_id':company.id,'change_reason':'Exact race identities'})
unit=env.ref('uom.product_uom_unit');usd=env.ref('base.USD');usd.active=True
rates=env['res.currency.rate'].with_company(company).create([{'currency_id':c.id,'company_id':company.id,'name':'2026-10-27','rate':v} for c,v in [(company.currency_id,94),(usd,1)]])
rate_id=rates.filtered(lambda r:r.currency_id==company.currency_id).id
batch_ids=[];products=[];rules=[];boxes=[]
labels=['PREPARE','SUBMIT','SOURCE_PRICE','POLICY_PUBLICATION','ASSUMPTIONS','SOURCE_GRANT','REVIEWER_ROLE','REVIEWER_COMPANY']
for n,label in enumerate(labels):
 product=env['product.product'].with_company(company).create({'name':'PR19 Race '+label,'default_code':f'RACE-{company.id}-{n}','company_id':company.id,'is_storable':True,'standard_price':70})
 box=env['uom.uom'].create({'name':f'PR19 Race Box10 {company.id}-{n}','relative_uom_id':unit.id,'relative_factor':10})
 rule=env['product.supplierinfo'].with_company(company).create({'partner_id':vendor.id,'company_id':company.id,'product_id':product.id,'uom_id':box.id,'currency_id':usd.id,'price':100,'min_qty':1,'date_end':'2026-10-31'})
 revision=env['vendor.price.revision'].with_user(preparer).with_context(**ctx).create({'company_id':company.id,'vendor_id':vendor.id})
 source=f'Code,Price,Currency,UoM,MOQ,Date,Note\n{product.default_code},110,USD,BOX,1,2026-11-01,{n}\n'.encode()
 wizard=env['vendor.price.revision.import.wizard'].with_user(preparer).with_context(**ctx).create({'company_id':company.id,'revision_id':revision.id,'upload_file':BinaryBytes(source),'upload_filename':f'race-{n}.csv'})
 wizard.action_upload_extract();batch=wizard.result_batch_id
 env['vendor.price.revision.import.mapping'].with_user(preparer).with_context(**ctx).create([{'batch_id':batch.id,'column_number':i,'target':t} for i,t in enumerate(['vendor_product_code','proposed_price_raw','currency_raw','purchase_uom_raw','min_qty_raw','effective_date_raw'],1)])
 batch.action_validate_structure();batch.action_match_products()
 interpretation=batch.action_propose_commercial_context({'uom_aliases':{'BOX':box.id},'price_basis':'net_exclusive'},'Explicit supplier units and net price')
 interpretation.with_user(manager).action_verify_context('Independent interpretation review')
 batch.action_validate_commercial_prices()
 assert batch.row_ids.commercial_status=='commercially_valid'
 batch_ids.append(batch.id);products.append(product.id);rules.append(rule.id);boxes.append(box.id)

from odoo.exceptions import AccessError
from odoo.addons.vendor_price_revision_impact_simulator.models.supply_governance import GRANT,LOCATION
wh=env['stock.warehouse'].search([('company_id','=',company.id)],limit=1)
if not wh:wh=env['stock.warehouse'].with_company(company).create({'name':'PR19 Races','code':'R'+str(company.id),'company_id':company.id})
wh.out_type_id.reservation_method='manual'
for user in users:
 env[GRANT].with_company(company).create({'company_id':company.id,'user_id':user.id,'warehouse_ids':[Command.set(wh.ids)],'allow_cost':True,'allow_demand':True,'reason':'Explicit isolated PR19 scope'})
env[LOCATION].with_company(company).create({'company_id':company.id,'warehouse_id':wh.id,'location_id':wh.lot_stock_id.id,'classification':'saleable','reason':'Verified race stock'})
pricelist=env['product.pricelist'].with_company(company).create({'name':'PR19 Races','company_id':company.id,'currency_id':company.currency_id.id})
quants=[];orders=[];purchase_lines=[];sales=[];sale_lines=[]
for n,product in enumerate(products):
 quant=env['stock.quant'].with_company(company).create({'product_id':product,'location_id':wh.lot_stock_id.id,'quantity':80})
 sale=env['sale.order'].with_company(company).create({'company_id':company.id,'partner_id':vendor.id,'warehouse_id':wh.id,'pricelist_id':pricelist.id,'commitment_date':'2026-11-05 10:00:00','order_line':[Command.create({'product_id':product,'product_uom_qty':200,'product_uom_id':unit.id,'price_unit':1500,'tax_ids':[Command.clear()]})]})
 sale.action_confirm()
 po=env['purchase.order'].with_company(company).create({'company_id':company.id,'partner_id':vendor.id,'currency_id':company.currency_id.id,'picking_type_id':wh.in_type_id.id,'order_line':[Command.create({'product_id':product,'product_qty':40,'uom_id':unit.id,'price_unit':100,'date_planned':'2026-11-02 08:00:00','tax_ids':[Command.clear()]})]})

 po.button_confirm()
 quants.append(quant.id);orders.append(po.id);purchase_lines.append(po.order_line.id);sales.append(sale.id);sale_lines.append(sale.order_line.id)
 batch=env['vendor.price.revision.import.batch'].browse(batch_ids[n]).with_user(preparer).with_context(**ctx)
 batch.action_collect_supply(wh.ids)



# Actual valued move is prepared before analytical collection.
receipt=env['stock.move'].with_company(company).create({'company_id':company.id,'product_id':products[3],'uom_id':unit.id,'product_uom_qty':10,'price_unit':70,'location_id':env.ref('stock.stock_location_suppliers').id,'location_dest_id':wh.lot_stock_id.id})
receipt._action_confirm();receipt.quantity=10;receipt.picked=True;receipt._action_done()
receipt_id=receipt.id
from odoo.addons.vendor_price_revision_impact_simulator.models.sales_exposure import GRANT as SALES_GRANT
for person in users:
 person.write({'group_ids':[Command.link(env.ref(module+'.group_vpr_sales_manager').id),Command.link(env.ref('sales_team.group_sale_salesman_all_leads').id)]})
 env[SALES_GRANT].with_company(company).create({'company_id':company.id,'user_id':person.id,'warehouse_ids':[Command.set(wh.ids)],'reason':'Explicit native-authorized financial customer scope'})
allocations=[];purchases=[];costs=[];sales_snapshots=[];financials=[];margins=[]
for n in range(len(labels)):
 b=env['vendor.price.revision.import.batch'].browse(batch_ids[n]).with_user(preparer).with_context(**ctx)
 b.action_collect_supply(wh.ids)
 a=b.action_run_allocation(wh.ids);allocations.append(a.id)
 purchases.append(b.action_collect_purchase_terms(wh.ids,True,a.id,False).id)
 terms=b.action_propose_supply_terms(wh.id,purchase_lines[n],'firm','Explicit synthetic contract');terms.with_user(manager).action_verify_terms('Independent exact contract review')
 b.action_collect_supply(wh.ids);a=b.action_run_allocation(wh.ids);allocations[-1]=a.id;purchases[-1]=b.action_collect_purchase_terms(wh.ids,True,a.id,False).id
 for line in env['vendor.price.revision.purchase.snapshot'].browse(purchases[-1]).line_ids:
  evidence=line.with_user(preparer).action_propose_evidence('fixed','Synthetic exact contract','No amendment accepted')
  evidence.with_user(manager).action_verify('Independent exact fixed agreement')
 purchases[-1]=b.action_collect_purchase_terms(wh.ids,True,a.id,False).id
 costs.append(b.action_attribute_costs(a.id,purchases[-1],'2026-11-05').id)
 sales_snapshots.append(a.with_user(manager).action_collect_sales_terms().id)
 financials.append(b.with_user(manager).action_calculate_financial_exposure(costs[-1],sales_snapshots[-1]).id)
 margins.append(b.with_user(manager).action_calculate_profitability(financials[-1]).id)
baselines=[];scenarios=[]
for n in range(len(labels)):
 b=env['vendor.price.revision.import.batch'].browse(batch_ids[n]).with_user(manager).with_context(**ctx)
 baseline=b.action_run_reconciliation(margins[n])
 assert baseline.readiness=='ready_for_financial_review', (labels[n],baseline.readiness,baseline.check_ids.filtered(lambda c:c.status not in ('pass','not_applicable')).read(['code','status','values']))
 baselines.append(baseline.id)
 scenarios.append(b.action_create_vendor_scenario(baselines[-1],'Race '+labels[n]).id)
 env['vendor.price.revision.scenario'].browse(scenarios[-1]).with_user(manager).with_context(**ctx).action_calculate_scenario()

checker=env['res.users'].with_context(no_reset_password=True).create(dict(name='PR19 Race Checker',login='pr19checker'+str(time.time_ns())+'@example.invalid',company_id=company.id,company_ids=[Command.set(company.ids)],group_ids=[Command.set([env.ref(module+'.group_vpr_finance_manager').id,env.ref(module+'.group_vpr_confidential_reader').id,env.ref('sales_team.group_sale_salesman_all_leads').id])]))
env[GRANT].create(dict(company_id=company.id,user_id=checker.id,warehouse_ids=[Command.set(wh.ids)],allow_cost=True,allow_demand=True,reason='Explicit checker source scope'))
env[SALES_GRANT].create(dict(company_id=company.id,user_id=checker.id,warehouse_ids=[Command.set(wh.ids)],reason='Explicit checker customer scope'))
other=env['res.company'].with_context(install_demo=True).create(dict(name='PR19 Other Checker Company '+str(time.time_ns())))
registry=env.registry;uid=manager.id;whid=wh.id
request_ids=[0]*len(labels)
for n in range(1,len(labels)):
 request_ids[n]=env['vendor.price.revision.approval.request'].with_user(manager).with_context(**ctx).create(dict(baseline_id=baselines[n],scenario_id=scenarios[n],request_type='supplier_scenario',reason='Synthetic concurrent management review')).id
grant_id=env[GRANT].search([('company_id','=',company.id),('user_id','=',uid)]).id
checker_id=checker.id;company_id=company.id;other_id=other.id
original_groups=checker.group_ids.ids
# Only this explicitly synthetic fixture is committed, in a dedicated database.
env.cr.commit()
H='vendor.price.revision.approval.request'
def prepare(s,n):
 return s[H].create(dict(baseline_id=baselines[n],scenario_id=scenarios[n],request_type='supplier_scenario',reason='Synthetic concurrent exact source prepare'))
def collect(s,n):
 r=prepare(s,n) if n==0 else s[H].browse(request_ids[n])
 request_ids[n]=r.id
 if n:r.action_submit_for_review();assert r.stage_ids and r.evidence_id
 return r

def race(n,mutation,expected):
 held,attempted,finished=threading.Event(),threading.Event(),threading.Event();outcomes={}
 def a():
  try:
   with registry.cursor() as cr:
    s=api.Environment(cr,uid,ctx);collect(s,n)
    held.set();assert attempted.wait(30);time.sleep(.4)
    assert not finished.is_set(),'Concurrent mutation bypassed source/approval locks'
    cr.commit();outcomes['submitter']='committed'
  except Exception as exc:outcomes['submitter']=type(exc).__name__+':'+str(exc);held.set()
 def b():
  assert held.wait(30)
  try:
   with registry.cursor() as cr:
    s=api.Environment(cr,uid,ctx);s[H].search_count([]);attempted.set();mutation(s,n);cr.commit();outcomes['competitor']='committed'
  except SerializationFailure:outcomes['competitor']='serialization_retry'
  except Exception as exc:outcomes['competitor']=type(exc).__name__+':'+str(exc)
  finally:finished.set()
 threads=[threading.Thread(target=a),threading.Thread(target=b)]
 for t in threads:t.start()
 for t in threads:t.join(75)
 assert not any(t.is_alive() for t in threads),labels[n]
 assert outcomes=={'submitter':'committed','competitor':expected},(labels[n],outcomes)
 print('PR19_CONCURRENT_'+labels[n]+'=PASS '+str(outcomes),flush=True)
def changed(n):
 with registry.cursor() as cr:
  s=api.Environment(cr,uid,ctx)
  try:s[H].browse(request_ids[n]).get_current_request()
  except (UserError,AccessError):pass
  else:raise AssertionError('Changed approval source/authority accepted '+labels[n])
def admin(s):return api.Environment(s.cr,1,ctx)
race(0,prepare,'serialization_retry')
with registry.cursor() as cr:
 s=api.Environment(cr,uid,ctx);r=prepare(s,0);assert r.id==request_ids[0];assert s[H].search_count([('scope_key','=',r.scope_key)])==1;cr.commit()
race(1,lambda s,n:collect(s,n),'serialization_retry')
with registry.cursor() as cr:
 s=api.Environment(cr,uid,ctx);r=collect(s,1);assert len(r.stage_ids)==1;assert s['vendor.price.revision.approval.evidence'].search_count([('request_id','=',r.id)])==1;cr.commit()
race(2,lambda s,n:admin(s)['sale.order.line'].browse(sale_lines[n]).write({'price_unit':160}),'committed');changed(2)
def publish(s,n):
 p=admin(s)['vendor.price.revision.config'].browse(policy.id).copy(dict(effective_from='2031-01-01',effective_to='2032-12-31',change_reason='Concurrent future policy'))
 p.action_publish()
race(3,publish,'serialization_retry')
with registry.cursor() as cr:
 s=api.Environment(cr,uid,ctx);publish(s,3);assert s[H].browse(request_ids[3]).get_current_request();cr.commit()
def assumptions(s,n):
 s['vendor.price.revision.scenario'].browse(scenarios[n]).action_set_assumptions([dict(product_id=products[n],mode='explicit',value='112',reason='Concurrent hypothetical negotiation')],'Concurrent source assumptions')
race(4,assumptions,'serialization_retry')
with registry.cursor() as cr:
 s=api.Environment(cr,uid,ctx);assumptions(s,4);cr.commit()
changed(4)
def revoke(s,n):admin(s)[GRANT].browse(grant_id).write(dict(allow_cost=False,reason='Concurrent explicit revocation'))
race(5,revoke,'serialization_retry')
with registry.cursor() as cr:
 s=api.Environment(cr,uid,ctx);revoke(s,5);cr.commit()
changed(5)
with registry.cursor() as cr:
 s=api.Environment(cr,1,ctx);s[GRANT].browse(grant_id).write(dict(allow_cost=True,reason='Restore isolated fixture for next independent race'));cr.commit()
def role(s,n):admin(s)['res.users'].browse(checker_id).write(dict(group_ids=[Command.set(env.ref('base.group_user').ids)]))
race(6,role,'committed');changed(6)
with registry.cursor() as cr:
 s=api.Environment(cr,1,ctx);s['res.users'].browse(checker_id).write(dict(group_ids=[Command.set(original_groups)]));cr.commit()
def company_change(s,n):admin(s)['res.users'].browse(checker_id).write(dict(company_id=other_id,company_ids=[Command.set([other_id])]))
race(7,company_change,'committed');changed(7)
clock_patch.stop();print('PR19_PROBE=PASS',flush=True)
