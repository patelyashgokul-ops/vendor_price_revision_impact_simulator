"""Run through Odoo shell on a disposable database with the PR-02 source."""
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
    {"vendor_id": vendor.id, "owner_id": owner.id, "notes": "Original PR02 notes"}
    for owner in owners
])
revisions[1].with_user(owners[0]).with_context(allowed_company_ids=company.ids).check_access("write")
print("LEGACY_BROAD_WRITE_BEFORE=CONFIRMED")
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
env["ir.config_parameter"].set_str(f"{module}.pr03_upgrade_probe", json.dumps(snapshot))
env.cr.commit()
print("PR02_UPGRADE_SEED=" + json.dumps(snapshot, sort_keys=True))
