"""PR20 real financial-source decisions, identity/quorum and validity controls."""
import logging
from datetime import datetime, date, timedelta
from unittest.mock import patch
from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from .test_approval import ApprovalFixtures
from .test_commercial_validation import MODULE
from ..models.approval import HEADER, STAGE, EVIDENCE, EVENT
from ..models.approval_decisions import DECISION, AUTHORIZATION, DELEGATION
from ..models.approval_decision_math import within, expiry

_logger = logging.getLogger(__name__)


@tagged('post_install', '-at_install')
class TestDecisionMath(TransactionCase):
    def test_windows_are_inclusive_start_exclusive_end(self):
        start = datetime(2026, 11, 1, 0); end = start + timedelta(hours=1)
        self.assertTrue(within(start, start, end)); self.assertFalse(within(end, start, end))
        self.assertFalse(within(start - timedelta(microseconds=1), start, end))

    def test_source_only_has_no_invented_duration(self):
        self.assertIsNone(expiry(datetime(2026, 11, 1), 'source_only'))

    def test_elapsed_days_and_explicit_indian_business_date(self):
        now = datetime(2026, 11, 1, 12)
        self.assertEqual(expiry(now, 'days', 2), datetime(2026, 11, 3, 12))
        self.assertEqual(expiry(now, 'date', local_date=date(2026, 11, 30), zone='Asia/Kolkata'), datetime(2026, 11, 30, 18, 30))

    def test_dst_business_date_and_missing_policy(self):
        self.assertEqual(expiry(datetime(2026, 11, 1), 'date', local_date=date(2026, 11, 1), zone='America/New_York'), datetime(2026, 11, 2, 5))
        with self.assertRaises(ValueError): expiry(datetime(2026, 11, 1), 'days', 0)
        with self.assertRaises(ValueError): expiry(datetime(2026, 11, 1), 'date', local_date=date(2026, 11, 1), zone='invented')


class DecisionFixtures(ApprovalFixtures):
    def _policy20(self, **kw):
        policy = self._policy19(decision_enabled=True,
            decision_governance_group_ids=[Command.set((self.env.ref(MODULE + '.group_vpr_finance_manager') | self.env.ref(MODULE + '.group_vpr_director')).ids)])
        policy.update(kw)
        return policy

    def _source20(self, **kw):
        return self._prepare18(**self._policy20(**kw))

    def _pending20(self, **kw):
        scenario = self._source20(**kw); request = self._request19(scenario)
        request.action_submit_for_review()
        return scenario, request

    def _multi20(self, **kw):
        scenario = self._prepare18(price=1400, **self._policy20(**kw))
        scenario.action_set_assumptions([self._spec(value='1600')], 'Explicit150000 cost-pressure reference')
        scenario.action_calculate_scenario(); request = self._request19(scenario, 'supplier_scenario')
        request.action_submit_for_review()
        return scenario, request

    def _two20(self, **kw):
        settings = self._policy20(**kw)
        settings['approval_ids'][0][2].update(required_role_ids=[Command.set((self.env.ref(MODULE+'.group_vpr_purchase_manager') | self.env.ref(MODULE+'.group_vpr_finance_manager')).ids)], required_independent_approvers=2)
        scenario = self._prepare18(**settings)
        scenario.action_set_assumptions([self._spec(value='109')], 'Exact hypothetical109 source, not acceptance')
        scenario.action_calculate_scenario(); request = self._request19(scenario, 'supplier_scenario')
        request.action_submit_for_review()
        return scenario, request

    def _finance20(self, **kw):
        self.reviewers['sales'].group_ids = [Command.link(self.env.ref(MODULE+'.group_vpr_finance_manager').id)]
        settings = self._policy20(workflow_contract_group_ids=[Command.set(self.env.ref(MODULE+'.group_vpr_finance_manager').ids)], **kw)
        for command in settings['approval_ids']:
            if command[2]['category'] == 'finance_exposure':
                command[2].update(required_role_ids=[Command.set(self.env.ref(MODULE+'.group_vpr_finance_manager').ids)], required_independent_approvers=2)
        scenario = self._prepare18(**settings); request = self._request19(scenario); request.action_submit_for_review()
        self.assertEqual(len(request.stage_ids), 1); self.assertEqual(request.stage_ids.quorum, 2)
        return scenario, request

    def _delegation20(self, request, start=None, end=None):
        stage = request.stage_ids[:1]; principal = stage.assigned_ids[:1]
        delegate = (stage.candidate_ids - stage.assigned_ids)[:1]
        now = fields.Datetime.now()
        record = request.with_user(principal).action_propose_delegation(stage.id, delegate.id,
            self.env.ref(MODULE+'.group_vpr_finance_manager').id, start or now-timedelta(hours=1), end or now+timedelta(hours=1),
            'Explicit independently authorized temporary Finance coverage')
        return record, principal, delegate

    def _vote20(self, request, who='purchase', kind='approve', **kw):
        record = request.with_user(self.reviewers[who])
        action = {'approve': record.action_approve, 'reject': record.action_reject, 'return': record.action_return_for_revision}[kind]
        result = action('Exact submitted commercial subject independently reviewed', **kw)
        if not result:
            _logger.error('PR20_FIXTURE_BLOCKED %s', request.issue_ids.mapped('description'))
        return result


@tagged('post_install', '-at_install')
class TestDecisionQuick(DecisionFixtures, TransactionCase):
    def test_one_level_exact_authorization(self):
        scenario, request = self._pending20(); price = self.native_line.price_unit
        decision = self._vote20(request)
        self.assertTrue(decision, request.issue_ids.mapped('description'))
        self.assertEqual(decision.acting_user_id, self.reviewers['purchase'])
        self.assertEqual(decision.reviewer_id, self.reviewers['purchase'])
        self.assertEqual(request.state, 'approved'); self.assertEqual(request.stage_ids.stage_status, 'approved')
        artifact = request.get_current_approval()
        self.assertEqual(artifact.decision_ids, decision); self.assertEqual(artifact.payload_fingerprint, request.payload_fingerprint)
        self.assertFalse(artifact.evidence['payload']['applied']); self.assertEqual(self.native_line.price_unit, price)
        self.assertEqual(request.current_validity, 'valid')
        _logger.info('PR20_REFERENCE_A single_level exposure1500 approved exact_payload no_price_application')

    def test_reject_and_return_are_terminal_decisions(self):
        scenario, request = self._pending20()
        with self.assertRaises(ValidationError): request.with_user(self.reviewers['purchase']).action_reject('')
        decision = self._vote20(request, kind='return')
        self.assertEqual(request.state, 'returned_for_revision'); self.assertEqual(decision.decision_type, 'return')
        old = request.evidence_id
        successor = request.action_new_version({}, 'New governed proposal after missing contract evidence')
        self.assertEqual(successor.previous_id, request); self.assertEqual(request.state, 'returned_for_revision')
        self.assertEqual(request.evidence_id, old); self.assertFalse(successor.decision_ids)
        successor.action_submit_for_review(); self._vote20(successor, kind='reject')
        self.assertEqual(successor.state, 'rejected'); self.assertFalse(successor.authorization_id)
        _logger.info('PR20_REFERENCE_E returned evidence preserved fresh_version_no_old_votes; rejection terminal')

    def test_maker_creator_wrong_role_and_duplicate_blocked(self):
        scenario, request = self._pending20()
        for user in (request.requested_by, request.maker_id, self.reviewers['finance'], self.users['auditor']):
            with self.assertRaises((AccessError, UserError)): request.with_user(user).action_approve('Forged self/role authority')
        self._vote20(request)
        with self.assertRaises(UserError): self._vote20(request)
        self.assertEqual(len(request.decision_ids), 1)
        with self.assertRaises(AccessError): request.write({'state': 'approved'})

    def test_required_justification_and_atomic_retry(self):
        scenario, request = self._pending20()
        with self.assertRaises(ValidationError): request.with_user(self.reviewers['purchase']).action_approve('')
        before = self.env[EVENT].search_count([])
        with patch.object(type(self.env[AUTHORIZATION]), '_record', side_effect=UserError('Injected final artifact persistence failure')):
            with self.assertRaises(UserError): self._vote20(request)
        self.assertEqual(request.state, 'awaiting_review'); self.assertFalse(request.decision_ids)
        self.assertEqual(request.stage_ids.stage_status, 'ready_for_review'); self.assertEqual(self.env[EVENT].search_count([]), before)
        self._vote20(request); self.assertEqual(request.state, 'approved')


@tagged('post_install', '-at_install')
class TestDecisionWorkflow(DecisionFixtures, TransactionCase):
    def test_three_levels_and_exactly_one_final_artifact(self):
        _, request = self._multi20()
        for who, states in [('purchase',['approved','ready_for_review','waiting_predecessor']),('finance',['approved','approved','ready_for_review']),('director',['approved','approved','approved'])]:
            self._vote20(request, who); self.assertEqual(self._states19(request), states)
            self.assertEqual(request.state, 'approved' if who=='director' else 'partially_approved')
        self.assertEqual(len(request.decision_ids),3); self.assertEqual(request.authorization_id.decision_ids,request.decision_ids)
        self.assertEqual(request.event_ids.filtered(lambda e:e.event=='final_management_authorization').__len__(),1)
        self.assertEqual(request.current_validity,'valid')
        _logger.info('PR20_REFERENCE_B exposure150000 Purchase_Finance_Director sequential three_decisions one_final_authorization')

    def test_two_level_source_and_premature_stage_denied(self):
        _,request=self._two20(); stages=request.stage_ids.sorted('sequence')
        with self.assertRaises(AccessError):request.with_user(self.reviewers['finance']).action_approve('Cannot skip Purchase',stage_id=stages[1].id)
        self._vote20(request); self.assertEqual(request.state,'partially_approved')
        with self.assertRaises(AccessError):request.with_user(self.reviewers['finance']).action_approve('Wrong stage',stage_id=stages[0].id)
        self._vote20(request,'finance'); self.assertEqual(request.state,'approved')

    def test_distinct_finance_quorum_and_duplicate(self):
        _,request=self._finance20(); stage=request.stage_ids; people=stage.assigned_ids
        request.with_user(people[0]).action_approve('First distinct Finance assessment')
        self.assertEqual(stage.stage_status,'partially_approved'); self.assertEqual(stage.current_approval_count,1)
        self.assertEqual(stage.remaining_approval_count,1); self.assertFalse(request.authorization_id)
        with self.assertRaises(UserError):request.with_user(people[0]).action_approve('Duplicate cannot count')
        request.with_user(people[1]).action_approve('Second independent Finance assessment')
        self.assertEqual(stage.current_approval_count,2); self.assertEqual(request.state,'approved')
        _logger.info('PR20_REFERENCE_C Finance quorum2 first_vote_partial duplicate_not_counted second_distinct_final')

    def test_finance_rejection_preserves_purchase_and_cancels_director(self):
        _,request=self._multi20(workflow_activities=True); self._vote20(request)
        first=request.decision_ids; self._vote20(request,'finance','reject')
        self.assertEqual(request.state,'rejected'); self.assertEqual(self._states19(request),['approved','rejected','cancelled'])
        self.assertIn(first,request.decision_ids); self.assertFalse(request.authorization_id)
        self.assertFalse(request.stage_ids.activity_ids.filtered('active'))
        with self.assertRaises(UserError):self._vote20(request,'director')
        _logger.info('PR20_REFERENCE_D Finance rejection preserves Purchase approval Director never_activated')

    def test_return_after_partial_requires_fresh_votes_and_evidence(self):
        _,request=self._two20(); self._vote20(request); data=request.evidence_id.data
        self._vote20(request,'finance','return'); self.assertEqual(self._states19(request),['approved','returned'])
        successor=request.action_new_version({},'Documented rework after return')
        successor.action_submit_for_review(); self.assertEqual(successor.state,'awaiting_review')
        self.assertFalse(successor.decision_ids); self.assertEqual(successor.version,2); self.assertEqual(request.evidence_id.data,data)
        with self.assertRaises(UserError):request.action_new_version({},'Duplicate successor')
        with self.assertRaises(AccessError):successor.with_user(self.users['purchase_b']).action_return_for_revision('Wrong company')

    def test_109_to_112_blocks_finance_and_keeps_original_vote(self):
        scenario,request=self._two20(); self._vote20(request); old=request.evidence_id.data
        scenario.action_set_assumptions([self._spec(value='112')],'Changed hypothetical price, not a continuation of109')
        self.assertFalse(request.with_user(self.reviewers['finance']).action_approve('Stale109 cannot authorize112'))
        self.assertEqual(request.state,'approval_invalidated'); self.assertEqual(len(request.decision_ids),1)
        self.assertEqual(request.evidence_id.data,old); self.assertEqual(old['scenario_assumptions'][0]['value'],'109')
        successor=request.action_new_version({},'Reanalyse112 under a fresh reviewed package')
        with self.assertRaises(UserError):successor.action_submit_for_review()
        scenario.action_calculate_scenario(); successor.action_submit_for_review()
        self.assertEqual(successor.evidence_id.data['scenario_assumptions'][0]['value'],'112'); self.assertFalse(successor.decision_ids)
        _logger.info('PR20_REFERENCE_F submitted109 changed112 stale_blocked old_vote_retained fresh_source_and_votes_required')

    def test_mid_final_stage_revalidation_rolls_back_new_vote(self):
        _,request=self._two20(); self._vote20(request); before=request.decision_ids
        original=type(request)._contract20; calls=[]
        def changed(record):
            calls.append(record.id)
            if len(calls)>1:raise UserError('Injected changed financial evidence before final persistence')
            return original(record)
        with patch.object(type(request),'_contract20',changed):
            self.assertFalse(request.with_user(self.reviewers['finance']).action_approve('Final revalidation mandatory'))
        self.assertEqual(request.decision_ids,before); self.assertFalse(request.authorization_id)
        self.assertEqual(request.state,'approval_invalidated')

    def test_activities_advance_once_and_never_send_mail(self):
        _,request=self._multi20(workflow_activities=True); mail=self.env['mail.mail'].search_count([])
        self.assertEqual(len(request.stage_ids.activity_ids),1)
        self._vote20(request); self.assertEqual(len(request.stage_ids.activity_ids),2)
        with self.assertRaises(UserError):self._vote20(request)
        self.assertEqual(len(request.stage_ids.activity_ids),2)
        self._vote20(request,'finance'); self._vote20(request,'director')
        self.assertEqual(len(request.stage_ids.activity_ids),3); self.assertFalse(request.stage_ids.activity_ids.filtered('active'))
        self.assertEqual(self.env['mail.mail'].search_count([]),mail)

    def test_corrupt_zero_quorum_or_skipped_state_cannot_finalize(self):
        _,request=self._two20(); first=request.stage_ids.sorted('sequence')[0]
        first._update({'stage_status':'approved'})  # Explicit corrupt legacy fixture, never ordinary ORM.
        self.assertFalse(request.with_user(self.reviewers['finance']).action_approve('A status is not a vote'))
        self.assertFalse(request.decision_ids); self.assertFalse(request.authorization_id)
        self.assertEqual(request.state,'approval_invalidated')

    def test_role_revocation_between_levels_blocks_final_authority(self):
        _,request=self._two20(); self._vote20(request)
        self.env['res.users'].browse(self.reviewers['purchase'].id).active=False
        self.assertFalse(request.with_user(self.reviewers['finance']).action_approve('Prior checker no longer eligible'))
        self.assertEqual(request.state,'approval_invalidated'); self.assertFalse(request.authorization_id)

    def test_legacy_routing_only_submission_keeps_history_and_cannot_vote(self):
        _,request=self._pending20(decision_enabled=False); old=request.evidence_id.data
        self.assertEqual(request.get_current_request(),request)
        with self.assertRaises(UserError):self._vote20(request)
        self.assertEqual(request.state,'awaiting_review'); self.assertEqual(request.evidence_id.data,old); self.assertFalse(request.decision_ids)


@tagged('post_install', '-at_install')
class TestDecisionDelegation(DecisionFixtures,TransactionCase):
    def test_valid_independent_delegate_and_historical_revocation(self):
        _,request=self._finance20(decision_delegation_enabled=True)
        delegation,principal,delegate=self._delegation20(request)
        with self.assertRaises(AccessError):request.with_user(delegate).action_approve('Not authorized yet',delegation_id=delegation.id)
        delegation.with_user(self.reviewers['director']).action_authorize()
        vote=request.with_user(delegate).action_approve('Eligible delegated Finance assessment',delegation_id=delegation.id)
        self.assertEqual(vote.reviewer_id,principal); self.assertEqual(vote.acting_user_id,delegate); self.assertEqual(vote.delegation_id,delegation)
        delegation.with_user(principal).action_revoke('Coverage ended after a valid historical vote')
        other=(request.stage_ids.assigned_ids-principal)[:1]
        request.with_user(other).action_approve('Other independent Finance slot')
        self.assertEqual(request.state,'approved'); self.assertEqual(request.current_validity,'valid')
        self.assertEqual(vote.evidence['delegation']['delegate_id'],delegate.id)

    def test_authorizer_must_be_independent_and_policy_enabled(self):
        _,request=self._finance20(decision_delegation_enabled=True); delegation,principal,delegate=self._delegation20(request)
        for person in (principal,delegate,request.requested_by):
            with self.assertRaises(AccessError):delegation.with_user(person).action_authorize()
        self.assertFalse(delegation.authorized_by); self.assertEqual(delegation.state,'proposed')

    def test_delegation_never_bypasses_maker_or_wrong_role(self):
        _,request=self._finance20(decision_delegation_enabled=True); stage=request.stage_ids; principal=stage.assigned_ids[:1]; now=fields.Datetime.now()
        for person in (request.maker_id,request.requested_by,self.reviewers['purchase'],self.users['purchase_b']):
            with self.assertRaises(AccessError):request.with_user(principal).action_propose_delegation(stage.id,person.id,self.env.ref(MODULE+'.group_vpr_finance_manager').id,now,now+timedelta(hours=1),'No delegated escalation')
        self.assertFalse(request.delegation_ids)

    def test_delegation_expired_boundary_and_future_start(self):
        _,request=self._finance20(decision_delegation_enabled=True); now=fields.Datetime.now()
        delegation,principal,delegate=self._delegation20(request,start=now+timedelta(hours=1),end=now+timedelta(hours=2))
        delegation.with_user(self.reviewers['director']).action_authorize()
        with self.assertRaises(AccessError):request.with_user(delegate).action_approve('Before start',delegation_id=delegation.id)
        with patch.object(fields.Datetime,'now',return_value=delegation.effective_until):
            with self.assertRaises(AccessError):request.with_user(delegate).action_approve('Exact end expired',delegation_id=delegation.id)
        self.assertFalse(request.decision_ids)

    def test_revoked_delegation_blocks_new_decisions(self):
        _,request=self._finance20(decision_delegation_enabled=True); delegation,principal,delegate=self._delegation20(request)
        delegation.with_user(self.reviewers['director']).action_authorize(); delegation.with_user(principal).action_revoke('Explicit revocation before voting')
        with self.assertRaises(AccessError):request.with_user(delegate).action_approve('Revoked relationship',delegation_id=delegation.id)
        self.assertFalse(request.decision_ids)

    def test_delegate_cannot_supply_another_actor_identity(self):
        _,request=self._finance20(decision_delegation_enabled=True); delegation,_,delegate=self._delegation20(request)
        delegation.with_user(self.reviewers['director']).action_authorize()
        with self.assertRaises(TypeError):request.with_user(delegate).action_approve('No impersonation',reviewer_id=self.reviewers['director'].id)
        with self.assertRaises(AccessError):self.env[DECISION].with_user(delegate).create({'acting_user_id':delegate.id})
        with self.assertRaises(AccessError):delegation.write({'state':'active'})

    def test_governance_authorizer_loses_role_before_delegate_votes(self):
        _,request=self._finance20(decision_delegation_enabled=True); delegation,_,delegate=self._delegation20(request)
        delegation.with_user(self.reviewers['director']).action_authorize()
        self.env['res.users'].browse(self.reviewers['director'].id).group_ids=[Command.set(self.env.ref('base.group_user').ids)]
        with self.assertRaises(AccessError):request.with_user(delegate).action_approve('Authorizer no longer governs',delegation_id=delegation.id)
        self.assertFalse(request.decision_ids)


@tagged('post_install', '-at_install')
class TestDecisionValidity(DecisionFixtures,TransactionCase):
    def test_review_expiry_during_finalization_rolls_back_vote(self):
        # Native cost fixtures predate this clock even when the suite runs after06:00 UTC.
        now=fields.Datetime.now()+timedelta(days=1)
        with patch.object(fields.Datetime,'now',return_value=now):_,request=self._pending20(decision_review_hours=1)
        original=type(request)._finish20
        def expire_before_final(record):
            with patch.object(fields.Datetime,'now',return_value=now+timedelta(hours=1)):
                return original(record)
        with patch.object(fields.Datetime,'now',return_value=now+timedelta(minutes=59)),patch.object(type(request),'_finish20',expire_before_final):
            self.assertFalse(request.with_user(self.reviewers['purchase']).action_approve('Clock crosses review boundary before persistence'))
        self.assertEqual(request.state,'approval_expired');self.assertFalse(request.decision_ids);self.assertFalse(request.authorization_id)

    def test_expiry_exact_boundary_preserves_approved_history(self):
        # Native cost fixtures predate this clock even when the suite runs after06:00 UTC.
        now=fields.Datetime.now()+timedelta(days=1)
        with patch.object(fields.Datetime,'now',return_value=now):
            _,request=self._pending20(decision_validity_mode='days',decision_valid_days=2); self._vote20(request)
        artifact=request.authorization_id; until=now+timedelta(days=2)
        self.assertEqual(request.approval_valid_until,until)
        with patch.object(fields.Datetime,'now',return_value=until-timedelta(seconds=1)):
            self.assertEqual(request.get_current_approval(),artifact)
        with patch.object(fields.Datetime,'now',return_value=until):
            self.assertEqual(request._validity20(),'expired')
            with self.assertRaises(UserError):request.get_current_approval()
            request.action_revalidate_approval()
        self.assertEqual(request.state,'approved'); self.assertEqual(request.authorization_id,artifact)
        self.assertTrue(request.approval_expired_at)
        _logger.info('PR20_REFERENCE_H approved_history_retained exact_end_expired no_current_application_authority')

    def test_date_only_approval_uses_explicit_business_timezone(self):
        now=datetime(2026,11,1,6)
        with patch.object(fields.Datetime,'now',return_value=now):
            _,request=self._pending20(decision_validity_mode='date',decision_valid_date='2026-11-30',decision_timezone='Asia/Kolkata');self._vote20(request)
        self.assertEqual(request.approval_valid_until,datetime(2026,11,30,18,30))

    def test_review_window_expires_without_final_or_vote(self):
        # Native cost fixtures predate this clock even when the suite runs after06:00 UTC.
        now=fields.Datetime.now()+timedelta(days=1)
        with patch.object(fields.Datetime,'now',return_value=now):_,request=self._pending20(decision_review_hours=1)
        with patch.object(fields.Datetime,'now',return_value=now+timedelta(hours=1)):
            self.assertFalse(request.with_user(self.reviewers['purchase']).action_approve('Exact review end'))
        self.assertEqual(request.state,'approval_expired'); self.assertFalse(request.decision_ids); self.assertFalse(request.authorization_id)

    def test_material_source_after_approval_invalidates_current_not_history(self):
        _,request=self._pending20(); self._vote20(request); old=request.authorization_id.evidence
        self.native_line.price_unit=141
        self.assertEqual(request._validity20(),'invalidated')
        with self.assertRaises(UserError):request.get_current_approval()
        request.action_revalidate_approval()
        self.assertEqual(request.state,'approved');self.assertEqual(request.authorization_id.evidence,old);self.assertTrue(request.approval_invalidated_at)

    def test_cosmetic_note_is_audited_without_changing_authority(self):
        _,request=self._pending20();self._vote20(request); fp=request.payload_fingerprint
        request.write({'review_display_note':'Internal presentation note only, no changed price terms'})
        self.assertEqual(request.get_current_approval(),request.authorization_id);self.assertEqual(request.payload_fingerprint,fp)
        self.assertTrue(request.event_ids.filtered(lambda e:e.event=='display_note_changed'))

    def test_governed_revocation_and_successor_do_not_copy_final_votes(self):
        _,request=self._pending20();self._vote20(request)
        with self.assertRaises(UserError):request.action_new_version({},'Cannot silently replace valid authority')
        with self.assertRaises(AccessError):request.with_user(self.reviewers['purchase']).action_invalidate_approval('Not governance')
        request.with_user(self.reviewers['director']).action_invalidate_approval('Explicit renewed commercial review required')
        successor=request.action_new_version({},'Fresh proposal after explicit invalidation')
        self.assertEqual(request.state,'approved');self.assertEqual(successor.previous_id,request);self.assertFalse(successor.decision_ids)

    def test_no_direct_extension_or_forged_validity(self):
        _,request=self._pending20();self._vote20(request)
        for values in ({'approval_valid_until':'2030-01-01'},{'approval_invalidated_at':False},{'authorization_id':False},{'decision_evidence_fingerprint':'forged'}):
            with self.assertRaises(AccessError):request.write(values)
        for record in (request.decision_ids,request.authorization_id):
            with self.assertRaises(AccessError):record.unlink()
            with self.assertRaises(AccessError):record.write({'source_fingerprint':'fake'})


@tagged('post_install', '-at_install')
class TestDecisionSecurity(DecisionFixtures,TransactionCase):
    def test_company_decisions_exports_groups_and_auditor(self):
        _,request=self._pending20();self._vote20(request)
        self.env['res.users'].browse(self.users['purchase_b'].id).group_ids=[Command.link(self.env.ref(MODULE+'.group_vpr_finance_manager').id)]
        for record in (request.decision_ids,request.authorization_id):
            with self.assertRaises(AccessError):record.with_user(self.users['purchase_b']).read(['id'])
            with self.assertRaises(AccessError):record.with_user(self.users['purchase_b']).export_data(['id'])
            with self.assertRaises(AccessError):record.with_user(self.env.ref('base.public_user')).read(['id'])
            self.assertTrue(record.with_user(self.users['auditor']).read(['id']))
        self.assertEqual(self.env[DECISION].with_user(self.users['purchase_b']).with_context(allowed_company_ids=self.b.ids)._read_group([],[],['__count'])[0][0],0)
        with self.assertRaises(AccessError):request.with_user(self.users['auditor']).action_invalidate_approval('Audit is read-only')

    def test_source_access_revocation_hides_derived_decisions(self):
        _,request=self._pending20();self._vote20(request); user=self.reviewers['purchase']
        self.env['vendor.price.revision.sales.grant'].search([('user_id','=',user.id)]).write({'active':False,'reason':'Explicit scope revocation'})
        with self.assertRaises(AccessError):request.decision_ids.with_user(user).read(['evidence'])
        self.assertEqual(self.env[AUTHORIZATION].with_user(user)._read_group([],[],['__count'])[0][0],0)

    def test_private_immutable_documents_and_no_token_or_company_escape(self):
        _,request=self._pending20()
        attachment=self.env['ir.attachment'].with_user(self.users['finance']).create(dict(name='Verified supplier terms.txt',raw=b'Only synthetic reference evidence',res_model=HEADER,res_id=request.id))
        for values in ({'public':True},{'access_token':'fake'},{'raw':b'Replaced'},{'res_model':'res.partner'}):
            with self.assertRaises(AccessError):attachment.write(values)
        with self.assertRaises(AccessError):attachment.unlink()
        with self.assertRaises(AccessError):attachment.generate_access_token()
        with self.assertRaises(AccessError):attachment.with_user(self.env.ref('base.public_user')).read(['raw'])
        with self.assertRaises(AccessError):self.env['ir.attachment'].with_context(default_public=True).create(dict(name='Public forbidden',raw=b'fake',res_model=HEADER,res_id=request.id))
        self._vote20(request,attachment_ids=attachment.ids)
        self.assertEqual(request.decision_ids.attachment_ids,attachment)
        self.assertEqual(request.current_validity,'valid')

    def test_wizard_identity_and_context_do_not_forge_actor(self):
        _,request=self._pending20(); actor=self.reviewers['purchase']
        action=request.with_user(actor).action_open_approve()
        wizard=self.env['vendor.price.revision.approval.decision.wizard'].with_user(actor).with_context(**action['context']).create(dict(request_id=request.id,stage_id=request.stage_ids.id,decision_type='approve',reason='Explicit authenticated form approval'))
        wizard.action_execute();self.assertEqual(request.decision_ids.acting_user_id,actor)
        with self.assertRaises(AccessError):request.with_user(request.requested_by).with_context(skip_security=True,reviewer_id=actor.id).action_approve('No context actor spoof')
        with self.assertRaises(AccessError):request.decision_ids.create({'acting_user_id':actor.id})

    def test_activities_cannot_create_votes_and_late_stages_not_active(self):
        _,request=self._multi20(workflow_activities=True); activity=request.stage_ids.activity_ids
        with self.assertRaises(AccessError):activity.action_done()
        with self.assertRaises(AccessError):activity.with_context(_vpr_approval_activity=True).write({'active':False})
        self.assertFalse(request.decision_ids);self.assertEqual(request.state,'awaiting_review')

    def test_other_scope_and_managed_actor_ids_cannot_be_supplied(self):
        _,request=self._pending20()
        with self.assertRaises(TypeError):request.with_user(self.reviewers['purchase']).action_approve('No supplied actor',acting_user_id=self.reviewers['director'].id)
        with self.assertRaises(AccessError):request.with_user(self.reviewers['purchase']).action_approve('Unrelated stage',stage_id=request.stage_ids.id+9999)
        with self.assertRaises(AccessError):self.env[AUTHORIZATION].create({'request_id':request.id,'approved_at':fields.Datetime.now()})
        self.assertFalse(request.decision_ids)


@tagged('post_install', '-at_install')
class TestDecisionFinancial(DecisionFixtures,TransactionCase):
    def test_lost_cost_basis_blocks_decision_without_zero_exposure(self):
        _,request=self._pending20(); old=request.financial_values
        self.red.with_company(self.a).standard_price=0
        self.assertFalse(request.with_user(self.reviewers['purchase']).action_approve('Missing cost is not zero exposure'))
        self.assertEqual(request.state,'approval_invalidated'); self.assertEqual(request.financial_values,old)
        self.assertFalse(request.authorization_id)

    def test_changed_imported_price_or_currency_cannot_use_old_votes(self):
        scenario,request=self._pending20(); old=request.evidence_id.data
        scenario.batch_id.row_ids.with_user(request.maker_id).action_correct('proposed_price_raw','120','New supplier evidence requires fresh approval')
        self.assertFalse(request.with_user(self.reviewers['purchase']).action_approve('Old115 cannot approve120'))
        self.assertFalse(request.decision_ids); self.assertEqual(request.evidence_id.data,old)

    def test_zero_quorum_is_never_automatic_approval(self):
        _,request=self._pending20(); request.stage_ids._update({'quorum':0})
        self.assertFalse(request.with_user(self.reviewers['purchase']).action_approve('Corrupt zero quorum must block'))
        self.assertFalse(request.decision_ids); self.assertFalse(request.authorization_id)

    def test_critical_risk_cannot_drop_high_risk_sales_authority(self):
        groups=self.env.ref(MODULE+'.group_vpr_sales_manager')|self.env.ref(MODULE+'.group_vpr_finance_manager')
        scenario=self._source20(workflow_high_group_ids=[Command.set(groups.ids)])
        scenario.action_set_assumptions([self._spec(value='300')],'Critical loss still requires every high-risk role'); scenario.action_calculate_scenario()
        request=self._request19(scenario,'supplier_scenario'); request.action_submit_for_review()
        self.assertEqual(len(request.stage_ids),4);self._vote20(request)
        with self.assertRaises(AccessError):self._vote20(request,'finance')
        for who in ('sales','finance','director'):self._vote20(request,who)
        self.assertEqual(request.state,'approved');self.assertEqual(len(request.decision_ids),4)

    def test_customer_and_combined_authorizations_keep_exact_action_types(self):
        scenario=self._prepare18(protection='price_adjustment_allowed_verified',**self._policy20())
        alt=scenario.action_clone_scenario('Exact hypothetical110')
        alt.action_set_assumptions([self._spec(value='110')],'Not supplier acceptance');alt.action_calculate_scenario()
        rec=scenario.action_generate_recommendations([self._input18(conditions='Verified customer notice conditions')],alternative_ids=alt.ids)
        for typ,selected,kind in [('customer_repricing',scenario,'customer_eligible_price_review'),('commercial_package',alt,'combined_customer_and_supplier_'+str(alt.id))]:
            option=rec.option_ids.filtered(lambda o:o.kind==kind)
            request=self._request19(selected,typ,recommendation_id=rec.id,option_id=option.id);request.action_submit_for_review()
            for stage in request.stage_ids.sorted('sequence'):
                request.with_user(stage.assigned_ids[:1]).action_approve('Exact commercial action type only')
            artifact=request.get_current_approval()
            self.assertEqual(artifact.request_type,typ);self.assertEqual(artifact.evidence['payload']['permitted_subject'],typ)
            self.assertFalse(artifact.evidence['payload']['applied']);self.assertEqual(artifact.evidence['payload']['option_id'],option.id)
        self.assertEqual(self.native_line.price_unit,140)

    def test_customer_eligibility_change_invalidates_recommendation_authority(self):
        scenario=self._prepare18(protection='price_adjustment_allowed_verified',**self._policy20())
        rec=scenario.action_generate_recommendations([self._input18(conditions='Original verified pricing eligibility')])
        option=rec.option_ids.filtered(lambda o:o.kind=='customer_eligible_price_review')
        request=self._request19(scenario,'customer_repricing',recommendation_id=rec.id,option_id=option.id);request.action_submit_for_review()
        scenario.baseline_id.margin_id.sales_id.line_ids.with_user(self.users['manager']).action_review_price_protection('fixed_price_verified','New fixed customer contract','New eligibility evidence requires revalidation')
        self.assertFalse(request.with_user(self.reviewers['purchase']).action_approve('Old customer permission no longer holds'))
        self.assertEqual(request.state,'approval_invalidated');self.assertFalse(request.authorization_id)

    def test_source_and_policy_json_tamper_cannot_create_authority(self):
        _,request=self._pending20();request._update({'decision_policy_fingerprint':'explicit corrupt fixture'})
        self.assertFalse(request.with_user(self.reviewers['purchase']).action_approve('Corrupt frozen policy'))
        self.assertFalse(request.decision_ids);self.assertFalse(request.authorization_id)

    def test_expiry_sync_is_idempotent_and_current_expired_action_includes_time(self):
        now=datetime(2026,11,1,6)
        with patch.object(fields.Datetime,'now',return_value=now):
            _,request=self._pending20(decision_validity_mode='days',decision_valid_days=1);self._vote20(request)
        with patch.object(fields.Datetime,'now',return_value=now+timedelta(days=1)):
            action=request.action_expired_invalidated_reviews()
            self.assertIn(request,self.env[HEADER].search(action['domain']))
            request.action_revalidate_approval(); before=len(request.event_ids)
            request.action_revalidate_approval();self.assertEqual(len(request.event_ids),before)
        self.assertEqual(request.state,'approved')

    def test_new_applicable_published_policy_requires_reauthorization(self):
        _,request=self._pending20()
        future=request.policy_id.with_user(self.env.user).copy(dict(policy_version='PR20 future tightened policy',
            effective_from='2031-01-01',effective_to='2032-12-31',change_reason='Explicit future authority change'))
        future.action_publish()
        self.assertEqual(request.get_current_request(),request)
        with patch.object(fields.Date,'today',return_value=date(2031,1,1)):
            self.assertFalse(request.with_user(self.reviewers['purchase']).action_approve('Old policy cannot authorize the new period'))
        self.assertEqual(request.state,'approval_invalidated');self.assertFalse(request.authorization_id)

    def test_maker_with_all_manager_roles_and_full_source_scope_still_cannot_decide(self):
        _,request=self._pending20(); maker=self.env['res.users'].browse(request.maker_id.id)
        maker.group_ids=[Command.link(self.env.ref(MODULE+'.group_vpr_'+role).id) for role in ('purchase_manager','finance_manager','director')]+[Command.link(self.env.ref('sales_team.group_sale_salesman_all_leads').id)]
        for model,extra in [('vendor.price.revision.supply.grant',{'allow_cost':True,'allow_demand':True}),('vendor.price.revision.sales.grant',{})]:
            grant=self.env[model].search([('company_id','=',self.a.id),('user_id','=',maker.id)])
            values=dict(company_id=self.a.id,user_id=maker.id,warehouse_ids=[Command.set((self.wh|self.wh2|self.wh3).ids)],reason='Explicit isolated self-approval negative fixture',**extra)
            if grant:grant.write({k:v for k,v in values.items() if k not in ('company_id','user_id')})
            else:self.env[model].create(values)
        with self.assertRaisesRegex(AccessError,'Maker'):
            request.with_user(maker).with_context(skip_security=True).action_approve('Every manager role still cannot override maker-checker')
        self.assertFalse(request.decision_ids)
        _logger.info('PR20_REFERENCE_G maker_Purchase_Finance_Director full_scope self_approval_denied')
