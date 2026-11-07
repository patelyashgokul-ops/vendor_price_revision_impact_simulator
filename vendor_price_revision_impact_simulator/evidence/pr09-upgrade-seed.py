"""PR08 commercial data fixture, executed only in the disposable upgrade database."""
from pathlib import Path
import json
from odoo import Command
module='vendor_price_revision_impact_simulator'
old_probe=env['ir.config_parameter'].get_str(module+'.pr08_upgrade_probe')
if old_probe:
    old=json.loads(old_probe)
    company=env['res.company'].browse(old['company_id'])
    env=env(context=dict(env.context,allowed_company_ids=company.ids))
    product=env['product.product'].browse(old['product_id'])
    revisions=env['vendor.price.revision'].browse(old['revision_ids'])
    owners=env['res.users'].browse(old['owner_ids'])
    vendor=revisions[0].vendor_id
    supplier_price=env['product.supplierinfo'].browse(old['supplier_price_id'])
    batch=env['vendor.price.revision.import.batch'].browse(old['batch_id'])
    manager=env['vendor.price.revision.product.mapping'].browse(old['mapping_id']).verified_by
else:
    seed_company=env['res.company'].create({'name':'PR09 Preserved Company','currency_id':env.ref('base.INR').id})
    env=env(context=dict(env.context,allowed_company_ids=seed_company.ids))
    env.company.currency_id=env.ref('base.INR')
    exec((Path(r"C:\PycharmProjects\odoo20\custom_addons\vendor_price_revision_impact_simulator\tests\upgrade\seed_pr07.py")).read_text())
# Existing operational records are prepared under PR08 code, before the update.
unit=env.ref('uom.product_uom_unit')
product.write({'is_storable':True,'standard_price':70,'taxes_id':[Command.clear()],'supplier_taxes_id':[Command.clear()]})
warehouse=env['stock.warehouse'].search([('company_id','=',company.id)],limit=1)
if not warehouse:warehouse=env['stock.warehouse'].create({'name':'PR09 Preserved Warehouse','code':'P9U','company_id':company.id})
receipt=env['stock.move'].create({'company_id':company.id,'product_id':product.id,'uom_id':unit.id,'product_uom_qty':50,'price_unit':70,'location_id':env.ref('stock.stock_location_suppliers').id,'location_dest_id':warehouse.lot_stock_id.id})
receipt._action_confirm();receipt.quantity=50;receipt.picked=True;receipt._action_done()
assert receipt.state=='done' and receipt.value>0
price_list=env['product.pricelist'].create({'name':'PR09 Preserved INR','currency_id':company.currency_id.id,'company_id':company.id})
sale=env['sale.order'].create({'partner_id':vendor.id,'company_id':company.id,'warehouse_id':warehouse.id,'pricelist_id':price_list.id,'order_line':[Command.create({'product_id':product.id,'product_uom_qty':3,'product_uom_id':unit.id,'price_unit':150,'tax_ids':[Command.clear()]})]})
sale.action_confirm();assert sale.state=='sale'
purchase=env['purchase.order'].create({'partner_id':vendor.id,'company_id':company.id,'currency_id':company.currency_id.id,'picking_type_id':warehouse.in_type_id.id,'order_line':[Command.create({'product_id':product.id,'product_qty':40,'uom_id':unit.id,'price_unit':100,'tax_ids':[Command.clear()],'date_planned':'2026-11-02 08:00:00'})]})
purchase.button_confirm();assert purchase.state=='purchase'
accounts=env['account.account'].create([{'name':'PR09 Preserved Debit','code':'P9D','account_type':'asset_current','company_ids':[Command.set(company.ids)]},{'name':'PR09 Preserved Credit','code':'P9C','account_type':'liability_current','company_ids':[Command.set(company.ids)]}])
journal=env['account.journal'].create({'name':'PR09 Preserved General','code':'P9J','type':'general','company_id':company.id})
entry=env['account.move'].create({'move_type':'entry','journal_id':journal.id,'date':'2026-10-28','line_ids':[Command.create({'name':'Preserved debit','account_id':accounts[0].id,'debit':100}),Command.create({'name':'Preserved credit','account_id':accounts[1].id,'credit':100})]})
entry.action_post();assert entry.state=='posted'
batch.action_match_products()
unit=env.ref('uom.product_uom_unit')
policy=env['vendor.price.revision.config'].create({'policy_version':'PR09-preserved-commercial-policy','change_reason':'PR09 actual PR08 upgrade fixture','effective_from':'2025-01-01','effective_to':'2030-12-31',
'margin_ids':[Command.create({'scope':'company','minimum_margin_percent':20,'target_margin_percent':25,'reason':'Preserved'})],
'risk_ids':[Command.create({'name':'Preserved','risk_level':'low','currency_id':company.currency_id.id,'open_ended':True,'reason':'Preserved'})],
'approval_ids':[Command.create({'name':'Preserved','currency_id':company.currency_id.id,'open_ended':True,'reason':'Preserved','required_role_ids':[Command.set(env.ref(module+'.group_vpr_finance_manager').ids)]})]})
policy.action_publish()
supplier_price.write({'currency_id':company.currency_id.id,'uom_id':unit.id,'date_start':'2025-01-01','date_end':'2026-10-31'})
ctx=batch.action_propose_commercial_context({'uom_aliases':{'PCS':unit.id},'price_basis':'net_exclusive'},'Original supplier terms retained through PR09 upgrade')
ctx.with_user(manager).action_verify_context('Independent retained commercial verification')
batch.action_validate_commercial_prices()
assert batch.row_ids.commercial_status=='commercially_valid',str(batch.row_ids.commercial_summary)
models=['product.product','stock.quant','stock.move','stock.move.line','stock.picking','purchase.order','purchase.order.line','sale.order','sale.order.line','account.move','account.move.line','vendor.price.revision.margin.policy','vendor.price.revision.risk.rule','vendor.price.revision.approval.policy','vendor.price.revision.product.audit','vendor.price.revision.import.review.event','vendor.price.revision','vendor.price.revision.line','vendor.price.revision.evidence','vendor.price.revision.config','vendor.price.revision.config.audit','vendor.price.revision.import.batch','vendor.price.revision.import.row','vendor.price.revision.import.mapping','vendor.price.revision.import.validation.run','vendor.price.revision.import.validation.result','vendor.price.revision.import.correction','vendor.price.revision.product.policy','vendor.price.revision.product.mapping','vendor.price.revision.product.resolution','vendor.price.revision.commercial.context','vendor.price.revision.commercial.validation','product.supplierinfo']
# Retain every stored non-binary scalar/relational field on the existing records.
env.flush_all()
retained={}
for name in models:
 if name not in env:continue
 records=env[name].with_context(active_test=False).search([])
 names=[n for n,f in records._fields.items() if f.store and f.type!='binary' and n not in ('display_name',) and not f.related]
 retained[name]={'ids':records.ids,'fields':names,'values':records.read(names,load=None)}
retained['source_bytes']={'attachment_id':batch.attachment_id.id,'hex':batch.attachment_id.raw.content.hex(),'company_id':company.id,'sale_id':sale.id,'purchase_id':purchase.id,'entry_id':entry.id,'receipt_id':receipt.id,'move_value':receipt.value}
env['ir.config_parameter'].set_str(module+'.pr09_upgrade_probe',json.dumps(retained,default=str,sort_keys=True))
env.cr.commit()
print('PR09_PROBE=PASS commercial snapshot and source bytes seeded')
