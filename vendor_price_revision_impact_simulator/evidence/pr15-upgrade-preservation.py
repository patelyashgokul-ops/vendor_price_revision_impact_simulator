"""Read-only PR10 to PR15 preservation checks on the disposable upgrade DB."""
import json
assert env.cr.dbname.startswith('codex_vpr_pr15_')
module='vendor_price_revision_impact_simulator'
retained=json.loads(env['ir.config_parameter'].get_str(module+'.pr15_upgrade_probe'))
env=env(context=dict(env.context,allowed_company_ids=[retained['source_bytes']['company_id']]))
for name, evidence in retained.items():
 if name=='source_bytes':continue
 records=env[name].with_context(active_test=False).browse(evidence['ids'])
 assert records.exists().ids==evidence['ids'],name+' missing records'
 # Stored related-company fields were not part of the generic scalar capture.
 # Their expected company is independently known from the pre-upgrade fixture.
 company_scoped=name.startswith('vendor.price.revision') or name in ('stock.quant','stock.move','stock.move.line','stock.picking','sale.order','sale.order.line','purchase.order','purchase.order.line','account.move','account.move.line')
 if records and company_scoped and 'company_id' in records._fields:
  assert records.company_id.ids==[retained['source_bytes']['company_id']],name+' company ownership changed'
 actual=json.loads(json.dumps(records.read(evidence['fields'],load=None),default=str,sort_keys=True))
 # Relational membership is unordered; cached insertion order can differ from
 # a fresh registry's native date/id order. Every related record's stored
 # business values and source row ordinals are still compared independently.
 relation_fields=[n for n in evidence['fields'] if records._fields[n].type in ('one2many','many2many')]
 for values in (actual,evidence['values']):
  for row in values:
   for key in relation_fields:row[key]=sorted(row[key])
 if actual!=evidence['values']:
  expected={v['id']:v for v in evidence['values']}
  for value in actual:
   for key,new in value.items():
    old=expected[value['id']].get(key)
    if new!=old:print('PRESERVATION_DIFFERENCE '+name+' id='+str(value['id'])+' field='+key+' before='+repr(old)+' after='+repr(new))
 assert actual==evidence['values'],name+' changed retained evidence'
source=retained['source_bytes']
assert env['ir.attachment'].browse(source['attachment_id']).raw.content.hex()==source['hex']
assert env['sale.order'].browse(source['sale_id']).state=='sale'
assert env['purchase.order'].browse(source['purchase_id']).state=='purchase'
assert env['account.move'].browse(source['entry_id']).state=='posted'
assert env['stock.move'].browse(source['receipt_id']).value==source['move_value']
assert env['vendor.price.revision.supply.snapshot'].browse(source['supply_id']).input_digest==source['supply_digest']
assert not env['vendor.price.revision.margin.snapshot'].search_count([])
assert env['vendor.price.revision.financial.snapshot'].search_count([])>0
assert env['vendor.price.revision.financial.line'].search_count([])>0
assert env['vendor.price.revision.cost.snapshot'].search_count([])>0
assert env['vendor.price.revision.cost.line'].search_count([])>0
assert env['vendor.price.revision.purchase.snapshot'].search_count([])>0
assert env['vendor.price.revision.purchase.evidence'].search_count([])>0
assert env['vendor.price.revision.sales.snapshot'].search_count([])>0
assert env['ir.module.module'].search([('name','=','sale_stock')]).state=='installed'
assert env['ir.module.module'].search([('name','=','purchase_stock')]).state=='installed'
assert env['ir.ui.menu'].search_count([('id','=',env.ref(module+'.menu_vendor_price_simulator_root').id)])==1
batch=env['vendor.price.revision.import.batch'].browse(retained['vendor.price.revision.import.batch']['ids'])
assert batch.with_company(batch.company_id).row_ids.commercial_status=='commercially_valid'
assert env['vendor.price.revision.allocation.snapshot'].browse(retained['vendor.price.revision.allocation.snapshot']['ids']).exists()
print('PR15_PRESERVED_MODELS='+str(len(retained)-1))
print('PR15_PRESERVED_ALLOCATIONS='+str(len(retained['vendor.price.revision.allocation.snapshot']['ids'])))
env.cr.rollback()
print('PR15_PROBE=PASS all prior records/source bytes/commercial snapshots preserved; existing PR09 supply evidence retained; existing PR11 sales evidence retained; PR12 purchase references preserved; PR13 cost references preserved; zero automatic profitability snapshots')
