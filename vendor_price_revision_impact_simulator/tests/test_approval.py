"""PR19 real source-to-route, SoD, immutable evidence and confidentiality tests."""
import logging
from decimal import Decimal as D
from unittest.mock import patch
from odoo import Command
from odoo.exceptions import AccessError,UserError,ValidationError
from odoo.tests import TransactionCase,tagged
from .test_recommendations import RecommendationFixtures
from .test_commercial_validation import MODULE
from ..models.approval import HEADER,STAGE,EVIDENCE,EVENT,ISSUE
from ..models.approval_math import TYPES,ROLES,metrics,select_rules,assign,plan

_logger=logging.getLogger(__name__)

@tagged('post_install','-at_install')
class TestApprovalMath(TransactionCase):
    def test_explicit_signed_metrics_and_no_automatic_abs(self):
        v=metrics('11500','10900','14000','14000','.01')
        self.assertEqual(D(v['signed_cost_change']),-600);self.assertEqual(D(v['cost_increase']),0);self.assertEqual(D(v['cost_reduction']),600)
    def test_missing_money_and_zero_revenue_fail_closed(self):
        for args in [(None,'10','20','20'),('10','10','0','20')]:
            with self.assertRaises(ValueError):metrics(*args,'.01')
    def test_threshold_currency_cent_boundaries(self):
        rules=[dict(id=i,category='finance_exposure',types=['vendor_revision'],metric='cost_increase',trigger='always',minimum=lo,maximum=hi,roles=[ROLES[0]],quorum=1) for i,lo,hi in [(1,'0','10000.01'),(2,'10000.01','100000.01'),(3,'100000.01',None)]]
        for value,expected in [('9999.99',1),('10000',1),('10000.01',2),('100000',2),('100000.01',3)]:self.assertEqual(select_rules(rules,'vendor_revision',{'cost_increase':value},{},'.01')[0]['id'],expected)
    def test_gap_and_overlap_fail_closed(self):
        r=dict(id=1,category='finance_exposure',types=['vendor_revision'],metric='cost_increase',trigger='always',minimum='0',maximum='100',roles=[ROLES[0]],quorum=1)
        with self.assertRaises(ValueError):select_rules([r],'vendor_revision',{'cost_increase':'100'},{},'.01')
        with self.assertRaises(ValueError):select_rules([r,dict(r,id=2)],'vendor_revision',{'cost_increase':'50'},{},'.01')
    def test_non_greedy_distinct_matching(self):
        self.assertEqual(assign([dict(code='purchase',quorum=1,candidates=[1,2]),dict(code='finance',quorum=1,candidates=[1])]),{'purchase':[2],'finance':[1]})
    def test_distinct_quorum_not_reused(self):
        with self.assertRaises(ValueError):assign([dict(code='finance',quorum=2,candidates=[7])])
        with self.assertRaises(ValueError):assign([dict(code='p',quorum=1,candidates=[7]),dict(code='f',quorum=1,candidates=[7])],{'p':[7],'f':[7]})
    def test_compatible_authorities_merge_but_not_quorum(self):
        row=dict(id=1,category='finance_exposure',metric='cost_increase',observed='1500',minimum='0',maximum=None,roles=[ROLES[0]],quorum=2,named=[])
        result=plan([row],[('high_risk',[ROLES[0],ROLES[2]])],list(ROLES),1)
        self.assertEqual(sum(s['quorum'] for s in result),3);self.assertEqual(sum(s['code']==ROLES[0] for s in result),1)

class ApprovalFixtures(RecommendationFixtures):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from ..models.supply_governance import GRANT
        from ..models.sales_exposure import GRANT as SALES_GRANT
        cls.reviewers={}
        for key,role in [('purchase',ROLES[0]),('finance',ROLES[2]),('director',ROLES[3]),('sales',ROLES[1]),('finance_extra',ROLES[2])]:
            u=cls.env['res.users'].with_context(no_reset_password=True).create(dict(name='PR19 '+key,login='pr19-'+key+'-'+str(cls.a.id)+'@example.invalid',company_id=cls.a.id,company_ids=[Command.set(cls.a.ids)],
                group_ids=[Command.set([cls.env.ref(MODULE+'.'+role).id,cls.env.ref(MODULE+'.group_vpr_confidential_reader').id,cls.env.ref('sales_team.group_sale_salesman_all_leads').id])]))
            cls.env[GRANT].create(dict(company_id=cls.a.id,user_id=u.id,warehouse_ids=[Command.set((cls.wh|cls.wh2|cls.wh3).ids)],allow_cost=True,allow_demand=True,reason='Explicit independent approval source scope'))
            cls.env[SALES_GRANT].create(dict(company_id=cls.a.id,user_id=u.id,warehouse_ids=[Command.set((cls.wh|cls.wh2|cls.wh3).ids)],reason='Explicit customer-commercial approval scope'))
            cls.reviewers[key]=u

    def _policy19(self,**kw):
        def groups(names):return [self.env.ref(MODULE+'.group_vpr_'+n).id for n in names]
        rows=[]
        for lo,hi,roles in [(0,10000.01,['purchase_manager']),(10000.01,100000.01,['purchase_manager','finance_manager']),(100000.01,None,['purchase_manager','finance_manager','director'])]:
            rows.append(Command.create(dict(name='Explicit test authority band',category='finance_exposure',currency_id=self.inr.id,minimum_amount=lo,maximum_amount=hi or 0,open_ended=hi is None,required_role_ids=[Command.set(groups(roles))],required_independent_approvers=len(roles),reason='Illustrative thresholds, not production defaults',workflow_types=list(TYPES),workflow_metric='cost_increase',workflow_trigger='always')))
        rows.append(Command.create(dict(name='Customer revenue review',category='customer_repricing',currency_id=self.inr.id,open_ended=True,required_role_ids=[Command.set(groups(['sales_manager']))],required_independent_approvers=1,reason='Explicit customer authority',workflow_types=list(TYPES[2:]),workflow_metric='revenue_increase',workflow_trigger='always')))
        values=dict(workflow_enabled=True,workflow_types=list(TYPES),workflow_high_group_ids=[Command.set(groups(['finance_manager']))],workflow_critical_group_ids=[Command.set(groups(['finance_manager','director']))],workflow_contract_group_ids=[Command.set(groups(['purchase_manager']))],approval_ids=rows)
        values.update(kw);return values

    def _source19(self,**kw):return self._prepare18(**self._policy19(**kw))
    def _request19(self,s,typ='vendor_revision',**kw):
        values=dict(baseline_id=s.baseline_id.id,request_type=typ,reason='Documented management review request; not an approval decision')
        if typ!='vendor_revision':values['scenario_id']=s.id
        values.update(kw)
        return self.env[HEADER].with_user(self.users['finance']).create(values)
    def _states19(self,r):return r.stage_ids.sorted('sequence').mapped('stage_status')

@tagged('post_install','-at_install')
class TestApprovalRoutes(ApprovalFixtures,TransactionCase):
    def test_critical_risk_keeps_all_high_risk_authority(self):
        groups=self.env.ref(MODULE+'.group_vpr_sales_manager')|self.env.ref(MODULE+'.group_vpr_finance_manager')
        s=self._source19(workflow_high_group_ids=[Command.set(groups.ids)])
        s.action_set_assumptions([self._spec(value='300')],'Critical hypothetical loss still requires high-risk Sales authority');s.action_calculate_scenario()
        r=self._request19(s,'supplier_scenario');r.action_submit_for_review()
        self.assertEqual(set(r.stage_ids.required_group_ids.get_external_id().values()),{MODULE+'.'+role for role in ROLES})
        self.assertEqual(len(r.stage_ids.assigned_ids),4)
    def test_manual_wizard_requires_every_level_and_rejects_self(self):
        s=self._source19(workflow_assignment='manual');r=self._request19(s)
        with self.assertRaises(UserError):r.action_submit_for_review()
        with self.assertRaises(AccessError):r.action_set_assignments({ROLES[0]:[r.maker_id.id]})
        action=r.action_open_assignment()
        w=self.env['vendor.price.revision.approval.assignment.wizard'].with_user(self.users['finance']).with_context(**action['context']).create(dict(request_id=r.id,stage_code=ROLES[0],assigned_ids=[Command.set(self.reviewers['purchase'].ids)]))
        self.assertEqual(w.quorum,1);self.assertIn(self.reviewers['purchase'],w.candidate_ids);w.action_save();r.action_submit_for_review()
        self.assertEqual(r.stage_ids.assigned_ids,self.reviewers['purchase'])
    def test_deterministic_policy_rejects_manual_override(self):
        s=self._source19();r=self._request19(s)
        with self.assertRaises(UserError):r.action_set_assignments({ROLES[0]:self.reviewers['purchase'].ids})
    def test_single_role_quorum_uses_distinct_people_in_one_level(self):
        p=self.reviewers['finance_extra'];p.group_ids=[Command.link(self.env.ref(MODULE+'.group_vpr_purchase_manager').id)]
        settings=self._policy19();settings['approval_ids'][0][2]['required_independent_approvers']=2
        s=self._prepare18(**settings);r=self._request19(s);r.action_submit_for_review()
        self.assertEqual(len(r.stage_ids),1);self.assertEqual(r.stage_ids.quorum,2);self.assertEqual(len(r.stage_ids.assigned_ids),2)
    def test_named_reviewer_validated_and_no_arbitrary_fallback(self):
        settings=self._policy19();settings['approval_ids'][0][2]['workflow_named_reviewer_ids']=[Command.set(self.reviewers['finance'].ids)]
        s=self._prepare18(**settings);r=self._request19(s)
        with self.assertRaises(UserError):r.action_submit_for_review()
        self.assertFalse(r.stage_ids)
    def test_negative_cost_change_not_routed_as_positive_increase(self):
        s=self._source19();s.action_set_assumptions([self._spec(value='95')],'Explicit supplier decrease');s.action_calculate_scenario()
        r=self._request19(s,'supplier_scenario');r.action_submit_for_review()
        self.assertEqual(D(r.financial_values['signed_cost_change']),-500);self.assertEqual(D(r.financial_values['cost_increase']),0)
        self.assertEqual(len(r.stage_ids),1)
    def test_reference_1500_one_purchase_stage(self):
        s=self._source19();r=self._request19(s);self.assertTrue(r.action_validate_request());r.action_submit_for_review()
        self.assertEqual(r.state,'awaiting_review');self.assertEqual(D(r.financial_values['signed_cost_change']),1500)
        self.assertEqual(self._states19(r),['ready_for_review']);self.assertEqual(r.stage_ids.assigned_ids,self.reviewers['purchase'])
        self.assertEqual(r.get_current_request(),r);self.assertEqual(self.native_line.price_unit,140)
        _logger.info('PR19_REFERENCE_A exposure1500 one_purchase_stage ready_for_review maker_excluded no_decision')
    def test_50000_two_and_150000_three_ordered_levels(self):
        s=self._prepare18(price=1400,**self._policy19())
        for price,amount,states in [('600',50000,['ready_for_review','waiting_predecessor']),('1600',150000,['ready_for_review','waiting_predecessor','waiting_predecessor'])]:
            alt=s.action_clone_scenario('Threshold '+price);alt.action_set_assumptions([self._spec(value=price)],'Explicit expensive alternative, not accepted');alt.action_calculate_scenario()
            r=self._request19(alt,'supplier_scenario');r.action_submit_for_review()
            self.assertEqual(D(r.financial_values['signed_cost_change']),amount);self.assertEqual(self._states19(r),states)
            self.assertEqual(len(r.stage_ids.assigned_ids),len(states))
            _logger.info('PR19_REFERENCE_ROUTE exposure%s stages%s distinct_authorized_only_first_ready',amount,len(states))
    def test_negotiated109_hypothetical_improvement600_not_acceptance(self):
        s=self._source19();s.action_set_assumptions([self._spec(value='109')],'Hypothetical negotiated price, no vendor acceptance');s.action_calculate_scenario()
        r=self._request19(s,'supplier_scenario');r.action_submit_for_review();data=r.evidence_id.data
        self.assertEqual(D(data['scenario_improvement_vs_original_proposal']),600);self.assertEqual(D(r.financial_values['signed_cost_change']),900)
        self.assertEqual(data['scenario_assumptions'][0]['value'],'109');self.assertEqual(self.native_line.price_unit,140)
        _logger.info('PR19_REFERENCE_G hypothetical109 improvement600 signed_cost_increase900 no_supplier_acceptance')
    def test_critical_negative_profit_adds_finance_and_director(self):
        s=self._source19();s.action_set_assumptions([self._spec(value='300')],'Hypothetical loss scenario');s.action_calculate_scenario()
        r=self._request19(s,'supplier_scenario');r.action_submit_for_review()
        self.assertEqual(r.risk_severity,'critical');self.assertEqual(len(r.stage_ids),3);self.assertEqual(self._states19(r).count('ready_for_review'),1)
    def test_customer_option_and_explicit_combined_sources(self):
        s=self._prepare18(protection='price_adjustment_allowed_verified',**self._policy19())
        alt=s.action_clone_scenario('Hypothetical110');alt.action_set_assumptions([self._spec(value='110')],'Supplier target, not accepted');alt.action_calculate_scenario()
        rec=s.action_generate_recommendations([self._input18(conditions='Verified customer notice conditions')],alternative_ids=alt.ids)
        customer=rec.option_ids.filtered(lambda o:o.kind=='customer_eligible_price_review')
        r=self._request19(s,'customer_repricing',recommendation_id=rec.id,option_id=customer.id);r.action_submit_for_review()
        self.assertEqual(r.evidence_id.data['recommendation_option'],customer.values)
        combined=rec.option_ids.filtered(lambda o:o.kind=='combined_customer_and_supplier_'+str(alt.id))
        p=self._request19(alt,'commercial_package',recommendation_id=rec.id,option_id=combined.id);p.action_submit_for_review()
        self.assertEqual(D(p.financial_values['projected_cost']),21000)
    def test_fixed_customer_cannot_request_repricing_permission(self):
        s=self._source19();rec=s.action_generate_recommendations();opt=rec.option_ids.filtered(lambda o:o.kind=='customer_eligible_price_review')
        r=self._request19(s,'customer_repricing',recommendation_id=rec.id,option_id=opt.id)
        with self.assertRaises(UserError):r.action_submit_for_review()
        self.assertFalse(r.evidence_id);self.assertFalse(r.stage_ids)
    def test_maker_and_creator_with_manager_roles_excluded(self):
        s=self._source19();maker=self.env['res.users'].browse(s.batch_id.revision_id.owner_id.id);maker.group_ids=[Command.link(self.env.ref(MODULE+'.group_vpr_purchase_manager').id)]
        r=self._request19(s);r.action_submit_for_review()
        self.assertNotIn(maker,r.stage_ids.candidate_ids);self.assertNotIn(r.requested_by,r.stage_ids.candidate_ids)
        _logger.info('PR19_SOD maker_multi_role_and_creator_excluded independent_purchase_reviewer_assigned')

@tagged('post_install','-at_install')
class TestApprovalLifecycle(ApprovalFixtures,TransactionCase):
    def test_disabled_published_workflow_is_not_authority(self):
        s=self._prepare18();r=self._request19(s)
        self.assertFalse(r.action_validate_request());self.assertEqual(r.state,'blocked')
        with self.assertRaises(UserError):r.action_submit_for_review()
    def test_reviewer_wrong_company_and_source_scope_never_candidate(self):
        s=self._source19();r=self._request19(s);u=self.reviewers['purchase']
        self.env['vendor.price.revision.sales.grant'].search([('user_id','=',u.id)]).write(dict(active=False,reason='No current customer-source authority'))
        with self.assertRaises(UserError):r.action_submit_for_review()
        self.assertFalse(r.stage_ids)
    def test_later_stages_receive_no_activities(self):
        s=self._prepare18(price=1400,**self._policy19(workflow_activities=True));s.action_set_assumptions([self._spec(value='600')],'Two-level activity routing');s.action_calculate_scenario()
        r=self._request19(s,'supplier_scenario');r.action_submit_for_review();stages=r.stage_ids.sorted('sequence')
        self.assertEqual(len(stages),2);self.assertEqual(len(stages[0].activity_ids),1);self.assertFalse(stages[1].activity_ids)
        self.assertEqual(stages[1].stage_status,'waiting_predecessor')
    def test_repeated_prepare_submit_no_duplicate_package_stages_events(self):
        s=self._source19();r=self._request19(s);self.assertEqual(self._request19(s),r);r.action_submit_for_review()
        counts={m:self.env[m].search_count([]) for m in (HEADER,STAGE,EVIDENCE,EVENT,ISSUE)}
        self.assertEqual(r.action_submit_for_review(),r);self.assertEqual(counts,{m:self.env[m].search_count([]) for m in counts})
    def test_blocked_reconciliation_not_zero_exposure(self):
        self._policy16();self._commercial14();self.red.categ_id.property_cost_method='fifo';self._quant(60);self._sales15(200)
        s=self._scenario(self._reconcile());s.action_calculate_scenario();r=self._request19(s)
        self.assertFalse(r.action_validate_request());self.assertEqual(r.state,'blocked');self.assertTrue(r.issue_ids)
        with self.assertRaises(UserError):r.action_submit_for_review()
        self.assertFalse(r.financial_values);self.assertFalse(r.stage_ids)
    def test_missing_independent_reviewer_blocks_recoverably(self):
        s=self._source19();u=self.reviewers['purchase'];u.active=False;r=self._request19(s)
        self.assertFalse(r.action_validate_request());self.assertFalse(r.stage_ids);u.active=True
        self.assertTrue(r.action_validate_request());r.action_submit_for_review();self.assertEqual(r.state,'awaiting_review')
    def test_source_change_stale_preserves_frozen_values(self):
        s=self._source19();r=self._request19(s);r.action_submit_for_review();before=r.evidence_id.data
        self.native_line.price_unit=150
        with self.assertRaises(UserError):r.get_current_request()
        self.assertEqual(r.action_refresh_readiness(),'stale');self.assertFalse(r.active_key);self.assertEqual(r.stage_ids.stage_status,'invalidated')
        self.assertEqual(r.evidence_id.data,before)
    def test_reviewer_revocation_invalidates_current_authority(self):
        s=self._source19();r=self._request19(s);r.action_submit_for_review();self.env['res.users'].browse(r.stage_ids.assigned_ids.ids).active=False
        with self.assertRaises(UserError):r.get_current_request()
        self.assertEqual(r.action_refresh_readiness(),'stale')
    def test_withdraw_new_version_and_history(self):
        s=self._source19();r=self._request19(s);r.action_submit_for_review();evidence=r.evidence_id
        r.action_withdraw_request('Commercial proposal withdrawn before any decision')
        new=r.action_new_version({},'Fresh undecided request version')
        self.assertEqual(new.previous_id,r);self.assertEqual(new.version,2);self.assertEqual(r.evidence_id,evidence);new.action_submit_for_review()
        self.assertEqual(new.state,'awaiting_review');self.assertEqual(r.state,'superseded')
    def test_submission_atomic_failure_and_retry(self):
        s=self._source19();r=self._request19(s);before={m:self.env[m].search_count([]) for m in (STAGE,EVIDENCE,EVENT)}
        with patch.object(type(self.env[EVIDENCE]),'_record',side_effect=UserError('Injected immutable evidence publication failure')):
            with self.assertRaises(UserError):r.action_submit_for_review()
        self.assertEqual(r.state,'draft');self.assertEqual(before,{m:self.env[m].search_count([]) for m in before});self.assertFalse(r.submitted_by)
        r.action_submit_for_review();self.assertEqual(r.state,'awaiting_review')
    def test_new_version_publication_failure_leaves_no_orphan(self):
        s=self._source19();r=self._request19(s);r.action_withdraw_request('Replace draft after new evidence')
        before=self.env[HEADER].search_count([])
        with patch.object(type(r),'_event',side_effect=UserError('Injected version audit failure')):
            with self.assertRaises(UserError):r.action_new_version({},'Retryable new version')
        self.assertEqual(self.env[HEADER].search_count([]),before);self.assertEqual(r.state,'withdrawn')
        self.assertEqual(r.action_new_version({},'Retry after audit recovery').version,2)
    def test_internal_activity_first_stage_only_idempotent_and_archive(self):
        s=self._source19(workflow_activities=True);r=self._request19(s);mails=self.env['mail.mail'].search_count([])
        r.action_submit_for_review();activities=r.stage_ids.activity_ids
        self.assertEqual(len(activities),1);self.assertEqual(activities.user_id,r.stage_ids[:1].assigned_ids)
        self.assertEqual(activities.res_id,r.id);r.action_submit_for_review();self.assertEqual(r.stage_ids.activity_ids,activities)
        self.assertEqual(self.env['mail.mail'].search_count([]),mails);r.action_withdraw_request('Withdraw activity without decision');self.assertFalse(activities.active)

@tagged('post_install','-at_install')
class TestApprovalSecurity(ApprovalFixtures,TransactionCase):
    def test_state_and_route_orm_forgery_and_immutable_evidence(self):
        s=self._source19();r=self._request19(s)
        with self.assertRaises(AccessError):r.with_context(skip_security=True).write(dict(state='awaiting_review'))
        with self.assertRaises(AccessError):self.env[HEADER].with_user(self.users['finance']).create(dict(baseline_id=s.baseline_id.id,request_type='vendor_revision',reason='Forged',state='approved'))
        r.action_submit_for_review()
        for record in (r.stage_ids,r.evidence_id,r.event_ids):
            with self.assertRaises(AccessError):record.write({'batch_id':s.batch_id.id})
            with self.assertRaises(AccessError):record.unlink()
    def test_source_company_and_related_record_scope(self):
        s=self._source19();r=self._request19(s);r.action_submit_for_review()
        for record in (r,r.stage_ids,r.evidence_id,r.event_ids):
            with self.assertRaises(AccessError):record.with_user(self.users['finance']).with_context(allowed_company_ids=self.b.ids).read(['id'])
            with self.assertRaises(AccessError):record.with_user(self.users['purchase_b']).export_data(['id'])
    def test_sales_purchase_portal_public_and_auditor_boundaries(self):
        s=self._source19();r=self._request19(s);r.action_submit_for_review()
        for u in (self.users['sales'],self.users['purchase'],self.env.ref('base.public_user')):
            for row in (r,r.stage_ids,r.evidence_id):
                with self.assertRaises(AccessError):row.with_user(u).read(['id'])
        self.assertTrue(r.with_user(self.users['auditor']).read(['name']))
        with self.assertRaises(AccessError):r.with_user(self.users['auditor']).action_refresh_readiness()
    def test_source_access_revocation_hides_derived_search_groups(self):
        s=self._source19();r=self._request19(s);r.action_submit_for_review();u=self.reviewers['purchase']
        self.assertTrue(r.with_user(u).read(['financial_values']))
        self.env['vendor.price.revision.sales.grant'].search([('user_id','=',u.id)]).write(dict(active=False,reason='Explicit approval source revocation'))
        with self.assertRaises(AccessError):r.with_user(u).read(['financial_values'])
        self.assertEqual(self.env[HEADER].with_user(u)._read_group([],[],['__count'])[0][0],0)
    def test_no_manual_activity_or_chatter_bypass(self):
        s=self._source19();r=self._request19(s);r.action_submit_for_review()
        with self.assertRaises(AccessError):r.message_post(body='Customer pricing accepted')
        with self.assertRaises(AccessError):self.env['mail.activity'].create(dict(res_model_id=self.env['ir.model']._get_id(HEADER),res_id=r.id,activity_type_id=self.env.ref('mail.mail_activity_data_todo').id,user_id=self.reviewers['purchase'].id))
        for model_value in ((self.env['ir.model']._get_id(HEADER),'Approval'),self.env['ir.model']._get(HEADER)):
            with self.assertRaises(AccessError):self.env['mail.activity'].with_context(mail_activity_quick_update=True).create(dict(res_model_id=model_value,res_id=r.id,user_id=self.env.uid))
        with self.assertRaises(AccessError):self.env['mail.activity'].with_context(default_res_model=HEADER,mail_activity_quick_update=True).create(dict(res_id=r.id,user_id=self.env.uid))
        ordinary=self.env['mail.activity'].with_context(mail_activity_quick_update=True).create(dict(res_model_id=self.env['ir.model']._get_id('res.partner'),res_id=self.native_order.partner_id.id,user_id=self.env.uid))
        ordinary.write({'summary':'Ordinary activity delegation still works'})
        for value in ((self.env['ir.model']._get_id(HEADER),'Approval'),self.env['ir.model']._get(HEADER)):
            with self.assertRaises(AccessError):ordinary.write(dict(res_model_id=value,res_id=r.id))
        ordinary.unlink()
    def test_real_wizard_and_pending_inbox(self):
        s=self._source19();w=self.env['vendor.price.revision.approval.wizard'].with_user(self.users['finance']).create(dict(baseline_id=s.baseline_id.id,request_type='vendor_revision',reason='Exact source review'))
        action=w.action_prepare();r=self.env[HEADER].with_user(self.users['finance']).browse(action['res_id']);r.action_submit_for_review()
        inbox=self.env[HEADER].with_user(self.reviewers['purchase']).action_my_pending_reviews()
        self.assertIn(r.stage_ids.id,inbox['domain'][0][2]);self.assertEqual(r.action_open_source()['res_id'],s.baseline_id.id)
