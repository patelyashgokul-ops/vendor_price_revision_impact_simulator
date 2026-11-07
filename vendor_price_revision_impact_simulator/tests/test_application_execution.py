"""PR22 genuine approval -> native operation, atomic failure and security."""
import logging
from unittest.mock import patch
from datetime import timedelta
from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from .test_application_planning import ApplicationFixtures
from ..models.application_engine import snapshot
from ..models.execution import EXEC, LINE
from ..models import execution as module

_logger = logging.getLogger(__name__)
PREFIX = 'vendor_price_revision_impact_simulator.'


class ExecutionFixtures(ApplicationFixtures):
    def _operator22(self, native=True):
        user = self.users['finance']
        groups = [self.env.ref(PREFIX+'group_vpr_pricing_operator').id]
        if native: groups.append(self.env.ref('purchase.group_purchase_manager').id)
        user.group_ids = [Command.link(g) for g in groups]
        return user

    def _plan22(self, operation='update', native=True, **policy):
        self.op22 = self._operator22(native)
        scenario, request = self._approved21(operation=operation, **policy)
        return scenario, request, request.action_run_application_dry_run().with_user(self.op22)

    def _apply22(self, plan):
        return plan.action_apply_approved_vendor_prices(True, plan.fingerprint)

    def _commercial14(self,*args,**kw):
        if getattr(self,'bulk22',False):
            kw.update(old=115,new=115,old_qty=1,old_start='2026-10-30',tiers=[(100+i,115) for i in range(10)])
            return super(ApplicationFixtures,self)._commercial14(*args,**kw)
        return super()._commercial14(*args,**kw)

    def _rule(self,*args,**kw):
        rule = super()._rule(*args,**kw)
        if getattr(self,'nullable22',False):
            # A real native rule without explicit discount can store SQL NULL;
            # original-user ORM material evidence correctly reads it as zero.
            rule.flush_recordset()
            self.env.cr.execute('UPDATE product_supplierinfo SET discount=NULL WHERE id=%s',[rule.id])
            rule.invalidate_recordset()
        if getattr(self,'bulk22',False):
            self.target22 = rule.copy(dict(min_qty=100,price=100))
        return rule

    def _bulk22(self):
        self.bulk22=True; self.op22=self._operator22()
        scenario=self._prepare18(**self._policy20())
        scenario.action_set_assumptions([self._spec(value='109',effective_date='2026-10-30',commitment_date='2026-11-05',timing_evidence='Explicit bulk vendor period')],'Exact mixed update/create scope')
        scenario.action_calculate_scenario();r=self._request19(scenario,'supplier_scenario')
        rows=r.batch_id.row_ids.sorted('source_row');intents=[]
        for i,row in enumerate(rows):
            intent=dict(row_id=row.id,operation='update' if i==0 else 'create',target_uom_id=self.unit.id)
            if i==0:intent['target_id']=self.target22.id
            else:intent['create_values']=dict(delay=1,sequence=1,product_code=False,product_name=False)
            intents.append(intent)
        r.action_set_vendor_application_scope(intents,'Exact independent mixed-operation review',calendar_timezone=self.a.partner_id.tz or 'UTC')
        r.action_submit_for_review()
        for stage in r.stage_ids.sorted('sequence'):
            for actor in stage.assigned_ids:self.assertTrue(r.with_user(actor).action_approve('Independent full mixed batch review'))
        p=r.action_run_application_dry_run().with_user(self.op22)
        self.assertEqual(p.historical_readiness,'READY_FOR_FUTURE_APPLICATION',p.evidence)
        return r,p


@tagged('post_install','-at_install')
class TestExecutionQuick(ExecutionFixtures,TransactionCase):
    def test_legacy_nullable_native_numeric_commit_guard(self):
        self.nullable22=True
        _,_,p=self._plan22()
        self.assertEqual(self.target21.discount,0)
        e=self._apply22(p)
        self.assertEqual(float(e.line_ids.observed_after_values['discount']),0)
        self.env.cr.execute('SET CONSTRAINTS app06_pr22_price_receipt_guard IMMEDIATE')
        self.env.cr.execute('SELECT price,discount FROM product_supplierinfo WHERE id=%s',[self.target21.id])
        self.assertEqual(self.env.cr.fetchone(),(109,None))
        self.env.cr.execute('SET CONSTRAINTS app06_pr22_price_receipt_guard DEFERRED')

    def test_exact_update_pending_commit_and_idempotent_no_second_write(self):
        _,r,p=self._plan22();before=snapshot(self.target21)[0]
        e=self._apply22(p);self.target21.invalidate_recordset()
        self.assertEqual(self.target21.price,109);self.assertEqual(e.update_count,1)
        self.assertEqual(e.state,'PENDING_COMMIT');self.assertFalse(e.executed_at)
        self.assertEqual(e.line_ids.before_values['price'],'100.0')
        self.assertEqual(e.line_ids.observed_after_values['price'],'109.0')
        self.assertEqual({k:e.line_ids.observed_after_values[k] for k in ('delay','sequence','product_code','product_name')},{k:before[k] for k in ('delay','sequence','product_code','product_name')})
        with patch.object(type(self.target21),'write',side_effect=AssertionError('SECOND_WRITE')):
            self.assertEqual(self._apply22(p),e)
        self.assertEqual(self.env[EXEC].search_count([('authorization_id','=',r.authorization_id.id)]),1)
        _logger.info('PR22_REFERENCE_A exact100_to109 verified_in_transaction; no committed-success claim before commit')
        _logger.info('PR22_REFERENCE_E same_plan_repeat_no_second_write')

    def test_create_moq100_preserves_lower_tier_and_selects_exact_price(self):
        self._moq21=1;self._old21=115
        _,r,p=self._plan22('create');old=snapshot(self.target21)
        e=self._apply22(p);new=self.env['product.supplierinfo'].browse(e.line_ids.target_id)
        self.assertEqual((new.min_qty,new.price,new.product_id,new.company_id),(100,109,self.red,self.a))
        self.assertEqual(snapshot(self.target21),old);self.assertEqual(e.create_count,1)
        self.assertEqual(e.line_ids.verification['at_start']['values']['price'],'109.0')
        self.assertEqual(e.line_ids.verification['below_moq']['values']['price'],'115.0')
        _logger.info('PR22_REFERENCE_B realMOQ100_create109 MOQ1_retained')

    def test_no_change_is_verified_without_native_write(self):
        self._old21=109;_,_,p=self._plan22()
        with patch.object(type(self.target21),'write',side_effect=AssertionError('NO_CHANGE_WRITE')),patch.object(type(self.target21),'create',side_effect=AssertionError('NO_CHANGE_CREATE')):
            e=self._apply22(p)
        self.assertEqual(e.no_change_count,1);self.assertEqual(e.action_verify_execution(),'VERIFIED_IN_TRANSACTION_PENDING_COMMIT')
        _logger.info('PR22_REFERENCE_C no_change_has_own_receipt_no_native_write')

    def test_confirmation_role_and_native_permissions_are_separate(self):
        _,_,p=self._plan22(native=False)
        with self.assertRaises(UserError):p.action_apply_approved_vendor_prices()
        with self.assertRaises(AccessError):self._apply22(p)
        self.assertEqual(self.target21.price,100)
        self.op22.group_ids=[Command.unlink(self.env.ref(PREFIX+'group_vpr_pricing_operator').id)]
        with self.assertRaises(AccessError):self._apply22(p)

    def test_post_write_mismatch_and_audit_failure_roll_back_update(self):
        _,_,p=self._plan22();typ=type(self.target21);original=typ.write
        def corrupt(records,vals):
            result=original(records,vals)
            original(records,{'price':108});return result
        with patch.object(typ,'write',corrupt),self.assertRaises(ValidationError):self._apply22(p)
        self.target21.invalidate_recordset();self.assertEqual(self.target21.price,100)
        with patch.object(type(self.env[EXEC]),'_record',side_effect=UserError('Injected audit persistence failure')),self.assertRaises(UserError):self._apply22(p)
        self.target21.invalidate_recordset();self.assertEqual(self.target21.price,100)
        self.assertFalse(self.env[EXEC].search([('plan_id','=',p.id)]))
        self.assertEqual(self._apply22(p).update_count,1)


@tagged('post_install','-at_install')
class TestExecutionControls(ExecutionFixtures,TransactionCase):
    def test_bulk_tenth_failure_rolls_back_update_and_eight_creates_then_retry(self):
        r,p=self._bulk22();before=snapshot(self.env['product.supplierinfo'].search([]));original=module.snapshot
        def mismatch(records):
            values=original(records)
            for value in values:
                if float(value['min_qty'])==109 and float(value['price'])==109:value['price']='108'
            return values
        with patch.object(module,'snapshot',mismatch),self.assertRaises(ValidationError):self._apply22(p)
        self.env.invalidate_all()
        self.assertEqual(snapshot(self.env['product.supplierinfo'].search([])),before)
        self.assertFalse(self.env[EXEC].search([('plan_id','=',p.id)]))
        e=self._apply22(p);self.assertEqual((e.update_count,e.create_count,e.verified_line_count),(1,9,10))
        self.assertEqual(len(e.line_ids),10)
        _logger.info('PR22_REFERENCE_D genuine10_line_batch_tenth_verification_failure_full_rollback_safe_retry')

    def test_target105_and_expiry_and_invalidation_block(self):
        _,r,p=self._plan22();self.target21.price=105
        with self.assertRaises(UserError):self._apply22(p)
        self.assertEqual(self.target21.price,105)
        _logger.info('PR22_REFERENCE_H target105_not_overwritten')
        # Independent fresh fixture per remaining boundary: restore source by
        # rolling back this test's nested savepoint is not a reapproval shortcut.
        self.assertFalse(self.env[EXEC].search([('plan_id','=',p.id)]))

    def test_expiry_after_plan_and_during_final_write_aborts(self):
        _,r,p=self._plan22(decision_validity_mode='days',decision_valid_days=1)
        with patch.object(fields.Datetime,'now',return_value=r.approval_valid_until),self.assertRaises(UserError):self._apply22(p)
        self.assertEqual(self.target21.price,100)
        original=type(self.target21).write
        def expire(records,vals):
            result=original(records,vals)
            clock=patch.object(fields.Datetime,'now',return_value=r.approval_valid_until);clock.start();self.addCleanup(clock.stop)
            return result
        with patch.object(type(self.target21),'write',expire),self.assertRaises(UserError):self._apply22(p)
        self.target21.invalidate_recordset();self.assertEqual(self.target21.price,100)
        _logger.info('PR22_REFERENCE_G expiry_blocks_before_and_after_native_write')

    def test_governed_invalidation_and_unapproved112_block(self):
        s,r,p=self._plan22()
        s.action_set_assumptions([self._spec(value='112')],'Unapproved new hypothetical price')
        with self.assertRaises(UserError):self._apply22(p)
        self.assertEqual(self.target21.price,100)

    def test_external_edit_after_execution_never_replays_old_price(self):
        _,_,p=self._plan22();e=self._apply22(p)
        self.target21.price=112
        with self.assertRaisesRegex(UserError,'ALREADY_APPLIED_TARGET_CHANGED'):self._apply22(p)
        self.assertEqual(self.target21.price,112)
        self.assertEqual(e.line_ids.observed_after_values['price'],'109.0')

    def test_context_target_field_and_success_ledger_forgery_denied(self):
        _,r,p=self._plan22()
        with self.assertRaises(TypeError):p.action_apply_approved_vendor_prices(True,p.fingerprint,target_id=self.white.id)
        with self.assertRaises(TypeError):p.action_apply_approved_vendor_prices(True,p.fingerprint,values={'price':1})
        for records in (self.env[EXEC],self.env[LINE]):
            with self.assertRaises(AccessError):records.create({'name':'Forged verified'})
            with self.assertRaises(AccessError):records.with_context(_vpr_receipt_capability=True)._record({})
        e=self._apply22(p.with_context(default_product_id=self.white.id,default_company_id=self.b.id,force_ready=True,skip_approval=True))
        self.assertEqual(self.env['product.supplierinfo'].browse(e.line_ids.target_id).product_id,self.red)
        for record in (e,e.line_ids):
            with self.assertRaises(AccessError):record.write({'operator_id':self.op22.id})
            with self.assertRaises(AccessError):record.unlink()
            with self.assertRaises(AccessError):record.copy()
        _logger.info('PR22_REFERENCE_I wrong_variant_and_field_injection_denied')

    def test_roles_company_exports_attachments_and_owner_confirmation(self):
        _,_,p=self._plan22();e=self._apply22(p)
        for user in (self.users['sales'],self.users['auditor'],self.users['purchase_b'],self.env.ref('base.public_user')):
            with self.assertRaises(AccessError):self._apply22(p.with_user(user))
        for user in (self.users['sales'],self.users['purchase_b'],self.env.ref('base.public_user')):
            for records in (e,e.line_ids):
                with self.assertRaises(AccessError):records.with_user(user).read(['id'])
                with self.assertRaises(AccessError):records.with_user(user).export_data(['id'])
        self.assertTrue(e.with_user(self.users['auditor']).read(['id']))
        with self.assertRaises(AccessError):self.env['ir.attachment'].create(dict(name='forged',res_model=EXEC,res_id=e.id,type='binary'))
        w=self.env['vendor.price.revision.application.confirmation'].with_user(self.op22).create({'plan_id':p.id})
        with self.assertRaises(AccessError):w.write({'plan_id':p.id})
        with self.assertRaises(UserError):w.action_confirm()

    def test_optional_company_maker_separation_is_server_side(self):
        _,_,p=self._plan22(application_distinct_maker=True)
        with self.assertRaisesRegex(AccessError,'MAKER_OPERATOR'):self._apply22(p)
        self.assertEqual(self.target21.price,100)

    def test_optional_company_approver_separation_is_server_side(self):
        _,r,p=self._plan22(application_distinct_approver=True)
        actor=r.decision_ids.filtered(lambda d:d.decision_type=='approve').acting_user_id[:1]
        self.assertTrue(actor)
        actor=self.env['res.users'].browse(actor.id)
        actor.group_ids=[Command.link(self.env.ref(PREFIX+'group_vpr_pricing_operator').id),
                         Command.link(self.env.ref('purchase.group_purchase_manager').id)]
        with self.assertRaisesRegex(AccessError,'APPROVER_OPERATOR'):
            self._apply22(p.with_user(actor))
        self.assertEqual(self.target21.price,100)

    def test_confirmation_action_executes_exact_reviewed_scope(self):
        _,_,p=self._plan22()
        self.assertTrue(p.can_execute22)
        action=p.action_open_execution_confirmation()
        w=self.env['vendor.price.revision.application.confirmation'].with_user(self.op22).browse(action['res_id'])
        self.assertFalse(w.confirmation)
        self.assertEqual(w.expected_fingerprint,p.fingerprint)
        w.write({'confirmation':True})
        result=w.action_confirm();e=self.env[EXEC].browse(result['res_id'])
        self.assertEqual(e.plan_id,p)
        self.assertEqual(e.state,'PENDING_COMMIT')
        self.assertEqual(self.target21.price,109)

    def test_template_conflict_cannot_apply(self):
        self._template21=True
        _,_,p=self._plan22('create');before=snapshot(self.target21)
        with self.assertRaises(UserError):self._apply22(p)
        self.assertEqual(snapshot(self.target21),before)

    def test_future_dated_create_preserves_history_and_boundaries(self):
        self._end21='2026-10-31';self._effective21='2026-11-01'
        _,_,p=self._plan22('create');old=snapshot(self.target21)
        e=self._apply22(p);values=e.line_ids.verification
        self.assertEqual(values['before_start']['values']['price'],'100.0')
        self.assertEqual(values['at_start']['values']['price'],'109.0')
        self.assertEqual(snapshot(self.target21),old)
        _logger.info('PR22_REFERENCE_K future_rule_not_active_early_old_history_retained')

    def test_shared_and_template_conflicts_do_not_mutate(self):
        self._shared21=True
        _,_,p=self._plan22('create');before=snapshot(self.target21)
        with self.assertRaises(UserError):self._apply22(p)
        self.assertEqual(snapshot(self.target21),before)
        _logger.info('PR22_REFERENCE_J shared_company_price_never_changed')

    def test_explicit_future_close_and_create_are_approved_and_atomic(self):
        self.op22=self._operator22();self._effective21='2026-11-01'
        _,r=self._approved21(operation='create',approve=False)
        row=r.batch_id.row_ids
        r.action_set_vendor_application_scope([dict(row_id=row.id,operation='create',target_uom_id=self.unit.id,
            close_previous_id=self.target21.id,create_values=dict(delay=1,sequence=1,product_code=False,product_name=False))],
            'Explicit old100 through Oct31 and new109 from Nov1; preserve history',calendar_timezone=self.a.partner_id.tz or 'UTC')
        r.action_submit_for_review()
        for stage in r.stage_ids.sorted('sequence'):
            for actor in stage.assigned_ids:self.assertTrue(r.with_user(actor).action_approve('Approve both exact date-boundary operations'))
        p=r.action_run_application_dry_run().with_user(self.op22)
        self.assertEqual(p.historical_readiness,'READY_FOR_FUTURE_APPLICATION',p.evidence)
        self.assertEqual(len(p.line_ids),2)
        with patch.object(type(self.target21),'create',side_effect=UserError('Injected new-rule failure')),self.assertRaises(UserError):self._apply22(p)
        self.target21.invalidate_recordset();self.assertFalse(self.target21.date_end);self.assertEqual(self.target21.price,100)
        e=self._apply22(p);self.target21.invalidate_recordset()
        self.assertEqual(str(self.target21.date_end),'2026-10-31');self.assertEqual(self.target21.price,100)
        self.assertEqual((e.update_count,e.create_count),(1,1))
        self.assertEqual(e.line_ids.filtered(lambda l:l.operation=='UPDATE_CANDIDATE').observed_after_values['price'],'100.0')

    def test_unapproved_open_ended_closure_is_blocked(self):
        self._effective21='2026-11-01';_,_,p=self._plan22('create')
        self.assertEqual(p.historical_readiness,'BLOCKED')
        with self.assertRaises(UserError):self._apply22(p)
        self.assertFalse(self.target21.date_end);self.assertEqual(self.target21.price,100)

    def test_false_state_authority_and_source_fingerprint_cannot_replay(self):
        _,r,p=self._plan22()
        for state in ('draft','partially_approved','rejected','returned_for_revision'):
            # Explicit corruption injection, not fabricated real approval votes.
            with self.env.cr.savepoint() as point:
                r._update({'state':state})
                with self.assertRaisesRegex(UserError,'APPROVAL_NOT_FINAL'):self._apply22(p)
                point.rollback()
        self.env.invalidate_all();e=self._apply22(p)
        r._update({'source_fingerprint':'f'*64})
        with self.assertRaisesRegex(UserError,'EXECUTION_EVIDENCE_MISMATCH'):self._apply22(p)
        self.target21.invalidate_recordset();self.assertEqual(self.target21.price,109)
        self.assertEqual(e.line_ids.before_values['price'],'100.0')

    def test_actual_governance_invalidation_blocks_ready_plan(self):
        _,r,p=self._plan22()
        actor=r.stage_ids.assigned_ids.filtered(lambda u:u.has_group(PREFIX+'group_vpr_finance_manager'))[:1]
        actor=actor or self.reviewers['finance']
        r.with_user(actor).action_invalidate_approval('Explicit governed withdrawal before application')
        with self.assertRaisesRegex(UserError,'APPROVAL_INVALIDATED'):self._apply22(p)
        self.assertEqual(self.target21.price,100)
