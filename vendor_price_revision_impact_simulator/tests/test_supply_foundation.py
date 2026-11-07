"""PR09 quantities/receipt boundaries/security. Operational writes are fixtures only."""
from decimal import Decimal as D
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from .test_commercial_validation import CommercialFixtures, MODULE
from ..models.supply_governance import GRANT, LOCATION, AUDIT
from ..models.supply_engine import SNAPSHOT, BUCKET, ISSUE, TERMS, SupplyEngine


class SupplyFixtures(CommercialFixtures):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.red.categ_id = cls.env['product.category'].with_company(cls.a).create({'name':'PR09 Explicit Cost Category', 'property_cost_method':'standard'})
        (cls.red | cls.white | cls.cable).is_storable = True
        cls.red.with_company(cls.a).standard_price = 90
        cls.wh = cls.env['stock.warehouse'].search([('company_id', '=', cls.a.id)], limit=1)
        cls.wh2 = cls.env['stock.warehouse'].create({'name': 'PR09 Warehouse B', 'code': 'P9B', 'company_id': cls.a.id})
        cls.wh3 = cls.env['stock.warehouse'].create({'name': 'PR09 Warehouse C', 'code': 'P9C', 'company_id': cls.a.id})
        cls.wh_b = cls.env['stock.warehouse'].search([('company_id', '=', cls.b.id)], limit=1)
        for role in ('purchase', 'manager', 'finance', 'auditor'):
            cls.env[GRANT].create({'company_id': cls.a.id, 'user_id': cls.users[role].id,
                'warehouse_ids': [Command.set((cls.wh | cls.wh2 | cls.wh3).ids)], 'allow_cost': True,
                'reason': 'Explicit narrowly scoped analytical access for PR09 fixture'})
        for wh in (cls.wh | cls.wh2 | cls.wh3):
            cls.env[LOCATION].create({'company_id': cls.a.id, 'warehouse_id': wh.id,
                'location_id': wh.lot_stock_id.id, 'classification': 'saleable', 'reason': 'Verified saleable exact location'})

    def _ready(self):
        self._rule(); batch = self._commercial_batch(); self._context(batch); self._validate(batch)
        return batch

    def _quant(self, qty, reserved=0, wh=None, location=None, **kwargs):
        return self.env['stock.quant'].create(dict(product_id=self.red.id,
            location_id=(location or (wh or self.wh).lot_stock_id).id, quantity=qty, reserved_quantity=reserved, **kwargs))

    def _collect(self, batch=None, warehouses=None, costs=True):
        return (batch or self._ready()).action_collect_supply((warehouses or self.wh).ids, costs)

    def _total(self, snapshot, wh=None):
        return snapshot.totals[str(self.red.id)+':'+str((wh or self.wh).id)]

    def _po(self, qty=100, price=100, wh=None, uom=None, **kwargs):
        wh = wh or self.wh
        po = self.env['purchase.order'].with_company(self.a).create(dict(partner_id=self.vendor.id,
            company_id=self.a.id, currency_id=self.inr.id, picking_type_id=wh.in_type_id.id,
            order_line=[Command.create({'product_id': self.red.id, 'product_qty': qty, 'uom_id': (uom or self.unit).id,
                'price_unit': price, 'tax_ids': [Command.clear()], 'date_planned': '2026-11-02 08:00:00'})], **kwargs))
        po.button_confirm()
        self.assertEqual(po.state, 'purchase')
        return po, po.order_line

    def _receive(self, po, qty, cancel=False):
        picking = po.picking_ids.filtered(lambda p: p.state not in ('done','cancel') and p.location_id.usage == 'supplier')[:1]
        for move in picking.move_ids:
            move.quantity = qty; move.picked = True
        picking.with_context(cancel_backorder=cancel)._action_done()
        return picking

    def _classify(self, wh, loc, role):
        return self.env[LOCATION].create({'company_id': self.a.id, 'warehouse_id': wh.id,
            'location_id': loc.id, 'classification': role, 'reason': 'Explicit receipt workflow classification'})


@tagged('post_install', '-at_install')
class TestSupplyQuantities(SupplyFixtures, TransactionCase):
    def test_fractional_stock_is_not_truncated(self):
        self._quant(1.25,.4);s=self._collect()
        self.assertEqual(D(self._total(s)['eligible_free']),D('.85'))

    def test_required_lot_missing_is_withheld(self):
        self.red.tracking='lot';self._quant(10);s=self._collect()
        self.assertEqual(D(self._total(s)['eligible_free']),0)
        self.assertIn('LOT_MISSING',s.issue_ids.mapped('code'))

    def test_lot_package_owner_identity_is_retained(self):
        self.red.tracking='lot'
        lot=self.env['stock.lot'].create({'name':'PR09 lot','product_id':self.red.id,'company_id':self.a.id})
        self._quant(10,lot_id=lot.id);s=self._collect()
        self.assertEqual(s.bucket_ids.evidence['quant']['lot_id'],lot.id)
        self.assertEqual(D(self._total(s)['eligible_free']),10)

    def test_untracked_product_has_no_fabricated_stock_zero(self):
        self.red.is_storable=False;s=self._collect()
        self.assertIsNone(self._total(s)['physical']);self.assertFalse(s.quantity_verified)

    def test_physical_100_reserved_30_free_70(self):
        self._quant(100,30); s=self._collect(); t=self._total(s)
        self.assertEqual((D(t['physical']),D(t['reserved']),D(t['eligible_free'])),(100,30,70))
        self.assertEqual(len(s.bucket_ids),1); self.assertTrue(s.quantity_verified)

    def test_multiwarehouse_free_70_40_0_total_110(self):
        self._quant(100,30); self._quant(50,10,wh=self.wh2); self._quant(20,20,wh=self.wh3)
        s=self._collect(warehouses=self.wh|self.wh2|self.wh3)
        self.assertEqual([D(self._total(s,w)['eligible_free']) for w in (self.wh,self.wh2,self.wh3)],[70,40,0])
        self.assertEqual(sum(D(t['eligible_free']) for t in s.totals.values()),110)

    def test_other_warehouse_and_company_not_in_scope(self):
        self._quant(80,20); self._quant(999,wh=self.wh2); self._quant(777,location=self.wh_b.lot_stock_id)
        s=self._collect(); self.assertEqual(D(self._total(s)['eligible_free']),60)
        self.assertNotIn('999',str(s.provenance)); self.assertNotIn('777',str(s.provenance))

    def test_owner_consignment_has_no_eligible_or_company_cost(self):
        self._quant(100,owner_id=self.vendor.id); s=self._collect(); b=s.bucket_ids
        self.assertEqual(b.kind,'consignment_excluded'); self.assertEqual(D(b.eligible_free),0)
        self.assertIsNone(b.evidence['cost']['unit_cost'])

    def test_unclassified_child_location_requires_review(self):
        loc=self.env['stock.location'].create({'name':'Unknown shelf','location_id':self.wh.lot_stock_id.id,'usage':'internal','company_id':self.a.id})
        self._quant(20,location=loc); s=self._collect()
        self.assertEqual(D(self._total(s)['eligible_free']),0); self.assertFalse(s.quantity_verified)
        self.assertIn('LOCATION_UNCLASSIFIED',s.issue_ids.mapped('code'))

    def test_negative_and_overreservation_retain_raw_evidence(self):
        self._quant(-5); self._quant(10,20); s=self._collect()
        self.assertFalse(s.quantity_verified); self.assertIsNone(self._total(s)['candidate_supply'])
        self.assertIn(D('-5'),[D(v) for v in s.bucket_ids.mapped('physical')]); self.assertEqual(D(self._total(s)['eligible_free']),0)

    def test_quality_staging_scrap_are_not_free(self):
        for name in ('quality','staging','excluded'):
            loc=self.env['stock.location'].create({'name':name,'location_id':self.wh.view_location_id.id,'usage':'internal','company_id':self.a.id})
            self._classify(self.wh,loc,name); self._quant(10,location=loc)
        s=self._collect(); self.assertEqual(D(self._total(s)['physical']),30); self.assertEqual(D(self._total(s)['eligible_free']),0)

    def test_internal_transfer_and_reservation_not_incremental_supply(self):
        self._quant(100)
        move=self.env['stock.move'].create({'product_id':self.red.id,'uom_id':self.unit.id,'product_uom_qty':30,
            'company_id':self.a.id,'location_id':self.wh.lot_stock_id.id,'location_dest_id':self.wh2.lot_stock_id.id})
        move._action_confirm();move._action_assign()
        s=self._collect(warehouses=self.wh|self.wh2)
        self.assertEqual(D(self._total(s)['reserved']),30);self.assertEqual(D(self._total(s)['eligible_free']),70)
        refs=s.bucket_ids.filtered(lambda b:b.kind=='internal_transfer_reference')
        self.assertEqual(len(refs),1);self.assertFalse(refs.contributes_quantity);self.assertEqual(D(refs.incoming),0)

    def test_standard_cost_is_reference_not_historical_acquisition(self):
        self._quant(10); b=self._collect().bucket_ids
        self.assertEqual(b.cost_basis,'standard_accounting_reference')
        self.assertEqual(D(b.evidence['cost']['unit_cost']),90)
        self.assertFalse(b.evidence['cost']['exact_acquisition_cost'])

    def test_fifo_does_not_invent_quant_location_layer_cost(self):
        self.red.categ_id.with_company(self.a).property_cost_method='fifo'
        self._quant(10);s=self._collect();b=s.bucket_ids
        self.assertEqual(b.cost_basis,'fifo');self.assertIsNone(b.evidence['cost']['unit_cost'])
        self.assertEqual(D(self._total(s)['eligible_free']),10)

    def test_avco_is_company_reference(self):
        self.red.categ_id.with_company(self.a).property_cost_method='average'
        self.red.with_company(self.a).standard_price=90
        self._quant(10);s=self._collect();self.assertEqual(s.bucket_ids.cost_basis,'company_avco_reference')

    def test_zero_cost_is_unavailable_without_zero_price_attestation(self):
        self.red.with_company(self.a).standard_price=0;self._quant(10);s=self._collect()
        self.assertIsNone(s.bucket_ids.evidence['cost']['unit_cost']);self.assertEqual(s.cost_state,'incomplete')


@tagged('post_install', '-at_install')
class TestSupplyReceipts(SupplyFixtures, TransactionCase):
    def test_reinterpreted_po_units_invalidate_firm_terms_after_commercial_refresh(self):
        po,line=self._po(qty=4,price=1000,uom=self.box);batch=self._ready()
        terms=batch.action_propose_supply_terms(self.wh.id,line.id,'firm','Supplier contract explicitly uses original box size')
        terms.with_user(self.users['manager']).action_verify_terms('Original box definition and fixed price checked')
        self.assertEqual(D(self._total(self._collect(batch))['protected']),40)
        self.box.relative_factor=12
        with self.assertRaises(UserError):batch.get_current_supply(self.wh.ids)
        self._context(batch);self._validate(batch)
        refreshed=self._collect(batch)
        self.assertEqual(D(self._total(refreshed)['protected']),0)
        self.assertFalse(refreshed.bucket_ids.evidence['cost']['firm_verified'])
        self.assertEqual(terms.state,'verified')  # retained history; current validity is separate

    def test_rfq_is_not_confirmed_supply(self):
        po=self.env['purchase.order'].with_company(self.a).create({'partner_id':self.vendor.id,'company_id':self.a.id,
            'picking_type_id':self.wh.in_type_id.id,'order_line':[Command.create({'product_id':self.red.id,
                'product_qty':40,'uom_id':self.unit.id,'price_unit':100,'date_planned':'2026-11-02 08:00:00'})]})
        self.assertEqual(po.state,'draft');s=self._collect()
        self.assertEqual(D(self._total(s)['incoming']),0);self.assertFalse(s.bucket_ids)

    def test_dropship_is_not_warehouse_supply(self):
        po,line=self._po(qty=40)
        po.picking_ids.move_ids.location_dest_id=self.env.ref('stock.stock_location_customers')
        s=self._collect();self.assertIsNone(self._total(s)['incoming'])
        self.assertIn('DROPSHIP_EXCLUDED',s.issue_ids.mapped('code'))

    def test_unsupported_return_replacement_chain_requires_review(self):
        po,line=self._po(qty=40)
        original=po.picking_ids.move_ids
        ret=original.copy({'location_id':self.wh.lot_stock_id.id,
            'location_dest_id':self.env.ref('stock.stock_location_suppliers').id,'state':'cancel'})
        original.origin_returned_move_id=ret
        s=self._collect();self.assertIsNone(self._total(s)['incoming'])
        self.assertIn('REPLACEMENT_CHAIN_REVIEW',s.issue_ids.mapped('code'))

    def test_purchase_box_uom_normalizes_quantity_and_inverse_price(self):
        self._po(qty=4,price=1000,uom=self.box);s=self._collect()
        self.assertEqual(D(self._total(s)['incoming']),40)
        self.assertEqual(D(s.bucket_ids.evidence['cost']['unit_cost']),100)

    def test_cancelled_po_has_no_active_incoming(self):
        po,line=self._po(qty=40);po.button_cancel();s=self._collect()
        self.assertEqual(D(self._total(s)['incoming']),0)

    def test_disputed_and_pending_amendment_are_not_protected(self):
        po,line=self._po(qty=40);batch=self._ready()
        for classification in ('disputed','amendment_pending'):
            terms=batch.action_propose_supply_terms(self.wh.id,line.id,classification,'Supplier terms require review')
            terms.with_user(self.users['manager']).action_verify_terms('Classification independently checked')
            s=self._collect(batch);self.assertEqual(D(self._total(s)['protected']),0)

    def test_confirmed_not_automatically_protected(self):
        po,line=self._po(qty=40);self._quant(80,20);s=self._collect();t=self._total(s)
        self.assertEqual((D(t['eligible_free']),D(t['incoming']),D(t['protected']),D(t['candidate_supply'])),(60,40,0,100))
        self.assertEqual(D(s.bucket_ids.filtered(lambda b:b.kind=='incoming_purchase').evidence['cost']['unit_cost']),100)

    def test_reference_60_free_40_verified_firm_candidate_100(self):
        po,line=self._po(qty=40);self._quant(80,20);batch=self._ready()
        terms=batch.action_propose_supply_terms(self.wh.id,line.id,'firm','Signed fixed-price supplier contract, no amendment')
        with self.assertRaises(AccessError):terms.action_verify_terms('ordinary preparer cannot verify')
        terms.with_user(self.users['manager']).action_verify_terms('Independent supplier contract verification')
        s=self._collect(batch);t=self._total(s)
        self.assertEqual((D(t['eligible_free']),D(t['protected']),D(t['candidate_supply'])),(60,40,100))
        self.assertNotIn('exposure',s.totals);self.assertNotIn('allocation',s.totals)

    def test_partial_receipt_backorder_only_supplier_unreceived(self):
        po,line=self._po();self._receive(po,40);s=self._collect();t=self._total(s)
        self.assertEqual((D(t['physical']),D(t['incoming'])),(40,60))
        self.assertEqual(len(s.bucket_ids.filtered(lambda b:b.kind=='incoming_purchase')),1)

    def test_two_step_received_input_40_pending_putaway_not_double_counted(self):
        self.wh.reception_steps='two_steps';self._classify(self.wh,self.wh.wh_input_stock_loc_id,'receiving')
        po,line=self._po();self._receive(po,40);s=self._collect();t=self._total(s)
        self.assertEqual((D(t['physical']),D(t['eligible_free']),D(t['incoming'])),(40,0,60))
        self.assertEqual(sum(D(b.incoming or '0') for b in s.bucket_ids),60)
        self.assertIn('received_pending_putaway',s.bucket_ids.mapped('kind'))

    def test_three_step_quality_is_received_not_supplier_incoming(self):
        self.wh.reception_steps='three_steps'
        self._classify(self.wh,self.wh.wh_input_stock_loc_id,'receiving');self._classify(self.wh,self.wh.wh_qc_stock_loc_id,'quality')
        po,line=self._po();self._receive(po,100);s=self._collect();t=self._total(s)
        self.assertEqual((D(t['physical']),D(t['eligible_free']),D(t['incoming'])),(100,0,0))

    def test_cancelled_backorder_not_incoming(self):
        po,line=self._po();self._receive(po,40,cancel=True);s=self._collect()
        self.assertEqual(D(self._total(s)['incoming']),0)
        b=s.bucket_ids.filtered(lambda b:b.kind=='incoming_purchase')
        self.assertEqual(D(b.evidence['cancelled']),60)

    def test_return_does_not_invent_replacement_incoming(self):
        po,line=self._po();picking=self._receive(po,100);original=picking.move_ids
        ret=self.env['stock.move'].create({'product_id':self.red.id,'uom_id':self.unit.id,'product_uom_qty':20,
            'quantity':20,'picked':True,'company_id':self.a.id,'location_id':self.wh.lot_stock_id.id,
            'location_dest_id':self.env.ref('stock.stock_location_suppliers').id,'purchase_line_id':line.id,
            'origin_returned_move_id':original.id,'to_refund':True})
        ret._action_confirm();ret._action_done();s=self._collect()
        self.assertEqual(D(self._total(s)['incoming']),0);self.assertEqual(D(self._total(s)['physical']),80)

    def test_duplicate_receipt_requirement_is_unknown_not_capped(self):
        po,line=self._po();move=po.picking_ids.move_ids
        move.copy({'picking_id':move.picking_id.id,'state':'confirmed'})
        s=self._collect();self.assertIsNone(self._total(s)['incoming'])
        self.assertIn('RECEIPT_RECONCILIATION_REQUIRED',s.issue_ids.mapped('code'))

    def test_po_terms_change_invalidates_firm_verification(self):
        po,line=self._po(qty=40);batch=self._ready()
        terms=batch.action_propose_supply_terms(self.wh.id,line.id,'firm','Supplier firm evidence')
        terms.with_user(self.users['manager']).action_verify_terms('Independent check')
        s=self._collect(batch);self.assertEqual(D(self._total(s)['protected']),40)
        line.price_unit=105
        with self.assertRaises(UserError):batch.get_current_supply(self.wh.ids)
        new=self._collect(batch);self.assertEqual(D(self._total(new)['protected']),0)

    def test_missing_foreign_currency_fx_keeps_quantity(self):
        po,line=self._po(qty=40);po.currency_id=self.eur
        s=self._collect();self.assertEqual(D(self._total(s)['incoming']),40)
        self.assertIsNone(s.bucket_ids.evidence['cost']['unit_cost'])
        self.assertIn('FX_DATE_UNSUPPORTED',s.issue_ids.mapped('code'))


@tagged('post_install', '-at_install')
class TestSupplyIntegrity(SupplyFixtures, TransactionCase):
    def test_unchanged_collection_is_idempotent(self):
        batch=self._ready();self._quant(10);s=self._collect(batch)
        self.assertEqual(self._collect(batch),s);self.assertEqual(batch.get_current_supply(self.wh.ids),s)

    def test_material_quant_reservation_change_versions_and_retains_history(self):
        batch=self._ready();q=self._quant(100,30);s=self._collect(batch);old=s.read(['totals','provenance'])
        q.reserved_quantity=40
        with self.assertRaises(UserError):batch.get_current_supply(self.wh.ids)
        new=self._collect(batch);self.assertEqual(new.version,2);self.assertEqual(new.previous_id,s)
        self.assertEqual(s.read(['totals','provenance']),old);self.assertEqual(D(self._total(new)['eligible_free']),60)

    def test_note_only_po_edit_is_not_material(self):
        po,line=self._po();batch=self._ready();s=self._collect(batch);po.note='Purely administrative note'
        self.assertEqual(batch.get_current_supply(self.wh.ids),s)

    def test_location_policy_change_is_stale(self):
        batch=self._ready();self._quant(20);s=self._collect(batch)
        policy=self.env[LOCATION].search([('location_id','=',self.wh.lot_stock_id.id)])
        policy.write({'classification':'staging','reason':'Stock under inspection'})
        with self.assertRaises(UserError):batch.get_current_supply(self.wh.ids)
        self.assertEqual(D(self._total(self._collect(batch))['eligible_free']),0)

    def test_source_relocation_is_stale(self):
        batch=self._ready();q=self._quant(20);s=self._collect(batch);q.location_id=self.wh2.lot_stock_id
        with self.assertRaises(UserError):batch.get_current_supply(self.wh.ids)

    def test_immutable_direct_rpc_context_and_nested_paths(self):
        batch=self._ready();self._quant(20);s=self._collect(batch)
        for record in (s,s.bucket_ids):
            with self.assertRaises(AccessError):record.write({'quantity_verified':True})
            with self.assertRaises(AccessError):record.unlink()
            with self.assertRaises(AccessError):record.copy()
        with self.assertRaises(AccessError):self.env[SNAPSHOT].with_user(self.users['purchase']).create({'batch_id':batch.id})

    def test_atomic_failure_does_not_leave_partial_header(self):
        batch=self._ready();self._quant(10)
        with patch.object(type(self.env[BUCKET]),'_record',side_effect=ValidationError('forced app evidence failure')):
            with self.assertRaises(ValidationError):self._collect(batch)
        self.assertFalse(self.env[SNAPSHOT].search([('batch_id','=',batch.id)]))

    def test_source_limit_fails_closed(self):
        batch=self._ready()
        with patch('odoo.addons.'+MODULE+'.models.supply_engine.LIMIT',0):
            with self.assertRaises(UserError):self._collect(batch)
        self.assertFalse(self.env[SNAPSHOT].search([('batch_id','=',batch.id)]))


@tagged('post_install', '-at_install')
class TestSupplySecurity(SupplyFixtures, TransactionCase):
    def test_redirected_receipt_cannot_disclose_unselected_warehouse_evidence(self):
        batch=self._ready();po,line=self._po(qty=40)
        po.picking_ids.move_ids.location_dest_id=self.wh2.lot_stock_id
        with self.assertRaises(AccessError):self._collect(batch)
        self.assertFalse(self.env[SNAPSHOT].search([('batch_id','=',batch.id)]))
        reviewed=self._collect(batch,warehouses=self.wh|self.wh2)
        self.assertFalse(reviewed.quantity_verified)
        self.assertIn('RECEIPT_SCOPE_UNCERTAIN',reviewed.issue_ids.mapped('code'))

    def test_purchase_manager_cannot_verify_own_terms_proposal(self):
        po,line=self._po(qty=40);batch=self._ready().with_user(self.users['manager'])
        terms=batch.action_propose_supply_terms(self.wh.id,line.id,'firm','Manager prepared supplier contract evidence')
        with self.assertRaises(ValidationError):terms.action_verify_terms('Self approval blocked')
        self.assertEqual(terms.state,'proposed')

    def test_foreign_company_warehouse_cannot_be_requested_even_with_forged_context(self):
        batch=self._ready()
        with self.assertRaises(AccessError):batch.with_context(allowed_company_ids=(self.a|self.b).ids).action_collect_supply(self.wh_b.ids)

    def test_no_grant_cannot_collect_or_read(self):
        batch=self._ready();self._quant(10);s=self._collect(batch)
        user=self.users['other'];foreign=batch.with_user(user)
        with self.assertRaises(AccessError):foreign.action_collect_supply(self.wh.ids)
        with self.assertRaises(AccessError):s.with_user(user).read(['provenance'])

    def test_mixed_warehouse_snapshot_requires_all_warehouses(self):
        batch=self._ready();self._quant(10);self._quant(20,wh=self.wh2);s=self._collect(batch,warehouses=self.wh|self.wh2)
        grant=self.env[GRANT].search([('user_id','=',self.users['auditor'].id)])
        grant.write({'warehouse_ids':[Command.set(self.wh.ids)],'reason':'Only warehouse A approved'})
        reader=s.with_user(self.users['auditor'])
        self.assertFalse(reader.search([('id','=',s.id)]))
        with self.assertRaises(AccessError):reader.read(['totals'])
        with self.assertRaises(AccessError):reader.export_data(['provenance'])
        with self.assertRaises(AccessError):s.bucket_ids.with_user(self.users['auditor']).read(['evidence'])

    def test_quantity_only_grant_cannot_read_cost_snapshot(self):
        batch=self._ready();self._quant(10);s=self._collect(batch)
        grant=self.env[GRANT].search([('user_id','=',self.users['purchase'].id)])
        grant.write({'allow_cost':False,'reason':'Quantity access only'})
        with self.assertRaises(AccessError):s.read(['provenance'])
        with self.assertRaises(AccessError):batch.action_collect_supply(self.wh.ids,True)
        q=batch.action_collect_supply(self.wh.ids,False)
        self.assertNotIn('standard_price',str(q.provenance));self.assertNotIn('price_unit',str(q.provenance))
        self.assertEqual(q.cost_state,'not_requested')

    def test_revoked_grant_blocks_history_and_grouped_reads(self):
        batch=self._ready();self._quant(10);s=self._collect(batch)
        grant=self.env[GRANT].search([('user_id','=',self.users['purchase'].id)])
        grant.write({'active':False,'reason':'Analytical access revoked'})
        with self.assertRaises(AccessError):s.read(['totals'])
        self.assertFalse(self.env[SNAPSHOT].with_user(self.users['purchase'])._read_group([('id','=',s.id)],[],['__count'])[0][0])

    def test_auditor_read_only_and_sales_configuration_roles_cannot_collect(self):
        batch=self._ready();s=self._collect(batch)
        self.assertTrue(s.with_user(self.users['auditor']).read(['totals']))
        for role in ('auditor','sales','configuration','purchase_b','portal'):
            with self.subTest(role=role),self.assertRaises(AccessError):batch.with_user(self.users[role]).action_collect_supply(self.wh.ids)

    def test_grants_require_admin_and_current_company(self):
        with self.assertRaises(AccessError):self.env[GRANT].with_user(self.users['purchase']).create({})
        with self.assertRaises(ValidationError):self.env[GRANT].create({'company_id':self.a.id,'user_id':self.users['other'].id,
            'warehouse_ids':[Command.set(self.wh_b.ids)],'reason':'Invalid foreign warehouse'})
        with self.assertRaises(AccessError):self.users['purchase'].write({'vpr_supply_warehouse_ids':[Command.set(self.wh_b.ids)]})

    def test_native_source_open_does_not_elevate(self):
        batch=self._ready();self._quant(10);s=self._collect(batch)
        quant=s.bucket_ids.filtered(lambda b:b.source_key.startswith('quant:'))
        source=self.env['stock.quant'].browse(int(quant.source_key.split(':')[1])).with_user(self.users['purchase'])
        source.check_access('read')
        self.assertEqual(quant.action_open_source()['res_id'],source.id)
        po,line=self._po(qty=40);s=self._collect(batch)
        with self.assertRaises(AccessError):s.bucket_ids.filtered(lambda b:b.kind=='incoming_purchase').action_open_source()

    def test_all_collector_actions_leave_operational_sources_unchanged(self):
        batch=self._ready();po,line=self._po(qty=40);self._quant(80,20)
        sources={'stock.quant':['quantity','reserved_quantity','write_date'],
            'stock.move':['state','quantity','product_uom_qty','write_date'],
            'purchase.order':['state','currency_id','locked','write_date'],
            'purchase.order.line':['price_unit','product_qty','qty_received','write_date'],
            'product.supplierinfo':['price','write_date'], 'account.move':['state','write_date']}
        def frozen():return {m:self.env[m].search([]).read(fs,load=None) for m,fs in sources.items()}
        before=frozen();s=self._collect(batch);batch.get_current_supply(self.wh.ids)
        terms=batch.action_propose_supply_terms(self.wh.id,line.id,'firm','Independent supplier terms evidence')
        terms.with_user(self.users['manager']).action_verify_terms('Contract checked');self._collect(batch)
        self.assertEqual(before,frozen())
