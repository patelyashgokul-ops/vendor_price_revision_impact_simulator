"""Real two-session PR13 races, only committed synthetic disposable fixtures."""
import threading
import time
from datetime import date
from unittest.mock import patch
from psycopg2.errors import SerializationFailure
from odoo import Command, api, fields
from odoo.exceptions import UserError
from odoo.tools.binary import BinaryBytes

assert env.cr.dbname.startswith('codex_vpr_pr13_')
clock_patch=patch.object(fields.Date,'context_today',return_value=date(2026,10,28));clock_patch.start()
module='vendor_price_revision_impact_simulator'
company=env['res.company'].with_context(install_demo=True).create({'name':'PR13 Races '+str(time.time_ns()),'currency_id':env.ref('base.INR').id})
ctx={'allowed_company_ids':company.ids}
users=env['res.users'].with_context(no_reset_password=True).create([
 {'name':'PR13 Race '+role,'login':role+str(time.time_ns())+'@example.invalid','company_id':company.id,'company_ids':[Command.set(company.ids)],'group_ids':[Command.set(env.ref(module+'.'+group).ids)]}
 for role,group in [('preparer','group_vendor_price_revision_user'),('manager','group_vpr_purchase_manager')]])
preparer,manager=users
vendor=env['res.partner'].create({'name':'PR13 Race Vendor'})
policy=env['vendor.price.revision.config'].with_company(company).create({'company_id':company.id,'policy_version':'race1','effective_from':'2025-01-01','effective_to':'2030-12-31','change_reason':'Explicit race fixture','currency_rate_policy':'company_reference_date','currency_reference_date':'2026-10-28',
 'margin_ids':[Command.create({'scope':'company','minimum_margin_percent':20,'target_margin_percent':25,'reason':'Fixture'})],
 'risk_ids':[Command.create({'name':'Fixture scale','risk_level':'low','currency_id':company.currency_id.id,'open_ended':True,'reason':'Fixture'})],
 'approval_ids':[Command.create({'name':'Fixture finance','currency_id':company.currency_id.id,'open_ended':True,'reason':'Fixture','required_role_ids':[Command.set(env.ref(module+'.group_vpr_finance_manager').ids)]})]})
policy.action_publish()
env['vendor.price.revision.product.policy'].with_company(company).create({'company_id':company.id,'change_reason':'Exact race identities'})
unit=env.ref('uom.product_uom_unit');usd=env.ref('base.USD');usd.active=True
rates=env['res.currency.rate'].with_company(company).create([{'currency_id':c.id,'company_id':company.id,'name':'2026-10-27','rate':v} for c,v in [(company.currency_id,94),(usd,1)]])
rate_id=rates.filtered(lambda r:r.currency_id==company.currency_id).id
batch_ids=[];products=[];rules=[];boxes=[]
labels=['COLLECT','PRICE','RECEIPT','VALUE','FX','GRANT']
for n,label in enumerate(labels):
 product=env['product.product'].create({'name':'PR13 Race '+label,'default_code':f'RACE-{company.id}-{n}','company_id':company.id,'is_storable':True,'standard_price':70})
 box=env['uom.uom'].create({'name':f'PR13 Race Box10 {company.id}-{n}','relative_uom_id':unit.id,'relative_factor':10})
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
if not wh:wh=env['stock.warehouse'].with_company(company).create({'name':'PR13 Races','code':'R'+str(company.id),'company_id':company.id})
wh.out_type_id.reservation_method='manual'
for user in users:
 env[GRANT].with_company(company).create({'company_id':company.id,'user_id':user.id,'warehouse_ids':[Command.set(wh.ids)],'allow_cost':True,'allow_demand':True,'reason':'Explicit isolated PR13 scope'})
env[LOCATION].with_company(company).create({'company_id':company.id,'warehouse_id':wh.id,'location_id':wh.lot_stock_id.id,'classification':'saleable','reason':'Verified race stock'})
pricelist=env['product.pricelist'].with_company(company).create({'name':'PR13 Races','company_id':company.id,'currency_id':company.currency_id.id})
quants=[];orders=[];purchase_lines=[];sales=[];sale_lines=[]
for n,product in enumerate(products):
 quant=env['stock.quant'].with_company(company).create({'product_id':product,'location_id':wh.lot_stock_id.id,'quantity':80})
 sale=env['sale.order'].with_company(company).create({'company_id':company.id,'partner_id':vendor.id,'warehouse_id':wh.id,'pricelist_id':pricelist.id,'commitment_date':'2026-11-05 10:00:00','order_line':[Command.create({'product_id':product,'product_uom_qty':200,'product_uom_id':unit.id,'price_unit':150,'tax_ids':[Command.clear()]})]})
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
allocations=[];purchases=[]
for n in range(len(labels)):
 b=env['vendor.price.revision.import.batch'].browse(batch_ids[n]).with_user(preparer).with_context(**ctx)
 b.action_collect_supply(wh.ids)
 a=b.action_run_allocation(wh.ids);allocations.append(a.id)
 purchases.append(b.action_collect_purchase_terms(wh.ids,True,a.id,False).id)
registry=env.registry;uid=preparer.id;whid=wh.id;grant_id=env[GRANT].search([('company_id','=',company.id),('user_id','=',uid)]).id
env.cr.commit()
def batch(s,n):return s['vendor.price.revision.import.batch'].browse(batch_ids[n])
def collect(s,n):return batch(s,n).action_attribute_costs(allocations[n],purchases[n],'2026-11-05')
def race(n,mutation,expected):
 held,attempted,finished=threading.Event(),threading.Event(),threading.Event();outcomes={}
 def a():
  try:
   with registry.cursor() as cr:
    s=api.Environment(cr,uid,ctx);snap=collect(s,n);assert snap.line_ids
    held.set();assert attempted.wait(30);time.sleep(.4)
    assert not finished.is_set(),'Source mutation bypassed held cost source locks'
    cr.commit();outcomes['collector']='committed'
  except Exception as exc:outcomes['collector']=type(exc).__name__+':'+str(exc);held.set()
 def b():
  assert held.wait(30)
  try:
   with registry.cursor() as cr:
    s=api.Environment(cr,uid,ctx);batch(s,n).read(['state']);attempted.set();mutation(s,n);cr.commit();outcomes['competitor']='committed'
  except SerializationFailure:outcomes['competitor']='serialization_retry'
  except Exception as exc:outcomes['competitor']=type(exc).__name__+':'+str(exc)
  finally:finished.set()
 threads=[threading.Thread(target=a),threading.Thread(target=b)]
 for t in threads:t.start()
 for t in threads:t.join(75)
 assert not any(t.is_alive() for t in threads),labels[n]
 assert outcomes=={'collector':'committed','competitor':expected},(labels[n],outcomes)
 print('PR13_CONCURRENT_'+labels[n]+'=PASS '+str(outcomes))
def receive(s,n):
 picking=s['purchase.order'].sudo().browse(orders[n]).picking_ids[:1]
 picking.move_ids.quantity=20;picking.move_ids.picked=True;picking._action_done()
def assert_changed_source_is_stale(n):
 with registry.cursor() as cr:
  s=api.Environment(cr,uid,ctx)
  try:batch(s,n).get_current_costs(allocations[n],purchases[n],'2026-11-05')
  except (UserError,AccessError):pass
  else:raise AssertionError('Changed cost source was not rejected: '+labels[n])
  cr.rollback()
race(0,lambda s,n:collect(s,n),'serialization_retry')
with registry.cursor() as cr:
 s=api.Environment(cr,uid,ctx);assert collect(s,0).version==1;assert s['vendor.price.revision.cost.snapshot'].search_count([('batch_id','=',batch_ids[0])])==1;cr.commit()
race(1,lambda s,n:s['purchase.order.line'].sudo().browse(purchase_lines[n]).write({'price_unit':115}),'committed')
assert_changed_source_is_stale(1)
race(2,receive,'committed')
assert_changed_source_is_stale(2)
race(3,lambda s,n:s['stock.move'].sudo().browse(receipt_id).write({'value':750}),'committed')
assert_changed_source_is_stale(3)
race(4,lambda s,n:s['res.currency.rate'].sudo().browse(rate_id).write({'rate':95}),'committed')
assert_changed_source_is_stale(4)
# FX mutation above invalidates PR08/supply for every fixture. Revalidate the
# final independent grant fixture explicitly before its own race.
with registry.cursor() as cr:
 s=api.Environment(cr,uid,ctx);b=batch(s,5);b.action_validate_commercial_prices();b.action_collect_supply([whid]);a=b.action_run_allocation([whid]);allocations[5]=a.id;purchases[5]=b.action_collect_purchase_terms([whid],True,a.id,False).id;cr.commit()
race(5,lambda s,n:s[GRANT].sudo().browse(grant_id).write({'allow_cost':False,'reason':'Concurrent cost access revocation'}),'serialization_retry')
with registry.cursor() as cr:
 s=api.Environment(cr,uid,ctx);s[GRANT].sudo().browse(grant_id).write({'allow_cost':False,'reason':'Fresh access revocation retry'});cr.commit()
with registry.cursor() as cr:
 s=api.Environment(cr,uid,ctx)
 try:batch(s,5).get_current_costs(allocations[5],purchases[5],'2026-11-05')
 except AccessError:pass
 else:raise AssertionError('Revoked user retained current cost service access')
 cr.rollback()
clock_patch.stop();print('PR13_PROBE=PASS')
