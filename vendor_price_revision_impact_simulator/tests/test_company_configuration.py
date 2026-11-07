import json
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

MODULE = 'vendor_price_revision_impact_simulator'


@tagged('post_install', '-at_install')
class TestCompanyConfiguration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.a = cls.env.company
        cls.a.write({'name': 'PR04 ABC India', 'currency_id': cls.env.ref('base.INR').id})
        cls.b = cls.env['res.company'].create({'name': 'PR04 ABC UAE', 'currency_id': cls.env.ref('base.AED').id})
        cls.today = fields.Date.today()
        cls.end = cls.today + timedelta(days=30)
        cls.category = cls.env['product.category'].create({'name': 'PR04 LED Lighting'})
        cls.product = cls.env['product.product'].create({'name': 'PR04 Shared LED', 'categ_id': cls.category.id})
        cls.other_product = cls.env['product.product'].create({'name': 'PR04 Other LED', 'categ_id': cls.product.categ_id.id})
        cls.unrelated = cls.env['product.product'].create({'name': 'PR04 Unrelated', 'categ_id': cls.env['product.category'].create({'name': 'PR04 Other'}).id})
        cls.users = {}
        for key, role, companies in [
            ('admin', 'configuration_admin', cls.a), ('admin_b', 'configuration_admin', cls.b),
            ('admin_ab', 'configuration_admin', cls.a | cls.b), ('finance', 'finance_manager', cls.a),
            ('manager', 'purchase_manager', cls.a), ('auditor', 'auditor', cls.a),
            ('purchase', 'vendor_price_revision_user', cls.a), ('sales', 'sales_user', cls.a),
            ('pricing', 'pricing_operator', cls.a), ('director', 'director', cls.a)]:
            group = 'group_' + role if role == 'vendor_price_revision_user' else 'group_vpr_' + role
            cls.users[key] = cls.env['res.users'].with_context(no_reset_password=True).create({
                'name': 'PR04 ' + key, 'login': 'pr04.' + key + '@example.invalid',
                'company_id': companies[0].id, 'company_ids': [Command.set(companies.ids)],
                'group_ids': [Command.set([cls.env.ref(MODULE + '.' + group).id])],
            })
        cls.config = cls._new_config(cls.a, '1')
        cls.config_b = cls._new_config(cls.b, '1', minimum=15, target=22)

    @classmethod
    def _new_config(cls, company, version, minimum=20, target=25, start=None, end=None):
        config = cls.env['vendor.price.revision.config'].with_company(company).create({
            'company_id': company.id, 'policy_version': version,
            'effective_from': start or cls.today, 'effective_to': end or cls.end,
            'change_reason': 'Explicit test governance',
            'margin_ids': [Command.create({'scope': 'company', 'minimum_margin_percent': minimum,
                'target_margin_percent': target, 'reason': 'Company minimum'})],
        })
        for level, lower, upper in [('low', 0, 10000), ('medium', 10000, 50000), ('high', 50000, 200000), ('critical', 200000, None)]:
            cls.env['vendor.price.revision.risk.rule'].create({
                'config_id': config.id, 'currency_id': company.currency_id.id, 'name': level,
                'risk_level': level, 'minimum_amount': lower, 'maximum_amount': upper or 0,
                'open_ended': upper is None, 'reason': 'Example thresholds',
            })
        cls.env['vendor.price.revision.approval.policy'].create({
            'config_id': config.id, 'currency_id': company.currency_id.id, 'name': 'Finance review',
            'open_ended': True, 'reason': 'Finance definition',
            'required_role_ids': [Command.set([cls.env.ref(MODULE + '.group_vpr_finance_manager').id])],
        })
        return config

    def _as(self, records, user='admin', companies=None):
        user = self.users[user]
        return records.with_user(user).with_context(allowed_company_ids=(companies or user.company_id).ids)

    def _invalid(self, record, values, exception=ValidationError):
        with self.assertRaises(exception), self.cr.savepoint():
            record.write(values)

    def test_authorized_setup_defaults_and_readiness(self):
        model = self._as(self.env['vendor.price.revision.config'])
        draft = model.create({'policy_version': 'incomplete', 'effective_to': self.end, 'change_reason': 'Setup'})
        self.assertEqual(draft.company_id, self.a)
        self.assertIn('missing', draft.readiness)
        with self.assertRaises(ValidationError):
            draft.action_publish()
        self.assertEqual(draft.state, 'draft')
        for name, value in [('missing_fx_policy', 'block_calculation'), ('missing_cost_policy', 'incomplete'),
                            ('backdated_application_policy', 'restricted_review'), ('stale_revision_policy', 'revalidate'),
                            ('delegation_policy', 'disabled')]:
            self.assertEqual(draft[name], value)
        self._as(self.config).action_publish()
        self.assertIn('structurally valid', self.config.readiness)
        self.assertEqual(self.config.published_by, self.users['admin'])

    def test_company_switch_and_shared_product(self):
        self.config.action_publish()
        self.config_b.action_publish()
        model = self._as(self.env['vendor.price.revision.config'], 'admin_ab', self.a | self.b)
        for company, expected in [(self.a, 20), (self.b, 15)]:
            record = model.with_company(company).get_company_revision_config(company, self.today)
            self.assertEqual(record.get_applicable_margin_policy(self.product).minimum_margin_percent, expected)
        with self.assertRaises(AccessError):
            self._as(model).get_company_revision_config(self.b, self.today)
        with self.assertRaises(AccessError):
            self._as(model).with_context(allowed_company_ids=[self.b.id]).get_company_revision_config(self.b, self.today)

    def test_roles_are_read_only_or_denied(self):
        for role in ('finance', 'manager', 'auditor', 'director'):
            record = self._as(self.config, role)
            self.assertEqual(record.read(['policy_version'])[0]['policy_version'], '1')
            self._invalid(record, {'name': 'unauthorized'}, AccessError)
            with self.assertRaises(AccessError):
                record.action_publish()
        for role in ('purchase', 'sales', 'pricing'):
            record = self._as(self.config, role)
            with self.assertRaises(AccessError):
                record.read(['id'])
            self._invalid(record, {'name': 'unauthorized'}, AccessError)

    def test_cross_company_crud_exports_and_grouped_read(self):
        for record in (self.config_b, self.config_b.margin_ids, self.config_b.risk_ids, self.config_b.approval_ids, self.config_b.audit_ids):
            with self.subTest(model=record._name):
                scoped = self._as(record)
                with self.assertRaises(AccessError):
                    scoped.read(['id'])
                with self.assertRaises(AccessError):
                    scoped.export_data(['id'])
                with self.assertRaises(AccessError):
                    scoped.write({})
                model = self._as(self.env[record._name])
                self.assertFalse(model.search([('company_id', '=', self.b.id)]))
                self.assertFalse(model._read_group([('company_id', '=', self.b.id)], ['company_id'], ['__count']))
        with self.assertRaises(AccessError):
            self._as(self.env['vendor.price.revision.config']).create({'company_id': self.b.id,
                'policy_version': 'forged', 'effective_to': self.end, 'change_reason': 'forged'})

    def test_nested_commands_and_ownership_protection(self):
        self._invalid(self._as(self.config), {'company_id': self.b.id}, AccessError)
        for relation in ('margin_ids', 'risk_ids', 'approval_ids'):
            own, other = self.config[relation], self.config_b[relation]
            for cmd in (Command.link(other[0].id), Command.set(other.ids), Command.clear(), Command.update(other[0].id, {'reason': 'forged'})):
                self._invalid(self._as(self.config), {relation: [cmd]}, AccessError)
            self._invalid(self._as(own), {'config_id': self.config_b.id}, AccessError)
            with self.assertRaises(AccessError):
                self._as(self.env[own._name]).create({'config_id': self.config_b.id})
        self._invalid(self._as(self.config), {'audit_ids': [Command.clear()]}, AccessError)
        self._as(self.config).write({'margin_ids': [Command.update(self.config.margin_ids.id, {'reason': 'authorized'})]})

    def test_product_company_validation_and_scope_shape(self):
        foreign = self.env['product.product'].create({'name': 'B only', 'company_id': self.b.id})
        foreign_category = self.env['product.category'].create({'name': 'B category', 'company_id': self.b.id})
        for values in [{'scope': 'product'}, {'scope': 'category'}, {'scope': 'company', 'product_id': self.product.id},
                       {'scope': 'product', 'product_id': foreign.id}, {'scope': 'category', 'category_id': foreign_category.id}]:
            with self.assertRaises((UserError, ValidationError)), self.cr.savepoint():
                self.env['vendor.price.revision.margin.policy'].create(dict(values, config_id=self.config.id,
                    minimum_margin_percent=20, target_margin_percent=25, reason='invalid'))

    def test_margin_precedence_and_provenance(self):
        model = self._as(self.env['vendor.price.revision.margin.policy'])
        category = model.create({'config_id': self.config.id, 'scope': 'category', 'category_id': self.product.categ_id.id,
            'minimum_margin_percent': 18, 'target_margin_percent': 24, 'reason': 'Category'})
        product = model.create({'config_id': self.config.id, 'scope': 'product', 'product_id': self.product.id,
            'minimum_margin_percent': 15, 'target_margin_percent': 22, 'reason': 'Product exception'})
        self.config.action_publish()
        for item, expected in [(self.product, product), (self.other_product, category), (self.unrelated, self.config.margin_ids.filtered(lambda r: r.scope == 'company'))]:
            result = self._as(self.config).get_applicable_margin_policy(item)
            self.assertEqual(result, expected)
            self.assertEqual(result.config_id.policy_version, '1')
        with self.assertRaises(AccessError):
            self._as(model, 'purchase').create({'config_id': self.config.id})

    def test_margin_values_finite_and_scope_duplicates(self):
        row = self.config.margin_ids
        for values in [{'minimum_margin_percent': -1}, {'minimum_margin_percent': 26}, {'target_margin_percent': 100},
                       {'target_margin_percent': float('inf')}, {'minimum_margin_percent': float('nan')},
                       {'minimum_margin_percent': False}, {'target_margin_percent': None}]:
            self._invalid(row, values)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env[row._name].create({'config_id': self.config.id, 'scope': 'company', 'reason': 'Duplicate'})

    def test_risk_ranges_boundaries_and_currency(self):
        rows = self.config.get_applicable_risk_rules()
        self.assertEqual(rows.mapped('risk_level'), ['low', 'medium', 'high', 'critical'])
        # Assert interval definitions only: no exposure/risk calculation service.
        self.assertEqual(rows[1].minimum_amount, rows[0].maximum_amount)
        self.assertEqual(rows[1].minimum_amount, 10000)
        self.assertEqual(rows[2].minimum_amount, 50000)
        self.assertTrue(rows[-1].open_ended)
        for amount, level in [(0, 'low'), (9999.99, 'low'), (10000, 'medium'), (50000, 'high'), (200000, 'critical')]:
            matching = rows.filtered(lambda r: r.currency_id.compare_amounts(amount, r.minimum_amount) >= 0 and
                (r.open_ended or r.currency_id.compare_amounts(amount, r.maximum_amount) < 0))
            self.assertEqual(matching.risk_level, level)
        low = rows[0]
        for vals in [{'minimum_amount': -1}, {'maximum_amount': 0}, {'maximum_amount': 10001},
                     {'open_ended': True, 'maximum_amount': 0}, {'currency_id': self.b.currency_id.id},
                     {'minimum_amount': float('nan')}, {'maximum_amount': float('inf')}]:
            self._invalid(low, vals)
        self.assertFalse(hasattr(self.config, 'calculate_risk'))

    def test_scale_gaps_block_publication_and_lookup(self):
        self.config.risk_ids[1].write({'minimum_amount': 11000})
        with self.assertRaises(ValidationError):
            self.config.get_applicable_risk_rules()
        with self.assertRaises(ValidationError):
            self.config.action_publish()
        self.assertEqual(self.config.state, 'draft')
        self.config.risk_ids[1].write({'minimum_amount': 10000})
        self.config.approval_ids.write({'minimum_amount': 1})
        with self.assertRaises(ValidationError):
            self.config.action_publish()

    def test_approval_ranges_multirole_and_normalized_amount(self):
        first = self.config.approval_ids
        first.write({'open_ended': False, 'maximum_amount': 25000})
        roles = [self.env.ref(MODULE + '.' + role).id for role in ('group_vpr_purchase_manager', 'group_vpr_finance_manager')]
        second = self.env[first._name].create({'config_id': self.config.id, 'name': 'Two roles', 'minimum_amount': 25000,
            'currency_id': self.a.currency_id.id, 'open_ended': True, 'reason': 'Multiple roles',
            'required_role_ids': [Command.set(roles)], 'required_independent_approvers': 2})
        self.assertEqual(self.config.get_applicable_approval_policy('finance_exposure', 24999.99, self.a.currency_id), first)
        self.assertEqual(self.config.get_applicable_approval_policy('finance_exposure', 25000, self.a.currency_id), second)
        self.assertEqual(len(second.required_role_ids), 2)
        for amount in (None, False, -1, float('nan'), float('inf')):
            with self.assertRaises(ValidationError):
                self.config.get_applicable_approval_policy('finance_exposure', amount, self.a.currency_id)
        with self.assertRaises(ValidationError):
            self.config.get_applicable_approval_policy('finance_exposure', 1, self.b.currency_id)
        self._invalid(first, {'maximum_amount': 25000.01})
        self._invalid(first, {'maximum_amount': -1})
        self._invalid(second, {'required_independent_approvers': 1})

    def test_approval_roles_do_not_grant_permissions(self):
        row = self.config.approval_ids
        original = self.users['admin'].group_ids
        for roles in ([], [self.env.ref(MODULE + '.group_vpr_configuration_admin').id],
                      [self.env.ref(MODULE + '.group_vpr_pricing_operator').id], [self.env.ref(MODULE + '.group_vpr_auditor').id]):
            self._invalid(row, {'required_role_ids': [Command.set(roles)]})
        self.assertEqual(self.users['admin'].group_ids, original)
        self.assertFalse(self.users['admin'].has_group(MODULE + '.group_vpr_finance_manager'))
        for method in ('action_approve', 'action_apply', 'action_apply_prices'):
            self.assertFalse(hasattr(self.config, method))

    def test_dates_versions_overlap_and_missing_config(self):
        self._invalid(self.config, {'effective_to': self.today - timedelta(days=1)})
        self.config.action_publish()
        overlap = self._new_config(self.a, 'overlap')
        with self.assertRaises(ValidationError):
            overlap.action_publish()
        future = self._new_config(self.a, 'future', minimum=15, target=22, start=self.end + timedelta(days=1), end=self.end + timedelta(days=40))
        future.action_publish()
        model = self.env['vendor.price.revision.config']
        self.assertEqual(model.get_company_revision_config(self.a, self.today), self.config)
        self.assertEqual(model.get_company_revision_config(self.a, self.end + timedelta(days=1)), future)
        with self.assertRaises(UserError):
            model.get_company_revision_config(self.a, self.end + timedelta(days=50))
        with self.assertRaises(ValidationError):
            model.get_company_revision_config(self.a, None)
        inactive = self._new_config(self.a, 'inactive')
        inactive.active = False
        with self.assertRaises(UserError):
            inactive.action_publish()

    def test_published_history_and_audit_are_immutable(self):
        row = self.config.margin_ids
        row.write({'minimum_margin_percent': 19, 'reason': 'Documented change'})
        audit = self.env['vendor.price.revision.config.audit'].search([('model_name', '=', row._name), ('operation', '=', 'write')], limit=1)
        self.assertEqual(json.loads(audit.before_json)['minimum_margin_percent'], 20)
        self.assertEqual(json.loads(audit.after_json)['minimum_margin_percent'], 19)
        self._as(self.config).action_publish()
        for record in (self.config, self.config.margin_ids, self.config.risk_ids, self.config.approval_ids):
            with self.assertRaises(UserError):
                self._as(record).write({'active': False})
            with self.assertRaises((AccessError, UserError)):
                self._as(record).unlink()
        for operation in (lambda: self._as(audit).write({'operation': 'forged'}), lambda: audit.unlink(),
                          lambda: self.env[audit._name].create({'operation': 'forged'})):
            with self.assertRaises(AccessError):
                operation()
        copy = self._as(self.config).copy()
        self.assertEqual(copy.state, 'draft')
        self.assertFalse(copy.published_by)
        self.assertEqual(len(copy.risk_ids), 4)
        self.assertEqual(copy.margin_ids.minimum_margin_percent, 19)
        with self.assertRaises(AccessError):
            self._as(self.config).copy({'company_id': self.b.id})

    def test_publication_cannot_be_forged_or_backdated(self):
        contextual = self._as(self.env[self.config._name]).with_context(
            default_state='published', default_published_by=self.env.uid,
            default_published_at=fields.Datetime.now()).create({
                'policy_version': 'context-default', 'effective_to': self.end, 'change_reason': 'Untrusted context'})
        self.assertEqual(contextual.state, 'draft')
        self.assertFalse(contextual.published_by)
        self.assertFalse(contextual.published_at)
        for values in [{'state': 'published'}, {'published_by': self.env.uid}, {'published_at': fields.Datetime.now()}]:
            self._invalid(self._as(self.config), values, AccessError)
            with self.assertRaises(AccessError):
                self._as(self.env[self.config._name]).create(dict(values, policy_version='forged', effective_to=self.end, change_reason='forged'))
        self.config.effective_from = self.today - timedelta(days=1)
        with self.assertRaises(AccessError):
            self._as(self.config).with_context(skip_security=True).action_publish()

    def test_unknown_values_and_independence_validation(self):
        self._invalid(self.config, {'cost_basis': 'invented'}, ValueError)
        for values in [{'minimum_distinct_approvers': 0}, {'require_independent_approver': False},
                       {'allow_same_user_multiple_stages': True}, {'currency_rate_policy': 'company_reference_date'},
                       {'currency_rate_policy': 'authorized_scenario_rate'}]:
            self._invalid(self.config, values)

    def test_missing_thresholds_and_changed_dependencies_fail_safely(self):
        model = self._as(self.env['vendor.price.revision.margin.policy'])
        with self.assertRaises(ValidationError):
            model.create({'config_id': self.config.id, 'scope': 'product', 'product_id': self.product.id, 'reason': 'Missing thresholds'})
        self.config.minimum_distinct_approvers = 2
        self.assertIn('Distinct approver', self.config.readiness)
        with self.assertRaises(ValidationError):
            self.config.action_publish()
        self.config.approval_ids.required_independent_approvers = 2
        self.assertIn('structurally valid', self.config.readiness)
        self.config.action_publish()
        original_currency = self.config.currency_id
        self.a.currency_id = self.env.ref('base.INR') if self.a.currency_id != self.env.ref('base.INR') else self.env.ref('base.USD')
        self.assertEqual(self.config.currency_id, original_currency)
        with self.assertRaises(UserError):
            self.env[self.config._name].get_company_revision_config(self.a, self.today)

    def test_company_defaults_inactive_users_role_union_and_bulk_guard(self):
        model = self._as(self.env[self.config._name])
        with self.assertRaises(AccessError):
            model.with_context(default_company_id=self.b.id).create({'policy_version': 'context-forged', 'effective_to': self.end, 'change_reason': 'forged'})
        self.users['admin'].group_ids = [Command.link(self.env.ref(MODULE + '.group_vpr_director').id)]
        self._invalid(self._as(self.config_b), {'name': 'role union'}, AccessError)
        self.users['admin'].active = False
        with self.assertRaises(AccessError):
            self._as(self.config).read(['id'])
        self.users['admin'].active = True
        self.config.action_publish()
        draft = self._new_config(self.a, 'bulk-draft')
        with self.assertRaises(UserError):
            self._as(draft | self.config).write({'name': 'bulk overwrite'})
        self.assertNotEqual(draft.name, 'bulk overwrite')

    def test_settings_views_and_no_operational_side_effects(self):
        vendor = self.env['res.partner'].create({'name': 'PR04 Supplier'})
        price = self.env['product.supplierinfo'].create({'partner_id': vendor.id, 'product_tmpl_id': self.product.product_tmpl_id.id, 'price': 110})
        revision = self.env['vendor.price.revision'].create({'vendor_id': vendor.id})
        before = (price.price, price.write_date, self.product.standard_price, self.product.list_price,
                  revision.state, revision.write_date, self.env['ir.cron'].search_count([]))
        self._as(self.config).write({'cost_basis': 'estimated_replacement_cost'})
        self._as(self.config).action_publish()
        self.assertEqual(before, (price.price, price.write_date, self.product.standard_price, self.product.list_price,
                                  revision.state, revision.write_date, self.env['ir.cron'].search_count([])))
        form = self._as(self.config).get_view(view_id=self.env.ref(MODULE + '.view_vpr_config_form').id, view_type='form')
        self.assertIn('Publish Configuration', form['arch'])
        self.assertEqual(self.env.ref(MODULE + '.menu_vpr_business_settings').action.res_model, self.config._name)
        self.assertFalse(self.env['vendor.price.revision.config'].search([('company_id', '=', self.b.id), ('state', '=', 'published')]))
