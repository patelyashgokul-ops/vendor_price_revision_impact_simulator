"""PR14 real company-scoped source fixtures; no operational writes by analysis."""
from decimal import Decimal as D
import logging
import time
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from .test_cost_attribution import CostFixtures
from .test_import_validation import VALID
from .test_commercial_validation import MODULE
from ..models.financial_exposure import HEADER, LINE, ISSUE, FinancialEngine, calculate
from ..models.sales_exposure import GRANT as SALES_GRANT

_logger = logging.getLogger(__name__)


class FinancialFixtures(CostFixtures):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.users['manager'].write({'group_ids': [Command.link(cls.env.ref(MODULE+'.group_vpr_sales_manager').id)]})
        for role in ('manager', 'finance', 'auditor', 'sales'):
            cls.users[role].write({'group_ids': [Command.link(cls.env.ref('sales_team.group_sale_salesman_all_leads').id)]})
            cls.env[SALES_GRANT].create({'company_id': cls.a.id, 'user_id': cls.users[role].id,
                'warehouse_ids': [Command.set((cls.wh | cls.wh2 | cls.wh3).ids)], 'reason': 'Explicit financial-source customer-commercial scope'})

    def _inputs14(self, allocation=None, date='2026-11-05'):
        b = self._batch12()
        a = allocation or self._run(batch=b)
        p = b.action_collect_purchase_terms(a.warehouse_ids.ids, True, a.id, False)
        c = b.action_attribute_costs(a.id, p.id, date)
        s = a.with_user(self.users['manager']).action_collect_sales_terms()
        return c, s

    def _finance(self, allocation=None, date='2026-11-05', confirmed=0, method='same_rate', inputs=None, actor='manager'):
        c, s = inputs or self._inputs14(allocation, date)
        return self._batch12().with_user(self.users[actor]).action_calculate_financial_exposure(c.id, s.id, confirmed, method)

    def _commercial14(self, old=100, new=115, old_qty=1, old_start='2025-01-01', currency=None, fx_options=None, context=None, tiers=None, effective='2026-11-01'):
        if fx_options:
            self._policy_replace(**fx_options)
        self._rule(price=old, qty=old_qty, uom=self.unit, currency=currency or self.inr, date_start=old_start)
        rows = []
        for qty, price in (tiers or [(old_qty, new)]):
            row = list(VALID)
            row[0], row[2], row[3], row[4], row[5], row[6] = 'LED-12W-RED', str(price), (currency or self.inr).name, 'PCS', str(qty), effective
            rows.append(row)
        b = self._commercial_batch(rows)
        self._context(b, **(context or {}))
        b.action_validate_commercial_prices()
        self.assertTrue(all(r.commercial_status == 'commercially_valid' for r in b.row_ids), b.row_ids.mapped('commercial_summary'))
        self._pb = b
        return b

    def _reference14(self, po_price=100, tier=False):
        if tier:
            self._commercial14(tiers=[(1, 115), (100, 109), (500, 104)])
        self.red.with_company(self.a).standard_price = 100
        self._quant(60)
        po, line = self._po(40, po_price)
        self._sale(200)
        r = self._row12(self._collect12(), line)
        self._assess12(r)
        return self._finance()

    def _assert_totals(self, s, b, r, delta):
        self.assertEqual((D(s.baseline_total), D(s.revised_total), D(s.incremental_total)), (D(b), D(r), D(delta)))
        self.assertEqual(sum(D(l.quantity) for l in s.line_ids), sum(D(e.quantity) for e in s.cost_id.allocation_id.entry_ids))
        self.assertEqual(sum(D(l.baseline_extended_cost) for l in s.line_ids), D(b))
        self.assertEqual(sum(D(l.revised_extended_cost) for l in s.line_ids), D(r))
        self.assertEqual(sum(D(l.incremental_extended_cost) for l in s.line_ids), D(delta))
        self.assertEqual(D(s.revised_total)-D(s.baseline_total), D(s.incremental_total))


@tagged('post_install', '-at_install')
class TestFinancialMath(TransactionCase):
    def test_signed_increase_decrease_unchanged_and_zero(self):
        for b, r, expected, direction in [('100', '115', '1500', 'cost_increase'), ('115', '109', '-600', 'potential_cost_reduction'), ('100', '100', '0', 'unchanged'), ('0', '115', '11500', 'cost_increase')]:
            with self.subTest(b=b, r=r):
                got = calculate('100', b, r)
                self.assertEqual(D(got['incremental_extended_cost']), D(expected))
                self.assertEqual(got['direction'], direction)

    def test_unknown_is_not_zero_or_complete_cost(self):
        r = calculate('60', None, None, unchanged=True)
        self.assertIsNone(r['baseline_extended_cost'])
        self.assertIsNone(r['revised_extended_cost'])
        self.assertEqual(r['incremental_extended_cost'], '0')
        self.assertIsNone(calculate('100', None, '115')['incremental_extended_cost'])
        self.assertIsNone(calculate('100', '100', None)['incremental_extended_cost'])

    def test_zero_quantity_safe_no_weighted_division(self):
        r = calculate('0', '100', '115')
        self.assertEqual(r['incremental_extended_cost'], '0')

    def test_decimal_precision_before_reporting(self):
        r = calculate('1000000000000000000000000.12345678', '.12345678', '.22345678')
        self.assertEqual(D(r['baseline_extended_cost']), D('123456780000000000000000.01524157652797'))
        self.assertEqual(D(r['incremental_unit_cost']), D('.10000000'))

    def test_nonfinite_negative_quantity_and_cost_rejected(self):
        for q, b, r in [('NaN', '1', '2'), ('-1', '1', '2'), ('1', '-1', '2'), ('1', '1', 'Infinity')]:
            with self.subTest(q=q, b=b, r=r), self.assertRaises(ValueError):
                calculate(q, b, r)


@tagged('post_install', '-at_install')
class TestFinancialReferences(FinancialFixtures, TransactionCase):
    def test_reference_a200_20000_21500_1500(self):
        s = self._reference14()
        self._assert_totals(s, '20000', '21500', '1500')
        self.assertEqual(s.line_count, 3)
        self.assertTrue(s.cost_complete and s.delta_complete)
        self.assertEqual(s.state, 'scenario_only')
        self.assertEqual(s.reconciliation['quantity_groups'][0]['revised_weighted_unit'], '107.5')
        self.assertTrue(all(D(l.incremental_extended_cost) == 0 for l in s.line_ids if l.source_type != 'new_procurement_requirement'))
        _logger.info('PR14_REFERENCE_A demand200=stock60+protected40+new100 baseline=20000 revised=21500 delta=1500 weighted=107.5 declared_scenario_not_expense')

    def test_reference_b_moq100_20900_900(self):
        s = self._reference14(tier=True)
        self._assert_totals(s, '20000', '20900', '900')
        r = s.line_ids.filtered(lambda r: r.source_type == 'new_procurement_requirement')
        self.assertEqual(D(r.revised_unit_cost), 109)
        _logger.info('PR14_REFERENCE_B baseline=20000 revised=20900 delta=900 qualifying_single_entry_MOQ100=109')

    def test_reference_c_negotiated95_19800_21300_1500(self):
        s = self._reference14(po_price=95)
        self._assert_totals(s, '19800', '21300', '1500')
        _logger.info('PR14_REFERENCE_C negotiated_PO95 baseline=19800 revised=21300 delta=1500 no_PO_repricing')

    def test_real_decrease_115_to109_not_realized_savings(self):
        self._commercial14(old=115, new=109)
        self._sale(100)
        s = self._finance()
        self._assert_totals(s, '11500', '10900', '-600')
        self.assertEqual(s.direction, 'potential_cost_reduction')

    def test_verified_zero_vendor_baseline_not_missing(self):
        self._commercial14(old=0, new=115)
        self._sale(100)
        s = self._finance()
        self._assert_totals(s, '0', '11500', '11500')
        self.assertEqual(D(s.line_ids.baseline_unit_cost), 0)

    def test_existing_stock100_not_old_vendor90_or_proposed115(self):
        self._commercial14(old=90, new=115)
        self.red.with_company(self.a).standard_price = 100
        self._quant(60)
        self._sale(60)
        s = self._finance()
        self._assert_totals(s, '6000', '6000', '0')
        self.assertEqual(s.state, 'estimated')

    def test_box_to_piece_normalization_not_115000(self):
        self._sale(100)
        s = self._finance()
        self._assert_totals(s, '10000', '11500', '1500')
        self.assertEqual(D(s.line_ids.revised_unit_cost), 115)

    def test_reserved_free_stock_distinct_once(self):
        self.red.with_company(self.a).standard_price = 100
        self._quant(60)
        sale, line = self._sale(100)
        self._reservation(line, 20)
        s = self._finance()
        self._assert_totals(s, '10000', '10600', '600')
        by = {l.source_type: D(l.quantity) for l in s.line_ids}
        self.assertEqual(by['existing_reserved_for_demand'], 20)
        self.assertEqual(by['eligible_free_stock'], 40)
        self.assertEqual(by['new_procurement_requirement'], 40)

    def test_no_demand_has_scope_zero_not_future_claim(self):
        s = self._finance()
        self._assert_totals(s, '0', '0', '0')
        self.assertTrue(s.provenance['no_eligible_demand'])
        self.assertEqual(s.line_count, 0)

    def test_no_margin_or_profit_fields(self):
        self.assertFalse({'gross_profit', 'gross_margin', 'risk_score'} & set(self.env[HEADER]._fields))

    def test_missing_sales_fx_does_not_block_cost_classification(self):
        price_list = self.env['product.pricelist'].create({'name': 'PR14 USD revenue context only', 'company_id': self.a.id, 'currency_id': self.usd.id})
        sale, line = self._sale(100, confirm=False)
        sale.pricelist_id = price_list
        sale.action_confirm()
        c, sales = self._inputs14()
        self.assertEqual(sales.line_ids.sales_currency_id, self.usd)
        self.assertFalse(sales.line_ids.company_sales_value)
        self.assertIsNone(sales.line_ids.fx_evidence['rate'])
        s = self._finance(inputs=(c, sales))
        self._assert_totals(s, '10000', '11500', '1500')


@tagged('post_install', '-at_install')
class TestFinancialPricing(FinancialFixtures, TransactionCase):
    def test_old_tier_resolved_at_actual_entry100_not_proposal_moq1(self):
        self._commercial14(old=100, new=115)
        self._rule(price=90, qty=100, uom=self.unit)
        b = self._batch12()
        b.action_validate_commercial_prices()
        self._sale(100)
        s = self._finance()
        self._assert_totals(s, '9000', '11500', '2500')
        self.assertEqual(D(s.line_ids.evidence['pricing']['applicable_old_tier']['normalized_min_qty']), 100)

    def test_two60_orders_do_not_consolidate_to_moq100(self):
        self._commercial14(tiers=[(1, 115), (100, 109)])
        self._sale(60)
        self._sale(60)
        s = self._finance()
        self._assert_totals(s, '12000', '13800', '1800')
        self.assertEqual(len(s.line_ids), 2)
        self.assertTrue(all(D(l.revised_unit_cost) == 115 for l in s.line_ids))

    def test_before_revision_date_new_price_not_applied(self):
        self._sale(100)
        s = self._finance(date='2026-10-30')
        self._assert_totals(s, '10000', '10000', '0')
        self.assertEqual(s.line_ids.evidence['pricing']['timing'], 'before_revision_effective_date')
        self.assertEqual(s.line_ids.cost_confidence, 'scenario_assumption')
        self.assertTrue(s.line_ids.evidence['pricing']['buying_quantity_hypothetical'])

    def test_missing_old_at_purchase_date_is_not_zero(self):
        self._commercial14(old_start='2026-10-31')
        self._sale(100)
        s = self._finance(date='2026-10-30')
        self.assertFalse(s.baseline_total or s.revised_total or s.incremental_total)
        self.assertEqual(s.incomplete_cost_line_count, 1)
        self.assertIn('BASELINE_UNAVAILABLE', s.issue_ids.mapped('code'))
        _logger.info('PR14_REFERENCE_D missing_old_price retained_qty=100 baseline=NULL revised=NULL delta=NULL not_zero')

    def test_missing_planning_date_incomplete(self):
        self._sale(100)
        s = self._finance(date=None)
        self.assertFalse(s.incremental_total)
        self.assertIn('PROCUREMENT_DATE_UNCERTAIN', s.issue_ids.mapped('code'))

    def test_old_tier_conflict_at_entry_quantity_not_hidden(self):
        self._commercial14()
        self._rule(price=90, qty=100, uom=self.unit)
        self._rule(price=91, qty=100, uom=self.unit)
        self._batch12().action_validate_commercial_prices()
        self._sale(100)
        s = self._finance()
        self.assertFalse(s.incremental_total)
        self.assertIn('BASELINE_CONFLICT', s.issue_ids.mapped('code'))

    def _usd14(self, old=10, new=11, reference='2026-10-28', historical=False):
        self._rates()
        context = dict(baseline_mode='explicit', baseline_date='2026-10-27', comparison_mode='date_specific', historical_attestation='Dated supplier baseline independently checked') if historical else None
        self._commercial14(old, new, currency=self.usd, fx_options=dict(currency_rate_policy='company_reference_date', currency_reference_date=reference), context=context)
        self._sale(100)

    def test_common_rate90_usd10_to11_is90_per_unit(self):
        self._usd14(reference='2026-10-27')
        s = self._finance()
        self._assert_totals(s, '90000', '99000', '9000')
        self.assertEqual(D(s.line_ids.supplier_price_component), 9000)
        self.assertEqual(D(s.line_ids.fx_component), 0)

    def test_date_specific900_to1034_split90_and44_per_unit(self):
        self._usd14(historical=True)
        c, sl = self._inputs14()
        s = self._finance(inputs=(c, sl), method='date_specific')
        self._assert_totals(s, '90000', '103400', '13400')
        self.assertEqual(D(s.line_ids.supplier_price_component), 9000)
        self.assertEqual(D(s.line_ids.fx_component), 4400)
        self.assertEqual(s.line_ids.delta_method, 'combined_supplier_price_and_fx_reference')
        common = self._finance(inputs=(c, sl))
        self._assert_totals(common, '94000', '103400', '9400')
        self.assertNotEqual(s, common)
        _logger.info('PR14_FX oldUSD10@90=900 newUSD11@94=1034 total134 price90 fx44 separate_common_rate_scope')

    def test_future_fx_missing_no_last_known_forecast(self):
        self._rates()
        self._commercial14(old=10, new=11, currency=self.usd, effective='2026-10-28', context=dict(baseline_mode='explicit', baseline_date='2026-10-27', comparison_mode='date_specific', historical_attestation='Dated supplier baseline independently checked'))
        self._sale(100)
        s = self._finance()
        self.assertFalse(s.incremental_total)
        self.assertIn('FX_DATE_UNSUPPORTED', s.issue_ids.mapped('code'))


@tagged('post_install', '-at_install')
class TestFinancialCompleteness(FinancialFixtures, TransactionCase):
    def test_unknown_fifo_total_unknown_but_unchanged_delta_zero(self):
        self.red.categ_id.with_company(self.a).property_cost_method = 'fifo'
        self._quant(60)
        self._sale(60)
        s = self._finance()
        self.assertFalse(s.baseline_total or s.revised_total)
        self.assertEqual(D(s.incremental_total), 0)
        self.assertTrue(s.delta_complete)
        self.assertFalse(s.cost_complete)
        self.assertEqual(s.state, 'verified_incremental_only')

    def test_unknown_fifo_and_new100_delta1500_without_complete_cost(self):
        self.red.categ_id.with_company(self.a).property_cost_method = 'fifo'
        self._quant(60)
        self._sale(160)
        s = self._finance()
        self.assertFalse(s.baseline_total or s.revised_total)
        self.assertEqual(D(s.incremental_total), 1500)
        self.assertTrue(s.delta_complete)
        self.assertEqual(s.incomplete_cost_line_count, 1)
        self.assertEqual(sum(D(l.quantity) for l in s.line_ids), 160)
        self.assertEqual(s.state, 'partially_verified')

    def test_pending_po_amendment_not_verified_or_repriced(self):
        po, line = self._po(40, 100)
        r = self._row12(self._collect12(), line)
        self._assess12(r, 'amendment_pending', '115')
        self._sale(40)
        s = self._finance()
        self.assertFalse(s.baseline_total or s.revised_total or s.incremental_total)
        self.assertEqual(s.line_ids.evidence['cost_evidence']['amendment_status'], 'amendment_pending')
        self.assertEqual(D(s.line_ids.evidence['cost_evidence']['recorded_company_unit_cost']), 100)
        self.assertEqual(line.price_unit, 100)
        _logger.info('PR14_REFERENCE_E pending_PO_amendment qty40 recorded100 requested115 selected_totals=NULL not_accepted')

    def test_partial_known_new_delta_not_full_total_when_po_unprotected(self):
        self._po(40, 100)
        self._sale(140)
        s = self._finance()
        self.assertFalse(s.incremental_total)
        self.assertEqual(D(s.partial_comparable_delta), 1500)
        self.assertEqual(s.line_count, 2)
        self.assertEqual(s.incomplete_cost_line_count, 1)

    def test_zero_configured_stock_cost_without_evidence_not_zero_total(self):
        self.red.with_company(self.a).with_context(disable_auto_revaluation=True).standard_price = 0
        self._quant(60)
        self._sale(60)
        s = self._finance()
        self.assertFalse(s.baseline_total)
        self.assertEqual(D(s.incremental_total), 0)


@tagged('post_install', '-at_install')
class TestFinancialQuotations(FinancialFixtures, TransactionCase):
    def _quote_case(self, portfolio=False):
        self._sale(100)
        quote, line = self._sale(70, confirm=False)
        quotes = quote
        if portfolio:
            other, ol = self._sale(30, confirm=False)
            quotes |= other
        b = self._batch12()
        a = self._run(batch=b, quotes=quotes.ids, reason='Explicit conditional portfolio' if portfolio else None)
        baseline = self._finance(a.baseline_id)
        s = self._finance(a, confirmed=baseline.id)
        return baseline, s, quote

    def test_standalone_quote170_total_delta2550_difference1050(self):
        base, s, quote = self._quote_case()
        self.assertEqual(D(base.incremental_total), 1500)
        self.assertEqual(D(s.incremental_total), 2550)
        self.assertEqual(D(s.conditional_incremental_delta), 1050)
        self.assertEqual(sum(D(l.quantity) for l in base.line_ids), 100)
        self.assertEqual(sum(D(l.quantity) for l in s.line_ids), 170)
        self.assertFalse(s.reconciliation['alternatives_additive'])
        self.assertEqual(quote.state, 'draft')
        _logger.info('PR14_REFERENCE_F confirmed_delta1500 quote_scenario_delta2550 conditional_difference1050 not_additive')

    def test_portfolio_shared_allocation_and_baseline_not_double_added(self):
        base, s, quote = self._quote_case(True)
        self.assertEqual(sum(D(l.quantity) for l in s.line_ids), 200)
        self.assertEqual(D(s.incremental_total), 3000)
        self.assertEqual(D(s.conditional_incremental_delta), 1500)
        self.assertEqual(s.scenario, 'quotation_portfolio')

    def test_conditional_needs_confirmed_current_reference(self):
        self._sale(100)
        quote, line = self._sale(70, confirm=False)
        a = self._run(batch=self._batch12(), quotes=quote.ids)
        with self.assertRaises(UserError):
            self._finance(a)

    def test_quote_confirmation_invalidates_old_snapshot(self):
        base, s, quote = self._quote_case()
        quote.action_confirm()
        with self.assertRaises(UserError):
            self._batch12().with_user(self.users['manager']).get_current_financial_exposure(**s.scope)

    def test_quote_baseline_fx_method_must_match(self):
        base, s, quote = self._quote_case()
        with self.assertRaises(ValidationError):
            self._finance(s.cost_id.allocation_id, confirmed=base.id, method='date_specific')


@tagged('post_install', '-at_install')
class TestFinancialIntegrity(FinancialFixtures, TransactionCase):
    def test_same_inputs_idempotent_and_source_versions_retained(self):
        self._sale(100)
        s = self._finance()
        b = self._batch12().with_user(self.users['manager'])
        self.assertEqual(b.action_calculate_financial_exposure(**s.scope), s)
        self.assertEqual(b.get_current_financial_exposure(**s.scope), s)
        self.assertEqual(s.freshness, 'current')
        self.assertEqual(s.provenance['cost_version'], s.cost_id.version)
        self.assertEqual(s.provenance['sales_fingerprint'], s.sales_id.fingerprint)

    def test_demand_change_stales_preserves_old_amount(self):
        sale, line = self._sale(100)
        s = self._finance()
        line.product_uom_qty = 120
        with self.assertRaises(UserError):
            self._batch12().with_user(self.users['manager']).get_current_financial_exposure(**s.scope)
        self.assertEqual(D(s.incremental_total), 1500)

    def test_product_cost_change_stales(self):
        self.red.with_company(self.a).standard_price = 100
        self._quant(60)
        self._sale(100)
        s = self._finance()
        self.red.with_company(self.a).standard_price = 105
        with self.assertRaises(UserError):
            self._batch12().with_user(self.users['manager']).get_current_financial_exposure(**s.scope)

    def test_old_eligible_larger_tier_change_stales(self):
        self._commercial14()
        rule = self._rule(price=90, qty=100, uom=self.unit)
        self._batch12().action_validate_commercial_prices()
        self._sale(100)
        s = self._finance()
        rule.price = 91
        with self.assertRaises(UserError):
            self._batch12().with_user(self.users['manager']).get_current_financial_exposure(**s.scope)

    def test_failed_calculation_no_partial_snapshot(self):
        self._sale(100)
        inputs = self._inputs14()
        with patch.object(FinancialEngine, 'aggregate', side_effect=ValidationError('Injected reconciliation failure')):
            with self.assertRaises(ValidationError):
                self._finance(inputs=inputs)
        self.assertFalse(self.env[HEADER].search([('cost_id', '=', inputs[0].id)]))

    def test_publication_failure_rolls_back_created_header(self):
        self._sale(100)
        inputs = self._inputs14()
        with patch.object(type(self.env[LINE]), '_record', side_effect=ValidationError('Injected publication failure after header')):
            with self.assertRaises(ValidationError):
                self._finance(inputs=inputs)
        self.assertFalse(self.env[HEADER].search([('cost_id', '=', inputs[0].id)]))

    def test_source_ids_and_fx_method_strict(self):
        self._sale(100)
        c, s = self._inputs14()
        b = self._batch12().with_user(self.users['manager'])
        for args in ((True, s.id, 0, 'same_rate'), (c.id, s.id, 0, 'unknown'), (c.id, True, 0, 'same_rate')):
            with self.subTest(args=args), self.assertRaises(ValidationError):
                b.action_calculate_financial_exposure(*args)

    def test_reporting_residual_is_explained_no_balancing_line(self):
        self._commercial14(old='0.001', new='0.004')
        for _ in range(3):
            self._sale(1)
        s = self._finance()
        self.assertEqual(len(s.line_ids), 3)
        values = s.reconciliation['rounding']['revised_total']
        self.assertEqual(D(values['raw']), D('.012'))
        self.assertEqual(D(values['reported']), D('.01'))
        self.assertEqual(D(values['sum_reported_lines']), 0)
        self.assertEqual(D(values['reporting_residual']), D('.01'))

    def test_finance_can_calculate_without_editing_upstream(self):
        self._sale(100)
        s = self._finance(actor='finance')
        self.assertEqual(D(s.incremental_total), 1500)


@tagged('post_install', '-at_install')
class TestFinancialSecurity(FinancialFixtures, TransactionCase):
    def test_financial_export_escapes_source_order_formula(self):
        self.users['manager'].group_ids = [Command.link(self.env.ref('base.group_allow_export').id)]
        sale, line = self._sale(100)
        sale.name = '=1+1'
        s = self._finance()
        exported = s.line_ids.export_data(['order_name'])['datas']
        self.assertEqual(exported[0][0], "'=1+1")

    def test_sales_only_costs_denied_read_export_group(self):
        self._sale(100)
        s = self._finance()
        for model, ids in ((HEADER, s.ids), (LINE, s.line_ids.ids)):
            rec = self.env[model].with_user(self.users['sales']).browse(ids)
            for action in (lambda: rec.read(['id']), lambda: rec.export_data(['id']), lambda: rec._read_group([], ['company_id'], ['__count'])):
                with self.assertRaises(AccessError):
                    action()

    def test_auditor_read_only_cannot_collect_or_forge(self):
        self._sale(100)
        s = self._finance()
        self.assertEqual(self.env[HEADER].with_user(self.users['auditor']).browse(s.id).read(['id'])[0]['id'], s.id)
        with self.assertRaises(AccessError):
            self._batch12().with_user(self.users['auditor']).action_calculate_financial_exposure(**s.scope)
        with self.assertRaises(AccessError):
            self.env[HEADER].with_user(self.users['auditor']).create({'state': 'fully_verified'})

    def test_purchase_without_customer_contract_scope_denied(self):
        self._sale(100)
        c, s = self._inputs14()
        with self.assertRaises(AccessError):
            self._batch12().action_calculate_financial_exposure(c.id, s.id)

    def test_foreign_selected_company_cannot_read_export(self):
        self._sale(100)
        s = self._finance()
        foreign = s.with_context(allowed_company_ids=self.b.ids)
        for action in (lambda: foreign.read(['provenance']), lambda: foreign.export_data(['line_ids/baseline_unit_cost'])):
            with self.assertRaises(AccessError):
                action()

    def test_public_and_portal_no_raw_financial_access(self):
        self._sale(100)
        s = self._finance()
        portal = self.env['res.users'].with_context(no_reset_password=True).create({'name': 'PR14 Portal', 'login': 'pr14.portal@example.invalid', 'company_id': self.a.id, 'company_ids': [Command.set(self.a.ids)], 'group_ids': [Command.set(self.env.ref('base.group_portal').ids)]})
        for user in (portal, self.env.ref('base.public_user')):
            with self.assertRaises(AccessError):
                self.env[HEADER].with_user(user).browse(s.id).read(['baseline_total'])

    def test_immutable_write_copy_delete_nested_and_context(self):
        self._sale(100)
        s = self._finance()
        for rec in (s, s.line_ids):
            for action in (lambda: rec.write({'batch_id': self._batch12().id}), lambda: rec.copy(), lambda: rec.unlink()):
                with self.assertRaises(AccessError):
                    action()
        with self.assertRaises(AccessError):
            s.with_context(default_company_id=self.b.id, financial_verified=True).write({'line_ids': [Command.create({'baseline_unit_cost': '0'})]})

    def test_sales_grant_revocation_hides_financial_history_children(self):
        self._sale(100)
        s = self._finance()
        g = self.env[SALES_GRANT].search([('company_id', '=', self.a.id), ('user_id', '=', self.users['manager'].id)])
        g.write({'active': False, 'reason': 'Withdraw customer-commercial scope'})
        self.assertFalse(self.env[HEADER].with_user(self.users['manager']).search([('id', '=', s.id)]))
        self.assertFalse(self.env[LINE].with_user(self.users['manager']).search([('snapshot_id', '=', s.id)]))


@tagged('post_install', '-at_install')
class TestFinancialWorkload(FinancialFixtures, TransactionCase):
    def test_100_entries_reconcile_and_measure(self):
        for _ in range(100):
            self._sale(10)
        c, s = self._inputs14()
        start = time.perf_counter()
        f = self._finance(inputs=(c, s))
        elapsed = time.perf_counter()-start
        self._assert_totals(f, '100000', '115000', '15000')
        self.assertEqual(f.line_count, 100)
        _logger.info('PR14_WORKLOAD financial_entries=100 seconds=%.3f baseline=100000 revised=115000 delta=15000', elapsed)
