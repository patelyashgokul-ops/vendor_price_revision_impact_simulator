"""PR23 pure comparison boundaries and genuine uncommitted execution exclusion."""
from unittest.mock import patch
from types import SimpleNamespace
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from .test_application_execution import ExecutionFixtures
from ..models import monitor_math as math
from ..models import monitor_service as service
from ..models.monitor_models import RUN, CHECK, INCIDENT, EVENT, CORRECTION


@tagged('post_install','-at_install')
class TestMonitorMath(TransactionCase):
    def test_stepwise_successor_price_boundary_then_price_and_wrong_tier(self):
        # Isolate scope comparison only. Real immutable authorization eligibility
        # is exercised separately by the committed independent-approval probe.
        values=dict(partner_id=1,product_tmpl_id=2,product_id=3,company_id=4,min_qty='100',price='109',
            currency_id=5,uom_id=6,date_start='2026-10-30',date_end=False,discount='0',delay=1,sequence=1,
            product_code=False,product_name=False)
        def event(i,after,boundary=False):
            return SimpleNamespace(id=i,target_id=77,execution_id=SimpleNamespace(id=i,verified_at=i,state='VERIFIED'),
                observed_after_values=after,plan_line_id=SimpleNamespace(evidence={'boundary':boundary}))
        events=[event(1,values),event(2,dict(values,price='112')),
            event(3,dict(values,price='112',date_end='2026-10-31'),True),
            event(4,dict(values,price='115',date_end='2026-10-31'))]
        engine=service.Observation.__new__(service.Observation)
        engine.history={77:events};engine.cache={}
        with patch.object(service,'historical',return_value=True):
            selected,incomplete=engine.successor(events[0])
            self.assertIs(selected,events[3]);self.assertFalse(incomplete)
            events.append(event(5,dict(values,price='117',date_end='2026-10-31',min_qty='10')))
            selected,incomplete=engine.successor(events[0])
            self.assertIs(selected,events[3]);self.assertTrue(incomplete)

    def test_numeric_representation_and_real_storage_precision(self):
        row=dict(partner_id=1,product_tmpl_id=2,product_id=3,company_id=4,min_qty='100',price='109.0000',
            currency_id=5,uom_id=6,date_start='2026-11-01',date_end=False,discount='0',delay=1,sequence=1,
            product_code=False,product_name=False)
        self.assertFalse(math.differences(row,dict(row,price='109.000000')))
        self.assertEqual(set(math.differences(row,dict(row,price='109.05'))),{'price'})
        self.assertEqual(set(math.differences(row,dict(row,currency_id=8,min_qty='10'))),{'currency_id','min_qty'})
        self.assertFalse(math.compatible(row,dict(row,product_id=False)))
        self.assertTrue(math.compatible(row,dict(row,price='112')))

    def test_monitor_schema_cron_inactive_and_direct_evidence_authorship_denied(self):
        cron=self.env.ref('vendor_price_revision_impact_simulator.cron_mon23_revalidation')
        self.assertFalse(cron.active)
        for model in (RUN,CHECK,INCIDENT,EVENT,CORRECTION):
            with self.subTest(model=model):
                with self.assertRaises(AccessError):self.env[model].create({})
                with self.assertRaises(AccessError):self.env[model]._record({})


@tagged('post_install','-at_install')
class TestMonitorPending(ExecutionFixtures,TransactionCase):
    def test_pending_commit_is_never_a_successful_monitor_baseline(self):
        _,_,plan=self._plan22()
        receipt=self._apply22(plan)
        self.assertEqual(receipt.state,'PENDING_COMMIT')
        native=self.env['product.supplierinfo']
        with patch.object(type(native),'write',side_effect=AssertionError('MONITOR_NATIVE_WRITE')), \
             patch.object(type(native),'create',side_effect=AssertionError('MONITOR_NATIVE_CREATE')), \
             patch.object(type(native),'unlink',side_effect=AssertionError('MONITOR_NATIVE_UNLINK')):
            run=receipt.action_check_applied_price_integrity()
        self.assertEqual(run.check_ids.status,'BLOCKED')
        self.assertEqual(run.passed_count,0)
        self.assertIn('HISTORICAL_EVIDENCE_INTEGRITY',run.check_ids.codes)
