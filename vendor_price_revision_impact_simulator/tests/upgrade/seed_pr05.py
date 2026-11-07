"""Run through Odoo shell on a disposable database with the PR-05 source."""
import json
from odoo import Command

module = "vendor_price_revision_impact_simulator"
company = env.company
group = env.ref(f"{module}.group_vendor_price_revision_user")
owners = env["res.users"].with_context(no_reset_password=True).create([
    {
        "name": f"PR03 Upgrade Owner {number}",
        "login": f"pr03.upgrade.owner{number}@example.invalid",
        "company_id": company.id, "company_ids": [Command.set(company.ids)],
        "group_ids": [Command.set(group.ids)],
    }
    for number in (1, 2)
])
vendor = env["res.partner"].create({"name": "PR03-UPGRADE-SENTINEL"})
product = env["product.product"].create({"name": "PR03 Upgrade Preserved Product"})
revisions = env["vendor.price.revision"].create([
    {"vendor_id": vendor.id, "owner_id": owner.id, "notes": "Original PR05 notes"}
    for owner in owners
])
from odoo.exceptions import AccessError
try:
    revisions[1].with_user(owners[0]).with_context(allowed_company_ids=company.ids).check_access("write")
except AccessError:
    pass
else:
    raise AssertionError("PR03 least privilege missing before upgrade")
line = env["vendor.price.revision.line"].create({
    "revision_id": revisions[0].id, "product_id": product.id,
    "proposed_price": 109.25, "vendor_product_code": "PRESERVED-CODE",
})
evidence = env["vendor.price.revision.evidence"].create({
    "revision_id": revisions[0].id, "name": "Preserved PR02 evidence",
    "source_reference": "PRESERVED-REFERENCE",
})
supplier_price = env["product.supplierinfo"].create({
    "partner_id": vendor.id, "product_tmpl_id": product.product_tmpl_id.id,
    "company_id": company.id, "price": 70.75,
})
snapshot = {
    "revision_ids": revisions.ids, "names": revisions.mapped("name"),
    "owner_ids": owners.ids, "company_id": company.id,
    "line_id": line.id, "evidence_id": evidence.id,
    "supplier_price_id": supplier_price.id,
    "revision_write_dates": [str(r.write_date) for r in revisions],
    "line_write_date": str(line.write_date), "evidence_write_date": str(evidence.write_date),
    "supplier_price_write_date": str(supplier_price.write_date),
}
env["ir.config_parameter"].set_str(f"{module}.pr06_upgrade_probe", json.dumps(snapshot))
from odoo import fields
config = env['vendor.price.revision.config'].create({
    'policy_version': 'PR04-preserved-version', 'change_reason': 'PR05 upgrade fixture',
    'effective_from': '2099-01-01', 'effective_to': '2099-12-31',
    'margin_ids': [Command.create({'scope': 'company', 'minimum_margin_percent': 20,
        'target_margin_percent': 25, 'reason': 'Preserved margin'})],
    'risk_ids': [Command.create({'name': 'Preserved scale', 'risk_level': 'low',
        'currency_id': company.currency_id.id, 'open_ended': True, 'reason': 'Preserved risk'})],
    'approval_ids': [Command.create({'name': 'Preserved finance requirement', 'open_ended': True,
        'currency_id': company.currency_id.id, 'reason': 'Preserved approval definition',
        'required_role_ids': [Command.set(env.ref(f'{module}.group_vpr_finance_manager').ids)]})],
})
config.action_publish()
snapshot['config_id'] = config.id
snapshot['config_write_date'] = str(config.write_date)
snapshot['margin_id'] = config.margin_ids.id
snapshot['audit_ids'] = config.audit_ids.ids
env['ir.config_parameter'].set_str(f'{module}.pr06_upgrade_probe', json.dumps(snapshot))
from odoo.tools.binary import BinaryBytes
source_bytes = b'Code,Price,Currency,UoM,MOQ,Date\n000123,115,INR,PCS,1,2026-11-01\n'
wizard = env['vendor.price.revision.import.wizard'].with_user(owners[0]).create({
    'company_id': company.id, 'revision_id': revisions[0].id,
    'upload_file': BinaryBytes(source_bytes), 'upload_filename': 'preserved-pr05.csv',
})
wizard.action_upload_extract()
batch = wizard.result_batch_id
assert batch.state == 'extracted' and len(batch.row_ids) == 1
snapshot['batch_id'] = batch.id
snapshot['batch_write_date'] = str(batch.write_date)
snapshot['sha256_digest'] = batch.sha256_digest
snapshot['raw_row_ids'] = batch.row_ids.ids
snapshot['raw_cells'] = batch.row_ids.raw_cells
snapshot['raw_row_write_dates'] = [str(row.write_date) for row in batch.row_ids]
snapshot['source_evidence_id'] = batch.evidence_id.id
snapshot['attachment_id'] = batch.attachment_id.id
snapshot['source_hex'] = source_bytes.hex()
snapshot['attempt_ids'] = batch.attempt_ids.ids
env['ir.config_parameter'].set_str(f'{module}.pr06_upgrade_probe', json.dumps(snapshot))
env.cr.commit()
print("PR06_PROBE=PASS " + json.dumps(snapshot, sort_keys=True))
