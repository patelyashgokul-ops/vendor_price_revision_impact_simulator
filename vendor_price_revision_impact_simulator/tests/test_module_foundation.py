import ast
from pathlib import Path

from odoo.tests import TransactionCase, tagged


MODULE = "vendor_price_revision_impact_simulator"
MODULE_ROOT = Path(__file__).resolve().parents[1]


@tagged("post_install", "-at_install")
class TestModuleFoundation(TransactionCase):
    def test_module_is_registered_and_installed(self):
        module = self.env["ir.module.module"].search([("name", "=", MODULE)])
        self.assertEqual(len(module), 1)
        self.assertEqual(module.state, "installed")

    def test_manifest_metadata_dependencies_and_data_files(self):
        manifest = ast.literal_eval((MODULE_ROOT / "__manifest__.py").read_text(encoding="utf-8"))

        self.assertEqual(manifest["name"], "Vendor Price Revision Impact Simulator")
        self.assertEqual(manifest["version"], "20.0.1.0.0")
        self.assertTrue(manifest["application"])
        self.assertTrue(manifest["installable"])
        self.assertEqual(manifest["depends"], ["base", "product", "purchase_stock", "sale_stock", "mail"])
        self.assertIn("security/vendor_revision_security.xml", manifest["data"])
        for relative_path in manifest["data"]:
            self.assertTrue((MODULE_ROOT / relative_path).is_file(), relative_path)

    def test_root_menu_exists_once_without_placeholder_actions(self):
        root_menu = self.env.ref(f"{MODULE}.menu_vendor_price_simulator_root")
        matching_roots = self.env["ir.ui.menu"].search(
            [("name", "=", "Vendor Price Simulator"), ("parent_id", "=", False)]
        )

        self.assertEqual(len(matching_roots), 1)
        self.assertEqual(matching_roots, root_menu)
        self.assertFalse(root_menu.parent_id)
        self.assertFalse(root_menu.action)
        self.assertEqual(root_menu.child_id, self.env.ref(f"{MODULE}.menu_vendor_price_revisions") | self.env.ref(f"{MODULE}.menu_import_wizard") | self.env.ref(f"{MODULE}.menu_import_batches") | self.env.ref(f"{MODULE}.menu_vpr_configuration") | self.env.ref(f"{MODULE}.menu_sales_snapshots") | self.env.ref(f"{MODULE}.menu_sales_lines") | self.env.ref(f"{MODULE}.menu_sales_grants") | self.env.ref(f"{MODULE}.menu_purchase_snapshot") | self.env.ref(f"{MODULE}.menu_purchase_line") | self.env.ref(f"{MODULE}.menu_purchase_evidence") | self.env.ref(f"{MODULE}.menu_cost_snapshots") | self.env.ref(f"{MODULE}.menu_financial_analysis") | self.env.ref(f"{MODULE}.menu_commercial_recommendations") | self.env.ref(f"{MODULE}.menu_approval_foundation") | self.env.ref(f"{MODULE}.report24_menu"))

    def test_root_menu_is_restricted_to_internal_users(self):
        root_menu = self.env.ref(f"{MODULE}.menu_vendor_price_simulator_root")
        public_user = self.env.ref("base.group_public")

        self.assertEqual(root_menu.group_ids, self.env.ref(f"{MODULE}.group_vendor_price_revision_user") | self.env.ref(f"{MODULE}.group_vpr_confidential_reader") | self.env.ref(f"{MODULE}.group_vpr_configuration_admin") | self.env.ref(f"{MODULE}.group_vpr_sales_user"))
        self.assertNotIn(public_user, root_menu.group_ids)
