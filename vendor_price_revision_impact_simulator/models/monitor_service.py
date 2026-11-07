"""Bounded original-user read-only price monitoring. Never invokes the PR22 gateway."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
import time
from odoo import api, fields, models
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError
from .application_engine import snapshot, schema
from .commercial_engine import uom_snapshot
from .application_math import MATERIAL, same, identity
from .execution import EXEC, LINE
from .structural_validation import digest
from .monitor_math import VERSION, CATEGORIES, differences, compatible, severity
from .monitor_models import RUN, CHECK, INCIDENT, EVENT, authority, record, update

MAX_LINES = 100
MAX_HISTORY = 10000


def lock(execution):
    # Nonblocking transaction lock: overlapping attempts retry rather than wait
    # under an already established repeatable-read snapshot. Unique incident keys
    # and versioned ORM writes remain the final stale-snapshot backstop.
    execution.env.cr.execute('SELECT pg_try_advisory_xact_lock(%s,%s)', [230600, execution.id])
    if not execution.env.cr.fetchone()[0]:
        raise UserError('MONITOR_BUSY: retry this bounded observation in a fresh transaction.')


def historical(line, cache):
    """Validate original immutable event, not today's approval expiry/source state."""
    execution = line.execution_id
    if execution.id not in cache:
        execution.check_access('read'); plan = execution.plan_id; auth = execution.authorization_id
        plan.check_access('read'); auth.check_access('read'); execution.request_id.check_access('read')
        data = execution.evidence or {}
        valid = (execution.state == 'VERIFIED' and data.get('contract') == 'pr22_atomic_native_vendor_price_v1'
            and digest(data) == execution.fingerprint and digest(plan.evidence) == plan.fingerprint
            and data.get('plan_fingerprint') == plan.fingerprint and data.get('plan_id') == plan.id
            and data.get('request_id') == execution.request_id.id == plan.request_id.id
            and data.get('authorization_id') == auth.id and auth.request_id == execution.request_id
            and digest(auth.evidence) == auth.fingerprint == data.get('approval_fingerprint')
            and digest(auth.evidence.get('payload')) == auth.payload_fingerprint == data.get('payload_fingerprint')
            and data.get('approved_payload') == auth.evidence.get('payload')
            and data.get('operator_id') == execution.operator_id.id
            and data.get('transaction_id') == execution.transaction_id
            and execution.source_fingerprint == plan.source_fingerprint
            and (data.get('approved_payload') or {}).get('company_id') == execution.company_id.id
            and len(data.get('lines', [])) == execution.verified_line_count == len(execution.line_ids))
        by_plan_line = defaultdict(list)
        for item in data.get('lines', []):
            by_plan_line[item.get('plan_line_id')].append(item)
        cache[execution.id] = (bool(valid), data, by_plan_line)
    valid, data, by_plan_line = cache[execution.id]
    if not valid:
        return False
    line.check_access('read')
    items = by_plan_line[line.plan_line_id.id]
    return bool(len(items) == 1 and line.batch_id == execution.batch_id and
        line.plan_line_id.plan_id == execution.plan_id and
        line.plan_line_id.evidence in execution.plan_id.evidence.get('lines', []) and
        items[0].get('target_id') == line.target_id and items[0].get('row_id') == line.row_id.id and
        items[0].get('operation') == line.operation and
        (items[0].get('before') == line.before_values or (items[0].get('before') is None and line.before_values is False)) and
        items[0].get('approved_after') == line.approved_after_values and
        items[0].get('observed_after') == line.observed_after_values and
        digest(items[0].get('before')) == line.fingerprint_before and digest(line.observed_after_values) == line.fingerprint_after and
        same(line.approved_after_values, line.observed_after_values) and
        set(MATERIAL) <= line.observed_after_values.keys() and
        data.get('after_selection', {}).get(items[0].get('selection_key')) == line.verification)


class Observation:
    def __init__(self, execution, lines):
        self.execution = execution; self.env = execution.env; self.lines = lines
        self.cache = {}; self.selector_cache = {}; self.candidate_cache = {}
        try:
            self.schema = schema(self.env)
        except ValidationError:
            self.schema = None
        # Query by bounded exact target IDs, not the complete price history.
        history = self.env[LINE].search([('company_id', '=', execution.company_id.id),
            ('target_id', 'in', lines.mapped('target_id'))], order='id', limit=MAX_HISTORY + 1)
        self.history_complete = len(history) <= MAX_HISTORY
        self.history = defaultdict(list)
        for line in history[:MAX_HISTORY]:
            self.history[line.target_id].append(line)
        self.now = fields.Datetime.now()

    def successor(self, line):
        source = line.observed_after_values
        candidates = [v for v in self.history[line.target_id]
            if (v.execution_id.verified_at, v.execution_id.id, v.id) >
               (line.execution_id.verified_at, line.execution_id.id, line.id)]
        expected = line; invalid = False
        for other in sorted(candidates, key=lambda v:(v.execution_id.verified_at,v.execution_id.id,v.id)):
            # Pending application is not a successful baseline. The same snapshot
            # cannot see an uncommitted application from another transaction.
            if other.execution_id.state != 'VERIFIED':
                invalid = True; continue
            if not historical(other, self.cache):
                invalid = True; continue
            source = expected.observed_after_values
            values = other.observed_after_values
            if compatible(source, values):
                expected = other
            else:
                # Explicit PR22 boundary closure is authorized for the exact old
                # target even though its date_end intentionally changes.
                changed = differences(source, values)
                if set(changed) == {'date_end'} and other.plan_line_id.evidence.get('boundary'):
                    expected = other
                else:
                    invalid = True
        return expected, invalid

    def selection(self, line):
        expected = line.observed_after_values
        scope_schema = (line.execution_id.evidence.get('approved_payload') or {}).get('vendor_application_scope', {}).get('schema')
        if scope_schema != self.schema:
            return {}, ['SELECTION_CHECK_UNAVAILABLE']
        contexts = line.verification or {}
        if not contexts or not expected.get('product_id'):
            return {}, ['SELECTION_CHECK_UNAVAILABLE']
        product = self.env['product.product'].browse(expected['product_id']); product.check_access('read')
        partner = self.env['res.partner'].browse(expected['partner_id']); partner.check_access('read')
        unit = self.env['uom.uom'].browse(expected['uom_id']); unit.check_access('read')
        start = fields.Date.to_date(expected['date_start']) if expected['date_start'] else fields.Date.context_today(product)
        end = fields.Date.to_date(expected['date_end']) if expected['date_end'] else None
        step = Decimal(10) ** -self.env['decimal.precision'].precision_get('Product Unit')
        qty = Decimal(expected['min_qty'])
        definitions = {'at_start': (start,qty), 'below_moq': (start,max(Decimal(0),qty-step)),
            'above_moq': (start,qty+step), 'before_start': (start-timedelta(days=1),qty)}
        if end:
            definitions.update(at_end=(end,qty), after_end=(end+timedelta(days=1),qty))
        results = {}; codes = []
        for name, before in contexts.items():
            if name not in definitions:
                codes.append('SELECTION_CHECK_UNAVAILABLE'); continue
            date, quantity = definitions[name]
            key = (product.id, partner.id, unit.id, str(date), str(quantity))
            if key not in self.selector_cache:
                selected = product.with_company(self.execution.company_id)._select_seller(
                    partner_id=partner, quantity=float(quantity), date=date, uom_id=unit)
                if not isinstance(selected, dict):
                    raise ValidationError('Unsupported selector return contract')
                chosen = selected.get('supplierinfo', self.env['product.supplierinfo'])
                if chosen:
                    chosen.check_access('read')
                    if chosen.company_id and chosen.company_id != self.execution.company_id:
                        raise AccessError('Selection outside authorized company')
                current = snapshot(chosen)[0] if chosen else None
                self.selector_cache[key] = (chosen.id if chosen else None, current,
                    bool(selected and not chosen))
            chosen_id, values, fallback = self.selector_cache[key]
            old = before.get('values')
            matches = chosen_id == before.get('supplierinfo_id') and ((not old and not values) or
                (old is not None and values is not None and same(old, values)))
            # A different ID is never silently treated as the original target.
            results[name] = dict(date=str(date), quantity=str(quantity), uom_id=unit.id,
                vendor_id=partner.id, product_id=product.id, company_id=self.execution.company_id.id,
                baseline=before, selected_id=chosen_id, values=values,
                fallback_without_supplierinfo=fallback, status='PASS' if matches else 'DRIFT_DETECTED')
            if not matches:
                codes.append('RULE_SELECTION_DRIFT')
        # Exact duplicate identities can be dangerous even if the winner is stable.
        candidate_key = (partner.id,expected['product_tmpl_id'],product.id)
        if candidate_key not in self.candidate_cache:
            candidates = self.env['product.supplierinfo'].with_context(active_test=False).search([
                ('company_id', 'in', [False,self.execution.company_id.id]),
                ('partner_id', '=', partner.id), ('product_tmpl_id', '=', expected['product_tmpl_id']),
                ('product_id', 'in', [False, product.id])], limit=MAX_HISTORY+1)
            counts = defaultdict(int)
            if len(candidates) <= MAX_HISTORY:
                for value in snapshot(candidates):
                    counts[identity(value)] += 1
            self.candidate_cache[candidate_key] = (len(candidates)>MAX_HISTORY, counts)
        incomplete, counts = self.candidate_cache[candidate_key]
        if incomplete:
            codes.append('SELECTION_CHECK_UNAVAILABLE')
        elif counts[identity(expected)] > 1:
            codes.append('DUPLICATE_EFFECTIVE_RULE')
        return results, codes

    def observe(self, line):
        payload = dict(expected=None, observed=None, differences={}, selection={}, metadata={}, codes=[],
            status='BLOCKED', classification='SOURCE_EVIDENCE_INCOMPLETE', successor_line_id=False)
        if not historical(line, self.cache):
            payload['codes'] = ['HISTORICAL_EVIDENCE_INTEGRITY']; return payload
        if not self.history_complete:
            payload['codes'] = ['SUCCESSOR_LINKAGE_UNVERIFIED']; return payload
        expected_line, invalid = self.successor(line)
        expected = expected_line.observed_after_values
        payload.update(expected=expected, successor_line_id=expected_line.id if expected_line != line else False)
        if self.schema is None:
            payload.update(codes=['MONITORING_SCHEMA_UNSUPPORTED'], classification='MONITORING_SCHEMA_UNSUPPORTED')
            return payload
        native = self.env['product.supplierinfo'].with_context(active_test=False)
        native.check_access('read')
        target = native.browse(line.target_id).exists()
        if not target:
            payload.update(codes=['TARGET_MISSING'], status='DRIFT_DETECTED', classification='TARGET_NOT_FOUND_VERIFIED')
            return payload
        target.check_access('read')
        # Never retain another company's current costs in this company's evidence.
        if target.company_id and target.company_id != self.execution.company_id:
            payload.update(codes=['COMPANY_SCOPE_DRIFT'], classification='CROSS_COMPANY_ACCESS_BLOCKED')
            return payload
        observed = snapshot(target)[0]
        payload.update(observed=observed, differences=differences(expected, observed),
            metadata=dict(write_uid=target.write_uid.id, write_date=str(target.write_date),
                archive_supported='active' in target._fields,
                attribution='Supplementary last ORM writer only; commercial authorization unproven.'))
        codes = [CATEGORIES[key] for key in payload['differences']]
        intents = (expected_line.execution_id.evidence.get('approved_payload') or {}).get('vendor_application_scope', {}).get('lines', [])
        intent = next((v for v in intents if v.get('row_id') == expected_line.row_id.id), {})
        frozen_unit = intent.get('target_uom')
        unit = self.env['uom.uom'].browse(expected['uom_id']); unit.check_access('read')
        current_unit = uom_snapshot(unit)
        unit_keys = ('id','factor','relative_factor','relative_uom_id','parent_path','active')
        payload['metadata'].update(approved_unit_definition=frozen_unit, observed_unit_definition=current_unit)
        if not frozen_unit:
            codes.append('HISTORICAL_EVIDENCE_INTEGRITY')
        elif any(frozen_unit.get(key) != current_unit.get(key) for key in unit_keys):
            codes.append('UOM_DEFINITION_DRIFT')
            payload['differences']['uom_definition'] = dict(expected=frozen_unit,observed=current_unit)
        product = self.env['product.product'].browse(expected['product_id']); product.check_access('read')
        current_product = dict(id=product.id,template_id=product.product_tmpl_id.id,company_id=product.company_id.id,
            active=product.active,purchase_ok=product.purchase_ok)
        payload['metadata'].update(approved_product_scope=intent.get('product_scope'),observed_product_scope=current_product)
        if intent.get('product_scope') != current_product:
            codes.append('PRODUCT_SCOPE_DRIFT')
            payload['differences']['product_scope'] = dict(expected=intent.get('product_scope'),observed=current_product)
        if 'active' in target._fields and not target.active:
            codes.append('TARGET_ARCHIVED')
        if invalid:
            codes.append('SUCCESSOR_LINKAGE_UNVERIFIED')
        try:
            selection, selection_codes = self.selection(expected_line)
            payload['selection'] = selection; codes.extend(selection_codes)
        except (UserError, ValidationError, TypeError, ValueError, AttributeError):
            codes.append('SELECTION_CHECK_UNAVAILABLE')
        payload['codes'] = sorted(set(codes))
        payload['status'] = ('BLOCKED' if any(c in codes for c in
            ('SELECTION_CHECK_UNAVAILABLE','SUCCESSOR_LINKAGE_UNVERIFIED','HISTORICAL_EVIDENCE_INTEGRITY')) else 'DRIFT_DETECTED' if codes else
            'EXPECTED_CHANGE' if expected_line != line else 'PASS')
        payload['classification'] = ('UNEXPLAINED_MODIFICATION' if codes else
            'AUTHORIZED_SUCCESSOR' if expected_line != line else 'NO_CHANGE')
        if not codes and expected.get('date_start') and expected['date_start'] > str(fields.Date.context_today(target)):
            payload['classification'] = 'EXPECTED_DATE_TRANSITION'
        if not codes and expected.get('date_end') and expected['date_end'] < str(fields.Date.context_today(target)):
            payload['classification'] = 'HISTORICAL_ONLY'
        if not set(payload['differences']) & {'currency_id','uom_id','uom_definition'}:
            payload['unit_price_difference'] = str(Decimal(observed['price']) - Decimal(expected['price']))
        return payload


def persist_incidents(env, check):
    # Historical observations remain attached to their original event, but the
    # current operational case belongs to the verified effective expectation.
    # Otherwise one external edit produces a case for every superseded receipt.
    line = check.successor_line_id or check.execution_line_id
    authority(line.execution_id)
    existing = env[INCIDENT].search([('execution_line_id', '=', line.id)])
    by_code = {r.code:r for r in existing}
    for code in check.codes or []:
        incident = by_code.get(code)
        if not incident:
            incident = record(env, INCIDENT, dict(batch_id=line.batch_id.id, execution_id=line.execution_id.id,
                execution_line_id=line.id, target_id=line.target_id, code=code, severity=severity(code), status='OPEN',
                name=code + ' / ' + str(line.target_id), incident_key=digest([check.company_id.id,line.id,line.fingerprint_after,code]),
                first_detected_at=check.checked_at, last_detected_at=check.checked_at,
                first_check_id=check.id, latest_check_id=check.id, assigned_user_id=env.uid))
            incident._event('detect', 'Observed anomaly; no conclusion of unauthorized conduct.', 'monitor.check:' + str(check.id), check)
        else:
            vals = dict(latest_check_id=check.id, last_detected_at=check.checked_at, revalidation_check_id=False)
            changed = incident.latest_check_id.observed_fingerprint != check.observed_fingerprint
            reopened = incident.status == 'RESOLVED_VERIFIED'
            if reopened:
                vals.update(status='REOPENED')
            update(incident, vals)
            if changed or reopened:
                incident._event('reopen' if reopened else 'new_observation',
                    'Material recurring observation retained.', 'monitor.check:' + str(check.id), check)
    # Every observation stays immutable; a clean check does not auto-close a case.
    for incident in existing:
        if incident.code not in (check.codes or []):
            update(incident, dict(latest_check_id=check.id, revalidation_check_id=False))


class ExecutionMonitor(models.Model):
    _inherit = EXEC
    monitor_run_ids = fields.One2many(RUN, 'execution_id')

    def _monitor23(self, after_line=0, line_ids=None, run_type='MANUAL_SINGLE_EXECUTION', limit=MAX_LINES):
        self.ensure_one(); authority(self)
        if type(limit) is not int or not 1 <= limit <= MAX_LINES or type(after_line) is not int or after_line < 0:
            raise UserError('Monitoring requires an explicit bounded line window.')
        if line_ids is not None and (not isinstance(line_ids, list) or len(line_ids) > MAX_LINES or
                any(type(i) is not int for i in line_ids)):
            raise UserError('Invalid exact monitoring line selection.')
        clean = api.Environment(self.env.cr, self.env.uid, {'allowed_company_ids':self.company_id.ids,
            'lang':self.env.user.lang, 'tz':'UTC'})
        execution = clean[EXEC].browse(self.id); authority(execution)
        with clean.cr.savepoint():
            lock(execution)
            domain = [('execution_id','=',execution.id), ('id','>',after_line)]
            if line_ids is not None:
                selected = clean[LINE].browse(line_ids); selected.check_access('read')
                if any(l.execution_id != execution for l in selected):
                    raise AccessError('Monitoring lines must belong to this exact execution.')
                domain.append(('id','in',line_ids))
            lines = clean[LINE].search(domain, order='id', limit=limit+1)
            expected_count = clean[LINE].search_count(domain)
            more = len(lines) > limit; lines = lines[:limit]
            if not lines:
                raise UserError('No authorized execution lines in this exact window.')
            started = fields.Datetime.now(); engine = Observation(execution,lines); observations=[]
            began = time.monotonic()
            for line in lines:
                if observations and time.monotonic() - began > 20:
                    more = True; break
                try:
                    payload = engine.observe(line)
                except (AccessError, MissingError):
                    payload = dict(status='BLOCKED', classification='TARGET_INACCESSIBLE', codes=['MONITORING_ACCESS_FAILURE'])
                except (UserError, ValidationError, KeyError, TypeError, ValueError, AttributeError):
                    payload = dict(status='ERROR', classification='SOURCE_EVIDENCE_INCOMPLETE', codes=['HISTORICAL_EVIDENCE_INTEGRITY'])
                observations.append((line,payload))
            counts = {status:sum(v['status']==status for _,v in observations)
                for status in ('PASS','EXPECTED_CHANGE','DRIFT_DETECTED','BLOCKED','ERROR')}
            run = record(clean,RUN,dict(batch_id=execution.batch_id.id,execution_id=execution.id,
                name='MONITOR / ' + str(execution.id),run_type=run_type,started_at=started,
                completed_at=fields.Datetime.now(),triggered_by=clean.uid,policy_version=VERSION,
                state='PARTIALLY_COMPLETED' if more else 'COMPLETED_WITH_ISSUES' if any(v['codes'] for _,v in observations) else 'COMPLETED',
                expected_count=expected_count,processed_count=len(observations),passed_count=counts['PASS']+counts['EXPECTED_CHANGE'],
                failed_count=counts['DRIFT_DETECTED'],blocked_count=counts['BLOCKED']+counts['ERROR'],has_more=more,
                last_processed_reference=observations[-1][0].id))
            for line,payload in observations:
                check = record(clean,CHECK,dict(batch_id=execution.batch_id.id,execution_id=execution.id,
                    run_id=run.id,execution_line_id=line.id,target_id=line.target_id,checked_at=started,
                    expected_fingerprint=digest(payload.get('expected')),observed_fingerprint=digest([payload.get('observed'),payload.get('selection'),payload['codes']]),
                    evidence_fingerprint=digest(payload),**payload))
                persist_incidents(clean,check)
            return run.with_env(self.env)

    def action_check_applied_price_integrity(self, after_line=0):
        return self._monitor23(after_line=after_line)

    def action_open_price_integrity(self):
        run = self.action_check_applied_price_integrity()
        return dict(type='ir.actions.act_window',res_model=RUN,res_id=run.id,view_mode='form')

    def action_monitor_selected_executions(self):
        if not self or len(self)>5:
            raise UserError('Select one to five exact executions; each observation is limited to 20 lines.')
        for execution in self:
            authority(execution)
        with self.env.cr.savepoint():
            runs=[execution._monitor23(limit=20,run_type='MANUAL_SELECTED_EXECUTIONS').id for execution in self.sorted('id')]
        return dict(type='ir.actions.act_window',res_model=RUN,view_mode='list,form',domain=[('id','in',runs)])
