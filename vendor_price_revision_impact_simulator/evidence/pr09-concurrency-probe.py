"""Real two-session PR09 races, only committed synthetic disposable fixtures."""
import threading
import time
from datetime import date
from unittest.mock import patch
from psycopg2.errors import SerializationFailure
from odoo import Command, api, fields
from odoo.exceptions import UserError
from odoo.tools.binary import BinaryBytes

assert env.cr.dbname.startswith('codex_vpr_pr09_')
clock_patch=patch.object(fields.Date,'context_today',return_value=date(2026,10,28));clock_patch.start()
module='vendor_price_revision_impact_simulator'
company=env['res.company'].with_context(install_demo=True).create({'name':'PR09 Races '+str(time.time_ns()),'currency_id':env.ref('base.INR').id})
ctx={'allowed_company_ids':company.ids}
users=env['res.users'].with_context(no_reset_password=True).create([
 {'name':'PR09 Race '+role,'login':role+str(time.time_ns())+'@example.invalid','company_id':company.id,'company_ids':[Command.set(company.ids)],'group_ids':[Command.set(env.ref(module+'.'+group).ids)]}
 for role,group in [('preparer','group_vendor_price_revision_user'),('manager','group_vpr_purchase_manager')]])
preparer,manager=users
vendor=env['res.partner'].create({'name':'PR09 Race Vendor'})
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
labels=['COLLECT','RESERVATION','RECEIPT','CANCEL','PRICE','UOM','LOCATION','GRANT']
for n,label in enumerate(labels):
 product=env['product.product'].create({'name':'PR09 Race '+label,'default_code':f'RACE-{company.id}-{n}','company_id':company.id,'is_storable':True})
 box=env['uom.uom'].create({'name':f'PR09 Race Box10 {company.id}-{n}','relative_uom_id':unit.id,'relative_factor':10})
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
if not wh:wh=env['stock.warehouse'].with_company(company).create({'name':'PR09 Races A','code':'RA'+str(company.id),'company_id':company.id})
wh2=env['stock.warehouse'].with_company(company).create({'name':'PR09 Races B','code':'RB'+str(company.id),'company_id':company.id})
for user in users:
 env[GRANT].with_company(company).create({'company_id':company.id,'user_id':user.id,'warehouse_ids':[Command.set((wh|wh2).ids)],'allow_cost':True,'reason':'Explicit isolated race service scope'})
for warehouse in (wh|wh2):
 env[LOCATION].with_company(company).create({'company_id':company.id,'warehouse_id':warehouse.id,'location_id':warehouse.lot_stock_id.id,'classification':'saleable','reason':'Verified race stock location'})
quants=[];orders=[];lines=[]
for product in products:
 quant=env['stock.quant'].with_company(company).create({'product_id':product,'location_id':wh.lot_stock_id.id,'quantity':10})
 po=env['purchase.order'].with_company(company).create({'company_id':company.id,'partner_id':vendor.id,'currency_id':company.currency_id.id,'picking_type_id':wh.in_type_id.id,'order_line':[Command.create({'product_id':product,'product_qty':100,'uom_id':unit.id,'price_unit':100,'tax_ids':[Command.clear()],'date_planned':'2026-11-02 08:00:00'})]})
 po.button_confirm();quants.append(quant.id);orders.append(po.id);lines.append(po.order_line.id)
registry=env.registry;uid=preparer.id;mid=manager.id;company_id=company.id;whid=wh.id;loc2=wh2.lot_stock_id.id
grant_id=env[GRANT].search([('company_id','=',company.id),('user_id','=',uid)]).id
env.cr.commit()
def batch(s,n):return s['vendor.price.revision.import.batch'].browse(batch_ids[n])
def race(n,mutation,expected):
 held,attempted,finished=threading.Event(),threading.Event(),threading.Event();outcomes={}
 def a():
  try:
   with registry.cursor() as cr:
    s=api.Environment(cr,uid,ctx);snap=batch(s,n).action_collect_supply([whid]);assert snap.exists()
    held.set();assert attempted.wait(25);time.sleep(.4)
    assert not finished.is_set(),'Mutation bypassed existing evidence locks'
    cr.commit();outcomes['collector']='committed'
  except Exception as exc:outcomes['collector']=type(exc).__name__+':'+str(exc);held.set()
 def b():
  assert held.wait(25)
  try:
   with registry.cursor() as cr:
    s=api.Environment(cr,uid,ctx);batch(s,n).read(['state']);attempted.set();mutation(s,n);cr.commit();outcomes['competitor']='committed'
  except SerializationFailure:outcomes['competitor']='serialization_retry'
  except Exception as exc:outcomes['competitor']=type(exc).__name__+':'+str(exc)
  finally:finished.set()
 threads=[threading.Thread(target=a),threading.Thread(target=b)]
 for t in threads:t.start()
 for t in threads:t.join(60)
 assert not any(t.is_alive() for t in threads),labels[n]
 assert outcomes=={'collector':'committed','competitor':expected},(labels[n],outcomes)
 print('PR09_CONCURRENT_'+labels[n]+'=PASS '+str(outcomes))

def receipt(s,n):
 po=s['purchase.order'].sudo().browse(orders[n]);picking=po.picking_ids.filtered(lambda p:p.state not in ('done','cancel'))[:1]
 picking.move_ids.quantity=40;picking.move_ids.picked=True;picking._action_done()
race(0,lambda s,n:batch(s,n).action_collect_supply([whid]),'serialization_retry')
with registry.cursor() as cr:
 s=api.Environment(cr,uid,ctx);snap=batch(s,0).action_collect_supply([whid]);assert snap.version==1;cr.commit()
race(1,lambda s,n:s['stock.quant'].sudo().browse(quants[n]).write({'reserved_quantity':3}),'committed')
race(2,receipt,'committed')
race(3,lambda s,n:s['purchase.order'].sudo().browse(orders[n]).button_cancel(),'committed')
race(4,lambda s,n:s['purchase.order.line'].sudo().browse(lines[n]).write({'price_unit':110}),'committed')
race(5,lambda s,n:s['uom.uom'].sudo().browse(boxes[n]).write({'relative_factor':12}),'committed')
race(6,lambda s,n:s['stock.quant'].sudo().browse(quants[n]).write({'location_id':loc2}),'committed')
for n in range(1,7):
 with registry.cursor() as cr:
  s=api.Environment(cr,uid,ctx)
  try:batch(s,n).get_current_supply([whid])
  except UserError:pass
  else:raise AssertionError('Changed source was not stale: '+labels[n])
  cr.rollback()
race(7,lambda s,n:s[GRANT].sudo().browse(grant_id).write({'active':False,'reason':'Concurrent grant revocation'}),'serialization_retry')
with registry.cursor() as cr:
 s=api.Environment(cr,uid,ctx);s[GRANT].sudo().browse(grant_id).write({'active':False,'reason':'Fresh revocation retry'});cr.commit()
with registry.cursor() as cr:
 s=api.Environment(cr,uid,ctx)
 try:batch(s,7).get_current_supply([whid])
 except AccessError:pass
 else:raise AssertionError('Revocation did not block fresh consumer')
 cr.rollback()
clock_patch.stop()
print('PR09_PROBE=PASS')
