"""P0 exact approved native writes and atomic immutable transaction receipts."""
import logging
import re
from datetime import timedelta
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from .application_plan import PLAN
from .application_engine import ApplicationEngine, snapshot
from .application_math import MATERIAL, NUMERIC, same
from .approval_decisions import safe_json
from .commercial_math import number
from .execution_lock import scopes
from .structural_validation import digest

EXEC = 'vendor.price.revision.application.execution'
LINE = EXEC + '.line'
OPERATOR = 'vendor_price_revision_impact_simulator.group_vpr_pricing_operator'
_logger = logging.getLogger(__name__)
_RECEIPT_CAPABILITY = object()


def selection_key(line):
    return str(line['row_id'])+(':boundary:'+str(line['target_id']) if line.get('boundary') else '')


def operator(plan):
    plan.ensure_one(); plan.check_access('read')
    user = plan.env.user
    if not user.active or user.share or not user.has_group(OPERATOR):
        raise AccessError('OPERATOR_NOT_AUTHORIZED: explicit application role required.')
    if not any(user.has_group('vendor_price_revision_impact_simulator.'+g) for g in ('group_vpr_purchase_manager','group_vpr_finance_manager')):
        raise AccessError('SOURCE_REVIEW_ACCESS_REQUIRED: independent Purchase/Finance source access is also required.')
    if plan.company_id not in user.company_ids or plan.company_id not in plan.env.companies:
        raise AccessError('COMPANY_MISMATCH: exact selected authorized company required.')


def source_watch(request):
    """Read-only replay input stamp. Supplier writes do not rewrite APP evidence.

    Historical replay does not rerun financial sources against its own applied
    native mutations. This stamp detects replaced/corrected APP inputs/versions;
    it never grants fresh execution authority or asserts current financial profit.
    """
    env = request.env; data = {}
    for name in sorted(env.registry.models):
        if not name.startswith('vendor.price.revision.') or '.application.' in name or '.approval.' in name:
            continue
        model = env[name]
        if model._abstract or model._transient or not model._auto:
            continue
        key = next((k for k in ('batch_id', 'batch_source_id') if k in model._fields and model._fields[k].store), None)
        if not key or not re.fullmatch('[a-z0-9_]+', model._table):
            continue
        names = ['id'] + (['write_date'] if 'write_date' in model._fields else [])
        data[name] = model.search([(key, '=', request.batch_id.id)], order='id').read(names, load=None)
    data['revision'] = request.batch_id.revision_id.read(['id','write_date','state'], load=None)
    return digest(data)


def selection_contexts(env, lines, target_ids):
    """Actual selectors before/after, at threshold and interval boundaries.

    All contexts are evaluated; a large critical batch is never falsely marked
    behavior-verified because only its first twenty lines were sampled.
    """
    result = {}; memo = {}
    for line in lines:
        a = line['after']; unit = env['uom.uom'].browse(a['uom_id'])
        product = env['product.product'].browse(a['product_id']).with_company(a['company_id'])
        start = fields.Date.to_date(a['date_start']); end = fields.Date.to_date(a['date_end']) if a['date_end'] else None
        quantity = number(a['min_qty'])
        step = number('10') ** -env['decimal.precision'].precision_get('Product Unit')
        cases = [('at_start', start, quantity), ('below_moq', start, max(number('0'), quantity-step)),
                 ('above_moq', start, quantity+step), ('before_start', start-timedelta(days=1), quantity)]
        if end:
            cases += [('at_end', end, quantity), ('after_end', end+timedelta(days=1), quantity)]
        checks = {}
        for label, date, qty in cases:
            key = (product.id,a['partner_id'],a['company_id'],unit.id,str(date),str(qty))
            if key not in memo:
                chosen = product._select_seller(partner_id=env['res.partner'].browse(a['partner_id']),
                    quantity=float(qty), date=date, uom_id=unit)
                native = chosen.get('supplierinfo', env['product.supplierinfo'])
                memo[key] = dict(supplierinfo_id=native.id or None,
                    values=snapshot(native)[0] if native else None,
                    fallback_without_supplierinfo=bool(chosen and not native))
                if target_ids is not None and native and native not in product._get_filtered_sellers(
                        partner_id=env['res.partner'].browse(a['partner_id']), quantity=float(qty), date=date, uom_id=unit):
                    raise ValidationError('SUPPLIER_SELECTION_ELIGIBILITY_MISMATCH')
            checks[label] = memo[key]
        if target_ids is not None and not line.get('boundary'):
            observed = checks['at_start']['values']
            # Equal-priced independent tiers are permitted; effective net price,
            # exact vendor/variant/company/currency/unit and quantity eligibility
            # must match. Never call a last-PO fallback a verified new rule.
            for label in ('at_start',) + (('at_end',) if end else ()):
                observed = checks[label]['values']
                if (not observed or any(observed[k] != a[k] for k in ('partner_id','product_id','product_tmpl_id','company_id','currency_id','uom_id'))
                        or number(observed['min_qty']) > (quantity+step if label=='above_moq' else quantity)
                        or number(observed['price'])*(1-number(observed['discount'])/100) != number(a['price'])*(1-number(a['discount'])/100)):
                    raise ValidationError('SUPPLIER_SELECTION_MISMATCH: approved effective price not selected.')
        result[selection_key(line)] = checks
    return safe_json(result)


class ApplicationExecution(models.Model):
    _name = EXEC
    _inherit = 'vendor.price.revision.import.review.guard'
    _description = 'Immutable Verified Vendor Price Execution Receipt'
    _order = 'id desc'
    _key = models.Constraint('UNIQUE(execution_key)', 'One successful application per approved payload.')
    _authority = models.Constraint('UNIQUE(authorization_id)', 'This exact approval has an execution receipt.')
    name = fields.Char(required=True)
    plan_id = fields.Many2one(PLAN, required=True, ondelete='restrict', index=True)
    request_id = fields.Many2one('vendor.price.revision.approval.request', required=True, ondelete='restrict', index=True)
    authorization_id = fields.Many2one('vendor.price.revision.approval.authorization', required=True, ondelete='restrict')
    operator_id = fields.Many2one('res.users', required=True)
    execution_key = fields.Char(required=True, index=True)
    transaction_id = fields.Char(required=True)
    verified_at = fields.Datetime(required=True, string='Verification instant (authoritative after commit)')
    executed_at = fields.Datetime(compute='_commit_state')
    state = fields.Char(compute='_commit_state')
    current_target_status = fields.Char(compute='_target_state')
    evidence = fields.Json(required=True)
    fingerprint = fields.Char(required=True)
    source_fingerprint = fields.Char(required=True)
    target_fingerprint_before = fields.Char(required=True)
    target_fingerprint_after = fields.Char(required=True)
    create_count = fields.Integer(required=True)
    update_count = fields.Integer(required=True)
    no_change_count = fields.Integer(required=True)
    verified_line_count = fields.Integer(required=True)
    line_ids = fields.One2many(LINE, 'execution_id')

    @api.model
    def _record(self, values):
        if self.env.context.get('_vpr_receipt_capability') is not _RECEIPT_CAPABILITY:
            raise AccessError('Execution receipts require the validated transaction service, not a private method name or context flag.')
        plan=self.env[PLAN].browse(values['plan_id']);operator(plan)
        if values['operator_id']!=self.env.uid or values['batch_id']!=plan.batch_id.id or values['request_id']!=plan.request_id.id:
            raise AccessError('Execution receipt source/operator cannot be reassigned.')
        return super()._record(values)

    def _commit_state(self):
        self.env.cr.execute('SELECT pg_current_xact_id_if_assigned()::text')
        current = self.env.cr.fetchone()[0]
        for record in self:
            pending = record.transaction_id == current
            record.state = 'PENDING_COMMIT' if pending else 'VERIFIED'
            record.executed_at = False if pending else record.verified_at

    def _target_state(self):
        for record in self:
            try:
                record.current_target_status = ('VERIFIED_IN_TRANSACTION_PENDING_COMMIT' if record.state=='PENDING_COMMIT'
                    else record._check_receipt22(check_source=False))
            except (AccessError, UserError, ValidationError):
                record.current_target_status = 'UNAUTHORIZED_OR_INVALID_EVIDENCE'

    def _check_receipt22(self, check_source=True):
        self.ensure_one(); self.check_access('read')
        data = self.evidence; plan = self.plan_id; request = self.request_id
        artifact = self.authorization_id
        if (digest(data) != self.fingerprint or data['plan_fingerprint'] != plan.fingerprint or
                digest(plan.evidence) != plan.fingerprint or request != plan.request_id or
                artifact.request_id != request or artifact.fingerprint != digest(artifact.evidence) or
                artifact.source_fingerprint != request.source_fingerprint or
                artifact.request_type != request.request_type or
                digest(artifact.evidence['payload']) != artifact.payload_fingerprint or
                data['authorization_id'] != artifact.id or data['request_id'] != request.id or data['plan_id'] != plan.id or
                data['operator_id'] != self.operator_id.id or self.source_fingerprint != plan.source_fingerprint or
                data['approval_fingerprint'] != artifact.fingerprint or
                data['payload_fingerprint'] != request.payload_fingerprint or
                artifact.payload_fingerprint != request.payload_fingerprint or
                data['approved_payload'] != request.submitted_payload):
            raise UserError('EXECUTION_EVIDENCE_MISMATCH: no reapplication permitted.')
        if check_source and source_watch(request) != data['source_watch']:
            raise UserError('ALREADY_APPLIED_SOURCE_CHANGED: preserve execution; no reapplication permitted.')
        targets = self.env['product.supplierinfo'].browse([v['target_id'] for v in data['lines']]).exists()
        actual = {v['id']:v for v in snapshot(targets)}
        if any(v['target_id'] not in actual or not same(actual[v['target_id']],v['observed_after']) for v in data['lines']):
            return 'ALREADY_APPLIED_TARGET_CHANGED'
        return 'ALREADY_APPLIED' if self.create_count or self.update_count else 'ALREADY_VERIFIED_NO_CHANGE'

    def action_verify_execution(self):
        self.ensure_one(); self.check_access('read')
        if self.state == 'PENDING_COMMIT':
            return 'VERIFIED_IN_TRANSACTION_PENDING_COMMIT'
        return self._check_receipt22(check_source=False)

    def action_show_execution_verification(self):
        status=self.action_verify_execution()
        return dict(type='ir.actions.client',tag='display_notification',params=dict(title='Recorded execution target check',message=status,sticky=True,type='info'))


class ExecutionLine(models.Model):
    _name = LINE
    _inherit = 'vendor.price.revision.import.review.guard'
    _description = 'Immutable Actual Vendor Price Execution Line'
    execution_id = fields.Many2one(EXEC, required=True, ondelete='restrict', index=True)
    plan_line_id = fields.Many2one(PLAN+'.line', required=True, ondelete='restrict')
    row_id = fields.Many2one('vendor.price.revision.import.row', required=True, ondelete='restrict')
    operation = fields.Char(required=True)
    target_id = fields.Integer(required=True)
    before_values = fields.Json()
    approved_after_values = fields.Json(required=True)
    observed_after_values = fields.Json(required=True)
    fingerprint_before = fields.Char(required=True)
    fingerprint_after = fields.Char(required=True)
    verification = fields.Json(required=True)

    @api.model
    def _record(self, values):
        if self.env.context.get('_vpr_receipt_capability') is not _RECEIPT_CAPABILITY:
            raise AccessError('Execution lines require the validated transaction service.')
        for value in values:
            receipt=self.env[EXEC].browse(value['execution_id']);operator(receipt.plan_id)
            line=self.env[PLAN+'.line'].browse(value['plan_line_id'])
            if line.plan_id!=receipt.plan_id or line.row_id.id!=value['row_id'] or value['batch_id']!=receipt.batch_id.id:
                raise AccessError('Execution line provenance cannot be reassigned.')
        return super()._record(values)


class ExecutePlan(models.Model):
    _inherit = PLAN
    execution_ids = fields.One2many(EXEC, 'plan_id')

    def action_apply_approved_vendor_prices(self, confirmation=False, expected_fingerprint=None):
        self.ensure_one(); operator(self)
        if type(confirmation) is not bool or not confirmation or expected_fingerprint != self.fingerprint:
            raise UserError('EXPLICIT_CONFIRMATION_REQUIRED: review and confirm this exact immutable plan.')
        # Rebuild a minimal trusted ORM context. No client default_*, force_*,
        # skip_*, params or custom capability can select another native target.
        clean = api.Environment(self.env.cr, self.env.uid, {'allowed_company_ids':self.company_id.ids,
            'lang':self.env.user.lang, 'tz':self.evidence.get('calendar_timezone') or 'UTC'})
        plan = clean[PLAN].browse(self.id); operator(plan); request = plan.request_id
        with clean.cr.savepoint():
            try:
                request._lock20()  # company -> batch -> request, before price barriers
                clean.cr.execute('SELECT id FROM res_users WHERE id=%s FOR SHARE', [clean.uid])
                clean.user.invalidate_recordset(); operator(plan)
                groups = clean.user.group_ids.ids
                if groups:
                    clean.cr.execute('SELECT id FROM res_groups WHERE id IN %s ORDER BY id FOR SHARE', [tuple(sorted(groups))])
                if plan.fingerprint != digest(plan.evidence):
                    raise UserError('PAYLOAD_FINGERPRINT_MISMATCH')
                authority = request.authorization_id
                existing = clean[EXEC].search([('authorization_id','=',authority.id)], limit=1) if authority else clean[EXEC]
                if existing:
                    if existing.plan_id != plan:
                        raise UserError('ALREADY_APPLIED_DIFFERENT_PLAN: review the original execution.')
                    status = existing._check_receipt22()
                    if status == 'ALREADY_APPLIED_TARGET_CHANGED':
                        raise UserError(status + ': old approval cannot overwrite an external edit.')
                    return existing
                if request.approval_invalidated_at:
                    raise UserError('APPROVAL_INVALIDATED')
                if request.approval_valid_until and fields.Datetime.now()>=request.approval_valid_until:
                    raise UserError('APPROVAL_EXPIRED')
                if request.state!='approved' or not authority:
                    raise UserError('APPROVAL_NOT_FINAL')
                if request.request_type not in ('vendor_revision','supplier_scenario','commercial_package'):
                    raise UserError('APPROVAL_SCOPE_MISMATCH')
                evidence = plan.evidence
                frozen_lines = evidence.get('lines') or []
                if not frozen_lines or any(v['operation'] not in ('UPDATE_CANDIDATE','CREATE_CANDIDATE','NO_CHANGE') for v in frozen_lines):
                    raise UserError('PLAN_NOT_READY')
                native = clean['product.supplierinfo']
                for action in ('create','write'):
                    if any(v['operation'] == ('CREATE_CANDIDATE' if action=='create' else 'UPDATE_CANDIDATE') for v in frozen_lines):
                        native.check_access(action)  # native rights are never elevated
                scopes(clean, {(v['after']['partner_id'],v['after']['product_tmpl_id']) for v in frozen_lines})
                # A separately approved target unit need not occur in the
                # financial source or any existing vendor rule. Protect its
                # factor and ancestor definitions through actual commit too.
                units = clean['uom.uom'].browse(sorted({v['after']['uom_id'] for v in frozen_lines})).exists()
                units.check_access('read')
                unit_ids = sorted(set(units.ids) | {int(i) for unit in units for i in (unit.parent_path or '').split('/') if i})
                if unit_ids:
                    clean.cr.execute('SELECT id FROM uom_uom WHERE id IN %s ORDER BY id FOR SHARE', [tuple(unit_ids)])
                clean['uom.uom'].invalidate_model()
                ids = sorted({v['target_id'] for v in frozen_lines if v['target_id']})
                if ids:
                    clean.cr.execute('SELECT id FROM product_supplierinfo WHERE id IN %s ORDER BY id FOR UPDATE', [tuple(ids)])
                native.invalidate_model()
                # One full PR20 approval/PR16 reconciliation gate, under locks;
                # one exact PR21 reconstruction. No per-line source rebuild.
                data = ApplicationEngine(request).build()
                if digest(data) != plan.fingerprint or data['readiness'] != 'READY_FOR_FUTURE_APPLICATION':
                    raise UserError('PLAN_STALE: source, authority, reconciliation or targets changed.')
                latest = clean[PLAN].search([('request_id','=',request.id)],order='version desc,id desc',limit=1)
                if latest != plan:
                    raise UserError('PLAN_SUPERSEDED')
                policy = request.policy_id
                if policy.application_distinct_maker and clean.user in (request.maker_id | request.requested_by):
                    raise AccessError('MAKER_OPERATOR_SEPARATION_REQUIRED')
                if policy.application_distinct_approver and clean.user in (request.decision_ids.acting_user_id | request.decision_ids.reviewer_id):
                    raise AccessError('APPROVER_OPERATOR_SEPARATION_REQUIRED')
                by_row = {digest(v.evidence):v for v in plan.line_ids}
                if len(by_row) != len(frozen_lines):
                    raise UserError('PLAN_LINE_LEDGER_MISMATCH')
                for line in frozen_lines:
                    stored = by_row[digest(line)]
                    if (stored.evidence != line or stored.operation != line['operation'] or
                            stored.planned_after_values != line['after'] or (stored.before_values or None) != line['before']):
                        raise UserError('PLAN_LINE_LEDGER_MISMATCH')
                before_selection = selection_contexts(clean, frozen_lines, None)
                watch = source_watch(request)
                rows = []
                for line in sorted(frozen_lines,key=lambda v:(not v.get('boundary',False),v['row_id'])):
                    after = line['after']; op = line['operation']; before = line['before']
                    if set(after) != set(MATERIAL) or after['company_id'] != plan.company_id.id or not after['product_id']:
                        raise UserError('UNAPPROVED_FIELD_CHANGE_OR_SCOPE')
                    values = {k:float(after[k]) if k in NUMERIC else after[k] for k in MATERIAL}
                    if op == 'UPDATE_CANDIDATE':
                        changed = [k for k in MATERIAL if not same(before,after,[k])]
                        allowed={'date_end'} if line.get('boundary') else {'price','discount'}
                        if set(changed) - allowed:
                            raise UserError('UNAPPROVED_FIELD_CHANGE: date-boundary changes need an exact approved plan.')
                        target = native.browse(line['target_id'])
                        target.write({k:values[k] for k in changed})
                    elif op == 'CREATE_CANDIDATE':
                        target = native.create(values)
                    else:
                        target = native.browse(line['target_id'])
                    target.flush_recordset(); target.invalidate_recordset()
                    observed = snapshot(target)[0]
                    if not same(observed, after):
                        raise ValidationError('POST_WRITE_VERIFICATION_FAILED')
                    rows.append(dict(row_id=line['row_id'],plan_line_id=by_row[digest(line)].id,selection_key=selection_key(line),
                        operation=op,target_id=target.id,before=before,approved_after=after,observed_after=observed))
                native.flush_model(); native.invalidate_model()
                discovery = ApplicationEngine(request)
                discovery.payload = authority.evidence['payload']
                actual_universe = discovery.discover(
                    {v['after']['product_tmpl_id'] for v in frozen_lines},
                    {v['after']['product_id'] for v in frozen_lines})
                expected_universe = {v['id']:v for v in data['targets']}
                expected_universe.update({v['target_id']:v['observed_after'] for v in rows})
                if (set(expected_universe) != {v['id'] for v in actual_universe} or
                        any(not same(v,expected_universe[v['id']]) for v in actual_universe)):
                    raise ValidationError('POST_WRITE_UNIVERSE_MISMATCH')
                observed_selection = selection_contexts(clean,frozen_lines,[v['target_id'] for v in rows])
                # Outside-MOQ/date contexts retain pre-write effective behavior,
                # unless another explicitly approved line applies in that scope.
                touched = {v['target_id'] for v in rows}
                for rid, contexts in observed_selection.items():
                    for label in ('below_moq','before_start','after_end'):
                        if label in contexts and contexts[label] != before_selection[rid][label]:
                            if contexts[label]['supplierinfo_id'] not in touched:
                                raise ValidationError('SUPPLIER_SELECTION_BOUNDARY_MISMATCH')
                if request.approval_invalidated_at or (request.approval_valid_until and fields.Datetime.now() >= request.approval_valid_until):
                    raise UserError('APPROVAL_EXPIRED_OR_INVALIDATED')
                if source_watch(request) != watch:
                    raise UserError('SOURCE_CHANGED_DURING_APPLICATION')
                clean.cr.execute('SELECT pg_current_xact_id()::text'); xid = clean.cr.fetchone()[0]
                receipt_data = safe_json(dict(contract='pr22_atomic_native_vendor_price_v1',plan_id=plan.id,
                    plan_fingerprint=plan.fingerprint,request_id=request.id,authorization_id=authority.id,
                    approval_fingerprint=authority.fingerprint,payload_fingerprint=authority.payload_fingerprint,
                    approved_payload=authority.evidence['payload'],source_watch=watch,
                    execution_policy=policy._execution_snapshot22(),operator_id=clean.uid,transaction_id=xid,
                    rows_verified=len(rows),lines=rows,before_selection=before_selection,after_selection=observed_selection,
                    meaning='Verification inside one transaction. Receipt is successful only after framework commit; no realized financial benefit asserted.'))
                audit=clean[EXEC].with_context(_vpr_receipt_capability=_RECEIPT_CAPABILITY)
                receipt = audit._record(dict(batch_id=request.batch_id.id,name='EXEC-'+str(plan.id),
                    plan_id=plan.id,request_id=request.id,authorization_id=authority.id,operator_id=clean.uid,
                    execution_key=digest([plan.company_id.id,authority.id,authority.payload_fingerprint]),
                    transaction_id=xid,verified_at=fields.Datetime.now(),evidence=receipt_data,fingerprint=digest(receipt_data),
                    source_fingerprint=plan.source_fingerprint,target_fingerprint_before=plan.target_fingerprint,
                    target_fingerprint_after=digest([v['observed_after'] for v in rows]),
                    create_count=sum(v['operation']=='CREATE_CANDIDATE' for v in rows),
                    update_count=sum(v['operation']=='UPDATE_CANDIDATE' for v in rows),
                    no_change_count=sum(v['operation']=='NO_CHANGE' for v in rows),verified_line_count=len(rows)))
                clean[LINE].with_context(_vpr_receipt_capability=_RECEIPT_CAPABILITY)._record([dict(batch_id=request.batch_id.id,execution_id=receipt.id,plan_line_id=v['plan_line_id'],
                    row_id=v['row_id'],operation=v['operation'],target_id=v['target_id'],before_values=v['before'],
                    approved_after_values=v['approved_after'],observed_after_values=v['observed_after'],
                    fingerprint_before=digest(v['before']),fingerprint_after=digest(v['observed_after']),
                    verification=observed_selection[v['selection_key']]) for v in rows])
                clean.flush_all()
                return receipt
            except Exception:
                # Savepoint encloses *all* price and audit writes even if a Python
                # caller catches the error. No persisted failed-attempt claim.
                _logger.warning('PR22_APPLICATION_TRANSACTION_ABORTED plan=%s operator=%s; no success receipt retained', plan.id, clean.uid)
                raise
