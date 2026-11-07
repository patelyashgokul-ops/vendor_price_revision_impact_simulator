"""Read-only preservation/permission assertions after the actual PR-07 to PR-08 upgrade."""
import json
from odoo.exceptions import AccessError

module = "vendor_price_revision_impact_simulator"
snapshot = json.loads(env["ir.config_parameter"].get_str(f"{module}.pr08_upgrade_probe"))
revisions = env["vendor.price.revision"].browse(snapshot["revision_ids"])
assert len(revisions.exists()) == 2
assert revisions.mapped("name") == snapshot["names"]
assert revisions.mapped("owner_id").ids == snapshot["owner_ids"]
assert revisions.mapped("company_id").ids == [snapshot["company_id"]]
assert revisions.mapped("notes") == ["Original PR05 notes", "Original PR05 notes"]
assert [str(r.write_date) for r in revisions] == snapshot["revision_write_dates"]
line = env["vendor.price.revision.line"].browse(snapshot["line_id"])
evidence = env["vendor.price.revision.evidence"].browse(snapshot["evidence_id"])
assert line.revision_id == revisions[0] and line.proposed_price == 109.25
assert line.vendor_product_code == "PRESERVED-CODE"
assert evidence.revision_id == revisions[0] and evidence.source_reference == "PRESERVED-REFERENCE"
assert str(line.write_date) == snapshot["line_write_date"]
assert str(evidence.write_date) == snapshot["evidence_write_date"]
supplier_price = env["product.supplierinfo"].browse(snapshot["supplier_price_id"])
assert supplier_price.price == 70.75
assert str(supplier_price.write_date) == snapshot["supplier_price_write_date"]
user = env["res.users"].browse(snapshot["owner_ids"][0])
assert user.has_group(f"{module}.group_vendor_price_revision_user")
assert not user.has_group(f"{module}.group_vpr_purchase_manager")
owned = revisions[0].with_user(user).with_context(allowed_company_ids=[snapshot["company_id"]])
owned.check_access("write")
try:
    revisions[1].with_env(owned.env).check_access("write")
except AccessError:
    pass
else:
    raise AssertionError("Legacy Purchase User retained broad draft editing")
access = env.ref(f"{module}.access_vendor_price_revision_user")
assert access.operation == "r" and "owner_id" in access.domain
assert env.ref(f"{module}.rule_vendor_price_revision_company").group_id.id is False
assert env["ir.ui.menu"].search_count([("id", "=", env.ref(f"{module}.menu_vendor_price_simulator_root").id)]) == 1
assert env["ir.sequence"].search_count([("code", "=", "vendor.price.revision")]) == 1
print("LEGACY_GROUP_LEAST_PRIVILEGE=PASS")
print("UNCHANGED_VENDOR_PRICE=PASS")
config = env['vendor.price.revision.config'].browse(snapshot['config_id'])
assert config.state == 'published' and config.policy_version == 'PR04-preserved-version'
assert str(config.write_date) == snapshot['config_write_date']
assert config.margin_ids.id == snapshot['margin_id']
assert config.margin_ids.minimum_margin_percent == 20
assert config.margin_ids.target_margin_percent == 25
assert sorted(config.audit_ids.ids) == sorted(snapshot['audit_ids'])
batch = env['vendor.price.revision.import.batch'].browse(snapshot['batch_id'])
assert batch.state == 'extracted'
assert str(batch.write_date) == snapshot['batch_write_date']
assert batch.sha256_digest == snapshot['sha256_digest']
assert batch.row_ids.ids == snapshot['raw_row_ids']
assert batch.row_ids.raw_cells == snapshot['raw_cells']
assert [str(row.write_date) for row in batch.row_ids] == snapshot['raw_row_write_dates']
assert batch.evidence_id.id == snapshot['source_evidence_id']
assert batch.attachment_id.id == snapshot['attachment_id']
assert batch.attachment_id.raw.content.hex() == snapshot['source_hex']
assert batch.attempt_ids.ids == snapshot['attempt_ids']
assert batch.mapping_ids.ids == snapshot['mapping_ids']
assert batch.validation_run_ids.ids == snapshot['run_ids']
assert batch.correction_ids.ids == snapshot['correction_ids']
assert batch.current_run_id.id == snapshot['current_run_id']
assert batch.row_ids.current_result_id.id == snapshot['current_result_id']
assert batch.row_ids.effective_values == snapshot['effective_values']
assert batch.review_event_ids.ids == snapshot['event_ids']
assert batch.row_ids.validation_status == 'structurally_ready'
assert batch.ready_rows == 1 and batch.pending_rows == 0
assert batch.row_ids.product_match_status=='manual_matched'
assert batch.row_ids.product_resolution_id.id==snapshot['product_resolution_id']
resolution=batch.row_ids.product_resolution_id
resolution_values=resolution.read(['identity','input_digest','status','source','product_snapshot','original_identifier','effective_identifier','mapping_id'])[0]
assert json.loads(json.dumps(resolution_values,default=str))==snapshot['product_resolution_values']
mapping=env['vendor.price.revision.product.mapping'].browse(snapshot['mapping_id'])
values=mapping.read(['state','source_context','product_evidence','reference_digest','verified_by','verified_at','verification_reason'])[0]
# JSON timestamps were serialized as ISO-compatible strings by the seed.
assert json.loads(json.dumps(values,default=str))==snapshot['mapping_values']
assert str(mapping.write_date)==snapshot['mapping_write_date']
identity_policy=env['vendor.price.revision.product.policy'].browse(snapshot['identity_policy_id'])
assert identity_policy.version==snapshot['identity_policy_version']
assert str(identity_policy.write_date)==snapshot['identity_policy_write_date']
assert identity_policy.audit_ids.ids==snapshot['identity_audit_ids']
assert str(env['product.product'].browse(snapshot['product_id']).write_date)==snapshot['product_write_date']
assert not batch.commercial_context_ids and not batch.commercial_result_ids
assert batch.row_ids.commercial_status=='pending_validation'
assert env['ir.ui.menu'].search_count([('id','=',env.ref(f'{module}.menu_vendor_price_simulator_root').id)])==1
try:
    batch.attachment_id.with_user(env.ref('base.public_user'))._can_return_content('raw')
except AccessError:
    pass
else:
    raise AssertionError('Source evidence became public')
assert env.ref(f'{module}.menu_import_batches').action.res_model == 'vendor.price.revision.import.batch'
assert not evidence.attachment_id and not evidence.sha256_digest
assert env.ref(f'{module}.menu_vpr_business_settings').action.res_model == 'vendor.price.revision.config'
assert not user.has_group(f'{module}.group_vpr_configuration_admin')
env.cr.rollback()
print("PR08_PROBE=PASS")
