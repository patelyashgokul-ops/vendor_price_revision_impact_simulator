"""PR15 actual PR11/14 integration plus independent mathematical references."""
import logging
import time
from decimal import Decimal as D
from unittest.mock import patch
from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from .test_financial_exposure import FinancialFixtures
from .test_commercial_validation import MODULE
from ..models.profitability import HEADER, LINE, AGGREGATE, RISK, MarginEngine, policy_values
from ..models.profitability_math import profitability, assess, reported
from ..models.sales_exposure import GRANT as SALES_GRANT

_logger=logging.getLogger(__name__)
POLICY=dict(id=1,minimum='15',target='25',erosion_enabled=True,erosion_points='5',negative_profit_critical=True)
RULES=[dict(id=1,minimum='0',maximum='100000',level='low'),dict(id=2,minimum='100000',maximum=None,level='high')]


@tagged('post_install','-at_install')
class TestProfitabilityMath(TransactionCase):
    def test_reference_profit_and_signed_reduction(self):
        v=profitability('28000','20000','21500')
        self.assertEqual(tuple(D(v[k]) for k in ('baseline_gross_profit','revised_gross_profit','gross_profit_change','gross_profit_reduction')), (8000,6500,-1500,1500))
        self.assertEqual(D(v['gross_profit_change']),-(D(v['revised_cost'])-D(v['baseline_cost'])))

    def test_reference_margin_erosion_and_relative_reduction(self):
        v=profitability('28000','20000','21500')
        self.assertAlmostEqual(float(v['baseline_margin_percent']),28.5714285714,places=8)
        self.assertAlmostEqual(float(v['revised_margin_percent']),23.2142857143,places=8)
        self.assertAlmostEqual(float(v['margin_erosion_points']),5.3571428571,places=8)
        self.assertEqual(D(v['profit_reduction_percent']),D('18.75'))
        self.assertAlmostEqual(float(v['relative_margin_decline_percent']),18.75,places=8)
        self.assertEqual(reported(v,'.01')['baseline_margin_percent'],'28.57')
        self.assertEqual(reported(v,'.01')['revised_margin_percent'],'23.21')

    def test_margin_is_not_markup(self):
        v=profitability('140','100','100')
        self.assertAlmostEqual(float(v['baseline_margin_percent']),28.57142857,places=7)
        self.assertEqual((D(140)-D(100))/D(100)*100,40)
        self.assertNotEqual(D(v['baseline_margin_percent']),40)

    def test_zero_revenue_preserves_loss_without_percentage(self):
        v=profitability('0','100','115')
        self.assertEqual(D(v['revised_gross_profit']),-115)
        self.assertIsNone(v['revised_margin_percent'])
        self.assertEqual(assess(v,POLICY,RULES,'fully_verified',True)['risk_status'],'review_required')

    def test_negative_revenue_review_with_monetary_reference(self):
        v=profitability('-10','100','115')
        self.assertEqual(D(v['revised_gross_profit']),-125)
        self.assertIsNone(v['baseline_margin_percent'])

    def test_missing_is_not_zero(self):
        for n,b,r in [(None,'100','115'),('140',None,None)]:
            v=profitability(n,b,r);self.assertIsNone(v['revised_gross_profit']);self.assertIsNone(v['revised_margin_percent'])

    def test_negative_and_extreme_margin(self):
        for n,c,profit,margin in [('10000','12000','-2000','-20'),('100','350','-250','-250')]:
            v=profitability(n,c,c);self.assertEqual(D(v['revised_gross_profit']),D(profit));self.assertEqual(D(v['revised_margin_percent']),D(margin))
            self.assertEqual(assess(v,POLICY,RULES,'fully_verified',True)['risk_status'],'critical')

    def test_cost_reduction_improves_profit(self):
        v=profitability('140','115','100')
        self.assertEqual(D(v['gross_profit_change']),15);self.assertLess(D(v['margin_erosion_points']),0)
        self.assertLess(D(v['gross_profit_reduction']),0)
        self.assertEqual(assess(v,POLICY,RULES,'fully_verified',True)['revision_effect'],'risk_improved')

    def test_zero_negative_baseline_profit_relative_ratio_unavailable(self):
        for b in ('140','150'):
            v=profitability('140',b,'160');self.assertIsNone(v['profit_reduction_percent']);self.assertIsNone(v['relative_margin_decline_percent'])

    def test_weighted_ratio_not_average_percent(self):
        a=profitability('10000','7000','7000');b=profitability('90000','81000','81000')
        v=profitability(str(D(a['net_revenue'])+D(b['net_revenue'])),'88000','88000')
        self.assertEqual(D(v['revised_margin_percent']),12)
        self.assertEqual((D(a['revised_margin_percent'])+D(b['revised_margin_percent']))/2,20)

    def test_invalid_nonfinite_and_negative_cost_rejected(self):
        for n,b in [('NaN','1'),('Infinity','1'),('140','-1')]:
            with self.assertRaises(ValueError):profitability(n,b,'2')


@tagged('post_install','-at_install')
class TestProfitabilityRisk(TransactionCase):
    def test_six_inclusive_threshold_boundaries(self):
        for margin,expected in [('14.99','critical'),('15','critical'),('15.01','warning'),('24.99','warning'),('25','warning'),('25.01','normal')]:
            v=profitability('100',str(100-D(margin)),str(100-D(margin)))
            self.assertEqual(assess(v,POLICY,RULES,'fully_verified',True)['risk_status'],expected)

    def test_unrounded_classification(self):
        v=profitability('100','74.996','74.996')
        self.assertEqual(reported(v,'.01')['revised_margin_percent'],'25.00')
        self.assertEqual(assess(v,POLICY,RULES,'fully_verified',True)['risk_status'],'normal')

    def test_reference_warning_reasons_overlap(self):
        r=assess(profitability('28000','20000','21500'),POLICY,RULES,'scenario_only',True)
        self.assertEqual(r['risk_status'],'warning');self.assertEqual(r['revision_effect'],'new_warning')
        self.assertTrue({'LOW_REVISED_MARGIN','MATERIAL_MARGIN_EROSION'} <= {i['code'] for i in r['risk_reasons']})

    def test_preexisting_and_revision_risk(self):
        for b,r,e in [('70','80','new_warning'),('80','90','warning_to_critical'),('90','91','existing_critical_worsened'),('90','90','existing_risk_unchanged'),('80','70','risk_improved'),('60','60','no_new_margin_risk')]:
            got=assess(profitability('100',b,r),POLICY,RULES,'fully_verified',True)
            self.assertEqual(got['revision_effect'],e)

    def test_large_exposure_correct_company_currency_scale(self):
        v=profitability('1000000','500000','650000')
        r=assess(v,POLICY,RULES,'fully_verified',True)
        self.assertEqual(r['risk_status'],'high')
        self.assertTrue({'LARGE_INCREMENTAL_COST','MATERIAL_PROFIT_REDUCTION'} <= {i['code'] for i in r['risk_reasons']})

    def test_missing_policy_and_incomplete_not_normal(self):
        for policy,complete in [(None,True),(POLICY,False)]:
            r=assess(profitability('140',None,None),policy,RULES,'incomplete',complete)
            self.assertEqual(r['risk_status'],'review_required');self.assertEqual(r['revision_effect'],'undetermined')

    def test_incomplete_keeps_independent_severe_reason(self):
        r=assess(profitability('100',None,'350'),POLICY,RULES,'incomplete',False)
        self.assertEqual(r['risk_status'],'review_required')
        self.assertIn('NEGATIVE_GROSS_PROFIT',{i['code'] for i in r['risk_reasons']})

    def test_price_protection_context_not_adjustment_permission(self):
        v=profitability('140','100','115')
        r=assess(v,POLICY,RULES,'scenario_only',True,['fixed_price_verified','price_protection_unknown'])
        self.assertTrue({'FIXED_CUSTOMER_PRICE','CUSTOMER_PRICE_PROTECTION_UNKNOWN'} <= {i['code'] for i in r['risk_reasons']})

    def test_negative_profit_rule_and_reason_precedence(self):
        r=assess(profitability('100','90','350'),POLICY,RULES,'estimated',True)
        self.assertEqual(r['risk_status'],'critical')
        self.assertTrue({'NEGATIVE_GROSS_PROFIT','CRITICAL_REVISED_MARGIN','MATERIAL_MARGIN_EROSION'} <= {i['code'] for i in r['risk_reasons']})

    def test_erosion_dimension_boundary(self):
        for erosion,trigger in [('4.9999',False),('5',True),('5.0001',True),('-5',False)]:
            r=assess(profitability('100','50',str(50+D(erosion))),POLICY,RULES,'fully_verified',True)
            self.assertEqual('MATERIAL_MARGIN_EROSION' in {i['code'] for i in r['risk_reasons']},trigger)


class MarginFixtures(FinancialFixtures):
    def _sales15(self,qty=100,price=140,confirm=True,**kw):
        so,line=self._sale(qty,confirm=False,**kw);line.price_unit=price
        if confirm:so.action_confirm()
        return so,line

    def _policy15(self,**options):
        options.setdefault('margin_ids',[Command.create(dict(scope='company',minimum_margin_percent=15,target_margin_percent=25,
            erosion_enabled=True,erosion_warning_points=5,negative_profit_critical=True,reason='Explicit PR15 threshold test policy'))])
        return self._policy_replace(**options)

    def _margin(self,financial=None,confirmed=0,actor='manager'):
        f=financial or self._finance()
        return self._batch12().with_user(self.users[actor]).action_calculate_profitability(f.id,confirmed)

    def _reference15(self):
        self._policy15();self._commercial14();self.red.with_company(self.a).standard_price=100
        self._quant(60);po,line=self._po(40,100);so,sl=self._sales15(200)
        self._assess12(self._row12(self._collect12(),line));return self._margin()


@tagged('post_install','-at_install')
class TestProfitabilityIntegration(MarginFixtures,TransactionCase):
    def test_reference_actual_sources_risk_and_no_mutation(self):
        s=self._reference15()
        self.assertEqual(tuple(D(s[k]) for k in ('net_revenue','baseline_cost','revised_cost','baseline_gross_profit','revised_gross_profit')), (28000,20000,21500,8000,6500))
        self.assertEqual(D(s.gross_profit_change),-1500);self.assertEqual(D(s.gross_profit_reduction),1500)
        self.assertAlmostEqual(float(s.margin_erosion_points),5.3571428571,places=8)
        self.assertEqual(s.risk_status,'warning');self.assertEqual(s.revision_effect,'new_warning')
        self.assertEqual(s.state,'scenario_only');self.assertEqual(len(s.line_ids),1)
        self.assertEqual(len(s.line_ids.source_financial_line_ids),3)
        self.assertEqual(s.reported_values['baseline_margin_percent'],'28.57')
        self.assertEqual(s.reported_values['revised_margin_percent'],'23.21')
        self.assertEqual(s.baseline_margin_display,'28.57')
        self.assertEqual(s.revised_margin_display,'23.21')
        self.assertEqual(s.erosion_display,'5.36')
        self.assertEqual(s.sales_id,s.financial_id.sales_id)
        self.assertEqual(s.provenance['risk_policy']['version'],self.financial.policy_version)
        self.assertTrue({'LOW_REVISED_MARGIN','MATERIAL_MARGIN_EROSION'} <= set(s.risk_ids.mapped('code')))
        _logger.info('PR15_REFERENCE revenue28000 baseline20000 revised21500 profit8000/6500 change-1500 reduction1500 margin28.57142857/23.21428571 erosion5.35714286pp reduction18.75percent riskWARNING minimum15 target25 erosion5 scenario_only')

    def test_exact_same_product_lines_preserve_prices_and_identity(self):
        so,l=self._sales15(10,140);l2=self.env['sale.order.line'].create(dict(order_id=so.id,product_id=self.red.id,product_uom_qty=90,product_uom_id=self.unit.id,price_unit=200,tax_ids=[Command.clear()]))
        s=self._margin();self.assertEqual(set(s.line_ids.sale_line_id.ids),{l.id,l2.id})
        self.assertEqual(sorted(D(v.net_revenue) for v in s.line_ids),[D(1400),D(18000)])
        order=s.aggregate_ids.filtered(lambda v:v.dimension=='order');self.assertEqual(D(order.net_revenue),19400)
        self.assertEqual(D(order.revised_gross_profit),7900)
        self.assertAlmostEqual(float(order.revised_margin_percent),7900/19400*100,places=8)

    def test_customers_and_products_group_exact_variant(self):
        so,l=self._sales15(10);other=self.env['res.partner'].create({'name':'PR15 Other legal customer'})
        so2,l2=self._sales15(20);so2.partner_id=other
        s=self._margin();groups=s.aggregate_ids.filtered(lambda v:v.dimension=='customer')
        self.assertEqual(set(groups.mapped('source_id')),{self.customer.id,other.id})
        self.assertEqual(sum(D(v.net_revenue) for v in groups),D(s.net_revenue))
        product=s.aggregate_ids.filtered(lambda v:v.dimension=='product');self.assertEqual(product.source_id,self.red.id)

    def test_aggregate_ratio_does_not_hide_critical_constituent_line(self):
        self._sales15(10,90);self._sales15(90,300);s=self._margin()
        product=s.aggregate_ids.filtered(lambda v:v.dimension=='product')
        self.assertGreater(D(product.revised_margin_percent),25)
        self.assertEqual(product.risk_status,'normal')
        self.assertEqual(product.highest_line_risk,'critical')
        self.assertEqual(s.highest_line_risk,'critical')
        self.assertIn('NEGATIVE_GROSS_PROFIT',s.risk_ids.mapped('code'))

    def test_known_zero_price_not_missing_revenue(self):
        self._sales15(10,0);s=self._margin()
        self.assertEqual(D(s.net_revenue),0);self.assertEqual(D(s.revised_gross_profit),-1150)
        self.assertFalse(s.revised_margin_percent);self.assertEqual(s.risk_status,'review_required')

    def test_negative_profit_actual_sources(self):
        self._sales15(100,100);s=self._margin()
        self.assertEqual(D(s.revised_gross_profit),-1500);self.assertEqual(D(s.revised_margin_percent),-15)
        self.assertEqual(s.risk_status,'critical')

    def test_unknown_fifo_incremental_only_not_gross_profit(self):
        self.red.categ_id.with_company(self.a).property_cost_method='fifo';self._quant(60);self._sales15(160)
        s=self._margin();self.assertEqual(D(s.financial_id.incremental_total),1500)
        self.assertFalse(s.baseline_cost or s.revised_gross_profit or s.revised_margin_percent)
        self.assertEqual(s.risk_status,'review_required');self.assertEqual(D(s.net_revenue),22400)

    def test_missing_company_sales_fx_not_zero(self):
        so,l=self._sales15(100,20,confirm=False);pl=self.env['product.pricelist'].create(dict(name='PR15 USD',company_id=self.a.id,currency_id=self.usd.id));so.pricelist_id=pl;so.action_confirm()
        s=self._margin();self.assertFalse(s.net_revenue or s.revised_gross_profit)
        self.assertEqual(D(s.revised_cost),11500);self.assertEqual(s.risk_status,'review_required')

    def test_global_discount_not_fabricated_as_product_revenue(self):
        so,l=self._sales15(100);discount=self.env['product.product'].create({'name':'Global discount','type':'service'});self.a.sale_discount_product_id=discount
        self.env['sale.order.line'].create(dict(order_id=so.id,product_id=discount.id,product_uom_qty=1,price_unit=-1000,tax_ids=[Command.clear()]))
        s=self._margin();self.assertFalse(s.net_revenue or s.revised_margin_percent)
        self.assertIn('GLOBAL_DISCOUNT_UNALLOCATED',s.line_ids.source_evidence['source_issues'])
        self.assertEqual(s.risk_status,'review_required')

    def test_service_charge_outside_affected_scope_not_full_order(self):
        so,l=self._sales15(100);service=self.env['product.product'].create({'name':'Freight service','type':'service'})
        self.env['sale.order.line'].create(dict(order_id=so.id,product_id=service.id,product_uom_qty=1,price_unit=500,tax_ids=[Command.clear()]))
        s=self._margin();self.assertEqual(D(s.net_revenue),14000);self.assertIn('not whole-order',s.provenance['scope'])

    def test_partial_delivery_changes_exact_remaining_scope_and_stales(self):
        self.red.with_company(self.a).standard_price=100;self._quant(100)
        so,l=self._sales15(100);s=self._margin()
        move=l.move_ids.filtered(lambda m:m.state not in ('done','cancel'))[:1]
        move.quantity=40;move.picked=True;move._action_done()
        self.assertEqual(l.qty_delivered,40)
        with self.assertRaises(UserError):s.batch_id.get_current_profitability(**s.scope)
        f=self._finance();new=self._margin(f)
        self.assertEqual(D(new.line_ids.quantity),60);self.assertEqual(D(new.net_revenue),8400)

    def test_partial_orders_retain_incomplete_lines(self):
        self._sales15(10);so,l=self._sales15(20,confirm=False);pl=self.env['product.pricelist'].create(dict(name='PR15 Missing FX',company_id=self.a.id,currency_id=self.usd.id));so.pricelist_id=pl;so.action_confirm()
        s=self._margin();self.assertEqual(s.line_count,2);self.assertEqual(s.incomplete_line_count,1)
        self.assertEqual(s.state,'verified_partial');self.assertFalse(s.net_revenue or s.revised_gross_profit)
        self.assertEqual(D(s.partial_amounts['net_revenue']),1400)
        self.assertEqual(s.risk_status,'review_required')

    def test_no_eligible_demand_not_normal_company_margin(self):
        s=self._margin();self.assertEqual(s.line_count,0);self.assertEqual(s.state,'no_eligible_demand')
        self.assertFalse(s.revised_margin_percent);self.assertEqual(s.risk_status,'not_evaluated')

    def test_fixed_price_review_current_snapshot_context(self):
        self._sales15(100);c,s=self._inputs14()
        s.line_ids.with_user(self.users['manager']).action_review_price_protection('fixed_price_verified','Customer signed terms #15','Explicit current customer contract')
        s=s.allocation_source_id and c.allocation_id.with_user(self.users['manager']).action_collect_sales_terms()
        f=self._finance(inputs=(c,s));m=self._margin(f)
        self.assertEqual(m.line_ids.price_protection,'fixed_price_verified');self.assertIn('FIXED_CUSTOMER_PRICE',m.risk_ids.mapped('code'))

    def test_discounts_use_native_net_sales_source(self):
        so,l=self._sales15(100,200);l.discount=30;s=self._margin()
        self.assertEqual(D(s.net_revenue),14000);self.assertEqual(D(s.revised_gross_profit),2500)


@tagged('post_install','-at_install')
class TestProfitabilitySnapshots(MarginFixtures,TransactionCase):
    def test_idempotence_and_exact_source_versions(self):
        self._sales15(100);s=self._margin()
        self.assertEqual(self._margin(s.financial_id),s);self.assertEqual(s.batch_id.get_current_profitability(**s.scope),s)
        self.assertEqual(s.version,1);self.assertEqual(s.freshness,'current')
        self.assertEqual(self.env[HEADER].search_count([('batch_id','=',s.batch_id.id)]),1)

    def test_sales_price_change_invalidates_and_preserves_history(self):
        so,l=self._sales15(100);s=self._margin();old=s.revised_gross_profit;l.price_unit=150
        with self.assertRaises(UserError):s.batch_id.get_current_profitability(**s.scope)
        self.assertEqual(s.freshness,'stale');self.assertEqual(s.revised_gross_profit,old)
        f=self._finance();new=self._margin(f);self.assertNotEqual(s,new);self.assertEqual(D(new.net_revenue),15000)

    def test_policy_change_invalidates_only_matching_company(self):
        self._sales15(100);s=self._margin()
        self.financial_b.with_context(active_test=False).read(['id'])
        self._policy15();self.assertEqual(s.freshness,'stale')
        self.assertEqual(s.provenance['risk_policy']['version'],'commercial1')

    def test_supplier_cost_change_invalidates(self):
        self._sales15(100);s=self._margin();self._batch12().row_ids.action_correct('proposed_price_raw','1200','PR15 stale source correction')
        with self.assertRaises(UserError):s.batch_id.get_current_profitability(**s.scope)

    def test_invalid_source_ids_and_cross_batch(self):
        self._sales15(100);f=self._finance()
        for value in (False,0,-1,str(f.id)):
            with self.assertRaises(ValidationError):f.batch_id.action_calculate_profitability(value)

    def test_failed_publication_rolls_back_header_lines_and_reasons(self):
        self._sales15(100);f=self._finance();model=type(self.env[RISK])
        def retained():
            return {name:self.env[name].search([],order='id').read([
                field for field,definition in self.env[name]._fields.items()
                if definition.store and definition.type!='binary' and not definition.related
            ],load=None) for name in (HEADER,LINE,RISK)}
        before=retained()
        with patch.object(model,'_record',side_effect=UserError('Injected PR15 publication failure')):
            with self.assertRaises(UserError):self._margin(f)
        self.assertEqual(retained(),before)
        self.assertFalse(self.env[HEADER].search([('batch_id','=',f.batch_id.id)]))

    def test_immutable_nested_defaults_no_forged_verification(self):
        self._sales15(100);s=self._margin()
        for row in (s,s.line_ids,s.aggregate_ids,s.risk_ids):
            with self.assertRaises(AccessError):row.write({'risk_status':'normal'})
            with self.assertRaises(AccessError):row.unlink()
            with self.assertRaises(AccessError):row.copy()
        with self.assertRaises(AccessError):self.env[HEADER].with_context(default_company_id=self.b.id).create({'name':'Forged','batch_id':s.batch_id.id,'risk_status':'normal'})

    def test_finance_can_calculate_without_intake_write(self):
        self._sales15(100);f=self._finance();s=self._margin(f,actor='finance');self.assertTrue(s.complete)

    def test_invalid_erosion_policy_and_governed_mutation(self):
        for points in (-1,0,float('nan')):
            with self.assertRaises(ValidationError),self.env.cr.savepoint():self._policy15(margin_ids=[Command.create(dict(scope='company',minimum_margin_percent=15,target_margin_percent=25,erosion_enabled=True,erosion_warning_points=points,reason='Invalid dimensional policy'))])
        with self.assertRaises(AccessError):self.financial.margin_ids.with_user(self.users['purchase']).write({'erosion_warning_points':1})

    def test_independent_company_policy_and_unrelated_change(self):
        self._policy15();self._sales15(100);s=self._margin()
        a=self.env['vendor.price.revision.config'].get_company_revision_config(self.a,'2026-10-28')
        b=self.env['vendor.price.revision.config'].get_company_revision_config(self.b,'2026-10-28')
        values=profitability('100','82','82')
        self.assertEqual(assess(values,policy_values(a.margin_ids),RULES,'fully_verified',True)['risk_status'],'warning')
        self.assertEqual(assess(values,policy_values(b.margin_ids),RULES,'fully_verified',True)['risk_status'],'critical')
        draft=b.copy(dict(effective_from='2031-01-01',effective_to='2032-12-31',change_reason='Unrelated company future policy'))
        draft.margin_ids.write({'minimum_margin_percent':10,'target_margin_percent':22,'reason':'Independent company thresholds'})
        draft.action_publish()
        self.assertEqual(s.batch_id.get_current_profitability(**s.scope),s)


@tagged('post_install','-at_install')
class TestProfitabilityQuotations(MarginFixtures,TransactionCase):
    def test_conditional_difference_not_additive(self):
        self._sales15(100);q,l=self._sales15(70,confirm=False);base=self._run(batch=self._batch12());f=self._finance(base);m=self._margin(f)
        a=self._run(batch=self._batch12(),quotes=q.ids);qf=self._finance(a,confirmed=f.id);qm=self._margin(qf,confirmed=m.id)
        self.assertEqual(D(m.revised_gross_profit),2500);self.assertEqual(D(qm.revised_gross_profit),4250)
        self.assertEqual(D(qm.conditional_incremental_profit),1750)
        self.assertEqual({v.demand_type for v in qm.aggregate_ids},{'confirmed','conditional'})
        self.assertFalse(qm.provenance['alternatives_additive']);self.assertEqual(q.state,'draft')
        q.action_confirm()
        with self.assertRaises(UserError):qm.batch_id.get_current_profitability(**qm.scope)

    def test_conditional_requires_exact_current_confirmed_margin(self):
        self._sales15(100);q,l=self._sales15(70,confirm=False);base=self._run(batch=self._batch12());f=self._finance(base)
        a=self._run(batch=self._batch12(),quotes=q.ids);qf=self._finance(a,confirmed=f.id)
        with self.assertRaises(ValidationError):self._margin(qf)

    def test_portfolio_and_standalone_alternatives_are_separate(self):
        self._sales15(100);q1,l1=self._sales15(70,confirm=False);q2,l2=self._sales15(80,confirm=False)
        q1.action_quotation_sent()
        base=self._run(batch=self._batch12());f=self._finance(base);m=self._margin(f)
        a1=self._run(batch=self._batch12(),quotes=q1.ids);f1=self._finance(a1,confirmed=f.id);m1=self._margin(f1,confirmed=m.id)
        a=self._run(batch=self._batch12(),quotes=(q1|q2).ids,reason='Explicit combined PR15 portfolio')
        pf=self._finance(a,confirmed=f.id);pm=self._margin(pf,confirmed=m.id)
        self.assertNotEqual(m1.scenario,'confirmed_baseline');self.assertEqual(D(pm.net_revenue),35000)
        self.assertEqual(D(pm.conditional_incremental_profit),3750)
        self.assertEqual(set(pm.line_ids.sale_line_id.ids),{*m.line_ids.sale_line_id.ids,l1.id,l2.id})
        self.assertEqual(q1.state,'sent');self.assertEqual(q2.state,'draft')
        self.assertFalse(pm.provenance['alternatives_additive'])
        q2.validity_date='2026-10-27'
        with self.assertRaises(ValidationError):pm.batch_id.get_current_profitability(**pm.scope)


@tagged('post_install','-at_install')
class TestProfitabilitySecurity(MarginFixtures,TransactionCase):
    def test_sales_only_no_derived_cost_disclosure_any_model(self):
        self._sales15(100);s=self._margin();u=self.users['sales']
        for row in (s,s.line_ids,s.aggregate_ids,s.risk_ids):
            with self.assertRaises(AccessError):row.with_user(u).read()
            with self.assertRaises(AccessError):row.with_user(u).export_data(['id'])
            with self.assertRaises(AccessError):row.with_user(u)._read_group([],[],['__count'])

    def test_purchase_only_no_customer_permission(self):
        self._sales15(100);s=self._margin();u=self.users['purchase']
        for row in (s,s.line_ids,s.aggregate_ids,s.risk_ids):
            with self.assertRaises(AccessError):row.with_user(u).read()
        with self.assertRaises(AccessError):self._margin(s.financial_id,actor='purchase')

    def test_auditor_read_only_without_calculation(self):
        self._sales15(100);s=self._margin();a=s.with_user(self.users['auditor']);self.assertEqual(a.revised_margin_percent,s.revised_margin_percent)
        with self.assertRaises(AccessError):a.write({'risk_status':'normal'})
        with self.assertRaises(AccessError):self._margin(s.financial_id,actor='auditor')

    def test_other_selected_company_and_portal_public(self):
        self._sales15(100);s=self._margin()
        portal=self.env['res.users'].with_context(no_reset_password=True).create(dict(name='PR15 Portal',login='pr15.portal@example.invalid',company_id=self.a.id,company_ids=[Command.set(self.a.ids)],group_ids=[Command.set(self.env.ref('base.group_portal').ids)]))
        for u in (portal,self.env.ref('base.public_user')):
            for row in (s,s.line_ids,s.aggregate_ids,s.risk_ids):
                with self.assertRaises(AccessError):row.with_user(u).read(['id'])
        with self.assertRaises(AccessError):s.with_user(self.users['manager']).with_context(allowed_company_ids=self.b.ids).read()

    def test_sales_grant_revocation_hides_children_and_getter(self):
        self._sales15(100);s=self._margin();u=self.users['manager'];grant=self.env[SALES_GRANT].search([('company_id','=',self.a.id),('user_id','=',u.id)])
        protected=(s,s.line_ids,s.aggregate_ids,s.risk_ids)
        batch=s.batch_id;scope=s.scope
        grant.write({'active':False,'reason':'PR15 explicit revocation'})
        for row in protected:
            with self.assertRaises(AccessError):row.with_user(u).read()
        with self.assertRaises(AccessError):batch.with_user(u).get_current_profitability(**scope)


@tagged('post_install','-at_install')
class TestProfitabilityWorkload(MarginFixtures,TransactionCase):
    def test_100_affected_lines_measured_after_upstream_preparation(self):
        for i in range(100):self._sales15(10)
        f=self._finance();start=time.perf_counter();s=self._margin(f);seconds=time.perf_counter()-start
        self.assertEqual(len(s.line_ids),100);self.assertEqual(D(s.net_revenue),140000)
        self.assertEqual(D(s.baseline_gross_profit),40000);self.assertEqual(D(s.revised_gross_profit),25000)
        self.assertEqual(D(s.gross_profit_change),-15000)
        _logger.info('PR15_WORKLOAD affected_lines=100 seconds=%.3f revenue140000 baselineprofit40000 revisedprofit25000 change-15000',seconds)
