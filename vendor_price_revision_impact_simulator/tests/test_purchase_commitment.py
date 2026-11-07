"""PR12 operational fixtures are synthetic. Analysis must preserve their values."""
from decimal import Decimal as D
import logging
import time
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from .test_demand_allocation import AllocationFixtures
from .test_commercial_validation import MODULE
from ..models.purchase_commitment import HEADER, LINE, ISSUE, EVIDENCE, PurchaseEngine

_logger=logging.getLogger(__name__)


class PurchaseFixtures(AllocationFixtures):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.users['manager'].group_ids=[Command.link(cls.env.ref('account.group_account_readonly').id)]

    def _batch12(self):
        if not getattr(self,'_pb',False):self._pb=self._ready()
        return self._pb

    def _collect12(self,bills=False,allocation=0,rfqs=True,**kw):
        b=self._batch12();b.action_collect_supply(self.wh.ids,True)
        actor=self.users['manager'] if bills else self.users['purchase']
        return b.with_user(actor).action_collect_purchase_terms(self.wh.ids,rfqs,allocation,bills,**kw)

    def _row12(self,s,line=None):
        rows=s.line_ids.filtered(lambda r:r.po_line_id==line.id) if line else s.line_ids
        rows.ensure_one();return rows

    def _rfq(self,qty=70,price=115,state='draft',product=None):
        o=self.env['purchase.order'].with_company(self.a).create({'company_id':self.a.id,'partner_id':self.vendor.id,
            'currency_id':self.inr.id,'picking_type_id':self.wh.in_type_id.id,'order_line':[Command.create({
                'product_id':(product or self.red).id,'product_qty':qty,'uom_id':self.unit.id,'price_unit':price,
                'tax_ids':[Command.clear()],'date_planned':'2026-11-10 08:00:00'})]})
        if state!='draft':o.state=state
        return o,o.order_line

    def _assess12(self,r,kind='fixed',price=None,**kw):
        e=r.action_propose_evidence(kind,'Supplier written confirmation #12','Documented exact source assessment',price,**kw)
        e.with_user(self.users['manager']).action_verify('Independent supplier evidence and current source checked')
        return e

    def _bill12(self,line,qty=60,price=115,kind='in_invoice'):
        account=self.env['account.account'].search([('code','=','P12EXP'),('company_ids','in',self.a.ids)],limit=1)
        if not account:account=self.env['account.account'].create({'name':'PR12 Expense','code':'P12EXP','account_type':'expense','company_ids':[Command.set(self.a.ids)]})
        journal=self.env['account.journal'].search([('code','=','P12B'),('company_id','=',self.a.id)],limit=1)
        if not journal:journal=self.env['account.journal'].create({'name':'PR12 Bills','code':'P12B','type':'purchase','company_id':self.a.id,'default_account_id':account.id})
        return self.env['account.move'].create({'move_type':kind,'partner_id':self.vendor.id,'company_id':self.a.id,'journal_id':journal.id,
            'invoice_line_ids':[Command.create({'product_id':self.red.id,'quantity':qty,'product_uom_id':line.uom_id.id,
                'price_unit':price,'account_id':account.id,'purchase_line_id':line.id,'tax_ids':[Command.clear()]})]})


@tagged('post_install','-at_install')
class TestPurchaseReferences(PurchaseFixtures,TransactionCase):
    def test_reference_a_100_ordered_40_received_60_open_fixed_100(self):
        po,l=self._po(100,100);po.date_approve='2026-10-20 08:00:00';self._receive(po,40)
        r=self._row12(self._collect12());self.assertEqual(D(r.open_qty),60);self.assertEqual(D(r.open_commitment_value),6000)
        self.assertEqual(D(r.normalized_agreed_unit_price),100);self.assertEqual(r.protection_status,'protection_unknown')
        self._assess12(r);r=self._row12(self._collect12())
        self.assertEqual(r.protection_status,'protected_verified');self.assertEqual(D(r.protected_unit_price),100)
        self.assertEqual(D(r.proposed_unit_price),115);self.assertEqual(po.order_line.price_unit,100)
        self.assertEqual(r.date_conflict_status,'revision_after_protected_commitment')
        self.assertEqual(D(r.ordered_qty)*D(r.normalized_agreed_unit_price),10000)
        self.assertEqual(D(r.received_qty)*D(r.normalized_agreed_unit_price),4000)
        _logger.info('PR12_REFERENCE_A ordered=100 received=40 open=60 agreed=100 value=6000 protected=100 proposed=115 no_repricing')

    def test_reference_b_pending_115_difference900_not_payable(self):
        po,l=self._po(100,100);self._receive(po,40);r=self._row12(self._collect12())
        self._assess12(r,'amendment_pending','115');r=self._row12(self._collect12())
        self.assertEqual(r.amendment_status,'amendment_pending');self.assertEqual(D(r.open_commitment_value),6000)
        self.assertEqual(D(r.hypothetical_amended_value),6900);self.assertEqual(D(r.conditional_open_difference),900)
        self.assertEqual(l.price_unit,100);self.assertEqual(po.state,'purchase')
        _logger.info('PR12_REFERENCE_B recorded=6000 conditional_amended=6900 disputed_difference=900 not_approved_payable')

    def test_reference_c_negotiated95_not_supplier100(self):
        po,l=self._po(40,95);r=self._row12(self._collect12())
        self.assertEqual(D(r.normalized_agreed_unit_price),95);self.assertEqual(D(r.proposed_unit_price),115)
        self.assertEqual(D(r.conditional_unit_difference),20);self.assertEqual(D(r.conditional_open_difference),800)
        self.assertEqual(D(r.price_evidence['comparison']['baseline']['net_comparable']),100)
        _logger.info('PR12_REFERENCE_C pricelist=100 recorded=95 proposal=115 unit_difference=20 conditional=800')

    def test_reference_d_conditional_rfq70_value8050(self):
        po,l=self._rfq();r=self._row12(self._collect12())
        self.assertEqual(r.commitment_type,'conditional');self.assertEqual(D(r.conditional_value),8050)
        self.assertFalse(r.open_qty);self.assertFalse(r.open_commitment_value);self.assertEqual(r.protection_status,'not_applicable')
        self.assertFalse(r.quantity_evidence['quantity_verified']);self.assertFalse(po.picking_ids)
        _logger.info('PR12_REFERENCE_D conditional_qty=70 value=8050 confirmed_commitment=not_established incoming=not_confirmed')

    def test_draft_sent_approval_distinct_from_confirmed_and_cancel(self):
        self._rfq(state='draft');self._rfq(state='sent');self._rfq(state='to approve');cancelled,l=self._rfq(state='cancel')
        self._po(20,100);s=self._collect12()
        self.assertEqual(len(s.line_ids),4);self.assertEqual(len(s.line_ids.filtered(lambda r:r.commitment_type=='confirmed')),1)
        self.assertNotIn(l.id,s.line_ids.mapped('po_line_id'));self.assertEqual(len(s.totals),2)

    def test_actual_price_survives_current_supplier_rule_change(self):
        po,l=self._po(40,95);b=self._batch12();rule=self.env['product.supplierinfo'].search([('partner_id','=',self.vendor.id),('product_id','=',self.red.id)])
        rule.price=1100;b.action_validate_commercial_prices();r=self._row12(self._collect12())
        self.assertEqual(D(r.source_unit_price),95);self.assertEqual(l.price_unit,95)

    def test_same_product_two_lines_keep_exact_prices(self):
        po,l=self._po(40,95)
        extra=self.env['purchase.order.line'].create({'order_id':po.id,'product_id':self.red.id,'product_qty':20,'uom_id':self.unit.id,'price_unit':105,'tax_ids':[Command.clear()],'date_planned':'2026-11-02 08:00:00'})
        s=self._collect12();self.assertEqual(len(s.line_ids),2)
        self.assertEqual(D(self._row12(s,l).normalized_agreed_unit_price),95);self.assertEqual(D(self._row12(s,extra).normalized_agreed_unit_price),105)

    def test_other_vendor_other_variant_and_warehouse_excluded(self):
        self._po(40,100);other,l=self._rfq(product=self.white);foreign,l=self._rfq();foreign.partner_id=self.customer
        self._po(40,999,wh=self.wh2);s=self._collect12();self.assertEqual(len(s.line_ids),1);self.assertEqual(s.line_ids.product_id,self.red.id)

    def test_locked_confirmed_order_still_has_open_commitment(self):
        po,l=self._po(40,100);po.locked=True;r=self._row12(self._collect12());self.assertEqual(D(r.open_qty),40)

    def test_cancelled_po_excluded(self):
        po,l=self._po(40,100);po.button_cancel();self.assertFalse(self._collect12().line_ids)


@tagged('post_install','-at_install')
class TestPurchaseReceipts(PurchaseFixtures,TransactionCase):
    def test_multiple_receipts_backorder_once(self):
        po,l=self._po(100,100);self._receive(po,20);self._receive(po,30);r=self._row12(self._collect12())
        self.assertEqual((D(r.ordered_qty),D(r.received_qty),D(r.open_qty)),(100,50,50))
        self.assertEqual(D(r.open_commitment_value),5000)

    def test_fully_received_no_future_commitment(self):
        po,l=self._po(100,100);self._receive(po,100);r=self._row12(self._collect12());self.assertEqual(D(r.open_qty),0);self.assertEqual(D(r.open_commitment_value),0)

    def test_short_closed_remainder_not_open(self):
        po,l=self._po(100,100);self._receive(po,40,cancel=True);r=self._row12(self._collect12())
        self.assertEqual((D(r.received_qty),D(r.cancelled_qty),D(r.open_qty)),(40,60,0));self.assertEqual(D(r.open_commitment_value),0)

    def test_multistep_putaway_not_supplier_unreceived(self):
        self.wh.reception_steps='two_steps';self._classify(self.wh,self.wh.wh_input_stock_loc_id,'receiving')
        po,l=self._po(100,100);self._receive(po,40);r=self._row12(self._collect12())
        self.assertEqual(D(r.received_qty),40);self.assertEqual(D(r.open_qty),60)
        pending=self.env['stock.move'].search([('company_id','=',self.a.id),('product_id','=',self.red.id),('location_id','=',self.wh.wh_input_stock_loc_id.id),('location_dest_id','=',self.wh.lot_stock_id.id),('state','not in',['done','cancel'])])
        self.assertTrue(pending)
        supply=self.env['vendor.price.revision.supply.snapshot'].browse(r.quantity_evidence['authoritative_supply_id'])
        self.assertTrue(supply.bucket_ids.filtered(lambda b:b.kind in ('received_pending_putaway','internal_transfer_reference')))
        self.assertEqual(D(r.open_commitment_value),6000)

    def test_return_does_not_recreate_incoming(self):
        po,l=self._po(100,100);self._receive(po,100);original=l.move_ids.filtered(lambda m:m.state=='done')
        ret=self.env['stock.move'].create({'company_id':self.a.id,'product_id':self.red.id,'uom_id':self.unit.id,'product_uom_qty':20,'quantity':20,'picked':True,
            'purchase_line_id':l.id,'origin_returned_move_id':original.id,'to_refund':True,'location_id':self.wh.lot_stock_id.id,'location_dest_id':self.env.ref('stock.stock_location_suppliers').id})
        ret._action_confirm();ret._action_done();r=self._row12(self._collect12());self.assertEqual(D(r.open_qty),0)
        self.assertTrue(r.quantity_evidence['returns'])

    def test_unverified_receipt_quantity_is_blank_not_zero(self):
        po,l=self._po(100,100);l.move_ids.unlink();r=self._row12(self._collect12())
        self.assertFalse(r.open_qty);self.assertFalse(r.open_commitment_value);self.assertEqual(r.valuation_status,'incomplete')

    def test_pr10_exact_allocated60_open100_residual40(self):
        po,l=self._po(100,100);self._sale(60);b=self._batch12();a=self._run(batch=b)
        r=self._row12(self._collect12(allocation=a.id));self.assertEqual(D(r.open_qty),100)
        self.assertEqual(D(r.allocation_evidence['allocated']),60);self.assertEqual(D(r.allocation_evidence['unattributed']),40)
        self.assertEqual(len(a.entry_ids),1);self.assertEqual(D(a.entry_ids.quantity),60)

    def test_alternative_scenarios_cannot_be_added_or_passed_as_list(self):
        self._po(100,100);q,l=self._sale(70,False);b=self._batch12();a=self._run(batch=b,quotes=q.ids)
        s=self._collect12(allocation=a.id);self.assertEqual(s.allocation_source_id,a.id)
        with self.assertRaises(ValidationError):b.action_collect_purchase_terms(self.wh.ids,allocation_id=[a.id])

    def test_stale_allocation_blocks_linked_commitment_publication(self):
        self._po(100,100);so,l=self._sale(60);b=self._batch12();a=self._run(batch=b);self._collect12(allocation=a.id)
        l.product_uom_qty=70
        with self.assertRaises(UserError):self._collect12(allocation=a.id)


@tagged('post_install','-at_install')
class TestPurchaseEvidence(PurchaseFixtures,TransactionCase):
    def test_explicit_unknown_does_not_revive_legacy_firm_assessment(self):
        po,l=self._po();b=self._batch12();legacy=b.action_propose_supply_terms(self.wh.id,l.id,'firm','Signed old terms')
        legacy.with_user(self.users['manager']).action_verify_terms('Independently checked')
        r=self._row12(self._collect12());self.assertEqual(r.protection_status,'protected_verified')
        self._assess12(r,'unknown');new=self._row12(self._collect12());self.assertEqual(new.protection_status,'protection_unknown')

    def test_amendment_request120_separate_from_general_proposal115(self):
        po,l=self._po(100,100);self._receive(po,40);r=self._row12(self._collect12())
        self._assess12(r,'amendment_pending','120');r=self._row12(self._collect12())
        self.assertEqual(D(r.proposed_unit_price),115);self.assertEqual(D(r.conditional_open_difference),900)
        self.assertEqual(D(r.amendment_evidence['conditional_difference']),1200)
        self.assertEqual(D(r.amendment_evidence['hypothetical_open_value']),7200)
        self.assertEqual(l.price_unit,100)

    def test_accepted_recorded_assessment_retains_documented_observation(self):
        po,l=self._po(100,108);r=self._row12(self._collect12());self._assess12(r,'accepted_recorded','108')
        r=self._row12(self._collect12());self.assertEqual(r.amendment_status,'accepted_recorded');self.assertEqual(l.price_unit,108)

    def test_confirmation_without_evidence_not_fixed(self):
        self._po();r=self._row12(self._collect12());self.assertEqual(r.protection_status,'protection_unknown');self.assertFalse(r.protected_unit_price)

    def test_legacy_pr09_independently_verified_firm_terms_reused(self):
        po,l=self._po();b=self._batch12();e=b.action_propose_supply_terms(self.wh.id,l.id,'firm','Signed exact PO terms')
        e.with_user(self.users['manager']).action_verify_terms('Independent source check');r=self._row12(self._collect12())
        self.assertEqual(r.protection_status,'protected_verified');self.assertEqual(r.protection_evidence['attestation_id'],e.id)

    def test_independent_checker_and_required_reference(self):
        self._po();r=self._row12(self._collect12())
        with self.assertRaises(ValidationError):r.action_propose_evidence('fixed','','reason')
        e=r.action_propose_evidence('fixed','Signed confirmation','Reason')
        with self.assertRaises(AccessError):e.with_user(self.users['purchase']).action_verify('Own evidence')
        self.users['purchase'].group_ids=[Command.link(self.env.ref(MODULE+'.group_vpr_purchase_manager').id)]
        with self.assertRaises(ValidationError):e.with_user(self.users['purchase']).action_verify('Own manager evidence')
        with self.assertRaises(ValidationError):e.with_user(self.users['manager']).action_verify('')
        e.with_user(self.users['manager']).action_verify('Independent check');self.assertEqual(e.state,'verified')

    def test_adjustable_clause_and_date_overlap_not_price_execution(self):
        po,l=self._po(100,100);po.date_approve='2026-10-20 08:00:00';r=self._row12(self._collect12())
        self._assess12(r,'adjustable');r=self._row12(self._collect12())
        self.assertEqual(r.protection_status,'price_adjustable_verified');self.assertEqual(r.date_conflict_status,'revision_within_adjustable_period')
        self.assertEqual(l.price_unit,100)

    def test_expired_agreement_not_protection(self):
        self._po();r=self._row12(self._collect12());self._assess12(r,effective_end='2020-01-01')
        r=self._row12(self._collect12());self.assertEqual(r.protection_status,'protection_unknown');self.assertIn('AGREEMENT_EXPIRED',r.issue_codes)

    def test_unverified_amendment_preserves_fixed_rights(self):
        self._po();r=self._row12(self._collect12());self._assess12(r);r=self._row12(self._collect12())
        e=r.action_propose_evidence('amendment_pending','Supplier request','Not accepted','115')
        r=self._row12(self._collect12());self.assertEqual(e.state,'proposed');self.assertEqual(r.protection_status,'protected_verified')
        self.assertEqual(r.amendment_status,'amendment_pending');self.assertEqual(D(r.source_unit_price),100)

    def test_recorded_accepted_evidence_cannot_execute_proposed_price(self):
        po,l=self._po(100,100);r=self._row12(self._collect12())
        with self.assertRaises(ValidationError):r.action_propose_evidence('accepted_recorded','Reference','Not an editor','115')
        self.assertEqual(l.price_unit,100)

    def test_actual_price_change_retains_history_and_requires_current_assessment(self):
        po,l=self._po(100,100);old=self._collect12();r=self._row12(old);self._assess12(r)
        l.price_unit=108;new=self._collect12();r=self._row12(new)
        self.assertEqual(D(self._row12(old).source_unit_price),100);self.assertEqual(D(r.source_unit_price),108)
        self.assertEqual(r.protection_status,'protection_unknown');self.assertIn('PO_PRICE_CHANGED',r.issue_codes)
        self.assertEqual(self._collect12(),new)

    def test_pending_assessment_cannot_be_verified_after_source_change(self):
        po,l=self._po();r=self._row12(self._collect12());e=r.action_propose_evidence('fixed','Supplier acknowledgement','Exact terms')
        l.price_unit=110
        with self.assertRaises(UserError):e.with_user(self.users['manager']).action_verify('Changed source')
        self.assertEqual(e.state,'proposed')

    def test_rfq_not_verified_fixed_or_accepted_purchase(self):
        self._rfq();r=self._row12(self._collect12())
        for kind in ('fixed','adjustable','accepted_recorded'):
            with self.assertRaises(ValidationError):r.action_propose_evidence(kind,'Ref','Not confirmed','115')


@tagged('post_install','-at_install')
class TestPurchaseNormalization(PurchaseFixtures,TransactionCase):
    def test_original_quantity_tiers_and_variant_date_scope(self):
        from .test_import_validation import VALID
        self._rule();rows=[]
        for minimum,price in ((1,115),(100,109)):
            row=list(VALID);row[0]=self.red.default_code;row[2]=str(price);row[4]='PCS';row[5]=str(minimum);rows.append(row)
        b=self._commercial_batch(rows);self._context(b);self._validate(b);self._pb=b
        po,l=self._po(100,100);self._receive(po,40);r=self._row12(self._collect12())
        self.assertEqual(D(r.open_qty),60);self.assertEqual(D(r.proposed_unit_price),109)
        self.assertEqual(D(r.price_evidence['comparison']['quantity']),100)
        self.assertEqual(D(r.conditional_open_difference),540)

    def test_zero_is_explicit_recorded_price_not_missing(self):
        po,l=self._po(10,0);r=self._row12(self._collect12());self.assertEqual(D(r.normalized_agreed_unit_price),0);self.assertEqual(D(r.open_commitment_value),0)

    def test_tax_definition_amendment_stales_frozen_tax_evidence(self):
        po,l=self._po(10,118);tax=self.env['account.tax'].create({'name':'PR12 Included18','company_id':self.a.id,'amount':18,'amount_type':'percent','type_tax_use':'purchase','price_include_override':'tax_included'})
        l.tax_ids=tax;s=self._collect12();self.assertEqual(s.line_ids.source_terms['taxes'][0]['amount'],18)
        tax.amount=20
        with self.assertRaises(UserError):s.action_check_current()
        self.assertEqual(s.line_ids.source_terms['taxes'][0]['amount'],18)

    def test_box10_inverse_price_and_quantity(self):
        po,l=self._po(10,1000,uom=self.box);r=self._row12(self._collect12())
        self.assertEqual(D(r.ordered_qty),100);self.assertEqual(D(r.normalized_agreed_unit_price),100);self.assertEqual(D(r.open_commitment_value),10000)
        self.assertEqual(r.source_uom_id,self.box);self.assertEqual(r.comparison_uom_id,self.unit)

    def test_line_discount_once_and_negative_discount_native(self):
        po,l=self._po(100,100);l.discount=10;r=self._row12(self._collect12());self.assertEqual(D(r.normalized_agreed_unit_price),90);self.assertEqual(D(r.open_commitment_value),9000)
        l.discount=-10;r=self._row12(self._collect12());self.assertEqual(D(r.normalized_agreed_unit_price),110);self.assertEqual(D(r.open_commitment_value),11000)

    def test_included_tax_is_not_net_goods_cost(self):
        po,l=self._po(100,118);tax=self.env['account.tax'].create({'name':'PR12 Included18','company_id':self.a.id,'amount':18,'amount_type':'percent','type_tax_use':'purchase','price_include_override':'tax_included'})
        l.tax_ids=tax;r=self._row12(self._collect12());self.assertEqual(D(r.normalized_agreed_unit_price),100);self.assertEqual(D(r.open_commitment_value),10000)

    def test_missing_fx_keeps_foreign_source_value_not_one_to_one(self):
        po,l=self._po(100,10);po.currency_id=self.usd;l.price_unit=10
        r=self._row12(self._collect12(fx_date='1900-01-01'));self.assertEqual(D(r.open_commitment_value),1000)
        self.assertFalse(r.company_open_value);self.assertIn('PO_FX_RATE_MISSING',r.issue_codes)

    def test_guarded_fx_direction_and_same_rate_comparison(self):
        self._rates();po,l=self._po(100,10);po.currency_id=self.usd;l.price_unit=10
        r=self._row12(self._collect12(fx_date='2026-10-28'))
        self.assertEqual(D(r.company_unit_price),940);self.assertEqual(D(r.company_open_value),94000)
        self.assertEqual(r.comparison_currency_id,self.inr)
        self.assertEqual(r.price_evidence['fx']['requested_date'],'2026-10-28')

    def test_mixed_currency_and_rfq_totals_separate(self):
        self._po(100,100);po,l=self._po(100,10);po.currency_id=self.usd;l.price_unit=10;self._rfq()
        s=self._collect12();self.assertEqual(len(s.totals),3)
        self.assertEqual(D(s.totals[str(self.inr.id)+':conditional']['value']),8050)

    def test_no_applicable_proposal_date_does_not_fabricate_delta(self):
        po,l=self._po();r=self._row12(self._collect12(comparison_date='2026-10-01'))
        self.assertFalse(r.proposed_unit_price);self.assertFalse(r.conditional_open_difference);self.assertIn('PROPOSED_PRICE_NOT_APPLICABLE',r.issue_codes)

    def test_order_service_adjustment_is_not_stock_or_allocated_charge(self):
        po,l=self._po();service=self.env['product.product'].create({'name':'PR12 Freight','type':'service'})
        self.env['purchase.order.line'].create({'order_id':po.id,'product_id':service.id,'product_qty':1,'uom_id':self.unit.id,'price_unit':500,'date_planned':'2026-11-02 08:00:00','tax_ids':[Command.clear()]})
        r=self._row12(self._collect12());self.assertEqual(r.valuation_status,'incomplete');self.assertFalse(r.open_commitment_value)
        self.assertIn('ORDER_CHARGES_UNALLOCATED',r.issue_codes)


@tagged('post_install','-at_install')
class TestPurchaseBills(PurchaseFixtures,TransactionCase):
    def test_reference_e_billed60_received50_open50(self):
        po,l=self._po(100,100);self._receive(po,50);bill=self._bill12(l,60,115);r=self._row12(self._collect12(bills=True))
        self.assertEqual(D(r.open_qty),50);self.assertEqual(D(r.billed_qty),60);self.assertEqual(D(r.open_commitment_value),5000)
        e=r.bill_evidence['bills'][0];self.assertEqual(e['state'],'draft');self.assertEqual(D(e['difference']),15)
        self.assertEqual(e['comparison'],'bill_price_mismatch_review');self.assertEqual(l.price_unit,100);self.assertEqual(bill.state,'draft')
        _logger.info('PR12_REFERENCE_E billed=60 received=50 open=50 draft_bill115 PO100 mismatch15 no_posting')

    def test_multiple_bills_and_credit_not_extra_commitments(self):
        po,l=self._po(100,100);self._bill12(l,40,100);self._bill12(l,20,115);self._bill12(l,10,115,'in_refund')
        r=self._row12(self._collect12(bills=True));self.assertEqual(D(r.open_qty),100);self.assertEqual(len(r.bill_evidence['bills']),3)
        credit=[b for b in r.bill_evidence['bills'] if b['move_type']=='in_refund'][0]
        self.assertEqual(credit['comparison'],'credit_note_reference_only');self.assertEqual(r.amendment_status,'no_documented_amendment')

    def test_unlinked_bill_not_matched(self):
        po,l=self._po();bill=self._bill12(l);bill.invoice_line_ids.purchase_line_id=False
        r=self._row12(self._collect12(bills=True));self.assertFalse(r.bill_evidence['bills'])

    def test_not_requested_billing_does_not_read_account_models(self):
        self._po();s=self._collect12();self.assertEqual(s.line_ids.bill_evidence['status'],'not_verified_not_requested')
        self.assertNotIn('account.move.line',s.provenance['sources'])

    def test_native_accounting_required_and_revocation_hides_bill_projection(self):
        self._po();b=self._batch12();b.action_collect_supply(self.wh.ids)
        with self.assertRaises(AccessError):b.action_collect_purchase_terms(self.wh.ids,include_bills=True)
        s=self._collect12(bills=True)
        with self.assertRaises(AccessError):s.with_user(self.users['purchase']).read()
        with self.assertRaises(AccessError):s.line_ids.with_user(self.users['auditor']).read()

    def test_bill_change_stales_only_bill_inclusive_scope(self):
        po,l=self._po();bill=self._bill12(l);plain=self._collect12();detailed=self._collect12(bills=True)
        bill.invoice_line_ids.price_unit=120
        self.assertTrue(plain._current());self.assertFalse(detailed._current())


@tagged('post_install','-at_install')
class TestPurchaseIntegrity(PurchaseFixtures,TransactionCase):
    def test_idempotent_snapshots_and_issues(self):
        self._po();s=self._collect12();again=self._collect12();self.assertEqual(s,again)
        self.assertEqual(s.batch_id.get_current_purchase_terms(self.wh.ids),s)
        self.assertEqual(len(self.env[HEADER].search([('batch_id','=',s.batch_id.id)])),1)

    def test_price_receipt_and_source_policy_changes_stale(self):
        po,l=self._po(100,100);s=self._collect12();self._receive(po,40)
        with self.assertRaises(UserError):s.action_check_current()
        new=self._collect12();self.assertEqual(D(new.line_ids.open_qty),60)
        self.assertEqual(D(s.line_ids.open_qty),100);self.assertEqual(new.previous_id,s)

    def test_notes_do_not_change_financial_inputs(self):
        po,l=self._po();s=self._collect12();po.note='Unrelated packing instructions';self.assertEqual(self._collect12(),s)

    def test_atomic_child_failure_no_success_header(self):
        self._po();b=self._batch12();count=self.env[HEADER].search_count([('batch_id','=',b.id)])
        with patch.object(type(self.env[LINE]),'_record',side_effect=UserError('Interrupted purchase publication')),self.assertRaises(UserError):self._collect12()
        self.assertEqual(self.env[HEADER].search_count([('batch_id','=',b.id)]),count)

    def test_operational_records_and_counts_unchanged(self):
        po,l=self._po();self._sale(20);self._quant(50);b=self._batch12();b.action_collect_supply(self.wh.ids)
        names=['purchase.order','purchase.order.line','product.supplierinfo','stock.move','stock.move.line','stock.quant','stock.picking','sale.order','sale.order.line','account.move','account.move.line','res.currency.rate','mail.mail','ir.cron']
        def capture():
            self.env.flush_all()
            return {n:self.env[n].search([]).read([k for k,f in self.env[n]._fields.items() if f.store and f.type not in ('binary','one2many','many2many')],load=None) for n in names}
        before=capture();s=self._collect12();self._collect12();s.batch_id.get_current_purchase_terms(self.wh.ids)
        self.assertEqual(before,capture())


@tagged('post_install','-at_install')
class TestPurchaseSecurity(PurchaseFixtures,TransactionCase):
    def test_user_metadata_cannot_impersonate_another_accounting_user(self):
        po,l=self._po();bill=self._bill12(l);self._collect12(bills=True);manager=self.users['manager']
        self.assertIn(bill.id,manager.with_user(manager).vpr_purchase_bill_ids.ids)
        with self.assertRaises(AccessError):manager.with_user(self.users['employee']).read(['vpr_purchase_bill_ids'])
        with self.assertRaises(AccessError):manager.with_user(self.users['employee']).with_context(uid=manager.id).read([
            'vpr_purchase_bill_ids','vpr_purchase_bill_line_ids'])
        self.assertFalse(manager.with_user(self.users['employee']).read(['vpr_purchase_bill_access'])[0]['vpr_purchase_bill_access'])

    def test_native_bill_record_rule_hides_snapshot_not_just_model_acl(self):
        po,l=self._po();bill=self._bill12(l);s=self._collect12(bills=True);u=self.users['manager']
        self.assertTrue(s.with_user(u).read(['contains_bills']))
        self.env['ir.access'].create({'name':'PR12 exact bill restriction','model_id':self.env.ref('account.model_account_move').id,
            'group_id':False,'operation':'r','domain':"[('id','!=',%s)]"%bill.id})
        self.env['res.users'].invalidate_model(['vpr_purchase_bill_ids','vpr_purchase_bill_line_ids'])
        self.assertFalse(self.env[HEADER].with_user(u).search([('id','=',s.id)]))
        with self.assertRaises(AccessError):s.with_user(u).read()
        with self.assertRaises(AccessError):s.line_ids.with_user(u).export_data(['bill_evidence'])

    def test_company_b_combined_roles_cannot_read_export_or_assess_company_a(self):
        self._po();s=self._collect12();u=self.users['purchase_b']
        u.group_ids=[Command.link(self.env.ref(MODULE+'.group_vpr_purchase_manager').id)]
        self.env['vendor.price.revision.supply.grant'].create({'company_id':self.b.id,'user_id':u.id,
            'warehouse_ids':[Command.set(self.wh_b.ids)],'allow_cost':True,'reason':'Other-company scoped cost access'})
        model=self.env[LINE].with_user(u).with_context(allowed_company_ids=self.b.ids)
        self.assertFalse(model.search([]));self.assertEqual(model._read_group([],[],['__count'])[0][0],0)
        rec=s.line_ids.with_user(u).with_context(allowed_company_ids=self.b.ids)
        with self.assertRaises(AccessError):rec.read()
        with self.assertRaises(AccessError):rec.export_data(['source_unit_price'])
        with self.assertRaises(AccessError):rec.action_propose_evidence('fixed','Ref','Other company')

    def test_bill_visibility_revocation_hides_existing_projection(self):
        po,l=self._po();self._bill12(l);s=self._collect12(bills=True);u=self.users['manager']
        self.assertTrue(s.with_user(u).read(['contains_bills']))
        u.group_ids=[Command.set(self.env.ref(MODULE+'.group_vpr_purchase_manager').ids)]
        self.env['res.users'].invalidate_model(['vpr_purchase_bill_access'])
        with self.assertRaises(AccessError):s.with_user(u).read()

    def test_sales_portal_employee_configuration_and_foreign_user_denied(self):
        self._po();s=self._collect12()
        for role in ('sales','portal','employee','configuration','purchase_b','other'):
            with self.subTest(role=role),self.assertRaises(AccessError):s.line_ids.with_user(self.users[role]).read()

    def test_company_scope_and_cost_grant_revocation_search_export_group(self):
        self._po();s=self._collect12();u=self.users['purchase'];m=self.env[LINE].with_user(u)
        self.assertTrue(m.search([]))
        grant=self.env['vendor.price.revision.supply.grant'].search([('user_id','=',u.id)])
        grant.write({'allow_cost':False,'reason':'Revoke cost permission'})
        self.assertFalse(m.search([]));self.assertEqual(m._read_group([],[],['__count'])[0][0],0)
        with self.assertRaises(AccessError):s.with_user(u).read()
        with self.assertRaises(AccessError):s.line_ids.with_user(u).export_data(['source_unit_price'])

    def test_direct_forgery_nested_commands_context_and_auditor_readonly(self):
        self._po();s=self._collect12()
        for model in (HEADER,LINE,ISSUE,EVIDENCE):
            with self.assertRaises(AccessError):self.env[model].with_context(vpr_internal=True,sudo=True).create({'batch_id':s.batch_id.id})
        for rec in (s,s.line_ids):
            with self.assertRaises(AccessError):rec.write({'company_id':self.b.id})
            with self.assertRaises(AccessError):rec.copy()
            with self.assertRaises(AccessError):rec.unlink()
        with self.assertRaises(AccessError):s.write({'line_ids':[Command.create({'company_id':self.b.id})]})
        with self.assertRaises(AccessError):s.line_ids.with_user(self.users['auditor']).action_propose_evidence('fixed','Ref','Readonly')

    def test_native_source_opening_separate_from_analytical_grant(self):
        self._po();r=self._row12(self._collect12())
        with self.assertRaises(AccessError):r.action_open_source()

    def test_direct_verified_status_cannot_be_forged(self):
        self._po();r=self._row12(self._collect12());e=r.action_propose_evidence('fixed','Reference','Reason')
        with self.assertRaises(AccessError):e.write({'state':'verified','verified_by':self.users['manager'].id})
        with self.assertRaises(AccessError):e.with_user(self.users['auditor']).action_verify('Not manager')

    def test_linked_allocation_requires_customer_demand_scope(self):
        self._po();self._sale(20);b=self._batch12();a=self._run(batch=b);s=self._collect12(allocation=a.id)
        grant=self.env['vendor.price.revision.supply.grant'].search([('user_id','=',self.users['purchase'].id)])
        grant.write({'allow_demand':False,'reason':'No customer quantity disclosure'})
        with self.assertRaises(AccessError):s.read()

    def test_wizard_cannot_be_alternate_bill_source_export_or_join(self):
        self._po();s=self._collect12();u=self.users['purchase']
        w=self.env['vendor.price.revision.purchase.evidence.wizard'].with_user(u).create({'line_id':s.line_ids.id,'kind':'fixed','reference':'Ref','reason':'Reason'})
        with self.assertRaises(AccessError):w.export_data(['line_id/bill_evidence'])
        with self.assertRaises(AccessError):w.web_read({'line_id':{'fields':{'bill_evidence':{}}}})
        with self.assertRaises(AccessError):w.search([('line_id.bill_evidence','!=',False)])


@tagged('post_install','-at_install')
class TestPurchaseWorkload(PurchaseFixtures,TransactionCase):
    def test_100_lines_bulk_projection_and_total(self):
        po,l=self._rfq(1,100)
        self.env['purchase.order.line'].create([{'order_id':po.id,'product_id':self.red.id,'product_qty':1,'uom_id':self.unit.id,'price_unit':100,'tax_ids':[Command.clear()],'date_planned':'2026-11-02 08:00:00'} for _ in range(99)])
        self._batch12().action_collect_supply(self.wh.ids);started=time.perf_counter();s=self._collect12();elapsed=time.perf_counter()-started
        self.assertEqual(len(s.line_ids),100);self.assertEqual(D(s.totals[str(self.inr.id)+':conditional']['value']),10000)
        _logger.info('PR12_WORKLOAD lines=100 seconds=%.3f conditional_value=10000',elapsed)
