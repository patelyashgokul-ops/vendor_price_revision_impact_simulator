import csv
import io
import time
from unittest.mock import patch

from psycopg2 import DatabaseError

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from ..models import structural_validation as lexical
from ..models.import_intake import BATCH, ROW
from ..models.import_validation import MAPPING, RUN, RESULT, ISSUE, CORRECTION, EVENT, PREFIX
from .test_import_intake import IntakeFixtures

HEADERS = ['Item', 'Description', 'Price', 'Currency', 'UoM', 'MOQ', 'Effective Date', 'Reference', 'Notes']
TARGETS = ['vendor_product_code', 'vendor_product_name', 'proposed_price_raw', 'currency_raw', 'purchase_uom_raw', 'min_qty_raw', 'effective_date_raw', 'supplier_reference_raw', 'notes_raw']
VALID = ['000123', 'LED उजाला', '115.00', 'INR', 'PCS', '1', '2026-11-01', 'Ref1', 'Terms']


def csv_bytes(rows, headers=None):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(headers or HEADERS)
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


@tagged('post_install', '-at_install')
class TestStructuralHelpers(TransactionCase):
    def test_decimal_conventions_are_exact_and_explicit(self):
        self.assertEqual(lexical.decimal_text('115.00'), '115.00')
        for text, style, expected in [('1,150.50', 'comma_group', '1150.50'), ('1.150,50', 'dot_group', '1150.50'), ('1 150,50', 'space_group', '1150.50')]:
            self.assertEqual(lexical.decimal_text(text, style), expected)
        for text in ('11O', 'NaN', 'Infinity', '--115', '1,150', '1e2', ''):
            with self.assertRaises(ValueError):
                lexical.decimal_text(text)
        self.assertNotEqual(lexical.duplicate_key({}, {'proposed_price_raw':'123456789012345678901234567890.1'}),
                            lexical.duplicate_key({}, {'proposed_price_raw':'123456789012345678901234567890.2'}))

    def test_lexical_classification_zero_missing_negative_and_dates(self):
        base = dict(zip(TARGETS, VALID))
        self.assertEqual(lexical.validate_values(base, {})[0], 'structurally_ready')
        for field, value, code, status in [('proposed_price_raw', '', 'MISSING_REQUIRED_VALUE', 'blocked'),
            ('proposed_price_raw', '0', 'ZERO_PRICE_REVIEW', 'needs_review'),
            ('proposed_price_raw', '-1', 'NEGATIVE_PRICE', 'blocked'),
            ('min_qty_raw', '-1', 'INVALID_QUANTITY_FORMAT', 'blocked'),
            ('effective_date_raw', '11/01/2026', 'AMBIGUOUS_DATE_FORMAT', 'needs_review'),
            ('effective_date_raw', '2026-02-30', 'INVALID_DATE_FORMAT', 'blocked'),
            ('currency_raw', 'INRR', 'INVALID_CURRENCY_TEXT', 'blocked')]:
            with self.subTest(field=field, value=value):
                result = lexical.validate_values(dict(base, **{field: value}), {})
                self.assertEqual(result[0], status)
                self.assertIn(code, [i['code'] for i in result[2]])
        result = lexical.validate_values(dict(base, effective_date_raw='01/11/2026'), {}, date_style='dmy')
        self.assertEqual(result[1]['effective_date_raw'], '2026-11-01')


class ReviewFixtures(IntakeFixtures):
    def _review_batch(self, rows=None, headers=None, role='purchase'):
        batch = self._upload(csv_bytes(rows or [VALID], headers), role=role)
        self.assertEqual(batch.state, 'extracted')
        return batch

    def _map(self, batch, inherit=False):
        rows = []
        for number, target in enumerate(TARGETS, 1):
            if inherit and target in ('currency_raw', 'effective_date_raw'):
                continue
            rows.append({'batch_id': batch.id, 'column_number': number, 'target': target})
        self.env[MAPPING].with_env(batch.env).create(rows)
        if inherit:
            batch.write({'inherit_currency': True, 'inherit_date': True})
        return batch

    def _counts(self, batch):
        return batch.ready_rows, batch.blocked_rows, batch.review_rows, batch.excluded_rows, batch.pending_rows


@tagged('post_install', '-at_install')
class TestImportMapping(ReviewFixtures, TransactionCase):
    def test_valid_explicit_mapping_ready_preserves_source(self):
        batch = self._review_batch()
        before = batch.attachment_id.raw.content, batch.sha256_digest, batch.row_ids.raw_cells
        self.assertEqual(batch.pending_rows, 1)
        self.assertEqual(batch.mapping_status, 'not_mapped')
        self.assertFalse(batch.action_validate_structure())
        self.assertEqual(batch.validation_state, 'mapping_incomplete')
        self._map(batch)
        self.assertEqual(batch.mapping_status, 'ready')
        self.assertTrue(batch.action_validate_structure())
        self.assertEqual(batch.row_ids.validation_status, 'structurally_ready')
        self.assertEqual(batch.row_ids.current_result_id.effective_values['vendor_product_code'], '000123')
        self.assertEqual(before, (batch.attachment_id.raw.content, batch.sha256_digest, batch.row_ids.raw_cells))
        self.assertFalse(self.revision.line_ids)

    def test_duplicate_empty_headers_are_identified_by_position(self):
        batch = self._review_batch(headers=['Price', '', 'Price'] + HEADERS[3:])
        self._map(batch)
        price = batch.mapping_ids.filtered(lambda r: r.target == 'proposed_price_raw')
        self.assertEqual(price.column_number, 3)
        self.assertEqual(price.header_text, 'Price')
        self.assertEqual(batch.mapping_ids.filtered(lambda r: r.column_number == 2).header_text, '')
        batch.action_validate_structure()
        self.assertEqual(batch.row_ids.validation_status, 'structurally_ready')

    def test_mapping_conflicts_positions_and_unsupported_targets(self):
        batch = self._review_batch()
        self._map(batch)
        for values, exception in [({'column_number': 99, 'target': 'product_identifier_raw'}, ValidationError),
                ({'column_number': 0, 'target': 'product_identifier_raw'}, ValidationError),
                ({'column_number': 1, 'target': 'product_identifier_raw'}, ValidationError),
                ({'column_number': 9, 'target': 'proposed_price_raw'}, ValidationError),
                ({'column_number': 1, 'target': 'product_id'}, ValueError)]:
            with self.assertRaises(exception), self.cr.savepoint():
                self.env[MAPPING].with_env(batch.env).create(dict(values, batch_id=batch.id))

    def test_mapping_change_invalidates_status_counts_and_keeps_history(self):
        batch = self._map(self._review_batch())
        batch.action_validate_structure()
        previous, version = batch.current_run_id, batch.review_version
        batch.mapping_ids.filtered(lambda r: r.target == 'proposed_price_raw').active = False
        self.assertGreater(batch.review_version, version)
        self.assertFalse(batch.current_run_id)
        self.assertEqual(batch.validation_state, 'validation_stale')
        self.assertEqual(batch.row_ids.validation_status, 'pending_validation')
        self.assertEqual(self._counts(batch), (0, 0, 0, 0, 1))
        self.assertFalse(previous.is_current)
        self.assertEqual(previous.result_ids.status, 'structurally_ready')
        self.assertTrue(batch.review_event_ids)
        with self.assertRaises(UserError):
            batch.get_structurally_ready_rows()
        price_mapping=batch.mapping_ids.filtered(lambda row:row.target=='proposed_price_raw')
        self.assertTrue(price_mapping)
        self.assertFalse(price_mapping.active)
        price_mapping.active=True
        self.assertTrue(batch.action_validate_structure())
        self.assertEqual(batch.ready_rows,1)

    def test_inherited_defaults_have_revision_provenance_and_stale_date(self):
        self._as(self.revision).proposed_effective_date = '2026-11-01'
        batch = self._map(self._review_batch(), inherit=True)
        batch.action_validate_structure()
        result = batch.row_ids.current_result_id
        for field in ('currency_raw', 'effective_date_raw'):
            self.assertEqual(result.provenance[field]['source'], 'REVISION_HEADER')
        self._as(self.revision).proposed_effective_date = '2026-12-01'
        self.assertFalse(batch.current_run_id)
        batch.action_validate_structure()
        self.assertEqual(batch.row_ids.current_result_id.parsed_candidates['effective_date_raw'], '2026-12-01')

    def test_defaults_never_override_blank_mapped_values_or_conflict_silently(self):
        row = list(VALID); row[3] = ''
        batch = self._map(self._review_batch([row]))
        batch.action_validate_structure()
        self.assertEqual(batch.blocked_rows, 1)
        batch.inherit_currency = True
        self.assertEqual(batch.mapping_status, 'incomplete')
        self.assertFalse(batch.action_validate_structure())


@tagged('post_install', '-at_install')
class TestImportValidation(ReviewFixtures, TransactionCase):
    def test_numeric_missing_zero_invalid_nonfinite_and_negative_candidates(self):
        rows = []
        for index, price in enumerate(['115', '', '0', '-1', '11O', 'NaN', 'Infinity', '--115', '1,150.50']):
            row = list(VALID); row[0] = f'{index:06d}'; row[2] = price; rows.append(row)
        batch = self._map(self._review_batch(rows))
        batch.action_validate_structure()
        self.assertEqual(self._counts(batch), (1, 6, 2, 0, 0))
        result = batch.row_ids[1].current_result_id
        self.assertNotIn('proposed_price_raw', result.parsed_candidates)
        self.assertEqual(batch.row_ids[2].current_result_id.parsed_candidates['proposed_price_raw'], '0')

    def test_identifiers_unicode_lengths_currency_uom_and_missing_quantity(self):
        rows = []
        for changes in [{0: '', 1: ''}, {3: '??'}, {4: ''}, {5: ''}, {5: 'abc'}, {5: '-1'}, {0: 'x' * 257}]:
            row = list(VALID)
            for index, value in changes.items(): row[index] = value
            rows.append(row)
        batch = self._map(self._review_batch(rows))
        batch.action_validate_structure()
        self.assertEqual(batch.blocked_rows, len(rows))
        self.assertEqual(batch.ready_rows, 0)
        self.assertNotEqual(batch.validation_state, 'structural_validation_complete')

    def test_numeric_date_policies_are_explicit_and_versioned(self):
        row = list(VALID);row[2]='1.150,50';row[6]='01/11/2026'
        batch = self._map(self._review_batch([row]))
        batch.action_validate_structure()
        self.assertNotEqual(batch.ready_rows, 1)
        batch.write({'number_style': 'dot_group', 'date_style': 'dmy'})
        self.assertFalse(batch.current_run_id)
        batch.action_validate_structure()
        self.assertEqual(batch.ready_rows, 1)
        self.assertEqual(batch.row_ids.current_result_id.parsed_candidates['proposed_price_raw'], '1150.50')

    def test_formula_like_cells_remain_untrusted_and_not_executed(self):
        row = list(VALID); row[1] = '=UNTRUSTED()'
        batch = self._map(self._review_batch([row]))
        batch.action_validate_structure()
        self.assertEqual(batch.row_ids.validation_status, 'needs_review')
        self.assertIn('MANUAL_REVIEW_REQUIRED', batch.row_ids.current_issue_ids.mapped('code'))
        self.assertEqual(batch.row_ids.raw_cells[1]['value'], '=UNTRUSTED()')

    def test_duplicate_groups_do_not_collapse_tiers_dates_currency_price_or_terms(self):
        rows = [list(VALID), list(VALID)]
        rows[1][0] = ' 000123 '
        for index, value in [(5, '100'), (2, '109'), (3, 'AED'), (6, '2026-12-01'), (8, 'Other terms')]:
            row=list(VALID);row[index]=value;rows.append(row)
        batch = self._map(self._review_batch(rows))
        batch.action_validate_structure()
        self.assertEqual((batch.ready_rows, batch.review_rows), (5, 2))
        self.assertEqual(batch.row_ids[0].current_result_id.duplicate_rows, [2, 3])
        self.assertEqual(batch.row_ids[1].current_result_id.duplicate_rows, [2, 3])
        self.assertEqual(len(batch.row_ids), 7)
        self.assertEqual(self.env[ROW].with_env(batch.env).search([('batch_id','=',batch.id),
            ('current_result_id.has_duplicates','=',True)]),batch.row_ids[:2])

    def test_idempotent_runs_do_not_accumulate_current_issues(self):
        row=list(VALID);row[2]='11O';row[3]='?'
        batch=self._map(self._review_batch([row]))
        batch.action_validate_structure()
        run, issues = batch.current_run_id, batch.row_ids.current_issue_ids
        self.assertEqual(batch.blocked_rows, 1)
        self.assertEqual(batch.active_error_issues, 2)
        for _ in range(2): self.assertTrue(batch.action_validate_structure())
        self.assertEqual(batch.current_run_id, run)
        self.assertEqual(batch.row_ids.current_issue_ids, issues)
        self.assertEqual(len(batch.validation_run_ids), 1)

    def test_500_row_reference_counts_and_no_product_or_fx_resolution(self):
        rows=[]
        for index in range(500):
            row=list(VALID);row[0]=f'UNKNOWN-{index:06d}';row[3]='ZZZ'
            if index >= 480: row[2] = '11O' if index < 492 else '0'
            rows.append(row)
        batch=self._map(self._review_batch(rows))
        began=time.monotonic();batch.action_validate_structure();elapsed=time.monotonic()-began
        self.assertEqual(self._counts(batch),(480,12,8,0,0))
        self.assertEqual(sum(self._counts(batch)),batch.extracted_row_count)
        self.assertEqual(len(batch.get_structurally_ready_rows()),480)
        self.assertFalse(self.revision.line_ids)
        import logging
        logging.getLogger(__name__).info('PR06_WORKLOAD rows=500 seconds=%.3f; product/FX resolution deferred; memory NOT_MEASURED',elapsed)

    def test_atomic_failure_and_retry_no_partial_current_result(self):
        batch=self._map(self._review_batch())
        with patch.object(type(self.env[RESULT]), '_record', side_effect=DatabaseError('private SQL secret')):
            self.assertFalse(batch.action_validate_structure())
        self.assertEqual(batch.validation_state,'validation_failed')
        self.assertFalse(batch.current_run_id)
        self.assertFalse(batch.row_ids.current_result_id)
        self.assertFalse(self.env[RESULT].search([('batch_id','=',batch.id)]))
        self.assertEqual(batch.validation_run_ids.state,'failed')
        self.assertNotIn('secret',batch.validation_run_ids.error_summary)
        self.assertTrue(batch.action_validate_structure())
        self.assertEqual(batch.ready_rows,1)

    def test_interruption_rolls_back_uncommitted_results(self):
        batch=self._map(self._review_batch())
        with patch.object(lexical,'validate_values',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt),self.cr.savepoint(): batch.action_validate_structure()
        self.assertFalse(batch.current_run_id)
        self.assertTrue(batch.action_validate_structure())


@tagged('post_install', '-at_install')
class TestImportCorrections(ReviewFixtures,TransactionCase):
    def test_overlay_history_revalidation_original_bytes_and_digest(self):
        row=list(VALID);row[2]='11O'
        batch=self._map(self._review_batch([row]));batch.action_validate_structure()
        raw, digest, cells = batch.attachment_id.raw.content,batch.sha256_digest,batch.row_ids.raw_cells
        old_run=batch.current_run_id
        source=batch.row_ids
        source.action_correct('proposed_price_raw','110','Supplier typing error')
        self.assertEqual(source.validation_status,'pending_validation')
        self.assertEqual(source.effective_values['proposed_price_raw'],'110')
        self.assertFalse(batch.current_run_id)
        batch.action_validate_structure()
        self.assertEqual(source.validation_status,'structurally_ready')
        self.assertFalse(old_run.is_current)
        self.assertEqual(old_run.result_ids.issue_ids.code,'INVALID_PRICE_FORMAT')
        self.assertFalse(source.current_issue_ids)
        source.action_correct('proposed_price_raw','109','Updated supplier evidence')
        events=source.correction_ids
        self.assertEqual(events.mapped('previous_value'),['11O','110'])
        self.assertEqual(events.mapped('new_value'),['110','109'])
        self.assertEqual(events.mapped('original_value'),['11O','11O'])
        self.assertEqual(events.actor_id,self.users['purchase'])
        self.assertTrue(all(events.mapped('corrected_at')))
        self.assertEqual((raw,digest,cells),(batch.attachment_id.raw.content,batch.sha256_digest,source.raw_cells))
        self.assertFalse(self.revision.line_ids)

    def test_exclusion_reinstatement_and_duplicate_resolution(self):
        batch=self._map(self._review_batch([VALID,VALID]));batch.action_validate_structure()
        source=batch.row_ids[1]
        with self.assertRaises(ValidationError):source.action_set_excluded(True,'')
        source.action_set_excluded(True,'Duplicate selected for exclusion')
        batch.action_validate_structure()
        self.assertEqual(self._counts(batch),(1,0,0,1,0))
        self.assertEqual(batch.get_structurally_ready_rows(),batch.row_ids[0])
        source.action_set_excluded(False,'Supplier confirmed distinct row')
        self.assertEqual(source.validation_status,'pending_validation')
        batch.action_validate_structure()
        self.assertEqual(batch.review_rows,2)
        source.action_correct('min_qty_raw','100','Distinct quantity tier')
        batch.action_validate_structure()
        self.assertEqual(batch.ready_rows,2)
        self.assertEqual(source.correction_ids.mapped('operation'),['exclude','reinstate','correct'])

    def test_correction_reason_allowlist_noop_and_wizard(self):
        batch=self._map(self._review_batch());source=batch.row_ids
        for field,value,reason in [('company_id','1','bad'),('proposed_price_raw','110',''),('proposed_price_raw',None,'bad')]:
            with self.assertRaises(ValidationError):source.action_correct(field,value,reason)
        source.action_correct('proposed_price_raw','115.00','Unchanged')
        self.assertFalse(source.correction_ids)
        action=source.action_open_correction()
        wizard=self.env[PREFIX+'review.wizard'].with_env(batch.env).create({'row_id':source.id,'new_value':'110','reason':'Explicit edit'})
        wizard.action_save_review()
        self.assertEqual(source.effective_values['proposed_price_raw'],'110')
        self.assertEqual(action['res_model'],wizard._name)
        source.action_correct('notes_raw','=UNTRUSTED()','Preserve literal source review text')
        self.users['purchase'].group_ids=[Command.link(self.env.ref('base.group_allow_export').id)]
        event=source.correction_ids[-1]
        self.assertEqual(event.export_data(['new_value'])['datas'],[["'=UNTRUSTED()"]])
        self.assertEqual(event.new_value,'=UNTRUSTED()')

    def test_no_business_operational_or_notification_side_effects(self):
        price=self.env['product.supplierinfo'].create({'partner_id':self.vendor.id,'product_tmpl_id':self.product.product_tmpl_id.id,'price':85})
        batch=self._map(self._review_batch());before=(price.price,price.write_date,self.product.standard_price,self.product.list_price,self.revision.state,self.revision.write_date)
        notifications=tuple(self.env[m].search_count([]) for m in ('mail.mail','mail.message','mail.activity','ir.cron'))
        batch.action_validate_structure();batch.row_ids.action_correct('proposed_price_raw','109','Supplier correction');batch.action_validate_structure()
        batch.row_ids.action_set_excluded(True,'Out of scope');batch.action_validate_structure()
        self.assertEqual(before,(price.price,price.write_date,self.product.standard_price,self.product.list_price,self.revision.state,self.revision.write_date))
        self.assertEqual(notifications,tuple(self.env[m].search_count([]) for m in ('mail.mail','mail.message','mail.activity','ir.cron')))
        self.assertFalse(self.revision.line_ids)


@tagged('post_install','-at_install')
class TestImportValidationSecurity(ReviewFixtures,TransactionCase):
    def test_read_only_roles_cannot_mutate_review(self):
        row=list(VALID);row[2]='11O';batch=self._map(self._review_batch([row]));batch.action_validate_structure()
        batch.row_ids.action_correct('proposed_price_raw','110','Fix');batch.action_validate_structure()
        for role in ('finance','auditor','director','pricing'):
            scoped=self._as(batch,role)
            self.assertEqual(scoped.read(['ready_rows'])[0]['ready_rows'],1)
            for operation in (lambda:scoped.action_validate_structure(),lambda:self._as(batch.row_ids,role).action_correct('proposed_price_raw','109','bad'),lambda:self._as(batch.row_ids,role).action_set_excluded(True,'bad')):
                with self.assertRaises(AccessError):operation()
        for role in ('sales','employee','portal','configuration','other'):
            for records in (batch.mapping_ids,batch.validation_run_ids,batch.current_run_id.result_ids,batch.correction_ids,batch.review_event_ids):
                with self.assertRaises(AccessError):self._as(records,role).read(['id'])

    def test_foreign_company_read_export_group_and_mutation_boundaries(self):
        row=list(VALID);row[2]='11O';batch=self._map(self._review_batch([row],role='purchase_b'));batch.action_validate_structure()
        batch.row_ids.action_correct('proposed_price_raw','110','Fix')
        for model in (MAPPING,RUN,RESULT,ISSUE,CORRECTION,EVENT):
            records=self.env[model].search([('batch_id','=',batch.id)])
            self.assertTrue(records)
            with self.assertRaises(AccessError):self._as(records).read(['id'])
            with self.assertRaises(AccessError):self._as(records).export_data(['id'])
            scoped=self._as(self.env[model])
            self.assertFalse(scoped.search([('company_id','=',self.b.id)]))
            self.assertFalse(scoped._read_group([('company_id','=',self.b.id)],['company_id'],['__count']))
        with self.assertRaises(AccessError):self._as(batch.row_ids).action_correct('proposed_price_raw','1','forged')
        with self.assertRaises(AccessError):self._as(self.env[MAPPING]).create({'batch_id':batch.id,'column_number':1,'target':'vendor_product_code'})

    def test_direct_forgery_reparenting_nested_commands_and_history_protection(self):
        batch=self._map(self._review_batch());batch.action_validate_structure()
        for model in (RUN,RESULT,ISSUE,CORRECTION,EVENT):
            with self.assertRaises(AccessError):self._as(self.env[model]).create({'batch_id':batch.id})
        for records in (batch,batch.row_ids):
            with self.assertRaises(AccessError):records.write({'validation_status':'structurally_ready'})
        for record in (batch.mapping_ids,batch.validation_run_ids,batch.current_run_id.result_ids):
            with self.assertRaises(AccessError):record.write({'company_id':self.b.id})
            with self.assertRaises(AccessError):record.unlink()
        with self.assertRaises(AccessError):batch.write({'mapping_ids':[Command.clear()]})
        foreign=self._map(self._review_batch(role='purchase_b'))
        with self.assertRaises(AccessError):batch.write({'mapping_ids':[Command.update(foreign.mapping_ids[0].id,{'active':False})]})
        with self.assertRaises(AccessError):batch.row_ids.write({'raw_cells':[]})

    def test_protected_revision_no_intake_mutation_or_approval_forgery(self):
        batch=self._map(self._review_batch())
        self.env.cr.execute('UPDATE vendor_price_revision SET state=%s WHERE id=%s',['approved',self.revision.id]);self.revision.invalidate_recordset(['state'])
        for operation in (lambda:batch.action_validate_structure(),lambda:batch.row_ids.action_correct('proposed_price_raw','1','bad'),lambda:batch.mapping_ids[0].write({'active':False})):
            with self.assertRaises(UserError):operation()
        for method in ('action_approve','action_apply','action_apply_prices'):
            self.assertFalse(hasattr(batch,method))

    def test_review_views_load_and_source_download_remains_protected(self):
        batch=self._map(self._review_batch());batch.action_validate_structure()
        for model,xmlid in [(BATCH,'view_import_batch_form'),(ROW,'view_source_row_review_form'),(PREFIX+'review.wizard','view_review_correction_wizard')]:
            view=self._as(self.env[model]).get_view(view_id=self.env.ref('vendor_price_revision_impact_simulator.'+xmlid).id,view_type='form')
            self.assertTrue(view['arch'])
        with self.assertRaises(AccessError):self._as(batch.attachment_id,'sales')._can_return_content('raw')

    def test_role_union_and_forged_company_context_do_not_bypass_isolation(self):
        foreign=self._map(self._review_batch(role='purchase_b'));foreign.action_validate_structure()
        self.users['purchase'].group_ids=[Command.link(self.env.ref('vendor_price_revision_impact_simulator.group_vpr_finance_manager').id)]
        with self.assertRaises(AccessError):self._as(foreign.mapping_ids).read(['id'])
        with self.assertRaises(AccessError):self._as(foreign).with_context(allowed_company_ids=self.b.ids).action_validate_structure()
        with self.assertRaises(AccessError):self._as(self.env[PREFIX+'review.wizard']).create({'row_id':foreign.row_ids.id,'reason':'forged'})
