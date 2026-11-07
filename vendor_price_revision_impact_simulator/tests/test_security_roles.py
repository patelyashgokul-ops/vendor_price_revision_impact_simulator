from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from ..models.vendor_price_revision import VendorPriceRevision


MODULE = "vendor_price_revision_impact_simulator"


@tagged("post_install", "-at_install")
class TestRevisionSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env.company
        cls.company_b = cls.env["res.company"].create({"name": "PR03 ABC UAE"})
        cls.vendor = cls.env["res.partner"].create({"name": "PR03 Shared Supplier"})
        cls.product = cls.env["product.product"].create({"name": "PR03 Shared LED Bulb"})
        cls.role_ids = {
            "purchase": "group_vendor_price_revision_user",
            "manager": "group_vpr_purchase_manager",
            "finance": "group_vpr_finance_manager",
            "sales": "group_vpr_sales_user",
            "sales_manager": "group_vpr_sales_manager",
            "pricing": "group_vpr_pricing_operator",
            "director": "group_vpr_director",
            "auditor": "group_vpr_auditor",
            "configuration": "group_vpr_configuration_admin",
        }
        cls.users = {
            role: cls._make_user(role, [role], cls.company_a)
            for role in cls.role_ids
        }
        cls.other_purchase = cls._make_user("other_purchase", ["purchase"], cls.company_a)
        cls.purchase_b = cls._make_user("purchase_b", ["purchase"], cls.company_b)
        cls.group_director = cls._make_user(
            "director_ab", ["director"], cls.company_a | cls.company_b
        )
        cls.revision_a = cls._make_revision(cls.company_a, cls.users["purchase"])
        cls.other_revision_a = cls._make_revision(cls.company_a, cls.other_purchase)
        cls.revision_b = cls._make_revision(cls.company_b, cls.purchase_b)
        cls.line_a = cls.env["vendor.price.revision.line"].create({
            "revision_id": cls.revision_a.id, "product_id": cls.product.id,
            "proposed_price": 109, "vendor_product_code": "PRIVATE-A",
        })
        cls.other_line_a = cls.env["vendor.price.revision.line"].create({
            "revision_id": cls.other_revision_a.id, "proposed_price": 210,
        })
        cls.line_b = cls.env["vendor.price.revision.line"].create({
            "revision_id": cls.revision_b.id, "product_id": cls.product.id,
            "proposed_price": 5.2, "vendor_product_code": "PRIVATE-B",
        })
        cls.evidence_a = cls.env["vendor.price.revision.evidence"].create({
            "revision_id": cls.revision_a.id, "name": "PR03 A Evidence",
            "source_reference": "PRIVATE-THREAD-A",
        })
        cls.evidence_b = cls.env["vendor.price.revision.evidence"].create({
            "revision_id": cls.revision_b.id, "name": "PR03 B Evidence",
            "source_reference": "PRIVATE-THREAD-B",
        })

    @classmethod
    def _make_user(cls, key, roles, companies):
        groups = [cls.env.ref(f"{MODULE}.{cls.role_ids[role]}").id for role in roles]
        return cls.env["res.users"].with_context(
            no_reset_password=True, mail_create_nosubscribe=True,
        ).create({
            "name": f"PR03 {key}", "login": f"pr03.{key}@example.invalid",
            "company_id": companies[0].id,
            "company_ids": [Command.set(companies.ids)],
            "group_ids": [Command.set(groups)],
        })

    @classmethod
    def _make_revision(cls, company, owner):
        return cls.env["vendor.price.revision"].with_company(company).create({
            "company_id": company.id, "vendor_id": cls.vendor.id,
            "currency_id": company.currency_id.id, "owner_id": owner.id,
        })

    def _as(self, record, user, companies=None):
        return record.with_user(user).with_context(
            allowed_company_ids=(companies or user.company_id).ids
        )

    def test_purchase_user_owns_creation_and_editing(self):
        user = self.users["purchase"]
        created = self._as(self.env["vendor.price.revision"], user).create({
            "vendor_id": self.vendor.id,
        })
        self.assertEqual(created.owner_id, user)
        self.assertEqual(created.state, "draft")
        self._as(self.revision_a, user).write({"notes": "Prepared by owner"})
        self.assertEqual(self.revision_a.notes, "Prepared by owner")
        with self.assertRaises(AccessError):
            self._as(self.other_revision_a, user).read(["name"])
        with self.assertRaises(AccessError):
            self._as(self.other_revision_a, user).write({"notes": "Not mine"})
        with self.assertRaises(AccessError):
            self._as(self.env["vendor.price.revision"], user).create({
                "vendor_id": self.vendor.id, "owner_id": self.other_purchase.id,
            })

    def test_manager_edits_company_drafts_and_reassigns_owner(self):
        manager = self.users["manager"]
        revision = self._as(self.other_revision_a, manager)
        revision.write({"notes": "Managed", "owner_id": self.users["purchase"].id})
        self.assertEqual(self.other_revision_a.owner_id, self.users["purchase"])
        self.assertEqual(self.other_revision_a.notes, "Managed")
        with self.assertRaises(ValidationError):
            revision.write({"owner_id": self.purchase_b.id})
        with self.assertRaises(AccessError):
            revision.write({"owner_id": self.users["finance"].id})

    def test_read_only_roles_read_but_cannot_mutate(self):
        for role in ("finance", "auditor", "director", "pricing"):
            with self.subTest(role=role):
                user = self.users[role]
                self.assertEqual(self._as(self.line_a, user).proposed_price, 109)
                self.assertEqual(self._as(self.evidence_a, user).source_reference, "PRIVATE-THREAD-A")
                for record in (self.revision_a, self.line_a, self.evidence_a):
                    with self.assertRaises(AccessError):
                        self._as(record, user).write({"notes": "forbidden"})
                    with self.assertRaises(AccessError):
                        self._as(record, user).unlink()
                with self.assertRaises(AccessError):
                    self._as(self.env["vendor.price.revision"], user).create({"vendor_id": self.vendor.id})
                with self.assertRaises(AccessError):
                    self._as(self.revision_a, user).copy()

    def test_sales_roles_and_configuration_have_no_raw_access(self):
        for role in ("sales", "sales_manager", "configuration"):
            with self.subTest(role=role):
                user = self.users[role]
                # Independently grant the framework's export feature so these
                # assertions reach APP model/field authorization, not its UI gate.
                user.group_ids = [Command.link(self.env.ref("base.group_allow_export").id)]
                for record in (self.revision_a, self.line_a, self.evidence_a):
                    with self.assertRaises(AccessError):
                        self._as(record, user).read()
                    with self.assertRaises(AccessError):
                        self._as(record, user).read(["id"])
                    with self.assertRaises(AccessError):
                        self._as(record, user).search_count([])
                with self.assertRaises(AccessError):
                    self._as(self.line_a, user).export_data(["proposed_price"])
                fields = self._as(self.env["vendor.price.revision.line"], user).fields_get()
                self.assertNotIn("proposed_price", fields)
                self.assertNotIn("vendor_product_code", fields)
                with self.assertRaises(AccessError):
                    self._as(self.env["vendor.price.revision.line"], user)._read_group([], [], ["__count"])

    def test_company_boundary_read_write_create_and_export(self):
        for role in ("purchase", "manager", "finance", "auditor", "director", "pricing"):
            with self.subTest(role=role):
                user = self.users[role]
                user.group_ids = [Command.link(self.env.ref("base.group_allow_export").id)]
                for record in (self.revision_b, self.line_b, self.evidence_b):
                    self.assertFalse(self._as(record, user).search([("id", "=", record.id)]))
                    with self.assertRaises(AccessError):
                        self._as(record, user).read()
                    with self.assertRaises(AccessError):
                        self._as(record, user).write({"notes": "cross company"})
                    with self.assertRaises(AccessError):
                        self._as(record, user).export_data(["id"])
                    with self.assertRaises(AccessError):
                        self._as(record, user).read(["id"])
                with self.assertRaises(AccessError):
                    self._as(self.env["vendor.price.revision"], user).create({
                        "company_id": self.company_b.id, "vendor_id": self.vendor.id,
                    })
        exported = self._as(self.revision_a, self.users["manager"]).export_data(["name"])
        self.assertEqual(exported["datas"], [[self.revision_a.name]])

    def test_company_context_and_aggregate_scope(self):
        director = self.group_director
        scoped = self._as(self.env["vendor.price.revision"], director, self.company_a)
        self.assertFalse(scoped.search([("id", "=", self.revision_b.id)]))
        both = self._as(scoped, director, self.company_a | self.company_b)
        self.assertEqual(both.search_count([("id", "in", (self.revision_a | self.revision_b).ids)]), 2)
        totals = self._as(self.env["vendor.price.revision.line"], self.users["purchase"])._read_group(
            [("id", "in", (self.line_a | self.other_line_a | self.line_b).ids)],
            ["company_id"], ["proposed_price:sum"],
        )
        self.assertEqual(totals, [(self.company_a, 109.0)])
        with self.assertRaises(AccessError):
            self._as(self.revision_b, self.users["manager"], self.company_b).read()
        preparer = self._make_user("purchase_ab", ["purchase"], self.company_a | self.company_b)
        model = self._as(self.env["vendor.price.revision"], preparer, self.company_b)
        created = model.create({"vendor_id": self.vendor.id})
        self.assertEqual(created.company_id, self.company_b)
        with self.assertRaises(AccessError):
            self._as(model, preparer, self.company_a).create({
                "company_id": self.company_b.id, "vendor_id": self.vendor.id,
            })

    def test_existing_draft_uom_integrity_uses_reference_units(self):
        compatible = self.env["uom.uom"].create({
            "name": "PR03 Pack of 12", "relative_uom_id": self.product.uom_id.id,
            "relative_factor": 12,
        })
        unrelated = self.env["uom.uom"].create({"name": "PR03 Unrelated Reference"})
        model = self._as(self.env["vendor.price.revision.line"], self.users["purchase"])
        line = model.create({
            "revision_id": self.revision_a.id, "product_id": self.product.id,
            "purchase_uom_id": compatible.id,
        })
        self.assertEqual(line.purchase_uom_id, compatible)
        with self.assertRaises(ValidationError):
            line.write({"purchase_uom_id": unrelated.id})

    def test_child_direct_and_embedded_operations_follow_parent(self):
        user = self.users["purchase"]
        for model in ("vendor.price.revision.line", "vendor.price.revision.evidence"):
            values = {"revision_id": self.other_revision_a.id}
            if model.endswith("evidence"):
                values["name"] = "forbidden"
            with self.assertRaises(AccessError):
                self._as(self.env[model], user).create(values)
        original_notes = self.revision_a.notes
        with self.assertRaises(AccessError):
            self._as(self.revision_a, user).write({
                "notes": "must not be stored",
                "line_ids": [Command.update(self.other_line_a.id, {"notes": "bypass"})],
            })
        self.assertEqual(self.revision_a.notes, original_notes)
        for command in (Command.delete(self.evidence_a.id), Command.unlink(self.evidence_a.id), Command.clear()):
            with self.assertRaises(AccessError):
                self._as(self.revision_a, user).write({"evidence_ids": [command]})
        self._as(self.revision_a, user).write({"evidence_ids": [Command.create({"name": "Owner reference"})]})
        self.assertEqual(len(self.revision_a.evidence_ids), 2)
        draft_line = self._as(self.env["vendor.price.revision.line"], user).create({"revision_id": self.revision_a.id})
        draft_line.unlink()
        self.assertFalse(draft_line.exists())

    def test_reassignment_and_foreign_child_links_are_denied(self):
        manager = self.users["manager"]
        for record in (self.line_a, self.evidence_a):
            with self.assertRaises(AccessError):
                self._as(record, manager).write({"revision_id": self.revision_b.id})
        with self.assertRaises(AccessError):
            self._as(self.revision_a, manager).write({"line_ids": [Command.link(self.line_b.id)]})
        with self.assertRaises(AccessError):
            self._as(self.env["vendor.price.revision.line"], self.users["purchase"]).create({
                "revision_id": self.revision_a.id, "company_id": self.company_b.id,
            })

    def test_ownership_bulk_atomicity_and_untrusted_context(self):
        user = self.users["purchase"]
        with self.assertRaises(AccessError):
            self._as(self.revision_a, user).write({"owner_id": self.other_purchase.id})
        with self.assertRaises(AccessError):
            self._as(self.revision_a | self.other_revision_a, user).write({"notes": "partial"})
        self.assertFalse(self.revision_a.notes)
        with self.assertRaises(AccessError):
            self._as(self.other_revision_a, user).with_context(
                skip_security=True, force_approve=True, is_manager=True,
            ).write({"notes": "context bypass"})

    def test_protected_state_and_children_remain_locked(self):
        # Trusted test fixture only, not a business validation/approval transition.
        super(VendorPriceRevision, self.revision_a).write({"state": "validated"})
        for record in (self.revision_a, self.line_a, self.evidence_a):
            with self.assertRaises(AccessError):
                self._as(record, self.users["manager"]).write({"notes": "historical edit"})
        with self.assertRaises(AccessError):
            self._as(self.line_a, self.users["manager"]).unlink()
        with self.assertRaises(AccessError):
            self._as(self.revision_a, self.users["manager"]).write({
                "line_ids": [Command.create({"proposed_price": 20})],
            })

    def test_copy_resets_owner_and_keeps_evidence_on_original(self):
        copied = self._as(self.other_revision_a, self.users["manager"]).copy()
        self.assertEqual(copied.owner_id, self.users["manager"])
        self.assertEqual(copied.state, "draft")
        self.assertNotEqual(copied.name, self.other_revision_a.name)
        self.assertFalse(copied.evidence_ids)
        self.assertFalse(copied.line_ids)

    def test_group_combinations_preserve_boundaries_and_state_gates(self):
        combinations = [
            ["purchase", "manager"], ["manager", "finance"], ["finance", "auditor"],
            ["sales_manager", "purchase"], ["director", "manager"], ["pricing", "finance"],
            ["pricing", "purchase"],
        ]
        for index, roles in enumerate(combinations):
            with self.subTest(roles=roles):
                user = self._make_user(f"combo_{index}", roles, self.company_a)
                own = self._make_revision(self.company_a, user)
                if "purchase" in roles or "manager" in roles:
                    self._as(own, user).write({"notes": "authorized union"})
                    self.assertEqual(own.notes, "authorized union")
                else:
                    with self.assertRaises(AccessError):
                        self._as(own, user).write({"notes": "read only union"})
                with self.assertRaises(AccessError):
                    self._as(self.revision_b, user).read()
                for state in ("approved", "applied"):
                    with self.assertRaises(AccessError):
                        self._as(own, user).write({"state": state})
                self.assertEqual(own.state, "draft")

    def test_role_assignment_is_administrative(self):
        director = self.env.ref(f"{MODULE}.group_vpr_director")
        for role in ("purchase", "configuration"):
            user = self.users[role]
            with self.assertRaises(AccessError):
                self._as(user, user).write({"group_ids": [Command.link(director.id)]})
            self.assertFalse(user.has_group(f"{MODULE}.group_vpr_director"))

    def test_inactive_user_and_removed_role_lose_access(self):
        user = self._make_user("inactive", ["finance"], self.company_a)
        self.assertTrue(self._as(self.revision_a, user).read(["name"]))
        user.active = False
        self.assertFalse(self._as(self.env["vendor.price.revision"], user).search([]))
        user = self._make_user("removed_role", ["finance"], self.company_a)
        self.assertTrue(self._as(self.revision_a, user).read(["name"]))
        user.group_ids = [Command.set(self.env.ref("base.group_user").ids)]
        with self.assertRaises(AccessError):
            self._as(self.revision_a, user).read()

    def test_standard_supplier_cost_visibility_boundary(self):
        # APP 06 ACLs do not revoke the product module's internal-user read grant.
        supplier_price = self.env["product.supplierinfo"].create({
            "partner_id": self.vendor.id, "product_tmpl_id": self.product.product_tmpl_id.id,
            "company_id": self.company_a.id, "price": 88,
        })
        sales = self.users["sales"]
        self.assertEqual(self._as(supplier_price, sales).price, 88)
        with self.assertRaises(AccessError):
            self._as(self.line_a, sales).read(["proposed_price"])

    def test_role_configuration_preserves_existing_prices(self):
        supplier_price = self.env["product.supplierinfo"].create({
            "partner_id": self.vendor.id, "product_tmpl_id": self.product.product_tmpl_id.id,
            "company_id": self.company_a.id, "price": 71.5, "min_qty": 5,
        })
        before = supplier_price.read(["price", "min_qty", "currency_id", "company_id"])
        before_product = self.product.read(["list_price", "standard_price"])
        operational_before = {m: self.env[m].search([]).read(["state", "write_date"], load=None) for m in ("purchase.order", "stock.move", "account.move", "sale.order") if m in self.env}
        user = self._make_user("business_safety", ["purchase", "auditor"], self.company_a)
        revision = self._make_revision(self.company_a, user)
        self._as(revision, user).write({"notes": "Draft preparation only"})
        self.assertEqual(supplier_price.read(["price", "min_qty", "currency_id", "company_id"]), before)
        self.assertEqual(self.product.read(["list_price", "standard_price"]), before_product)
        self.assertEqual(operational_before, {m: self.env[m].search([]).read(["state", "write_date"], load=None) for m in operational_before})

    def test_menu_and_sensitive_field_contract(self):
        action = self.env.ref(f"{MODULE}.action_vendor_price_revision")
        expected = self.env.ref(f"{MODULE}.group_vendor_price_revision_user") | self.env.ref(f"{MODULE}.group_vpr_confidential_reader")
        self.assertEqual(action.group_ids, expected)
        self.assertEqual(self.env.ref(f"{MODULE}.menu_vendor_price_simulator_root").group_ids, expected | self.env.ref(f"{MODULE}.group_vpr_configuration_admin") | self.env.ref(f"{MODULE}.group_vpr_sales_user"))
        self.assertEqual(self.env.ref(f"{MODULE}.menu_vendor_price_revisions").group_ids, expected)
        self.assertIn("attachment_id", self.evidence_a._fields)
        self.assertFalse(self.evidence_a.attachment_id)
        self.assertFalse(self.evidence_a.import_batch_id)
        self.assertNotIn("message_ids", self.revision_a._fields)
        for role in self.role_ids:
            for method in ("action_approve", "action_apply", "action_apply_prices"):
                self.assertFalse(hasattr(self._as(self.revision_a, self.users[role]), method))
