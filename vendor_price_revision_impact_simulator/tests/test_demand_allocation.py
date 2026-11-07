"""PR10 actual operational fixtures; analysis itself never mutates them."""
from decimal import Decimal as D
import logging
import time
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from .test_supply_foundation import SupplyFixtures
from .test_commercial_validation import MODULE
from ..models.allocation_policy import GRANT, POLICY
from ..models.allocation_engine import HEADER, DEMAND, LEDGER, ISSUE, take

_logger=logging.getLogger(__name__)


class AllocationFixtures(SupplyFixtures):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env[GRANT].search([('company_id','=',cls.a.id)]).write({'allow_demand':True,'reason':'Explicit PR10 sales-demand analytical grant'})
        (cls.wh|cls.wh2|cls.wh3).out_type_id.reservation_method='manual'
        cls.customer=cls.env['res.partner'].create({'name':'PR10 Customer'})
        cls.pricelist=cls.env['product.pricelist'].create({'name':'PR10 INR','currency_id':cls.inr.id,'company_id':cls.a.id})

    def _sale(self,qty=200,confirm=True,wh=None,product=None,uom=None,date='2026-11-05 10:00:00'):
        wh=wh or self.wh;product=product or self.red
        sale=self.env['sale.order'].with_company(self.a).create({'partner_id':self.customer.id,'company_id':self.a.id,
            'warehouse_id':wh.id,'pricelist_id':self.pricelist.id,'commitment_date':date,
            'order_line':[Command.create({'product_id':product.id,'product_uom_qty':qty,
                'product_uom_id':(uom or self.unit).id,'price_unit':150,'tax_ids':[Command.clear()]})]})
        if confirm:sale.action_confirm()
        return sale,sale.order_line

    def _reservation(self,line,qty):
        moves=line.move_ids.filtered(lambda m:m.state not in ('done','cancel') and m.location_id==self.wh.lot_stock_id)
        moves.ensure_one();moves._update_reserved_quantity(qty,self.wh.lot_stock_id)
        self.env.flush_all()
        return moves

    def _run(self,batch=None,warehouses=None,costs=True,confirmed=None,quotes=None,horizon=None,reason=None):
        batch=batch or self._ready();warehouses=warehouses or self.wh
        batch.action_collect_supply(warehouses.ids,costs)
        return batch.action_run_allocation(warehouses.ids,costs,horizon,confirmed,quotes,reason)

    def _one(self,snapshot,line=None):
        rows=snapshot.demand_ids.filtered(lambda r:r.sale_line_id==line.id) if line else snapshot.demand_ids
        rows.ensure_one();return rows

    def _check(self,snapshot):
        for row in snapshot.demand_ids:
            if row.outstanding:
                self.assertEqual(D(row.outstanding),sum(D(row[k] or '0') for k in ('reserved','free_stock','incoming','new_procurement','unresolved')))
        for key,cap in (snapshot.source_capacities or {}).items():
            consumed=sum((D(e.quantity) for e in snapshot.entry_ids if e.capacity_key==key),D(0))
            self.assertEqual(consumed,D(cap['allocated']));self.assertLessEqual(consumed,D(cap['initial']))
            self.assertEqual(consumed+D(cap['remaining']),D(cap['initial']))


@tagged('post_install','-at_install')
class TestAllocationHelpers(TransactionCase):
    def test_capacity_math_retains_38_digit_precision(self):
        used,need,left=take('123456789012345678901234567890.12345678','.00000001')
        self.assertEqual(used,D('.00000001'))
        self.assertEqual(need,D('123456789012345678901234567890.12345677'))
        self.assertEqual(left,0)

    def test_decimal_consumption_no_truncation_or_negative_balance(self):
        self.assertEqual(take('1.25','.4'),(D('.4'),D('.85'),D('0')))
        self.assertEqual(take('0','3'),(D('0'),D('0'),D('3')))
        self.assertEqual(take('3','1'),(D('1'),D('2'),D('0')))
        for x in ('-1','NaN',None):
            with self.assertRaises(ValueError):take(x,'10')


@tagged('post_install','-at_install')
class TestConfirmedDemand(AllocationFixtures,TransactionCase):
    def test_confirmed_200_draft_sent_and_cancel_excluded(self):
        self._sale();draft,_=self._sale(70,False);sent,_=self._sale(30,False);sent.state='sent'
        cancelled,_=self._sale(25);cancelled.action_cancel()
        s=self._run();self.assertEqual(len(s.demand_ids),1);self.assertEqual(D(s.demand_ids.outstanding),200)
        self.assertEqual(s.demand_ids.demand_type,'confirmed');self._check(s)

    def test_partial_delivery_100_40_backorder_60(self):
        so,line=self._sale(100);move=line.move_ids;move.quantity=40;move.picked=True
        move.picking_id._action_done();s=self._run();row=self._one(s)
        self.assertEqual((D(row.ordered),D(row.delivered),D(row.outstanding)),(100,40,60));self._check(s)

    def test_short_closed_delivery_does_not_erase_unchanged_sales_commitment(self):
        so,line=self._sale(100);move=line.move_ids;move.quantity=40;move.picked=True
        move.picking_id.with_context(cancel_backorder=True)._action_done();s=self._run();row=self._one(s)
        self.assertEqual(line.product_uom_qty,100);self.assertEqual(line.qty_delivered,40)
        self.assertEqual((D(row.outstanding),D(row.unresolved),D(row.new_procurement)),(60,60,0))
        self.assertIn('CANCELLED_DELIVERY_COMMITMENT_REVIEW',s.issue_ids.mapped('code'));self._check(s)

    def test_short_closed_delivery_with_commercial_quantity_amendment_has_no_open_demand(self):
        so,line=self._sale(100);move=line.move_ids;move.quantity=40;move.picked=True
        move.picking_id.with_context(cancel_backorder=True)._action_done();line.product_uom_qty=40
        s=self._run();self.assertEqual(line.product_uom_qty,line.qty_delivered);self.assertFalse(s.demand_ids)

    def test_cancelled_old_route_and_active_replacement_do_not_duplicate_commitment(self):
        self._quant(100);so,line=self._sale(100);move=line.move_ids;move.quantity=40;move.picked=True
        move.picking_id.with_context(cancel_backorder=True)._action_done()
        replacement=self.env['stock.move'].create({'company_id':self.a.id,'product_id':self.red.id,'uom_id':self.unit.id,
            'product_uom_qty':60,'location_id':self.wh.lot_stock_id.id,'location_dest_id':self.env.ref('stock.stock_location_customers').id,'sale_line_id':line.id})
        replacement._action_confirm();s=self._run();row=self._one(s)
        self.assertEqual((D(row.outstanding),D(row.free_stock),D(row.new_procurement)),(60,60,0))
        self.assertNotIn('DELIVERY_BOUNDARY_MISMATCH',s.issue_ids.mapped('code'));self._check(s)

    def test_multiple_steps_do_not_duplicate_commercial_demand(self):
        self.wh.delivery_steps='pick_pack_ship'
        self._quant(100)
        self._classify(self.wh,self.wh.wh_pack_stock_loc_id,'staging')
        self._classify(self.wh,self.wh.wh_output_stock_loc_id,'staging')
        so,line=self._sale(100)
        for step in range(2):
            move=line.move_ids.filtered(lambda m:m.state not in ('done','cancel'))
            move.ensure_one();move.quantity=100;move.picked=True;move.picking_id._action_done()
        self.assertGreaterEqual(len(line.move_ids),3)
        s=self._run();self.assertEqual(len(s.demand_ids),1);self.assertEqual(D(s.demand_ids.outstanding),100)
        self._check(s)

    def test_return_does_not_fabricate_new_replacement_commitment(self):
        so,line=self._sale(100);original=line.move_ids;original.quantity=100;original.picked=True;original._action_done()
        ret=self.env['stock.move'].create({'product_id':self.red.id,'uom_id':self.unit.id,'product_uom_qty':20,'quantity':20,
            'picked':True,'company_id':self.a.id,'location_id':self.env.ref('stock.stock_location_customers').id,
            'location_dest_id':self.wh.lot_stock_id.id,'sale_line_id':line.id,'origin_returned_move_id':original.id,'to_refund':True})
        ret._action_confirm();ret._action_done();s=self._run();row=self._one(s)
        self.assertEqual(D(row.new_procurement),0);self.assertEqual(row.status,'unresolved')
        self.assertIn('RETURN_REPLACEMENT_REVIEW',s.issue_ids.mapped('code'));self._check(s)

    def test_box_demand_normalized_to_product_base_units(self):
        self._sale(20,uom=self.box);s=self._run();self.assertEqual(D(self._one(s).outstanding),200)

    def test_variants_and_irrelevant_products_not_collapsed(self):
        self._sale(100,product=self.white);self._sale(70)
        s=self._run();self.assertEqual(len(s.demand_ids),1);self.assertEqual(s.demand_ids.product_id,self.red.id)

    def test_service_does_not_become_physical_new_procurement(self):
        self.red.is_storable=False;self._sale(100);s=self._run();row=self._one(s)
        self.assertEqual(D(row.new_procurement),0);self.assertEqual(D(row.unresolved),100)
        self.assertIn('NON_STOCK_DEMAND',s.issue_ids.mapped('code'))

    def test_missing_delivery_evidence_is_unresolved(self):
        so,line=self._sale(100);line.move_ids.unlink();s=self._run();row=self._one(s)
        self.assertEqual(D(row.new_procurement),0);self.assertEqual(D(row.unresolved),100)

    def test_date_horizon_retains_only_due_scope(self):
        self._sale(40,date='2026-11-02 08:00:00');self._sale(60,date='2026-11-10 08:00:00')
        s=self._run(horizon='2026-11-05 23:59:59');self.assertEqual(D(self._one(s).outstanding),40)


@tagged('post_install','-at_install')
class TestAllocationReservations(AllocationFixtures,TransactionCase):
    def test_multistep_current_reservation_counted_only_at_current_physical_stage(self):
        self.wh.delivery_steps='pick_pack_ship';self._quant(100)
        self._classify(self.wh,self.wh.wh_pack_stock_loc_id,'staging')
        self._classify(self.wh,self.wh.wh_output_stock_loc_id,'saleable')
        so,line=self._sale(100)
        for step in range(2):
            move=line.move_ids.filtered(lambda m:m.state not in ('done','cancel'))
            move.quantity=100;move.picked=True;move.picking_id._action_done()
        final=line.move_ids.filtered(lambda m:m.state not in ('done','cancel'))
        final._do_unreserve()  # Fixture: the push chain may automatically reserve80.
        final._update_reserved_quantity(20,self.wh.wh_output_stock_loc_id)
        self.assertEqual(final.quantity,20)
        s=self._run();row=self._one(s)
        self.assertEqual((D(row.outstanding),D(row.reserved),D(row.free_stock),D(row.new_procurement)),(100,20,80,0));self._check(s)

    def test_draft_linked_reservation_is_not_confirmed_reservation_coverage(self):
        self._quant(20);quote,line=self._sale(20,False)
        move=self.env['stock.move'].create({'company_id':self.a.id,'product_id':self.red.id,'uom_id':self.unit.id,
            'product_uom_qty':20,'location_id':self.wh.lot_stock_id.id,'location_dest_id':self.env.ref('stock.stock_location_customers').id,'sale_line_id':line.id})
        move._action_confirm();move._update_reserved_quantity(20,self.wh.lot_stock_id)
        s=self._run(quotes=quote.ids);row=self._one(s)
        self.assertEqual(D(row.reserved),0);self.assertEqual(D(row.free_stock),0)
        self.assertIn('RESERVATION_NONCONFIRMED_OWNER',s.issue_ids.mapped('code'))

    def test_reference_A_outside_reserved20_free60_incoming40_new100(self):
        self._quant(80);outside,ol=self._sale(20);self._reservation(ol,20)
        included,line=self._sale(200);po,pl=self._po(qty=40);batch=self._ready()
        terms=batch.action_propose_supply_terms(self.wh.id,pl.id,'firm','Signed protected purchase price for reference A')
        terms.with_user(self.users['manager']).action_verify_terms('Independent firm price check')
        s=self._run(batch,confirmed=included.ids);row=self._one(s)
        self.assertEqual(tuple(D(row[k]) for k in ('outstanding','reserved','free_stock','incoming','new_procurement')),(200,0,60,40,100));self.assertEqual(D(row.protected_incoming),40);self._check(s)
        _logger.info('PR10_REFERENCE_A demand=200 included_reserved=0 free=60 protected_incoming=40 new=100')

    def test_reference_B_included_reserved20_free60_incoming40_new80(self):
        self._quant(80);so,line=self._sale(200);self._reservation(line,20);po,pl=self._po(qty=40);batch=self._ready()
        terms=batch.action_propose_supply_terms(self.wh.id,pl.id,'firm','Signed fixed price purchase terms')
        terms.with_user(self.users['manager']).action_verify_terms('Independent exact terms checked')
        s=self._run(batch);row=self._one(s)
        self.assertEqual(tuple(D(row[k]) for k in ('reserved','free_stock','incoming','protected_incoming','new_procurement')),(20,60,40,40,80));self._check(s)
        _logger.info('PR10_REFERENCE_B demand=200 included_reserved=20 free=60 protected_incoming=40 new=80')

    def test_reservation_is_not_reassigned_to_earlier_other_order(self):
        self._quant(100);a,al=self._sale(80,date='2026-11-02 10:00:00');b,bl=self._sale(70)
        self._reservation(bl,70);s=self._run()
        self.assertEqual(D(self._one(s,al).free_stock),30);self.assertEqual(D(self._one(s,bl).reserved),70)
        self.assertEqual(D(self._one(s,al).new_procurement),50);self._check(s)

    def test_unattributed_quant_reservation_is_unresolved_not_new(self):
        self._quant(80,20);self._sale(200);self._po(qty=40);s=self._run();row=self._one(s)
        self.assertEqual((D(row.free_stock),D(row.incoming),D(row.unresolved),D(row.new_procurement)),(60,40,20,80))
        self.assertIn('RESERVATION_LINEAGE_UNKNOWN',s.issue_ids.mapped('code'));self._check(s)

    def test_same_quant_reservations_for_two_lines_reconcile_once(self):
        self._quant(100);a,al=self._sale(80);b,bl=self._sale(70)
        self._reservation(al,30);self._reservation(bl,20);s=self._run()
        self.assertEqual(sum(D(r.reserved) for r in s.demand_ids),50)
        self.assertEqual(sum(D(r.free_stock) for r in s.demand_ids),50);self._check(s)

    def test_fractional_reservation(self):
        self._quant(1.25);so,line=self._sale(2.5);self._reservation(line,.4);s=self._run();row=self._one(s)
        self.assertEqual((D(row.reserved),D(row.free_stock),D(row.new_procurement)),(D('.4'),D('.85'),D('1.25')));self._check(s)


@tagged('post_install','-at_install')
class TestAllocationCapacity(AllocationFixtures,TransactionCase):
    def test_unknown_eta_withheld_as_uncertainty_not_definite_new(self):
        from ..models.supply_engine import SupplyEngine
        original=SupplyEngine.read
        def undated(reader,model,domain,names):
            result=original(reader,model,domain,names)
            if model=='stock.move':
                for row in result.values():
                    if row.get('purchase_line_id') and row.get('state') not in ('done','cancel'):row['date']=False
            return result
        self._sale(100);self._po(qty=40)
        # Simulate missing ETA at the approved source projection boundary without
        # corrupting required operational date fields or inventing a fallback.
        with patch.object(SupplyEngine,'read',undated):s=self._run()
        row=self._one(s);self.assertEqual((D(row.incoming),D(row.unresolved),D(row.new_procurement)),(0,40,60))
        self.assertIn('ARRIVAL_DATE_UNKNOWN',s.issue_ids.mapped('code'));self._check(s)

    def test_mixed_due_dates_share_late_capacity_only_when_timely(self):
        self._quant(10);a,al=self._sale(50,date='2026-11-01 10:00:00');b,bl=self._sale(50)
        self._po(qty=40);s=self._run()
        self.assertEqual((D(self._one(s,al).free_stock),D(self._one(s,al).incoming)),(10,0))
        self.assertEqual(D(self._one(s,bl).incoming),40);self._check(s)

    def test_equal_dates_and_confirmation_times_use_stable_source_id(self):
        self._quant(100);a,al=self._sale(80);b,bl=self._sale(70)
        (a|b).date_order='2026-10-28 10:00:00';s=self._run()
        self.assertEqual(D(self._one(s,al).free_stock),80);self.assertEqual(D(self._one(s,bl).free_stock),20)

    def test_reference_C_80_and70_compete_for100_new50(self):
        self._quant(100);a,al=self._sale(80,date='2026-11-02 10:00:00');b,bl=self._sale(70)
        s=self._run();self.assertEqual((D(self._one(s,al).free_stock),D(self._one(s,bl).free_stock)),(80,20))
        self.assertEqual(D(self._one(s,bl).new_procurement),50);self._check(s)
        _logger.info('PR10_REFERENCE_C demands=80,70 free_allocations=80,20 capacity=100 new=50')

    def test_multiple_same_product_lines_preserve_exact_identity(self):
        self._quant(100);a,al=self._sale(40);a.order_line=[Command.create({'product_id':self.red.id,'product_uom_qty':30,'product_uom_id':self.unit.id,'price_unit':150})]
        self._sale(50);s=self._run();self.assertEqual(len(s.demand_ids),3)
        self.assertEqual(sum(D(r.free_stock) for r in s.demand_ids),100);self.assertEqual(sum(D(r.new_procurement) for r in s.demand_ids),20);self._check(s)

    def test_warehouse_B_not_instant_supply_for_A(self):
        self._quant(100,wh=self.wh2);self._sale(80);s=self._run(warehouses=self.wh|self.wh2)
        self.assertEqual(D(self._one(s).free_stock),0);self.assertEqual(D(self._one(s).new_procurement),80)

    def test_quality_input_not_free(self):
        self.wh.reception_steps='two_steps';self._classify(self.wh,self.wh.wh_input_stock_loc_id,'receiving')
        self._quant(100,location=self.wh.wh_input_stock_loc_id);self._sale(80);s=self._run()
        self.assertEqual(D(self._one(s).free_stock),0);self.assertEqual(D(self._one(s).new_procurement),80)

    def test_late_incoming_not_on_time_coverage(self):
        self._sale(200);po,line=self._po(qty=40);po.picking_ids.move_ids.date='2026-11-10 10:00:00'
        s=self._run();row=self._one(s);self.assertEqual(D(row.incoming),0);self.assertEqual(D(row.new_procurement),200)
        self.assertIn('ARRIVAL_AFTER_REQUIRED_DATE',s.issue_ids.mapped('code'))

    def test_partial_receipt_input40_incoming60_only(self):
        self.wh.reception_steps='two_steps';self._classify(self.wh,self.wh.wh_input_stock_loc_id,'receiving')
        self.env[POLICY].create({'company_id':self.a.id,'allow_receiving_buffer':True,'receiving_buffer_hours':24,
            'reason':'Documented same-warehouse Input-to-stock planning time for the synthetic receipt workflow'})
        self._sale(100);po,line=self._po();self._receive(po,40)
        s=self._run();row=self._one(s);self.assertEqual((D(row.free_stock),D(row.incoming),D(row.new_procurement)),(0,60,40));self._check(s)

    def test_incoming_competes_only_once(self):
        self._sale(80,date='2026-11-04 10:00:00');self._sale(70);self._po(qty=100);s=self._run()
        self.assertEqual(sum(D(r.incoming) for r in s.demand_ids),100);self.assertEqual(sum(D(r.new_procurement) for r in s.demand_ids),50);self._check(s)

    def test_input_arrival_without_putaway_timing_is_unresolved(self):
        self.wh.reception_steps='two_steps';self._classify(self.wh,self.wh.wh_input_stock_loc_id,'receiving')
        self._sale(100);po,line=self._po();self._receive(po,40)
        s=self._run();row=self._one(s)
        self.assertEqual((D(row.incoming),D(row.unresolved),D(row.new_procurement)),(0,60,40))
        self.assertIn('SALEABLE_AVAILABILITY_UNVERIFIED',s.issue_ids.mapped('code'));self._check(s)

    def test_receiving_buffer_can_make_incoming_late(self):
        self.wh.reception_steps='two_steps';self._classify(self.wh,self.wh.wh_input_stock_loc_id,'receiving')
        self.env[POLICY].create({'company_id':self.a.id,'allow_receiving_buffer':True,'receiving_buffer_hours':120,
            'reason':'Documented five-day Input-to-stock processing time'})
        self._sale(40);self._po(qty=40);s=self._run()
        self.assertEqual(D(s.demand_ids.incoming),0);self.assertEqual(D(s.demand_ids.new_procurement),40)
        self.assertIn('ARRIVAL_AFTER_REQUIRED_DATE',s.issue_ids.mapped('code'))

    def test_quality_receipt_never_gets_automatic_clearance_from_buffer(self):
        self.wh.reception_steps='three_steps';self._classify(self.wh,self.wh.wh_qc_stock_loc_id,'quality')
        self.env[POLICY].create({'company_id':self.a.id,'allow_receiving_buffer':True,'receiving_buffer_hours':0,
            'reason':'Input buffer is not a quality release authorization'})
        self._sale(40);po,line=self._po(qty=40);po.picking_ids.move_ids.location_dest_id=self.wh.wh_qc_stock_loc_id
        s=self._run();self.assertEqual(D(s.demand_ids.incoming),0);self.assertEqual(D(s.demand_ids.unresolved),40)

    def test_receiving_policy_rejects_invalid_delay(self):
        for hours in (-1,745):
            with self.assertRaises(ValidationError),self.env.cr.savepoint():
                self.env[POLICY].create({'company_id':self.a.id,'allow_receiving_buffer':True,'receiving_buffer_hours':hours,'reason':'Invalid planning interval fixture'})

    def test_mto_direct_owner_precedes_other_earlier_demand(self):
        a,al=self._sale(80,date='2026-11-04 10:00:00');b,bl=self._sale(70);po,line=self._po(qty=70)
        po.picking_ids.move_ids.move_dest_ids=[Command.link(bl.move_ids.id)]
        s=self._run();self.assertEqual(D(self._one(s,al).incoming),0);self.assertEqual(D(self._one(s,bl).incoming),70);self._check(s)

    def test_mto_link_to_excluded_order_not_general_incoming(self):
        a,al=self._sale(80);b,bl=self._sale(70);po,line=self._po(qty=70)
        po.picking_ids.move_ids.move_dest_ids=[Command.link(bl.move_ids.id)]
        s=self._run(confirmed=a.ids);self.assertEqual(D(self._one(s).incoming),0);self.assertEqual(D(self._one(s).new_procurement),80)

    def test_ambiguous_procurement_multiple_owners_requires_review(self):
        a,al=self._sale(80);b,bl=self._sale(70);po,line=self._po(qty=100)
        po.picking_ids.move_ids.move_dest_ids=[Command.set((al.move_ids|bl.move_ids).ids)]
        s=self._run();self.assertEqual(sum(D(r.incoming) for r in s.demand_ids),0)
        self.assertEqual(sum(D(r.unresolved) for r in s.demand_ids),100);self._check(s)

    def test_unverified_price_does_not_prevent_known_quantity_coverage(self):
        self._sale(40);self._po(qty=40);s=self._run();row=self._one(s)
        self.assertEqual(D(row.incoming),40);self.assertEqual(D(row.protected_incoming),0)
        self.assertIn('incoming_cost_unverified',s.entry_ids.mapped('allocation_type'))

    def test_priority_policy_reorders_free_allocation_with_audit(self):
        self._quant(100);first,fl=self._sale(80,date='2026-11-10 10:00:00');second,sl=self._sale(70)
        first.date_order='2026-10-27 10:00:00';second.date_order='2026-10-28 10:00:00'
        batch=self._ready();s=self._run(batch);self.assertEqual(D(self._one(s,sl).free_stock),70)
        policy=self.env[POLICY].create({'company_id':self.a.id,'priority':'confirmation','reason':'Confirmed commitments first by recorded confirmation time'})
        changed=self._run(batch);self.assertEqual(D(self._one(changed,fl).free_stock),80);self.assertEqual(changed.version,2)
        with self.assertRaises(AccessError):policy.with_user(self.users['purchase']).write({'priority':'required_date','reason':'forged'})


@tagged('post_install','-at_install')
class TestQuotationAllocation(AllocationFixtures,TransactionCase):
    def test_sent_quote_is_conditional_and_cancelled_quote_rejected(self):
        quote,line=self._sale(70,False);quote.state='sent';batch=self._ready();s=self._run(batch,quotes=quote.ids)
        self.assertEqual(s.demand_ids.demand_type,'conditional');quote.action_cancel()
        with self.assertRaises(AccessError):self._run(batch,quotes=quote.ids)

    def test_quote_cannot_be_explicit_confirmed_and_conditional(self):
        quote,_=self._sale(70,False)
        with self.assertRaises(ValidationError):self._run(confirmed=quote.ids,quotes=quote.ids)

    def test_reference_D_200_committed_plus70_quote_separate(self):
        self._quant(60);self._sale(200);quote,ql=self._sale(70,False);po,pl=self._po(qty=40);batch=self._ready()
        terms=batch.action_propose_supply_terms(self.wh.id,pl.id,'firm','Signed protected incoming for conditional reference')
        terms.with_user(self.users['manager']).action_verify_terms('Independent firm contract review')
        base=self._run(batch);scenario=self._run(batch,quotes=quote.ids)
        self.assertEqual(sum(D(r.outstanding) for r in base.demand_ids),200)
        self.assertEqual(sum(D(r.outstanding) for r in scenario.demand_ids),270)
        self.assertEqual(D(self._one(scenario,ql).new_procurement),70)
        self.assertEqual(D(base.demand_ids.new_procurement),100)
        self.assertEqual(sum(D(r.new_procurement) for r in scenario.demand_ids),170)
        self.assertEqual(scenario.baseline_id,base);self.assertEqual(len(base.demand_ids),1);self._check(scenario)
        _logger.info('PR10_REFERENCE_D committed=200 baseline_new=100 scenario_with_quote=270 scenario_new=170 conditional_new=70')

    def test_standalone_quotes_are_alternatives_not_additive(self):
        self._quant(100);a,al=self._sale(100,False);b,bl=self._sale(100,False);batch=self._ready()
        sa=self._run(batch,quotes=a.ids);sb=self._run(batch,quotes=b.ids)
        self.assertEqual(D(self._one(sa).free_stock),100);self.assertEqual(D(self._one(sb).free_stock),100)
        self.assertNotEqual(sa,sb);self.assertEqual(sa.baseline_id,sb.baseline_id)

    def test_explicit_portfolio_shares_pool_once_and_deduplicates(self):
        self._quant(100);a,al=self._sale(100,False);b,bl=self._sale(100,False);s=self._run(quotes=[a.id,b.id,a.id],reason='Two independent opportunities, explicitly selected together')
        self.assertEqual(s.scenario,'quotation_portfolio');self.assertEqual(len(s.demand_ids),2)
        self.assertEqual(sum(D(r.free_stock) for r in s.demand_ids),100);self.assertEqual(sum(D(r.new_procurement) for r in s.demand_ids),100);self._check(s)

    def test_portfolio_requires_explicit_reason(self):
        a,_=self._sale(10,False);b,_=self._sale(10,False)
        with self.assertRaises(ValidationError):self._run(quotes=[a.id,b.id])

    def test_quote_conversion_stales_old_scenario_and_enters_baseline_once(self):
        quote,line=self._sale(70,False);batch=self._ready();s=self._run(batch,quotes=quote.ids)
        quote.action_confirm();batch.action_collect_supply(self.wh.ids)
        with self.assertRaises((AccessError,UserError)):batch.get_current_allocation(self.wh.ids,quotation_ids=quote.ids)
        base=self._run(batch);self.assertEqual(len(base.demand_ids),1);self.assertEqual(base.demand_ids.demand_type,'confirmed')
        self.assertEqual(D(base.demand_ids.outstanding),70)

    def test_expired_quote_excluded_from_current_scenario(self):
        quote,_=self._sale(70,False);quote.validity_date='2026-01-01'
        with self.assertRaises(ValidationError):self._run(quotes=quote.ids)


@tagged('post_install','-at_install')
class TestAllocationIntegrity(AllocationFixtures,TransactionCase):
    def test_customer_required_date_and_po_eta_changes_make_result_stale(self):
        so,line=self._sale(100);po,pl=self._po(qty=40);batch=self._ready();s=self._run(batch)
        so.commitment_date='2026-11-01 10:00:00'
        with self.assertRaises(UserError):batch.get_current_allocation(self.wh.ids)
        later=self._run(batch);self.assertEqual(D(later.demand_ids.incoming),0)
        po.picking_ids.move_ids.date='2026-10-31 10:00:00'
        with self.assertRaises(UserError):batch.get_current_allocation(self.wh.ids)
        self.assertEqual(D(self._run(batch).demand_ids.incoming),40)

    def test_cancelled_so_removed_from_current_baseline(self):
        so,line=self._sale(100);batch=self._ready();s=self._run(batch);so.action_cancel()
        batch.action_collect_supply(self.wh.ids)
        with self.assertRaises(UserError):batch.get_current_allocation(self.wh.ids)
        self.assertFalse(self._run(batch).demand_ids)

    def test_policy_change_requires_new_current_version(self):
        self._sale(100);batch=self._ready();s=self._run(batch)
        policy=self.env[POLICY].create({'company_id':self.a.id,'reason':'Explicit priority','priority':'confirmation'})
        with self.assertRaises(UserError):batch.get_current_allocation(self.wh.ids)
        new=self._run(batch);self.assertEqual(new.version,2)
        policy.write({'priority':'required_date','reason':'Reviewed date-first priority'})
        self.assertEqual(policy.version,2)
        with self.assertRaises(UserError):batch.get_current_allocation(self.wh.ids)

    def test_idempotency_retains_one_snapshot_and_consumption(self):
        self._quant(100);self._sale(200);batch=self._ready();s=self._run(batch)
        self.assertEqual(self._run(batch),s);self.assertEqual(batch.get_current_allocation(self.wh.ids),s)
        self.assertEqual(len(batch.allocation_snapshot_ids),1);self._check(s)

    def test_quantity_change_stales_and_versions_without_erasing_old_ledger(self):
        so,line=self._sale(100);batch=self._ready();s=self._run(batch);old=s.demand_ids.read(['outstanding','new_procurement'])
        line.product_uom_qty=120;batch.action_collect_supply(self.wh.ids)
        with self.assertRaises(UserError):batch.get_current_allocation(self.wh.ids)
        new=self._run(batch);self.assertEqual(new.version,2);self.assertEqual(new.previous_id,s)
        self.assertEqual(s.demand_ids.read(['outstanding','new_procurement']),old)

    def test_note_only_change_is_not_stale(self):
        so,line=self._sale(100);batch=self._ready();s=self._run(batch);so.note='Administrative note only'
        self.assertEqual(batch.get_current_allocation(self.wh.ids),s)

    def test_reservation_change_requires_current_supply_and_allocation_refresh(self):
        self._quant(80);so,line=self._sale(100);batch=self._ready();s=self._run(batch);self._reservation(line,20)
        with self.assertRaises(UserError):batch.get_current_allocation(self.wh.ids)
        refreshed=self._run(batch);self.assertEqual(D(refreshed.demand_ids.reserved),20);self.assertEqual(refreshed.version,2)

    def test_failure_rolls_back_entire_new_evidence(self):
        self._sale(100);batch=self._ready();batch.action_collect_supply(self.wh.ids)
        with patch.object(type(self.env[LEDGER]),'_record',side_effect=ValidationError('forced ledger publication failure')):
            with self.assertRaises(ValidationError):batch.action_run_allocation(self.wh.ids)
        self.assertFalse(self.env[HEADER].search([('batch_id','=',batch.id)]))

    def test_all_records_immutable_with_forged_context(self):
        self._sale(100);s=self._run()
        for rec in (s,s.demand_ids,s.entry_ids):
            with self.assertRaises(AccessError):rec.with_context(allow_verified=True).write({})
            with self.assertRaises(AccessError):rec.unlink()
            with self.assertRaises(AccessError):rec.copy()
        with self.assertRaises(AccessError):self.env[HEADER].create({'batch_id':s.batch_id.id})

    def test_operational_models_exactly_unchanged_by_analysis(self):
        self._quant(80);so,line=self._sale(200);self._reservation(line,20);po,pl=self._po(qty=40);batch=self._ready();batch.action_collect_supply(self.wh.ids)
        models={'sale.order':['state','write_date'],'sale.order.line':['product_uom_qty','price_unit','qty_delivered','write_date'],
            'stock.quant':['quantity','reserved_quantity','write_date'],'stock.move':['state','quantity','product_uom_qty','value','remaining_value','write_date'],
            'stock.move.line':['quantity','write_date'],'stock.picking':['state','write_date'],
            'purchase.order':['state','write_date'],'purchase.order.line':['price_unit','product_qty','write_date'],
            'product.supplierinfo':['price','write_date'],'product.product':['standard_price','write_date'],
            'account.move':['state','write_date'],'account.move.line':['balance','write_date']}
        def values():return {m:self.env[m].search([],order='id').read(fs,load=None) for m,fs in models.items()}
        before=values();s=batch.action_run_allocation(self.wh.ids);batch.get_current_allocation(self.wh.ids)
        self.assertEqual(values(),before);self._check(s)


@tagged('post_install','-at_install')
class TestAllocationSecurity(AllocationFixtures,TransactionCase):
    def test_transfer_alternative_is_excluded_without_route_and_timing_policy(self):
        self._quant(100,wh=self.wh2);so,line=self._sale(80)
        s=self._run(warehouses=self.wh|self.wh2)
        self.assertEqual(D(s.demand_ids.free_stock),0)
        self.assertEqual(D(s.demand_ids.new_procurement),80)
        self.assertTrue(all(cap['warehouse_id']==self.wh2.id for cap in s.source_capacities.values()))

    def test_supply_grant_without_demand_permission_cannot_collect_or_read(self):
        self._sale(100);batch=self._ready();s=self._run(batch)
        grant=self.env[GRANT].search([('user_id','=',self.users['purchase'].id)])
        grant.write({'allow_demand':False,'reason':'Supply permission only; sales-demand scope revoked'})
        with self.assertRaises(AccessError):batch.action_run_allocation(self.wh.ids)
        with self.assertRaises(AccessError):s.read(['provenance'])

    def test_other_company_warehouse_and_role_denials(self):
        self._sale(100);batch=self._ready();s=self._run(batch)
        for role in ('sales','configuration','portal','purchase_b','other'):
            with self.subTest(role=role),self.assertRaises(AccessError):s.with_user(self.users[role]).read(['totals'])
        with self.assertRaises(AccessError):batch.action_run_allocation(self.wh_b.ids)

    def test_auditor_read_only_cost_scope_and_export(self):
        self._sale(100);batch=self._ready();s=self._run(batch)
        self.users['auditor'].group_ids=[Command.link(self.env.ref('base.group_allow_export').id)]
        self.assertTrue(s.with_user(self.users['auditor']).export_data(['totals']))
        with self.assertRaises(AccessError):batch.with_user(self.users['auditor']).action_run_allocation(self.wh.ids)
        grant=self.env[GRANT].search([('user_id','=',self.users['auditor'].id)])
        grant.write({'allow_cost':False,'reason':'Quantity-only review'})
        with self.assertRaises(AccessError):s.with_user(self.users['auditor']).export_data(['provenance'])

    def test_mixed_warehouses_require_every_scope_for_children_and_grouped_read(self):
        self._sale(100);s=self._run(warehouses=self.wh|self.wh2)
        grant=self.env[GRANT].search([('user_id','=',self.users['auditor'].id)])
        grant.write({'warehouse_ids':[Command.set(self.wh.ids)],'reason':'Only A approved'})
        with self.assertRaises(AccessError):s.demand_ids.with_user(self.users['auditor']).read(['outstanding'])
        self.assertFalse(self.env[HEADER].with_user(self.users['auditor'])._read_group([('id','=',s.id)],[],['__count'])[0][0])

    def test_quantity_only_has_no_selling_or_vendor_price_projection(self):
        self._sale(100);self._po(qty=40);s=self._run(costs=False)
        encoded=str(s.provenance)
        self.assertNotIn('price_unit',encoded);self.assertNotIn('standard_price',encoded)
        self.assertEqual(D(self._one(s).protected_incoming),0)

    def test_foreign_explicit_order_ids_cannot_enter_projection(self):
        self._sale(100);foreign,line=self._sale(50,wh=self.wh2)
        with self.assertRaises(AccessError):self._run(confirmed=foreign.ids)

    def test_native_sales_drilldown_does_not_elevate(self):
        self._sale(100);s=self._run()
        with self.assertRaises(AccessError):s.demand_ids.action_open_source()

    def test_scope_combinations_and_nested_commands_cannot_forge_or_cross_company(self):
        self._sale(100);batch=self._ready();s=self._run(batch)
        user=self.users['sales'];user.group_ids=[Command.link(self.env.ref(MODULE+'.group_vpr_auditor').id)]
        with self.assertRaises(AccessError):s.with_user(user).with_context(allowed_company_ids=self.b.ids).read(['totals'])
        with self.assertRaises(AccessError):s.write({'demand_ids':[Command.create({'sale_line_id':999,'company_id':self.b.id})]})
        with self.assertRaises(AccessError):self.users['purchase'].write({'vpr_allocation_warehouse_ids':[Command.set(self.wh_b.ids)]})

    def test_graph_to_unselected_internal_warehouse_does_not_publish_evidence(self):
        a,al=self._sale(100);b,bl=self._sale(70,wh=self.wh2);po,line=self._po(qty=70)
        po.picking_ids.move_ids.move_dest_ids=[Command.link(bl.move_ids.id)]
        batch=self._ready();batch.action_collect_supply(self.wh.ids)
        with self.assertRaises(AccessError):batch.action_run_allocation(self.wh.ids,confirmed_order_ids=a.ids)
        self.assertFalse(self.env[HEADER].search([('batch_id','=',batch.id)]))

    def test_wizard_authorized_preview_and_source_ids_without_native_sales_grant(self):
        so,line=self._sale(100);quote,ql=self._sale(70,False);batch=self._ready();batch.action_collect_supply(self.wh.ids)
        wizard=self.env['vendor.price.revision.allocation.wizard'].with_user(self.users['purchase']).create({
            'batch_id':batch.id,'warehouse_ids':[Command.set(self.wh.ids)],'quotation_ids':str(quote.id)})
        wizard.action_preview_sources()
        self.assertEqual({v['id'] for v in wizard.candidate_sources},{so.id,quote.id})
        self.assertNotIn('price_unit',str(wizard.candidate_sources))
        action=wizard.action_run();self.assertEqual(action['res_model'],HEADER)
        self.assertEqual(self.env[HEADER].browse(action['res_id']).scenario,'single_quotation')


@tagged('post_install','-at_install')
class TestAllocationWorkload(AllocationFixtures,TransactionCase):
    def test_100_order_quantity_workload_bulk_projection(self):
        from ..models.supply_engine import SupplyEngine
        self._quant(100)
        sales=self.env['sale.order'].with_company(self.a).create([{'partner_id':self.customer.id,'company_id':self.a.id,
            'warehouse_id':self.wh.id,'pricelist_id':self.pricelist.id,'commitment_date':'2026-11-05 10:00:00',
            'order_line':[Command.create({'product_id':self.red.id,'product_uom_qty':2,'product_uom_id':self.unit.id,'price_unit':150,'tax_ids':[Command.clear()]})]} for n in range(100)])
        sales.action_confirm();batch=self._ready();batch.action_collect_supply(self.wh.ids)
        original=SupplyEngine.read;calls=[]
        def observed(reader,model,domain,names):
            calls.append(model);return original(reader,model,domain,names)
        start=time.perf_counter()
        with patch.object(SupplyEngine,'read',observed):snapshot=batch.action_run_allocation(self.wh.ids)
        elapsed=time.perf_counter()-start
        self.assertEqual(len(snapshot.demand_ids),100)
        self.assertEqual(sum(D(r.outstanding) for r in snapshot.demand_ids),200)
        self.assertEqual(sum(D(r.free_stock) for r in snapshot.demand_ids),100)
        self.assertEqual(sum(D(r.new_procurement) for r in snapshot.demand_ids),100)
        self.assertEqual(calls.count('sale.order.line'),1);self.assertEqual(calls.count('sale.order'),1)
        self.assertLessEqual(calls.count('stock.move'),4);self._check(snapshot)
        _logger.info('PR10_WORKLOAD orders=100 lines=100 demand=200 free=100 new=100 seconds=%.3f sales_line_bulk_reads=%s stock_move_bulk_reads=%s',elapsed,calls.count('sale.order.line'),calls.count('stock.move'))

