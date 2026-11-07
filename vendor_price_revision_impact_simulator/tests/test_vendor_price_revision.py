from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


MODULE = "vendor_price_revision_impact_simulator"


@tagged("post_install", "-at_install")
class TestVendorPriceRevision(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.vendor = cls.env["res.partner"].create({"name": "PR-02 Test Supplier"})
        cls.currency = cls.company.currency_id
        cls.group_revision_user = cls.env.ref(f"{MODULE}.group_vendor_price_revision_user")

    def _revision(self, **values):
        vals = {
            "company_id": self.company.id,
            "vendor_id": self.vendor.id,
            "currency_id": self.currency.id,
        }
        vals.update(values)
        return self.env["vendor.price.revision"].create(vals)

    def _app_user(self, name, company):
        return self.env["res.users"].create({
            "name": name,
            "login": f"{name.lower().replace(' ', '.')}.pr02@example.invalid",
            "company_id": company.id,
            "company_ids": [Command.set(company.ids)],
            "group_ids": [Command.set(self.group_revision_user.ids)],
        })

    def test_draft_creation_numbering_and_copy(self):
        first = self._revision()
        second = self._revision()
        duplicate = first.copy()

        self.assertEqual(first.state, "draft")
        self.assertTrue(first.name.startswith("VPR/"))
        self.assertEqual(len({first.name, second.name, duplicate.name}), 3)
        self.assertEqual(first.company_id, self.company)
        self.assertEqual(first.vendor_id, self.vendor)
        self.assertEqual(first.currency_id, self.currency)
        self.assertEqual(duplicate.state, "draft")

    def test_authorized_non_admin_can_create_draft(self):
        user = self._app_user("PR-02 Authorized Draft User", self.company)
        revision = self.env["vendor.price.revision"].with_user(user).create({
            "vendor_id": self.vendor.id,
            "currency_id": self.currency.id,
        })
        self.assertEqual(revision.state, "draft")
        self.assertEqual(revision.company_id, self.company)
        self.assertEqual(revision.owner_id, user)
        self.assertTrue(revision.name.startswith("VPR/"))

    def test_line_count_and_unmapped_draft_price_semantics(self):
        revision = self._revision()
        unset_line = self.env["vendor.price.revision.line"].create({
            "revision_id": revision.id,
            "vendor_product_code": "UNMAPPED-01",
        })
        explicit_zero = self.env["vendor.price.revision.line"].create({
            "revision_id": revision.id,
            "vendor_product_code": "ZERO-PRICE",
            "proposed_price": 0.0,
            "price_is_set": True,
        })
        positive = self.env["vendor.price.revision.line"].create({
            "revision_id": revision.id,
            "proposed_price": 12.5,
        })

        self.assertEqual(revision.line_count, 3)
        self.assertFalse(unset_line.product_id)
        self.assertFalse(unset_line.price_is_set)
        self.assertEqual(unset_line.proposed_price, 0.0)
        self.assertTrue(explicit_zero.price_is_set)
        self.assertEqual(explicit_zero.proposed_price, 0.0)
        self.assertTrue(positive.price_is_set)
        self.assertEqual(positive.proposed_price, 12.5)

    def test_negative_price_and_quantity_are_rejected(self):
        revision = self._revision()
        with self.assertRaises(ValidationError):
            self.env["vendor.price.revision.line"].create({
                "revision_id": revision.id,
                "proposed_price": -1.0,
                "price_is_set": True,
            })
        with self.assertRaises(ValidationError):
            self.env["vendor.price.revision.line"].create({
                "revision_id": revision.id,
                "min_qty": -1.0,
            })

    def test_company_and_revision_identity_are_immutable(self):
        revision = self._revision()
        other_company = self.env["res.company"].create({"name": "PR-02 Other Company"})
        with self.assertRaises(AccessError):
            revision.write({"company_id": other_company.id})
        with self.assertRaises(AccessError):
            revision.write({"name": "MANUAL/REFERENCE"})
        with self.assertRaises(AccessError):
            self.env["vendor.price.revision.line"].create({
                "revision_id": revision.id,
                "company_id": other_company.id,
            })

    def test_currency_and_vendor_lock_after_children_exist(self):
        revision = self._revision()
        self.env["vendor.price.revision.line"].create({"revision_id": revision.id})
        other_vendor = self.env["res.partner"].create({"name": "Other Vendor"})
        with self.assertRaises(UserError):
            revision.write({"vendor_id": other_vendor.id})
        other_currency = self.env["res.currency"].search([("id", "!=", self.currency.id)], limit=1)
        if other_currency:
            with self.assertRaises(UserError):
                revision.write({"currency_id": other_currency.id})

    def test_lifecycle_state_cannot_be_forged(self):
        with self.assertRaises(AccessError):
            self._revision(state="approved")
        with self.assertRaises(AccessError):
            self._revision(state="applied")
        revision = self._revision()
        with self.assertRaises(AccessError):
            revision.write({"state": "approved"})
        with self.assertRaises(AccessError):
            revision.write({"state": "applied"})
        self.assertEqual(revision.state, "draft")

    def test_child_reassignment_and_evidence_deletion_are_blocked(self):
        revision = self._revision()
        other_revision = self._revision()
        line = self.env["vendor.price.revision.line"].create({"revision_id": revision.id})
        evidence = self.env["vendor.price.revision.evidence"].create({
            "revision_id": revision.id,
            "name": "Supplier email reference",
            "source_reference": "email-thread-123",
        })
        with self.assertRaises(AccessError):
            line.write({"revision_id": other_revision.id})
        with self.assertRaises(UserError):
            evidence.unlink()
        self.assertEqual(evidence.company_id, revision.company_id)
        self.assertIn("attachment_id", evidence._fields)
        self.assertFalse(evidence.attachment_id)
        self.assertFalse(evidence.sha256_digest)

    def test_user_without_app_group_has_no_model_access(self):
        user = self.env["res.users"].create({
            "name": "PR-02 Unprivileged Internal",
            "login": "pr02.unprivileged@example.invalid",
            "company_id": self.company.id,
            "company_ids": [Command.set(self.company.ids)],
            "group_ids": [Command.set(self.env.ref("base.group_user").ids)],
        })
        with self.assertRaises(AccessError):
            self.env["vendor.price.revision"].with_user(user).search_count([])

    def test_public_and_portal_users_have_no_model_access(self):
        public_user = self.env.ref("base.public_user")
        with self.assertRaises(AccessError):
            self.env["vendor.price.revision"].with_user(public_user).search_count([])

        portal_user = self.env["res.users"].create({
            "name": "PR-02 Portal User",
            "login": "pr02.portal@example.invalid",
            "company_id": self.company.id,
            "company_ids": [Command.set(self.company.ids)],
            "group_ids": [Command.set(self.env.ref("base.group_portal").ids)],
        })
        with self.assertRaises(AccessError):
            self.env["vendor.price.revision"].with_user(portal_user).search_count([])

    def test_company_record_rule_and_create_boundary(self):
        company_b = self.env["res.company"].create({"name": "PR-02 Company B"})
        revision_b = self.env["vendor.price.revision"].with_company(company_b).create({
            "company_id": company_b.id,
            "vendor_id": self.vendor.id,
            "currency_id": self.currency.id,
        })
        user_a = self._app_user("PR-02 Company A User", self.company)
        model_as_a = self.env["vendor.price.revision"].with_user(user_a)

        self.assertEqual(model_as_a.search_count([("id", "=", revision_b.id)]), 0)
        with self.assertRaises(AccessError):
            model_as_a.browse(revision_b.id).read()
        with self.assertRaises(AccessError):
            model_as_a.create({
                "company_id": company_b.id,
                "vendor_id": self.vendor.id,
                "currency_id": self.currency.id,
            })

    def test_company_boundary_protects_revision_lines_and_evidence(self):
        company_b = self.env["res.company"].create({"name": "PR-02 Evidence Company B"})
        revision_b = self.env["vendor.price.revision"].with_company(company_b).create({
            "company_id": company_b.id,
            "vendor_id": self.vendor.id,
            "currency_id": self.currency.id,
        })
        line_b = self.env["vendor.price.revision.line"].create({"revision_id": revision_b.id})
        evidence_b = self.env["vendor.price.revision.evidence"].create({
            "revision_id": revision_b.id,
            "name": "Company B supplier note",
        })
        user_a = self._app_user("PR-02 Boundary A User", self.company)

        for model, record in (
            ("vendor.price.revision", revision_b),
            ("vendor.price.revision.line", line_b),
            ("vendor.price.revision.evidence", evidence_b),
        ):
            records_as_a = self.env[model].with_user(user_a)
            self.assertEqual(records_as_a.search_count([("id", "=", record.id)]), 0)
            with self.assertRaises(AccessError):
                records_as_a.browse(record.id).read()
            with self.assertRaises(AccessError):
                records_as_a.browse(record.id).write({"notes": "unauthorized"})

        with self.assertRaises(AccessError):
            self.env["vendor.price.revision"].with_user(user_a).browse(revision_b.id).unlink()

    def test_company_specific_product_cannot_be_linked_across_companies(self):
        company_b = self.env["res.company"].create({"name": "PR-02 Product Company B"})
        revision_a = self._revision()
        product_b = self.env["product.product"].create({
            "name": "Company B Product",
            "company_id": company_b.id,
        })
        with self.assertRaises(UserError):
            self.env["vendor.price.revision.line"].create({
                "revision_id": revision_a.id,
                "product_id": product_b.id,
            })

    def test_draft_revision_does_not_change_vendor_or_product_prices(self):
        product = self.env["product.product"].create({"name": "PR-02 No Side Effect Product"})
        original_list_price = product.list_price
        original_cost = product.standard_price
        supplier_infos = self.env["product.supplierinfo"].search([])
        supplier_info_values = supplier_infos.read(
            ["partner_id", "product_tmpl_id", "price", "min_qty", "company_id"]
        )
        operational_before = {m: self.env[m].search([]).read(["state", "write_date"], load=None) for m in ("purchase.order", "stock.move", "account.move")}
        revision = self._revision()
        self.env["vendor.price.revision.line"].create({
            "revision_id": revision.id,
            "product_id": product.id,
            "proposed_price": 99.0,
        })
        self.assertEqual(product.list_price, original_list_price)
        self.assertEqual(product.standard_price, original_cost)
        self.assertEqual(self.env["product.supplierinfo"].search([]), supplier_infos)
        self.assertEqual(supplier_infos.read(
            ["partner_id", "product_tmpl_id", "price", "min_qty", "company_id"]
        ), supplier_info_values)
        self.assertEqual(operational_before, {m: self.env[m].search([]).read(["state", "write_date"], load=None) for m in operational_before})

    def test_menu_action_and_views_are_connected(self):
        action = self.env.ref(f"{MODULE}.action_vendor_price_revision")
        menu = self.env.ref(f"{MODULE}.menu_vendor_price_revisions")
        self.assertEqual(action.res_model, "vendor.price.revision")
        self.assertEqual(menu.action, action)
        self.assertIn(self.group_revision_user, action.group_ids)
        self.assertEqual(
            self.env.ref(f"{MODULE}.view_vendor_price_revision_form").model,
            "vendor.price.revision",
        )
