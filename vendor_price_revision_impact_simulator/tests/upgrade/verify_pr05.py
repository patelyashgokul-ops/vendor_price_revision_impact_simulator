"""Read-only preservation/permission assertions after the actual PR-04 upgrade."""
import json
from odoo.exceptions import AccessError

module = "vendor_price_revision_impact_simulator"
snapshot = json.loads(env["ir.config_parameter"].get_str(f"{module}.pr05_upgrade_probe"))
revisions = env["vendor.price.revision"].browse(snapshot["revision_ids"])
assert len(revisions.exists()) == 2
assert revisions.mapped("name") == snapshot["names"]
assert revisions.mapped("owner_id").ids == snapshot["owner_ids"]
assert revisions.mapped("company_id").ids == [snapshot["company_id"]]
assert revisions.mapped("notes") == ["Original PR04 notes", "Original PR04 notes"]
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
assert not env['vendor.price.revision.import.batch'].search([])
assert env.ref(f'{module}.menu_import_batches').action.res_model == 'vendor.price.revision.import.batch'
assert not evidence.attachment_id and not evidence.sha256_digest
assert env.ref(f'{module}.menu_vpr_business_settings').action.res_model == 'vendor.price.revision.config'
assert not user.has_group(f'{module}.group_vpr_configuration_admin')
env.cr.rollback()
print("PR05_PROBE=PASS")
