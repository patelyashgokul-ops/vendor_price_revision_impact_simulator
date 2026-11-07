"""Exact frozen PR20 subject -> analytical supplierinfo changeset. Never writes prices."""
from collections import defaultdict
import hashlib
import marshal
from decimal import localcontext
from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from .approval_decisions import safe_json
from .commercial_math import number, price
from .scenario_math import negotiated
from .commercial_engine import uom_snapshot
from .structural_validation import digest
from . import application_math as math

VERSION = 'pr21_frozen_vendor_scope_exact_variant_readonly_v1'
LIMIT = 10000
MODULE = 'vendor_price_revision_impact_simulator.'


def planner(env):
    if not env.user.active or env.user.share or not any(env.user.has_group(MODULE + role) for role in (
            'group_vpr_purchase_manager', 'group_vpr_finance_manager')):
        raise AccessError('Active company-authorized Purchase or Finance Manager planning authority required.')


def snapshot(records):
    rows = records.with_context(active_test=False).read(['id'] + list(math.MATERIAL), load=None)
    for row in rows:
        for key in math.NUMERIC:
            row[key] = str(row[key])
        for key in ('date_start', 'date_end'):
            row[key] = str(row[key]) if row[key] else False
    return sorted(rows, key=lambda r: r['id'])


def schema(env):
    model = env['product.supplierinfo']
    missing = set(math.MATERIAL) - model._fields.keys()
    if missing:
        raise ValidationError('Unsupported supplierinfo schema: ' + ', '.join(sorted(missing)))
    result = {name: dict(type=model._fields[name].type, stored=model._fields[name].store,
                         comodel=getattr(model._fields[name], 'comodel_name', None),
                         digits=model._fields[name].get_digits(env) if model._fields[name].type == 'float' else None) for name in math.MATERIAL}
    result['selector_implementations'] = []
    for cls in type(env['product.product']).__mro__:
        for name in ('_select_seller', '_get_filtered_sellers', '_prepare_sellers'):
            method = cls.__dict__.get(name)
            if method and hasattr(method, '__code__'):
                result['selector_implementations'].append(dict(method=name, module=method.__module__,
                    code=hashlib.sha256(marshal.dumps(method.__code__)).hexdigest()))
    return safe_json(result)


class ApplicationEngine:
    def __init__(self, request):
        request.ensure_one(); request.check_access('read')
        self.r = request; self.env = request.env; self.company = request.company_id
        if self.company not in self.env.companies or self.company not in self.env.user.company_ids:
            raise AccessError('Exact approved company must be selected and authorized.')
        self.issues = []; self.lines = []; self.schema = schema(self.env)
        self.calendar_timezone = None
        self.analysis_date = fields.Date.context_today(request.with_context(tz='UTC'))
        self.payload = {}; self.native_samples = set(); self.artifact = request.authorization_id

    def issue(self, code, row_id=None):
        self.issues.append(dict(code=code, row_id=row_id, severity='blocking'))

    def gate(self):
        r = self.r
        if r.request_type not in ('vendor_revision', 'supplier_scenario', 'commercial_package'):
            self.issue('APPROVAL_SCOPE_NOT_VENDOR_PRICING'); return
        if r.state != 'approved' or not self.artifact:
            self.issue('FINAL_APPROVAL_REQUIRED'); return
        a = self.artifact
        if a.request_id != r or a.fingerprint != digest(a.evidence) or a.payload_fingerprint != r.payload_fingerprint:
            self.issue('APPROVAL_INTEGRITY_FAILED'); return
        self.payload = a.evidence.get('payload') or {}
        if digest(self.payload) != a.payload_fingerprint or self.payload.get('company_id') != self.company.id:
            self.payload = {}; self.issue('APPROVED_PAYLOAD_MISMATCH'); return
        scope=self.payload.get('vendor_application_scope') or {}
        if scope and (scope.get('contract') != 'pr21_preapproval_vendor_intent_v1' or scope.get('schema') != self.schema):
            self.issue('APPROVED_TARGET_SCHEMA_UNSUPPORTED_OR_CHANGED')
        if r.request_type == 'commercial_package' and not self.payload.get('vendor_application_scope', {}).get('vendor_component'):
            self.payload = {}; self.issue('EXPLICIT_VENDOR_COMPONENT_REQUIRED'); return
        if r.approval_invalidated_at:
            self.issue('APPROVAL_INVALIDATED')
        elif r.approval_expired_at or (r.approval_valid_until and fields.Datetime.now() >= r.approval_valid_until):
            self.issue('APPROVAL_EXPIRED')
        try:
            r.get_current_approval()  # PR20 owns complete decision/financial validation.
        except AccessError:
            raise
        except (UserError, ValidationError):
            if not self.issues:
                self.issue('APPROVAL_SOURCE_OR_FINANCIAL_STALE')

    def discover(self, template_ids, product_ids):
        vendor = self.env['res.partner'].browse(self.payload['vendor_id']).exists()
        vendor.check_access('read')
        if not vendor or not vendor.active or (vendor.company_id and vendor.company_id != self.company):
            raise ValidationError('Exact active approved vendor/company identity required.')
        expected=(self.payload.get('vendor_application_scope') or {}).get('vendor_identity')
        current=dict(id=vendor.id,company_id=vendor.company_id.id,parent_id=vendor.parent_id.id,commercial_partner_id=vendor.commercial_partner_id.id,active=vendor.active)
        if expected and current != expected:
            self.issue('APPROVED_VENDOR_HIERARCHY_CHANGED')
        # Parent contacts are inspected as conflicts; never silently substituted.
        partners = (vendor | vendor.parent_id | vendor.commercial_partner_id).ids
        targets = self.env['product.supplierinfo'].with_context(active_test=False).search([
            ('partner_id', 'in', partners), ('company_id', 'in', [False, self.company.id]),
            ('product_tmpl_id', 'in', sorted(template_ids)), ('product_id', 'in', [False] + sorted(product_ids))], order='id', limit=LIMIT + 1)
        if len(targets) > LIMIT:
            raise ValidationError('Target discovery exceeds10000 references; narrow the approved scope.')
        return snapshot(targets)

    def terms(self, row, product, intent):
        s = row['snapshot']; p = s['proposal']
        if s.get('status') != 'commercially_valid' or s.get('vendor_id') != self.payload['vendor_id'] or s.get('company_id') != self.company.id:
            raise ValidationError('APPROVED_ROW_SCOPE_MISMATCH')
        if p['product_id'] != product.id or not product.active or not product.purchase_ok or (product.company_id and product.company_id != self.company):
            raise ValidationError('PRODUCT_VARIANT_OR_COMPANY_INVALID')
        if intent.get('product_scope') != dict(id=product.id, template_id=product.product_tmpl_id.id, company_id=product.company_id.id, active=product.active, purchase_ok=product.purchase_ok):
            raise ValidationError('APPROVED_PRODUCT_SCOPE_CHANGED')
        original = self.env['uom.uom'].browse(p['source_uom_id']); target = self.env['uom.uom'].browse(intent.get('target_uom_id') or original.id)
        for unit in original | target:
            unit.check_access('read')
            if not unit.active:
                raise ValidationError('UOM_INACTIVE')
        if original.parent_path.split('/')[0] != target.parent_path.split('/')[0]:
            raise ValidationError('UOM_INCOMPARABLE')
        if uom_snapshot(target) != intent.get('target_uom'):
            raise ValidationError('APPROVED_TARGET_UOM_CHANGED')
        if p.get('price_basis') != 'net_exclusive':
            raise ValidationError('OPERATIONAL_TAX_REPRESENTATION_UNSUPPORTED')
        if str(original.factor) != str(p['uom']['source']['factor']):
            raise ValidationError('APPROVED_UOM_CHANGED')
        amount = number(p['source_price'], True); discount = number(p['discount_percent'], True)
        start, end = p['effective_date'], p.get('end_date') or False
        specs = [v for v in self.payload.get('scenario_assumptions', []) if v.get('product_id') == product.id]
        if self.r.request_type in ('supplier_scenario', 'commercial_package'):
            if len(specs) != 1:
                raise ValidationError('EXACT_GLOBAL_SUPPLIER_ASSUMPTION_REQUIRED')
            spec = specs[0]
            if any(spec.get(k) for k in ('warehouse_id', 'po_line_id', 'landed', 'grouped')) or spec.get('fx_method', 'price_only_common_fx') != 'price_only_common_fx':
                raise ValidationError('CONDITIONAL_OR_FX_SCENARIO_UNSUPPORTED')
            if spec.get('currency_id', p['source_currency_id']) != p['source_currency_id'] and 'currency_id' in spec:
                raise ValidationError('APPROVED_CURRENCY_MISMATCH')
            if spec.get('uom_id', original.id) != original.id:
                raise ValidationError('APPROVED_UOM_MISMATCH')
            if discount:
                raise ValidationError('NET_SCENARIO_DISCOUNT_REPRESENTATION_UNSUPPORTED')
            comparison_factor = p['uom']['comparison']['factor']
            proposal = price(p['net_comparable'], comparison_factor, original.factor)
            baseline = s.get('baseline', {}).get('net_comparable')
            old = price(baseline, comparison_factor, original.factor) if baseline is not None else None
            amount = negotiated(proposal, old, spec.get('mode', 'original'), spec.get('value'), spec.get('discount_base', 'proposal'))
            if spec.get('effective_date'):
                start = spec['effective_date']
        currency = self.env['res.currency'].browse(p['source_currency_id']).exists(); currency.check_access('read')
        if not currency or not currency.active:
            raise ValidationError('APPROVED_CURRENCY_MISSING_OR_INACTIVE')
        if not start or (end and end < start):
            raise ValidationError('INVALID_APPROVED_DATE_RANGE')
        converted, moq = math.converted_terms(amount, p['source_min_qty'], original.factor, target.factor)
        import math as finite_math
        if any(not finite_math.isfinite(float(v)) or number(str(float(v))) != number(v) for v in (converted, moq)):
            raise ValidationError('OPERATIONAL_FLOAT_PRECISION_UNSUPPORTED')
        desired = dict(partner_id=self.payload['vendor_id'], product_id=product.id, product_tmpl_id=product.product_tmpl_id.id,
            company_id=self.company.id, currency_id=currency.id, uom_id=target.id, price=converted,
            min_qty=moq, date_start=start, date_end=end, discount=str(discount))
        # Metadata is either exact before-state or explicitly approved creation terms.
        base = intent.get('before') or intent.get('create_values') or {}
        for name in ('delay', 'sequence', 'product_code', 'product_name'):
            if name not in base:
                raise ValidationError('EXPLICIT_TARGET_METADATA_REQUIRED')
            desired[name] = base[name]
        if not intent.get('allow_discount_change') and intent.get('operation') == 'update' and number(base['discount']) != discount:
            raise ValidationError('DISCOUNT_REPRESENTATION_CONFLICT')
        model=self.env['product.supplierinfo']
        for name in ('price','min_qty','discount'):
            actual=model._fields[name].convert_to_cache(float(desired[name]),model)
            if number(str(actual)) != number(desired[name]):
                raise ValidationError('NATIVE_FIELD_PRECISION_LOSS_UNSUPPORTED')
        return desired

    def build(self):
        with localcontext() as ctx:
            ctx.prec = 38
            return self._build()

    def _build(self):
        self.gate()
        scope=(self.payload or {}).get('vendor_application_scope') or {}
        self.calendar_timezone=scope.get('calendar_timezone')
        import pytz
        if scope and (self.calendar_timezone not in pytz.all_timezones_set or scope.get('company_timezone_setting') != (self.company.partner_id.tz or False)):
            self.issue('APPROVED_COMPANY_CALENDAR_MISSING_OR_CHANGED')
            self.calendar_timezone=None
        self.analysis_date=fields.Date.context_today(self.r.with_context(tz=self.calendar_timezone or 'UTC'))
        gate_codes = [v['code'] for v in self.issues]
        if not self.payload:
            self.targets = []; return self.finish()
        rows = self.payload.get('source_rows') or []
        if not rows or len(rows) > LIMIT:
            self.issue('INVALID_APPROVED_LINE_COUNT'); self.targets = []; return self.finish()
        scope = self.payload.get('vendor_application_scope') or {}
        self.native_samples = {v['row_id'] for v in rows[:10] + rows[-10:]}
        intents = {v['row_id']: v for v in scope.get('lines', [])}
        if intents:
            if set(intents) - {v['row_id'] for v in rows}:
                self.issue('APPROVED_INTENT_ROW_MISSING'); self.targets = []; return self.finish()
            rows = [v for v in rows if v['row_id'] in intents]
        products = self.env['product.product'].browse(sorted({v['snapshot']['proposal']['product_id'] for v in rows})).exists()
        products.check_access('read'); by_product = {p.id: p for p in products}
        self.targets = self.discover(products.product_tmpl_id.ids, products.ids)
        grouped = defaultdict(list)
        for target in self.targets:
            grouped[target['product_tmpl_id']].append(target)
        for row in rows:
            rid = row['row_id']; desired = {}; before = None; boundary = None; codes = []; intent = intents.get(rid, {})
            try:
                product = by_product[row['snapshot']['proposal']['product_id']]
                if not intent:
                    raise ValidationError('EXPLICIT_APPLICATION_INTENT_REQUIRED')
                desired = self.terms(row, product, intent)
                candidates = grouped[product.product_tmpl_id.id]
                boundary = None
                if intent.get('boundary'):
                    from .execution_boundary import boundary_plan
                    candidates,boundary,boundary_codes=boundary_plan(self,row,desired,intent,candidates)
                else:
                    boundary_codes=[]
                op, before, codes = math.classify(desired, candidates, intent, str(self.analysis_date))
                codes += boundary_codes
                if any(v['partner_id'] != desired['partner_id'] and math.overlap(v, desired) for v in candidates):
                    codes.append('VENDOR_HIERARCHY_SCOPE_CONFLICT')
                if codes and op not in ('BLOCKED', 'MANUAL_REVIEW', 'UNSUPPORTED'):
                    op = 'BLOCKED'
                if rid in self.native_samples and not gate_codes and op in ('UPDATE_CANDIDATE', 'NO_CHANGE', 'CREATE_CANDIDATE'):
                    # Actual existing-only selector; never create virtual operational records.
                    selected = product.with_company(self.company)._select_seller(partner_id=self.env['res.partner'].browse(desired['partner_id']),
                        quantity=float(desired['min_qty']), date=fields.Date.to_date(desired['date_start']),
                        uom_id=self.env['uom.uom'].browse(desired['uom_id']))
                    selection = dict(existing_selected_id=selected.get('supplierinfo', self.env['product.supplierinfo']).id or None,
                        meaning='Existing-only native selector; hypothetical after-state/future RFQ winner is not guaranteed; Purchase may use last-PO fallback.')
                else:
                    selection = dict(meaning='Existing native selection not sampled for this row (maximum20 contexts), or authority/line blocked. Hypothetical after-state not asserted.')
            except (ValidationError, ValueError, KeyError) as exc:
                op = 'UNSUPPORTED' if 'UNSUPPORTED' in str(exc) else 'BLOCKED'; codes = [str(exc) or 'APPROVED_DATA_INCOMPLETE']; selection = {}
            if gate_codes:
                op = 'BLOCKED'; codes += gate_codes
            changes = [k for k in math.MATERIAL if desired and (not before or not math.same(before, desired, [k]))]
            if before and any(k not in ('price', 'discount') for k in changes):
                op = 'BLOCKED'; codes.append('UPDATE_FIELD_ALLOWLIST_CONFLICT')
            for code in sorted(set(codes)):
                self.issue(code, rid)
            self.lines.append(dict(row_id=rid, commercial_result_id=row['commercial_result_id'], product_id=desired.get('product_id'),
                target_id=before['id'] if before else None, operation=op, before=before, after=desired,
                changed_fields=changes, unchanged_fields=[k for k in math.MATERIAL if k not in changes],
                conflicts=sorted(set(codes)), selection=selection, intent=intent,
                target_fingerprint=digest(before), source_fingerprint=digest(row)))
            if intent.get('boundary') and boundary:
                if gate_codes:
                    boundary['operation']='BLOCKED';boundary['conflicts']+=gate_codes
                self.lines.append(boundary)
        self.duplicates()
        for rid, codes in math.effective_conflicts(self.lines, self.targets).items():
            line = next(v for v in self.lines if v['row_id'] == rid)
            line['operation'] = 'BLOCKED'; line['conflicts'] = sorted(set(line['conflicts'] + codes))
            for code in codes: self.issue(code, rid)
        return self.finish()

    def duplicates(self):
        identities = defaultdict(list)
        for line in self.lines:
            if line['after']:
                identities[math.identity(line['after'])].append(line)
        for group in identities.values():
            if len(group) > 1:
                for line in group:
                    line['operation'] = 'BLOCKED'; line['conflicts'].append('DUPLICATE_APPROVED_TARGET')
                    self.issue('DUPLICATE_APPROVED_TARGET', line['row_id'])

    def finish(self):
        end_code = None
        if fields.Date.context_today(self.r.with_context(tz=self.calendar_timezone or 'UTC')) != self.analysis_date:
            end_code = 'PLANNING_DATE_CHANGED'
        elif self.artifact and self.r.approval_valid_until and fields.Datetime.now() >= self.r.approval_valid_until:
            end_code = 'APPROVAL_EXPIRED'
        if end_code:
            if not any(v['code'] == end_code for v in self.issues):self.issue(end_code)
            for line in self.lines:
                line['operation'] = 'BLOCKED'
                line['conflicts'] = sorted(set(line['conflicts'] + [end_code]))
        counts = {op: sum(v['operation'] == op for v in self.lines) for op in math.OPERATIONS}
        data = safe_json(dict(contract=VERSION, request_id=self.r.id, request_version=self.r.version,
            authorization_id=self.artifact.id or None, payload_fingerprint=self.artifact.payload_fingerprint or None,
            approval_fingerprint=self.artifact.fingerprint or None, valid_until=self.r.approval_valid_until or None,
            company_id=self.company.id, schema=self.schema, targets=self.targets, lines=self.lines, issues=self.issues,
            counts=counts, calendar_timezone=self.calendar_timezone, as_of=str(self.analysis_date), applied=False,
            readiness='READY_FOR_FUTURE_APPLICATION' if self.lines and not self.issues else 'BLOCKED',
            meaning='Immutable analytical plan only. PR22 must revalidate authority/targets, lock targets, enforce idempotency and verify atomic writes.'))
        return data
