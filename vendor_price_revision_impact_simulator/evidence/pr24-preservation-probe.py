"""Hash original PR23 stored business facts and verify original evidence bytes."""
import hashlib
import json
from pathlib import Path
from odoo.addons.vendor_price_revision_impact_simulator.models.import_intake import EVIDENCE

ROOT = Path(r'C:\PycharmProjects\odoo20\custom_addons\vendor_price_revision_impact_simulator')
assert env.cr.dbname == 'codex_vpr_pr24_upgrade_1_20261103'
capture = not (ROOT/'evidence/pr24-cold-pr23-preservation-v2.json').exists()
path = ROOT/'evidence/pr24-cold-pr23-preservation-v2.json'
if capture:
    names = [name for name in env.registry if (name.startswith('vendor.price.revision.') or name == 'vendor.price.revision') and not env[name]._abstract and not env[name]._transient]
    names += ['product.supplierinfo', 'sale.order', 'sale.order.line', 'purchase.order', 'purchase.order.line', 'stock.move', 'stock.move.line', 'stock.quant', 'account.move', 'account.move.line']
    baseline = {}
else:
    baseline = json.loads(path.read_text(encoding='utf-8'))
    names = baseline
for name in sorted(names):
    model = env[name].with_context(active_test=False)
    fields_list = sorted(k for k, f in model._fields.items() if f.store and f.type != 'binary' and k != '__last_update') if capture else baseline[name]['fields']
    values = model.search([], order='id').read(fields_list, load=None)
    for row in values:
        for key in fields_list:
            if model._fields[key].type in ('many2many', 'one2many'):
                row[key] = sorted(row[key])
    digest = hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()
    if capture:
        baseline[name] = dict(count=len(values), fields=fields_list, sha256=digest)
    else:
        assert len(values) == baseline[name]['count'] and digest == baseline[name]['sha256'], name+' changed'
if capture:
    path.write_text(json.dumps(baseline, indent=2)+'\n', encoding='utf-8')
total = 0
evidences = env[EVIDENCE].search([])
for evidence in evidences:
    raw = evidence.attachment_id.raw.content
    assert raw and len(raw) == evidence.file_size
    assert hashlib.sha256(raw).hexdigest() == evidence.sha256_digest
    assert hashlib.sha1(raw).hexdigest() == evidence.attachment_id.checksum
    total += len(raw)
print('PR24_PRESERVATION='+json.dumps(dict(mode='COLD_PR23_CAPTURE' if capture else 'AFTER_PR24_UPGRADE', models=len(baseline), source_files=len(evidences), source_bytes=total)), flush=True)
print('PR24_CASE ORIGINAL_STORED_BUSINESS_MODELS=PASS', flush=True)
print('PR24_CASE ORIGINAL_SOURCE_BYTES=PASS', flush=True)
print('PR24_PROBE=PASS', flush=True)
