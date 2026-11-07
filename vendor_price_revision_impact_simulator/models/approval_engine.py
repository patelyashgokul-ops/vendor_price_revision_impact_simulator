"""Current financial evidence and least-privilege, company-bound reviewer routing."""
from decimal import localcontext
from odoo import api,fields
from odoo.exceptions import AccessError,UserError,ValidationError
from .approval_math import TYPES,ROLES,metrics,select_rules,plan,assign
from .commercial_math import number
from .profitability import nullable
from .structural_validation import digest

MODULE='vendor_price_revision_impact_simulator.'
VERSION='pr19_current_financial_sources_additive_risk_distinct_matching_no_decisions_v2'
RANK={'normal':0,'low':0,'warning':1,'medium':1,'high':2,'review_required':2,'critical':3}

class ApprovalEngine:
    def __init__(self,request):
        request.ensure_one();request.check_access('read')
        self.r=request;self.env=request.env;self.base=request.baseline_id;self.batch=request.batch_id;self.company=request.company_id

    def source(self):
        r=self.r;b=self.batch;base=self.base;base.check_access('read')
        if not self.env.user.active or self.company not in self.env.companies or b.state!='extracted' or b.revision_id.state!='draft':raise AccessError('Current selected company, active internal source scope and extracted draft revision required.')
        if base.batch_id!=b or b.revision_id.owner_id!=r.maker_id:raise UserError('SOURCE_IDENTITY_CHANGED: maker or exact revision/baseline changed; create a new version.')
        if not r.maker_id.active or r.maker_id.share or self.company not in r.maker_id.company_ids:raise UserError('MAKER_COMPANY_MISMATCH: accountable initiator must remain an active internal company member.')
        current=b.get_current_reconciliation(base.margin_id.id)
        if current!=base or base.readiness!='ready_for_financial_review' or base.critical_exception_count:raise UserError('SOURCE_RECONCILIATION_BLOCKED: current PR16 readiness and P0 controls required.')
        self.m=base.margin_id;self.f=self.m.financial_id
        n=nullable(self.m.net_revenue);c=nullable(self.m.revised_cost);self.rs=False
        sources=[base,self.m,self.f,self.f.cost_id,self.m.allocation_id,self.m.sales_id]
        if r.scenario_id:
            self.rs=r.scenario_id.get_current_scenario()
            if r.scenario_id.baseline_id!=base or not self.rs.complete or self.rs.state!='financially_verified':raise UserError('SOURCE_SCENARIO_STALE: exact complete current PR17 baseline required.')
            n=self.rs.profit['net_revenue'];c=self.rs.profit['revised_cost'];sources.extend([r.scenario_id,self.rs,r.scenario_id._inputs()])
        if r.request_type=='vendor_revision':
            if r.scenario_id or r.recommendation_id or r.option_id or base.scenario!='confirmed_baseline':raise ValidationError('Vendor revision requests require an exact confirmed PR16 scope, without an alternative or recommendation.')
        elif r.request_type=='supplier_scenario':
            if not self.rs or r.recommendation_id or r.option_id:raise ValidationError('Supplier scenario request requires only its exact current PR17 alternative.')
        elif r.request_type in ('customer_repricing','commercial_package'):
            rec=r.recommendation_id;opt=r.option_id
            if not rec or not opt or opt.recommendation_id!=rec or rec.scenario_id.baseline_id!=base:raise ValidationError('Exact same-baseline PR18 recommendation/option required.')
            rec.get_current_recommendation()
            if not rec.complete:raise UserError('RECOMMENDATION_STALE: current financially complete PR18 evidence required.')
            if r.request_type=='customer_repricing':
                if r.scenario_id!=rec.scenario_id or opt.kind!='customer_eligible_price_review' or opt.feasibility not in ('commercially_eligible_for_review','price_cap_constrained'):raise UserError('CUSTOMER_CONTRACT_REVIEW: no eligible customer pricing option; permission cannot be granted by an approval request.')
            elif not self.rs or opt.kind!='combined_customer_and_supplier_'+str(r.scenario_id.id) or r.scenario_id.id not in (rec.scope.get('alternative_ids') or []):raise ValidationError('Explicit combined PR18 option and matching PR17 alternative required; never add standalone benefits.')
            n=opt.values['values']['net_revenue'];c=opt.values['values']['revised_cost'];sources.extend([rec,opt,rec.scenario_id])
        else:raise ValidationError('Unsupported approval request type.')
        self.money=metrics(nullable(self.m.baseline_cost),c,nullable(self.m.net_revenue),n,self.company.currency_id.rounding)
        known=[self.m.risk_status,self.m.highest_line_risk]+self.m.line_ids.mapped('risk_status')
        if self.rs:known.append(self.rs.risk_status)
        if r.option_id:known.append(r.option_id.risk_status)
        severity=max((RANK.get(v,2) for v in known if v),default=2)
        protection=self.m.sales_id.line_ids.mapped('price_protection')
        self.flags=dict(high_risk=severity>=2,critical_risk=severity>=3,negative_profit=number(self.money['projected_profit'])<0 or any(nullable(v.revised_gross_profit) is not None and number(v.revised_gross_profit)<0 for v in self.m.line_ids),
            contract_review=any(v not in ('price_adjustment_allowed_verified','not_applicable') for v in protection),cost_decrease=number(self.money['signed_cost_change'])<0)
        if self.flags['negative_profit']:severity=3;self.flags.update(high_risk=True,critical_risk=True)
        self.risk=('normal','warning','high','critical')[severity]
        self.policy=self.env['vendor.price.revision.config'].get_company_revision_config(self.company,fields.Date.today())
        if not self.policy.workflow_enabled or r.request_type not in (self.policy.workflow_types or []):raise UserError('APPROVAL_POLICY_MISSING: enable and publish this company/request type explicitly.')
        errors=self.policy._workflow_errors()
        if errors:raise UserError('APPROVAL_MATRIX_GAP: '+'; '.join(errors))
        self.source_refs=[]
        for obj in sources:
            obj.check_access('read')
            if obj.company_id!=self.company:raise AccessError('CROSS_COMPANY_SOURCE_CONFLICT')
            self.source_refs.append(dict(model=obj._name,id=obj.id,version=obj.version if 'version' in obj._fields else None,fingerprint=obj.fingerprint if 'fingerprint' in obj._fields else None))
        self.policy_data=self.policy._approval_routing_snapshot()
        self.rules=[]
        for rule in self.policy.approval_ids.filtered('active').sorted('id'):
            self.rules.append(dict(id=rule.id,category=rule.category,types=rule.workflow_types or [],metric=rule.workflow_metric,trigger=rule.workflow_trigger,
                minimum=str(rule.minimum_amount),maximum=None if rule.open_ended else str(rule.maximum_amount),roles=[v for v in ROLES if self.env.ref(MODULE+v) in rule.required_role_ids],
                quorum=rule.required_independent_approvers,named=sorted(rule.workflow_named_reviewer_ids.ids)))
        submitter=r.submitted_by.id or self.env.uid
        self.excluded={r.maker_id.id,r.requested_by.id,submitter,1}
        if self.policy.workflow_exclude_contributors:
            self.excluded.update((self.m.collected_by|self.f.collected_by|base.collected_by).ids)
            self.excluded.add(b.uploaded_by.id)
            for obj in sources:
                self.excluded.update(obj.create_uid.ids)
            context=b.current_commercial_context_id
            for field in ('proposed_by','verified_by'):
                if field in context._fields:self.excluded.update(context[field].ids)
            if self.rs:self.excluded.update((self.rs.actor_id|r.scenario_id._inputs().actor_id).ids)
            if r.recommendation_id:self.excluded.add(r.recommendation_id.actor_id.id)
        self.package=dict(version=VERSION,company_id=self.company.id,currency_id=self.company.currency_id.id,revision_id=b.revision_id.id,batch_id=b.id,file_sha256=b.sha256_digest,
            maker_id=r.maker_id.id,creator_id=r.requested_by.id,submitter_id=submitter,request_type=r.request_type,source_refs=self.source_refs,
            source_reconciliation=dict(id=base.id,fingerprint=base.fingerprint,readiness=base.readiness,provenance=base.provenance),
            money=self.money,risk=self.risk,flags=self.flags,policy=self.policy_data,rules=self.rules,
            scenario_assumptions=[v.values for v in r.scenario_id._inputs().line_ids] if r.scenario_id else [],
            scenario_improvement_vs_original_proposal=self.rs.improvement_vs_proposal if self.rs else None,
            recommendation_option=r.option_id.values if r.option_id else None,
            commercial_status='Hypothetical proposal/eligible review only; no acceptance, consent, decision or application',excluded_reviewers=sorted(self.excluded))
        self.source_fingerprint=digest(self.package)
        return self

    def eligible(self,user,roles,excluded=None):
        if not user.active or user.share or user.id in (excluded if excluded is not None else self.excluded) or self.company not in user.company_ids:return False
        scoped=user.with_user(user).with_context(allowed_company_ids=self.company.ids)
        if not any(scoped.has_group(MODULE+role) for role in roles):return False
        try:
            for record in (self.base,self.r.scenario_id,self.r.recommendation_id,self.r.option_id):
                if record:record.with_user(user).with_context(allowed_company_ids=self.company.ids).check_access('read')
            # Explicit native order/line checks prevent an approval link broadening source rights.
            self.m.order_ids.with_user(user).with_context(allowed_company_ids=self.company.ids).check_access('read')
            self.m.order_ids.order_line.with_user(user).with_context(allowed_company_ids=self.company.ids).check_access('read')
            return True
        except AccessError:return False

    def route(self,assignments=True):
        with localcontext() as ctx:
            ctx.prec=38
            selected=select_rules(self.rules,self.r.request_type,self.money,self.flags,self.company.currency_id.rounding)
            escalations=[]
            def roles(records):return [v for v in ROLES if self.env.ref(MODULE+v) in records]
            if self.flags['critical_risk']:escalations.append(('critical_or_negative_profit',roles(self.policy.workflow_critical_group_ids)))
            if self.flags['high_risk']:escalations.append(('high_or_unknown_risk',roles(self.policy.workflow_high_group_ids)))
            if self.flags['contract_review']:escalations.append(('protected_or_unknown_customer_terms',roles(self.policy.workflow_contract_group_ids)))
            self.stages=plan(selected,escalations,self.policy.workflow_role_order,self.policy.minimum_distinct_approvers)
            users=self.env['res.users'].search([('active','=',True),('share','=',False),('company_ids','in',self.company.ids),('id','not in',sorted(self.excluded))],order='id',limit=5001)
            if len(users)>5000:raise UserError('NO_ELIGIBLE_APPROVER: bound reviewer directory through company membership before routing.')
            # Lock user/group metadata alongside company/source locks until submission commits.
            if users:self.env.cr.execute('SELECT id FROM res_users WHERE id IN %s ORDER BY id FOR SHARE',[tuple(users.ids)])
            group_ids=[self.env.ref(MODULE+v).id for v in ROLES]
            self.env.cr.execute('SELECT id FROM res_groups WHERE id IN %s ORDER BY id FOR SHARE',[tuple(group_ids)])
            eligible={role:[u.id for u in users if self.eligible(u,[role])] for role in ROLES}
            for stage in self.stages:
                candidates=set(uid for role in stage['roles'] for uid in eligible[role])
                for named in stage['named_sets']:candidates.intersection_update(named)
                stage['candidates']=sorted(candidates)
                if not candidates:raise UserError('NO_ELIGIBLE_APPROVER: '+stage['code']+'; grant exact source/company rights to an independent reviewer.')
            if not assignments:
                for i,stage in enumerate(self.stages):stage['sequence']=i+1
                return self
            assigned=assign(self.stages,self.r.manual_assignments or {} if self.policy.workflow_assignment=='manual' else None)
            for i,stage in enumerate(self.stages):stage.update(sequence=i+1,assigned=assigned[stage['code']],status='ready_for_review' if i==0 else 'waiting_predecessor')
            self.package['route']=self.stages
            self.fingerprint=digest(self.package)
            return self
