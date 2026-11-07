"""PR16 independent controls over real PR08-15 synthetic source fixtures."""
import copy
import logging
import time
from decimal import Decimal as D
from unittest.mock import patch
from psycopg2.extras import Json
from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from .test_profitability import MarginFixtures, POLICY, RULES
from .test_commercial_validation import MODULE
from ..models.reconciliation import HEADER,CHECK,ISSUE,REVIEW,Reconciler
from ..models.reconciliation_controls import Controls, metric, readiness, independent_profit, independent_risk

_logger=logging.getLogger(__name__)


@tagged('post_install','-at_install')
class TestReconciliationMath(TransactionCase):
    def test_independent_profit_margin_erosion(self):
        v=independent_profit('28000','20000','21500')
        self.assertEqual(D(v['baseline_gross_profit']),8000);self.assertEqual(D(v['revised_gross_profit']),6500)
        self.assertEqual(D(v['gross_profit_change']),-1500);self.assertEqual(D(v['gross_profit_reduction']),1500)
        self.assertAlmostEqual(float(v['baseline_margin_percent']),28.5714285714,places=8)
        self.assertAlmostEqual(float(v['revised_margin_percent']),23.2142857143,places=8)
        self.assertAlmostEqual(float(v['margin_erosion_points']),5.3571428571,places=8)
        self.assertEqual(D(v['profit_reduction_percent']),D('18.75'))

    def test_typed_numeric_and_canonical_evidence(self):
        c=Controls();c.equation('ALLOCATION_QUANTITY_MISMATCH','quantity_integrity','source','200','220','.01','quantity')
        v=c.checks[0];self.assertEqual(v['status'],'fail');self.assertEqual(v['difference'],20)
        self.assertEqual(v['values']['difference'],'20');self.assertTrue(v['numeric_known'])

    def test_missing_is_blocked_not_zero_pass(self):
        c=Controls();c.equation('MISSING_COST','cost','source',None,'0','.01')
        self.assertEqual(c.checks[0]['status'],'blocked');self.assertFalse(c.checks[0]['numeric_known'])
        self.assertIsNone(c.checks[0]['values']['expected'])

    def test_defined_currency_and_quantity_tolerances(self):
        c=Controls();c.equation('MONEY','cost','a','100','100.004','.01');c.equation('MATERIAL','cost','b','100','101','.01')
        self.assertEqual([v['status'] for v in c.checks],['pass','fail'])

    def test_ready_requires_all_p0_controls_and_demand(self):
        c=Controls();c.record('P0','quantity','a','pass')
        self.assertEqual(readiness(c.checks,True)['readiness'],'ready_for_financial_review')
        self.assertEqual(readiness(c.checks,False)['state'],'no_eligible_demand')
        for status in ('blocked','not_run','stale','fail'):
            c.checks[0]['status']=status
            self.assertNotEqual(readiness(c.checks,True)['readiness'],'ready_for_financial_review')

    def test_critical_failure_blocks_not_overridden_by_many_passes(self):
        c=Controls()
        for i in range(20):c.record(str(i),'quantity',str(i),'pass')
        c.record('DUPLICATE','quantity','dup','fail')
        self.assertEqual(readiness(c.checks,True)['readiness'],'blocked')

    def test_seventy_five_percent_quantity_not_amount_confidence(self):
        v=metric(150,200,'Exact product/UoM cost-known quantity')
        self.assertEqual(D(v['percent']),75);self.assertEqual(v['numerator'],'150');self.assertEqual(v['denominator'],'200')
        self.assertIn('never monetary confidence',v['unit'])

    def test_empty_metric_not_one_hundred_percent(self):
        self.assertIsNone(metric(0,0,'no demand')['percent'])
        self.assertIsNone(independent_profit('0','10','20')['revised_margin_percent'])

    def test_independent_risk_boundaries_and_preexisting(self):
        for margin,risk in [('14.99','critical'),('15','critical'),('15.01','warning'),('25','warning'),('25.01','normal')]:
            v=independent_profit('100',str(100-D(margin)),str(100-D(margin)))
            self.assertEqual(independent_risk(v,POLICY,RULES,True,[])[0]['risk_status'],risk)
        v=independent_profit('100','90','91')
        self.assertEqual(independent_risk(v,POLICY,RULES,True,[])[0]['revision_effect'],'existing_critical_worsened')

    def test_identity_duplicates_not_equal_amounts(self):
        c=Controls();c.unique('QUANTS','supply','a',[1,1]);c.unique('LEGITIMATE','cost','b',[(1,'100'),(2,'100')])
        self.assertEqual([v['status'] for v in c.checks],['fail','pass'])


class ReconciliationFixtures(MarginFixtures):
    def _policy16(self,projection=True):
        return self._policy15(reconciliation_basis_policy='documented_projection' if projection else 'strict_verified')

    def _reconcile(self,margin=None,actor='finance'):
        m=margin or self._margin()
        return m.batch_id.with_user(self.users[actor]).action_run_reconciliation(m.id)

    def _reference16(self,tier=False,projection=True):
        self._policy16(projection);self._commercial14(tiers=[(1,115),(100,109)] if tier else None)
        self.red.with_company(self.a).standard_price=100;self._quant(60)
        po,line=self._po(40,100);self._sales15(200)
        self._assess12(self._row12(self._collect12(),line))
        return self._reconcile()

    def _corrupt(self,row,field,value):
        # Deliberate immutable-evidence corruption in disposable transaction only.
        # Service must detect the inconsistency, not trust stored VERIFIED labels.
        row.ensure_one();self.env.flush_all()
        self.env.cr.execute('UPDATE '+row._table+' SET '+field+'=%s WHERE id=%s',[Json(value) if row._fields[field].type=='json' else value,row.id])
        row.invalidate_recordset([field])

    def _checks(self,run,code):return run.check_ids.filtered(lambda v:v.code==code)


@tagged('post_install','-at_install')
class TestReconciliationReferences(ReconciliationFixtures,TransactionCase):
    def test_full_reference_independent_equations_ready_projection_policy(self):
        r=self._reference16();m=r.margin_id
        failed=r.check_ids.filtered(lambda v:v.status not in ('pass','not_applicable'))
        self.assertFalse(failed,[(v.code,v.source_key,v.status,v.values) for v in failed])
        self.assertEqual(r.state,'fully_reconciled');self.assertEqual(r.readiness,'ready_for_financial_review')
        self.assertEqual(r.current_readiness,r.readiness)
        self.assertEqual((D(m.net_revenue),D(m.baseline_cost),D(m.revised_cost)),(28000,20000,21500))
        self.assertEqual((D(m.baseline_gross_profit),D(m.revised_gross_profit)),(8000,6500))
        self.assertEqual(sum(D(d.outstanding) for d in m.allocation_id.demand_ids),200)
        self.assertEqual(sorted(D(v.quantity) for v in m.financial_id.line_ids),[40,60,100])
        self.assertEqual(r.metrics['readiness_basis_policy'],'documented_projection')
        self.assertEqual(m.state,'scenario_only');self.assertFalse(r.exception_ids)
        self.assertEqual(len(r.provenance['source_versions']),7)
        _logger.info('PR16_REFERENCE demand200 stock60 protected40 procurement100 revenue28000 baseline20000 revised21500 delta1500 profits8000/6500 margins28.57142857/23.21428571 erosion5.35714286pp READY_FOR_FINANCIAL_REVIEW documented_projection not_approved checks=%s',len(r.check_ids))

    def test_strict_default_estimates_do_not_become_ready(self):
        r=self._reference16(projection=False)
        self.assertEqual(self._checks(r,'FINANCIAL_BASIS_READINESS').status,'blocked')
        self.assertEqual(r.readiness,'not_ready')

    def test_moq100_reference_delta900(self):
        r=self._reference16(tier=True)
        self.assertEqual(D(r.margin_id.financial_id.incremental_total),900)
        self.assertEqual(self._checks(r,'APPLICABLE_MOQ_DATE_TIER').status,'pass')
        self.assertEqual(r.readiness,'ready_for_financial_review')

    def test_wrong_quantity220_for200_blocks(self):
        r=self._reference16();a=r.margin_id.allocation_id
        entry=a.entry_ids.filtered(lambda v:v.allocation_type=='new_procurement_requirement')
        self._corrupt(entry,'quantity','120');new=self._reconcile(r.margin_id)
        check=self._checks(new,'ALLOCATION_QUANTITY_MISMATCH')
        self.assertEqual(check.status,'fail');self.assertEqual(check.difference,20)
        self.assertEqual(new.readiness,'blocked')
        _logger.info('PR16_FAILURE_A quantity200_vs220 difference20 ALLOCATION_QUANTITY_MISMATCH BLOCKED')

    def test_duplicate_physical_quant_with_different_label_detected(self):
        r=self._reference16();bucket=r.margin_id.allocation_id.supply_snapshot_id.bucket_ids.filtered(lambda v:v.source_key.startswith('quant:'))
        fields=['batch_id','snapshot_id','source_key','product_id','product_name','uom_id','warehouse_id','kind','physical','reserved','unreserved','eligible_free','incoming','protected','contributes_quantity','quantity_verified','cost_basis','unit_cost_reference','confidence','evidence']
        vals=bucket.read(fields,load=None)[0];vals.pop('id');vals['source_key']='quant:999999'
        self.env[bucket._name]._record(vals)
        new=self._reconcile(r.margin_id)
        self.assertEqual(self._checks(new,'UNIQUE_PHYSICAL_QUANT').status,'fail');self.assertEqual(new.readiness,'blocked')

    def test_wrong_protected_po_revised115_detected(self):
        r=self._reference16();line=r.margin_id.financial_id.line_ids.filtered(lambda v:v.cost_line_id.confidence=='verified_commercial_basis')
        self.assertEqual(len(line),1)
        self._corrupt(line,'revised_unit_cost','115');self._corrupt(line,'revised_extended_cost','4600')
        new=self._reconcile(r.margin_id);checks=self._checks(new,'UNCHANGED_REVISED_SOURCE_COST')
        self.assertTrue(checks.filtered(lambda v:v.status=='fail'));self.assertEqual(new.readiness,'blocked')
        _logger.info('PR16_FAILURE_B protected40_price100_vs115 BLOCKED no_source_repair')

    def test_wrong_revenue30000_not_silently_corrected(self):
        r=self._reference16();line=r.margin_id.line_ids
        self._corrupt(line,'net_revenue','30000');new=self._reconcile(r.margin_id)
        self.assertEqual(self._checks(new,'REVENUE_SOURCE_MATCH').status,'fail')
        self.assertEqual(new.readiness,'blocked');self.assertEqual(line.net_revenue,'30000')

    def test_unknown_fifo_preserves_incremental_delta_no_readiness(self):
        self._policy16();self.red.categ_id.with_company(self.a).property_cost_method='fifo';self._quant(60);self._sales15(160)
        r=self._reconcile();self.assertEqual(D(r.margin_id.financial_id.incremental_total),1500)
        self.assertFalse(r.margin_id.revised_gross_profit);self.assertEqual(r.readiness,'not_ready')
        self.assertTrue(r.high_exception_count)
        _logger.info('PR16_FAILURE_C unknown_FIFO delta1500 complete_cost_NULL margin_NULL NOT_READY')

    def test_missing_company_sales_fx_not_ready(self):
        self._policy16();so,line=self._sales15(100,20,confirm=False)
        pl=self.env['product.pricelist'].create(dict(name='PR16 USD',company_id=self.a.id,currency_id=self.usd.id));so.pricelist_id=pl;so.action_confirm()
        r=self._reconcile();self.assertFalse(r.margin_id.net_revenue)
        self.assertEqual(self._checks(r,'SALES_COMPANY_FX').status,'blocked');self.assertEqual(r.readiness,'not_ready')
        _logger.info('PR16_FAILURE_D missing_sales_FX NOT_READY no_1_to_1')

    def test_unknown_po_protection_not_invented(self):
        self._policy16();self._po(40,100);self._sales15(40)
        r=self._reconcile();self.assertEqual(self._checks(r,'PO_PROTECTION_UNVERIFIED').status,'blocked')
        self.assertEqual(r.readiness,'not_ready');self.assertFalse(r.margin_id.revised_cost)
        _logger.info('PR16_FAILURE_F unknown_PO_protection NOT_READY no_price_substitution')

    def test_forged_financial_sum_and_risk_detected_independently(self):
        r=self._reference16();m=r.margin_id
        self._corrupt(m.financial_id,'incremental_total','1501');self._corrupt(m,'risk_status','normal')
        new=self._reconcile(m)
        self.assertEqual(self._checks(new,'FINANCIAL_TOTAL_INCREMENTAL_TOTAL').status,'fail')
        self.assertTrue(self._checks(new,'RISK_RISK_STATUS').filtered(lambda v:v.status=='fail'))
        self.assertEqual(new.readiness,'blocked')

    def test_wrong_variant_cost_and_aggregate_detected(self):
        r=self._reference16();line=r.margin_id.financial_id.line_ids[:1]
        wrong=self.env['product.product'].create(dict(name='PR16 wrong exact variant',company_id=self.a.id))
        self._corrupt(line,'product_id',wrong.id)
        new=self._reconcile(r.margin_id)
        self.assertTrue(self._checks(new,'FINANCIAL_EXACT_COST_SOURCE').filtered(lambda v:v.status=='fail'))
        self.assertEqual(new.readiness,'blocked')

    def test_capacity_overconsumption_detected(self):
        r=self._reference16();a=r.margin_id.allocation_id;caps=copy.deepcopy(a.source_capacities)
        first=next(iter(caps));caps[first]['initial']='1';self._corrupt(a,'source_capacities',caps)
        new=self._reconcile(r.margin_id)
        self.assertTrue(self._checks(new,'SUPPLY_CAPACITY_EXCEEDED').filtered(lambda v:v.status=='fail'))
        self.assertEqual(new.readiness,'blocked')

    def test_false_company_total_and_percentage_average_detected(self):
        r=self._reference16();aggregate=r.margin_id.aggregate_ids.filtered(lambda v:v.dimension=='company')
        self._corrupt(aggregate,'revised_margin_percent','40')
        new=self._reconcile(r.margin_id)
        self.assertTrue(self._checks(new,'PROFIT_REVISED_MARGIN_PERCENT').filtered(lambda v:v.status=='fail'))
        self.assertEqual(new.readiness,'blocked')

    def test_no_demand_not_automatic100percent(self):
        self._policy16();r=self._reconcile()
        self.assertEqual(r.state,'no_eligible_demand');self.assertEqual(r.readiness,'not_ready')
        self.assertIsNone(r.metrics['margin_lines']['percent'])

    def test_global_discount_missing_basis_blocks(self):
        self._policy16();so,line=self._sales15(100);discount=self.env['product.product'].create({'name':'PR16 discount','type':'service'});self.a.sale_discount_product_id=discount
        self.env['sale.order.line'].create(dict(order_id=so.id,product_id=discount.id,product_uom_qty=1,price_unit=-1000,tax_ids=[Command.clear()]))
        r=self._reconcile();self.assertFalse(r.margin_id.net_revenue);self.assertEqual(r.readiness,'not_ready')

    def test_real_reservation_and_free_stock_counted_once(self):
        self._policy16();self.red.with_company(self.a).standard_price=100;self._quant(80)
        so,line=self._sales15(100);self._reservation(line,20)
        r=self._reconcile();d=r.margin_id.allocation_id.demand_ids
        self.assertEqual((D(d.reserved),D(d.free_stock),D(d.new_procurement)),(20,60,20))
        self.assertTrue(all(v.status=='pass' for v in self._checks(r,'STOCK_PHYSICAL_SPLIT')))
        self.assertEqual(r.readiness,'ready_for_financial_review')

    def test_stock_only_optional_purchase_snapshot_is_not_missing_evidence(self):
        self._policy16();self.red.with_company(self.a).standard_price=100;self._quant(100);self._sales15(100)
        b=self._batch12();a=self._run(batch=b);cost=b.action_attribute_costs(a.id,0,'2026-11-05')
        sales=a.with_user(self.users['manager']).action_collect_sales_terms();m=self._margin(self._finance(inputs=(cost,sales)))
        r=self._reconcile(m)
        self.assertFalse(cost.purchase_id.id);self.assertEqual(r.readiness,'ready_for_financial_review')
        self.assertEqual(len(r.provenance['source_versions']),6)

    def test_out_of_scope_reservation_not_reused(self):
        self._policy16();self.red.with_company(self.a).standard_price=100;self._quant(80)
        unrelated,ul=self._sales15(20);self._reservation(ul,20);selected,sl=self._sales15(100)
        a=self._run(batch=self._batch12(),confirmed=selected.ids);m=self._margin(self._finance(a));r=self._reconcile(m)
        d=a.demand_ids;self.assertEqual(D(d.reserved),0);self.assertEqual(D(d.free_stock),60);self.assertEqual(D(d.new_procurement),40)
        self.assertEqual(r.readiness,'ready_for_financial_review')

    def test_partial_po_receipt_open60_not_original100_plus_backorder(self):
        self._policy16();self.red.with_company(self.a).standard_price=100
        po,line=self._po(100,100);picking=po.picking_ids[:1];picking.move_ids.quantity=40;picking.move_ids.picked=True;picking._action_done()
        self._sales15(100);self._assess12(self._row12(self._collect12(),line))
        r=self._reconcile();b=r.margin_id.allocation_id.supply_snapshot_id.bucket_ids.filtered(lambda v:v.source_key=='po_line:'+str(line.id))
        self.assertEqual(D(b.incoming),60)
        self.assertEqual(self._checks(r,'PO_SUPPLIER_UNRECEIVED').status,'pass')
        self.assertEqual(r.readiness,'ready_for_financial_review')


@tagged('post_install','-at_install')
class TestReconciliationLifecycle(ReconciliationFixtures,TransactionCase):
    def test_idempotent_current_run_and_no_duplicate_checks_exceptions(self):
        r=self._reference16();self.assertEqual(self._reconcile(r.margin_id),r)
        self.assertEqual(r.batch_id.get_current_reconciliation(**r.scope),r)
        self.assertEqual(len(r.check_ids),len(set(r.check_ids.mapped('check_key'))))
        self.assertEqual(r.version,1)

    def test_stale_current_readiness_after_native_sales_price_change(self):
        r=self._reference16();m=r.margin_id
        m.line_ids.sale_line_id.price_unit=150
        self.assertEqual(r.freshness,'stale');self.assertEqual(r.current_readiness,'not_ready')
        self.assertEqual(r.readiness,'ready_for_financial_review')
        with self.assertRaises(UserError):r.batch_id.get_current_reconciliation(**r.scope)
        new=self._reconcile(m);self.assertEqual(new.state,'stale');self.assertEqual(new.readiness,'not_ready')
        self.assertEqual(new.previous_id,r)

    def test_append_only_review_notes_never_make_pass_or_ready(self):
        r=self._reference16(projection=False);issue=r.exception_ids.filtered(lambda v:v.code=='FINANCIAL_BASIS_READINESS')
        event=issue.action_record_review('revalidation_required','Source reviewed','Finance evidence #16')
        self.assertEqual(issue.status,'revalidation_required');self.assertEqual(r.readiness,'not_ready')
        self.assertEqual(issue.action_record_review('revalidation_required','Source reviewed','Finance evidence #16'),event)
        with self.assertRaises(ValidationError):issue.action_record_review('waived_nonblocking','Ignore','Note')
        with self.assertRaises(ValidationError):issue.action_record_review('closed_verified','Fixed','Note')
        self.assertEqual(issue.check_id.status,'blocked')
        wizard=self.env['vendor.price.revision.reconciliation.review.wizard'].with_user(self.users['finance']).create(dict(
            batch_id=r.batch_id.id,exception_id=issue.id,event='in_review',reason='UI review without optional owner',evidence='Finance review evidence #16'))
        wizard.action_run()
        self.assertEqual(issue.status,'in_review');self.assertEqual(r.readiness,'not_ready')

    def test_verified_closure_requires_later_matching_pass(self):
        r=self._reference16();line=r.margin_id.line_ids
        original=line.net_revenue;self._corrupt(line,'net_revenue','30000');failed=self._reconcile(r.margin_id)
        issue=failed.exception_ids.filtered(lambda v:v.code=='REVENUE_SOURCE_MATCH')
        self.assertEqual(len(issue),1)
        self._corrupt(line,'net_revenue',original);current=self._reconcile(r.margin_id)
        self.assertEqual(current.readiness,'ready_for_financial_review')
        event=issue.action_record_review('closed_verified','Corrected and rechecked','Current exact check PASS',verification_run_id=current.id)
        self.assertEqual(event.event,'closed_verified');self.assertEqual(issue.status,'closed_verified')
        self.assertEqual(failed.readiness,'blocked')
        self._corrupt(line,'net_revenue','30000');reopened=self._reconcile(r.margin_id)
        self.assertEqual(reopened.readiness,'blocked');self.assertTrue(reopened.exception_ids.filtered(lambda v:v.code==issue.code))
        self.assertEqual(issue.status,'closed_verified')

    def test_owner_assignment_company_and_no_new_source_rights(self):
        r=self._reference16(projection=False);issue=r.exception_ids[:1]
        event=issue.action_record_review('assigned','Finance owner','Auditable assignment',owner_id=self.users['finance'].id)
        self.assertEqual(event.owner_id,self.users['finance'])
        with self.assertRaises(AccessError):issue.action_record_review('assigned','Wrong company','Invalid owner',owner_id=self.users['purchase_b'].id)
        self.assertIn(issue,self.env[ISSUE].search([('status','=','assigned')]))
        self.assertIn(issue,self.env[ISSUE].search([('assigned_user_id','=',self.users['finance'].id)]))

    def test_atomic_publication_failure_retry_no_partial_success(self):
        self._policy16(False);self._sales15(100);m=self._margin()
        def retained():
            return {name:self.env[name].search([],order='id').read([
                field for field,definition in self.env[name]._fields.items()
                if definition.store and definition.type!='binary' and not definition.related],load=None)
                for name in (HEADER,CHECK,ISSUE,REVIEW)}
        before=retained()
        with patch.object(type(self.env[ISSUE]),'_record',side_effect=UserError('PR16 injected exception publication failure')):
            with self.assertRaises(UserError):self._reconcile(m)
        self.assertEqual(retained(),before)
        self.assertFalse(self.env[HEADER].search([('batch_id','=',m.batch_id.id)]))
        self.assertTrue(self._reconcile(m).check_ids)

    def test_policy_change_stales_only_relevant_sources(self):
        r=self._reference16();old=r.provenance
        self._policy16(False)
        self.assertEqual(r.current_readiness,'not_ready');self.assertEqual(r.provenance,old)

    def test_source_ids_strict_and_no_public_ready_forgery(self):
        r=self._reference16();b=r.batch_id
        for value in (False,0,-1,str(r.margin_id.id)):
            with self.assertRaises(ValidationError):b.action_run_reconciliation(value)
        for row in (r,r.check_ids,r.exception_ids,self.env[REVIEW]):
            with self.assertRaises(AccessError):row.write({'readiness':'ready_for_financial_review'})
        with self.assertRaises(AccessError):self.env[HEADER].with_context(default_company_id=self.b.id).create(dict(batch_id=b.id,name='Forged',readiness='ready_for_financial_review'))


@tagged('post_install','-at_install')
class TestReconciliationScenarios(ReconciliationFixtures,TransactionCase):
    def test_conditional_own_scope_not_confirmed_double_add(self):
        self._policy16();self._sales15(100);q,line=self._sales15(70,confirm=False)
        a=self._run(batch=self._batch12());f=self._finance(a);m=self._margin(f)
        qa=self._run(batch=self._batch12(),quotes=q.ids);qf=self._finance(qa,confirmed=f.id);qm=self._margin(qf,confirmed=m.id)
        r=self._reconcile(qm);self.assertEqual(self._checks(r,'CONDITIONAL_EXACT_BASELINE').status,'pass')
        self.assertEqual(self._checks(r,'CONDITIONAL_INCREMENTAL_PROFIT').status,'pass')
        self.assertEqual(r.readiness,'ready_for_financial_review')
        provenance=copy.deepcopy(qm.provenance);provenance['alternatives_additive']=True;self._corrupt(qm,'provenance',provenance)
        bad=self._reconcile(qm);self.assertEqual(self._checks(bad,'ALTERNATIVES_NONADDITIVE').status,'fail')
        self.assertEqual(bad.readiness,'blocked')
        _logger.info('PR16_FAILURE_E inappropriate_quote_addition BLOCKED distinct_scenario_baselines')


@tagged('post_install','-at_install')
class TestReconciliationSecurity(ReconciliationFixtures,TransactionCase):
    def test_finance_initiates_purchase_manager_cannot_force_run(self):
        r=self._reference16()
        with self.assertRaises(AccessError):self._reconcile(r.margin_id,actor='manager')
        self.assertEqual(r.collected_by,self.users['finance'])

    def test_sales_purchase_only_read_export_group_denial(self):
        r=self._reference16(projection=False)
        for role in ('sales','purchase'):
            for row in (r,r.check_ids,r.exception_ids):
                denied=row.with_user(self.users[role])
                with self.assertRaises(AccessError):denied.read(['id'])
                with self.assertRaises(AccessError):denied.export_data(['id'])
                if role=='sales':
                    with self.assertRaises(AccessError):denied._read_group([],[],['__count'])
                else:
                    self.assertEqual(denied._read_group([],[],['__count'])[0][0],0)

    def test_auditor_read_only_no_review_or_readiness_mutation(self):
        r=self._reference16(projection=False);u=self.users['auditor']
        self.assertEqual(r.with_user(u).readiness,r.readiness)
        with self.assertRaises(AccessError):self._reconcile(r.margin_id,actor='auditor')
        with self.assertRaises(AccessError):r.exception_ids[:1].with_user(u).action_record_review('in_review','Note','Evidence')

    def test_portal_public_and_other_company_denial(self):
        r=self._reference16(projection=False)
        portal=self.env['res.users'].with_context(no_reset_password=True).create(dict(name='PR16 Portal',login='pr16.portal@example.invalid',company_id=self.a.id,company_ids=[Command.set(self.a.ids)],group_ids=[Command.set(self.env.ref('base.group_portal').ids)]))
        for u in (portal,self.env.ref('base.public_user')):
            for row in (r,r.check_ids,r.exception_ids):
                with self.assertRaises(AccessError):row.with_user(u).read(['id'])
        with self.assertRaises(AccessError):r.with_user(self.users['finance']).with_context(allowed_company_ids=self.b.ids).read()

    def test_revoked_customer_scope_hides_children_and_evidence(self):
        from ..models.sales_exposure import GRANT
        r=self._reference16(projection=False);rows=(r,r.check_ids,r.exception_ids);b=r.batch_id;scope=r.scope
        self.env[GRANT].search([('company_id','=',self.a.id),('user_id','=',self.users['finance'].id)]).write(dict(active=False,reason='PR16 customer scope revoke'))
        for row in rows:
            with self.assertRaises(AccessError):row.with_user(self.users['finance']).read()
        with self.assertRaises(AccessError):b.with_user(self.users['finance']).get_current_reconciliation(**scope)

    def test_exact_source_drilldown_and_export_authorization(self):
        r=self._reference16();check=self._checks(r,'REVENUE_SOURCE_MATCH')
        action=check.action_open_source();self.assertEqual(action['res_model'],'vendor.price.revision.margin.line')
        self.assertEqual(action['res_id'],r.margin_id.line_ids.id)
        with self.assertRaises(AccessError):check.with_user(self.users['sales']).action_open_source()
        self.users['finance'].group_ids=[Command.link(self.env.ref('base.group_allow_export').id)]
        self.assertTrue(r.check_ids[:1].export_data(['code','values'])['datas'])


@tagged('post_install','-at_install')
class TestReconciliationWorkload(ReconciliationFixtures,TransactionCase):
    def test_100_lines_actual_control_count_and_time(self):
        self._policy16()
        for i in range(100):self._sales15(10)
        m=self._margin();start=time.perf_counter();r=self._reconcile(m);seconds=time.perf_counter()-start
        self.assertEqual(r.readiness,'ready_for_financial_review');self.assertFalse(r.exception_ids)
        self.assertGreater(len(r.check_ids),1000);self.assertEqual(r.metrics['margin_lines']['denominator'],'100')
        _logger.info('PR16_WORKLOAD lines=100 seconds=%.3f controls=%s exceptions=0 ready_for_financial_review',seconds,len(r.check_ids))
