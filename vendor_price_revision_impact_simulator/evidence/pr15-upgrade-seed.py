"""PR08 commercial data fixture, executed only in the disposable upgrade database."""
from pathlib import Path
import json
from odoo import Command
assert env.cr.dbname.startswith('codex_vpr_pr15_')
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
    seed_company=env['res.company'].create({'name':'PR15 Preserved Company','currency_id':env.ref('base.INR').id})
    env=env(context=dict(env.context,allowed_company_ids=seed_company.ids))
    env.company.currency_id=env.ref('base.INR')
    exec((Path(r"C:\PycharmProjects\odoo20\custom_addons\vendor_price_revision_impact_simulator\tests\upgrade\seed_pr07.py")).read_text())
# Existing operational records are prepared under PR08 code, before the update.
unit=env.ref('uom.product_uom_unit')
product.write({'is_storable':True,'standard_price':70,'taxes_id':[Command.clear()],'supplier_taxes_id':[Command.clear()]})
warehouse=env['stock.warehouse'].search([('company_id','=',company.id)],limit=1)
if not warehouse:warehouse=env['stock.warehouse'].create({'name':'PR15 Preserved Warehouse','code':'P9U','company_id':company.id})
receipt=env['stock.move'].create({'company_id':company.id,'product_id':product.id,'uom_id':unit.id,'product_uom_qty':50,'price_unit':70,'location_id':env.ref('stock.stock_location_suppliers').id,'location_dest_id':warehouse.lot_stock_id.id})
receipt._action_confirm();receipt.quantity=50;receipt.picked=True;receipt._action_done()
assert receipt.state=='done' and receipt.value>0
price_list=env['product.pricelist'].create({'name':'PR15 Preserved INR','currency_id':company.currency_id.id,'company_id':company.id})
sale=env['sale.order'].create({'partner_id':vendor.id,'company_id':company.id,'warehouse_id':warehouse.id,'pricelist_id':price_list.id,'order_line':[Command.create({'product_id':product.id,'product_uom_qty':3,'product_uom_id':unit.id,'price_unit':150,'tax_ids':[Command.clear()]})]})
sale.action_confirm();assert sale.state=='sale'
purchase=env['purchase.order'].create({'partner_id':vendor.id,'company_id':company.id,'currency_id':company.currency_id.id,'picking_type_id':warehouse.in_type_id.id,'order_line':[Command.create({'product_id':product.id,'product_qty':40,'uom_id':unit.id,'price_unit':100,'tax_ids':[Command.clear()],'date_planned':'2026-11-02 08:00:00'})]})
purchase.button_confirm();assert purchase.state=='purchase'
accounts=env['account.account'].create([{'name':'PR15 Preserved Debit','code':'P9D','account_type':'asset_current','company_ids':[Command.set(company.ids)]},{'name':'PR15 Preserved Credit','code':'P9C','account_type':'liability_current','company_ids':[Command.set(company.ids)]}])
journal=env['account.journal'].create({'name':'PR15 Preserved General','code':'P9J','type':'general','company_id':company.id})
entry=env['account.move'].create({'move_type':'entry','journal_id':journal.id,'date':'2026-10-28','line_ids':[Command.create({'name':'Preserved debit','account_id':accounts[0].id,'debit':100}),Command.create({'name':'Preserved credit','account_id':accounts[1].id,'credit':100})]})
entry.action_post();assert entry.state=='posted'
batch.action_match_products()
unit=env.ref('uom.product_uom_unit')
policy=env['vendor.price.revision.config'].create({'policy_version':'PR15-preserved-commercial-policy','change_reason':'PR15 actual PR08 upgrade fixture','effective_from':'2025-01-01','effective_to':'2030-12-31',
'margin_ids':[Command.create({'scope':'company','minimum_margin_percent':20,'target_margin_percent':25,'reason':'Preserved'})],
'risk_ids':[Command.create({'name':'Preserved','risk_level':'low','currency_id':company.currency_id.id,'open_ended':True,'reason':'Preserved'})],
'approval_ids':[Command.create({'name':'Preserved','currency_id':company.currency_id.id,'open_ended':True,'reason':'Preserved','required_role_ids':[Command.set(env.ref(module+'.group_vpr_finance_manager').ids)]})]})
policy.action_publish()
supplier_price.write({'currency_id':company.currency_id.id,'uom_id':unit.id,'date_start':'2025-01-01','date_end':'2026-10-31'})
ctx=batch.action_propose_commercial_context({'uom_aliases':{'PCS':unit.id},'price_basis':'net_exclusive'},'Original supplier terms retained through PR15 upgrade')
ctx.with_user(manager).action_verify_context('Independent retained commercial verification')
batch.action_validate_commercial_prices()
assert batch.row_ids.commercial_status=='commercially_valid',str(batch.row_ids.commercial_summary)
models=['product.product','stock.quant','stock.move','stock.move.line','stock.picking','purchase.order','purchase.order.line','sale.order','sale.order.line','account.move','account.move.line','vendor.price.revision.margin.policy','vendor.price.revision.risk.rule','vendor.price.revision.approval.policy','vendor.price.revision.product.audit','vendor.price.revision.import.review.event','vendor.price.revision','vendor.price.revision.line','vendor.price.revision.evidence','vendor.price.revision.config','vendor.price.revision.config.audit','vendor.price.revision.import.batch','vendor.price.revision.import.row','vendor.price.revision.import.mapping','vendor.price.revision.import.validation.run','vendor.price.revision.import.validation.result','vendor.price.revision.import.correction','vendor.price.revision.product.policy','vendor.price.revision.product.mapping','vendor.price.revision.product.resolution','vendor.price.revision.commercial.context','vendor.price.revision.commercial.validation','product.supplierinfo']
# Retain every stored non-binary scalar/relational field on the existing records.
env.flush_all()
# Actual PR09 supply evidence exists before PR15 code is installed.
from odoo.addons.vendor_price_revision_impact_simulator.models.supply_governance import GRANT,LOCATION
for person in (owners|manager):
 env[GRANT].create({'company_id':company.id,'user_id':person.id,'warehouse_ids':[Command.set(warehouse.ids)],'allow_cost':True,'allow_demand':True,'reason':'PR10 preserved analytical supply grant'})
env[LOCATION].create({'company_id':company.id,'warehouse_id':warehouse.id,'location_id':warehouse.lot_stock_id.id,'classification':'saleable','reason':'PR09 preserved exact stock classification'})
supply=batch.action_collect_supply(warehouse.ids)
assert supply.exists() and supply.bucket_ids
models+=['vendor.price.revision.supply.snapshot','vendor.price.revision.supply.bucket','vendor.price.revision.supply.issue','vendor.price.revision.supply.terms','vendor.price.revision.supply.grant','vendor.price.revision.supply.location','vendor.price.revision.supply.governance.audit']
allocation=batch.action_run_allocation(warehouse.ids)
assert allocation.demand_ids and allocation.entry_ids
models += ['vendor.price.revision.allocation.snapshot','vendor.price.revision.allocation.demand','vendor.price.revision.allocation.entry','vendor.price.revision.allocation.issue','vendor.price.revision.allocation.policy','product.pricelist','product.pricelist.item','res.currency.rate']
# PR11 customer commercial evidence exists before PR15 schema registration.
from odoo.addons.vendor_price_revision_impact_simulator.models.sales_exposure import GRANT as SALES_GRANT
for person in owners|manager:
 person.write({'group_ids':[Command.link(env.ref(module+'.group_vpr_sales_manager').id),Command.link(env.ref('sales_team.group_sale_salesman_all_leads').id)]})
 env[SALES_GRANT].create({'company_id':company.id,'user_id':person.id,'warehouse_ids':[Command.set(warehouse.ids)],'reason':'Explicit preserved customer commercial scope'})
commercial=allocation.action_collect_sales_terms()
assert commercial.line_ids
review=commercial.line_ids.action_review_price_protection('fixed_price_verified','Preserved customer signed terms','Documented exact customer terms')
commercial=allocation.action_collect_sales_terms()
assert commercial.line_ids.price_protection=='fixed_price_verified'
models += ['vendor.price.revision.sales.snapshot','vendor.price.revision.sales.line','vendor.price.revision.sales.issue','vendor.price.revision.sales.review','vendor.price.revision.sales.grant']
# PR12 purchase snapshot and independently verified source assessment exist
# before the PR15 cost schema is registered.
purchase_snapshot=batch.action_collect_purchase_terms(warehouse.ids,True,allocation.id,False)
assert purchase_snapshot.line_ids
purchase_review=purchase_snapshot.line_ids.action_propose_evidence('fixed','Retained supplier signed terms','Exact PR12 terms preserved')
purchase_review.with_user(manager).action_verify('Independent preserved supplier terms checked')
purchase_snapshot=batch.action_collect_purchase_terms(warehouse.ids,True,allocation.id,False)
assert purchase_snapshot.line_ids.protection_status=='protected_verified'
models += ['vendor.price.revision.purchase.snapshot','vendor.price.revision.purchase.line','vendor.price.revision.purchase.issue','vendor.price.revision.purchase.evidence','product.value']
# A real PR13 cost attribution exists before the PR15 schema is registered.
cost_snapshot=batch.action_attribute_costs(allocation.id,purchase_snapshot.id,'2026-11-05')
assert cost_snapshot.line_ids
models += ['vendor.price.revision.cost.snapshot','vendor.price.revision.cost.line','vendor.price.revision.cost.issue']
financial_snapshot=batch.action_calculate_financial_exposure(cost_snapshot.id,commercial.id)
assert financial_snapshot.line_ids
models += ['vendor.price.revision.financial.snapshot','vendor.price.revision.financial.line','vendor.price.revision.financial.issue']

env.flush_all()
retained={}
for name in models:
 if name not in env:continue
 records=env[name].with_context(active_test=False).search([])
 names=[n for n,f in records._fields.items() if f.store and f.type!='binary' and n not in ('display_name',) and not f.related]
 retained[name]={'ids':records.ids,'fields':names,'values':records.read(names,load=None)}
retained['source_bytes']={'attachment_id':batch.attachment_id.id,'hex':batch.attachment_id.raw.content.hex(),'company_id':company.id,'sale_id':sale.id,'purchase_id':purchase.id,'entry_id':entry.id,'receipt_id':receipt.id,'move_value':receipt.value,'supply_id':supply.id,'supply_digest':supply.input_digest}
env['ir.config_parameter'].set_str(module+'.pr15_upgrade_probe',json.dumps(retained,default=str,sort_keys=True))
env.cr.commit()
print('PR15_PROBE=PASS commercial snapshot and source bytes seeded')
