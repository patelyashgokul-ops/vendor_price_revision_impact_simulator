"""Verify all original vendor source bytes against immutable original metadata."""
import hashlib
import json
from odoo.addons.vendor_price_revision_impact_simulator.models.import_intake import EVIDENCE
assert env.cr.dbname.startswith('codex_vpr_pr23_')
sample=json.loads(env['ir.config_parameter'].get_str('app06.pr23.sample'))
old=sample['preservation'][EVIDENCE]
model=env[EVIDENCE]
originals=model.with_context(active_test=False).search([],order='id',limit=old['count'])
assert len(originals)==old['count']>0
values=json.loads(json.dumps(originals.read(old['fields'],load=None),default=str))
for row in values:
 for key in old['fields']:
  if model._fields[key].type in ('many2many','one2many'):row[key]=sorted(row[key])
assert hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()==old['sha256'],'Original source metadata changed after cold PR22 capture'
total=0
for evidence in originals:
 raw=evidence.attachment_id.raw.content
 assert raw and len(raw)==evidence.file_size,(evidence.id,'missing/truncated source')
 assert hashlib.sha256(raw).hexdigest()==evidence.sha256_digest,(evidence.id,'source digest mismatch')
 assert hashlib.sha1(raw).hexdigest()==evidence.attachment_id.checksum,(evidence.id,'native content checksum mismatch')
 total+=len(raw)
print('PR23_SOURCE_FILES='+json.dumps(dict(original_source_files=len(originals),total_verified_bytes=total,
 basis='Exact cold-PR22 source metadata hash plus each immutable SHA256, native SHA1 and nonzero file size; not an empty cloned-file baseline.')),flush=True)
print('PR23_CASE ORIGINAL_VENDOR_FILES_NONEMPTY_CHECKSUMS=PASS',flush=True)
print('PR23_CASE ORIGINAL_SOURCE_METADATA_RETAINS_COLD_BASELINE=PASS',flush=True)
print('PR23_PROBE=PASS',flush=True)
