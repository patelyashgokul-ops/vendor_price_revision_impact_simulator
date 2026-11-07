"""PR17 real frozen PR08-16 references, isolation and confidentiality."""
import logging
import time
from copy import deepcopy
from decimal import Decimal as D
from unittest.mock import patch
from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from .test_reconciliation import ReconciliationFixtures
from .test_commercial_validation import MODULE
from ..models.vendor_scenario import HEADER,INPUT,LINE,RESULT,DETAIL,EVENT
from ..models.scenario_math import negotiated

_logger=logging.getLogger(__name__)

@tagged('post_install','-at_install')
class TestVendorScenarioMath(TransactionCase):
    def test_explicit_fixed_percent_and_old_base(self):
        self.assertEqual(negotiated('115','100','explicit','112'),112)
        self.assertEqual(negotiated('115','100','fixed_discount','3'),112)
        self.assertEqual(negotiated('115','100','percent_discount','10'),D('103.5'))
        self.assertEqual(negotiated('115','100','percent_discount','10','old'),90)

    def test_unknown_nonfinite_negative_invalid_discount(self):
        for mode,value in [('explicit',None),('explicit','NaN'),('explicit','-1'),('percent_discount','101'),('fixed_discount','116')]:
            with self.subTest(mode=mode,value=value),self.assertRaises(ValidationError):negotiated('115','100',mode,value)

    def test_zero_discount_and_below_old_price(self):
        self.assertEqual(negotiated('115','100','percent_discount','100'),0)
        self.assertEqual(negotiated('115','100','explicit','95'),95)

class ScenarioFixtures(ReconciliationFixtures):
    def _scenario(self,base=None,name='Analytical alternative'):
        base=base or self._reference16()
        return base.batch_id.with_user(self.users['finance']).action_create_vendor_scenario(base.id,name)

    def _spec(self,mode='explicit',value='112',**kw):
        result=dict(product_id=self.red.id,mode=mode,reason='Documented hypothetical supplier discussion')
        if value is not None:result['value']=value
        result.update(kw);return result

    def _set(self,s,spec):return s.action_set_assumptions([spec],'Independent scenario assumption revision')

    def _assert(self,r,cost,profit,improvement):
        self.assertEqual(D(r.profit['baseline_cost']),20000)
        self.assertEqual(D(r.profit['revised_cost']),D(cost));self.assertEqual(D(r.projected_profit),D(profit))
        self.assertEqual(D(r.improvement_vs_proposal),D(improvement));self.assertEqual(r.state,'financially_verified')
        self.assertTrue(r.complete);self.assertEqual(len(r.detail_ids),3)
        self.assertTrue(all(c['status'] in ('pass','not_applicable') for c in r.controls),r.controls)

@tagged('post_install','-at_install')
class TestVendorScenarioReferences(ScenarioFixtures,TransactionCase):
    def test_four_reference_alternatives_and_risk_recalculation(self):
        s=self._scenario();base=s.baseline_id;scenarios=s
        r=s.action_calculate_scenario();self._assert(r,21500,6500,0)
        for unit,cost,profit,benefit in [('112',21200,6800,300),('109',20900,7100,600),('105',20500,7500,1000)]:
            alternative=s.action_clone_scenario('Negotiate '+unit);self._set(alternative,self._spec(value=unit))
            r=alternative.action_calculate_scenario();self._assert(r,cost,profit,benefit)
            self.assertAlmostEqual(float(r.projected_margin),profit/28000*100,places=8)
            self.assertEqual(D(r.profit['net_revenue']),28000)
            self.assertEqual(r.profit['revised_risk'],'warning' if unit=='112' else 'normal')
            scenarios|=alternative
        self.assertEqual(len(scenarios.action_compare_scenarios()['domain'][0][2]),4)
        self.assertEqual(D(base.margin_id.revised_cost),21500)
        _logger.info('PR17_REFERENCE baseline20000 proposal21500 negotiated112=21200/6800/300 negotiated109=20900/7100/600 negotiated105=20500/7500/1000 revenue28000 alternatives_not_additive')

    def test_fixed_and_percentage_discounts_not_applied_to_protected_sources(self):
        s=self._scenario();self._set(s,self._spec('fixed_discount','3'));self._assert(s.action_calculate_scenario(),21200,6800,300)
        self._set(s,self._spec('percent_discount','10'));r=s.action_calculate_scenario();self._assert(r,20350,7650,1150)
        self.assertEqual([D(d.values['revised_extended_cost']) for d in r.detail_ids if d.values['source_type']!='new_procurement_requirement'],[6000,4000])

    def test_discount_old_base_and_negative_exposure(self):
        s=self._scenario();self._set(s,self._spec('percent_discount','5',discount_base='old'))
        r=s.action_calculate_scenario();self._assert(r,19500,8500,2000)
        self.assertEqual(D(r.financial['totals']['incremental_total']),-500)

    def test_missing_unknown_stock_cost_never_filled_by_negotiated_price(self):
        self._policy16();self._commercial14();self.red.categ_id.property_cost_method='fifo';self._quant(60);self._sales15(200)
        s=self._scenario(self._reconcile());self._set(s,self._spec());r=s.action_calculate_scenario()
        self.assertFalse(r.complete);self.assertFalse(r.projected_profit);self.assertFalse(r.improvement_vs_proposal)
        self.assertNotEqual(r.state,'financially_verified');self.assertIsNone(r.profit['revised_cost'])

    def test_strict_baseline_cannot_be_bypassed(self):
        s=self._scenario(self._reference16(projection=False));self._set(s,self._spec());r=s.with_context(financially_verified=True,skip_reconciliation=True).action_calculate_scenario()
        self.assertNotEqual(r.state,'financially_verified')
        with self.assertRaises(UserError):s.action_compare_scenarios()

    def test_exact_protected_po_hypothesis_600_separate(self):
        s=self._scenario();f=s.baseline_id.margin_id.financial_id
        source=f.line_ids.filtered(lambda l:l.cost_line_id.evidence.get('po_line_id'))
        po=source.cost_line_id.evidence['po_line_id'];actual=self.env['purchase.order.line'].browse(po).price_unit
        self._set(s,self._spec(value='115',po_line_id=po,po_evidence='Unaccepted supplier amendment request'))
        r=s.action_calculate_scenario();self._assert(r,22100,5900,-600)
        self.assertEqual(self.env['purchase.order.line'].browse(po).price_unit,actual)
        self.assertFalse(r.provenance['price_accepted'])
        self.assertEqual(D(f.revised_total),21500)
        _logger.info('PR17_PO_HYPOTHESIS protected40x100 remains native100 hypothetical40x115 additional600 total22100 unapproved')

    def test_date_delay_uses_documented_commitment_not_delivery(self):
        s=self._scenario();self._set(s,self._spec(value='112',effective_date='2026-12-01',commitment_date='2026-11-05',timing_evidence='Explicit hypothetical commercial commitment on November5'))
        self._assert(s.action_calculate_scenario(),20000,8000,1500)
        self._set(s,self._spec(value='112',effective_date='2026-11-05',commitment_date='2026-11-05',timing_evidence='Boundary date commercial commitment'))
        self._assert(s.action_calculate_scenario(),21200,6800,300)

    def test_date_unknown_is_incomplete(self):
        s=self._scenario();self._set(s,self._spec(value='112',effective_date='2026-12-01'));r=s.action_calculate_scenario()
        self.assertFalse(r.complete);self.assertFalse(r.projected_profit);self.assertNotEqual(r.state,'financially_verified')

    def test_tier_100_eligible_500_ineligible_surplus_blocked(self):
        self._policy16();self._commercial14(tiers=[(1,115),(100,109),(500,104)]);self.red.with_company(self.a).standard_price=100
        self._quant(60);po,line=self._po(40,100);self._sales15(200);self._assess12(self._row12(self._collect12(),line))
        s=self._scenario(self._reconcile());rows=s.batch_id.row_ids
        tier=rows.filtered(lambda r:D(r.commercial_result_id.snapshot['proposal']['normalized_min_qty'])==100)
        self._set(s,self._spec('tier',None,row_id=tier.id,buying_quantity='100'));r=s.action_calculate_scenario()
        self.assertEqual(D(r.profit['revised_cost']),20900);self.assertEqual(r.state,'financially_verified')
        self._set(s,self._spec('tier',None,row_id=rows[-1].id,buying_quantity='500'));r=s.action_calculate_scenario()
        self.assertFalse(r.complete);self.assertIsNone(r.profit['revised_cost'])
        _logger.info('PR17_MOQ actual residual100 eligible100 tier109; surplus500 rejected without allocating invented quantities')

    def test_explicit_grouping_40_60_no_duplicate_demand(self):
        self._policy16();self._commercial14(tiers=[(1,115),(100,109)]);self._sales15(40);self._sales15(60)
        s=self._scenario(self._reconcile());tier=s.batch_id.row_ids[-1]
        self._set(s,self._spec('tier',None,row_id=tier.id,grouped=True,group_reason='Same company/vendor/product/UoM/warehouse commercial buying group',buying_quantity='100'))
        r=s.action_calculate_scenario();self.assertEqual(D(r.profit['revised_cost']),10900);self.assertEqual(r.state,'financially_verified')
        self.assertEqual(sum(D(v.values['quantity']) for v in r.detail_ids),100)

    def test_fx_90_44_decomposition_preserves_rate_table(self):
        self._rates(old=90,new=90)
        self._policy15(reconciliation_basis_policy='documented_projection',fx_override_policy='finance_governed',currency_rate_policy='company_reference_date',currency_reference_date='2026-10-28')
        self._commercial14(old=10,new=11,currency=self.usd)
        self._sales15(1);s=self._scenario(self._reconcile())
        before=self.env['res.currency.rate'].search([]).read(['rate','name','company_id'])
        source=s.baseline_id.margin_id.financial_id.line_ids
        old_fx=D(source.evidence['pricing']['old_fx']['rate'])
        self._set(s,self._spec('original',None,fx_method='fx_only_sensitivity',fx_rate=str(old_fx+4),fx_date='2026-11-05'))
        r=s.action_calculate_scenario();parts=r.detail_ids.values['decomposition']
        self.assertEqual(D(parts['supplier_component']),old_fx);self.assertEqual(D(parts['fx_component']),44)
        self.assertEqual(D(parts['total']),old_fx+44)
        self.assertEqual(before,self.env['res.currency.rate'].search([]).read(['rate','name','company_id']))
        _logger.info('PR17_FX actual_old_rate=%s price_effect=%s fx_effect44 total=%s',old_fx,old_fx,old_fx+44)

    def test_landed_policy_disabled_is_incomplete(self):
        s=self._scenario();component=dict(code='freight',amount='3',evidence='Future incremental freight not included in net proposal',nonrecoverable=True,not_included=True,currency_id=s.currency_id.id,uom_id=self.unit.id)
        self._set(s,self._spec('original',None,landed=[component]));r=s.action_calculate_scenario()
        self.assertFalse(r.complete);self.assertNotEqual(r.state,'financially_verified')

    def test_two_date_baseline_requires_explicit_combined_fx_not_price_only_label(self):
        self._rates()
        self._policy15(reconciliation_basis_policy='documented_projection',fx_override_policy='finance_governed',currency_rate_policy='company_reference_date',currency_reference_date='2026-10-28')
        self._commercial14(old=10,new=11,currency=self.usd,context=dict(baseline_mode='explicit',baseline_date='2026-10-27',comparison_mode='date_specific',historical_attestation='Dated supplier baseline independently checked'))
        self._sales15(100,price=1400);f=self._finance(method='date_specific');m=self._margin(f)
        s=self._scenario(self._reconcile(m));original=s.action_calculate_scenario()
        self.assertEqual(D(original.profit['baseline_cost']),90000)
        self.assertEqual(D(original.profit['revised_cost']),103400)
        before=s._inputs()
        with self.assertRaises(ValidationError):self._set(s,self._spec(value='10.9'))
        self.assertEqual(s._inputs(),before)
        self._set(s,self._spec(value='10.9',fx_method='combined_price_and_fx',fx_rate='95',fx_date='2026-11-05'))
        r=s.action_calculate_scenario();self.assertEqual(r.state,'financially_verified')
        self.assertEqual(D(r.profit['revised_cost']),103550)
        self.assertEqual(D(r.improvement_vs_proposal),-150)
        self.assertEqual(D(r.detail_ids.values['decomposition']['supplier_component']),81)
        self.assertEqual(D(r.detail_ids.values['decomposition']['fx_component']),D('54.5'))
        _logger.info('PR17_FX_METHOD_GUARD two-date90000/103400 rejects common-FX label; explicit10.9x95 total103550 potential_improvement-150')

    def test_unevidenced_source_charges_cannot_create_scenario_baseline(self):
        self._policy15(reconciliation_basis_policy='documented_projection',additional_cost_policy='evidenced_nonrecoverable_charges',scenario_landed_policy='evidenced_nonrecoverable_charges')
        self._rule(price=1000,uom=self.box);b=self._commercial_batch();self._context(b);b.action_validate_commercial_prices()
        self.assertNotEqual(b.row_ids.commercial_status,'commercially_valid')
        self.assertIn('TAX_BASIS_UNKNOWN',[v['code'] for v in b.row_ids.commercial_result_id.snapshot['issues']])
        self.assertFalse(b.get_commercially_valid_rows())

    def test_governed_future_landed_policy_keeps_net_baseline_and_verifies_arithmetic(self):
        self._policy15(reconciliation_basis_policy='documented_projection',scenario_landed_policy='evidenced_nonrecoverable_charges')
        self._commercial14();self.red.with_company(self.a).standard_price=100;self._quant(60)
        po,line=self._po(40,100);self._sales15(200);self._assess12(self._row12(self._collect12(),line))
        s=self._scenario(self._reconcile())
        components=[dict(code=code,amount=amount,evidence='Explicit future incremental '+code,nonrecoverable=True,not_included=True,currency_id=s.currency_id.id,uom_id=self.unit.id) for code,amount in [('freight','3'),('nonrecoverable_duty','2')]]
        self._set(s,self._spec('original',None,landed=components));self._assert(s.action_calculate_scenario(),22000,6000,-500)
        self.assertEqual(D(s.baseline_id.margin_id.revised_cost),21500)
        _logger.info('PR17_LANDED new100 at120 includes unique freight3 duty2; cost22000 profit6000 projected benefit-500 baseline21500 unchanged')

    def test_negative_profit_recalculates_critical_risk(self):
        s=self._scenario();self._set(s,self._spec(value='300'));r=s.action_calculate_scenario()
        self.assertEqual(D(r.projected_profit),-12000);self.assertEqual(r.risk_status,'critical')
        self.assertLess(D(r.projected_margin),0)

    def test_multi_product_override_preserves_omitted_proposal(self):
        from .test_import_validation import VALID
        self._policy16();self._rule(price=100,uom=self.unit);self._rule(price=80,uom=self.unit,product=self.white)
        rows=[]
        for code,amount in [('LED-12W-RED','115'),('LED-12W-WHT','90')]:
            row=list(VALID);row[0]=code;row[2]=amount;row[3]=self.inr.name;row[4]='PCS';row[5]='1';row[6]='2026-11-01';rows.append(row)
        b=self._commercial_batch(rows);self._context(b);b.action_validate_commercial_prices();self._pb=b
        self._sales15(100);self._sales15(100,product=self.white)
        s=self._scenario(self._reconcile());self._set(s,self._spec());r=s.action_calculate_scenario()
        self.assertEqual(D(r.profit['revised_cost']),20200)
        white=r.detail_ids.filtered(lambda d:d.values['product_id']==self.white.id)
        self.assertEqual(D(white.values['revised_unit_cost']),90)
        self.assertEqual(r.state,'financially_verified')

    def test_conditional_quotation_cohort_and_portfolio_not_additive(self):
        self._policy16();self._sales15(100);q,_=self._sales15(70,confirm=False);q2,_=self._sales15(30,confirm=False)
        a=self._run(batch=self._batch12());f=self._finance(a);m=self._margin(f);base=self._reconcile(m)
        baseline=self._scenario(base)
        qa=self._run(batch=self._batch12(),quotes=(q|q2).ids,reason='Explicit conditional quotation portfolio')
        qf=self._finance(qa,confirmed=f.id);qm=self._margin(qf,confirmed=m.id)
        conditional=self._scenario(self._reconcile(qm));self._set(conditional,self._spec());r=conditional.action_calculate_scenario()
        self.assertEqual(sum(D(v.values['quantity']) for v in r.detail_ids),200)
        self.assertFalse(r.provenance['alternatives_additive']);self.assertEqual(r.state,'financially_verified')
        with self.assertRaises(ValidationError):(baseline|conditional).action_compare_scenarios()

    def test_box_source_negotiation_normalizes_per_piece_once(self):
        from .test_import_validation import VALID
        self._policy16();self._rule(price=1000,uom=self.box)
        row=list(VALID);row[0]='LED-12W-RED';row[2]='1150';row[3]=self.inr.name;row[4]='BOX';row[5]='1';row[6]='2026-11-01'
        b=self._commercial_batch([row]);self._context(b);b.action_validate_commercial_prices();self._pb=b;self._sales15(100)
        s=self._scenario(self._reconcile());self._set(s,self._spec(value='1120',uom_id=self.box.id));r=s.action_calculate_scenario()
        self.assertEqual(D(r.profit['revised_cost']),11200);self.assertEqual(D(r.improvement_vs_proposal),300)

@tagged('post_install','-at_install')
class TestVendorScenarioLifecycle(ScenarioFixtures,TransactionCase):
    def test_clone_independence_versions_idempotency_and_staleness(self):
        s=self._scenario();a=s.action_calculate_scenario();clone=s.action_clone_scenario('Independent B')
        self.assertFalse(clone.result_ids);self._set(clone,self._spec());b=clone.action_calculate_scenario()
        self.assertEqual(clone.action_calculate_scenario(),b);self.assertEqual(s.get_current_scenario(),a)
        clone.action_select_for_review('preferred_for_review','Hypothetical discussion preference only')
        self._set(clone,self._spec(value='109'));self.assertEqual(clone.selection_status,'not_selected')
        with self.assertRaises(UserError):clone.get_current_scenario()
        c=clone.action_calculate_scenario();self.assertEqual(c.previous_id,b);self.assertEqual(c.version,2)
        self.assertEqual(D(b.projected_cost),21200);self.assertEqual(D(c.projected_cost),20900)

    def test_assumption_rejections_are_atomic(self):
        s=self._scenario();original=s._inputs()
        for spec in [self._spec(value=None),self._spec(value='-1'),self._spec(value='NaN'),self._spec('percent_discount','101'),self._spec(price='112'),self._spec(grouped=True),self._spec(fx_method='fx_only_sensitivity',fx_rate='94',fx_date='2026-11-05'),self._spec(po_line_id=999999,po_evidence='Wrong PO')]:
            with self.subTest(spec=spec),self.assertRaises(ValidationError):self._set(s,spec)
            self.assertEqual(s._inputs(),original)

    def test_wrong_currency_uom_and_fx_governance_not_verified(self):
        s=self._scenario()
        for spec in [self._spec(currency_id=self.usd.id),self._spec(uom_id=self.env.ref('uom.product_uom_dozen').id),self._spec(fx_method='combined_price_and_fx',fx_rate='94',fx_date='2026-11-05')]:
            self._set(s,spec);self.assertNotEqual(s.action_calculate_scenario().state,'financially_verified')

    def test_duplicate_cost_components_recoverable_or_wrong_units_rejected(self):
        s=self._scenario();v=dict(code='freight',amount='3',evidence='Hypothetical incremental',nonrecoverable=True,not_included=True,currency_id=s.currency_id.id,uom_id=self.unit.id)
        for values in ([v,v],[dict(v,not_included=False)],[dict(v,nonrecoverable=False)],[dict(v,currency_id=self.usd.id)]):
            with self.assertRaises(ValidationError):self._set(s,self._spec(landed=values))

    def test_source_change_stales_history_and_blocks_comparison(self):
        s=self._scenario();old=s.action_calculate_scenario();so=s.baseline_id.margin_id.sales_id.order_ids
        s.action_select_for_review('preferred_for_review','Current analytical preference before source change')
        so.order_line.price_unit=150
        self.assertNotEqual(s.selection_status,'preferred_for_review')
        with self.assertRaises(UserError):s.get_current_scenario()
        self.assertEqual(D(old.projected_cost),21500)
        with self.assertRaises(UserError):s.action_compare_scenarios()

    def test_archive_immutable_history_selection_not_approval(self):
        s=self._scenario();r=s.action_calculate_scenario()
        with self.assertRaises(ValidationError):s.action_select_for_review('approved','Forged acceptance')
        s.action_select_for_review('archived','Retain this alternative as historical')
        with self.assertRaises(UserError):s.action_calculate_scenario()
        self.assertTrue(r.exists());self.assertTrue(s.action_clone_scenario('New draft').exists())

    def test_failed_detail_publication_rolls_back_and_retry(self):
        s=self._scenario()
        with patch.object(type(self.env[DETAIL]),'_record',side_effect=UserError('Injected PR17 interrupted publication')):
            with self.assertRaises(UserError):s.action_calculate_scenario()
        self.assertFalse(self.env[RESULT].search([('scenario_id','=',s.id)]));self.assertTrue(s.action_calculate_scenario().complete)

    def test_empty_optional_wizard_boundary_and_baseline_drilldown(self):
        s=self._scenario();w=self.env[HEADER+'.wizard'].with_user(self.users['finance']).create(dict(scenario_id=s.id,product_id=self.red.id,mode='explicit',value='112',reason='UI exact negotiated price'))
        self.assertIn('115',w.source_basis);self.assertIn(self.inr.display_name,w.source_basis)
        self.assertIn(self.unit.display_name,w.source_basis);self.assertIn('100',w.source_basis)
        self.assertEqual(w.action_save()['res_id'],s.id);self._assert(s.action_calculate_scenario(),21200,6800,300)
        self.assertEqual(s.action_open_baseline()['res_id'],s.baseline_id.id)

    def test_ten_alternatives_benchmark(self):
        s=self._scenario();started=time.perf_counter();results=[]
        for i in range(10):
            v=s.action_clone_scenario('Alternative '+str(i));self._set(v,self._spec(value=str(105+i)));results.append(v.action_calculate_scenario())
        self.assertEqual(len(set(r.id for r in results)),10);self.assertTrue(all(r.complete for r in results))
        _logger.info('PR17_WORKLOAD scenarios=10 seconds=%.3f details=%s',time.perf_counter()-started,sum(len(r.detail_ids) for r in results))

@tagged('post_install','-at_install')
class TestVendorScenarioSecurity(ScenarioFixtures,TransactionCase):
    def test_purchase_manager_without_customer_grant_cannot_read_or_group(self):
        s=self._scenario();s.action_calculate_scenario();manager=self.users['manager']
        self.env['vendor.price.revision.sales.grant'].search([('user_id','=',manager.id)]).write({'active':False,'reason':'No customer-commercial grant for purchase-only review'})
        denied=s.with_user(manager)
        with self.assertRaises(AccessError):denied.read(['name'])
        with self.assertRaises(AccessError):denied.export_data(['name'])
        self.assertEqual(self.env[HEADER].with_user(manager)._read_group([],[],['__count'])[0][0],0)

    def test_sales_purchase_portal_public_no_derived_cost_disclosure(self):
        s=self._scenario();r=s.action_calculate_scenario()
        for user in (self.users['sales'],self.users['purchase'],self.env.ref('base.public_user')):
            for record in (s,r,s._inputs(),s._inputs().line_ids,r.detail_ids):
                if record:
                    with self.subTest(user=user.id,model=record._name),self.assertRaises(AccessError):record.with_user(user).read(['id'])
            with self.assertRaises(AccessError):s.with_user(user).action_calculate_scenario()
        # This fixture manager has both Purchase/Sales roles AND explicit cost/
        # customer grants. Such combined authorized read scope is intentional.
        self.assertTrue(s.with_user(self.users['manager']).read(['name']))
        with self.assertRaises(AccessError):s.with_user(self.users['manager']).action_calculate_scenario()

    def test_auditor_readonly_and_public_create_write_forgery(self):
        s=self._scenario();r=s.action_calculate_scenario();auditor=s.with_user(self.users['auditor'])
        self.assertTrue(auditor.read(['name']))
        for record in (s,r,s._inputs(),r.detail_ids):
            with self.assertRaises(AccessError):record.with_context(skip_security=True).write({'batch_id':s.batch_id.id})
            with self.assertRaises(AccessError):record.unlink()
        with self.assertRaises(AccessError):auditor.action_set_assumptions([],'Unauthorized')
        with self.assertRaises(AccessError):self.env[RESULT].with_user(self.users['finance']).create({'state':'financially_verified'})

    def test_other_company_and_revoked_source_scope_deny_search_export(self):
        s=self._scenario();r=s.action_calculate_scenario();foreign=self.users['purchase_b']
        with self.assertRaises(AccessError):s.with_user(foreign).read(['name'])
        with self.assertRaises(AccessError):self.env[HEADER].with_user(foreign).search([('id','=',s.id)])
        grants=self.env['vendor.price.revision.supply.grant'].search([('user_id','=',self.users['finance'].id)])
        grants.write({'allow_cost':False,'reason':'Revoke scenario supplier cost authority'})
        with self.assertRaises(AccessError):r.export_data(['projected_profit'])
        with self.assertRaises(AccessError):s.get_current_scenario()
