"""Real two-session PR08 races, only committed synthetic disposable fixtures."""
import threading
import time
from datetime import date
from unittest.mock import patch
from psycopg2.errors import SerializationFailure
from odoo import Command, api, fields
from odoo.exceptions import UserError
from odoo.tools.binary import BinaryBytes

assert env.cr.dbname.startswith('codex_vpr_pr08_')
clock_patch=patch.object(fields.Date,'context_today',return_value=date(2026,10,28));clock_patch.start()
module='vendor_price_revision_impact_simulator'
company=env['res.company'].with_context(install_demo=True).create({'name':'PR08 Races '+str(time.time_ns()),'currency_id':env.ref('base.INR').id})
ctx={'allowed_company_ids':company.ids}
users=env['res.users'].with_context(no_reset_password=True).create([
 {'name':'PR08 Race '+role,'login':role+str(time.time_ns())+'@example.invalid','company_id':company.id,'company_ids':[Command.set(company.ids)],'group_ids':[Command.set(env.ref(module+'.'+group).ids)]}
 for role,group in [('preparer','group_vendor_price_revision_user'),('manager','group_vpr_purchase_manager')]])
preparer,manager=users
vendor=env['res.partner'].create({'name':'PR08 Race Vendor'})
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
labels=['VALIDATE','BASELINE','FX','UOM_FACTOR','PRODUCT_UOM','CORRECT','MAPPING','CANCEL','CONTEXT']
for n,label in enumerate(labels):
 product=env['product.product'].create({'name':'PR08 Race '+label,'default_code':f'RACE-{company.id}-{n}','company_id':company.id})
 box=env['uom.uom'].create({'name':f'PR08 Race Box10 {company.id}-{n}','relative_uom_id':unit.id,'relative_factor':10})
 rule=env['product.supplierinfo'].with_company(company).create({'partner_id':vendor.id,'company_id':company.id,'product_id':product.id,'uom_id':box.id,'currency_id':usd.id,'price':100,'min_qty':1,'date_end':'2026-10-31'})
 revision=env['vendor.price.revision'].with_user(preparer).with_context(**ctx).create({'company_id':company.id,'vendor_id':vendor.id})
 source=f'Code,Price,Currency,UoM,MOQ,Date,Note\n{product.default_code},110,USD,BOX,1,2026-11-01,{n}\n'.encode()
 wizard=env['vendor.price.revision.import.wizard'].with_user(preparer).with_context(**ctx).create({'company_id':company.id,'revision_id':revision.id,'upload_file':BinaryBytes(source),'upload_filename':f'race-{n}.csv'})
 wizard.action_upload_extract();batch=wizard.result_batch_id
 env['vendor.price.revision.import.mapping'].with_user(preparer).with_context(**ctx).create([{'batch_id':batch.id,'column_number':i,'target':t} for i,t in enumerate(['vendor_product_code','proposed_price_raw','currency_raw','purchase_uom_raw','min_qty_raw','effective_date_raw'],1)])
 batch.action_validate_structure();batch.action_match_products()
 interpretation=batch.action_propose_commercial_context({'uom_aliases':{'BOX':box.id},'price_basis':'net_exclusive'},'Explicit supplier units and net price')
 interpretation.with_user(manager).action_verify_context('Independent interpretation review')
 batch_ids.append(batch.id);products.append(product.id);rules.append(rule.id);boxes.append(box.id)
registry=env.registry;uid=preparer.id;mid=manager.id;company_id=company.id;unit_id=unit.id
env.cr.commit()

def get_batch(session,n):return session['vendor.price.revision.import.batch'].browse(batch_ids[n])
def race(n,competitor,expected):
 held,attempted,finished=threading.Event(),threading.Event(),threading.Event();outcomes={}
 def a():
  try:
   with registry.cursor() as cr:
    session=api.Environment(cr,uid,ctx);batch=get_batch(session,n)
    assert batch.action_validate_commercial_prices()
    assert batch.row_ids.commercial_result_id.status=='commercially_valid'
    held.set();assert attempted.wait(15);time.sleep(.3)
    assert not finished.is_set(),'Competing mutation bypassed held evidence locks'
    cr.commit();outcomes['validator']='committed'
  except Exception as exc:outcomes['validator']=type(exc).__name__+':'+str(exc);held.set()
 def b():
  assert held.wait(15)
  try:
   with registry.cursor() as cr:
    session=api.Environment(cr,uid,ctx);get_batch(session,n).read(['state'])
    attempted.set();competitor(session,n);cr.commit();outcomes['competitor']='committed'
  except SerializationFailure:outcomes['competitor']='serialization_retry'
  except Exception as exc:outcomes['competitor']=type(exc).__name__+':'+str(exc)
  finally:finished.set()
 threads=[threading.Thread(target=a),threading.Thread(target=b)]
 for t in threads:t.start()
 for t in threads:t.join(40)
 assert not any(t.is_alive() for t in threads),labels[n]
 assert outcomes=={'validator':'committed','competitor':expected},(labels[n],outcomes)
 print('PR08_CONCURRENT_'+labels[n]+'=PASS '+str(outcomes))

race(0,lambda s,n:get_batch(s,n).action_validate_commercial_prices(),'serialization_retry')
with registry.cursor() as cr:
 s=api.Environment(cr,uid,ctx);b=get_batch(s,0)
 assert b.action_validate_commercial_prices() and len(b.commercial_result_ids)==1
 assert len(b.get_commercially_valid_rows())==1;cr.commit()
race(1,lambda s,n:s['product.supplierinfo'].browse(rules[n]).sudo().write({'price':90}),'committed')
race(2,lambda s,n:s['res.currency.rate'].browse(rate_id).sudo().write({'rate':95}),'committed')
race(3,lambda s,n:s['uom.uom'].browse(boxes[n]).sudo().write({'relative_factor':12}),'committed')
race(4,lambda s,n:s['product.product'].browse(products[n]).sudo().write({'uom_id':boxes[n]}),'committed')
for n in (1,2,3,4):
 with registry.cursor() as cr:
  s=api.Environment(cr,uid,ctx);b=get_batch(s,n)
  assert not b.get_commercially_valid_rows() and b.row_ids.commercial_status=='stale'
  assert b.commercial_result_ids.exists();cr.rollback()
race(5,lambda s,n:get_batch(s,n).row_ids.action_correct('proposed_price_raw','120','Concurrent corrected supplier price'),'serialization_retry')
with registry.cursor() as cr:
 s=api.Environment(cr,uid,ctx);b=get_batch(s,5)
 b.row_ids.action_correct('proposed_price_raw','120','Fresh transaction correction')
 try:b.get_commercially_valid_rows()
 except UserError:pass
 else:raise AssertionError('Stale source entered commercial handoff')
 assert b.commercial_result_ids.exists();cr.commit()
race(6,lambda s,n:get_batch(s,n).row_ids.action_propose_product(products[n],'Concurrent mapping version','2026-01-01','2026-12-31'),'serialization_retry')
with registry.cursor() as cr:
 s=api.Environment(cr,uid,ctx);b=get_batch(s,6)
 mapping=b.row_ids.action_propose_product(products[6],'Fresh mapping proposal','2026-01-01','2026-12-31')
 mapping.with_user(mid).action_confirm_mapping('Independent mapping review')
 assert not b.get_commercially_valid_rows() and b.row_ids.commercial_status=='stale';cr.commit()
race(7,lambda s,n:get_batch(s,n).action_cancel(),'serialization_retry')
with registry.cursor() as cr:
 s=api.Environment(cr,uid,ctx);b=get_batch(s,7)
 try:b.action_cancel()
 except UserError:pass
 else:raise AssertionError('Cancellation discarded extracted evidence')
 assert b.state=='extracted' and len(b.commercial_result_ids)==1;cr.rollback()
race(8,lambda s,n:get_batch(s,n).current_commercial_context_id.with_user(mid).action_retire_context('Concurrent context retirement'),'serialization_retry')
with registry.cursor() as cr:
 s=api.Environment(cr,uid,ctx);b=get_batch(s,8)
 b.current_commercial_context_id.with_user(mid).action_retire_context('Fresh retirement retry')
 assert not b.get_commercially_valid_rows() and b.row_ids.commercial_status=='stale';cr.commit()
clock_patch.stop()
print('PR08_PROBE=PASS')
