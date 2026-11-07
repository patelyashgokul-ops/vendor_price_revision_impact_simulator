"""PR21 exact authority, real supplier rules, immutable preview and no-write assertions."""
import logging
from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch
from odoo import fields, Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from .test_approval_decisions import DecisionFixtures
from ..models import application_math as m
from ..models.application_engine import ApplicationEngine, snapshot
from ..models.application_plan import PLAN, LINE, ISSUE

_logger = logging.getLogger(__name__)


@tagged('post_install','-at_install')
class TestApplicationMath(TransactionCase):
    def _values(self, **kw):
        v=dict(id=1, partner_id=10, product_id=20, product_tmpl_id=30, company_id=40,
            min_qty='100.0', price='100.0', currency_id=50, uom_id=60,
            date_start='2026-11-01', date_end=False, discount='0.0', delay=2,
            sequence=1, product_code='EXACT', product_name='Original')
        v.update(kw);return v

    def test_exact_update_and_normalized_identity(self):
        before=self._values();after=self._values(price='109',min_qty='100')
        op,target,codes=m.classify(after,[before],dict(operation='update',target_id=1,before=before),'2026-10-29')
        self.assertEqual((op,target['id'],codes),('UPDATE_CANDIDATE',1,[]))

    def test_new_tier_no_change_and_duplicate_ambiguity(self):
        desired=self._values(price='109');broad=self._values(min_qty='1',price='115')
        self.assertEqual(m.classify(desired,[broad],dict(operation='create'),'2026-10-29')[0],'CREATE_CANDIDATE')
        self.assertEqual(m.classify(desired,[desired],dict(operation='create'),'2026-10-29')[0],'NO_CHANGE')
        self.assertIn('AMBIGUOUS_TARGET',m.classify(desired,[desired,dict(desired,id=2)],{},'2026-10-29')[2])

    def test_shared_template_and_wrong_identity(self):
        desired=self._values()
        for before,code in [(self._values(company_id=False),'SHARED_RECORD_SCOPE_CONFLICT'),(self._values(product_id=False),'TEMPLATE_VARIANT_SCOPE_CONFLICT')]:
            self.assertIn(code,m.classify(desired,[before],dict(operation='create'),'2026-10-29')[2])
        self.assertEqual(m.classify(desired,[self._values(partner_id=99)],dict(operation='create'),'2026-10-29')[0],'CREATE_CANDIDATE')

    def test_target_drift_and_historical_no_overwrite(self):
        before=self._values();changed=self._values(price='105');after=self._values(price='109')
        self.assertIn('TARGET_CHANGED_SINCE_APPROVAL',m.classify(after,[changed],dict(operation='update',target_id=1,before=before),'2026-10-29')[2])
        self.assertIn('HISTORICAL_PERIOD_REWRITE',m.classify(after,[before],dict(operation='update',target_id=1,before=before),'2026-11-02')[2])

    def test_uom_direction_and_inclusive_date_overlap(self):
        self.assertEqual(m.converted_terms('1090','10','10','1'),('109','100'))
        self.assertTrue(m.overlap(self._values(date_end='2026-11-01'),self._values(date_start='2026-11-01')))
        self.assertFalse(m.overlap(self._values(date_end='2026-10-31'),self._values(date_start='2026-11-01')))

    def test_conflicting_approved_lines_both_blocked(self):
        engine=object.__new__(ApplicationEngine);engine.issues=[]
        engine.lines=[dict(row_id=i,after=self._values(price=p),operation='CREATE_CANDIDATE',conflicts=[]) for i,p in [(1,'109'),(2,'112')]]
        engine.duplicates()
        self.assertEqual([v['operation'] for v in engine.lines],['BLOCKED','BLOCKED'])
        self.assertEqual(len(engine.issues),2)

    def test_complete_after_state_tiers_and_complementary_updates(self):
        cheap=self._values(id=1,min_qty='1',price='90')
        tier=self._values(id=2,min_qty='100',price='100')
        def line(rid,before,after,op='UPDATE_CANDIDATE'):
            return dict(row_id=rid,target_id=before['id'] if before else None,after=after,operation=op)
        rows=[line(1,cheap,dict(cheap,price='120')),line(2,tier,dict(tier,price='109'))]
        # The old cheap rule changes in this same approved plan.
        self.assertEqual(m.effective_conflicts(rows,[cheap,tier]),{})
        creates=[line(3,None,dict(cheap,price='90'),'CREATE_CANDIDATE'),line(4,None,dict(tier,price='109'),'CREATE_CANDIDATE')]
        self.assertEqual(m.effective_conflicts(creates,{}),{4:['OVERLAPPING_EFFECTIVE_RULE']})
        rows[0]['operation']='BLOCKED'
        self.assertEqual(m.effective_conflicts(rows,[cheap,tier]),{2:['OVERLAPPING_EFFECTIVE_RULE']})


class ApplicationFixtures(DecisionFixtures):
    def _rule(self,*args,**kw):
        kw.update(date_start='2026-10-30',date_end=getattr(self,'_end21',False))
        rule=super()._rule(*args,**kw)
        if getattr(self,'_shared21',False):rule.company_id=False
        if getattr(self,'_template21',False):rule.product_id=False
        self.target21=rule
        return rule

    def _commercial14(self,*args,**kw):
        kw.update(old=getattr(self,'_old21',100),new=115,old_qty=getattr(self,'_moq21',100),
                  old_start='2026-10-30',tiers=[(100,115)])
        return super()._commercial14(*args,**kw)

    def _approved21(self,operation='update',price='109',approve=True,**policy):
        scenario=self._prepare18(**self._policy20(**policy))
        scenario.action_set_assumptions([self._spec(value=price,effective_date=getattr(self,'_effective21','2026-10-30'),commitment_date='2026-11-05',timing_evidence='Explicit supplier rule period')],'Exact prospective vendor price scope')
        scenario.action_calculate_scenario()
        r=self._request19(scenario,'supplier_scenario')
        spec=dict(row_id=r.batch_id.row_ids.id,operation=operation,target_uom_id=getattr(self,'_target_unit21',self.unit).id)
        if operation=='update':spec['target_id']=self.target21.id
        else:spec['create_values']=dict(delay=1,sequence=1,product_code=False,product_name=False)
        r.action_set_vendor_application_scope([spec],'Explicit exact variant rule and approved operational intent',calendar_timezone=self.a.partner_id.tz or 'UTC')
        if approve:
            r.action_submit_for_review()
            for stage in r.stage_ids.sorted('sequence'):
                for user in stage.assigned_ids:
                    self.assertTrue(r.with_user(user).action_approve('Independent exact price and rule intent approved'),r.issue_ids.mapped('description'))
            self.assertEqual(r.state,'approved')
        return scenario,r


@tagged('post_install','-at_install')
class TestApplicationQuick(ApplicationFixtures,TransactionCase):
    def test_commercial_package_explicit_vendor_component_only(self):
        scenario=self._prepare18(protection='price_adjustment_allowed_verified',**self._policy20())
        alt=scenario.action_clone_scenario('Exact approved package vendor109')
        alt.action_set_assumptions([self._spec(value='109',effective_date='2026-10-30',commitment_date='2026-11-05',timing_evidence='Explicit vendor price period')],'Exact vendor component')
        alt.action_calculate_scenario()
        rec=scenario.action_generate_recommendations([self._input18(conditions='Verified customer notice conditions')],alternative_ids=alt.ids)
        option=rec.option_ids.filtered(lambda o:o.kind=='combined_customer_and_supplier_'+str(alt.id))
        r=self._request19(alt,'commercial_package',recommendation_id=rec.id,option_id=option.id)
        r.action_set_vendor_application_scope([dict(row_id=r.batch_id.row_ids.id,operation='update',target_id=self.target21.id,target_uom_id=self.unit.id)],'Explicit package vendor component only',vendor_component=True,calendar_timezone=self.a.partner_id.tz or 'UTC')
        r.action_submit_for_review()
        for stage in r.stage_ids.sorted('sequence'):
            for actor in stage.assigned_ids:r.with_user(actor).action_approve('Exact package vendor scope')
        before=snapshot(self.target21);sale_price=self.native_line.price_unit
        plan=r.action_run_application_dry_run()
        self.assertEqual(plan.historical_readiness,'READY_FOR_FUTURE_APPLICATION',plan.evidence)
        self.assertEqual(plan.line_ids.operation,'UPDATE_CANDIDATE')
        self.assertEqual(float(plan.line_ids.planned_after_values['price']),109)
        self.assertEqual(snapshot(self.target21),before);self.assertEqual(self.native_line.price_unit,sale_price)

    def test_exact_update_preview_no_write_and_repeat(self):
        _,r=self._approved21();before=snapshot(self.target21);request=r.read(['state','write_date','payload_fingerprint'])
        p=r.action_run_application_dry_run();line=p.line_ids
        self.assertEqual(line.operation,'UPDATE_CANDIDATE');self.assertEqual(line.before_values['price'],'100.0')
        self.assertEqual(float(line.planned_after_values['price']),109);self.assertEqual(line.changed_fields,['price'])
        self.assertEqual(line.planned_after_values['delay'],before[0]['delay'])
        self.assertEqual(p.get_current_application_plan(),p);self.assertEqual(r.action_run_application_dry_run(),p)
        self.assertEqual(snapshot(self.target21),before);self.assertEqual(r.read(['state','write_date','payload_fingerprint']),request)
        self.assertFalse(p.evidence['applied'])
        _logger.info('PR21_REFERENCE_A actual100 planned109 exactMOQ100 update no_native_write')

    def test_create_and_no_change(self):
        self._old21=115;self._moq21=1
        _,r=self._approved21(operation='create');count=self.env['product.supplierinfo'].search_count([])
        p=r.action_run_application_dry_run();self.assertEqual(p.line_ids.operation,'CREATE_CANDIDATE')
        self.assertFalse(p.line_ids.target_id);self.assertEqual(float(p.line_ids.planned_after_values['min_qty']),100)
        self.assertEqual(self.env['product.supplierinfo'].search_count([]),count)
        self.assertEqual(self.target21.min_qty,1);self.assertEqual(self.target21.price,115)
        _logger.info('PR21_REFERENCE_B approved_newMOQ100 existingMOQ1_retained no_record_created')


@tagged('post_install','-at_install')
class TestApplicationControls(ApplicationFixtures,TransactionCase):
    def test_already_matching_no_change(self):
        self._old21=109;_,r=self._approved21();p=r.action_run_application_dry_run()
        self.assertEqual(p.line_ids.operation,'NO_CHANGE');self.assertFalse(p.line_ids.changed_fields)
        _logger.info('PR21_REFERENCE_C exact109 no_change no_update')

    def test_shared_rule_is_not_update_or_create(self):
        self._shared21=True;_,r=self._approved21(operation='create');p=r.action_run_application_dry_run()
        self.assertEqual(p.historical_readiness,'BLOCKED');self.assertIn('SHARED_RECORD_SCOPE_CONFLICT',p.issue_ids.mapped('code'))
        self.assertFalse(self.target21.company_id);self.assertEqual(self.target21.price,100)
        _logger.info('PR21_REFERENCE_D shared_scope_blocked')

    def test_template_rule_cannot_broaden_variant_scope(self):
        self._template21=True;_,r=self._approved21(operation='create');p=r.action_run_application_dry_run()
        self.assertIn('TEMPLATE_VARIANT_SCOPE_CONFLICT',p.issue_ids.mapped('code'));self.assertEqual(p.line_ids.operation,'BLOCKED')
        _logger.info('PR21_REFERENCE_E template_rule_not_variant_authority')

    def test_expiry_invalidates_current_readiness(self):
        _,r=self._approved21(decision_validity_mode='days',decision_valid_days=1);p=r.action_run_application_dry_run();old=deepcopy(p.evidence)
        with patch.object(fields.Datetime,'now',return_value=r.approval_valid_until):
            with self.assertRaises(UserError):p.get_current_application_plan()
            new=r.action_run_application_dry_run();self.assertIn('APPROVAL_EXPIRED',new.issue_ids.mapped('code'))
            self.assertEqual(new.historical_readiness,'BLOCKED')
        self.assertEqual(p.evidence,old);self.assertEqual(r.state,'approved')
        _logger.info('PR21_REFERENCE_F expired_authority_blocked history_retained')

    def test_109_approval_does_not_plan_unapproved112(self):
        s,r=self._approved21();p=r.action_run_application_dry_run()
        s.action_set_assumptions([self._spec(value='112')],'New unapproved negotiation')
        with self.assertRaises(UserError):p.get_current_application_plan()
        new=r.action_run_application_dry_run();self.assertEqual(new.historical_readiness,'BLOCKED')
        self.assertEqual(float(new.line_ids.planned_after_values['price']),109)
        _logger.info('PR21_REFERENCE_G frozen109 not_current112 blocked')

    def test_target105_current_before_and_old_plan_immutable(self):
        _,r=self._approved21();p=r.action_run_application_dry_run();old=deepcopy(p.evidence)
        self.target21.price=105
        with self.assertRaises(UserError):p.get_current_application_plan()
        new=r.action_run_application_dry_run();self.assertEqual(new.version,p.version+1)
        self.assertEqual(float(new.line_ids.before_values['price']),105)
        self.assertIn('TARGET_CHANGED_SINCE_APPROVAL',new.issue_ids.mapped('code'));self.assertEqual(p.evidence,old)
        self.assertEqual(self.target21.price,105)
        _logger.info('PR21_REFERENCE_H observed105 original100_history_preserved no_write109')

    def test_unapproved_and_terminal_states_cannot_plan_ready(self):
        _,r=self._approved21(approve=False)
        for state in ('draft','rejected','returned_for_revision','partially_approved'):
            # Controlled fixture corruption checks the gate, never an application API.
            r._update({'state':state});p=r.action_run_application_dry_run()
            self.assertEqual(p.historical_readiness,'BLOCKED');self.assertFalse(p.line_ids)
        with self.assertRaises(AccessError):r.write({'vendor_application_scope':{'forged':True}})

    def test_intent_is_frozen_and_cannot_change_after_approval(self):
        _,r=self._approved21();scope=deepcopy(r.vendor_application_scope)
        with self.assertRaises(AccessError):r.action_set_vendor_application_scope([], 'Cannot replace approved scope')
        self.assertEqual(r.authorization_id.evidence['payload']['vendor_application_scope'],scope)
        for method,args in [('write',({'historical_readiness':'READY_FOR_FUTURE_APPLICATION'},)),('unlink',()),('copy',())]:
            p=r.action_run_application_dry_run()
            with self.assertRaises(AccessError):getattr(p,method)(*args)
        with self.assertRaises(AccessError):self.env[LINE].create({'plan_id':p.id,'batch_id':r.batch_id.id})

    def test_discount_metadata_and_uom_changes_block(self):
        _,r=self._approved21();p=r.action_run_application_dry_run();self.target21.discount=5
        new=r.action_run_application_dry_run();self.assertEqual(new.historical_readiness,'BLOCKED')
        self.assertEqual(self.target21.discount,5);self.assertEqual(self.target21.price,100)
        self.assertEqual(p.line_ids.planned_after_values['discount'],'0')

    def test_unknown_vendor_target_cannot_be_declared(self):
        _,r=self._approved21(approve=False)
        other=self.env['res.partner'].create({'name':self.vendor.name})
        target=self.target21.copy({'partner_id':other.id})
        with self.assertRaises(AccessError):r.action_set_vendor_application_scope([dict(row_id=r.batch_id.row_ids.id,operation='update',target_id=target.id)],'Names are not identities',calendar_timezone=self.a.partner_id.tz or 'UTC')

    def test_no_operational_write_path_and_no_chatter(self):
        _,r=self._approved21();models=['product.supplierinfo','purchase.order','purchase.order.line','sale.order','sale.order.line','product.pricelist','product.pricelist.item','product.product','product.template','stock.quant','stock.move','stock.move.line','account.move','account.move.line','res.currency.rate','mail.mail','mail.message']
        def capture():
            result={}
            for model in models:
                records=self.env[model].with_context(active_test=False).search([])
                names=[n for n in ('id','write_date','state','price','price_unit','standard_price','quantity','reserved_quantity','value','amount_total','discount') if n in records._fields]
                result[model]=records.read(names,load=None)
            return result
        before=capture();supplier=type(self.env['product.supplierinfo'])
        with patch.object(supplier,'create',side_effect=AssertionError('DRY_RUN_SUPPLIER_CREATE')),patch.object(supplier,'write',side_effect=AssertionError('DRY_RUN_SUPPLIER_WRITE')),patch.object(supplier,'unlink',side_effect=AssertionError('DRY_RUN_SUPPLIER_UNLINK')):
            p=r.action_run_application_dry_run();p.get_current_application_plan();r.action_run_application_dry_run()
        self.assertEqual(capture(),before)
        self.assertFalse(any('apply' in name.lower() and 'button' in name.lower() for name in p._fields))

    def test_sales_auditor_foreign_portal_group_export_denials(self):
        _,r=self._approved21();p=r.action_run_application_dry_run()
        self.users['purchase_b'].group_ids=[Command.link(self.env.ref('vendor_price_revision_impact_simulator.group_vpr_finance_manager').id)]
        for user in (self.users['sales'],self.users['purchase_b'],self.env.ref('base.public_user')):
            for records in (p,p.line_ids,p.issue_ids):
                if records:
                    with self.assertRaises(AccessError):records.with_user(user).read(['id'])
            with self.assertRaises(AccessError):p.with_user(user).export_data(['name'])
        self.assertTrue(p.with_user(self.users['auditor']).read(['name']))
        with self.assertRaises(AccessError):p.with_user(self.users['auditor']).action_revalidate_application_plan()
        with self.assertRaises(AccessError):r.with_user(self.users['sales']).with_context(force_ready=True).action_run_application_dry_run()
        with self.assertRaises(AccessError):self.env['ir.attachment'].create(dict(name='forged',res_model=PLAN,res_id=p.id,type='binary'))
        self.assertFalse(self.env[PLAN].with_user(self.users['purchase_b']).search([('id','=',p.id)]))

    def test_legacy_approval_cannot_invent_creation_intent(self):
        s=self._prepare18(**self._policy20());r=self._request19(s);r.action_submit_for_review();self._vote20(r)
        p=r.action_run_application_dry_run();self.assertEqual(p.historical_readiness,'BLOCKED')
        self.assertIn('EXPLICIT_APPLICATION_INTENT_REQUIRED',p.issue_ids.mapped('code'))

    def test_customer_approval_never_authorizes_vendor_prices(self):
        s=self._prepare18(protection='price_adjustment_allowed_verified',**self._policy20())
        alt=s.action_clone_scenario('Supplier110');alt.action_set_assumptions([self._spec(value='110')],'Exact hypothetical supplier');alt.action_calculate_scenario()
        rec=s.action_generate_recommendations([self._input18(conditions='Customer notice evidenced')],alternative_ids=alt.ids)
        opt=rec.option_ids.filtered(lambda o:o.kind=='customer_eligible_price_review')
        r=self._request19(s,'customer_repricing',recommendation_id=rec.id,option_id=opt.id);r.action_submit_for_review()
        for stage in r.stage_ids.sorted('sequence'):
            for user in stage.assigned_ids:self.assertTrue(r.with_user(user).action_approve('Independent customer-only review'))
        p=r.action_run_application_dry_run();self.assertIn('APPROVAL_SCOPE_NOT_VENDOR_PRICING',p.issue_ids.mapped('code'));self.assertFalse(p.line_ids)
        _logger.info('PR21_REFERENCE_J customer_approved_not_vendor_authority')

    def test_dated_new_period_preserves_history(self):
        self._end21='2026-10-31';self._effective21='2026-11-01'
        _,r=self._approved21(operation='create');before=snapshot(self.target21)
        p=r.action_run_application_dry_run();self.assertEqual(p.line_ids.operation,'CREATE_CANDIDATE')
        self.assertEqual(p.line_ids.planned_after_values['date_start'],'2026-11-01')
        self.assertEqual(snapshot(self.target21),before)
        _logger.info('PR21_REFERENCE_I old100_through_Oct31 new109_from_Nov1 planned_only')

    def test_approved_uom_conversion_then_definition_change(self):
        self._end21='2026-10-31';self._effective21='2026-11-01';self._target_unit21=self.box
        _,r=self._approved21(operation='create');p=r.action_run_application_dry_run()
        self.assertEqual(p.line_ids.operation,'CREATE_CANDIDATE')
        self.assertEqual(float(p.line_ids.planned_after_values['price']),1090)
        self.assertEqual(float(p.line_ids.planned_after_values['min_qty']),10)
        self.box.relative_factor=12
        with self.assertRaises(UserError):p.get_current_application_plan()
        new=r.action_run_application_dry_run();self.assertEqual(new.historical_readiness,'BLOCKED')

    def test_ambiguous_duplicate_target_and_deletion(self):
        _,r=self._approved21();p=r.action_run_application_dry_run();self.target21.copy()
        duplicate=r.action_run_application_dry_run()
        self.assertIn('AMBIGUOUS_TARGET',duplicate.issue_ids.mapped('code'))
        self.target21.unlink()
        with self.assertRaises(UserError):p.get_current_application_plan()
        self.assertTrue(p.line_ids.evidence['intent']['target_id'])

    def test_expiry_during_planning_cannot_finish_ready(self):
        _,r=self._approved21(decision_validity_mode='days',decision_valid_days=1)
        original=ApplicationEngine.finish
        def expired(engine):
            with patch.object(fields.Datetime,'now',return_value=r.approval_valid_until):return original(engine)
        with patch.object(ApplicationEngine,'finish',expired):p=r.action_run_application_dry_run()
        self.assertEqual(p.historical_readiness,'BLOCKED');self.assertIn('APPROVAL_EXPIRED',p.issue_ids.mapped('code'))

    def test_plan_projection_states_and_no_forged_actor(self):
        _,r=self._approved21();p=r.action_run_application_dry_run()
        self.assertEqual(float(p.line_ids.price_delta),9);self.assertEqual(p.line_ids.approved_currency_id,self.inr)
        self.assertEqual(p.line_ids.approved_uom_id,self.unit)
        self.target21.price=105;new=r.action_run_application_dry_run()
        p.invalidate_recordset(['current_readiness']);self.assertEqual(p.current_readiness,'SUPERSEDED')
        with self.assertRaises(UserError):p.get_current_application_plan()
        with self.assertRaises(AccessError):new.line_ids.write({'plan_id':p.id})

    def test_company_calendar_is_frozen_and_caller_tz_cannot_replace_it(self):
        _,r=self._approved21();zone=r.vendor_application_scope['calendar_timezone']
        p=r.with_context(tz='Pacific/Honolulu').action_run_application_dry_run()
        self.assertEqual(p.evidence['calendar_timezone'],zone)
        self.a.partner_id.tz='Asia/Kolkata' if zone!='Asia/Kolkata' else 'UTC'
        new=r.action_run_application_dry_run()
        self.assertEqual(new.historical_readiness,'BLOCKED')
        self.assertIn('APPROVED_COMPANY_CALENDAR_MISSING_OR_CHANGED',new.issue_ids.mapped('code'))

    def test_real_intent_wizard_is_creator_bound(self):
        _,r=self._approved21(approve=False)
        wizard=self.env['vendor.price.revision.application.intent.wizard'].with_user(self.users['finance']).create(dict(request_id=r.id,row_id=r.batch_id.row_ids.id,operation='update',target_id=self.target21.id,target_uom_id=self.unit.id,calendar_timezone=self.a.partner_id.tz or 'UTC',reason='Explicit real wizard input'))
        action=wizard.action_declare();self.assertEqual(action['res_id'],r.id)
        with self.assertRaises(AccessError):wizard.with_user(self.reviewers['purchase']).action_declare()
