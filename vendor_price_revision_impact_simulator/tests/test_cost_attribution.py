"""Controlled real stock/PO/SO fixtures; attribution never mutates operations."""
from decimal import Decimal as D
import logging
import time
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from .test_purchase_commitment import PurchaseFixtures
from .test_commercial_validation import MODULE
from ..models.cost_attribution import HEADER, LINE, ISSUE, CostEngine, amount

_logger = logging.getLogger(__name__)


class CostFixtures(PurchaseFixtures):
    def _cost(self, allocation=None, purchase=0, date='2026-11-05'):
        b = self._batch12()
        a = allocation or self._run(batch=b)
        return b.action_attribute_costs(a.id, purchase, date)

    def _costrow(self, snapshot, kind):
        rows = snapshot.line_ids.filtered(lambda r: r.allocation_type == kind)
        rows.ensure_one()
        return rows

    def _priced_stock(self, qty=60, price=100):
        self.red.with_company(self.a).standard_price = price
        self._quant(qty)
        self._sale(200)


@tagged('post_install', '-at_install')
class TestCostMath(TransactionCase):
    def test_unknown_is_not_zero(self):
        self.assertEqual(amount('100', None, '.01'), (None, None))
        self.assertEqual(amount('100', '0', '.01'), ('0', '0.00'))

    def test_precision_and_reporting_are_separate(self):
        raw, reported = amount('1000000000000000000000000.12345678', '.12345678', '.01')
        self.assertEqual(D(raw), D('123456780000000000000000.01524157652797'))
        self.assertEqual(reported, '123456780000000000000000.02')

    def test_invalid_costs_cannot_be_numeric_evidence(self):
        for value in ('NaN', 'Infinity', '-1', 'bad'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                amount('1', value, '.01')


@tagged('post_install', '-at_install')
class TestCostStock(CostFixtures, TransactionCase):
    def test_fifo_partial_first_native_move_remaining_portion(self):
        self.red.categ_id.with_company(self.a).property_cost_method = 'fifo'
        for price in (90, 100):
            po, line = self._po(30, price)
            self._receive(po, 30)
        sale, line = self._sale(10)
        self._reservation(line, 10)
        picking = sale.picking_ids
        picking.move_ids.quantity = 10
        picking.move_ids.picked = True
        picking._action_done()
        self._sale(50)
        pool = self._cost().provenance['stock_pools'][str(self.red.id)]
        self.assertEqual([D(v['quantity']) for v in pool['layers']], [20, 30])
        self.assertEqual(D(pool['reference_value']), 4800)
        self.assertEqual(D(pool['reference_quantity']), 50)

    def test_standard100_proposal115_does_not_revalue(self):
        self._priced_stock()
        s = self._cost()
        r = self._costrow(s, 'eligible_free_stock')
        self.assertEqual((D(r.quantity), D(r.unit_cost), D(r.reference_value)), (60, 100, 6000))
        self.assertEqual(r.confidence, 'supported_estimate')
        self.assertEqual(r.evidence['source_confidence'], 'verified_accounting_basis')
        self.assertEqual(self.red.with_company(self.a).standard_price, 100)
        _logger.info('PR13_STANDARD quantity=60 accounting_reference=100 value=6000 proposed=115 unchanged')

    def test_reserved_and_free_not_double_counted(self):
        self.red.with_company(self.a).standard_price = 100
        self._quant(60)
        sale, line = self._sale(100)
        self._reservation(line, 20)
        s = self._cost()
        self.assertEqual(D(self._costrow(s, 'existing_reserved_for_demand').quantity), 20)
        self.assertEqual(D(self._costrow(s, 'eligible_free_stock').quantity), 40)
        self.assertEqual(sum(D(r.quantity) for r in s.line_ids), 100)
        self.assertEqual(sum(D(r.reference_value) for r in s.line_ids if r.allocation_type != 'new_procurement_requirement'), 6000)

    def test_avco_real_receipts10at90_10at110(self):
        self.red.categ_id.with_company(self.a).property_cost_method = 'average'
        for price in (90, 110):
            po, line = self._po(10, price)
            self._receive(po, 10)
        self._sale(20)
        s = self._cost()
        r = self._costrow(s, 'eligible_free_stock')
        self.assertEqual(D(r.unit_cost), 100)
        self.assertEqual(r.evidence['scope'], 'company_product')
        _logger.info('PR13_AVCO native_receipts=10@90+10@110 company_product_reference=100 no_warehouse_acquisition_claim')

    def test_fifo_real_receipts30at90_30at100_company5700_only(self):
        self.red.categ_id.with_company(self.a).property_cost_method = 'fifo'
        for price in (90, 100):
            po, line = self._po(30, price)
            self._receive(po, 30)
        self._sale(60)
        s = self._cost()
        pool = s.provenance['stock_pools'][str(self.red.id)]
        self.assertEqual((D(pool['reference_quantity']), D(pool['reference_value']), D(pool['reference_unit_cost'])), (60, 5700, 95))
        self.assertEqual([D(v['quantity']) for v in pool['layers']], [30, 30])
        r = self._costrow(s, 'eligible_free_stock')
        self.assertFalse(r.unit_cost)
        self.assertFalse(r.reference_value)
        self.assertEqual(r.confidence, 'review_required')
        self.assertNotIn('layers', r.evidence)
        self.assertEqual(r.evidence['pool_key'], str(self.red.id))
        _logger.info('PR13_FIFO native_stack=30@90+30@100 company_reference=5700 weighted=95 warehouse_cost=INCOMPLETE')

    def test_fifo_quant_without_valuation_moves_no_standard_fallback(self):
        self.red.categ_id.with_company(self.a).property_cost_method = 'fifo'
        self._priced_stock()
        r = self._costrow(self._cost(), 'eligible_free_stock')
        self.assertFalse(r.unit_cost)
        self.assertEqual(r.evidence['reason'], 'FIFO_REMAINING_QUANTITY_NOT_RECONCILED')

    def test_zero_default_cost_is_unknown(self):
        self.red.with_company(self.a).with_context(disable_auto_revaluation=True).standard_price = 0
        self._quant(60)
        self._sale(200)
        r = self._costrow(self._cost(), 'eligible_free_stock')
        self.assertFalse(r.unit_cost)
        self.assertFalse(r.reference_value)

    def test_documented_native_zero_update_is_real_zero(self):
        self._priced_stock(price=0)
        r = self._costrow(self._cost(), 'eligible_free_stock')
        self.assertEqual(D(r.unit_cost), 0)
        self.assertEqual(D(r.reference_value), 0)
        self.assertTrue(r.evidence['zero_evidence'])

    def test_landed105_is_never110(self):
        self._priced_stock(price=105)
        r = self._costrow(self._cost(), 'eligible_free_stock')
        self.assertEqual(D(r.unit_cost), 105)
        self.assertEqual(D(r.reference_value), 6300)
        self.assertIn('no additional historical charge', r.evidence['landed_cost'])
        _logger.info('PR13_LANDED recorded_reference=105 includes_historical5 additional=0 result=105 not110')

    def test_foreign_company_cost_not_used(self):
        self.red.with_company(self.b).standard_price = 999
        self._priced_stock()
        self.assertEqual(D(self._costrow(self._cost(), 'eligible_free_stock').unit_cost), 100)

    def test_consignment_is_not_cost_backed_stock(self):
        self.red.with_company(self.a).standard_price = 100
        self._quant(60, owner_id=self.vendor.id)
        self._sale(100)
        s = self._cost()
        self.assertFalse(s.line_ids.filtered(lambda r: r.allocation_type == 'eligible_free_stock'))


@tagged('post_install', '-at_install')
class TestCostIncoming(CostFixtures, TransactionCase):
    def test_reference_a200_distinct60_stock40_protected100_replacement(self):
        self._priced_stock()
        po, line = self._po(40, 100)
        r = self._row12(self._collect12(), line)
        self._assess12(r)
        a = self._run(batch=self._batch12())
        p = self._batch12().action_collect_purchase_terms(self.wh.ids, True, a.id, False)
        s = self._cost(a, p.id)
        self.assertEqual(len(s.line_ids), 3)
        stock = self._costrow(s, 'eligible_free_stock')
        incoming = s.line_ids.filtered(lambda r: r.allocation_type in ('protected_incoming_po', 'incoming_cost_unverified'))
        replacement = self._costrow(s, 'new_procurement_requirement')
        self.assertEqual((D(stock.quantity), D(stock.unit_cost)), (60, 100))
        self.assertEqual((D(incoming.quantity), D(incoming.unit_cost)), (40, 100))
        self.assertEqual((D(replacement.quantity), D(replacement.unit_cost)), (100, 115))
        self.assertEqual(sum(D(r.quantity) for r in s.line_ids), 200)
        _logger.info('PR13_REFERENCE_A demand200=stock60@100+protected40@100+new100@115 distinct_sources_no_margin')

    def _incoming(self, kind='fixed'):
        po, line = self._po(40, 100)
        row = self._row12(self._collect12(), line)
        self._assess12(row, kind, '115' if kind == 'amendment_pending' else None)
        self._sale(40)
        a = self._run(batch=self._batch12())
        p = self._batch12().action_collect_purchase_terms(self.wh.ids, True, a.id, False)
        return po, line, a, p

    def test_protected40_at100_not115(self):
        po, line, a, p = self._incoming()
        s = self._cost(a, p.id)
        r = s.line_ids
        self.assertEqual((D(r.quantity), D(r.unit_cost), D(r.reference_value)), (40, 100, 4000))
        self.assertEqual(r.confidence, 'verified_commercial_basis')
        self.assertEqual(line.price_unit, 100)
        _logger.info('PR13_PROTECTED exact_PR12 quantity=40 agreed=100 reference=4000 proposal115_not_applied')

    def test_pending_amendment_retains_recorded_and_alternative_no_selected_cost(self):
        po, line, a, p = self._incoming('amendment_pending')
        r = self._cost(a, p.id).line_ids
        self.assertFalse(r.unit_cost)
        self.assertEqual(r.confidence, 'review_required')
        self.assertEqual(D(r.evidence['recorded_company_unit_cost']), 100)
        self.assertTrue(r.evidence['amendment_alternatives'])
        self.assertEqual(line.price_unit, 100)

    def test_pr09_label_without_pr12_is_not_authority(self):
        po, line, a, p = self._incoming()
        r = self._cost(a).line_ids
        self.assertFalse(r.unit_cost)
        self.assertEqual(r.evidence['reason'], 'CURRENT_EXACT_PR12_PROTECTION_REQUIRED')

    def test_stale_po_cannot_supply_verified_cost(self):
        po, line, a, p = self._incoming()
        line.price_unit = 115
        with self.assertRaises(UserError):
            self._cost(a, p.id)

    def test_other_allocation_purchase_snapshot_rejected(self):
        po, line, a, p = self._incoming()
        p0 = self._batch12().action_collect_purchase_terms(self.wh.ids)
        with self.assertRaises(AccessError):
            self._cost(a, p0.id)


@tagged('post_install', '-at_install')
class TestCostReplacement(CostFixtures, TransactionCase):
    def _tier_batch(self):
        from .test_import_validation import VALID
        self._rule(price=100, qty=1, uom=self.unit)
        rows = []
        for qty, price in ((1, 115), (100, 109), (500, 104)):
            row = list(VALID)
            row[0], row[2], row[4], row[5] = 'LED-12W-RED', str(price), 'PCS', str(qty)
            rows.append(row)
        b = self._commercial_batch(rows)
        self._context(b)
        b.action_validate_commercial_prices()
        self.assertTrue(all(r.commercial_status == 'commercially_valid' for r in b.row_ids))
        self._pb = b
        return b

    def test_explicit_single_entry100_qualifies109_tier(self):
        self._tier_batch()
        self._sale(100)
        r = self._cost().line_ids
        self.assertEqual(D(r.unit_cost), 109)
        self.assertEqual(D(r.evidence['proposal']['normalized_min_qty']), 100)
        self.assertEqual(r.confidence, 'scenario_assumption')
        self.assertTrue(r.evidence['hypothetical_buying_quantity'])
        _logger.info('PR13_MOQ single_entry_explicit_buying_scenario=100 qualifying_MOQ=100 price=109 not_guaranteed_actual_order')

    def test_two60_entries_do_not_qualify100_tier(self):
        self._tier_batch()
        self._sale(60)
        self._sale(60)
        s = self._cost()
        self.assertEqual(len(s.line_ids), 2)
        self.assertTrue(all(D(r.unit_cost) == 115 for r in s.line_ids))

    def test_500_tier_not_used_for100_units(self):
        self._tier_batch()
        self._sale(100)
        self.assertEqual(D(self._cost().line_ids.unit_cost), 109)

    def test_foreign_price_uses_documented_reference_date_not_future_forecast(self):
        from .test_import_validation import VALID
        self._policy_replace(currency_rate_policy='company_reference_date', currency_reference_date='2026-10-28')
        self._rates()
        self._rule(price=100, qty=1, uom=self.unit, currency=self.usd)
        row = list(VALID)
        row[0], row[2], row[3] = 'LED-12W-RED', '115', 'USD'
        b = self._commercial_batch([row])
        self._context(b)
        self._validate(b)
        self._pb = b
        self._sale(100)
        # Company-reference date deliberately provides an evidenced rate. The
        # future planning date must not relabel that historic rate as a forecast.
        r = self._cost().line_ids
        self.assertEqual(D(r.unit_cost), D(115)*94)
        self.assertEqual(r.evidence['fx_date'], '2026-10-28')
        self.assertEqual(r.evidence['proposal']['source_currency_id'], self.usd.id)

    def test_future_fx_not_guessed_from_last_known_rate(self):
        from .test_import_validation import VALID
        self._rates()
        self._rule(price=100, qty=1, uom=self.unit, currency=self.usd, date_end='2026-10-27')
        row = list(VALID)
        row[0], row[2], row[3], row[6] = 'LED-12W-RED', '115', 'USD', '2026-10-28'
        b = self._commercial_batch([row])
        self._context(b, baseline_mode='explicit', baseline_date='2026-10-27', comparison_mode='date_specific', historical_attestation='Dated supplier baseline independently checked')
        self._validate(b)
        self._pb = b
        self._sale(100)
        r = self._cost().line_ids
        self.assertFalse(r.unit_cost)
        self.assertEqual(r.evidence['reason'], 'FX_DATE_UNSUPPORTED')


    def test_new100_at115_box10_normalized(self):
        self._sale(100)
        r = self._costrow(self._cost(), 'new_procurement_requirement')
        self.assertEqual((D(r.quantity), D(r.unit_cost), D(r.reference_value)), (100, 115, 11500))
        self.assertEqual(r.confidence, 'scenario_assumption')
        self.assertEqual(D(r.evidence['proposal']['source_price']), 1150)
        self.assertFalse(r.evidence['price_accepted'])
        _logger.info('PR13_REPLACEMENT single_entry_buying_scenario=100 unit=115 reference=11500 no_PO')

    def test_missing_planning_date_not_today_guessed(self):
        self._sale(100)
        r = self._costrow(self._cost(date=None), 'new_procurement_requirement')
        self.assertFalse(r.unit_cost)
        self.assertEqual(r.evidence['reason'], 'EXPLICIT_PROCUREMENT_DATE_REQUIRED')

    def test_before_effective_date_is_ineligible(self):
        self._sale(100)
        r = self._costrow(self._cost(date='2026-10-01'), 'new_procurement_requirement')
        self.assertFalse(r.unit_cost)

    def test_entry_below_moq_does_not_aggregate_other_demands(self):
        self._sale(6)
        self._sale(6)
        s = self._cost()
        self.assertEqual(len(s.line_ids), 2)
        self.assertTrue(all(not r.unit_cost for r in s.line_ids))

    def test_all_entries_quantities_and_segments_reconcile(self):
        self._priced_stock()
        s = self._cost()
        self.assertEqual(len(s.line_ids), len(s.allocation_id.entry_ids))
        self.assertEqual(sum(D(r.quantity) for r in s.line_ids), 200)
        for r in s.line_ids:
            self.assertEqual(sum(D(v['quantity']) for v in r.segments), D(r.quantity))
        self.assertFalse(s.reconciliation['alternatives_additive'])


@tagged('post_install', '-at_install')
class TestCostIntegrity(CostFixtures, TransactionCase):
    def test_native_manual_history_change_versions_same_allocation(self):
        self._priced_stock()
        s = self._cost()
        manual = self.env['product.value'].search([('product_id', '=', self.red.id), ('company_id', '=', self.a.id)], order='id desc', limit=1)
        manual.description = 'Additional native audit description checked'
        with self.assertRaises(UserError):
            self._batch12().get_current_costs(**s.scope)
        new = self._batch12().action_attribute_costs(**s.scope)
        self.assertEqual(new.version, 2)
        self.assertEqual(new.previous_id, s)
        self.assertEqual(s.version, 1)

    def test_repeated_unchanged_is_idempotent(self):
        self._priced_stock()
        s = self._cost()
        self.assertEqual(self._batch12().action_attribute_costs(**s.scope), s)
        self.assertEqual(self._batch12().get_current_costs(**s.scope), s)
        self.assertEqual(s.freshness, 'current')

    def test_product_cost_change_invalidates(self):
        self._priced_stock()
        s = self._cost()
        self.red.with_company(self.a).standard_price = 105
        with self.assertRaises(UserError):
            self._batch12().get_current_costs(**s.scope)
        self.assertEqual(D(self._costrow(s, 'eligible_free_stock').unit_cost), 100)

    def test_atomic_failure_creates_no_partial_snapshot(self):
        self._priced_stock()
        a = self._run(batch=self._batch12())
        with patch.object(CostEngine, 'attribute', side_effect=ValidationError('Injected incomplete source')):
            with self.assertRaises(ValidationError):
                self._cost(a)
        self.assertFalse(self.env[HEADER].search([('allocation_id', '=', a.id)]))

    def test_invalid_ids_and_dates(self):
        self._priced_stock()
        a = self._run(batch=self._batch12())
        for aid, pid, date in ((True, 0, None), (a.id, True, None), (a.id, 0, 'bad')):
            with self.subTest(aid=aid, pid=pid, date=date), self.assertRaises(ValidationError):
                self._batch12().action_attribute_costs(aid, pid, date)

    def test_no_operational_writes(self):
        self._priced_stock()
        po, line = self._po(40, 100)
        b = self._batch12()
        a = self._run(batch=b)
        models = {'product.product': ['standard_price', 'write_date'], 'product.supplierinfo': ['price', 'write_date'],
            'purchase.order.line': ['price_unit', 'product_qty', 'qty_received', 'write_date'],
            'sale.order.line': ['price_unit', 'product_uom_qty', 'write_date'],
            'stock.quant': ['quantity', 'reserved_quantity', 'write_date'], 'stock.move': ['value', 'state', 'quantity', 'write_date'],
            'account.move': ['state', 'amount_total', 'write_date'], 'product.value': ['value', 'write_date']}
        before = {m: self.env[m].search([]).read(names, load=None) for m, names in models.items()}
        s = self._cost(a)
        self.assertTrue(s)
        self.assertEqual(before, {m: self.env[m].search([]).read(names, load=None) for m, names in models.items()})


@tagged('post_install', '-at_install')
class TestCostSecurity(CostFixtures, TransactionCase):
    def test_cost_source_drilldown_requires_native_permissions(self):
        self._sale(100)
        s = self._cost()
        # APP source evidence is available; native Purchase rights were not granted.
        po, line = self._po(40, 100)
        a = self._run(batch=self._batch12())
        p = self._batch12().action_collect_purchase_terms(self.wh.ids, True, a.id, False)
        incoming = self._cost(a, p.id).line_ids.filtered(lambda r: r.allocation_type == 'incoming_cost_unverified')
        self.assertTrue(incoming)
        with self.assertRaises(AccessError):
            incoming.action_open_cost_source()

    def test_foreign_company_context_cannot_read_id_export_or_nested(self):
        self._priced_stock()
        s = self._cost()
        foreign = self.env[HEADER].with_user(self.users['purchase']).with_context(allowed_company_ids=self.b.ids).browse(s.id)
        for operation in (lambda: foreign.read(['provenance']), lambda: foreign.export_data(['line_ids/unit_cost'])):
            with self.assertRaises(AccessError):
                operation()

    def test_public_portal_have_no_cost_access(self):
        self._priced_stock()
        s = self._cost()
        for user in (self.env.ref('base.public_user'),):
            with self.assertRaises(AccessError):
                self.env[HEADER].with_user(user).browse(s.id).read(['provenance'])

    def test_sales_only_cannot_read_costs_or_export_or_group(self):
        self._priced_stock()
        s = self._cost()
        u = self.users['sales']
        for model, rid in ((HEADER, s.id), (LINE, s.line_ids[0].id)):
            rec = self.env[model].with_user(u).browse(rid)
            for operation in (lambda: rec.read(), lambda: rec.export_data(['evidence'] if model == LINE else ['provenance']),
                              lambda: rec._read_group([], ['company_id'], ['__count'])):
                with self.assertRaises(AccessError):
                    operation()

    def test_auditor_readonly_cannot_collect_or_forge(self):
        self._priced_stock()
        s = self._cost()
        u = self.users['auditor']
        self.assertEqual(self.env[HEADER].with_user(u).browse(s.id).read(['id'])[0]['id'], s.id)
        with self.assertRaises(AccessError):
            self._batch12().with_user(u).action_attribute_costs(**s.scope)
        with self.assertRaises(AccessError):
            self.env[LINE].with_user(u).create({'unit_cost': '0'})

    def test_immutable_direct_write_copy_unlink_nested_commands(self):
        self._priced_stock()
        s = self._cost()
        for rec in (s, s.line_ids[0], s.issue_ids):
            if not rec:
                continue
            for operation in (lambda: rec.write({'batch_id': self._batch12().id}), lambda: rec.copy(), lambda: rec.unlink()):
                with self.assertRaises(AccessError):
                    operation()
        with self.assertRaises(AccessError):
            s.with_context(default_company_id=self.b.id).write({'line_ids': [Command.create({'unit_cost': '0'})]})

    def test_revoked_cost_scope_hides_snapshots_and_children(self):
        self._priced_stock()
        s = self._cost()
        from ..models.supply_governance import GRANT
        grants = self.env[GRANT].search([('company_id', '=', self.a.id), ('user_id', '=', self.users['purchase'].id)])
        grants.write({'allow_cost': False, 'reason': 'Withdraw cost access'})
        self.assertFalse(self.env[HEADER].with_user(self.users['purchase']).search([('id', '=', s.id)]))
        self.assertFalse(self.env[LINE].with_user(self.users['purchase']).search([('snapshot_id', '=', s.id)]))
        with self.assertRaises(AccessError):
            self._batch12().get_current_costs(**s.scope)


@tagged('post_install', '-at_install')
class TestCostWorkload(CostFixtures, TransactionCase):
    def test_100_demand_entries_measured(self):
        for _ in range(100):
            self._sale(10)
        a = self._run(batch=self._batch12())
        start = time.perf_counter()
        s = self._cost(a)
        elapsed = time.perf_counter()-start
        self.assertEqual(len(s.line_ids), 100)
        self.assertEqual(sum(D(r.quantity) for r in s.line_ids), 1000)
        self.assertTrue(all(D(r.unit_cost) == 115 for r in s.line_ids))
        _logger.info('PR13_WORKLOAD demand_entries=100 costs=%s seconds=%.3f result=reconciled', len(s.line_ids), elapsed)
