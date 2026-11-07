import logging
import time
from unittest.mock import patch

from psycopg2 import DatabaseError

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from ..models.product_resolution import POLICY, REGISTRY, AUDIT, RESOLUTION, WIZARD, key
from ..models.import_intake import BATCH, ROW
from .test_import_validation import ReviewFixtures, VALID


class ProductFixtures(ReviewFixtures):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # An actual upgrade fixture can already own the unique company policy.
        # Reuse it inside the test transaction; preservation checks assert that
        # test teardown retains its values, version, audits and write date.
        cls.policy = cls.env[POLICY].search([('company_id', '=', cls.a.id)]) or cls.env[POLICY].create(
            {'company_id': cls.a.id, 'change_reason': 'Explicit exact identity rules'})
        cls.policy_b = cls.env[POLICY].with_company(cls.b).create({'company_id': cls.b.id, 'change_reason': 'Separate company policy'})
        attribute = cls.env['product.attribute'].create({'name': 'PR07 Color', 'create_variant': 'always'})
        values = cls.env['product.attribute.value'].create([{'name': color, 'attribute_id': attribute.id} for color in ('Red', 'White')])
        cls.template = cls.env['product.template'].create({'name': 'PR07 LED Bulb 12W',
            'attribute_line_ids': [Command.create({'attribute_id': attribute.id, 'value_ids': [Command.set(values.ids)]})]})
        cls.red = cls.template.product_variant_ids.filtered(lambda p: 'Red' in p.product_template_attribute_value_ids.mapped('name'))
        cls.white = cls.template.product_variant_ids - cls.red
        cls.red.default_code = 'LED-12W-RED'
        cls.white.default_code = 'LED-12W-WHT'
        cls.cable = cls.env['product.product'].create({'name': 'PR07 Cable', 'default_code': 'CABLE-001'})
        cls.archived = cls.env['product.product'].create({'name': 'PR07 Archived', 'default_code': 'OLD-SKU-01', 'active': False})
        cls.manager2 = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'PR07 Second Manager', 'login': 'pr07.second.manager@example.invalid',
            'company_id': cls.a.id, 'company_ids': [Command.set(cls.a.ids)],
            'group_ids': [Command.set(cls.env.ref('vendor_price_revision_impact_simulator.group_vpr_purchase_manager').ids)]})

    def _batch(self, codes, role='purchase', vendor=None, dates=None, quantities=None):
        rows = []
        for n, code in enumerate(codes):
            row = list(VALID);row[0] = code
            if dates: row[6] = dates[n]
            if quantities: row[5] = str(quantities[n])
            rows.append(row)
        if vendor:
            revision = self._revision_for(self.users[role])
            revision.with_user(self.users[role]).vendor_id = vendor
            from .test_import_validation import csv_bytes
            batch = self._upload(csv_bytes(rows), role=role, revision=revision)
        else:
            batch = self._review_batch(rows, role=role)
        self._map(batch)
        batch.action_validate_structure()
        return batch

    def _supplier(self, code, product=None, template=None, vendor=None, company=None):
        values = {'partner_id': (vendor or self.vendor).id, 'company_id': (company or self.a).id,
            'product_code': code, 'price': 85, 'product_tmpl_id': (template or product.product_tmpl_id).id}
        if product: values['product_id'] = product.id
        return self.env['product.supplierinfo'].create(values)

    def _verify(self, row, product, begin='2026-01-01', end='2026-12-31', reusable=True, verifier=None):
        proposal = row.action_propose_product(product.id, 'Supplier identity evidence', begin, end, reusable)
        manager = verifier or self.users['manager']
        proposal.with_user(manager).with_context(allowed_company_ids=row.company_id.ids).action_confirm_mapping('Independently checked exact variant')
        return proposal


@tagged('post_install', '-at_install')
class TestProductExactMatching(ProductFixtures, TransactionCase):
    def test_exact_variant_reference_scenario_and_tier_row_counts(self):
        self._supplier('LED-12W', template=self.template)
        batch = self._batch(['LED-12W-RED','LED-12W-WHT','LED-12W','UNKNOWN-001','OLD-SKU-01','LED-12W-RED'], quantities=[1,1,1,1,1,100])
        self.assertTrue(batch.action_match_products())
        rows = batch.row_ids
        self.assertEqual(rows.mapped('product_match_status'), ['auto_matched','auto_matched','ambiguous','unmatched','ineligible','auto_matched'])
        self.assertEqual(rows[0].resolved_product_id, self.red)
        self.assertEqual(rows[1].resolved_product_id, self.white)
        self.assertEqual(rows[5].resolved_product_id, self.red)
        counts = batch.product_counts
        self.assertEqual(counts['eligible_rows'],6)
        self.assertEqual(counts['auto_matched'],3)
        self.assertEqual(counts['distinct_matched_products'],2)
        self.assertEqual(len(batch.get_product_resolved_rows()),3)
        logging.getLogger(__name__).info('PR07_REFERENCE rows=6 eligible=6 auto=3 manual=0 ambiguous=1 unmatched=1 ineligible=1 distinct_products=2')

    def test_exact_vendor_variant_and_single_template_sources(self):
        self._supplier('VENDOR-RED',product=self.red)
        single=self.env['product.product'].create({'name':'PR07 Single variant'})
        self._supplier('VENDOR-SINGLE',template=single.product_tmpl_id)
        batch=self._batch(['VENDOR-RED','VENDOR-SINGLE']);batch.action_match_products()
        self.assertEqual(batch.row_ids.resolved_product_id,self.red|single)
        self.assertEqual(set(batch.row_ids.product_resolution_id.mapped('source')),{'vendor_reference'})

    def test_duplicate_internal_code_and_conflicting_vendor_references_are_ambiguous(self):
        self.env['product.product'].create([{'name':'PR07 Duplicate 1','default_code':'DUP-SKU'}, {'name':'PR07 Duplicate 2','default_code':'DUP-SKU'}])
        self._supplier('CONFLICT',product=self.red);self._supplier('CONFLICT',product=self.cable)
        batch=self._batch(['DUP-SKU','CONFLICT']);batch.action_match_products()
        self.assertEqual(batch.row_ids.mapped('product_match_status'),['ambiguous','ambiguous'])
        self.assertFalse(batch.row_ids.resolved_product_id)

    def test_identifier_case_punctuation_and_leading_zeros_are_preserved(self):
        codes=['000123','AB-001','A/B-001','CaseSensitive']
        products=self.env['product.product'].create([{'name':'PR07 '+code,'default_code':code} for code in codes])
        batch=self._batch(codes+['123','AB001','ab-001','casesensitive']);batch.action_match_products()
        self.assertEqual(batch.row_ids[:4].resolved_product_id,products)
        self.assertEqual(batch.row_ids[4:].mapped('product_match_status'),['unmatched']*4)
        self.assertEqual(key(' 000123 '),'000123')
        self.assertEqual(key('A/B-001'),'A/B-001')

    def test_barcode_requires_explicit_policy_and_designated_input(self):
        self.red.barcode='00000987654321'
        batch=self._batch(['00000987654321']);batch.action_match_products()
        self.assertEqual(batch.row_ids.product_match_status,'unmatched')
        self.policy.write({'barcode_source':'vendor_product_code','change_reason':'Supplier code is explicitly barcode data'})
        batch.action_match_products()
        self.assertEqual(batch.row_ids.resolved_product_id,self.red)
        self.assertEqual(batch.row_ids.product_resolution_id.source,'barcode')

    def test_names_never_auto_match_and_missing_policy_is_review(self):
        batch=self._batch([self.red.name]);batch.action_match_products()
        self.assertEqual(batch.row_ids.product_match_status,'unmatched')
        company=self.env['res.company'].create({'name':'PR07 Unconfigured'})
        user=self.env['res.users'].with_context(no_reset_password=True).create({'name':'PR07 Unconfigured Preparer',
            'login':'pr07.unconfigured@example.invalid','company_id':company.id,'company_ids':[Command.set(company.ids)],
            'group_ids':[Command.set(self.env.ref('vendor_price_revision_impact_simulator.group_vendor_price_revision_user').ids)]})
        self.users['no_policy']=user
        revision=self._revision_for(user)
        from .test_import_validation import csv_bytes
        missing=self._upload(csv_bytes([VALID]),role='no_policy',revision=revision)
        self._map(missing);missing.action_validate_structure();missing.action_match_products()
        self.assertEqual(missing.row_ids.product_match_status,'needs_review')
        self.assertFalse(missing.row_ids.resolved_product_id)

    def test_eligibility_services_purchase_flag_and_single_template_policy(self):
        service=self.env['product.product'].create({'name':'PR07 Service','default_code':'SERVICE','type':'service','purchase_ok':True})
        nonpurchase=self.env['product.product'].create({'name':'PR07 Not for purchase','default_code':'NO-BUY','purchase_ok':False})
        self._supplier('SINGLE-TEMPLATE',template=self.cable.product_tmpl_id)
        self.policy.write({'allow_single_variant':False,'allow_services':False,'change_reason':'Company eligibility controls'})
        batch=self._batch(['SERVICE','NO-BUY','SINGLE-TEMPLATE']);batch.action_match_products()
        self.assertEqual(batch.row_ids.mapped('product_match_status'),['ineligible','ineligible','needs_review'])

    def test_structural_gate_prevents_direct_unready_and_excluded_mapping(self):
        batch=self._batch(['LED-12W-RED','UNKNOWN-001'])
        source=batch.row_ids[0]
        source.action_correct('proposed_price_raw','11O','Structural blocker');batch.action_validate_structure()
        batch.row_ids[1].action_set_excluded(True,'Not in scope');batch.action_validate_structure()
        batch.action_match_products()
        self.assertFalse(batch.product_resolution_ids)
        self.assertEqual(source.product_match_status,'pending_structure')
        self.assertEqual(batch.row_ids[1].product_match_status,'excluded')
        with self.assertRaises(UserError):source.action_propose_product(self.red.id,'No bypass','2026-01-01','2026-12-31')

    def test_repeated_match_is_idempotent_and_status_filter_is_authorized(self):
        batch=self._batch(['LED-12W-RED','MISSING']);batch.action_match_products()
        previous=batch.product_resolution_ids.ids
        batch.action_match_products();batch.action_match_products()
        self.assertEqual(batch.product_resolution_ids.ids,previous)
        found=self.env[ROW].with_env(batch.env).with_context(product_review_batch_id=batch.id).search([('product_match_status','=','auto_matched')])
        self.assertEqual(found,batch.row_ids[0])

    def test_legacy_duplicate_barcode_candidates_are_ambiguous(self):
        # Simulate pre-existing inconsistent master data; production resolution
        # never changes barcodes or bypasses the standard product constraints.
        self.env.cr.execute('UPDATE product_product SET barcode=%s WHERE id IN %s',['PR07-DUP-BAR',tuple((self.red|self.white).ids)])
        (self.red|self.white).invalidate_recordset(['barcode'])
        self.policy.write({'barcode_source':'vendor_product_code','change_reason':'Explicit barcode identity input'})
        batch=self._batch(['PR07-DUP-BAR']);batch.action_match_products()
        self.assertEqual(batch.row_ids.product_match_status,'ambiguous')
        self.assertFalse(batch.row_ids.resolved_product_id)

    def test_matching_failure_is_atomic_and_recoverable(self):
        batch=self._batch(['LED-12W-RED','LED-12W-WHT'])
        original_record=type(self.env[RESOLUTION])._record
        attempted=[]
        def fail_second(records,values):
            attempted.append(values)
            if len(attempted)==2:
                raise DatabaseError('private/path secret SQL')
            return original_record(records,values)
        with patch.object(type(self.env[RESOLUTION]),'_record',fail_second):
            self.assertFalse(batch.action_match_products())
        self.assertEqual(len(attempted),2)
        self.assertEqual(batch.product_matching_state,'failed')
        self.assertFalse(batch.row_ids.product_resolution_id)
        self.assertFalse(batch.product_resolution_ids)
        self.assertNotIn('secret',batch.product_matching_error)
        self.assertTrue(batch.action_match_products())

    def test_500_rows_bulk_identity_lookup_and_distinct_products(self):
        codes=[f'PR07-P-{n:04d}' for n in range(500)]
        self.env['product.product'].create([{'name':code,'default_code':code} for code in codes])
        batch=self._batch(codes)
        searches=[]
        original_search=type(self.env['product.product']).search
        def count_search(records,*args,**kwargs):
            searches.append(1)
            return original_search(records,*args,**kwargs)
        start=time.monotonic()
        with patch.object(type(self.env['product.product']),'search',count_search):
            batch.action_match_products()
        elapsed=time.monotonic()-start
        self.assertLessEqual(len(searches),6,'Product lookups must be bulk, not one search per row')
        self.assertEqual(batch.product_counts['auto_matched'],500)
        self.assertEqual(batch.product_counts['distinct_matched_products'],500)
        self.assertEqual(len(batch.product_resolution_ids),500)
        logging.getLogger(__name__).info('PR07_WORKLOAD rows=500 seconds=%.3f; memory NOT_MEASURED',elapsed)


@tagged('post_install','-at_install')
class TestVendorProductRegistry(ProductFixtures,TransactionCase):
    def test_purchase_proposes_independent_manager_verifies_and_audit_is_preserved(self):
        batch=self._batch(['VENDOR-NEW']);batch.action_match_products()
        self.assertEqual(batch.row_ids.product_match_status,'unmatched')
        proposal=batch.row_ids.action_propose_product(self.red.id,'Supplier confirms variant','2026-01-01','2026-12-31')
        self.assertEqual(proposal.state,'proposed')
        self.assertFalse(proposal.verified_by)
        with self.assertRaises(AccessError):proposal.action_confirm_mapping('Not a manager')
        proposal.with_user(self.users['manager']).action_confirm_mapping('Independent evidence review')
        batch.action_match_products()
        self.assertEqual(batch.row_ids.product_match_status,'manual_matched')
        self.assertEqual(batch.row_ids.resolved_product_id,self.red)
        self.assertEqual(proposal.verified_by,self.users['manager'])
        self.assertTrue(proposal.verified_at)
        self.assertEqual(proposal.product_tmpl_id,self.red.product_tmpl_id)
        audits=self.env[AUDIT].search([('mapping_id','=',proposal.id)],order='id')
        self.assertEqual(audits.mapped('operation'),['propose','verify'])
        self.assertEqual(batch.row_ids.product_resolution_id.mapping_id,proposal)

    def test_manager_cannot_verify_own_proposal(self):
        batch=self._batch(['MANAGER-OWN'])
        row=batch.row_ids.with_user(self.users['manager'])
        proposed=row.action_propose_product(self.red.id,'Manager proposal','2026-01-01','2026-12-31')
        with self.assertRaises(AccessError):proposed.action_confirm_mapping('Self review')
        proposed.with_user(self.manager2).action_confirm_mapping('Separate manager check')
        self.assertEqual(proposed.state,'verified')

    def test_overlap_rejected_supersession_retains_old_and_new_product_evidence(self):
        batch=self._batch(['REUSED'])
        old=self._verify(batch.row_ids,self.red);batch.action_match_products();history=batch.row_ids.product_resolution_id
        proposed=batch.row_ids.action_propose_product(self.white.id,'Corrected identity evidence','2026-01-01','2026-12-31')
        with self.assertRaises(ValidationError):proposed.with_user(self.users['manager']).action_confirm_mapping('Conflicting active period')
        old.with_user(self.users['manager']).action_retire_mapping('Supplier replaced prior identity')
        self.assertEqual(old.state,'superseded')
        self.assertFalse(batch.get_product_resolved_rows())
        proposed.with_user(self.users['manager']).action_confirm_mapping('New independent identity version')
        batch.action_match_products()
        self.assertEqual(batch.row_ids.resolved_product_id,self.white)
        self.assertEqual(history.product_id,self.red)
        self.assertEqual(proposed.previous_mapping_id,old)

    def test_nonoverlapping_identity_periods_resolve_source_date(self):
        old_batch=self._batch(['DATED'],dates=['2025-11-01'])
        self._verify(old_batch.row_ids,self.red,'2025-01-01','2025-12-31')
        new_batch=self._batch(['DATED'],dates=['2026-11-01'])
        self._verify(new_batch.row_ids,self.white,'2026-01-01','2026-12-31')
        old_batch.action_match_products();new_batch.action_match_products()
        self.assertEqual(old_batch.row_ids.resolved_product_id,self.red)
        self.assertEqual(new_batch.row_ids.resolved_product_id,self.white)

    def test_vendor_scope_parent_contacts_and_other_company_registry(self):
        vendor_b=self.env['res.partner'].create({'name':'PR07 Different Vendor','parent_id':self.vendor.id})
        a=self._batch(['VENDOR-X']);b=self._batch(['VENDOR-X'],vendor=vendor_b)
        self._verify(a.row_ids,self.red);self._verify(b.row_ids,self.cable)
        a.action_match_products();b.action_match_products()
        self.assertEqual(a.row_ids.resolved_product_id,self.red)
        self.assertEqual(b.row_ids.resolved_product_id,self.cable)
        self._supplier('PARENT-ONLY',product=self.red)
        child=self._batch(['PARENT-ONLY'],vendor=vendor_b);child.action_match_products()
        self.assertEqual(child.row_ids.product_match_status,'unmatched')

    def test_manual_disambiguation_and_one_off_description_only_mapping(self):
        self._supplier('LED-12W',template=self.template)
        batch=self._batch(['LED-12W']);batch.action_match_products()
        self.assertEqual(batch.row_ids.product_match_status,'ambiguous')
        self._verify(batch.row_ids,self.white);batch.action_match_products()
        self.assertEqual(batch.row_ids.resolved_product_id,self.white)
        description=self._batch([''])
        proposal=self._verify(description.row_ids,self.cable,reusable=False)
        description.action_match_products()
        self.assertEqual(proposal.identifier_type,'row')
        self.assertEqual(description.row_ids.product_match_status,'manual_matched')

    def test_proposal_source_changes_and_ineligible_or_wrong_period_are_rejected(self):
        batch=self._batch(['PENDING'])
        for product in (self.archived,):
            with self.assertRaises(ValidationError):batch.row_ids.action_propose_product(product.id,'Invalid product','2026-01-01','2026-12-31')
        with self.assertRaises(ValidationError):batch.row_ids.action_propose_product(self.red.id,'Invalid dates','2026-12-31','2026-01-01')
        proposal=batch.row_ids.action_propose_product(self.red.id,'Awaiting verification','2026-01-01','2026-12-31')
        batch.row_ids.action_correct('vendor_product_code','CHANGED','Supplier correction');batch.action_validate_structure()
        with self.assertRaises(UserError):proposal.with_user(self.users['manager']).action_confirm_mapping('Old source')


@tagged('post_install','-at_install')
class TestProductResolutionFreshness(ProductFixtures,TransactionCase):
    def test_barcode_and_variant_value_changes_are_material_identity_evidence(self):
        batch=self._batch(['LED-12W-RED']);batch.action_match_products();old=batch.row_ids.product_resolution_id
        self.red.barcode='PR07-NEW-BARCODE'
        self.assertFalse(batch.get_product_resolved_rows())
        batch.action_match_products();self.assertEqual(batch.row_ids.product_match_status,'auto_matched')
        value=self.red.product_template_attribute_value_ids.product_attribute_value_id
        value.name='Scarlet (identity review needed)'
        self.assertFalse(batch.get_product_resolved_rows())
        self.assertEqual(old.product_snapshot['attribute_values'][0][2],'Red')

    def test_identifier_correction_marks_stale_and_preserves_history(self):
        batch=self._batch(['LED-12W-RED']);batch.action_match_products();old=batch.row_ids.product_resolution_id
        batch.row_ids.action_correct('vendor_product_code','LED-12W-WHT','Correct variant')
        self.assertEqual(batch.row_ids.product_match_status,'stale')
        self.assertFalse(batch.row_ids.resolved_product_id)
        batch.action_validate_structure();batch.action_match_products()
        self.assertEqual(batch.row_ids.resolved_product_id,self.white)
        self.assertEqual(old.product_id,self.red)

    def test_note_only_change_retains_identity_after_structural_revalidation(self):
        batch=self._batch(['LED-12W-RED']);batch.action_match_products();old=batch.row_ids.product_resolution_id
        batch.row_ids.action_correct('notes_raw','Shipping note only','No identity change')
        self.assertEqual(batch.row_ids.product_match_status,'pending_structure')
        batch.action_validate_structure();batch.action_match_products()
        self.assertEqual(batch.row_ids.product_resolution_id,old)
        self.assertEqual(batch.row_ids.product_match_status,'auto_matched')
        self.assertEqual(batch.get_product_resolved_rows(),batch.row_ids)

    def test_archive_sku_barcode_and_new_duplicate_invalidate_reused_results(self):
        batch=self._batch(['LED-12W-RED']);batch.action_match_products();old=batch.row_ids.product_resolution_id
        self.red.active=False
        self.assertFalse(batch.get_product_resolved_rows())
        self.assertEqual(batch.row_ids.product_match_status,'stale')
        self.assertEqual(old.product_id,self.red)
        batch.action_match_products();self.assertEqual(batch.row_ids.product_match_status,'ineligible')
        self.red.active=True;batch.action_match_products()
        self.env['product.product'].create({'name':'PR07 New duplicate','default_code':'LED-12W-RED'})
        self.assertFalse(batch.get_product_resolved_rows())
        self.assertEqual(batch.row_ids.product_match_status,'stale')
        batch.action_match_products();self.assertEqual(batch.row_ids.product_match_status,'ambiguous')

    def test_verified_reference_change_is_stale_not_silent_fallback(self):
        batch=self._batch(['MANUAL-FRESH']);mapping=self._verify(batch.row_ids,self.red);batch.action_match_products()
        self.red.default_code='CHANGED-RED-SKU'
        self.assertFalse(batch.get_product_resolved_rows())
        batch.action_match_products()
        self.assertEqual(batch.row_ids.product_match_status,'stale')
        self.assertEqual(mapping.product_evidence['code'],'LED-12W-RED')
        self._supplier('MANUAL-FRESH',product=self.white)
        batch.action_match_products()
        self.assertEqual(batch.row_ids.product_match_status,'stale')

    def test_policy_change_and_registry_retirement_require_revalidation(self):
        batch=self._batch(['LED-12W-RED']);batch.action_match_products()
        self.policy.write({'allow_internal':False,'change_reason':'Disable internal-code inference'})
        self.assertFalse(batch.get_product_resolved_rows())
        batch.action_match_products();self.assertEqual(batch.row_ids.product_match_status,'unmatched')
        mapping=self._verify(batch.row_ids,self.red);batch.action_match_products()
        mapping.with_user(self.users['manager']).action_retire_mapping('Identity no longer reusable')
        self.assertEqual(batch.row_ids.product_match_status,'stale')

    def test_identity_resolution_leaves_source_master_prices_and_notifications_unchanged(self):
        supplier=self._supplier('EXACT',product=self.red)
        batch=self._batch(['EXACT'])
        before=(supplier.price,supplier.write_date,self.red.default_code,self.red.barcode,self.red.write_date,
            self.red.standard_price,self.red.list_price,batch.sha256_digest,batch.attachment_id.raw.content,
            batch.row_ids.raw_cells,self.revision.state,self.revision.write_date)
        counts=tuple(self.env[m].search_count([]) for m in ('product.product','product.supplierinfo','product.pricelist.item','mail.mail','mail.message','mail.activity','ir.cron'))
        batch.action_match_products();batch.action_match_products()
        self.assertEqual(before,(supplier.price,supplier.write_date,self.red.default_code,self.red.barcode,self.red.write_date,
            self.red.standard_price,self.red.list_price,batch.sha256_digest,batch.attachment_id.raw.content,
            batch.row_ids.raw_cells,self.revision.state,self.revision.write_date))
        self.assertEqual(counts,tuple(self.env[m].search_count([]) for m in ('product.product','product.supplierinfo','product.pricelist.item','mail.mail','mail.message','mail.activity','ir.cron')))
        self.assertFalse(self.revision.line_ids)


@tagged('post_install','-at_install')
class TestProductResolutionSecurity(ProductFixtures,TransactionCase):
    def test_product_moved_company_does_not_leak_new_labels_through_history(self):
        batch=self._batch(['PRIVATE-MOVE']);mapping=self._verify(batch.row_ids,self.red);batch.action_match_products()
        history=batch.row_ids.product_resolution_id
        self.template.write({'company_id':self.b.id,'name':'PRIVATE NEW COMPANY B NAME'})
        self.assertFalse(batch.get_product_resolved_rows())
        self.assertFalse(batch.row_ids.product_candidate_snapshot)
        self.assertNotIn('PRIVATE NEW COMPANY B NAME',str(mapping.read(['product_id','product_tmpl_id'])))
        self.assertNotIn('PRIVATE NEW COMPANY B NAME',str(history.read(['product_id','candidate_snapshot'])))
        self.users['purchase'].group_ids=[Command.link(self.env.ref('base.group_allow_export').id)]
        with self.assertRaises(AccessError):mapping.export_data(['product_id'])
        with self.assertRaises(AccessError):history.export_data(['product_id'])

    def test_other_company_candidates_are_permission_neutral_even_for_multi_company_user(self):
        foreign=self.env['product.product'].create({'name':'PR07 PRIVATE B','company_id':self.b.id,'default_code':'SECRET-B'})
        batch=self._batch(['SECRET-B']);batch.action_match_products()
        self.assertEqual(batch.row_ids.product_match_status,'unmatched')
        self.assertFalse(batch.row_ids.product_candidate_snapshot)
        self.users['purchase'].company_ids=[Command.link(self.b.id)]
        multi=batch.with_context(allowed_company_ids=(self.a|self.b).ids)
        multi.action_match_products()
        self.assertFalse(multi.row_ids.product_candidate_snapshot)
        with self.assertRaises(ValidationError):multi.row_ids.action_propose_product(foreign.id,'Wrong company','2026-01-01','2026-12-31')

    def test_same_vendor_code_different_company_mapping_and_read_isolation(self):
        a=self._batch(['COMPANY-X']);self._verify(a.row_ids,self.red);a.action_match_products()
        self.users['manager'].company_ids=[Command.link(self.b.id)]
        b=self._batch(['COMPANY-X'],role='purchase_b')
        proposal=b.row_ids.action_propose_product(self.cable.id,'Company B evidence','2026-01-01','2026-12-31')
        proposal.with_user(self.users['manager']).with_context(allowed_company_ids=self.b.ids).action_confirm_mapping('Company B independent verification')
        b.action_match_products()
        self.assertEqual(a.row_ids.resolved_product_id,self.red)
        self.assertEqual(b.row_ids.resolved_product_id,self.cable)
        for records in (proposal,b.product_resolution_ids,self.env[AUDIT].search([('mapping_id','=',proposal.id)])):
            with self.assertRaises(AccessError):self._as(records).read(['id'])
            with self.assertRaises(AccessError):self._as(records).export_data(['id'])
            scoped=self._as(self.env[records._name])
            self.assertFalse(scoped._read_group([('company_id','=',self.b.id)],['company_id'],['__count']))

    def test_direct_orm_state_company_result_and_audit_forgery_is_denied(self):
        batch=self._batch(['PROPOSAL']);proposal=batch.row_ids.action_propose_product(self.red.id,'Evidence','2026-01-01','2026-12-31')
        for model in (REGISTRY,AUDIT,RESOLUTION):
            with self.assertRaises(AccessError):self._as(self.env[model]).create({'company_id':self.a.id,'state':'verified'})
        for values in ({'state':'verified'},{'company_id':self.b.id},{'product_id':self.white.id},{'verified_by':self.users['manager'].id}):
            with self.assertRaises(AccessError):proposal.write(values)
        with self.assertRaises(AccessError):batch.row_ids.write({'product_resolution_id':1})
        with self.assertRaises(AccessError):proposal.unlink()
        with self.assertRaises(AccessError):proposal.copy()
        with self.assertRaises(AccessError):batch.write({'product_resolution_ids':[Command.clear()]})
        foreign=self._batch(['FOREIGN-WIZARD'],role='purchase_b')
        wizard_model=self._as(self.env[WIZARD])
        with self.assertRaises(AccessError):wizard_model.create({'row_id':foreign.row_ids.id,'reason':'Forged foreign link'})
        with self.assertRaises(AccessError):wizard_model.with_context(default_row_id=foreign.row_ids.id).create({'reason':'Forged context link'})
        wizard=wizard_model.create({'row_id':batch.row_ids.id,'reason':'Authorized review'})
        with self.assertRaises(AccessError):wizard.write({'row_id':foreign.row_ids.id})

    def test_read_only_roles_no_verification_or_matching_and_sales_no_source_access(self):
        batch=self._batch(['LED-12W-RED']);batch.action_match_products()
        proposal=batch.row_ids.action_propose_product(self.red.id,'Identity evidence','2026-01-01','2026-12-31')
        for role in ('finance','auditor','pricing','director'):
            self.assertTrue(self._as(batch.product_resolution_ids,role).read(['id']))
            with self.assertRaises(AccessError):self._as(batch,role).action_match_products()
            with self.assertRaises(AccessError):self._as(proposal,role).action_confirm_mapping('Not a verifier')
        for role in ('sales','portal','employee','configuration','other'):
            with self.assertRaises(AccessError):self._as(batch.product_resolution_ids,role).read(['id'])
        with self.assertRaises(AccessError):self._as(self.policy,'purchase').write({'allow_internal':False,'change_reason':'bad'})
        config=self._as(self.policy,'configuration')
        config.write({'allow_services':False,'change_reason':'Explicit company identity control'})
        self.assertEqual(config.version,2)
        with self.assertRaises(AccessError):config.write({'company_id':self.b.id,'change_reason':'Company switch'})
        with self.assertRaises(AccessError):self._as(self.env[POLICY],'configuration').create({'company_id':self.b.id,'change_reason':'Foreign configuration'})

    def test_context_and_protected_revision_do_not_bypass_gate(self):
        batch=self._batch(['LED-12W-RED'])
        self.env.cr.execute('UPDATE vendor_price_revision SET state=%s WHERE id=%s',['approved',self.revision.id]);self.revision.invalidate_recordset(['state'])
        with self.assertRaises(UserError):batch.with_context(skip_security=True,default_product_id=self.red.id).action_match_products()
        with self.assertRaises(UserError):batch.row_ids.action_propose_product(self.red.id,'No bypass','2026-01-01','2026-12-31')

    def test_policy_and_review_views_load_and_identity_is_not_price_approval(self):
        batch=self._batch(['LED-12W-RED']);batch.action_match_products()
        for model,xmlid in [(BATCH,'view_import_batch_form'),(REGISTRY,'view_vendor_product_mapping_form'),(WIZARD,'view_product_proposal_wizard')]:
            self.assertTrue(self._as(self.env[model],'manager').get_view(view_id=self.env.ref('vendor_price_revision_impact_simulator.'+xmlid).id,view_type='form')['arch'])
        for action in ('action_approve','action_apply','action_apply_prices'):
            self.assertFalse(hasattr(batch,action))
