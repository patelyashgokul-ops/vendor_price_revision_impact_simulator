"""Real two-session PR12 races, only committed synthetic disposable fixtures."""
import threading
import time
from datetime import date
from unittest.mock import patch
from psycopg2.errors import SerializationFailure
from odoo import Command, api, fields
from odoo.exceptions import UserError
from odoo.tools.binary import BinaryBytes

assert env.cr.dbname.startswith('codex_vpr_pr12_')
clock_patch=patch.object(fields.Date,'context_today',return_value=date(2026,10,28));clock_patch.start()
module='vendor_price_revision_impact_simulator'
company=env['res.company'].with_context(install_demo=True).create({'name':'PR12 Races '+str(time.time_ns()),'currency_id':env.ref('base.INR').id})
ctx={'allowed_company_ids':company.ids}
users=env['res.users'].with_context(no_reset_password=True).create([
 {'name':'PR12 Race '+role,'login':role+str(time.time_ns())+'@example.invalid','company_id':company.id,'company_ids':[Command.set(company.ids)],'group_ids':[Command.set(env.ref(module+'.'+group).ids)]}
 for role,group in [('preparer','group_vendor_price_revision_user'),('manager','group_vpr_purchase_manager')]])
preparer,manager=users
vendor=env['res.partner'].create({'name':'PR12 Race Vendor'})
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
labels=['OPERATIONS']
for n,label in enumerate(labels):
 product=env['product.product'].create({'name':'PR12 Race '+label,'default_code':f'RACE-{company.id}-{n}','company_id':company.id})
 box=env['uom.uom'].create({'name':f'PR12 Race Box10 {company.id}-{n}','relative_uom_id':unit.id,'relative_factor':10})
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


# All document/master mutations below are synthetic fixture preparation only.
ops=api.Environment(env.cr,env.uid,dict(ctx,tracking_disable=True,mail_create_nosubscribe=True,mail_notrack=True))
assert all(model in ops for model in ('purchase.order','sale.order','stock.move','stock.quant','account.move'))
product=ops['product.product'].browse(products[0])
product.write({'is_storable':True,'standard_price':70,'list_price':150,'taxes_id':[Command.clear()],'supplier_taxes_id':[Command.clear()]})
warehouse=ops['stock.warehouse'].search([('company_id','=',company_id)],limit=1)
if not warehouse:warehouse=ops['stock.warehouse'].create({'name':'PR12 Operational Warehouse','code':'P8W','company_id':company_id})
receipt=ops['stock.move'].create({'product_id':product.id,'product_uom_qty':50,'uom_id':unit_id,'location_id':ops.ref('stock.stock_location_suppliers').id,'location_dest_id':warehouse.lot_stock_id.id,'company_id':company_id,'price_unit':70})
receipt._action_confirm();receipt._action_assign();receipt.quantity=50;receipt.picked=True;receipt._action_done()
assert receipt.state=='done' and receipt.value>0
package_model=ops['stock.quant']._fields['package_id'].comodel_name
package=ops[package_model].create({'name':'PR12 Retained Package'})
owned_quant=ops['stock.quant'].search([('product_id','=',product.id),('location_id','=',warehouse.lot_stock_id.id),('quantity','>',0)])
owned_quant.write({'package_id':package.id})
pricelist=ops['product.pricelist'].create({'name':'PR12 Operational INR','currency_id':company.currency_id.id,'company_id':company_id})
sale=ops['sale.order'].create({'partner_id':vendor.id,'company_id':company_id,'warehouse_id':warehouse.id,'pricelist_id':pricelist.id,'commitment_date':'2026-11-05 10:00:00','order_line':[Command.create({'product_id':product.id,'product_uom_qty':.3,'product_uom_id':boxes[0],'price_unit':150,'tax_ids':[Command.clear()]})]})
sale.action_confirm();assert sale.state=='sale'
purchase=ops['purchase.order'].create({'partner_id':vendor.id,'company_id':company_id,'currency_id':company.currency_id.id,'order_line':[Command.create({'product_id':product.id,'product_qty':4,'uom_id':unit_id,'price_unit':100,'name':'PR12 Existing commitment','date_planned':'2026-11-01 00:00:00','tax_ids':[Command.clear()]})]})
purchase.button_confirm();assert purchase.state=='purchase'
accounts=ops['account.account'].create([{'name':'PR12 Fixture Debit','code':'P8D','account_type':'asset_current','company_ids':[Command.set([company_id])]}, {'name':'PR12 Fixture Credit','code':'P8C','account_type':'liability_current','company_ids':[Command.set([company_id])]}])
journal=ops['account.journal'].create({'name':'PR12 Fixture General','code':'P8J','type':'general','company_id':company_id})
entry=ops['account.move'].create({'move_type':'entry','journal_id':journal.id,'date':'2026-10-28','line_ids':[Command.create({'name':'PR12 Debit','account_id':accounts[0].id,'debit':100,'credit':0}),Command.create({'name':'PR12 Credit','account_id':accounts[1].id,'debit':0,'credit':100})]})
entry.action_post();assert entry.state=='posted'
assert ops['stock.quant'].search_count([('product_id','=',product.id),('quantity','>',0)])>0
batch=ops['vendor.price.revision.import.batch'].browse(batch_ids[0]).with_user(uid)
# Master setup may change identity evidence; explicitly refresh upstream gates.
batch.action_validate_structure();batch.action_match_products()
interpretation=batch.action_propose_commercial_context({'uom_aliases':{'BOX':boxes[0]},'price_basis':'net_exclusive'},'Operational safety comparison context')
interpretation.with_user(mid).action_verify_context('Independent operational reference review')
from odoo.addons.vendor_price_revision_impact_simulator.models.supply_governance import GRANT,LOCATION
for user in users:
 ops[GRANT].create({'company_id':company_id,'user_id':user.id,'warehouse_ids':[Command.set(warehouse.ids)],'allow_cost':True,'allow_demand':True,'reason':'Explicit operational safety analytical scope'})
ops[LOCATION].create({'company_id':company_id,'warehouse_id':warehouse.id,'location_id':warehouse.lot_stock_id.id,'classification':'saleable','reason':'Verified saleable operational fixture location'})
batch.action_validate_commercial_prices()
assert batch.row_ids.commercial_status=='commercially_valid'

models={
 'product.supplierinfo':['price','discount','currency_id','uom_id','min_qty','date_start','date_end','write_date'],
 'product.product':['standard_price','list_price','uom_id','write_date'],
 'purchase.order':['state','write_date'], 'purchase.order.line':['price_unit','product_qty','uom_id','write_date'],
 'sale.order':['state','write_date'], 'sale.order.line':['price_unit','product_uom_qty','product_uom_id','write_date'],
 'stock.quant':['quantity','reserved_quantity','write_date'],
 'stock.move.line':['move_id','quantity','quantity_product_uom','state','lot_id','package_id','owner_id','write_date'],
 'stock.picking':['state','location_id','location_dest_id','write_date'],
 'stock.move':['state','quantity','value','price_unit','remaining_value','write_date'],
 'account.move':['state','date','write_date'],'account.move.line':['debit','credit','balance','write_date'],
 'res.currency.rate':['rate','name','write_date'],
 'mail.mail':['state','write_date'],'mail.message':['write_date'],'mail.activity':['write_date'],'ir.cron':['write_date']}
models[package_model]=['name','write_date']
if 'stock.valuation.layer' in ops:models['stock.valuation.layer']=['quantity','value','write_date']
def snapshot():
 return {name:ops[name].search([],order='id').read([field for field in names if field in ops[name]._fields]) for name,names in models.items()}
from odoo.addons.vendor_price_revision_impact_simulator.models.sales_exposure import GRANT as SALES_GRANT
users.write({'group_ids':[Command.link(ops.ref(module+'.group_vpr_sales_manager').id),Command.link(ops.ref('sales_team.group_sale_salesman_all_leads').id)]})
for user in users:
 ops[SALES_GRANT].create({'company_id':company_id,'user_id':user.id,'warehouse_ids':[Command.set(warehouse.ids)],'reason':'Explicit customer scope for PR12 safety'})
models['product.pricelist']=['currency_id','write_date']
models['product.pricelist.item']=['fixed_price','write_date']
models['sale.order.line']+=['discount','tax_ids']
before=snapshot()
supply=batch.action_collect_supply(warehouse.ids)
assert supply.quantity_verified and supply.bucket_ids
quant_buckets=supply.bucket_ids.filtered(lambda b:b.source_key.startswith('quant:'))
assert len(quant_buckets)==1 and quant_buckets.evidence['quant']['package_id']==package.id
assert float(quant_buckets.physical)==50 and float(quant_buckets.reserved)==3 and float(quant_buckets.eligible_free)==47
assert batch.get_current_supply(warehouse.ids)==supply
assert batch.action_collect_supply(warehouse.ids)==supply
terms=batch.action_propose_supply_terms(warehouse.id,purchase.order_line.id,'firm','Signed supplier commitment in synthetic fixture')
terms.with_user(mid).action_verify_terms('Independent synthetic contract check')
updated=batch.action_collect_supply(warehouse.ids)
assert updated.version==2 and updated.previous_id==supply
allocation=batch.action_run_allocation(warehouse.ids)
assert allocation.demand_ids and float(allocation.demand_ids.outstanding)==3
assert float(allocation.demand_ids.reserved)==3
assert sale.order_line.product_uom_id.id==boxes[0] and sale.order_line.product_uom_qty==.3
print('PR12_MIXED_UOM ordered_boxes=.3 box_factor=10 normalized_outstanding=3 reservation_backed=3')
assert batch.get_current_allocation(warehouse.ids)==allocation
assert batch.action_run_allocation(warehouse.ids)==allocation
commercial=allocation.action_collect_sales_terms()
assert commercial.line_ids and float(commercial.line_ids.outstanding_sales_value)==45
assert allocation.action_collect_sales_terms()==commercial
assert allocation.get_current_sales_terms()==commercial
assert commercial.line_ids.sale_line_id==sale.order_line
purchase_snapshot=batch.action_collect_purchase_terms(warehouse.ids,allocation_id=allocation.id)
assert purchase_snapshot.line_ids and float(purchase_snapshot.line_ids.open_qty)==4
assert float(purchase_snapshot.line_ids.normalized_agreed_unit_price)==100
assert batch.action_collect_purchase_terms(warehouse.ids,allocation_id=allocation.id)==purchase_snapshot
assert batch.get_current_purchase_terms(warehouse.ids,allocation_id=allocation.id)==purchase_snapshot
evidence=purchase_snapshot.line_ids.action_propose_evidence('amendment_pending','Supplier synthetic request','Not accepted by buyer','115')
evidence.with_user(mid).action_verify('Independent reference-only request review')
updated_purchase=batch.action_collect_purchase_terms(warehouse.ids,allocation_id=allocation.id)
assert updated_purchase.line_ids.amendment_status=='amendment_pending'
assert float(updated_purchase.line_ids.amendment_evidence['conditional_difference'])==60
assert snapshot()==before,'Allocation analysis modified operational/master records or counts'
assert entry.state=='posted' and sale.state=='sale' and purchase.state=='purchase'
print('PR12_OPERATIONAL_FIXTURES confirmed_SO='+str(sale.id)+' confirmed_PO='+str(purchase.id)+' posted_entry='+str(entry.id)+' valued_done_move='+str(receipt.id)+' move_value='+str(receipt.value))
print('PR12_OPERATIONAL_MODELS='+','.join(models))
print('PR12_OPERATIONAL_SVL_MODEL='+('PRESENT' if 'stock.valuation.layer' in ops else 'NOT_APPLICABLE_Odoo20_stock_move_value'))
print('PR12_OPERATIONAL_SAFETY=PASS')
print('PR12_PROBE=PASS')
env.cr.rollback();clock_patch.stop()
