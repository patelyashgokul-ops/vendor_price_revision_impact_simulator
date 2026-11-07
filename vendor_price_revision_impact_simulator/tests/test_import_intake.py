import hashlib
import logging
import time
from unittest.mock import patch

from psycopg2 import DatabaseError

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools.binary import BinaryBytes

from ..models import import_parser as parser
from ..models.import_intake import BATCH, ROW, ATTEMPT, WIZARD, EVIDENCE, binary_bytes
from .test_import_parser import workbook_bytes

MODULE = 'vendor_price_revision_impact_simulator'
CSV = b'Code,Description,Price\r\n000123,"LED, bulb",115\r\n000045,Other,0\r\n'


class IntakeFixtures:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.a = cls.env.company
        cls.b = cls.env['res.company'].create({'name': 'PR05 Other Company'})
        cls.vendor = cls.env['res.partner'].create({'name': 'PR05 Shared Vendor'})
        cls.product = cls.env['product.product'].create({'name': 'PR05 Existing Product'})
        cls.users = {}
        for key, group, company in [('purchase', 'group_vendor_price_revision_user', cls.a),
            ('other', 'group_vendor_price_revision_user', cls.a), ('purchase_b', 'group_vendor_price_revision_user', cls.b),
            ('manager', 'group_vpr_purchase_manager', cls.a), ('finance', 'group_vpr_finance_manager', cls.a),
            ('auditor', 'group_vpr_auditor', cls.a), ('sales', 'group_vpr_sales_user', cls.a),
            ('director', 'group_vpr_director', cls.a), ('pricing', 'group_vpr_pricing_operator', cls.a),
            ('configuration', 'group_vpr_configuration_admin', cls.a), ('portal', 'base.group_portal', cls.a),
            ('employee', 'base.group_user', cls.a)]:
            ref = group if group.startswith('base.') else MODULE + '.' + group
            cls.users[key] = cls.env['res.users'].with_context(no_reset_password=True).create({
                'name': 'PR05 ' + key, 'login': 'pr05.' + key + '@example.invalid',
                'company_id': company.id, 'company_ids': [Command.set(company.ids)],
                'group_ids': [Command.set(cls.env.ref(ref).ids)],
            })
        cls.revision = cls._revision_for(cls.users['purchase'])
        cls.other_revision = cls._revision_for(cls.users['other'])
        cls.revision_b = cls._revision_for(cls.users['purchase_b'])

    @classmethod
    def _revision_for(cls, user):
        return cls.env['vendor.price.revision'].with_user(user).with_context(
            allowed_company_ids=user.company_id.ids).create({'vendor_id': cls.vendor.id})

    def _as(self, records, role='purchase', companies=None):
        user = self.users[role]
        return records.with_user(user).with_context(allowed_company_ids=(companies or user.company_id).ids)

    def _wizard(self, raw=CSV, name='prices.csv', role='purchase', revision=None, **options):
        revision = revision or (self.revision_b if role == 'purchase_b' else self.revision)
        vals = dict(company_id=revision.company_id.id, revision_id=revision.id,
            upload_file=BinaryBytes(raw), upload_filename=name,
            file_format='xlsx' if name.endswith('.xlsx') else 'csv')
        vals.update(options)
        return self._as(self.env[WIZARD], role).create(vals)

    def _upload(self, raw=CSV, name='prices.csv', role='purchase', **options):
        wizard = self._wizard(raw, name, role, **options)
        action = wizard.action_upload_extract()
        self.assertEqual(action['res_model'], BATCH)
        return self._as(self.env[BATCH].browse(action['res_id']), role)


@tagged('post_install', '-at_install')
class TestImportIntake(IntakeFixtures, TransactionCase):
    def test_csv_actual_upload_evidence_raw_bytes_and_binary_api(self):
        batch = self._upload()
        self.assertEqual(batch.state, 'extracted')
        self.assertEqual(batch.extracted_row_count, 2)
        self.assertEqual(len(batch.row_ids), 2)
        self.assertEqual(batch.file_size, len(CSV))
        self.assertEqual(batch.sha256_digest, hashlib.sha256(CSV).hexdigest())
        self.assertEqual(binary_bytes(batch.attachment_id.raw), CSV)
        self.assertEqual(batch.evidence_id.sha256_digest, batch.sha256_digest)
        self.assertEqual(batch.evidence_id.import_batch_id, batch)
        self.assertEqual(batch.attachment_id.res_model, EVIDENCE)
        self.assertEqual(batch.attachment_id.res_id, batch.evidence_id.id)
        self.assertEqual(batch.attachment_id.company_id, self.a)
        self.assertFalse(batch.attachment_id.public)
        self.assertFalse(batch.attachment_id.access_token)
        self.assertEqual(batch.uploaded_by, self.users['purchase'])
        self.assertTrue(batch.uploaded_at)
        self.assertEqual(batch.row_ids[0].raw_cells[0]['value'], '000123')
        self.assertEqual(batch.row_ids[1].raw_cells[2]['value'], '0')
        self.assertFalse(self.revision.line_ids)
        with self.assertRaises(ValidationError):
            binary_bytes(b'not an Odoo binary abstraction')

    def test_xlsx_actual_upload_and_explicit_worksheet_flow(self):
        raw = workbook_bytes(sheets={'INSTRUCTIONS': [['Instructions'], ['Ignore this sheet']]})
        wizard = self._wizard(raw, 'prices.xlsx')
        action = wizard.action_upload_extract()
        self.assertEqual(action['res_model'], WIZARD)
        self.assertFalse(wizard.result_batch_id)
        self.assertEqual([s['name'] for s in wizard.available_sheets], ['PRICES', 'INSTRUCTIONS'])
        wizard.worksheet_name = 'PRICES'
        action = wizard.action_upload_extract()
        batch = self._as(self.env[BATCH].browse(action['res_id']))
        self.assertEqual(batch.state, 'extracted')
        self.assertEqual(batch.extracted_row_count, 1)
        self.assertEqual(batch.worksheet_name, 'PRICES')
        self.assertEqual(batch.sheet_index, 0)
        self.assertEqual(batch.attachment_id.raw.content, raw)
        self.assertFalse(wizard.upload_file)

    def test_duplicate_fingerprint_and_correction_are_distinct(self):
        original = self._upload()
        renamed = self._upload(name='renamed.csv')
        changed = self._upload(CSV.replace(b'115', b'116'))
        self.assertEqual(renamed.state, 'duplicate_review')
        self.assertFalse(renamed.row_ids)
        self.assertEqual(renamed.sha256_digest, original.sha256_digest)
        self.assertNotEqual(renamed.evidence_id, original.evidence_id)
        self.assertEqual(original.attachment_id.raw.content, CSV)
        self.assertEqual(changed.state, 'extracted')
        self.assertNotEqual(changed.sha256_digest, original.sha256_digest)
        with self.assertRaises(UserError):
            renamed.action_extract()

    def test_duplicate_scope_company_vendor_and_authorized_visibility(self):
        self._upload()
        other_company = self._upload(role='purchase_b')
        self.assertEqual(other_company.state, 'extracted')
        other_vendor = self.env['res.partner'].create({'name': 'PR05 Another Vendor'})
        revision = self._revision_for(self.users['purchase'])
        revision.with_user(self.users['purchase']).vendor_id = other_vendor
        self.assertEqual(self._upload(revision=revision).state, 'extracted')
        # An ordinary preparer must not learn about another preparer's private source.
        self.assertEqual(self._upload(role='other', revision=self.other_revision).state, 'extracted')

    def test_double_click_and_repeated_extraction_are_idempotent(self):
        wizard = self._wizard()
        first = wizard.action_upload_extract()
        second = wizard.action_upload_extract()
        self.assertEqual(first['res_id'], second['res_id'])
        batch = self._as(self.env[BATCH].browse(first['res_id']))
        row_ids, attempt_ids = batch.row_ids.ids, batch.attempt_ids.ids
        batch.action_extract()
        self.assertEqual(batch.row_ids.ids, row_ids)
        self.assertEqual(batch.attempt_ids.ids, attempt_ids)

    def test_failed_encoding_corrected_retry_retains_failure_and_source(self):
        raw = 'Code,Description\n000123,café\n'.encode('cp1252')
        batch = self._upload(raw)
        self.assertEqual(batch.state, 'extraction_failed')
        self.assertFalse(batch.row_ids)
        self.assertEqual(batch.error_code, 'encoding')
        first_attempt = batch.attempt_ids
        self.assertEqual(first_attempt.state, 'failed')
        batch.csv_encoding = 'cp1252'
        batch.action_extract()
        self.assertEqual(batch.state, 'extracted')
        self.assertEqual(batch.extracted_row_count, 1)
        self.assertEqual(len(batch.attempt_ids), 2)
        self.assertEqual(first_attempt.state, 'failed')
        self.assertEqual(first_attempt.options['csv_encoding'], 'utf-8-sig')
        self.assertEqual(batch.attachment_id.raw.content, raw)
        self.assertEqual(batch.sha256_digest, hashlib.sha256(raw).hexdigest())
        batch.action_extract()
        self.assertEqual(len(batch.row_ids), 1)

    def test_row_persistence_failure_rolls_back_all_staged_rows(self):
        model_class = type(self.env[ROW])
        original = model_class._stage
        calls = []
        def failing_stage(records, batch, rows):
            created = original(records, batch, rows)
            calls.append(created.ids)
            raise DatabaseError('private/path and secret SQL payload')
        with patch.object(model_class, '_stage', failing_stage):
            batch = self._upload()
        self.assertTrue(calls)
        self.assertEqual(batch.state, 'extraction_failed')
        self.assertEqual(batch.extracted_row_count, 0)
        self.assertFalse(batch.row_ids)
        self.assertNotIn('secret', batch.error_summary)
        self.assertNotIn('private/path', batch.error_summary)
        self.assertTrue(batch.evidence_id.attachment_id)
        batch.action_extract()
        self.assertEqual(batch.state, 'extracted')
        self.assertEqual(len(batch.row_ids), 2)

    def test_parser_failure_header_only_and_no_false_success(self):
        for raw in (b'Code,Price\n', b'Code,Price\n1,"bad quote'):
            batch = self._upload(raw)
            self.assertEqual(batch.state, 'extraction_failed')
            self.assertFalse(batch.row_ids)
            self.assertEqual(batch.technical_error_count, 1)
            self.assertTrue(batch.error_summary)
            self.assertEqual(batch.attachment_id.raw.content, raw)

    def test_interrupted_attempt_remains_recoverable_and_cancellation_blocks_retry(self):
        existing_batches = self.env[BATCH].search([])
        with patch.object(parser, 'extract', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt), self.cr.savepoint():
                self._upload()
        self.assertEqual(self.env[BATCH].search([]), existing_batches)
        failed = self._upload(b'Header\n')
        failed.action_cancel()
        self.assertEqual(failed.state, 'cancelled')
        self.assertTrue(failed.attachment_id)
        with self.assertRaises(UserError):
            failed.action_extract()

    def test_company_resource_policy_limits_and_oversized_input(self):
        limits = self._as(self.env['vendor.price.revision.import.limit'], 'configuration').create({
            'company_id': self.a.id, 'max_rows': 1, 'max_columns': 3, 'upload_mib': 1})
        batch = self._upload()
        self.assertEqual(batch.state, 'extraction_failed')
        self.assertEqual(batch.error_code, 'row_limit')
        self.assertFalse(batch.row_ids)
        self.assertEqual(batch.attempt_ids.limits['max_rows'], 1)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._wizard(b'x' * (1024 * 1024 + 1))
        with self.assertRaises(ValidationError), self.cr.savepoint():
            limits.max_rows = 0
        with self.assertRaises(AccessError):
            limits.with_user(self.users['purchase']).write({'max_rows': 20000})

    def test_wizard_views_defaults_and_safe_paths(self):
        action = self._as(self.revision).action_import_supplier_file()
        self.assertEqual(action['context']['default_revision_id'], self.revision.id)
        wizard = self._wizard(name='../../sensitive\\prices.csv')
        batch_action = wizard.action_upload_extract()
        batch = self.env[BATCH].browse(batch_action['res_id'])
        self.assertEqual(batch.original_filename, 'prices.csv')
        for model, view in [(WIZARD, 'view_import_wizard_form'), (BATCH, 'view_import_batch_form')]:
            result = self._as(self.env[model]).get_view(view_id=self.env.ref(MODULE + '.' + view).id, view_type='form')
            self.assertTrue(result['arch'])
        self.assertFalse(self.revision.line_ids)

    def test_no_business_price_state_or_scheduler_side_effects(self):
        price = self.env['product.supplierinfo'].create({'partner_id': self.vendor.id,
            'product_tmpl_id': self.product.product_tmpl_id.id, 'price': 85})
        pricelist = self.env['product.pricelist'].create({'name': 'PR05 Existing Customer Pricelist'})
        rule = self.env['product.pricelist.item'].create({'pricelist_id': pricelist.id,
            'applied_on': '1_product', 'product_tmpl_id': self.product.product_tmpl_id.id,
            'compute_price': 'fixed', 'fixed_price': 200})
        def notification_counts():
            return tuple(self.env[model].search_count([]) for model in ('mail.mail', 'mail.message', 'mail.activity'))
        before = (price.price, price.write_date, self.product.standard_price, self.product.list_price,
                  self.revision.state, self.revision.write_date, self.env['ir.cron'].search_count([]),
                  rule.fixed_price, rule.write_date, notification_counts())
        self._upload()
        self.assertEqual(before, (price.price, price.write_date, self.product.standard_price, self.product.list_price,
            self.revision.state, self.revision.write_date, self.env['ir.cron'].search_count([]),
            rule.fixed_price, rule.write_date, notification_counts()))
        self.assertFalse(self.revision.line_ids)
        self.assertEqual(self.revision.state, 'draft')

    def test_bounded_500_row_extract_count_and_idempotency(self):
        raw = ('Code,Price\n' + ''.join(f'{i:06d},{i}\n' for i in range(500))).encode()
        started = time.monotonic()
        batch = self._upload(raw)
        elapsed = time.monotonic() - started
        self.assertEqual(batch.extracted_row_count, 500)
        self.assertEqual(len(batch.row_ids), 500)
        batch.action_extract()
        self.assertEqual(len(batch.row_ids), 500)
        logging.getLogger(__name__).info('PR05_WORKLOAD rows=500 seconds=%.3f (single local fixture; memory NOT_MEASURED)', elapsed)


@tagged('post_install', '-at_install')
class TestImportSecurity(IntakeFixtures, TransactionCase):
    def test_company_ownership_batch_row_attempt_and_attachment_boundaries(self):
        batch = self._upload(role='purchase_b')
        for records in (batch, batch.row_ids, batch.attempt_ids, batch.evidence_id, batch.attachment_id):
            for fields in (['id'], None):
                with self.assertRaises(AccessError):
                    self._as(records).read(fields)
            with self.assertRaises(AccessError):
                self._as(records).export_data(['id'])
        with self.assertRaises(AccessError):
            self._as(batch.attachment_id)._can_return_content('raw')
        with self.assertRaises(AccessError):
            self._as(batch.attachment_id)._to_http_stream()
        for model in (BATCH, ROW, ATTEMPT):
            scoped = self._as(self.env[model])
            self.assertFalse(scoped.search([('company_id', '=', self.b.id)]))
            self.assertFalse(scoped._read_group([('company_id', '=', self.b.id)], ['company_id'], ['__count']))

    def test_role_visibility_and_read_only_audit(self):
        batch = self._upload()
        for role in ('auditor', 'finance', 'director', 'pricing', 'manager'):
            scoped = self._as(batch, role)
            self.assertEqual(scoped.read(['state'])[0]['state'], 'extracted')
            self.assertEqual(self._as(batch.attachment_id, role).raw.content, CSV)
            if role != 'manager':
                with self.assertRaises(AccessError):
                    scoped.action_extract()
            with self.assertRaises(AccessError):
                scoped.write({'state': 'uploaded'})
        for role in ('sales', 'portal', 'employee', 'configuration', 'other'):
            for records in (batch, batch.row_ids, batch.attempt_ids, batch.attachment_id):
                with self.assertRaises(AccessError):
                    self._as(records, role).read(['id'])
        public = self.env.ref('base.public_user')
        with self.assertRaises(AccessError):
            batch.with_user(public).read(['id'])

    def test_upload_authorization_and_foreign_drafts(self):
        for role in ('sales', 'auditor', 'finance', 'director', 'pricing', 'configuration', 'employee', 'portal', 'other'):
            with self.subTest(role=role), self.assertRaises((AccessError, UserError)), self.cr.savepoint():
                self._wizard(role=role)
        with self.assertRaises(AccessError), self.cr.savepoint():
            self._wizard(revision=self.revision_b)
        with self.assertRaises(AccessError), self.cr.savepoint():
            self._wizard(company_id=self.b.id)
        action = self._as(self.revision, 'manager').action_import_supplier_file()
        self.assertEqual(action['res_model'], WIZARD)

    def test_direct_orm_state_row_evidence_and_context_forgery_denied(self):
        for model in (BATCH, ROW, ATTEMPT):
            with self.assertRaises(AccessError):
                self._as(self.env[model]).create({'revision_id': self.revision.id, 'state': 'extracted'})
        with self.assertRaises(AccessError), self.cr.savepoint():
            self._wizard(result_batch_id=1)
        wizard = self._wizard()
        wizard = wizard.with_context(default_public=True, default_access_token='forged', default_state='extracted',
            default_company_id=self.b.id, default_raw_cells=[{'value': 'forged'}])
        action = wizard.action_upload_extract()
        batch = self._as(self.env[BATCH].browse(action['res_id']))
        self.assertEqual(batch.company_id, self.a)
        self.assertFalse(batch.attachment_id.public)
        self.assertFalse(batch.attachment_id.access_token)
        self.assertNotIn('forged', str(batch.row_ids.mapped('raw_cells')))
        for record in (batch, batch.row_ids, batch.attempt_ids, batch.evidence_id):
            with self.assertRaises(AccessError):
                record.write({'company_id': self.b.id})
        for values in ({'attachment_id': batch.attachment_id.id}, {'sha256_digest': 'forged'}, {'import_batch_id': batch.id}):
            with self.assertRaises(AccessError):
                self._as(self.env[EVIDENCE]).create(dict(values, revision_id=self.revision.id, name='forged'))

    def test_attachment_immutability_token_copy_and_reassignment(self):
        batch = self._upload()
        attachment = batch.attachment_id
        for values in ({'raw': b'changed'}, {'public': True}, {'access_token': 'forged'},
                       {'res_id': self.revision_b.id}, {'res_model': 'res.partner'},
                       {'company_id': self.b.id}, {'vpr_source_evidence_id': False}):
            with self.assertRaises(AccessError):
                attachment.write(values)
        with self.assertRaises(AccessError):
            attachment.unlink()
        with self.assertRaises(AccessError):
            attachment.generate_access_token()
        with self.assertRaises(AccessError):
            attachment._can_return_content('raw', 'forged')
        with self.assertRaises(AccessError):
            attachment.copy({'res_model': 'res.partner', 'res_id': self.vendor.id})
        with self.assertRaises(AccessError):
            self._as(self.env['ir.attachment']).with_context(default_vpr_source_evidence_id=batch.evidence_id.id).create({'name': 'forged', 'raw': b'forged'})
        self.assertEqual(attachment.raw.content, CSV)

    def test_staging_nested_commands_and_raw_exports(self):
        batch = self._upload()
        with self.assertRaises(AccessError):
            batch.row_ids.write({'batch_id': 999})
        with self.assertRaises(AccessError):
            batch.write({'row_ids': [Command.clear()]})
        with self.assertRaises(AccessError):
            batch.row_ids.unlink()
        with self.assertRaises(AccessError):
            batch.evidence_id.write({'filename': 'replaced.csv'})
        with self.assertRaises(UserError):
            self._as(batch.row_ids, 'auditor').export_data(['source_row'])
        self.users['auditor'].group_ids = [Command.link(self.env.ref('base.group_allow_export').id)]
        self.assertEqual(self._as(batch.row_ids, 'auditor').export_data(['source_row'])['datas'], [[2], [3]])
        with self.assertRaises(AccessError):
            self._as(batch.row_ids, 'sales').export_data(['raw_cells'])

    def test_protected_revision_and_removed_role_cannot_intake(self):
        wizard = self._wizard()
        self.env.cr.execute('UPDATE vendor_price_revision SET state = %s WHERE id = %s', ['approved', self.revision.id])
        self.revision.invalidate_recordset(['state'])
        with self.assertRaises(UserError):
            wizard.action_upload_extract()
        self.env.cr.execute('UPDATE vendor_price_revision SET state = %s WHERE id = %s', ['draft', self.revision.id])
        self.revision.invalidate_recordset(['state'])
        self.users['purchase'].active = False
        with self.assertRaises(AccessError):
            wizard.action_upload_extract()


@tagged('post_install', '-at_install')
class TestImportDownload(IntakeFixtures, HttpCase):
    def test_original_content_requires_current_authorized_user(self):
        batch = self._upload()
        foreign = self._upload(role='purchase_b')
        self.authenticate(self.users['purchase'].login, 'unused-test-only')
        response = self.url_open('/web/content/%s?download=true' % batch.attachment_id.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, CSV)
        denied = self.url_open('/web/content/%s?download=true' % foreign.attachment_id.id)
        self.assertIn(denied.status_code, (403, 404))
        self.authenticate(self.users['sales'].login, 'unused-test-only')
        denied = self.url_open('/web/content/%s?download=true' % batch.attachment_id.id)
        self.assertIn(denied.status_code, (403, 404))
        self.authenticate(None, None)
        denied = self.url_open('/web/content/%s?download=true' % batch.attachment_id.id)
        self.assertIn(denied.status_code, (403, 404))
