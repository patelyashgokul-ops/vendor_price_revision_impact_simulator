"""PR11 native sales/tax/stock fixtures; source mutations are fixture setup only."""
from datetime import date
from decimal import Decimal as D
import logging
import time
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from .test_demand_allocation import AllocationFixtures
from .test_commercial_validation import MODULE
from ..models.sales_exposure import HEADER, LINE, ISSUE, REVIEW, GRANT, SalesEngine

_logger=logging.getLogger(__name__)


class SalesFixtures(AllocationFixtures):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.enterClassContext(patch.object(fields.Date,'today',return_value=date(2026,10,29)))
        for key in ('sales','manager','finance','auditor','director'):
            cls.users[key].write({'group_ids':[Command.link(cls.env.ref('sales_team.group_sale_salesman_all_leads').id)]})
            cls.env[GRANT].create({'company_id':cls.a.id,'user_id':cls.users[key].id,
                'warehouse_ids':[Command.set((cls.wh|cls.wh2|cls.wh3).ids)],'reason':'Explicit PR11 customer price access'})
        cls.users['manager'].write({'group_ids':[Command.link(cls.env.ref(MODULE+'.group_vpr_sales_manager').id)]})
        cls.sales_manager=cls.env['res.users'].with_context(no_reset_password=True).create({
            'name':'PR11 Customer Reviewer','login':'pr11.reviewer@example.invalid','company_id':cls.a.id,'company_ids':[Command.set(cls.a.ids)],
            'group_ids':[Command.set((cls.env.ref(MODULE+'.group_vpr_sales_manager')|cls.env.ref('sales_team.group_sale_salesman_all_leads')).ids)]})
        cls.env[GRANT].create({'company_id':cls.a.id,'user_id':cls.sales_manager.id,'warehouse_ids':[Command.set(cls.wh.ids)],'reason':'Sales-only customer reviewer'})

    def _sales(self,qty=200,price=140,discount=0,confirm=True,pricelist=None,**kw):
        order,line=self._sale(qty,False,**kw)
        if pricelist: order.pricelist_id=pricelist
        line.write({'price_unit':price,'discount':discount})
        if confirm:order.action_confirm()
        return order,line

    def _run(self, **kw):
        return super()._run(**kw).with_user(self.users['manager'])

    def _snapshot(self,allocation=None,**kw):
        return (allocation or self._run()).with_user(self.users['manager']).action_collect_sales_terms(**kw)

    def _line(self,snapshot,line=None):
        rows=snapshot.line_ids.filtered(lambda r:r.sale_line_id==line) if line else snapshot.line_ids
        rows.ensure_one();return rows

    def _tax(self,amount=18,included=False,kind='percent'):
        return self.env['account.tax'].create({'name':'PR11 Tax','company_id':self.a.id,'amount':amount,'amount_type':kind,
            'type_tax_use':'sale','price_include_override':'tax_included' if included else 'tax_excluded'})

    def _deliver(self,line,qty):
        move=line.move_ids;move.quantity=qty;move.picked=True;move.picking_id._action_done()


@tagged('post_install','-at_install')
class TestSalesCommercial(SalesFixtures,TransactionCase):
    def test_reference_a_200_at_140_and_allocation_categories(self):
        self._quant(60);po,pl=self._po(40);so,line=self._sales();batch=self._ready()
        terms=batch.action_propose_supply_terms(self.wh.id,pl.id,'firm','Signed protected purchase price reference A')
        terms.with_user(self.users['manager']).action_verify_terms('Independent fixed supplier commitment check')
        s=self._snapshot(self._run(batch=batch));r=self._line(s)
        self.assertEqual(D(r.net_sales_unit_price),140);self.assertEqual(D(r.outstanding_sales_value),28000)
        by={v['allocation_type']:D(v['value']) for v in r.allocation_values}
        self.assertEqual(by['eligible_free_stock'],8400);self.assertEqual(by['protected_incoming_po'],5600)
        self.assertEqual(by['new_procurement_requirement'],14000);self.assertEqual(sum(by.values()),28000)
        self.assertEqual(r.sale_line_id,line);self.assertEqual(r.customer_id,self.customer);self.assertEqual(r.company_id,self.a)
        _logger.info('PR11_REFERENCE_A value=28000 free=8400 incoming=5600 procurement=14000')

    def test_reference_b_discount_partial_delivery(self):
        so,line=self._sales(discount=10);self._deliver(line,50);r=self._line(self._snapshot())
        self.assertEqual(line.price_subtotal,25200);self.assertEqual(D(r.net_sales_unit_price),126)
        self.assertEqual((D(r.delivered_qty),D(r.outstanding_qty),D(r.outstanding_sales_value)),(50,150,18900))
        _logger.info('PR11_REFERENCE_B full=25200 net=126 outstanding=150 value=18900')

    def test_reference_c_actual_price_not_current_pricelist(self):
        so,line=self._sales(100)
        self.env['product.pricelist.item'].create({'pricelist_id':self.pricelist.id,'applied_on':'0_product_variant','product_id':self.red.id,'fixed_price':160})
        r=self._line(self._snapshot());self.assertEqual(D(r.source_unit_price),140);self.assertEqual(D(r.outstanding_sales_value),14000)
        self.assertEqual(line.price_unit,140);_logger.info('PR11_REFERENCE_C current_pricelist=160 actual=140 value=14000')

    def test_cancelled_and_fully_delivered_excluded(self):
        so,line=self._sales();so.action_cancel();other,l=self._sales(20);self._deliver(l,20)
        self.assertFalse(self._snapshot().line_ids)

    def test_duplicate_product_lines_keep_individual_price(self):
        so,l1=self._sales(40);l2=self.env['sale.order.line'].create({'order_id':so.id,'product_id':self.red.id,'product_uom_qty':20,'price_unit':135,'tax_ids':[Command.clear()]})
        s=self._snapshot();self.assertEqual(len(s.line_ids),2)
        self.assertEqual(D(self._line(s,l1).outstanding_sales_value),5600);self.assertEqual(D(self._line(s,l2).outstanding_sales_value),2700)

    def test_variant_and_different_customer_prices_remain_exact(self):
        so,l=self._sales(10);other,l2=self._sales(10,155);other.partner_id=self.vendor
        self._sales(10,999,product=self.white);s=self._snapshot()
        self.assertEqual(set(s.line_ids.product_id.ids),{self.red.id});self.assertEqual(len(s.line_ids),2)
        self.assertEqual(D(self._line(s,l2).net_sales_unit_price),155);self.assertEqual(self._line(s,l2).customer_id,self.vendor)

    def test_invoice_quantity_is_context_not_delivery(self):
        so,line=self._sales(100)
        a=self._run()
        income=self.env['account.account'].create({'name':'PR11 Income','code':'PR11INC','account_type':'income','company_ids':[Command.set(self.a.ids)]})
        journal=self.env['account.journal'].create({'name':'PR11 Sales','code':'P11S','type':'sale','company_id':self.a.id,'default_account_id':income.id})
        invoice=self.env['account.move'].create({'move_type':'out_invoice','partner_id':self.customer.id,'company_id':self.a.id,'journal_id':journal.id,
            'invoice_line_ids':[Command.create({'product_id':self.red.id,'quantity':100,'price_unit':140,'account_id':income.id,'sale_line_ids':[Command.set(line.ids)],'tax_ids':[Command.clear()]})]})
        self.assertTrue(invoice.invoice_line_ids);self.assertEqual(line.qty_invoiced,100);self.assertEqual(line.qty_delivered,0)
        r=self._line(self._snapshot(a));self.assertEqual(D(r.outstanding_qty),100);self.assertEqual(D(r.outstanding_sales_value),14000)

    def test_box_price_normalizes_inverse_to_quantity(self):
        self._sales(20,1400,uom=self.box);r=self._line(self._snapshot())
        self.assertEqual(r.source_uom_id,self.box);self.assertEqual(r.comparison_uom_id,self.unit)
        self.assertEqual(D(r.net_sales_unit_price),140);self.assertEqual(D(r.outstanding_sales_value),28000)

    def test_sales_specific_uom_not_in_supplier_context_is_supported(self):
        pack=self.env['uom.uom'].create({'name':'PR11 Sales Pack7','relative_uom_id':self.unit.id,'relative_factor':7})
        self._sales(10,980,uom=pack);r=self._line(self._snapshot())
        self.assertEqual(D(r.outstanding_qty),70);self.assertEqual(D(r.net_sales_unit_price),140)
        self.assertEqual(D(r.outstanding_sales_value),9800)

    def test_customer_return_requires_review_without_fabricated_sale_value(self):
        so,line=self._sales(100);self._deliver(line,100);original=line.move_ids.filtered(lambda m:m.state=='done')
        ret=self.env['stock.move'].create({'product_id':self.red.id,'uom_id':self.unit.id,'product_uom_qty':20,'quantity':20,
            'picked':True,'company_id':self.a.id,'location_id':self.env.ref('stock.stock_location_customers').id,
            'location_dest_id':self.wh.lot_stock_id.id,'sale_line_id':line.id,'origin_returned_move_id':original.id,'to_refund':True})
        ret._action_confirm();ret._action_done();r=self._line(self._snapshot())
        self.assertEqual(r.valuation_status,'incomplete');self.assertFalse(r.outstanding_sales_value)

    def test_explicit_zero_not_replaced_by_list_price(self):
        self._sales(10,0);r=self._line(self._snapshot())
        self.assertEqual(D(r.source_unit_price),0);self.assertEqual(D(r.outstanding_sales_value),0)
        self.assertIn('ZERO_PRICE_REVIEW',r.issue_codes)

    def test_reserved_backed_value_once(self):
        self._quant(100);so,line=self._sales(100);self._reservation(line,20)
        r=self._line(self._snapshot());self.assertEqual(sum(D(v['quantity']) for v in r.allocation_values),100)
        self.assertEqual(sum(D(v['value']) for v in r.allocation_values),14000)

    def test_unresolved_supply_is_a_separate_quantity_linked_selling_value(self):
        self._quant(80,20);self._sales();self._po(40);r=self._line(self._snapshot())
        values=[v for v in r.allocation_values if v['allocation_type']=='unresolved']
        self.assertEqual(len(values),1);self.assertEqual(D(values[0]['quantity']),20)
        self.assertEqual(D(values[0]['value']),2800);self.assertEqual(D(r.outstanding_sales_value),28000)
        self.assertEqual(sum(D(v['value']) for v in r.allocation_values),28000)

    def test_unverified_incoming_not_promoted_to_protected(self):
        self._sales(40);self._po(40);r=self._line(self._snapshot())
        self.assertEqual(r.allocation_values[0]['allocation_type'],'incoming_cost_unverified')
        self.assertEqual(D(r.allocation_values[0]['value']),5600)

    def test_unresolved_delivery_does_not_fabricate_value(self):
        so,line=self._sales(100);line.move_ids.unlink();r=self._line(self._snapshot())
        self.assertEqual(r.valuation_status,'incomplete');self.assertFalse(r.outstanding_sales_value)

    def test_rounding_residual_is_explicit_not_arbitrary_income(self):
        self._quant(1);self._sales(3,.335);r=self._line(self._snapshot())
        self.assertEqual(D(r.outstanding_sales_value),D('1.01'))
        self.assertEqual(sum(D(v['unrounded_value']) for v in r.allocation_values),D('1.005'))
        self.assertEqual(sum(D(v['value']) for v in r.allocation_values)+D(r.source_terms['rounding_residual']),D('1.01'))


@tagged('post_install','-at_install')
class TestSalesDiscountTax(SalesFixtures,TransactionCase):
    def test_negative_discount_matches_native_surcharge(self):
        so,line=self._sales(10,100,-10);r=self._line(self._snapshot())
        self.assertEqual(line.price_subtotal,1100);self.assertEqual(D(r.net_sales_unit_price),110);self.assertEqual(D(r.outstanding_sales_value),1100)

    def test_tax_excluded_18_percent_not_revenue(self):
        so,line=self._sales();line.tax_ids=self._tax();r=self._line(self._snapshot())
        self.assertEqual(D(r.net_sales_unit_price),140);self.assertEqual(D(r.outstanding_sales_value),28000)
        self.assertGreater(line.price_total,float(r.outstanding_sales_value))

    def test_price_included_tax_118_is_net_100(self):
        so,line=self._sales(100,118);line.tax_ids=self._tax(included=True);r=self._line(self._snapshot())
        self.assertEqual(D(r.net_sales_unit_price),100);self.assertEqual(D(r.outstanding_sales_value),10000)

    def test_included_tax_and_discount_are_not_subtracted_twice(self):
        so,line=self._sales(100,118,10);line.tax_ids=self._tax(included=True);r=self._line(self._snapshot())
        self.assertAlmostEqual(float(r.net_sales_unit_price),90);self.assertEqual(D(r.outstanding_sales_value),9000)

    def test_fixed_tax_native_basis(self):
        so,line=self._sales(10,105);line.tax_ids=self._tax(5,True,'fixed');r=self._line(self._snapshot())
        self.assertEqual(D(r.net_sales_unit_price),100);self.assertEqual(D(r.outstanding_sales_value),1000)

    def test_reference_e_unallocated_global_discount_retains_order_only(self):
        so,line=self._sales(100,100);other=self.env['product.product'].create({'name':'Other service','type':'service'})
        self.env['sale.order.line'].create({'order_id':so.id,'product_id':other.id,'product_uom_qty':1,'price_unit':5000,'tax_ids':[Command.clear()]})
        discount=self.env['product.product'].create({'name':'Global discount','type':'service'})
        self.a.sale_discount_product_id=discount
        dl=self.env['sale.order.line'].create({'order_id':so.id,'product_id':discount.id,'product_uom_qty':1,'price_unit':-1000,'tax_ids':[Command.clear()]})
        s=self._snapshot();r=self._line(s)
        self.assertEqual(s.order_context[0]['full_order_tax_excluded'],'14000.0')
        self.assertEqual(s.order_context[0]['adjustment_lines'][0]['id'],dl.id)
        self.assertIn('GLOBAL_DISCOUNT_UNALLOCATED',r.issue_codes);self.assertFalse(r.outstanding_sales_value)
        self.assertEqual(len(s.line_ids),1);self.assertNotIn(dl.id,s.line_ids.sale_line_id.ids)
        total=s.totals[str(self.inr.id)+':confirmed'];self.assertIsNone(total['value']);self.assertEqual(total['incomplete_lines'],1);self.assertFalse(total['complete'])
        _logger.info('PR11_REFERENCE_E products=15000 discount=-1000 order=14000 product_attribution=incomplete')

    def test_shipping_service_not_treated_as_product_revenue(self):
        so,line=self._sales(10);shipping=self.env['product.product'].create({'name':'Shipping','type':'service'})
        self.env['sale.order.line'].create({'order_id':so.id,'product_id':shipping.id,'product_uom_qty':1,'price_unit':200,'tax_ids':[Command.clear()]})
        r=self._line(self._snapshot());self.assertEqual(D(r.outstanding_sales_value),1400)

    def test_discount_above_100_is_incomplete(self):
        so,line=self._sales(10,100,110);r=self._line(self._snapshot());self.assertEqual(r.valuation_status,'incomplete')

    def test_tax_definition_change_invalidates_snapshot(self):
        so,line=self._sales(10,118);tax=self._tax(included=True);line.tax_ids=tax;s=self._snapshot()
        self.assertEqual(s.line_ids.source_terms['tax_evidence'][0]['amount'],18)
        self.assertEqual(s.line_ids.source_terms['rounding_policy']['source_currency_rounding'],'0.01')
        tax.amount=20
        with self.assertRaises(UserError):s.action_check_current()
        self.assertEqual(s.line_ids.source_terms['tax_evidence'][0]['amount'],18)


@tagged('post_install','-at_install')
class TestSalesQuotations(SalesFixtures,TransactionCase):
    def test_rolling_native_quote_eta_does_not_stale_explicit_commitment(self):
        q,l=self._sales(70,150,confirm=False)
        with patch.object(fields.Datetime,'now',return_value=fields.Datetime.to_datetime('2026-10-29 08:00:00')):
            q.invalidate_recordset(['expected_date']);first=q.expected_date
            a=self._run(quotes=q.ids);s=self._snapshot(a)
        with patch.object(fields.Datetime,'now',return_value=fields.Datetime.to_datetime('2026-10-29 09:00:00')):
            q.invalidate_recordset(['expected_date']);self.assertNotEqual(q.expected_date,first)
            self.assertEqual(a.get_current_sales_terms(),s)
            self.assertEqual(self._snapshot(a),s)

    def test_missing_quote_commitment_is_review_not_rolling_now_deadline(self):
        q,l=self._sales(70,150,confirm=False,date=None);a=self._run(quotes=q.ids)
        self.assertIn('DEMAND_DATE_UNKNOWN',a.demand_ids.issues)
        self.assertFalse(a.demand_ids.required_date)
        r=self._line(self._snapshot(a));self.assertEqual(r.valuation_status,'incomplete')
        self.assertFalse(r.outstanding_sales_value)

    def test_reference_d_confirmed_and_conditional_separate(self):
        self._sales();q,l=self._sales(70,150,confirm=False);a=self._run(quotes=q.ids);s=self._snapshot(a)
        self.assertEqual(D(s.totals[str(self.inr.id)+':confirmed']['value']),28000)
        self.assertEqual(D(s.totals[str(self.inr.id)+':conditional']['value']),10500)
        self.assertEqual(s.scenario,'single_quotation');self.assertEqual(self._line(s,l).demand_type,'conditional')
        _logger.info('PR11_REFERENCE_D confirmed=28000 conditional=10500 selected_what_if=38500 not_confirmed')

    def test_sent_valid_offer_requires_review(self):
        q,l=self._sales(10,confirm=False);q.write({'state':'sent','validity_date':'2026-11-10'})
        r=self._line(self._snapshot(self._run(quotes=q.ids)))
        self.assertEqual(r.price_protection,'offer_validity_review');self.assertEqual(r.opportunity_status,'sent_valid_offer_review')

    def test_expired_quotation_remains_review_not_current_offer(self):
        q,l=self._sales(10,confirm=False);q.write({'state':'sent','validity_date':'2026-11-10'})
        historical_allocation=self._run(quotes=q.ids);historical=self._snapshot(historical_allocation)
        q.validity_date='2026-10-20'
        with self.assertRaises(UserError):historical.action_check_current()
        with self.assertRaises(UserError):historical_allocation.batch_id.action_run_allocation(self.wh.ids,quotation_ids=q.ids)
        self.assertEqual(historical.line_ids.opportunity_status,'sent_valid_offer_review')

    def test_quote_confirmation_invalidates_allocation_and_sales(self):
        q,l=self._sales(10,confirm=False);a=self._run(quotes=q.ids);s=self._snapshot(a);q.action_confirm()
        with self.assertRaises(UserError):s.action_check_current()
        new=self._snapshot(self._run(batch=a.batch_id));self.assertEqual(new.line_ids.demand_type,'confirmed');self.assertEqual(len(new.line_ids),1)

    def test_quotation_portfolio_and_alternatives_separate(self):
        self._sales();q1,l1=self._sales(70,150,confirm=False);q2,l2=self._sales(80,150,confirm=False)
        b=self._ready();a=self._run(batch=b,quotes=q1.ids);s1=self._snapshot(a)
        a2=b.action_run_allocation(self.wh.ids,True,None,None,q2.ids);s2=self._snapshot(a2)
        portfolio=b.action_run_allocation(self.wh.ids,True,None,None,(q1|q2).ids,'Explicit combined customer portfolio')
        sp=self._snapshot(portfolio)
        self.assertEqual(s1.conditional_line_count,1);self.assertEqual(s2.conditional_line_count,1);self.assertEqual(sp.conditional_line_count,2)
        self.assertEqual(D(sp.totals[str(self.inr.id)+':conditional']['value']),22500)
        self.assertNotEqual(s1.allocation_source_id,s2.allocation_source_id)

    def test_expiration_passage_without_source_write_is_stale(self):
        q,l=self._sales(10,confirm=False);q.write({'state':'sent','validity_date':'2026-10-30'});s=self._snapshot(self._run(quotes=q.ids))
        with patch.object(fields.Date,'today',return_value=date(2026,10,31)),self.assertRaises(UserError):s.action_check_current()


@tagged('post_install','-at_install')
class TestSalesCurrency(SalesFixtures,TransactionCase):
    def test_fx_rate_amendment_stales_sales_conversion(self):
        self.env['res.currency.rate'].create([{'currency_id':c.id,'company_id':self.a.id,'name':'2026-10-28','rate':r} for c,r in ((self.inr,90),(self.eur,1))])
        pl=self.env['product.pricelist'].create({'name':'PR11 EUR','company_id':self.a.id,'currency_id':self.eur.id})
        self._sales(100,20,pricelist=pl);a=self._run();s=self._snapshot(a,fx_date='2026-10-29')
        self.assertEqual(D(s.line_ids.company_sales_value),180000)
        self.env['res.currency.rate'].search([('company_id','=',self.a.id),('currency_id','=',self.eur.id),('name','=','2026-10-28')]).rate=2
        with self.assertRaises(UserError):s.action_check_current()

    def test_explicit_sales_fx_direction_and_provenance(self):
        self.env['res.currency.rate'].create([{'currency_id':c.id,'company_id':self.a.id,'name':'2026-10-28','rate':r} for c,r in ((self.inr,90),(self.usd,1))])
        pl=self.env['product.pricelist'].create({'name':'PR11 USD','company_id':self.a.id,'currency_id':self.usd.id})
        so,line=self._sales(100,20,pricelist=pl)
        r=self._line(self._snapshot(fx_date='2026-10-29'))
        self.assertEqual(r.sales_currency_id,self.usd);self.assertEqual(D(r.outstanding_sales_value),2000)
        self.assertEqual(D(r.company_sales_value),180000);self.assertEqual(D(r.fx_evidence['rate']),90)
        self.assertEqual(r.fx_evidence['requested_date'],'2026-10-29');self.assertEqual(len(r.fx_evidence['rate_records']),2)

    def test_foreign_sales_without_explicit_date_retains_source_not_one_to_one(self):
        pl=self.env['product.pricelist'].create({'name':'PR11 USD','company_id':self.a.id,'currency_id':self.usd.id})
        so,line=self._sales(100,20,pricelist=pl);r=self._line(self._snapshot())
        self.assertEqual(D(r.outstanding_sales_value),2000);self.assertFalse(r.company_sales_value);self.assertIsNone(r.fx_evidence['rate'])

    def test_missing_historical_rate_does_not_fallback(self):
        pl=self.env['product.pricelist'].create({'name':'PR11 EUR','company_id':self.a.id,'currency_id':self.eur.id})
        so,line=self._sales(100,20,pricelist=pl);r=self._line(self._snapshot(fx_date='1900-01-01'))
        self.assertFalse(r.company_sales_value);self.assertIn('SALES_FX_RATE_MISSING',r.issue_codes)

    def test_mixed_currencies_grouped(self):
        self._sales(10);pl=self.env['product.pricelist'].create({'name':'PR11 USD','company_id':self.a.id,'currency_id':self.usd.id})
        so,line=self._sales(10,20,pricelist=pl);s=self._snapshot()
        self.assertEqual(len(s.totals),2);self.assertEqual(D(s.totals[str(self.usd.id)+':confirmed']['value']),200)


@tagged('post_install','-at_install')
class TestSalesProtection(SalesFixtures,TransactionCase):
    def _review(self,line,status='fixed_price_verified',**kw):
        return line.with_user(self.sales_manager).action_review_price_protection(status,'Customer PO / signed agreement #11','Documented review',**kw)

    def test_confirmation_alone_not_verified_fixed_price(self):
        self._sales();r=self._line(self._snapshot());self.assertEqual(r.price_protection,'contract_review_required');self.assertFalse(r.protection_evidence)

    def test_cancelled_source_batch_cannot_receive_new_protection_review(self):
        self._sales();a=self._run();r=self._line(self._snapshot(a))
        with self.assertRaises(UserError):a.batch_id.action_cancel()
        # Existing intake forbids discarding extracted evidence. Establish a
        # retained retired-state fixture directly to test the PR11 guard too.
        a.batch_id.sudo()._set({'state':'cancelled'})
        with self.assertRaises(UserError):self._review(r)
        self.assertFalse(self.env[REVIEW].search([('line_id','=',r.id)]))

    def test_authorized_sales_only_review_fixed_and_adjustment_preserves_history(self):
        self._sales();a=self._run();s=self._snapshot(a);r=self._line(s)
        first=self._review(r);s2=self._snapshot(a);self.assertEqual(s2.line_ids.price_protection,'fixed_price_verified')
        second=self._review(s2.line_ids,'price_adjustment_allowed_verified');s3=self._snapshot(a)
        self.assertEqual(s3.line_ids.price_protection,'price_adjustment_allowed_verified');self.assertEqual(len(self.env[REVIEW].search([('sale_line_id','=',r.sale_line_id.id)])),2)
        self.assertEqual(s.line_ids.price_protection,'contract_review_required');self.assertEqual(first.classification,'fixed_price_verified')
        self.assertEqual(s3.line_ids.protection_evidence['review_id'],second.id)

    def test_expired_agreement_requires_review(self):
        self._sales();a=self._run();r=self._line(self._snapshot(a));self._review(r,effective_end='2026-10-01')
        r2=self._line(self._snapshot(a));self.assertEqual(r2.price_protection,'contract_review_required');self.assertIn('PRICE_AMENDMENT_UNVERIFIED',r2.issue_codes)

    def test_evidence_reason_and_effective_interval_required(self):
        self._sales();r=self._line(self._snapshot()).with_user(self.sales_manager)
        for args in [('fixed_price_verified','','reason'),('bad','ref','reason'),('fixed_price_verified','ref','')]:
            with self.assertRaises(ValidationError):r.action_review_price_protection(*args)
        with self.assertRaises(ValidationError):self._review(r,effective_start='2027-01-01',effective_end='2026-01-01')

    def test_changed_price_invalidates_assessment_and_historical_value_retained(self):
        so,line=self._sales();a=self._run();r=self._line(self._snapshot(a));self._review(r)
        old=self._snapshot(a);line.price_unit=145
        with self.assertRaises(UserError):self._review(old.line_ids)
        new=self._snapshot(a);self.assertEqual(new.line_ids.price_protection,'contract_review_required');self.assertEqual(D(old.line_ids.source_unit_price),140)

    def test_auditor_and_sales_user_cannot_review(self):
        self._sales();r=self._line(self._snapshot())
        for user in (self.users['sales'],self.users['auditor']):
            with self.assertRaises(AccessError):r.with_user(user).action_review_price_protection('fixed_price_verified','ref','reason')


@tagged('post_install','-at_install')
class TestSalesSnapshots(SalesFixtures,TransactionCase):
    def test_idempotent_no_duplicate_snapshot_or_issues(self):
        self._sales();a=self._run();s=self._snapshot(a);again=self._snapshot(a)
        self.assertEqual(s,again);self.assertEqual(a.get_current_sales_terms(),s);self.assertEqual(len(self.env[HEADER].search([('allocation_source_id','=',a.id)])),1)

    def test_price_discount_stale_new_version_and_history(self):
        so,line=self._sales();a=self._run();s=self._snapshot(a);line.discount=10
        with self.assertRaises(UserError):s.action_check_current()
        new=self._snapshot(a);self.assertEqual(new.previous_id,s);self.assertEqual(new.version,2)
        self.assertEqual(D(s.line_ids.outstanding_sales_value),28000);self.assertEqual(D(new.line_ids.outstanding_sales_value),25200)

    def test_notes_do_not_invalidate_material_inputs(self):
        so,line=self._sales();a=self._run();s=self._snapshot(a);so.note='Unrelated packing note';self.assertEqual(a.get_current_sales_terms(),s)

    def test_delivery_and_allocation_source_changes_stale(self):
        so,line=self._sales();s=self._snapshot();self._deliver(line,50)
        with self.assertRaises(UserError):s.action_check_current()

    def test_atomic_interrupted_child_creation_rolls_back_header(self):
        self._sales();a=self._run();count=self.env[HEADER].search_count([])
        with patch.object(type(self.env[LINE]),'_record',side_effect=UserError('Injected interrupted publication')),self.assertRaises(UserError):self._snapshot(a)
        self.assertEqual(self.env[HEADER].search_count([]),count)

    def test_no_operational_side_effects(self):
        self._quant(50);self._po(40);so,line=self._sales();a=self._run()
        models=['sale.order','sale.order.line','product.pricelist','product.pricelist.item','purchase.order','purchase.order.line',
            'product.supplierinfo','stock.quant','stock.move','stock.move.line','account.move','account.move.line','res.currency.rate','mail.mail','ir.cron']
        def capture():
            self.env.flush_all()
            return {name:self.env[name].search([]).read([n for n,f in self.env[name]._fields.items() if f.store and f.type not in ('one2many','many2many','binary')],load=None) for name in models}
        before=capture();s=self._snapshot(a);self._snapshot(a);a.get_current_sales_terms();self._review_for_safety(s.line_ids)
        self.assertEqual(before,capture());self.assertFalse(any('margin' in n or 'profit' in n for n in self.env[LINE]._fields))

    def _review_for_safety(self,line):
        line.with_user(self.sales_manager).action_review_price_protection('fixed_price_verified','Test source agreement','Read-only commercial assessment')


@tagged('post_install','-at_install')
class TestSalesSecurity(SalesFixtures,TransactionCase):
    def test_review_wizard_is_not_an_alternate_native_cost_projection(self):
        self._sales();s=self._snapshot();r=s.line_ids
        self.sales_manager.group_ids=[Command.link(self.env.ref('base.group_allow_export').id)]
        model=self.env['vendor.price.revision.sales.review.wizard'].with_user(self.sales_manager)
        w=model.create({'line_id':r.id,'classification':'fixed_price_verified','evidence_reference':'Customer agreement #11','reason':'Documented review'})
        self.assertEqual(w.web_read({'line_id':{'fields':{'display_name':{}}}})[0]['line_id']['id'],r.id)
        with self.assertRaises(AccessError):w.export_data(['line_id/product_id/standard_price'])
        with self.assertRaises(AccessError):model.search([('line_id.product_id.standard_price','>',0)])
        with self.assertRaises(AccessError):w.web_read({'line_id':{'fields':{'product_id':{'fields':{'standard_price':{}}}}}})
        with self.assertRaises(AccessError):model.web_read_group([],['line_id'],groupby_read_specification={'line_id':{'product_id':{'fields':{'standard_price':{}}}}})
        with self.assertRaises(AccessError):model.search_panel_select_multi_range('line_id',group_by='price_unit')

    def test_nested_cost_exports_web_reads_domains_and_group_metadata_blocked(self):
        self._sales();s=self._snapshot();u=self.users['sales'];u.group_ids=[Command.link(self.env.ref('base.group_allow_export').id)]
        row=s.line_ids.with_user(u);model=self.env[LINE].with_user(u)
        for path in ('product_id/standard_price','product_id/seller_ids/price','sale_order_id/order_line/product_id/standard_price'):
            with self.subTest(path=path),self.assertRaises(AccessError):row.export_data([path])
        with self.assertRaises(AccessError):row.web_read({'product_id':{'fields':{'standard_price':{}}}})
        with self.assertRaises(AccessError):model.search([('product_id.standard_price','>',0)])
        with self.assertRaises(AccessError):model.search([('product_id','any',[('seller_ids','any',[('price','>',0)])])])
        with self.assertRaises(AccessError):model.search([],order='product_id.standard_price')
        with self.assertRaises(AccessError):model.web_read_group([],['product_id'],groupby_read_specification={'product_id':{'standard_price':{}}})
        with self.assertRaises(AccessError):model._read_group([],[],['product_id.standard_price:sum'])
        with self.assertRaises(AccessError):model.search_panel_select_multi_range('product_id',group_by='standard_price')
        with self.assertRaises(AccessError):model.search_panel_select_range('product_id',comodel_domain=[('standard_price','>',0)])
        with self.assertRaises(AccessError):s.with_user(u).web_read({'line_ids':{'fields':{'product_id':{'fields':{'standard_price':{}}}}}})

    def test_safe_source_labels_and_customer_projection_exports_remain_available(self):
        self._sales();s=self._snapshot();u=self.users['sales'];u.group_ids=[Command.link(self.env.ref('base.group_allow_export').id)]
        row=s.line_ids.with_user(u)
        values=row.web_read({'product_id':{'fields':{'display_name':{}}},'outstanding_sales_value':{}})
        self.assertEqual(values[0]['product_id']['id'],self.red.id);self.assertEqual(D(values[0]['outstanding_sales_value']),28000)
        self.assertEqual(row.export_data(['source_unit_price'])['datas'][0][0],'140.0')
        self.assertTrue(self.env[LINE].with_user(u).search([('product_id.name','ilike','LED')]))

    def test_genuine_other_company_customer_reader_cannot_read_export_or_review(self):
        self._sales();s=self._snapshot();u=self.users['purchase_b']
        u.write({'group_ids':[Command.link(self.env.ref(MODULE+'.group_vpr_sales_manager').id),Command.link(self.env.ref('sales_team.group_sale_salesman_all_leads').id)]})
        self.env[GRANT].create({'company_id':self.b.id,'user_id':u.id,'warehouse_ids':[Command.set(self.wh_b.ids)],'reason':'Isolated other company customer scope'})
        model=self.env[LINE].with_user(u).with_context(allowed_company_ids=self.b.ids)
        self.assertFalse(model.search([]));self.assertEqual(model._read_group([],[],['__count'])[0][0],0)
        row=s.line_ids.with_user(u).with_context(allowed_company_ids=self.b.ids)
        with self.assertRaises(AccessError):row.read()
        with self.assertRaises(AccessError):row.export_data(['source_unit_price'])
        with self.assertRaises(AccessError):row.action_review_price_protection('fixed_price_verified','ref','reason')

    def test_native_own_order_scope_does_not_disclose_combined_snapshot(self):
        so,l=self._sales(10);other,l2=self._sales(10);u=self.users['sales']
        so.user_id=u;other.user_id=self.sales_manager;s=self._snapshot()
        u.group_ids=[Command.set((self.env.ref(MODULE+'.group_vpr_sales_user')|self.env.ref('sales_team.group_sale_salesman')).ids)]
        self.env['res.users'].invalidate_model(['vpr_sales_order_ids'])
        self.assertEqual(so.with_user(u).name,so.name)
        with self.assertRaises(AccessError):s.line_ids.with_user(u).read()

    def test_customer_grant_cannot_be_forged_by_sales_role(self):
        self._sales();s=self._snapshot();u=self.users['sales']
        with self.assertRaises(AccessError):self.env[GRANT].with_user(u).create({'company_id':self.a.id,'user_id':u.id,'warehouse_ids':[Command.set(self.wh.ids)],'reason':'Forged'})
        with self.assertRaises(AccessError):u.with_user(u).write({'vpr_sales_warehouse_ids':[Command.set(self.wh.ids)]})
        with self.assertRaises(AccessError):u.with_user(u).write({'vpr_sales_order_ids':[Command.set(s.order_ids.ids)]})

    def test_sales_only_read_projection_no_supplier_or_allocation_access(self):
        self._sales();a=self._run();s=self._snapshot(a);user=self.users['sales']
        self.assertEqual(s.with_user(user).read(['name'])[0]['name'],s.name)
        self.assertEqual(s.line_ids.with_user(user).read(['source_unit_price'])[0]['source_unit_price'],'140.0')
        for source in (a,a.batch_id,a.supply_snapshot_id,a.batch_id.revision_id):
            with self.assertRaises(AccessError):source.with_user(user).read()
        self.assertNotIn('provenance',self.env[HEADER]._fields);self.assertNotIn('supply_bucket_id',self.env[LINE]._fields)

    def test_purchase_user_without_customer_grant_or_role_cannot_read(self):
        self._sales();s=self._snapshot()
        for role in ('purchase','other','portal','employee','configuration','pricing','purchase_b'):
            with self.subTest(role=role),self.assertRaises(AccessError):s.line_ids.with_user(self.users[role]).read(['source_unit_price'])

    def test_no_native_sales_access_no_projection_even_with_grant(self):
        self._sales();s=self._snapshot();u=self.users['sales']
        u.group_ids=[Command.set(self.env.ref(MODULE+'.group_vpr_sales_user').ids)]
        self.env['res.users'].invalidate_model(['vpr_sales_order_ids'])
        with self.assertRaises(AccessError):s.with_user(u).read()

    def test_other_company_selection_and_nested_forgery_blocked(self):
        self._sales();s=self._snapshot();u=self.users['sales']
        with self.assertRaises(AccessError):s.with_user(u).with_context(allowed_company_ids=self.b.ids).read()
        for rec in (s,s.line_ids,s.issue_ids):
            with self.assertRaises(AccessError):rec.with_user(u).write({'company_id':self.b.id})
        with self.assertRaises(AccessError):s.with_user(u).write({'line_ids':[Command.create({'company_id':self.b.id})]})

    def test_direct_create_copy_unlink_and_context_forgery_blocked(self):
        self._sales();s=self._snapshot()
        for name in (HEADER,LINE,ISSUE,REVIEW):
            with self.assertRaises(AccessError):self.env[name].with_context(vpr_internal=True,sudo=True).create({'company_id':self.a.id})
        for rec in (s,s.line_ids):
            with self.assertRaises(AccessError):rec.copy()
            with self.assertRaises(AccessError):rec.unlink()

    def test_grant_revocation_hides_history_search_read_export_and_aggregation(self):
        self._sales();s=self._snapshot();u=self.users['sales'];model=self.env[LINE].with_user(u)
        self.assertTrue(model.search([]))
        self.env[GRANT].search([('user_id','=',u.id)]).write({'active':False,'reason':'Access revoked'})
        self.assertFalse(model.search([]));self.assertFalse(model._read_group([],[],['__count'])[0][0])
        with self.assertRaises(AccessError):s.line_ids.with_user(u).read()
        with self.assertRaises(AccessError):s.line_ids.with_user(u).export_data(['source_unit_price'])

    def test_native_source_drilldown_and_assessment_do_not_grant_price_write(self):
        self._sales();s=self._snapshot();self.assertEqual(s.line_ids.with_user(self.users['sales']).action_open_source()['res_model'],'sale.order')
        with self.assertRaises(AccessError):s.line_ids.with_user(self.users['auditor']).action_review_price_protection('fixed_price_verified','ref','reason')

    def test_sales_user_cannot_collect_even_if_context_claims_manager(self):
        self._sales();a=self._run()
        with self.assertRaises(AccessError):a.with_user(self.users['sales']).with_context(is_manager=True).action_collect_sales_terms()

    def test_missing_warehouse_grant_hides_whole_multiwarehouse_snapshot(self):
        self._sales(10);self._sales(10,wh=self.wh2);a=self._run(warehouses=self.wh|self.wh2);s=self._snapshot(a);u=self.users['sales']
        self.env[GRANT].search([('user_id','=',u.id)]).write({'warehouse_ids':[Command.set(self.wh.ids)],'reason':'Narrowed scope'})
        with self.assertRaises(AccessError):s.line_ids.with_user(u).read()


@tagged('post_install','-at_install')
class TestSalesWorkload(SalesFixtures,TransactionCase):
    def test_100_lines_bounded_sales_projection(self):
        so,line=self._sales(2)
        self.env['sale.order.line'].create([{'order_id':so.id,'product_id':self.red.id,'product_uom_qty':2,'price_unit':140,'tax_ids':[Command.clear()]} for _ in range(99)])
        a=self._run();calls=[];original=SalesEngine.read
        def counted(engine,model,domain,names):
            calls.append(model);return original(engine,model,domain,names)
        started=time.perf_counter()
        with patch.object(SalesEngine,'read',counted):s=self._snapshot(a)
        elapsed=time.perf_counter()-started
        self.assertEqual(len(s.line_ids),100);self.assertEqual(D(s.totals[str(self.inr.id)+':confirmed']['value']),28000)
        self.assertEqual(calls.count('sale.order.line'),2);self.assertEqual(calls.count('sale.order'),1)
        _logger.info('PR11_WORKLOAD lines=100 elapsed=%.3fs value=28000 sales_line_projections=2 order_projections=1',elapsed)
