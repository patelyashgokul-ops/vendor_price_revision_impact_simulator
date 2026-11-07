"""Cold-registry persisted PR09 baseline, before any PR10 schema update.

The preparation transaction can retain cached log-access values across its normal
sudo related-field computations. Compare committed storage, not those caches.
No source/evidence row is changed by this read-only capture.
"""
import json
assert env.cr.dbname.startswith('codex_vpr_pr10_upgrade_')
module='vendor_price_revision_impact_simulator'
previous=json.loads(env['ir.config_parameter'].get_str(module+'.pr10_upgrade_probe'))
assert 'vendor.price.revision.allocation.snapshot' not in env,'Capture must run with exact PR09 source'
env.cr.execute("SELECT to_regclass('vendor_price_revision_allocation_snapshot')")
assert env.cr.fetchone()[0] is None,'Cold baseline must precede creation of any PR10 schema table'
env=env(context=dict(env.context,allowed_company_ids=[previous['source_bytes']['company_id']]))
retained={}
for name,evidence in previous.items():
 if name=='source_bytes':continue
 records=env[name].with_context(active_test=False).browse(evidence['ids'])
 assert records.exists().ids==evidence['ids'],name
 values=records.read(evidence['fields'],load=None)
 expected={v['id']:v for v in evidence['values']}
 serialized=json.loads(json.dumps(values,default=str))
 for value in serialized:
  for key,new in value.items():
   old=expected[value['id']].get(key)
   if new!=old:
    # Relations can differ in iteration order, but no business value may drift.
    field=records._fields[key]
    if field.type in ('one2many','many2many') and sorted(new)==sorted(old):continue
    print('PREUPDATE_COLD_CAPTURE_DIFFERENCE model='+name+' id='+str(value['id'])+' field='+key+' cached='+repr(old)+' committed='+repr(new))
    assert key in ('write_uid','write_date'),'Unexpected business difference before upgrade: '+name+'.'+key
 retained[name]={'ids':evidence['ids'],'fields':evidence['fields'],'values':serialized}
# Independently confirm SQL matches the cold ORM log-access metadata. This is a
# read-only diagnostic, not restoration of UID/date or a repair of old evidence.
ids=previous['vendor.price.revision.supply.bucket']['ids']
env.cr.execute('SELECT id,create_uid,write_uid,write_date FROM vendor_price_revision_supply_bucket WHERE id IN %s ORDER BY id',[tuple(ids)])
for row in env.cr.fetchall():print('PR09_COMMITTED_BUCKET_METADATA='+str(row))
retained['source_bytes']=previous['source_bytes']
assert env['ir.attachment'].browse(previous['source_bytes']['attachment_id']).raw.content.hex()==previous['source_bytes']['hex']
env['ir.config_parameter'].set_str(module+'.pr10_upgrade_probe',json.dumps(retained,default=str,sort_keys=True))
env.cr.commit()
print('PR10_CAPTURE=PASS persisted cold-registry PR09 baseline recorded before PR10 update')
