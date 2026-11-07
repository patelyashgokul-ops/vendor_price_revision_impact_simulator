import logging
from datetime import date
from decimal import Decimal as D
from unittest.mock import patch
import time

from psycopg2 import DatabaseError
from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from .test_product_resolution import ProductFixtures
from .test_import_validation import VALID, csv_bytes
from ..models import commercial_math as math
from ..models.commercial_engine import CommercialEngine, supplier_snapshot
from ..models.commercial_validation import CONTEXT, RESULT, ISSUE, WIZARD, ALIAS_WIZARD
from ..models.import_intake import BATCH, ROW

MODULE='vendor_price_revision_impact_simulator'


@tagged('post_install','-at_install')
class TestCommercialMath(TransactionCase):
    def test_box_quantity_and_inverse_price_dimensions_match_odoo20(self):
        unit=self.env.ref('uom.product_uom_unit')
        box=self.env['uom.uom'].create({'name':'PR08 Math Box10','relative_uom_id':unit.id,'relative_factor':10})
        self.assertEqual(math.quantity('2',box.factor,unit.factor),D('20'))
        self.assertEqual(math.price('1150',box.factor,unit.factor),D('115'))
        self.assertEqual(math.price('1000',box.factor,unit.factor),D('100'))
        self.assertEqual(box._compute_quantity(2,unit,round=False),20)
        self.assertEqual(box._compute_price(1150,unit),115)
        self.assertEqual(unit._compute_price(115,box),1150)

    def test_kg_gram_precision_and_repeating_decimal(self):
        self.assertEqual(math.quantity('2','1','.001'),D('2000'))
        self.assertEqual(math.price('100','1','.001'),D('.1'))
        self.assertGreater(len(str(math.price('1','3','1'))),30)
        self.assertGreater(len(str(math.net_price('1','7','1','10'))),35)
        self.assertTrue(str(math.net_price('1','7','1','10')).startswith('0.128571428571'))
        self.assertEqual(math.rounded('1.025','.05'),'1.05')
        self.assertEqual(math.rounded('12345678901234567890123456789012345678','.01'),
                         '12345678901234567890123456789012345678.00')
        for value in ('1'*39, '1e1001', '1'*129):
            with self.assertRaises(ValueError):math.number(value)

    def test_delta_direction_percent_zero_missing_and_tolerance(self):
        self.assertEqual(math.comparison('100','115')['delta'],'15')
        self.assertEqual(D(math.comparison('100','115')['percent']),15)
        decrease=math.comparison('115','109')
        self.assertEqual(decrease['delta'],'-6')
        self.assertAlmostEqual(float(decrease['percent']),-5.217391304,places=8)
        self.assertEqual(math.comparison('100','100')['classification'],'unchanged')
        self.assertEqual(math.comparison('0','10')['classification'],'new_from_zero')
        self.assertEqual(math.comparison('0','0')['classification'],'zero_to_zero')
        self.assertIsNone(math.comparison('0','10')['percent'])
        self.assertEqual(math.comparison('100','100.000000001')['classification'],'increase')
        with self.assertRaises(ValueError):math.comparison(None,'10')

    def test_fx_direction_and_labeled_decomposition_reconciles(self):
        self.assertEqual(math.converted('11','94'),1034)
        self.assertEqual(math.converted('10','90'),900)
        parts=math.decomposition('10','11','90','94')
        self.assertEqual(parts['supplier_component'],'90')
        self.assertEqual(parts['fx_component'],'44')
        self.assertEqual(parts['total'],'134')
        self.assertEqual(parts['method'],'supplier_at_old_rate_then_fx_on_proposed_price')
        self.assertFalse(parts['accounting_outcome'])

    def test_nonfinite_negative_missing_and_zero_factors_are_rejected(self):
        for value in ('NaN','Infinity','-1',None,'bad'):
            with self.subTest(value=value),self.assertRaises(ValueError):math.price(value,10,1)
        for factor in ('0','-1','NaN',None):
            with self.subTest(factor=factor),self.assertRaises(ValueError):math.quantity('1',factor,1)
        with self.assertRaises(ValueError):math.converted('10','0')


class CommercialFixtures(ProductFixtures):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.enterClassContext(patch.object(fields.Date,'context_today',return_value=date(2026,10,28)))
        cls.inr=cls.env.ref('base.INR');cls.usd=cls.env.ref('base.USD');cls.eur=cls.env.ref('base.EUR')
        (cls.inr|cls.usd|cls.eur).active=True
        (cls.a|cls.b).currency_id=cls.inr
        cls.unit=cls.env.ref('uom.product_uom_unit')
        cls.box=cls.env['uom.uom'].create({'name':'PR08 Verified Box of10','relative_uom_id':cls.unit.id,'relative_factor':10})
        cls.kg=cls.env.ref('uom.product_uom_kgm')
        cls.gram=cls.env['uom.uom'].create({'name':'PR08 Gram','relative_uom_id':cls.kg.id,'relative_factor':.001})
        cls.financial=cls._financial_policy(cls.a,'commercial1')
        cls.financial_b=cls._financial_policy(cls.b,'commercial1')

    @classmethod
    def _financial_policy(cls,company,version,**options):
        values={'company_id':company.id,'policy_version':version,'effective_from':'2025-01-01','effective_to':'2030-12-31',
            'change_reason':'PR08 explicit company commercial policy',
            'margin_ids':[Command.create({'scope':'company','minimum_margin_percent':20,'target_margin_percent':25,'reason':'Test governance'})],
            'risk_ids':[Command.create({'name':'Full test interval','risk_level':'low','currency_id':company.currency_id.id,'open_ended':True,'reason':'Test interval'})],
            'approval_ids':[Command.create({'name':'Finance definition','currency_id':company.currency_id.id,'open_ended':True,'reason':'Test definition',
                'required_role_ids':[Command.set(cls.env.ref(MODULE+'.group_vpr_finance_manager').ids)]})]}
        values.update(options)
        policy=cls.env['vendor.price.revision.config'].with_company(company).create(values);policy.action_publish()
        return policy

    def _policy_replace(self,**options):
        # Published versions are immutable. Simulate retiring a dated version only
        # in controlled fixture SQL; production comparison never edits policies.
        self.env.cr.execute('UPDATE vendor_price_revision_config SET active=false,state=%s WHERE id=%s',['draft',self.financial.id])
        self.financial.invalidate_recordset(['active','state'])
        self.financial=self._financial_policy(self.a,'changed-'+str(time.time_ns()),**options)
        return self.financial

    def _commercial_batch(self,rows=None,role='purchase',vendor=None):
        if rows is None:
            row=list(VALID);row[0]='LED-12W-RED';row[2]='1150';row[4]='BOX';rows=[row]
        if vendor:
            revision=self._revision_for(self.users[role]);revision.vendor_id=vendor
            batch=self._upload(csv_bytes(rows),role=role,revision=revision)
        else:batch=self._review_batch(rows,role=role)
        self._map(batch);batch.action_validate_structure();batch.action_match_products()
        return batch

    def _rule(self,price=1000,qty=1,uom=None,currency=None,product=None,company=None,**options):
        product=product or self.red
        values={'partner_id':self.vendor.id,'company_id':(company or self.a).id,'product_id':product.id,
            'product_tmpl_id':product.product_tmpl_id.id,'price':price,'min_qty':qty,'uom_id':(uom or self.box).id,
            'currency_id':(currency or self.inr).id,'date_start':'2025-01-01','date_end':'2026-10-31'}
        values.update(options)
        return self.env['product.supplierinfo'].create(values)

    def _context(self,batch,verifier=None,**options):
        settings={'uom_aliases':{'BOX':self.box.id,'PCS':self.unit.id},'price_basis':'net_exclusive'}
        settings.update(options)
        context=batch.action_propose_commercial_context(settings,'Supplier evidence for units and net tax-exclusive prices')
        context.with_user(verifier or self.users['manager']).with_context(allowed_company_ids=batch.company_id.ids).action_verify_context('Independent supplier terms and conversion evidence checked')
        return context

    def _validate(self,batch):
        self.assertTrue(batch.action_validate_commercial_prices())
        self.assertEqual(batch.commercial_processing_state,'complete')
        return batch.row_ids[0].commercial_result_id

    def _rates(self,company=None,old=90,new=94):
        company=company or self.a
        return self.env['res.currency.rate'].with_company(company).create([
            {'currency_id':currency.id,'company_id':company.id,'name':day,'rate':value}
            for day,rate in [('2026-10-26',old),('2026-10-27',new)]
            for currency,value in [(self.inr,rate),(self.usd,1)]])


@tagged('post_install','-at_install')
class TestCommercialNormalization(CommercialFixtures,TransactionCase):
    def test_box_reference_old100_new115_delta15_percent15(self):
        rule=self._rule();batch=self._commercial_batch();self._context(batch)
        result=self._validate(batch);snap=result.snapshot
        self.assertEqual(result.status,'commercially_valid')
        self.assertEqual(D(snap['baseline']['net_comparable']),100)
        self.assertEqual(D(snap['proposal']['net_comparable']),115)
        self.assertEqual(D(snap['comparison']['delta']),15)
        self.assertEqual(D(snap['comparison']['percent']),15)
        self.assertEqual(snap['baseline']['selected']['id'],rule.id)
        self.assertEqual(snap['proposal']['comparison_uom_id'],self.unit.id)
        self.assertEqual(result.classification,'increase')
        self.assertIn('Old supplier rule ID: '+str(rule.id),result.calculation_explanation)
        self.assertIn('BOX',result.context_id.interpretation_summary)
        self.assertEqual(batch.get_commercially_valid_rows(),batch.row_ids)
        self.assertEqual(batch.commercial_counts['commercially_valid'],1)
        self.assertEqual(D(batch.row_ids.commercial_delta),15)
        logging.getLogger(__name__).info('PR08_REFERENCE old_per_piece=%s proposed_per_piece=%s delta=%s percent=%s baseline_id=%s product_id=%s',snap['baseline']['net_comparable'],snap['proposal']['net_comparable'],snap['comparison']['delta'],snap['comparison']['percent'],rule.id,self.red.id)

    def test_piece_box_moq_normalization_and_legitimate_distinct_tiers(self):
        self._rule(price=1000,qty=1);self._rule(price=900,qty=10)
        rows=[]
        for price,qty in [('115','10'),('109','100')]:
            r=list(VALID);r[0]='LED-12W-RED';r[2]=price;r[4]='PCS';r[5]=qty;rows.append(r)
        batch=self._commercial_batch(rows);self._context(batch);self._validate(batch)
        self.assertEqual(batch.row_ids.mapped('commercial_status'),['commercially_valid']*2)
        self.assertEqual([D(x.snapshot['baseline']['normalized_min_qty']) for x in batch.commercial_result_ids],[D(10),D(100)])
        self.assertEqual(batch.commercial_counts['commercially_valid'],2)

    def test_unknown_ambiguous_and_incompatible_units_are_not_guessed(self):
        self._rule();batch=self._commercial_batch();self._context(batch,uom_aliases={})
        result=self._validate(batch);self.assertEqual(result.status,'uom_invalid')
        self.assertIn('UOM_UNKNOWN',result.issue_ids.mapped('code'))
        self.env['uom.uom'].create([{'name':'BOX','relative_uom_id':self.unit.id,'relative_factor':6},{'name':'BOX','relative_uom_id':self.unit.id,'relative_factor':12}])
        self._context(batch,uom_aliases={});result=self._validate(batch)
        self.assertIn('UOM_AMBIGUOUS',result.issue_ids.mapped('code'))
        self._context(batch,uom_aliases={'BOX':self.kg.id});result=self._validate(batch)
        self.assertIn('UOM_INCOMPATIBLE',result.issue_ids.mapped('code'))
        self.assertFalse(batch.get_commercially_valid_rows())

    def test_negative_or_missing_factor_is_blocked_and_no_master_repair(self):
        self._rule();batch=self._commercial_batch();self._context(batch)
        self.env.cr.execute('UPDATE uom_uom SET factor=0 WHERE id=%s',[self.box.id]);self.box.invalidate_recordset(['factor'])
        result=self._validate(batch)
        self.assertNotEqual(result.status,'commercially_valid')
        self.assertEqual(self.box.factor,0)
        self.assertFalse(batch.get_commercially_valid_rows())

    def test_missing_baseline_normalizes_proposal_without_zero_or_standard_cost(self):
        self.red.standard_price=43
        batch=self._commercial_batch();self._context(batch);result=self._validate(batch)
        self.assertEqual(result.status,'baseline_unavailable')
        self.assertTrue(result.proposal_normalized)
        self.assertNotIn('comparison',result.snapshot)
        self.assertNotIn('company_price',result.snapshot['baseline'])
        self.assertFalse(result.classification)
        self.assertFalse(batch.row_ids.commercial_delta)
        self.assertFalse(batch.row_ids.commercial_old_price)

    def test_zero_old_price_and_small_material_delta(self):
        rule=self._rule(price=0);batch=self._commercial_batch();self._context(batch);result=self._validate(batch)
        self.assertEqual(result.classification,'new_from_zero')
        self.assertIsNone(result.snapshot['comparison']['percent'])
        rule.price=1149.999999
        result=self._validate(batch)
        self.assertEqual(result.classification,'increase')
        self.assertGreater(D(result.snapshot['comparison']['delta']),0)

    def test_supplier_discount_and_explicit_proposed_discount_net_basis(self):
        self._rule(price=1250,discount=20);batch=self._commercial_batch()
        self._context(batch,discount_percent='10');result=self._validate(batch)
        self.assertEqual(D(result.snapshot['baseline']['net_comparable']),100)
        self.assertEqual(D(result.snapshot['proposal']['net_comparable']),D('103.5'))
        self.assertEqual(D(result.snapshot['comparison']['delta']),D('3.5'))

    def test_tax_unknown_inclusive_and_unsupported_discount_do_not_compare(self):
        rule=self._rule();batch=self._commercial_batch()
        for basis in ('unknown','tax_inclusive'):
            self._context(batch,price_basis=basis);result=self._validate(batch)
            self.assertEqual(result.status,'needs_review')
            self.assertIn('TAX_BASIS_UNKNOWN',result.issue_ids.mapped('code'))
            self.assertNotIn('comparison',result.snapshot)
        rule.discount=101;self._context(batch);result=self._validate(batch)
        self.assertEqual(result.status,'baseline_conflict')

    def test_current_product_and_structural_gates_and_exclusion(self):
        batch=self._commercial_batch();self._context(batch)
        batch.row_ids.action_correct('proposed_price_raw','11O','Invalid monetary source');batch.action_validate_structure()
        self._validate(batch);self.assertFalse(batch.commercial_result_ids)
        self.assertFalse(batch.get_commercially_valid_rows())
        batch.row_ids.action_correct('proposed_price_raw','1150','Supplier correction');batch.action_validate_structure();batch.action_match_products()
        batch.row_ids.action_set_excluded(True,'Not part of offer');batch.action_validate_structure()
        self._validate(batch);self.assertEqual(batch.row_ids.commercial_status,'excluded')
        self.assertEqual(batch.commercial_counts['excluded'],1)

    def test_no_verified_context_means_review_not_implicit_tax_and_unit_assumptions(self):
        self._rule();batch=self._commercial_batch();result=self._validate(batch)
        self.assertEqual(result.status,'needs_review')
        self.assertIn('COMMERCIAL_CONTEXT_UNVERIFIED',result.issue_ids.mapped('code'))
        proposed=batch.action_propose_commercial_context({'price_basis':'net_exclusive'},'Unverified proposal')
        result=self._validate(batch);self.assertEqual(result.status,'needs_review')
        with self.assertRaises(AccessError):proposed.action_verify_context('Not a manager')


@tagged('post_install','-at_install')
class TestCommercialFx(CommercialFixtures,TransactionCase):
    def _usd_batch(self):
        r=list(VALID);r[0]='LED-12W-RED';r[2]='11';r[3]='USD';r[4]='PCS'
        return self._commercial_batch([r])

    def test_date_specific_90_94_reference_decomposition_and_odoo_direction(self):
        self._policy_replace(currency_rate_policy='company_reference_date',currency_reference_date='2026-10-28')
        rates=self._rates();rule=self._rule(price=10,uom=self.unit,currency=self.usd,date_end='2026-10-27')
        batch=self._usd_batch();self._context(batch,baseline_mode='explicit',baseline_date='2026-10-27',comparison_mode='date_specific',historical_attestation='Supplier dated agreement independently reviewed')
        result=self._validate(batch);snap=result.snapshot
        self.assertEqual(result.status,'commercially_valid')
        self.assertEqual(D(snap['baseline']['company_price']),900)
        self.assertEqual(D(snap['proposal']['company_price']),1034)
        self.assertEqual(D(snap['comparison']['delta']),134)
        self.assertEqual(D(snap['comparison']['decomposition']['supplier_component']),90)
        self.assertEqual(D(snap['comparison']['decomposition']['fx_component']),44)
        self.assertEqual(snap['proposal']['fx']['requested_date'],'2026-10-28')
        self.assertEqual({r['date'] for r in snap['proposal']['fx']['rate_records']},{'2026-10-27'})
        self.assertEqual(self.usd._convert(11,self.inr,self.a,date(2026,10,28),round=False),1034)
        self.assertFalse(snap['proposal']['fx']['hypothetical'])
        self.assertEqual(batch.row_ids.commercial_fx_method,'Date-specific: supplier and FX')
        self.assertEqual(D(batch.row_ids.commercial_supplier_percent),10)
        self.assertGreater(D(batch.row_ids.commercial_percent),14)
        logging.getLogger(__name__).info('PR08_FX_REFERENCE old=900 proposed=1034 total=134 supplier=90 fx=44 method=%s',snap['comparison']['decomposition']['method'])

    def test_common_rate_method_separates_supplier_effect_from_date_specific(self):
        self._policy_replace(currency_rate_policy='company_reference_date',currency_reference_date='2026-10-28')
        self._rates();self._rule(price=10,uom=self.unit,currency=self.usd)
        batch=self._usd_batch();self._context(batch);result=self._validate(batch)
        self.assertEqual(D(result.snapshot['comparison']['delta']),94)
        self.assertEqual(D(result.snapshot['comparison']['decomposition']['fx_component']),0)
        self.assertEqual(result.snapshot['comparison']['method'],'same_rate')
        self.assertEqual(D(result.snapshot['comparison']['source_currency_comparison']['delta']),1)

    def test_missing_rate_never_falls_back_to_one_and_future_rate_is_not_forecast(self):
        self._rule(price=10,uom=self.unit,currency=self.usd);batch=self._usd_batch();self._context(batch)
        result=self._validate(batch)
        self.assertEqual(result.status,'fx_rate_missing')
        self.assertIn('FX_DATE_UNSUPPORTED',result.issue_ids.mapped('code'))
        self.assertFalse(result.proposal_normalized)
        self._policy_replace(currency_rate_policy='company_reference_date',currency_reference_date='2026-10-28')
        result=self._validate(batch)
        self.assertIn('FX_RATE_MISSING',result.issue_ids.mapped('code'))
        self.assertNotIn('company_price',result.snapshot['proposal'])

    def test_inactive_currency_and_unknown_code_block(self):
        self._rule();batch=self._usd_batch();self._context(batch)
        self.usd.active=False;result=self._validate(batch)
        self.assertIn('CURRENCY_INACTIVE',result.issue_ids.mapped('code'))
        self.usd.active=True
        batch.row_ids.action_correct('currency_raw','ZZZ','Unknown currency source');batch.action_validate_structure();batch.action_match_products();self._context(batch)
        result=self._validate(batch);self.assertIn('CURRENCY_UNKNOWN',result.issue_ids.mapped('code'))

    def test_finance_governed_scenario_is_independent_labeled_and_no_rate_writes(self):
        self._policy_replace(currency_rate_policy='authorized_scenario_rate',fx_override_policy='finance_governed')
        self._rule(price=10,uom=self.unit,currency=self.usd);batch=self._usd_batch()
        before=self.env['res.currency.rate'].search([]).read(['rate','name','company_id','write_date'])
        proposed=batch.action_propose_commercial_context({'uom_aliases':{'PCS':self.unit.id},'price_basis':'net_exclusive','scenario_rates':{'USD':'94'},'scenario_reference':'Finance scenario quotation 2026-NOV'},'Explicit hypothetical quote')
        with self.assertRaises(AccessError):proposed.with_user(self.users['manager']).action_verify_context('Manager lacks Finance role')
        proposed.with_user(self.users['finance']).action_verify_context('Independent finance scenario verification')
        result=self._validate(batch)
        self.assertEqual(result.status,'commercially_valid')
        self.assertEqual(D(result.snapshot['proposal']['company_price']),1034)
        self.assertTrue(result.snapshot['proposal']['fx']['hypothetical'])
        self.assertEqual(batch.row_ids.commercial_fx_assumption,'Hypothetical scenario')
        self.assertEqual(before,self.env['res.currency.rate'].search([]).read(['rate','name','company_id','write_date']))

    def test_unauthorized_scenario_policy_and_self_verification_are_denied(self):
        batch=self._usd_batch()
        proposed=batch.action_propose_commercial_context({'scenario_rates':{'USD':'94'},'scenario_reference':'Unapproved scenario','price_basis':'net_exclusive'},'Proposed')
        with self.assertRaises(UserError):proposed.with_user(self.users['finance']).action_verify_context('Policy does not authorize scenario')
        manager_batch=batch.with_user(self.users['manager'])
        own=manager_batch.action_propose_commercial_context({'price_basis':'net_exclusive'},'Manager prepares')
        with self.assertRaises(AccessError):own.action_verify_context('Self check')
        own.with_user(self.manager2).action_verify_context('Separate authorized manager')

    def test_company_rate_scope_and_strict_cutoff_and_shared_fallback(self):
        self._policy_replace(currency_rate_policy='company_reference_date',currency_reference_date='2026-10-28')
        rates=self._rates();self._rates(self.b,old=20,new=30)
        self._rule(price=10,uom=self.unit,currency=self.usd);batch=self._usd_batch();self._context(batch)
        self.users['purchase'].company_ids=[Command.link(self.b.id)]
        multi=batch.with_context(allowed_company_ids=(self.a|self.b).ids)
        result=self._validate(multi)
        self.assertEqual(D(result.snapshot['proposal']['fx']['rate']),94)
        ids={v['id'] for v in result.snapshot['proposal']['fx']['rate_records']}
        self.assertTrue(ids.issubset(set(rates.ids)))
        same_day=self.env['res.currency.rate'].create({'currency_id':self.inr.id,'company_id':self.a.id,'name':'2026-10-28','rate':999})
        self.assertEqual(D(self._validate(batch).snapshot['proposal']['fx']['rate']),94)
        self.env['res.currency.rate'].create([{'currency_id':c.id,'company_id':False,'name':'2026-10-27','rate':value} for c,value in [(self.inr,95),(self.usd,1)]])
        self.assertEqual(D(self._validate(batch).snapshot['proposal']['fx']['rate']),94)
        rates.unlink()
        result=self._validate(batch)
        self.assertEqual(D(result.snapshot['proposal']['fx']['rate']),95)
        self.assertTrue(all(not v['company_id'] for v in result.snapshot['proposal']['fx']['rate_records']))


@tagged('post_install','-at_install')
class TestVendorCommercialBaseline(CommercialFixtures,TransactionCase):
    def test_quantity_80_120_600_respects_1_100_500_eligible_tiers(self):
        rules=[self._rule(price=p,qty=q,uom=self.unit) for q,p in [(1,115),(100,109),(500,104)]]
        r=list(VALID);r[0]='LED-12W-RED';r[4]='PCS';r[5]='120';r[2]='110'
        batch=self._commercial_batch([r]);self._context(batch)
        for quantity,index in [(80,0),(120,1),(600,2)]:
            result=batch.resolve_vendor_tier(self.red.id,str(quantity),self.unit.id,'2026-10-31')
            self.assertEqual(result['selected']['id'],rules[index].id)
            standard=self.red.with_company(self.a)._select_seller(partner_id=self.vendor,quantity=quantity,date=date(2026,10,31),uom_id=self.unit,params={'partner_id':self.vendor})
            self.assertEqual(standard['supplierinfo'],rules[index])
        result=batch.resolve_vendor_tier(self.red.id,'12',self.box.id,'2026-10-31')
        self.assertEqual(result['selected']['id'],rules[1].id)
        self.assertEqual(D(result['normalized_quantity']),120)
        logging.getLogger(__name__).info('PR08_TIER_REFERENCE quantities=80,120,600 selected_thresholds=1,100,500; boxes12=pieces120')

    def test_specific_company_and_variant_scope_then_eligible_price_order(self):
        shared=self._rule(price=1,company=self.a);shared.company_id=False
        template=self._rule(price=2,product_id=False)
        variant=self._rule(price=1000)
        batch=self._commercial_batch();self._context(batch);result=self._validate(batch)
        self.assertEqual(result.snapshot['baseline']['selected']['id'],variant.id)
        self.assertIn('company_before_shared',result.snapshot['baseline']['precedence'])
        self.assertIn('variant_before_template',result.snapshot['baseline']['precedence'])
        variant.unlink();result=self._validate(batch)
        self.assertEqual(result.snapshot['baseline']['selected']['id'],template.id)
        template.unlink();result=self._validate(batch)
        self.assertEqual(result.snapshot['baseline']['selected']['id'],shared.id)

    def test_vendor_company_variant_and_future_rules_do_not_become_old_price(self):
        other_vendor=self.env['res.partner'].create({'name':'PR08 Other vendor'})
        self._rule(price=1,partner_id=other_vendor.id)
        self._rule(price=2,company=self.b)
        self._rule(price=3,product=self.white)
        old=self._rule(price=1000)
        future=self._rule(price=900,date_start='2026-11-01',date_end='2026-12-31')
        batch=self._commercial_batch();self._context(batch);result=self._validate(batch)
        self.assertEqual(result.snapshot['baseline']['selected']['id'],old.id)
        self.assertEqual(result.status,'date_conflict')
        self.assertIn('PRICE_RULE_OVERLAP',result.issue_ids.mapped('code'))
        self.assertNotIn(future.id,[c['id'] for c in result.snapshot['baseline']['candidates']])

    def test_overlapping_duplicate_baselines_conflict_and_no_arbitrary_cheapest(self):
        self._rule(price=1000);self._rule(price=1)
        batch=self._commercial_batch();self._context(batch);result=self._validate(batch)
        self.assertEqual(result.status,'baseline_conflict')
        self.assertIn('BASELINE_CONFLICT',result.issue_ids.mapped('code'))
        self.assertNotIn('comparison',result.snapshot)
        self.assertEqual(len(result.snapshot['baseline']['candidates']),2)

    def test_proposed_duplicate_normalized_tier_conflicts_but_distinct_tiers_work(self):
        self._rule()
        first=list(VALID);first[0]='LED-12W-RED';first[2]='1150';first[4]='BOX';first[5]='1'
        second=list(first);second[2]='116';second[4]='PCS';second[5]='10'
        batch=self._commercial_batch([first,second]);self._context(batch);self._validate(batch)
        self.assertEqual(batch.row_ids.mapped('commercial_status'),['tier_conflict','tier_conflict'])
        self.assertEqual(batch.commercial_counts['tier_conflict'],2)
        self.assertEqual(len(batch.get_commercially_valid_rows()),0)
        self.assertTrue(all('TIER_AMBIGUOUS' in r.issue_ids.mapped('code') for r in batch.commercial_result_ids))

    def test_validity_boundaries_old_end_and_expired_rules(self):
        old=self._rule(date_end='2026-10-31')
        expired=self._rule(price=1,date_end='2026-10-30')
        batch=self._commercial_batch();self._context(batch);result=self._validate(batch)
        self.assertEqual(result.status,'commercially_valid')
        self.assertEqual(result.snapshot['baseline']['as_of'],'2026-10-31')
        self.assertEqual(result.snapshot['proposal']['effective_date'],'2026-11-01')
        self.assertEqual(result.snapshot['baseline']['selected']['id'],old.id)
        self.assertEqual(batch.resolve_vendor_tier(self.red.id,'1',self.box.id,'2026-11-01')['status'],'baseline_unavailable')

    def test_invalid_end_dates_and_future_policy_and_historical_evidence_are_explicit(self):
        self._rule();batch=self._commercial_batch();self._context(batch,end_date='2026-10-31')
        result=self._validate(batch);self.assertEqual(result.status,'date_conflict')
        self._context(batch,baseline_mode='explicit',baseline_date='2026-11-01');result=self._validate(batch)
        self.assertEqual(result.status,'date_conflict')
        self._policy_replace(allow_future_dated_revisions=False)
        self._context(batch);result=self._validate(batch);self.assertEqual(result.status,'date_conflict')

    def test_historical_baseline_unverified_not_zero_and_attestation_bound_to_rules(self):
        rule=self._rule();batch=self._commercial_batch()
        self._context(batch,baseline_mode='explicit',baseline_date='2026-10-27')
        result=self._validate(batch)
        self.assertEqual(result.status,'baseline_unavailable')
        self.assertIn('BASELINE_UNVERIFIED',result.issue_ids.mapped('code'))
        self.assertNotIn('comparison',result.snapshot)
        self._context(batch,baseline_mode='explicit',baseline_date='2026-10-27',historical_attestation='Dated supplier contract reviewed')
        verified=self._validate(batch);self.assertEqual(verified.status,'commercially_valid')
        rule.price=950
        self.assertFalse(batch.get_commercially_valid_rows())
        reviewed=self._validate(batch);self.assertEqual(reviewed.status,'needs_review')
        self.assertEqual(D(verified.snapshot['baseline']['selected']['price']),1000)

    def test_backdated_offer_review_and_policy_block_are_not_application(self):
        self._rule(date_end='2026-10-31')
        r=list(VALID);r[0]='LED-12W-RED';r[2]='1150';r[4]='BOX';r[6]='2026-10-27'
        batch=self._commercial_batch([r]);self._context(batch,historical_attestation='Historical evidence')
        result=self._validate(batch);self.assertEqual(result.status,'needs_review')
        self.assertEqual(self.revision.state,'draft')
        self._policy_replace(backdated_proposal_policy='block')
        result=self._validate(batch);self.assertEqual(result.status,'date_conflict')

    def test_no_policy_and_no_arbitrary_product_tier_lookup(self):
        self._rule();batch=self._commercial_batch();self._context(batch)
        with self.assertRaises(AccessError):batch.resolve_vendor_tier(self.cable.id,'1',self.unit.id,'2026-10-31')
        self.env.cr.execute('UPDATE vendor_price_revision_config SET active=false WHERE id=%s',[self.financial.id]);self.financial.invalidate_recordset(['active'])
        result=self._validate(batch);self.assertEqual(result.status,'needs_review')
        self.assertIn('POLICY_UNAVAILABLE',result.issue_ids.mapped('code'))


@tagged('post_install','-at_install')
class TestCommercialSnapshots(CommercialFixtures,TransactionCase):
    def test_idempotent_immutable_versions_provenance_and_note_only_revalidation(self):
        rule=self._rule();batch=self._commercial_batch();context=self._context(batch)
        first=self._validate(batch)
        before=(batch.sha256_digest,batch.attachment_id.raw.content,batch.row_ids.raw_cells)
        self._validate(batch);self.assertEqual(batch.row_ids.commercial_result_id,first)
        self.assertEqual(len(batch.commercial_result_ids),1)
        self.assertEqual(first.context_id,context)
        self.assertEqual(first.structural_result_id,batch.row_ids.current_result_id)
        self.assertEqual(first.product_resolution_id,batch.row_ids.product_resolution_id)
        self.assertEqual(first.snapshot['source_hash'],before[0])
        batch.row_ids.action_correct('notes_raw','Shipping note only','No commercial term changed')
        batch.action_validate_structure();batch.action_match_products();self._validate(batch)
        self.assertEqual(batch.row_ids.commercial_result_id,first)
        self.assertEqual(before,(batch.sha256_digest,batch.attachment_id.raw.content,batch.row_ids.raw_cells))
        rule.price=900
        self.assertFalse(batch.get_commercially_valid_rows());self.assertEqual(batch.row_ids.commercial_status,'stale')
        second=self._validate(batch)
        self.assertEqual(second.version,2);self.assertEqual(second.previous_id,first)
        self.assertEqual(D(first.snapshot['baseline']['selected']['price']),1000)
        self.assertEqual(D(second.snapshot['baseline']['selected']['price']),900)

    def test_source_price_product_mapping_and_uom_changes_require_fresh_review(self):
        self._rule();batch=self._commercial_batch();self._context(batch);old=self._validate(batch)
        batch.row_ids.action_correct('proposed_price_raw','1250','Changed supplier price')
        self.assertEqual(batch.row_ids.commercial_status,'stale')
        batch.action_validate_structure();batch.action_match_products();self._context(batch);self._validate(batch)
        self.box.relative_factor=12
        self.assertFalse(batch.get_commercially_valid_rows())
        self.assertEqual(batch.row_ids.commercial_status,'stale')
        self.assertEqual(D(old.snapshot['proposal']['uom']['source']['factor']),10)
        self._context(batch);self._validate(batch)
        self.red.active=False
        self.assertFalse(batch.get_commercially_valid_rows())
        self.assertEqual(batch.row_ids.commercial_status,'stale')

    def test_description_only_row_mapping_cannot_survive_changed_source_identity(self):
        self._rule();r=list(VALID);r[0]='';r[2]='1150';r[4]='BOX'
        batch=self._commercial_batch([r]);self._verify(batch.row_ids,self.red,reusable=False)
        batch.action_match_products();self._context(batch);old=self._validate(batch)
        batch.row_ids.action_correct('vendor_product_name','Different supplier item','Source identity changed')
        batch.action_validate_structure();batch.action_match_products()
        self.assertEqual(batch.row_ids.product_match_status,'stale')
        self.assertFalse(batch.get_commercially_valid_rows())
        self.assertTrue(old.exists())

    def test_fx_assumption_and_policy_changes_mark_current_comparison_stale(self):
        self._policy_replace(currency_rate_policy='company_reference_date',currency_reference_date='2026-10-28')
        self._rates();self._rule(price=10,uom=self.unit,currency=self.usd)
        r=list(VALID);r[0]='LED-12W-RED';r[2]='11';r[3]='USD';r[4]='PCS'
        batch=self._commercial_batch([r]);self._context(batch);old=self._validate(batch)
        rate=self.env['res.currency.rate'].search([('currency_id','=',self.inr.id),('company_id','=',self.a.id),('name','=','2026-10-27')])
        rate.rate=95
        self.assertFalse(batch.get_commercially_valid_rows())
        self.assertEqual(D(old.snapshot['proposal']['fx']['rate']),94)
        fresh=self._validate(batch);self.assertEqual(D(fresh.snapshot['proposal']['fx']['rate']),95)
        self._policy_replace(currency_rate_policy='company_reference_date',currency_reference_date='2026-10-27')
        self.assertFalse(batch.get_commercially_valid_rows())

    def test_mid_batch_failure_rolls_back_partial_results_and_safe_retry(self):
        self._rule(product=self.red);self._rule(product=self.white)
        rows=[]
        for code in ('LED-12W-RED','LED-12W-WHT'):
            r=list(VALID);r[0]=code;r[2]='1150';r[4]='BOX';rows.append(r)
        batch=self._commercial_batch(rows);self._context(batch)
        original=type(self.env[RESULT])._record;calls=[]
        def fail_second(records,values):
            calls.append(values)
            if len(calls)==2:raise DatabaseError('private secret SQL/path')
            return original(records,values)
        with patch.object(type(self.env[RESULT]),'_record',fail_second):self.assertFalse(batch.action_validate_commercial_prices())
        self.assertEqual(len(calls),2)
        self.assertFalse(batch.commercial_result_ids)
        self.assertFalse(batch.row_ids.commercial_result_id)
        self.assertEqual(batch.commercial_processing_state,'failed')
        self.assertNotIn('secret',batch.commercial_error)
        self.assertTrue(batch.action_validate_commercial_prices())
        self.assertEqual(len(batch.commercial_result_ids),2)

    def test_counts_filters_and_excluded_rows_reconcile_current_detail(self):
        self._rule();rows=[]
        for price,qty in [('1150','1'),('900','100')]:
            r=list(VALID);r[0]='LED-12W-RED';r[2]=price;r[4]='BOX';r[5]=qty;rows.append(r)
        batch=self._commercial_batch(rows);self._context(batch);self._validate(batch)
        counts=batch.commercial_counts
        from ..models.commercial_validation import STATUSES
        self.assertEqual(sum(counts[s] for s,label in STATUSES),counts['total_rows'])
        found=self.env[ROW].with_env(batch.env).with_context(commercial_review_batch_id=batch.id).search([('commercial_status','=','commercially_valid')])
        self.assertEqual(found,batch.get_commercially_valid_rows())
        increases=self.env[ROW].with_env(batch.env).with_context(commercial_review_batch_id=batch.id).search([('commercial_classification','=','increase')])
        self.assertEqual(len(increases),1)
        self.assertEqual(counts['decrease'],1)
        batch.row_ids[1].action_set_excluded(True,'Withdrawn supplier tier');batch.action_validate_structure()
        self.assertEqual(batch.row_ids[1].commercial_status,'excluded')
        self.assertEqual(batch.commercial_counts['excluded'],1)

    def test_500_rows_bulk_scoped_queries_and_no_duplicate_current_results(self):
        codes=[f'PR08-BULK-{i}' for i in range(500)]
        products=self.env['product.product'].create([{'name':c,'default_code':c} for c in codes])
        self.env['product.supplierinfo'].create([{'partner_id':self.vendor.id,'company_id':self.a.id,'product_id':p.id,'price':100,'uom_id':self.unit.id,'currency_id':self.inr.id,'min_qty':1,'date_end':'2026-10-31'} for p in products])
        rows=[]
        for code in codes:
            r=list(VALID);r[0]=code;r[2]='115';r[4]='PCS';rows.append(r)
        batch=self._commercial_batch(rows);self._context(batch)
        original=type(self.env['product.supplierinfo']).search;searches=[]
        def count(records,*args,**kwargs):searches.append(1);return original(records,*args,**kwargs)
        started=time.monotonic()
        with patch.object(type(self.env['product.supplierinfo']),'search',count):self.assertTrue(batch.action_validate_commercial_prices())
        elapsed=time.monotonic()-started
        self.assertLessEqual(len(searches),8,'Supplier searches must be bulk and independent of row count')
        self.assertEqual(batch.commercial_counts['commercially_valid'],500)
        self.assertEqual(len(batch.commercial_result_ids),500)
        self._validate(batch);self.assertEqual(len(batch.commercial_result_ids),500)
        logging.getLogger(__name__).info('PR08_WORKLOAD rows=500 valid=500 seconds=%.3f supplier_searches=%s peak_memory=NOT_MEASURED',elapsed,len(searches))

    def test_source_product_supplier_rate_and_notifications_unchanged_by_validation(self):
        rule=self._rule();batch=self._commercial_batch();self._context(batch)
        masters=(rule.read(['price','discount','min_qty','date_start','date_end','currency_id','uom_id','write_date']),self.red.read(['standard_price','list_price','uom_id','write_date']))
        source=(batch.sha256_digest,batch.attachment_id.raw.content,batch.row_ids.raw_cells,self.revision.state,self.revision.write_date)
        models=('product.product','product.supplierinfo','product.pricelist.item','res.currency.rate','mail.mail','mail.message','mail.activity','ir.cron')
        counts={m:self.env[m].search_count([]) for m in models}
        self._validate(batch);self._validate(batch)
        self.assertEqual(masters,(rule.read(['price','discount','min_qty','date_start','date_end','currency_id','uom_id','write_date']),self.red.read(['standard_price','list_price','uom_id','write_date'])))
        self.assertEqual(source,(batch.sha256_digest,batch.attachment_id.raw.content,batch.row_ids.raw_cells,self.revision.state,self.revision.write_date))
        self.assertEqual(counts,{m:self.env[m].search_count([]) for m in models})


@tagged('post_install','-at_install')
class TestCommercialSecurity(CommercialFixtures,TransactionCase):
    def test_company_and_role_scopes_apply_to_read_export_group_and_actions(self):
        self._rule();batch=self._commercial_batch();self._context(batch);result=self._validate(batch)
        for role in ('sales','portal','employee','configuration','other'):
            for records in (result,result.context_id):
                with self.assertRaises(AccessError):self._as(records,role).read(['id'])
                with self.assertRaises(AccessError):self._as(records,role).export_data(['id'])
        for role in ('auditor','finance','pricing','director'):
            self.assertTrue(self._as(result,role).read(['snapshot']))
            scoped=self._as(batch.row_ids,role)
            scoped.invalidate_recordset(['commercial_status'])
            self.assertEqual(scoped.commercial_status,'commercially_valid')
            with self.assertRaises(AccessError):self._as(batch,role).action_validate_commercial_prices()
        self.assertFalse(self._as(self.env[RESULT],'purchase_b')._read_group([],['company_id'],['__count']))
        with self.assertRaises(AccessError):self._as(batch,'purchase_b').action_validate_commercial_prices()
        with self.assertRaises(AccessError):self._as(result,'purchase_b').read(['id'])
        with self.assertRaises(AccessError):self._as(result,'purchase_b').export_data(['snapshot'])

    def test_direct_create_write_nested_copy_delete_and_context_forgery_denied(self):
        self._rule();batch=self._commercial_batch();context=self._context(batch);result=self._validate(batch)
        for model in (RESULT,CONTEXT,ISSUE):
            with self.assertRaises(AccessError):self._as(self.env[model]).with_context(default_status='commercially_valid',skip_security=True).create({'batch_id':batch.id})
        for record in (result,context):
            for values in ({'company_id':self.b.id},{'state':'verified'},{'snapshot':{'company_price':'0'}}):
                with self.assertRaises(AccessError):record.write(values)
            with self.assertRaises(AccessError):record.unlink()
            with self.assertRaises(AccessError):record.copy()
        with self.assertRaises(AccessError):batch.write({'commercial_result_ids':[Command.clear()]})
        with self.assertRaises(AccessError):batch.row_ids.write({'commercial_result_id':result.id})
        with self.assertRaises(AccessError):batch.write({'current_commercial_context_id':context.id})

    def test_foreign_rules_do_not_leak_even_with_role_union_and_selected_companies(self):
        private=self._rule(price=123456,company=self.b)
        batch=self._commercial_batch();self._context(batch)
        self.users['purchase'].company_ids=[Command.link(self.b.id)]
        self.users['purchase'].group_ids=[Command.link(self.env.ref(MODULE+'.group_vpr_finance_manager').id)]
        result=self._validate(batch.with_context(allowed_company_ids=(self.a|self.b).ids))
        self.assertEqual(result.status,'baseline_unavailable')
        self.assertNotIn('123456',str(result.read(['snapshot'])))
        self.assertNotIn(private.id,[c.get('id') for c in result.snapshot['baseline'].get('candidates',[])])

    def test_wizard_foreign_links_alias_reparent_and_context_defaults_rejected(self):
        batch=self._commercial_batch();foreign=self._commercial_batch(role='purchase_b')
        model=self._as(self.env[WIZARD])
        with self.assertRaises(AccessError):model.create({'batch_id':foreign.id,'reason':'Foreign source'})
        with self.assertRaises(AccessError):model.with_context(default_batch_id=foreign.id).create({'reason':'Forged context'})
        wizard=model.create({'batch_id':batch.id,'reason':'Allowed source'})
        with self.assertRaises(AccessError):wizard.write({'batch_id':foreign.id})
        alias=self._as(self.env[ALIAS_WIZARD]).create({'wizard_id':wizard.id,'source_text':'BOX','uom_id':self.box.id})
        with self.assertRaises(AccessError):alias.write({'wizard_id':999})
        self.assertFalse(hasattr(wizard,'action_apply_prices'))

    def test_moved_product_history_masks_current_labels_and_related_exports(self):
        self._rule();batch=self._commercial_batch();self._context(batch);result=self._validate(batch)
        self.template.write({'company_id':self.b.id,'name':'PRIVATE PR08 COMPANY B NEW NAME'})
        self.assertFalse(batch.get_commercially_valid_rows())
        self.assertNotIn('PRIVATE PR08 COMPANY B NEW NAME',str(result.read(['product_id','snapshot'])))
        self.users['purchase'].group_ids=[Command.link(self.env.ref('base.group_allow_export').id)]
        with self.assertRaises(AccessError):result.export_data(['product_id'])
        with self.assertRaises(AccessError):batch.export_data(['commercial_result_ids/product_id'])

    def test_published_policy_read_is_narrow_and_does_not_grant_write_or_draft_access(self):
        policy=self._as(self.financial)
        self.assertEqual(policy.get_company_revision_config(self.a,'2026-11-01'),policy)
        with self.assertRaises(AccessError):policy.write({'currency_rate_policy':'authorized_scenario_rate'})
        draft=self.financial.copy({'policy_version':'draft-no-purchase-read'})
        with self.assertRaises(AccessError):self._as(draft).read(['id'])
        with self.assertRaises(AccessError):self._as(self.financial_b).read(['id'])

    def test_protected_state_no_bypass_no_application_and_views_load(self):
        batch=self._commercial_batch();self._context(batch)
        for model,xmlid in [(BATCH,'view_import_batch_form'),(RESULT,'view_commercial_result_form'),(WIZARD,'view_commercial_wizard_form')]:
            self.assertTrue(self._as(self.env[model],'manager').get_view(view_id=self.env.ref(MODULE+'.'+xmlid).id,view_type='form')['arch'])
        self.env.cr.execute('UPDATE vendor_price_revision SET state=%s WHERE id=%s',['approved',self.revision.id]);self.revision.invalidate_recordset(['state'])
        with self.assertRaises(UserError):batch.with_context(skip_security=True).action_validate_commercial_prices()
        for action in ('action_apply_prices','action_approve','action_simulate_exposure'):
            self.assertFalse(hasattr(batch,action))
