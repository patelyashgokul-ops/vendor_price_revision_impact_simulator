"""PR18 source-linked pricing, eligibility, options, immutable audit and security."""
import logging,time
from datetime import date
from decimal import Decimal as D,localcontext
from unittest.mock import patch
from odoo import Command,fields
from odoo.exceptions import AccessError,UserError,ValidationError
from odoo.tests import TransactionCase,tagged
from .test_vendor_scenarios import ScenarioFixtures
from .test_commercial_validation import MODULE
from ..models.recommendation import HEADER,LINE,OPTION,REVIEW
from ..models.recommendation_math import target,upward,supplier_ceiling,eligibility
from ..models.profitability_math import profitability
from ..models.reconciliation_controls import independent_profit

_logger=logging.getLogger(__name__)

@tagged('post_install','-at_install')
class TestRecommendationMath(TransactionCase):
    def test_margin_inversion_not_markup(self):
        v=target('115','140','25','.01');self.assertAlmostEqual(float(v['required_raw']),153.3333333333,places=8)
        self.assertNotEqual(D(v['required_raw']),D(115)*D('1.25'))
    def test_reference_gap_and_supplier_ceiling(self):
        v=target('21500','28000','25','.01')
        self.assertEqual(v['required_rounded'],'28666.67');self.assertEqual(v['additional_required'],'666.67')
        self.assertEqual(D(v['max_cost']),21000);self.assertEqual(D(v['cost_reduction']),500)
        self.assertEqual(D(supplier_ceiling(v['max_cost'],'10000','100')),110)
    def test_invalid_targets_missing_cost_and_zero_quantity(self):
        for m in ('100','110','-1','NaN'):
            with self.assertRaises(ValueError):target('115','140',m,'.01')
        self.assertIsNone(target(None,'140','25','.01')['required_raw']);self.assertIsNone(supplier_ceiling('100','10','0'))
    def test_already_met_signed_gap_and_rounding_increment(self):
        v=target('100','140','25','.05');self.assertLess(D(v['signed_gap']),0);self.assertEqual(D(v['additional_required']),0)
        self.assertEqual(upward('143.333333','.01'),D('143.34'));self.assertEqual(upward('143.333333','.05'),D('143.35'))
    def test_revenue_changing_profit_preserves_actual_baseline(self):
        v=profitability('28666.67','21500','21500',baseline_revenue='28000')
        self.assertEqual(D(v['baseline_gross_profit']),6500);self.assertEqual(D(v['revised_gross_profit']),D('7166.67'))
        self.assertEqual(D(v['gross_profit_change']),D('666.67'));self.assertLess(D(v['margin_erosion_points']),0)
        with localcontext() as ctx:
            ctx.prec=38
            self.assertEqual(v,independent_profit('28666.67','21500','21500',baseline_revenue='28000'))
    def test_exact_eligibility_states(self):
        args=('2026-11-01','2026-10-29','review')
        self.assertEqual(eligibility('sale','fixed_price_verified',*args),'protected_not_eligible')
        self.assertEqual(eligibility('sale','price_protection_unknown',*args),'customer_contract_review')
        self.assertTrue(eligibility('sale','price_adjustment_allowed_verified',*args,conditions=True).startswith('eligible_'))
        self.assertTrue(eligibility('draft','price_protection_unknown',*args).startswith('eligible_'))
        self.assertEqual(eligibility('sent','price_protection_unknown',*args),'offer_validity_review')
        self.assertEqual(eligibility('draft','price_protection_unknown','2026-10-28','2026-10-29','review'),'expired_offer_review')
        self.assertEqual(eligibility('cancel','not_applicable',*args),'cancelled_not_eligible')

class RecommendationFixtures(ScenarioFixtures):
    def _prepare18(self,protection='fixed_price_verified',quote=False,sent=False,discount=0,tax=None,stock=60,po_qty=40,qty=200,delivered=0,price=140,**policy):
        self.enterContext(patch.object(fields.Date,'today',return_value=date(2026,10,29)))
        self._policy15(reconciliation_basis_policy='documented_projection',**policy);self._commercial14()
        self.red.with_company(self.a).standard_price=100
        if stock:self._quant(stock)
        if po_qty:
            po,pl=self._po(po_qty,100);self._assess12(self._row12(self._collect12(),pl))
        if quote:self._sales15(100)
        so,sl=self._sales15(qty,price=price,confirm=not quote)
        sl.discount=discount
        if tax:sl.tax_ids=[Command.set(tax.ids)]
        if quote:
            so.validity_date='2026-11-30'
            if sent:so.state='sent'
        if delivered:
            move=sl.move_ids;move.quantity=delivered;move.picked=True;move.picking_id._action_done()
        a=self._run(batch=self._batch12(),quotes=so.ids if quote else None)
        c,s=self._inputs14(a)
        selected=s.line_ids.filtered(lambda l:l.sale_line_id==sl)
        if protection:selected.with_user(self.users['manager']).action_review_price_protection(protection,'Exact documented customer terms','Independent commercial review for PR18')
        s=a.with_user(self.users['manager']).action_collect_sales_terms()
        if quote:
            bc,bs=self._inputs14(a.baseline_id);bf=self._finance(inputs=(bc,bs));bm=self._margin(bf)
            f=self._finance(inputs=(c,s),confirmed=bf.id);m=self._margin(f,confirmed=bm.id)
        else:f=self._finance(inputs=(c,s));m=self._margin(f)
        scenario=self._scenario(self._reconcile(m));scenario.action_calculate_scenario()
        self.native_order,self.native_line=so,sl
        return scenario
    def _tax18(self,amount=18,included=False,kind='percent'):
        return self.env['account.tax'].create(dict(name=f'PR18 {kind} {amount} {included}',company_id=self.a.id,amount=amount,amount_type=kind,type_tax_use='sale',price_include_override='tax_included' if included else 'tax_excluded'))
    def _input18(self,**kw):return dict(sale_line_id=self.native_line.id,reason='Exact documented commercially restricted assumption',**kw)
    def _option18(self,r,kind):return r.option_ids.filtered(lambda v:v.kind==kind)
    def _rebuild18(self,protection=None):
        a=self._run(batch=self._batch12());c,s=self._inputs14(a)
        if protection:
            for line in s.line_ids:line.with_user(self.users['manager']).action_review_price_protection(protection,'Exact customer agreement','Independent review of unchanged customer prices')
            s=a.with_user(self.users['manager']).action_collect_sales_terms()
        f=self._finance(inputs=(c,s));m=self._margin(f);scenario=self._scenario(self._reconcile(m));scenario.action_calculate_scenario()
        return scenario

@tagged('post_install','-at_install')
class TestRecommendationReferences(RecommendationFixtures,TransactionCase):
    def test_reference_fixed200_gap66667_ceiling110(self):
        s=self._prepare18();r=s.action_generate_recommendations()
        self.assertEqual(r.state,'financially_verified');self.assertTrue(r.complete,r.controls)
        self.assertEqual(D(r.required_revenue),D('28666.67'));self.assertEqual(D(r.revenue_gap),D('666.67'));self.assertEqual(D(r.supplier_ceiling),110)
        self.assertEqual(r.line_ids.eligibility,'protected_not_eligible');self.assertEqual(D(r.line_ids.eligible_qty),0);self.assertFalse(r.line_ids.display_price_unit)
        customer=self._option18(r,'customer_eligible_price_review');self.assertEqual(customer.feasibility,'customer_repricing_not_available')
        supplier=self._option18(r,'supplier_unit_ceiling');self.assertEqual(D(supplier.reduced_procurement_cost),500)
        self.assertEqual(D(supplier.values['values']['revised_margin_percent']),25)
        self.assertEqual(D(customer.values['values']['revised_gross_profit']),6500)
        self.assertEqual(self.native_line.price_unit,140)
        _logger.info('PR18_REFERENCE revenue28000 cost21500 profit6500 margin23.21428571 target25 required28666.67 gap666.67 supplier_total21000 unchanged10000 new100 ceiling110 cost_reduction500 fixed200_no_reprice')
    def test_partial_100_of_200_uses_only_eligible_denominator(self):
        s=self._prepare18(protection='price_adjustment_allowed_verified')
        r=s.action_generate_recommendations([self._input18(eligible_qty='100',conditions='Verified remaining100 amendment/notice conditions for review')])
        line=r.line_ids;self.assertEqual(D(line.eligible_qty),100);self.assertEqual(D(line.display_price_unit),D('146.67'))
        self.assertEqual(D(line.values['additional_revenue']),667);self.assertGreaterEqual(D(self._option18(r,'customer_eligible_price_review').values['values']['revised_margin_percent']),25)
        self.assertEqual(self.native_line.price_unit,140)
        _logger.info('PR18_PARTIAL total200 eligible100 native_price146.67 incremental_revenue667 target_reached_no_source_write')
    def test_unknown_contract_no_permission_from_input(self):
        s=self._prepare18(protection=None);r=s.action_generate_recommendations()
        self.assertEqual(r.line_ids.eligibility,'customer_contract_review')
        with self.assertRaises(ValidationError):s.action_generate_recommendations([self._input18(eligible_qty='1',conditions='User text is not a customer right')])
    def test_draft_quote_own_target_not_fixed_book_gap(self):
        s=self._prepare18(quote=True,qty=100,protection=None);r=s.action_generate_recommendations()
        line=r.line_ids.filtered(lambda l:l.sale_line_id==self.native_line)
        self.assertEqual(line.eligibility,'eligible_unsent_quote_review');self.assertEqual(D(line.display_price_unit),D('153.34'))
        self.assertEqual(D(line.values['required_gap']),D('1333.34'))
        self.assertNotEqual(D(line.values['required_gap']),D(r.revenue_gap))
        self.assertEqual(self.native_order.state,'draft')
    def test_sent_valid_offer_review_without_adjustment_permission(self):
        s=self._prepare18(quote=True,sent=True,qty=100,protection=None);r=s.action_generate_recommendations()
        line=r.line_ids.filtered(lambda l:l.sale_line_id==self.native_line)
        self.assertEqual(line.eligibility,'offer_validity_review');self.assertFalse(line.display_price_unit)
    def test_adjustable_sent_offer_requires_recorded_conditions(self):
        s=self._prepare18(quote=True,sent=True,qty=100,protection='price_adjustment_allowed_verified')
        r=s.action_generate_recommendations([self._input18(conditions='Exact verified offer-amendment notice/customer acceptance conditions')])
        self.assertTrue(r.line_ids.filtered(lambda l:l.sale_line_id==self.native_line).eligibility.startswith('eligible_'))
    def test_cap_leaves_gap_and_floor_conflict_not_verified(self):
        s=self._prepare18(protection='price_adjustment_allowed_verified',recommendation_max_uplift_percent='1')
        args=[self._input18(conditions='Verified permitted amendment conditions')]
        r=s.action_generate_recommendations(args);self.assertEqual(D(r.line_ids.display_price_unit),D('141.4'))
        option=self._option18(r,'customer_eligible_price_review');self.assertEqual(option.feasibility,'price_cap_constrained');self.assertGreater(D(option.remaining_target_gap),0)
        bad=s.action_generate_recommendations([self._input18(conditions='Verified conditions',min_net_source_unit='200',max_net_source_unit='145')])
        self.assertFalse(bad.complete);self.assertFalse(bad.line_ids.display_price_unit)
    def test_target_met_supplier_scenario_no_unneeded_uplift(self):
        s=self._prepare18(protection='price_adjustment_allowed_verified');s.action_set_assumptions([self._spec(value='109')],'Hypothetical improved supplier price');s.action_calculate_scenario()
        r=s.action_generate_recommendations([self._input18(conditions='Verified amendment conditions')]);self.assertEqual(D(r.revenue_gap),0)
        self.assertFalse(r.line_ids.display_price_unit);self.assertEqual(D(self._option18(r,'supplier_unit_ceiling').reduced_procurement_cost),0)
    def test_supplier_alternatives_and_combined_recalculate_not_add_benefits(self):
        s=self._prepare18(protection='price_adjustment_allowed_verified');alt=s.action_clone_scenario('Supplier110');alt.action_set_assumptions([self._spec(value='110')],'Supplier discussion target, not accepted');alt.action_calculate_scenario()
        r=s.action_generate_recommendations([self._input18(conditions='Verified amendment conditions')],alternative_ids=alt.ids)
        supplier=self._option18(r,'supplier_scenario_'+str(alt.id));self.assertEqual(D(supplier.values['values']['revised_margin_percent']),25)
        combined=self._option18(r,'combined_customer_and_supplier_'+str(alt.id))
        self.assertEqual(D(combined.values['values']['revised_cost']),21000);self.assertGreater(D(combined.values['values']['revised_margin_percent']),25)
        self.assertFalse(combined.values['approved']);self.assertFalse(combined.values['applied'])
    def test_delivered_quantity_never_eligible(self):
        s=self._prepare18(qty=100,stock=100,po_qty=0,delivered=40,protection='price_adjustment_allowed_verified',price=110)
        r=s.action_generate_recommendations([self._input18(conditions='Verified remaining-only contractual amendment conditions')])
        self.assertEqual(D(r.line_ids.values['outstanding_qty']),60);self.assertEqual(D(r.line_ids.eligible_qty),60);self.assertEqual(D(r.line_ids.values['delivered_qty']),40)
    def test_missing_fifo_cost_no_target_price(self):
        self._policy16();self._commercial14();self.red.categ_id.property_cost_method='fifo';self._quant(60);self._sales15(200)
        s=self._scenario(self._reconcile());s.action_calculate_scenario();r=s.action_generate_recommendations()
        self.assertFalse(r.complete);self.assertFalse(r.required_revenue);self.assertTrue(all(not l.display_price_unit for l in r.line_ids))
    def test_governed_same_order_allocation_respects_different_discounts(self):
        self._prepare18(qty=100,price=110,protection='price_adjustment_allowed_verified',recommendation_recovery_scope='same_order')
        other=self.env['sale.order.line'].create(dict(order_id=self.native_order.id,product_id=self.red.id,product_uom_qty=100,product_uom_id=self.unit.id,price_unit=140,discount=10,tax_ids=[Command.clear()]))
        s=self._rebuild18('price_adjustment_allowed_verified')
        inputs=[dict(sale_line_id=l.id,reason='Explicit same-order scope',conditions='Verified adjustment rights and notice conditions') for l in (self.native_line|other)]
        r=s.action_generate_recommendations(inputs,objective='same_order_targets')
        self.assertEqual(len(r.line_ids),2);self.assertTrue(r.complete,r.controls)
        projected=self._option18(r,'customer_eligible_price_review')
        self.assertGreaterEqual(D(projected.values['values']['revised_margin_percent']),25)
        self.assertAlmostEqual(sum(float(l.values['required_gap']) for l in r.line_ids),float(r.revenue_gap),places=6)
    def test_same_order_scope_cannot_be_unilaterally_enabled(self):
        s=self._prepare18()
        with self.assertRaises(ValidationError):s.action_generate_recommendations(objective='same_order_targets')
    def test_expiration_invalidates_old_quote_recommendation(self):
        s=self._prepare18(quote=True,qty=100,protection=None);r=s.action_generate_recommendations()
        with patch.object(fields.Date,'today',return_value=date(2026,12,1)):
            with self.assertRaises(UserError):r.get_current_recommendation()
    def test_global_discount_unallocated_never_generates_verified_product_price(self):
        self._prepare18();discount=self.env['product.product'].create(dict(name='PR18 global discount',type='service'))
        self.a.sale_discount_product_id=discount
        self.env['sale.order.line'].create(dict(order_id=self.native_order.id,product_id=discount.id,product_uom_qty=1,price_unit=-1000,tax_ids=[Command.clear()]))
        s=self._rebuild18();r=s.action_generate_recommendations()
        self.assertFalse(r.complete);self.assertFalse(r.required_revenue)
        self.assertTrue(all(not l.display_price_unit for l in r.line_ids))

@tagged('post_install','-at_install')
class TestRecommendationTaxDiscount(RecommendationFixtures,TransactionCase):
    def test_ten_percent_discount_native_inverse(self):
        s=self._prepare18(protection='price_adjustment_allowed_verified',stock=0,po_qty=0,qty=100,price=150,discount=10)
        r=s.action_generate_recommendations([self._input18(conditions='Verified conditions')])
        line=r.line_ids;self.assertEqual(D(line.display_price_unit),D('170.38'))
        self.assertGreaterEqual(D(self._option18(r,'customer_eligible_price_review').values['values']['revised_margin_percent']),25)
        self.assertEqual(self.native_line.discount,10)
    def test_price_included_tax_native_roundtrip(self):
        tax=self._tax18(included=True)
        s=self._prepare18(protection='price_adjustment_allowed_verified',stock=0,po_qty=0,qty=100,price=165.2,tax=tax)
        r=s.action_generate_recommendations([self._input18(conditions='Verified conditions')]);p=r.line_ids.values['native_price']
        self.assertEqual(D(p['display_price_unit']),D('180.94'));self.assertGreater(D(p['expected_tax_amount']),0)
        self.assertGreaterEqual(D(self._option18(r,'customer_eligible_price_review').values['values']['revised_margin_percent']),25)
        _logger.info('PR18_TAX_NATIVE included18 candidate180.94 native excluded revenue meets25; discount applied once')
    def test_fixed_and_group_tax_native(self):
        fixed=self._tax18(amount=2,kind='fixed');percent=self._tax18(amount=10)
        group=self.env['account.tax'].create(dict(name='PR18 group',company_id=self.a.id,type_tax_use='sale',amount_type='group',children_tax_ids=[Command.set((fixed|percent).ids)]))
        s=self._prepare18(protection='price_adjustment_allowed_verified',stock=0,po_qty=0,qty=100,price=140,tax=group)
        r=s.action_generate_recommendations([self._input18(conditions='Verified conditions')]);self.assertTrue(r.complete,r.controls)
        self.assertGreater(D(r.line_ids.values['native_price']['expected_tax_amount']),0)
    def test_partial_foreign_discount_native_unchanged_rounding(self):
        from ..models.recommendation_engine import native_tax
        self.enterContext(patch.object(fields.Date,'today',return_value=date(2026,10,29)))
        self._policy15(reconciliation_basis_policy='documented_projection');self._commercial14()
        self.env['res.currency.rate'].create([dict(currency_id=c.id,company_id=self.a.id,name='2026-10-28',rate=v) for c,v in ((self.inr,90),(self.usd,1))])
        pl=self.env['product.pricelist'].create(dict(name='PR18 partial USD',company_id=self.a.id,currency_id=self.usd.id))
        self.native_order,self.native_line=self._sales15(3,price=3.35,confirm=False)
        self.native_order.pricelist_id=pl;self.native_line.discount=10;self.native_order.action_confirm()
        a=self._run(batch=self._batch12());c,_=self._inputs14(a)
        sales=a.with_user(self.users['manager']).action_collect_sales_terms('2026-10-29')
        sales.line_ids.with_user(self.users['manager']).action_review_price_protection('price_adjustment_allowed_verified','Exact partial USD agreement','Independent one-unit amendment evidence')
        sales=a.with_user(self.users['manager']).action_collect_sales_terms('2026-10-29')
        s=self._scenario(self._reconcile(self._margin(self._finance(inputs=(c,sales)))))
        s.action_set_assumptions([self._spec(value='206.62')],'Explicit hypothetical future supplier unit cost');rs=s.action_calculate_scenario()
        self.assertEqual(D(rs.profit['net_revenue']),D('814.5'));self.assertEqual(D(rs.profit['revised_cost']),D('619.86'))
        r=s.action_generate_recommendations([self._input18(eligible_qty='1',conditions='Verified one-of-three quantity amendment conditions')])
        self.assertTrue(r.complete,r.controls);row=r.line_ids;source=sales.line_ids
        unchanged,_=native_tax(source,'3.35',2);eligible,_=native_tax(source,row.display_price_unit,1)
        actual=D(str(self.inr.round((self.usd.round(float(unchanged))+self.usd.round(float(eligible)))*90)))
        actual_margin=(actual-D('619.86'))/actual*100
        self.assertGreaterEqual(actual_margin,25,'Native split-quantity rounding must not miss the target')
        self.assertEqual(D(row.display_price_unit),D('3.51'));self.assertEqual(actual,D('827.1'))
        customer=self._option18(r,'customer_eligible_price_review');self.assertEqual(D(customer.values['values']['net_revenue']),actual)
        self.assertEqual(D(row.values['unchanged_price_evidence']['company_revenue']),D('542.7'))
        self.assertEqual(self.native_line.price_unit,3.35);self.assertEqual(self.native_line.discount,10)
        capped=s.action_generate_recommendations([self._input18(eligible_qty='1',max_net_source_unit='3.15',conditions='Same verified one-unit amendment, restrictive USD net cap')])
        option=self._option18(capped,'customer_eligible_price_review')
        self.assertTrue(capped.complete,capped.controls);self.assertEqual(D(capped.line_ids.display_price_unit),D('3.50'))
        self.assertEqual(option.feasibility,'price_cap_constrained');self.assertEqual(D(option.remaining_target_gap),D('.28'))
        self.assertEqual(D(option.values['values']['net_revenue']),D('826.2'));self.assertLess(D(option.values['values']['revised_margin_percent']),25)
        self.assertEqual(self.native_line.price_unit,3.35);self.assertEqual(self.native_line.discount,10)
        _logger.info('PR18_PARTIAL_FX_ROUNDING originalUSD9.05 company814.5 cost619.86 target826.48 unchangedUSD6.03 company542.7 candidateUSD3.51 native_total827.1 margin_ge25 no_price_write')

    def test_hundred_percent_discount_safe_review(self):
        s=self._prepare18(protection='price_adjustment_allowed_verified',discount=100)
        r=s.action_generate_recommendations([self._input18(conditions='Verified conditions')]);self.assertFalse(r.complete);self.assertFalse(r.line_ids.display_price_unit)
    def test_negative_discount_native_surcharge(self):
        s=self._prepare18(protection='price_adjustment_allowed_verified',stock=0,po_qty=0,qty=100,price=125,discount=-10)
        r=s.action_generate_recommendations([self._input18(conditions='Verified conditions')]);self.assertTrue(r.complete,r.controls)
        self.assertLess(D(r.line_ids.display_price_unit),D('153.34'));self.assertEqual(self.native_line.discount,-10)

    def test_foreign_currency_box_uom_native_inverse(self):
        self.enterContext(patch.object(fields.Date,'today',return_value=date(2026,10,29)))
        self._policy15(reconciliation_basis_policy='documented_projection');self._commercial14()
        self.env['res.currency.rate'].create([dict(currency_id=c.id,company_id=self.a.id,name='2026-10-28',rate=v) for c,v in ((self.inr,90),(self.usd,1))])
        pl=self.env['product.pricelist'].create(dict(name='PR18 USD customer',company_id=self.a.id,currency_id=self.usd.id))
        self.native_order,self.native_line=self._sales15(10,price=15.5,uom=self.box,confirm=False)
        self.native_order.pricelist_id=pl
        self.native_order.action_confirm()
        a=self._run(batch=self._batch12());c,_=self._inputs14(a)
        sales=a.with_user(self.users['manager']).action_collect_sales_terms('2026-10-29')
        sales.line_ids.with_user(self.users['manager']).action_review_price_protection('price_adjustment_allowed_verified','Exact foreign currency box terms','Independent customer amendment evidence')
        sales=a.with_user(self.users['manager']).action_collect_sales_terms('2026-10-29')
        s=self._scenario(self._reconcile(self._margin(self._finance(inputs=(c,sales)))));s.action_calculate_scenario()
        r=s.action_generate_recommendations([self._input18(conditions='Verified USD per box amendment conditions')])
        self.assertTrue(r.complete,r.controls);line=r.line_ids
        self.assertEqual(line.sales_currency_id,self.usd);self.assertEqual(line.sales_uom_id,self.box)
        self.assertEqual(D(line.eligible_qty),100);self.assertEqual(D(line.display_price_unit),D('17.04'))
        self.assertEqual(D(line.values['native_price']['eligible_source_qty']),10)
        self.assertGreaterEqual(D(self._option18(r,'customer_eligible_price_review').values['values']['revised_margin_percent']),25)
        self.assertEqual(self.native_line.price_unit,15.5)
        _logger.info('PR18_FX_UOM USD90 companyINR box10 eligible100units candidateUSD17.04perBox native_forward_margin_ge25 source_unchanged')

@tagged('post_install','-at_install')
class TestRecommendationLifecycle(RecommendationFixtures,TransactionCase):
    def test_idempotency_history_stale_source_and_new_scenario(self):
        s=self._prepare18();r=s.action_generate_recommendations();self.assertEqual(s.action_generate_recommendations(),r);self.assertEqual(r.get_current_recommendation(),r)
        s.action_set_assumptions([self._spec(value='112')],'Explicit independent supplier price assumption')
        with self.assertRaises(UserError):r.get_current_recommendation()
        s.action_calculate_scenario();new=s.action_generate_recommendations();self.assertEqual(new.previous_id,r);self.assertEqual(new.version,2)
        self.assertEqual(D(r.summary['scenario_cost']),21500);self.assertEqual(D(new.summary['scenario_cost']),21200)
    def test_price_change_and_quote_confirmation_stale(self):
        s=self._prepare18(quote=True,qty=70,protection=None);r=s.action_generate_recommendations();self.native_order.action_confirm()
        with self.assertRaises(UserError):r.get_current_recommendation()
        self.assertTrue(r.exists())
    def test_review_immutable_no_management_approval_and_archive_regeneration(self):
        s=self._prepare18();r=s.action_generate_recommendations();option=r.option_ids[:1]
        event=r.action_record_review('preferred_for_review','Preferred analytical option','Commercial evidence reviewed',option.id)
        self.assertEqual(r.action_record_review('preferred_for_review','Preferred analytical option','Commercial evidence reviewed',option.id),event)
        with self.assertRaises(ValidationError):r.action_record_review('approved','Attempted management approval','Not allowed',option.id)
        with self.assertRaises(AccessError):event.write({'reason':'Erase history'})
        r.action_record_review('archived','Retained prior review','Never erase source history')
        with self.assertRaises(UserError):r.get_current_recommendation()
        self.assertEqual(s.action_generate_recommendations().previous_id,r)
    def test_publication_failure_rolls_back_and_retry(self):
        s=self._prepare18();before={n:self.env[n].search_count([]) for n in (HEADER,LINE,OPTION,REVIEW)}
        with patch.object(type(self.env[OPTION]),'_record',side_effect=UserError('Injected PR18 option publication failure')):
            with self.assertRaises(UserError):s.action_generate_recommendations()
        self.assertEqual(before,{n:self.env[n].search_count([]) for n in before});self.assertTrue(s.action_generate_recommendations().line_ids)
    def test_forged_scope_input_and_alternative_rejected(self):
        s=self._prepare18()
        for v in ([dict(sale_line_id=999999,reason='Foreign line')],[self._input18(eligible_qty='201')],[self._input18(allow_reprice=True)]):
            with self.assertRaises((AccessError,ValidationError)):s.action_generate_recommendations(v)
        with self.assertRaises(ValidationError):s.action_generate_recommendations(objective='company_book_recovered_by_unrelated_quotes')
    def test_real_wizard_and_source_drilldown(self):
        s=self._prepare18();w=self.env[HEADER+'.wizard'].with_user(self.users['finance']).create(dict(scenario_id=s.id))
        action=w.action_generate();r=self.env[HEADER].browse(action['res_id']).with_user(self.users['finance'])
        self.assertEqual(r.action_open_source()['res_id'],s.id);self.assertEqual(r.line_ids.action_open_source()['res_id'],self.native_order.id)
    def test_ten_generation_benchmark(self):
        s=self._prepare18();started=time.perf_counter()
        for i in range(10):self.assertTrue(s.action_generate_recommendations().line_ids)
        self.assertEqual(self.env[HEADER].search_count([('scenario_id','=',s.id)]),1)
        _logger.info('PR18_WORKLOAD repeated_generations=10 seconds=%.3f unique_headers=1',time.perf_counter()-started)

@tagged('post_install','-at_install')
class TestRecommendationSecurity(RecommendationFixtures,TransactionCase):
    def test_sales_purchase_public_denied_read_export_and_calculation(self):
        s=self._prepare18();r=s.action_generate_recommendations()
        for user in (self.users['sales'],self.users['purchase'],self.env.ref('base.public_user')):
            for row in (r,r.line_ids,r.option_ids):
                with self.assertRaises(AccessError):row.with_user(user).read(['id'])
                with self.assertRaises(AccessError):row.with_user(user).export_data(['id'])
            with self.assertRaises(AccessError):s.with_user(user).action_generate_recommendations()
    def test_auditor_readonly_direct_orm_forgery_and_company_scope(self):
        s=self._prepare18();r=s.action_generate_recommendations();self.assertTrue(r.with_user(self.users['auditor']).read(['name']))
        for row in (r,r.line_ids,r.option_ids):
            with self.assertRaises(AccessError):row.with_context(skip_security=True).write({'batch_id':s.batch_id.id})
            with self.assertRaises(AccessError):row.unlink()
        with self.assertRaises(AccessError):self.env[HEADER].with_user(self.users['finance']).create({'state':'financially_verified'})
        with self.assertRaises(AccessError):r.with_user(self.users['purchase_b']).read(['name'])
        with self.assertRaises(AccessError):r.with_user(self.users['auditor']).action_record_review('reviewed','No authority','Read-only actor')
    def test_revoked_customer_grant_denies_groups_and_related_values(self):
        s=self._prepare18();r=s.action_generate_recommendations();manager=self.users['manager']
        self.env['vendor.price.revision.sales.grant'].search([('user_id','=',manager.id)]).write({'active':False,'reason':'Explicit source scope revocation'})
        with self.assertRaises(AccessError):r.with_user(manager).read(['summary'])
        self.assertEqual(self.env[HEADER].with_user(manager)._read_group([],[],['__count'])[0][0],0)

@tagged('post_install','-at_install')
class TestRecommendationWorkload(RecommendationFixtures,TransactionCase):
    def test_one_hundred_real_affected_lines(self):
        self._policy15(reconciliation_basis_policy='documented_projection');self._commercial14()
        for i in range(100):self._sales15(1)
        s=self._scenario(self._reconcile());s.action_calculate_scenario();started=time.perf_counter()
        r=s.action_generate_recommendations();elapsed=time.perf_counter()-started
        self.assertEqual(len(r.line_ids),100);self.assertEqual(r.state,'financially_verified')
        self.assertEqual(sum(D(v.eligible_qty) for v in r.line_ids),0)
        self.assertEqual(D(r.summary['scenario_cost']),11500)
        _logger.info('PR18_WORKLOAD lines=100 seconds=%.3f recommendation_lines=%s source_lookups_coherent_no_double_recovery',elapsed,len(r.line_ids))
