"""Read-only PR08 to PR09 preservation checks on the disposable upgrade DB."""
import json
module='vendor_price_revision_impact_simulator'
retained=json.loads(env['ir.config_parameter'].get_str(module+'.pr09_upgrade_probe'))
env=env(context=dict(env.context,allowed_company_ids=[retained['source_bytes']['company_id']]))
for name, evidence in retained.items():
 if name=='source_bytes':continue
 records=env[name].with_context(active_test=False).browse(evidence['ids'])
 assert records.exists().ids==evidence['ids'],name+' missing records'
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
assert not env['vendor.price.revision.supply.snapshot'].search_count([])
assert env['ir.module.module'].search([('name','=','purchase_stock')]).state=='installed'
assert env['ir.ui.menu'].search_count([('id','=',env.ref(module+'.menu_vendor_price_simulator_root').id)])==1
batch=env['vendor.price.revision.import.batch'].search([])
assert batch.with_company(batch.company_id).row_ids.commercial_status=='commercially_valid'
env.cr.rollback()
print('PR09_PROBE=PASS all prior records/source bytes/commercial snapshots preserved; zero supply snapshots')
