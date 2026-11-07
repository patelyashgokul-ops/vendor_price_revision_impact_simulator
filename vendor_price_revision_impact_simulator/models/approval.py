"""PR19 request/routing foundation. Only PR20 may implement decisions."""
from datetime import timedelta
from odoo import api,fields,models,Command
from odoo.exceptions import AccessError,UserError,ValidationError
from .import_validation import PREFIX as IMPORT_PREFIX,ImmutableReview
from .product_resolution import company_lock
from .scenario_math import text
from .structural_validation import digest
from .approval_math import TYPES,ROLES
from .approval_engine import ApprovalEngine,MODULE

PREFIX='vendor.price.revision.approval.'
HEADER,STAGE,EVIDENCE,EVENT,ISSUE=[PREFIX+x for x in ('request','stage','evidence','event','issue')]
BASE='vendor.price.revision.reconciliation.run'
SCENARIO='vendor.price.revision.scenario'
REC='vendor.price.revision.recommendation'
INACTIVE=('withdrawn','stale','invalidated','superseded')
SOURCE_FIELDS=('baseline_id','scenario_id','recommendation_id','option_id','request_type','reason')
ACTIVITY_TOKEN=object()

def activity_model_id(value):
    """Recognize native Many2one target forms before native activity side effects."""
    if isinstance(value,dict):return value.get('id')
    if isinstance(value,(tuple,list)):return value[0] if value else False
    return getattr(value,'id',value)

def authority(env):
    if not env.user.active or env.user.share or not any(env.user.has_group(MODULE+r) for r in ROLES):raise AccessError('An active scoped commercial/financial manager authority is required; audit membership alone is read-only.')

class ApprovalRequest(models.Model):
    _name=HEADER
    _inherit=[IMPORT_PREFIX+'review.guard','mail.thread','mail.activity.mixin']
    _description='Management Review Request - No Approval Decision or Price Application'
    _order='id desc'
    _reference=models.Constraint('UNIQUE(name)','Unique stable request reference required.')
    _active=models.Constraint('UNIQUE(active_key)','One active request per exact source identity.')
    _version=models.Constraint('UNIQUE(scope_key,version)','Unique source-scope request version required.')
    name=fields.Char(required=True)
    baseline_id=fields.Many2one(BASE,required=True,ondelete='restrict',index=True)
    revision_id=fields.Many2one(related='batch_id.revision_id')
    currency_id=fields.Many2one('res.currency',required=True,ondelete='restrict')
    request_type=fields.Selection([(t,t.replace('_',' ').title()) for t in TYPES],required=True)
    scenario_id=fields.Many2one(SCENARIO,ondelete='restrict',index=True)
    recommendation_id=fields.Many2one(REC,ondelete='restrict',index=True)
    option_id=fields.Many2one(REC+'.option',ondelete='restrict')
    reason=fields.Text(required=True)
    requested_by=fields.Many2one('res.users',required=True)
    maker_id=fields.Many2one('res.users',required=True)
    submitted_by=fields.Many2one('res.users')
    submitted_at=fields.Datetime()
    scope_key=fields.Char(required=True,index=True)
    active_key=fields.Char(index=True)
    version=fields.Integer(required=True)
    previous_id=fields.Many2one(HEADER,ondelete='restrict')
    state=fields.Selection([(v,v.replace('_',' ').title()) for v in ('draft','ready_to_submit','blocked','awaiting_review')+INACTIVE],required=True,default='draft',index=True)
    current_state=fields.Char(compute='_effective_state')
    manual_assignments=fields.Json()
    policy_id=fields.Many2one('vendor.price.revision.config',ondelete='restrict')
    policy_version=fields.Char()
    source_fingerprint=fields.Char()
    submission_fingerprint=fields.Char()
    financial_values=fields.Json()
    risk_severity=fields.Char()
    financial_readiness=fields.Char()
    evidence_id=fields.Many2one(EVIDENCE,ondelete='restrict')
    stage_ids=fields.One2many(STAGE,'request_id')
    event_ids=fields.One2many(EVENT,'request_id')
    issue_ids=fields.One2many(ISSUE,'request_id')
    stale_reason=fields.Text()

    @api.model_create_multi
    def create(self,vals_list):
        return self.concat(*(self._prepare(v) for v in vals_list))

    @api.model
    def _prepare(self,vals,previous=None):
        authority(self.env)
        if set(vals)-set(SOURCE_FIELDS):raise AccessError('Only declared draft source links and reason may be supplied; state, maker, actors, policy, evidence and route are server-controlled.')
        values=dict(vals);text(values.get('reason'),'Approval request reason')
        if values.get('request_type') not in TYPES:raise ValidationError('Select a supported request type.')
        for key in ('baseline_id','scenario_id','recommendation_id','option_id'):
            if values.get(key) is False:values[key]=0
            if key in values and (type(values[key]) is not int or values[key]<0):raise ValidationError('Use exact integer source IDs.')
        base=self.env[BASE].browse(values.get('baseline_id',0)).exists();base.check_access('read')
        if not base:raise ValidationError('Exact financial reconciliation required.')
        batch=base.batch_id;company=base.company_id
        if company not in self.env.companies or company not in self.env.user.company_ids:raise AccessError('Selected authorized company required.')
        records=[]
        for key,model in (('scenario_id',SCENARIO),('recommendation_id',REC),('option_id',REC+'.option')):
            obj=self.env[model].browse(values.get(key,0)).exists();obj.check_access('read')
            if values.get(key) and not obj:raise ValidationError('Source record missing: '+key)
            if obj and obj.batch_id!=batch:raise AccessError('CROSS_COMPANY_SOURCE_CONFLICT: every source must belong to the exact batch/revision.')
            # Integer0 can remain browse(0) in Odoo20's relation cache. Persist
            # native False so an absent optional document is never a phantom ID.
            values[key]=obj.id if obj else False
            records.append(obj)
        scenario,rec,opt=records
        typ=values['request_type']
        if scenario and scenario.baseline_id!=base:raise ValidationError('Scenario baseline differs.')
        if rec and rec.scenario_id.baseline_id!=base:raise ValidationError('Recommendation baseline differs.')
        if opt and opt.recommendation_id!=rec:raise ValidationError('Option belongs to another recommendation.')
        if typ=='vendor_revision' and (scenario or rec or opt or base.scenario!='confirmed_baseline'):raise ValidationError('Vendor review uses only a confirmed exact baseline.')
        if typ=='supplier_scenario' and (not scenario or rec or opt):raise ValidationError('Supplier review requires only its selected scenario.')
        if typ=='customer_repricing':
            if not rec or not opt:raise ValidationError('Customer review requires an exact recommendation and customer option.')
            if scenario and scenario!=rec.scenario_id:raise ValidationError('Customer scenario mismatch.')
            values['scenario_id']=rec.scenario_id.id
        if typ=='commercial_package' and (not rec or not opt or not scenario):raise ValidationError('Explicit linked combined package required.')
        company_lock(self.env,company);batch._lock()
        key=digest(dict(company_id=company.id,batch_id=batch.id,**{k:values.get(k) or 0 for k in SOURCE_FIELDS if k!='reason'}))
        active=self.search([('active_key','=',key)],limit=1)
        if active:
            if previous:raise UserError('DUPLICATE_ACTIVE_APPROVAL_REQUEST: another current version exists.')
            return active
        old=self.search([('scope_key','=',key)],limit=1)
        parent=previous or old
        result=self.with_context(mail_create_nolog=True,mail_create_nosubscribe=True,tracking_disable=True)._record(dict(values,batch_id=batch.id,
            name=self.env['ir.sequence'].with_company(company).next_by_code('vpr.approval.request'),currency_id=base.currency_id.id,
            requested_by=self.env.uid,maker_id=batch.revision_id.owner_id.id,scope_key=key,active_key=key,version=max(old.version,parent.version)+1 if parent else 1,previous_id=parent.id,state='draft'))
        result._event('created','Draft source selection; no decision',{},'draft')
        return result

    def write(self,vals):
        self.check_access('write');authority(self.env)
        if set(vals)!={'reason'} or any(r.state not in ('draft','blocked','ready_to_submit') or r.requested_by!=self.env.user for r in self):raise AccessError('Only the creator may edit a draft reason. All authority, source links and submitted values require controlled services/new versions.')
        text(vals['reason'],'Draft reason')
        for r in self:r._lock();r._update(vals);r._event('draft_reason_changed',vals['reason'],{},r.state)
        return True

    def _update(self,values):
        self.check_access('write')
        return super(ImmutableReview,self.with_context(tracking_disable=True,mail_create_nolog=True,mail_create_nosubscribe=True)).write(values)

    def _lock(self):
        self.ensure_one();self.check_access('read');company_lock(self.env,self.company_id);self.batch_id._lock()
        self.env.cr.execute('SELECT id FROM vendor_price_revision_approval_request WHERE id=%s FOR UPDATE',[self.id])

    def _event(self,event,reason,data,new_state):
        return self.env[EVENT]._record(dict(batch_id=self.batch_id.id,request_id=self.id,event=event,reason=reason,data=dict(operation=event,details=data),actor_id=self.env.uid,recorded_at=fields.Datetime.now(),previous_state=self.state,new_state=new_state))

    def _builder(self,route=True):
        try:
            e=ApprovalEngine(self).source()
            return e.route() if route else e
        except ValueError as exc:raise UserError(str(exc)) from None

    def _submission_authority(self,policy):
        authority(self.env)
        if not any(self.env.user.with_user(self.env.user).has_group(g.get_external_id()[g.id]) for g in policy.workflow_submitter_group_ids):raise AccessError('Company policy does not authorize this submitting role.')

    def action_set_assignments(self,assignments):
        self._lock();authority(self.env)
        if self.state not in ('draft','blocked','ready_to_submit') or self.requested_by!=self.env.user:raise AccessError('Only the draft creator can propose assignments.')
        policy=self.env['vendor.price.revision.config'].get_company_revision_config(self.company_id,fields.Date.today())
        if not policy.workflow_enabled or policy.workflow_assignment!='manual':raise UserError('This company policy does not permit manual reviewer assignment.')
        if not isinstance(assignments,dict) or len(assignments)>32 or any(not isinstance(k,str) or not isinstance(v,list) or len(v)>32 or any(type(uid) is not int or uid<=0 for uid in v) for k,v in assignments.items()):raise ValidationError('Bound exact stage-code/user-ID lists; eligibility is checked on submission.')
        e=self._builder(route=False).route(assignments=False);plans={v['code']:v for v in e.stages};used=set()
        for code,ids in assignments.items():
            if code not in plans or len(ids)!=plans[code]['quorum'] or len(set(ids))!=len(ids) or any(uid not in plans[code]['candidates'] or uid in used for uid in ids):raise AccessError('Only current eligible independent reviewers and exact stage quorum may be proposed.')
            used.update(ids)
        self._update(dict(manual_assignments=assignments,state='draft'));self._event('assignment_proposed','Manual assignment proposal, not authority',assignments,'draft');return True

    def action_validate_request(self):
        self._lock();authority(self.env)
        if self.state not in ('draft','blocked','ready_to_submit'):raise UserError('Only editable drafts may be validated.')
        try:e=self._builder();self._submission_authority(e.policy)
        except (UserError,ValidationError) as exc:
            code=str(exc).split(':',1)[0][:100]
            self.env[ISSUE]._record(dict(batch_id=self.batch_id.id,request_id=self.id,code=code,description=str(exc),severity='critical',resolution='Correct exact source/policy/independent reviewer prerequisites and validate again; no waiver creates readiness.',actor_id=self.env.uid,recorded_at=fields.Datetime.now()))
            self._event('validation_blocked',str(exc),{},'blocked');self._update(dict(state='blocked'));return False
        self._event('validated','Current financial and independent routing prerequisites passed',dict(source=e.source_fingerprint,route=e.stages),'ready_to_submit')
        self._update(dict(state='ready_to_submit'));return True

    def action_submit_for_review(self):
        self._lock();authority(self.env)
        if self.state=='awaiting_review':self.get_current_request();return self
        if self.state not in ('draft','blocked','ready_to_submit'):raise UserError('Create a new version of withdrawn/stale history.')
        e=self._builder();self._submission_authority(e.policy)
        with self.env.cr.savepoint():
            self._event('submitted','Immutable financial evidence and route; no approval decision',dict(source=e.source_fingerprint),'awaiting_review')
            self._update(dict(state='awaiting_review',submitted_by=self.env.uid,submitted_at=fields.Datetime.now(),policy_id=e.policy.id,policy_version=e.policy.policy_version,
                source_fingerprint=e.source_fingerprint,submission_fingerprint=e.fingerprint,financial_values=e.money,risk_severity=e.risk,financial_readiness='ready_for_financial_review'))
            stages=self.env[STAGE]
            for spec in e.stages:
                stages|=self.env[STAGE]._record(dict(batch_id=self.batch_id.id,request_id=self.id,sequence=spec['sequence'],code=spec['code'],
                    required_group_ids=[Command.set([self.env.ref(MODULE+x).id for x in spec['roles']])],quorum=spec['quorum'],
                    candidate_ids=[Command.set(spec['candidates'])],assigned_ids=[Command.set(spec['assigned'])],stage_status=spec['status'],
                    plan=spec,assigned_by=self.env.uid,assigned_at=fields.Datetime.now(),policy_version=e.policy.policy_version))
            if e.policy.workflow_activities:
                first=stages.sorted('sequence')[:1]
                for user in first.assigned_ids:
                    activity=self.env['mail.activity'].with_context(_vpr_approval_activity=ACTIVITY_TOKEN,mail_activity_quick_update=True).create(dict(
                        res_model_id=self.env['ir.model']._get_id(HEADER),res_id=self.id,activity_type_id=self.env.ref('mail.mail_activity_data_todo').id,user_id=user.id,
                        summary='Management review required: '+self.name,note='Internal review routing only. Open the authorized request; no decision or price application.',date_deadline=fields.Date.today()+timedelta(days=e.policy.workflow_due_days)))
                    first._update(dict(activity_ids=[Command.link(activity.id)]))
                self._event('activities_created','Internal activities created; no email/delivery claim',dict(activity_ids=first.activity_ids.ids),'awaiting_review')
            data=dict(e.package,activities=stages.activity_ids.ids)
            evidence=self.env[EVIDENCE]._record(dict(batch_id=self.batch_id.id,request_id=self.id,fingerprint=digest(data),data=data,actor_id=self.env.uid,recorded_at=fields.Datetime.now()))
            self._update(dict(evidence_id=evidence.id));self._event('routed','Only first stage ready; all later stages await PR20 decisions',dict(stages=stages.ids,evidence=evidence.id),'awaiting_review')
        return self

    def get_current_request(self):
        self.ensure_one();self.check_access('read')
        if self.state!='awaiting_review':raise UserError('Request is not currently awaiting review.')
        e=self._builder(route=False)
        if e.source_fingerprint!=self.source_fingerprint or self.currency_id!=self.company_id.currency_id:raise UserError('Submitted source/policy changed; invalidate and create a new evidence version.')
        used=set()
        for stage in self.stage_ids:
            roles=stage.plan['roles']
            if len(stage.assigned_ids)!=stage.quorum or any(u.id in used or not e.eligible(u,roles) for u in stage.assigned_ids):raise UserError('Assigned reviewer company/role/source access or independent quorum changed.')
            used.update(stage.assigned_ids.ids)
        return self

    def _effective_state(self):
        for r in self:
            if r.state!='awaiting_review':r.current_state=r.state;continue
            try:r.get_current_request();r.current_state='awaiting_review'
            except (AccessError,UserError,ValidationError):r.current_state='stale_or_unauthorized'

    def _deactivate(self,state,reason):
        text(reason,'Lifecycle reason');old=self.state
        for stage in self.stage_ids:
            stage._update(dict(stage_status='cancelled' if state=='withdrawn' else 'invalidated'))
            stage.activity_ids.with_context(_vpr_approval_activity=ACTIVITY_TOKEN,mail_activity_quick_update=True).write(dict(active=False))
        self._event(state,reason,dict(previous_state=old,stages=self.stage_ids.ids),state)
        self._update(dict(state=state,active_key=False,stale_reason=reason))

    def action_refresh_readiness(self):
        self._lock();authority(self.env)
        if self.state!='awaiting_review':return self.state
        try:self.get_current_request()
        except (UserError,ValidationError,AccessError) as exc:self._deactivate('stale',str(exc));return 'stale'
        return 'awaiting_review'

    def action_withdraw_request(self,reason):
        self._lock();authority(self.env)
        if self.state=='withdrawn':return self
        if self.state not in ('draft','blocked','ready_to_submit','awaiting_review'):raise UserError('Only an undecided active request may be withdrawn.')
        policy=self.policy_id or self.env['vendor.price.revision.config'].get_company_revision_config(self.company_id,fields.Date.today())
        if self.env.user not in (self.maker_id|self.requested_by|self.submitted_by) and not (policy.workflow_manager_withdrawal and any(self.env.user.has_group(MODULE+x) for x in ('group_vpr_purchase_manager','group_vpr_finance_manager'))):raise AccessError('Only maker/creator/submitter or explicitly permitted manager can withdraw.')
        self._deactivate('withdrawn',reason);return self

    def action_new_version(self,values,reason):
        self._lock();authority(self.env);text(reason,'New version reason')
        if self.state not in INACTIVE:raise UserError('Invalidate/withdraw current routing before creating a new version.')
        if not isinstance(values,dict) or set(values)-set(SOURCE_FIELDS):raise ValidationError('Supply only new explicit source links and reason.')
        if values.get('request_type',self.request_type)!=self.request_type:raise ValidationError('A new version preserves its review type; prepare a separate request for a different commercial action.')
        source={k:(self[k].id or 0) if self._fields[k].type=='many2one' else self[k] for k in SOURCE_FIELDS};source.update(values,reason=reason)
        # Keep the whole publication atomic even when a caller catches the error.
        with self.env.cr.savepoint():
            new=self._prepare(source,previous=self)
            if new.batch_id.revision_id!=self.batch_id.revision_id:raise AccessError('A new version preserves exact original revision/company.')
            self._event('superseded',reason,dict(new_request_id=new.id),'superseded');self._update(dict(state='superseded'))
        return new

    @api.model
    def action_my_pending_reviews(self):
        stages=self.env[STAGE].search([('assigned_ids','in',[self.env.uid]),('stage_status','=','ready_for_review'),('request_id.state','=','awaiting_review')],limit=501)
        if len(stages)>500:raise UserError('Narrow the selected companies; at most500 active stages are validated per inbox request.')
        current=set()
        for request in stages.request_id:
            try:request.get_current_request();current.add(request.id)
            except (UserError,AccessError,ValidationError):pass
        return dict(type='ir.actions.act_window',name='My current review assignments - no decision',res_model=STAGE,view_mode='list,form',domain=[('id','in',stages.filtered(lambda s:s.request_id.id in current).ids)])

    def action_open_source(self):
        self.ensure_one();self.check_access('read');self.baseline_id.check_access('read')
        return dict(type='ir.actions.act_window',res_model=BASE,res_id=self.baseline_id.id,view_mode='form')

    def message_subscribe(self,partner_ids=None,subtype_ids=None):
        self.check_access('read');return True  # Activity assignment must not create external followers.

    def message_post(self,**kw):raise AccessError('Approval evidence uses append-only internal audit, not chatter/external notifications.')
    def message_notify(self,**kw):raise AccessError('External/email notification is outside this routing foundation.')

class ApprovalStage(models.Model):
    _name=STAGE
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Sequential Planned Review Stage - No Decision'
    _order='request_id,sequence,id'
    _unique=models.Constraint('UNIQUE(request_id,code)','One exact stage per request.')
    request_id=fields.Many2one(HEADER,required=True,ondelete='restrict',index=True)
    sequence=fields.Integer(required=True)
    code=fields.Char(required=True)
    required_group_ids=fields.Many2many('res.groups',relation='vpr_ap_stage_group_rel')
    candidate_ids=fields.Many2many('res.users',relation='vpr_ap_stage_candidate_rel',string='Submitted eligible candidate snapshot')
    assigned_ids=fields.Many2many('res.users',relation='vpr_ap_stage_assigned_rel')
    quorum=fields.Integer(required=True)
    stage_status=fields.Selection([(v,v.replace('_',' ').title()) for v in ('ready_for_review','waiting_predecessor','invalidated','cancelled')],required=True,index=True)
    effective_status=fields.Char(compute='_effective_status')
    plan=fields.Json(required=True)
    assigned_by=fields.Many2one('res.users',required=True)
    assigned_at=fields.Datetime(required=True)
    policy_version=fields.Char(required=True)
    activity_ids=fields.Many2many('mail.activity',relation='vpr_ap_stage_activity_rel')
    def _update(self,values):return super(ImmutableReview,self).write(values)
    def _effective_status(self):
        cache={}
        for s in self:
            if s.request_id.id not in cache:cache[s.request_id.id]=s.request_id.current_state
            s.effective_status=s.stage_status if cache[s.request_id.id]=='awaiting_review' else 'inactive_or_stale'

class ApprovalEvidence(models.Model):
    _name=EVIDENCE
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Immutable Submitted Financial and Routing Evidence'
    request_id=fields.Many2one(HEADER,required=True,ondelete='restrict',index=True)
    fingerprint=fields.Char(required=True)
    data=fields.Json(required=True)
    actor_id=fields.Many2one('res.users',required=True)
    recorded_at=fields.Datetime(required=True)

class ApprovalEvent(models.Model):
    _name=EVENT
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Append-Only Approval Foundation Audit - Not Decisions'
    _order='id desc'
    request_id=fields.Many2one(HEADER,required=True,ondelete='restrict',index=True)
    event=fields.Char(required=True)
    reason=fields.Text(required=True)
    data=fields.Json(required=True)
    actor_id=fields.Many2one('res.users',required=True)
    recorded_at=fields.Datetime(required=True)
    previous_state=fields.Char()
    new_state=fields.Char(required=True)

class ApprovalIssue(models.Model):
    _name=ISSUE
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Retained Approval Prerequisite Blocker'
    _order='id desc'
    request_id=fields.Many2one(HEADER,required=True,ondelete='restrict',index=True)
    code=fields.Char(required=True)
    severity=fields.Char(required=True)
    description=fields.Text(required=True)
    resolution=fields.Text(required=True)
    actor_id=fields.Many2one('res.users',required=True)
    recorded_at=fields.Datetime(required=True)

class ApprovalActivity(models.Model):
    _inherit='mail.activity'
    @api.model_create_multi
    def create(self,vals_list):
        rid=self.env['ir.model']._get_id(HEADER)
        defaults=self.default_get(['res_model_id','res_model'])
        if any(activity_model_id(v.get('res_model_id',defaults.get('res_model_id')))==rid or v.get('res_model',defaults.get('res_model'))==HEADER for v in vals_list) and self.env.context.get('_vpr_approval_activity') is not ACTIVITY_TOKEN:raise AccessError('Approval activities are created only by validated first-stage routing.')
        return super().create(vals_list)
    def write(self,vals):
        rid=self.env['ir.model']._get_id(HEADER)
        if (any(a.res_model==HEADER for a in self) or activity_model_id(vals.get('res_model_id'))==rid or vals.get('res_model')==HEADER) and self.env.context.get('_vpr_approval_activity') is not ACTIVITY_TOKEN:raise AccessError('Approval activities are archived by controlled workflow actions; activity completion is not approval.')
        return super().write(vals)
    def unlink(self):
        if any(a.res_model==HEADER for a in self):raise AccessError('Approval activity history is retained; archive through request lifecycle.')
        return super().unlink()

class ApprovalWizard(models.TransientModel):
    _name=PREFIX+'wizard'
    _inherit='vendor.price.revision.purchase.wizard.boundary'
    _description='Prepare Exact Approval Review Scope'
    baseline_id=fields.Many2one(BASE,required=True)
    request_type=fields.Selection([(v,v.replace('_',' ').title()) for v in TYPES],default='vendor_revision',required=True)
    scenario_id=fields.Many2one(SCENARIO)
    recommendation_id=fields.Many2one(REC)
    option_id=fields.Many2one(REC+'.option')
    reason=fields.Text(required=True)
    def action_prepare(self):
        self.ensure_one()
        values={k:(self[k].id or 0) if self._fields[k].type=='many2one' else self[k] for k in SOURCE_FIELDS}
        r=self.env[HEADER].create(values)
        return dict(type='ir.actions.act_window',res_model=HEADER,res_id=r.id,view_mode='form')

class ApprovalLifecycleWizard(models.TransientModel):
    _name=PREFIX+'lifecycle.wizard'
    _inherit='vendor.price.revision.purchase.wizard.boundary'
    _description='Reasoned Approval Routing Withdrawal or New Version'
    request_id=fields.Many2one(HEADER,required=True)
    operation=fields.Selection([('withdraw','Withdraw undecided request'),('new_version','New draft version with explicit current sources')],required=True)
    baseline_id=fields.Many2one(BASE)
    scenario_id=fields.Many2one(SCENARIO)
    recommendation_id=fields.Many2one(REC)
    option_id=fields.Many2one(REC+'.option')
    reason=fields.Text(required=True)
    def action_execute(self):
        self.ensure_one();r=self.request_id
        if self.operation=='withdraw':r.action_withdraw_request(self.reason)
        else:
            if not self.baseline_id:raise ValidationError('Select explicit current financial sources for the new version.')
            values={k:self[k].id or 0 for k in ('baseline_id','scenario_id','recommendation_id','option_id')}
            r=r.action_new_version(values,self.reason)
        return dict(type='ir.actions.act_window',res_model=HEADER,res_id=r.id,view_mode='form')

class ApprovalSourceAction(models.Model):
    _inherit=BASE
    def action_prepare_approval_request(self):
        self.ensure_one();self.check_access('read');authority(self.env)
        return dict(type='ir.actions.act_window',res_model=PREFIX+'wizard',view_mode='form',target='new',context=dict(default_baseline_id=self.id))

class ApprovalRequestActions(models.Model):
    _inherit=HEADER
    def action_open_lifecycle(self):
        self.ensure_one();self.check_access('read');authority(self.env)
        return dict(type='ir.actions.act_window',res_model=PREFIX+'lifecycle.wizard',view_mode='form',target='new',context=dict(default_request_id=self.id))
    def action_open_assignment(self):
        self.ensure_one();self.check_access('read');authority(self.env)
        if self.requested_by!=self.env.user or self.state not in ('draft','blocked','ready_to_submit'):raise AccessError('Only the creator can assign draft review levels.')
        policy=self.env['vendor.price.revision.config'].get_company_revision_config(self.company_id,fields.Date.today())
        if not policy.workflow_enabled or policy.workflow_assignment!='manual':raise UserError('This company selects independent reviewers deterministically; manual assignment is not enabled.')
        return dict(type='ir.actions.act_window',res_model=PREFIX+'assignment.wizard',view_mode='form',target='new',context=dict(default_request_id=self.id))

class ApprovalAssignmentWizard(models.TransientModel):
    _name=PREFIX+'assignment.wizard'
    _inherit='vendor.price.revision.purchase.wizard.boundary'
    _description='Choose Current Independent Reviewers for One Draft Level'
    request_id=fields.Many2one(HEADER,required=True)
    stage_code=fields.Selection('_stage_choices',required=True,string='Review level')
    candidate_ids=fields.Many2many('res.users',relation='vpr_ap_input_candidates_rel',compute='_candidates')
    quorum=fields.Integer(compute='_candidates')
    assigned_ids=fields.Many2many('res.users',relation='vpr_ap_input_assigned_rel',string='Proposed independent reviewers')

    @api.model
    def _stage_choices(self):
        rid=self.env.context.get('default_request_id')
        if type(rid) is not int or rid<=0:return []
        r=self.env[HEADER].browse(rid);r.check_access('read');authority(self.env)
        e=r._builder(route=False).route(assignments=False)
        return [(s['code'],str(s['sequence'])+': '+', '.join(self.env.ref(MODULE+v).display_name for v in s['roles'])+' ('+str(s['quorum'])+' distinct)') for s in e.stages]

    @api.depends('request_id','stage_code')
    def _candidates(self):
        for w in self:
            w.candidate_ids=False;w.quorum=0
            if not w.request_id or not w.stage_code:continue
            e=w.request_id._builder(route=False).route(assignments=False)
            stage=next((v for v in e.stages if v['code']==w.stage_code),None)
            if stage:w.candidate_ids=self.env['res.users'].browse(stage['candidates']);w.quorum=stage['quorum']

    def action_save(self):
        self.ensure_one();values=dict(self.request_id.manual_assignments or {});values[self.stage_code]=self.assigned_ids.ids
        self.request_id.action_set_assignments(values)
        return dict(type='ir.actions.act_window',res_model=HEADER,res_id=self.request_id.id,view_mode='form')
