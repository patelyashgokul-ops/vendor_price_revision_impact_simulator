"""Exact identity resolution only. No product/supplier-price master writes."""
from collections import Counter, defaultdict
from datetime import datetime

from psycopg2 import DatabaseError
from psycopg2.errors import SerializationFailure, DeadlockDetected

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from .import_intake import BATCH, ROW, clean_defaults, ADMIN, PURCHASE_USER, PURCHASE_MANAGER
from .import_validation import PREFIX, ImmutableReview
from . import structural_validation as lexical

POLICY = 'vendor.price.revision.product.policy'
REGISTRY = 'vendor.price.revision.product.mapping'
AUDIT = 'vendor.price.revision.product.audit'
RESOLUTION = PREFIX + 'product.resolution'
WIZARD = PREFIX + 'product.wizard'
STATUS = [(s, s.replace('_', ' ').title()) for s in (
    'pending_structure', 'pending_match', 'auto_matched', 'manual_matched',
    'needs_review', 'ambiguous', 'unmatched', 'ineligible', 'stale', 'excluded')]
POLICY_FIELDS = ('allow_internal', 'barcode_source', 'allow_single_variant', 'allow_services')
LIMIT = 5000


def key(value):
    """Only surrounding whitespace; preserve case, zeros and punctuation."""
    return str(value or '').strip()


def company_lock(env, companies):
    for company in companies.sorted('id'):
        if company not in env.companies:
            raise AccessError(_('Product mapping company is outside your authorized selected companies.'))
        env.cr.execute('UPDATE res_company SET id = id WHERE id = %s', [company.id])


def product_snapshot(product):
    return {'id': product.id, 'template_id': product.product_tmpl_id.id,
        'code': product.default_code or '', 'barcode': product.barcode or '',
        'active': product.active, 'template_active': product.product_tmpl_id.active,
        'company_id': product.company_id.id, 'purchase_ok': product.purchase_ok,
        'type': product.type, 'uom_id': product.uom_id.id, 'attributes': sorted(product.product_template_attribute_value_ids.ids),
        'attribute_values': [[value.id, value.product_attribute_value_id.id, value.with_context(lang=None).name]
                             for value in product.product_template_attribute_value_ids.sorted('id')]}


def eligible(product, company, policy):
    return bool(product and product.active and product.product_tmpl_id.active and
        (not product.company_id or product.company_id == company) and product.purchase_ok
        and product.type in (('consu', 'service') if policy.allow_services else ('consu',)))


def protect_product_labels(records, values):
    """Many2one display labels must not reveal a product moved to another company.

    Historical IDs/evidence remain retained; current related names are masked
    unless the product is still readable and belongs to this record's company.
    """
    by_record = {rec.id: rec.company_id.id for rec in records}
    groups = defaultdict(set)
    for row in values:
        value = row.get('product_id')
        if value:
            groups[by_record[row['id']]].add(value[0] if isinstance(value, (list, tuple)) else value)
    allowed = {}
    for company_id, ids in groups.items():
        allowed[company_id] = set(records.env['product.product'].with_context(active_test=False).search([
            ('id', 'in', list(ids)), ('company_id', 'in', [False, company_id])]).ids)
    for row in values:
        value = row.get('product_id')
        if value:
            product_id = value[0] if isinstance(value, (list, tuple)) else value
            if product_id not in allowed.get(by_record[row['id']], set()):
                row['product_id'] = False
                if 'product_tmpl_id' in row:
                    row['product_tmpl_id'] = False
    return values


def check_product_export(records, fields_to_export):
    if not any(part in ('product_id', 'product_tmpl_id') for field in fields_to_export for part in field.split('/')):
        return
    records.check_access('read')
    for company in records.company_id:
        subset = records.filtered(lambda record: record.company_id == company)
        ids = subset.product_id.ids
        allowed = records.env['product.product'].with_context(active_test=False).search([
            ('id', 'in', ids), ('company_id', 'in', [False, company.id])])
        if set(ids) - set(allowed.ids):
            raise AccessError(_('Current product labels are no longer accessible in this history company. Export retained snapshot evidence instead.'))


def escape_export(result):
    for row in result.get('datas', []):
        for index, value in enumerate(row):
            if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
                row[index] = "'" + value
    return result


def lock_identity_evidence(env, plans, extra_products=()):
    """Read locks only: no master write, write_date update, or core override."""
    products, suppliers = set(extra_products), set()
    for plan in plans:
        products.update(plan['all_reference_ids'])
        if plan['registry_current_product_id']:
            products.add(plan['registry_current_product_id'])
        suppliers.update(plan['supplier_reference_ids'])
    if products:
        env.cr.execute('SELECT id FROM product_template WHERE id IN '
            '(SELECT product_tmpl_id FROM product_product WHERE id IN %s) ORDER BY id FOR SHARE', [tuple(sorted(products))])
        env.cr.execute('SELECT id FROM product_product WHERE id IN %s ORDER BY id FOR SHARE', [tuple(sorted(products))])
    if suppliers:
        env.cr.execute('SELECT id FROM product_supplierinfo WHERE id IN %s ORDER BY id FOR SHARE', [tuple(sorted(suppliers))])


class ProductAudit(models.Model):
    _name = AUDIT
    _inherit = 'vendor.price.revision.intake.read.guard'
    _description = 'Immutable Product Identity Governance Audit'
    _order = 'id desc'
    company_id = fields.Many2one('res.company', required=True, index=True)
    policy_id = fields.Many2one(POLICY, ondelete='restrict')
    mapping_id = fields.Many2one(REGISTRY, ondelete='restrict')
    actor_id = fields.Many2one('res.users', required=True)
    operation = fields.Char(required=True)
    reason = fields.Char(required=True)
    before_values = fields.Json()
    after_values = fields.Json(required=True)

    @api.model
    def _append(self, values):
        return super(ProductAudit, clean_defaults(self)).create(values)

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Product mapping audit is system-authored.'))

    def write(self, vals):
        raise AccessError(_('Product mapping audit is immutable.'))

    def unlink(self):
        raise AccessError(_('Product mapping audit is retained.'))

    def export_data(self, fields_to_export):
        return escape_export(super().export_data(fields_to_export))


class ProductPolicy(models.Model):
    _name = POLICY
    _inherit = 'vendor.price.revision.intake.read.guard'
    _description = 'Company Exact Product Identity Policy'
    _company_unique = models.Constraint('UNIQUE(company_id)', 'Only one current identity policy per company.')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    allow_internal = fields.Boolean(default=True)
    barcode_source = fields.Selection([('disabled', 'Disabled'), ('vendor_product_code', 'Supplier code explicitly represents barcode'),
        ('product_identifier_raw', 'Other product identifier explicitly represents barcode')], default='disabled', required=True)
    allow_single_variant = fields.Boolean(default=True)
    allow_services = fields.Boolean(default=True)
    version = fields.Integer(default=1, readonly=True)
    change_reason = fields.Char(required=True)
    audit_ids = fields.One2many(AUDIT, 'policy_id', readonly=True)

    def _admin(self):
        if not self.env.su and (not self.env.user.active or not self.env.user.has_group(ADMIN)):
            raise AccessError(_('Only Configuration Administrators manage exact identity policy.'))

    def _snapshot(self):
        self.ensure_one()
        return dict({name: self[name] for name in POLICY_FIELDS}, version=self.version, company_id=self.company_id.id)

    @api.model_create_multi
    def create(self, vals_list):
        self._admin()
        for vals in vals_list:
            if set(vals) - set(POLICY_FIELDS) - {'company_id', 'change_reason'}:
                raise AccessError(_('Identity policy version and audit are system-authored.'))
            vals['company_id'] = vals.get('company_id') or self.default_get(['company_id']).get('company_id')
            company_lock(self.env, self.env['res.company'].browse(vals['company_id']))
            if not isinstance(vals.get('change_reason'), str) or not 1 <= len(vals['change_reason'].strip()) <= 500:
                raise ValidationError(_('Supply a policy change reason of 1–500 characters.'))
            vals['version'] = 1
        records = super(ProductPolicy, clean_defaults(self)).create(vals_list)
        for rec in records:
            self.env[AUDIT]._append({'company_id': rec.company_id.id, 'policy_id': rec.id,
                'actor_id': self.env.uid, 'operation': 'policy_create', 'reason': rec.change_reason,
                'after_values': rec._snapshot()})
        return records

    def write(self, vals):
        self._admin()
        self.check_access('write')
        if set(vals) - set(POLICY_FIELDS) - {'change_reason'} or not isinstance(vals.get('change_reason'), str) or not 1 <= len(vals['change_reason'].strip()) <= 500:
            raise AccessError(_('Policy edits require a reason and cannot change company, version or history.'))
        company_lock(self.env, self.company_id)
        for rec in self:
            before = rec._snapshot()
            super(ProductPolicy, rec).write(dict(vals, version=rec.version + 1))
            self.env[AUDIT]._append({'company_id': rec.company_id.id, 'policy_id': rec.id,
                'actor_id': self.env.uid, 'operation': 'policy_change', 'reason': rec.change_reason,
                'before_values': before, 'after_values': rec._snapshot()})
        # Configuration-only users deliberately cannot read confidential batches.
        # Cache invalidation requires no access to their records or source values.
        self.env[ROW].invalidate_model(['product_match_status', 'resolved_product_id', 'product_candidate_snapshot'])
        self.env[BATCH].invalidate_model(['product_counts'])
        return True

    def unlink(self):
        raise AccessError(_('Identity policies and audit history are retained.'))

    def export_data(self, fields_to_export):
        return escape_export(super().export_data(fields_to_export))


class ProductMapping(models.Model):
    _name = REGISTRY
    _inherit = 'vendor.price.revision.intake.read.guard'
    _description = 'Versioned Verified Vendor Product Identity'
    _order = 'id desc'
    company_id = fields.Many2one('res.company', required=True, index=True)
    vendor_id = fields.Many2one('res.partner', required=True, index=True)
    identifier_type = fields.Selection([('vendor_code', 'Supplier code'), ('internal_identifier', 'Other source identifier'), ('row', 'One source row only')], required=True)
    source_identifier = fields.Char(required=True)
    normalized_code = fields.Char(required=True, readonly=True, index=True)
    product_id = fields.Many2one('product.product', required=True, ondelete='restrict')
    product_tmpl_id = fields.Many2one(related='product_id.product_tmpl_id', readonly=True)
    source_row_id = fields.Many2one(ROW, required=True, ondelete='restrict')
    source_evidence_id = fields.Many2one('vendor.price.revision.evidence', ondelete='restrict')
    source_context = fields.Json(required=True, readonly=True)
    proposed_by = fields.Many2one('res.users', required=True, readonly=True)
    proposed_at = fields.Datetime(required=True, readonly=True)
    verified_by = fields.Many2one('res.users', readonly=True)
    verified_at = fields.Datetime(readonly=True)
    reason = fields.Char(required=True)
    verification_reason = fields.Char(readonly=True)
    retirement_reason = fields.Char(readonly=True)
    state = fields.Selection([(s, s.title()) for s in ('proposed', 'verified', 'rejected', 'superseded')], required=True, readonly=True)
    effective_from = fields.Date(required=True)
    effective_to = fields.Date(required=True)
    product_evidence = fields.Json(readonly=True)
    reference_digest = fields.Char(readonly=True)
    previous_mapping_id = fields.Many2one(REGISTRY, ondelete='restrict', readonly=True)
    source_type = fields.Selection([('manual_proposed', 'Unverified manual proposal'), ('manual_verified', 'Independent manager verified identity')], default='manual_proposed', required=True, readonly=True)
    audit_ids = fields.One2many(AUDIT, 'mapping_id', readonly=True)

    def read(self, fields=None, load='_classic_read'):
        # Include the variant ID internally when only its template was requested.
        requested = fields
        fields = list(fields) + ['product_id'] if fields and 'product_tmpl_id' in fields and 'product_id' not in fields else fields
        result = protect_product_labels(self, super().read(fields=fields, load=load))
        if requested and 'product_id' not in requested:
            for row in result:
                row.pop('product_id', None)
        return result

    def export_data(self, fields_to_export):
        check_product_export(self, fields_to_export)
        return escape_export(super().export_data(fields_to_export))

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Propose mappings through a current structurally-ready source row.'))

    def write(self, vals):
        raise AccessError(_('Mapping evidence and verified versions cannot be overwritten.'))

    def unlink(self):
        raise AccessError(_('Product mapping versions are retained.'))

    def copy(self, default=None):
        raise AccessError(_('Propose a new dated identity version instead of copying history.'))

    def _set(self, values):
        return super().write(values)

    def _audit(self, operation, reason, before):
        for rec in self:
            self.env[AUDIT]._append({'company_id': rec.company_id.id, 'mapping_id': rec.id,
                'actor_id': self.env.uid, 'operation': operation, 'reason': reason,
                'before_values': before, 'after_values': {'state': rec.state, 'product_id': rec.product_id.id,
                    'code': rec.normalized_code, 'type': rec.identifier_type, 'vendor_id': rec.vendor_id.id,
                    'effective_from': str(rec.effective_from), 'effective_to': str(rec.effective_to)}})

    def _manager(self):
        self.check_access('write')
        if not self.env.user.active or not self.env.user.has_group(PURCHASE_MANAGER):
            raise AccessError(_('Only a Purchase Manager may independently verify or retire identity mappings.'))
        company_lock(self.env, self.company_id)

    def action_confirm_mapping(self, reason):
        self.ensure_one()
        self._manager()
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
            raise ValidationError(_('Supply a verification reason of 1–500 characters.'))
        if self.state != 'proposed' or self.proposed_by == self.env.user:
            raise AccessError(_('A different Purchase Manager must verify an unmodified proposed mapping.'))
        row = self.source_row_id
        row.batch_id._check_review_access()
        row.batch_id._lock()
        identity = row._product_identity()
        if identity != self.source_context or row not in row.batch_id.get_structurally_ready_rows():
            raise UserError(_('Source identity/structural context changed; submit a new proposal.'))
        date = fields.Date.to_date(identity['date'])
        if not self.effective_from <= date <= self.effective_to:
            raise ValidationError(_('Mapping identity period must cover this source date.'))
        policy, plans = row.batch_id._product_plans()
        if not policy or not eligible(self.product_id, self.company_id, policy):
            raise ValidationError(_('Choose an accessible active purchasable variant allowed by the company policy.'))
        self.product_id.check_access('read')
        evidence = plans[row.id]
        lock_identity_evidence(self.env, [evidence], self.product_id.ids)
        if evidence['all_reference_ids'] and self.product_id.id not in evidence['all_reference_ids']:
            raise ValidationError(_('The selected variant contradicts existing exact reference evidence. Review master data or the explicit matching policy.'))
        if evidence['truncated']:
            raise ValidationError(_('Candidate scope is too large for safe verification.'))
        conflicts = self.search([('company_id', '=', self.company_id.id), ('vendor_id', '=', self.vendor_id.id),
            ('identifier_type', '=', self.identifier_type), ('normalized_code', '=', self.normalized_code),
            ('state', '=', 'verified'), ('effective_from', '<=', self.effective_to), ('effective_to', '>=', self.effective_from)])
        if conflicts:
            raise ValidationError(_('Verified identity periods overlap. Retire the prior version explicitly or choose a nonoverlapping period.'))
        self._set({'state': 'verified', 'verified_by': self.env.uid, 'verified_at': fields.Datetime.now(),
            'verification_reason': reason.strip(), 'product_evidence': product_snapshot(self.product_id),
            'reference_digest': evidence['reference_digest'], 'source_type': 'manual_verified'})
        self._audit('verify', reason.strip(), {'state': 'proposed', 'product_id': self.product_id.id})
        self._invalidate_views()
        return True

    def action_retire_mapping(self, reason):
        self._manager()
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
            raise ValidationError(_('Retirement/rejection requires a reason of 1–500 characters.'))
        for rec in self:
            if rec.state not in ('proposed', 'verified'):
                raise UserError(_('Only proposed or verified versions can be retired.'))
            old = rec.state
            rec._set({'state': 'rejected' if old == 'proposed' else 'superseded', 'retirement_reason': reason.strip()})
            rec._audit('retire', reason.strip(), {'state': old, 'product_id': rec.product_id.id})
        self._invalidate_views()
        return True

    def _invalidate_views(self):
        batches = self.env[BATCH].search([('company_id', 'in', self.company_id.ids), ('vendor_id', 'in', self.vendor_id.ids)])
        batches.row_ids.invalidate_recordset(['product_match_status', 'resolved_product_id', 'product_candidate_snapshot'])
        batches.invalidate_recordset(['product_counts'])


class ProductResolution(models.Model):
    _name = RESOLUTION
    _inherit = PREFIX + 'review.guard'
    _description = 'Immutable Exact Product Resolution Evidence'
    _order = 'id desc'
    row_id = fields.Many2one(ROW, required=True, ondelete='restrict', index=True)
    structural_result_id = fields.Many2one(PREFIX+'validation.result', required=True, ondelete='restrict')
    input_digest = fields.Char(required=True, index=True)
    identity = fields.Json(required=True)
    status = fields.Selection(STATUS, required=True)
    source = fields.Char(required=True)
    reason = fields.Char(required=True)
    product_id = fields.Many2one('product.product', ondelete='restrict', readonly=True)
    product_snapshot = fields.Json()
    original_identifier = fields.Char()
    effective_identifier = fields.Char()
    mapping_id = fields.Many2one(REGISTRY, ondelete='restrict')
    candidate_snapshot = fields.Json()
    actor_id = fields.Many2one('res.users', required=True)
    resolved_at = fields.Datetime(required=True)

    def read(self, fields=None, load='_classic_read'):
        return protect_product_labels(self, super().read(fields=fields, load=load))

    def export_data(self, fields_to_export):
        check_product_export(self, fields_to_export)
        return super().export_data(fields_to_export)


class BatchProductResolution(models.Model):
    _inherit = BATCH
    product_resolution_ids = fields.One2many(RESOLUTION, 'batch_id', readonly=True)
    product_matching_state = fields.Selection([(s, s.title()) for s in ('not_started', 'complete', 'failed')], default='not_started', readonly=True)
    product_matching_error = fields.Char(readonly=True)
    product_counts = fields.Json(compute='_compute_product_counts')

    def _product_policy(self):
        self.ensure_one()
        if self.company_id not in self.env.companies:
            raise AccessError(_('Unauthorized identity policy context.'))
        return self.env[POLICY].search([('company_id', '=', self.company_id.id)])

    def _product_plans(self):
        """Bulk, normal-user exact searches. Never read price/rate/stock fields."""
        self.ensure_one()
        self.check_access('read')
        policy = self._product_policy()
        rows = self.row_ids
        identities = {row.id: row._product_identity() for row in rows}
        codes = {v['code'] for v in identities.values() if v['code']}
        internal = {v['identifier'] or v['code'] for v in identities.values() if v['identifier'] or v['code']}
        registry = self.env[REGISTRY].search([('company_id', '=', self.company_id.id),
            ('vendor_id', '=', self.vendor_id.id), ('state', '=', 'verified'),
            ('normalized_code', 'in', list(codes | {v['identifier'] for v in identities.values()} | {f'row:{r.id}' for r in rows}))], order='id', limit=LIMIT+1)
        suppliers = self.env['product.supplierinfo'].search([('partner_id', '=', self.vendor_id.id),
            ('company_id', 'in', [False, self.company_id.id]), ('product_code', 'in', list(codes))], order='id', limit=LIMIT+1)
        scope = [('company_id', 'in', [False, self.company_id.id])]
        barcode_codes = {key(v.get('code' if policy.barcode_source == 'vendor_product_code' else 'identifier')) for v in identities.values()} if policy and policy.barcode_source != 'disabled' else set()
        # Also load verified selections, which may have no matching internal code.
        domain = scope + ['|', '|', '|', ('default_code', 'in', list(internal) if policy and policy.allow_internal else []),
            ('barcode', 'in', list(barcode_codes - {''})), ('product_tmpl_id', 'in', suppliers.product_tmpl_id.ids),
            ('id', 'in', registry.product_id.ids)]
        products = self.env['product.product'].with_context(active_test=False).search(domain, order='id', limit=LIMIT+1)
        truncated = any(len(records) > LIMIT for records in (registry, suppliers, products))
        by_id = {p.id: p for p in products[:LIMIT]}
        by_code, by_barcode, by_template, vendor_refs, registry_keys = (defaultdict(list) for _ in range(5))
        for product in products[:LIMIT]:
            by_code[product.default_code or ''].append(product)
            by_barcode[product.barcode or ''].append(product)
            by_template[product.product_tmpl_id.id].append(product)
        for supplier in suppliers[:LIMIT]:
            candidates = [by_id[supplier.product_id.id]] if supplier.product_id.id in by_id else [] if supplier.product_id else by_template[supplier.product_tmpl_id.id]
            vendor_refs[supplier.product_code].append((supplier.id, bool(supplier.product_id), candidates))
        for rec in registry[:LIMIT]:
            registry_keys[(rec.identifier_type, rec.normalized_code)].append(rec)
        plans = {}
        for row in rows:
            identity = identities[row.id]
            ref_entries = vendor_refs[identity['code']]
            vendor_candidates = {p.id: p for _, _, candidates in ref_entries for p in candidates}
            levels = [('vendor_reference', list(vendor_candidates.values()))]
            if policy and policy.allow_internal:
                levels.append(('internal_sku', by_code[identity['identifier'] or identity['code']]))
            if policy and policy.barcode_source != 'disabled':
                levels.append(('barcode', by_barcode[identity['code'] if policy.barcode_source == 'vendor_product_code' else identity['identifier']]))
            all_refs = {p.id: p for _, candidates in levels for p in candidates}
            ref_snapshot = {'levels': [(source, sorted(p.id for p in candidates)) for source, candidates in levels],
                'products': {str(pid): product_snapshot(p) for pid, p in all_refs.items()},
                'supplier_refs': [(sid, variant, sorted(p.id for p in candidates)) for sid, variant, candidates in ref_entries],
                'policy': policy._snapshot() if policy else None, 'truncated': truncated}
            ref_digest = lexical.digest(ref_snapshot)
            mappings = registry_keys[('vendor_code', identity['code'])] + registry_keys[('internal_identifier', identity['identifier'])] + registry_keys[('row', f'row:{row.id}')]
            date = fields.Date.to_date(identity['date']) if identity['date'] else None
            mappings = [m for m in mappings if date and m.effective_from <= date <= m.effective_to]
            status, source, reason, selected, mapping = 'unmatched', 'exact_lookup', 'No authorized exact product identity found. Review the identifier or propose an existing variant.', None, None
            if not policy:
                status, reason = 'needs_review', 'Company exact identity policy must be configured explicitly.'
            elif not self.vendor_id.active:
                status, reason = 'needs_review', 'Vendor is inactive; identity review is required.'
            elif truncated:
                status, reason = 'needs_review', 'Exact candidate scope exceeds the supported bound; no arbitrary selection is allowed.'
            elif len(mappings) > 1:
                status, reason = 'ambiguous', 'Multiple verified identity keys apply; review conflicting mappings.'
            elif mappings:
                mapping = mappings[0]
                chosen = by_id.get(mapping.product_id.id)
                if (not chosen or not eligible(chosen, self.company_id, policy)
                        or mapping.product_evidence != product_snapshot(chosen) or mapping.reference_digest != ref_digest
                        or (mapping.identifier_type == 'row' and mapping.source_context != identity)):
                    status, source, reason = 'stale', 'verified_registry', 'Verified identity evidence changed or is no longer eligible. Independent re-verification is required.'
                else:
                    status, source, reason, selected = 'manual_matched', 'verified_registry', 'Independent manager-verified exact variant and unchanged reference evidence.', chosen
            else:
                good = {pid: p for pid, p in all_refs.items() if eligible(p, self.company_id, policy)}
                # An ineligible higher-level reference is not silently discarded.
                if all_refs and not good:
                    status, reason = 'ineligible', 'Only archived or otherwise ineligible authorized products match.'
                elif len(all_refs) > 1:
                    status, reason = 'ambiguous', 'Conflicting exact products or template variants require explicit review.'
                elif len(good) == 1:
                    chosen = next(iter(good.values()))
                    used = [name for name, candidates in levels if chosen in candidates]
                    template_only = bool(ref_entries) and not any(variant for _, variant, _ in ref_entries)
                    if template_only and not policy.allow_single_variant:
                        status, reason = 'needs_review', 'Template-only reference requires an explicitly allowed unique variant.'
                    else:
                        status, source, reason, selected = 'auto_matched', used[0], 'Unique eligible exact variant; no conflicting authorized reference evidence.', chosen
            registry_snapshot = [(m.id, m.state, m.product_id.id, str(m.effective_from), str(m.effective_to), m.product_evidence, m.reference_digest) for m in mappings]
            fingerprint = lexical.digest({'identity': identity, 'references': ref_snapshot,
                'registry': registry_snapshot, 'vendor_active': self.vendor_id.active,
                'registry_current_products': {str(m.product_id.id): product_snapshot(by_id[m.product_id.id])
                    if m.product_id.id in by_id else None for m in mappings},
                'decision': [status, source, selected.id if selected else False]})
            candidates = list({**all_refs, **({mapping.product_id.id: by_id[mapping.product_id.id]} if mapping and mapping.product_id.id in by_id else {})}.values())[:40]
            plans[row.id] = {'identity': identity, 'fingerprint': fingerprint, 'status': status, 'source': source,
                'reason': reason, 'product': selected, 'mapping': mapping,
                'reference_digest': ref_digest, 'all_reference_ids': set(all_refs), 'truncated': truncated,
                'supplier_reference_ids': [sid for sid, _, _ in ref_entries],
                'registry_current_product_id': mapping.product_id.id if mapping and mapping.product_id.id in by_id else False,
                'candidates': [dict(product_snapshot(p), name=p.display_name) for p in candidates]}
        return policy, plans

    def action_match_products(self):
        self.ensure_one()
        self._check_review_access()
        company_lock(self.env, self.company_id)
        self._lock()
        ready = self.get_structurally_ready_rows()
        try:
            with self.env.cr.savepoint():
                _, plans = self._product_plans()
                lock_identity_evidence(self.env, [plans[row.id] for row in ready])
                for row in ready:
                    plan = plans[row.id]
                    if row.product_resolution_id and row.product_resolution_id.input_digest == plan['fingerprint']:
                        continue
                    selected = plan['product']
                    resolution = self.env[RESOLUTION]._record({'batch_id': self.id, 'row_id': row.id,
                        'structural_result_id': row.current_result_id.id, 'input_digest': plan['fingerprint'],
                        'identity': plan['identity'], 'status': plan['status'], 'source': plan['source'],
                        'reason': plan['reason'], 'product_id': selected.id if selected else False,
                        'product_snapshot': product_snapshot(selected) if selected else {},
                        'original_identifier': row._original_product_code(),
                        'effective_identifier': plan['identity']['code'] or plan['identity']['identifier'],
                        'mapping_id': plan['mapping'].id if plan['mapping'] else False,
                        'candidate_snapshot': plan['candidates'], 'actor_id': self.env.uid,
                        'resolved_at': fields.Datetime.now()})
                    row._review_set({'product_resolution_id': resolution.id})
                self._set({'product_matching_state': 'complete', 'product_matching_error': False})
        except (SerializationFailure, DeadlockDetected):
            raise
        except (DatabaseError, ValueError, TypeError, RuntimeError):
            self._set({'product_matching_state': 'failed', 'product_matching_error': 'Exact matching failed atomically; no partial new result set was retained. Retry is available.'})
            return False
        self.row_ids.invalidate_recordset(['product_match_status', 'resolved_product_id'])
        self.invalidate_recordset(['product_counts'])
        return True

    def export_data(self, fields_to_export):
        check_product_export(self.product_resolution_ids, fields_to_export)
        return super().export_data(fields_to_export)

    @api.depends('row_ids.product_resolution_id', 'current_run_id', 'review_version')
    def _compute_product_counts(self):
        for batch in self:
            _, plans = batch._product_plans()
            counts = Counter()
            products = set()
            for row in batch.row_ids:
                status, product = row._current_product_outcome(plans[row.id])
                counts[status] += 1
                if product:
                    products.add(product.id)
            counts['eligible_rows'] = sum(counts[s] for s in ('pending_match', 'auto_matched', 'manual_matched', 'needs_review', 'ambiguous', 'unmatched', 'ineligible', 'stale'))
            counts['distinct_matched_products'] = len(products)
            counts['total_rows'] = len(batch.row_ids)
            batch.product_counts = dict(counts)

    def get_product_resolved_rows(self):
        self.ensure_one()
        ready = self.get_structurally_ready_rows()
        self.row_ids.invalidate_recordset(['product_match_status', 'resolved_product_id'])
        self.invalidate_recordset(['product_counts'])
        _, plans = self._product_plans()
        lock_identity_evidence(self.env, [plans[row.id] for row in ready])
        ids = []
        for row in ready:
            status, product = row._current_product_outcome(plans[row.id])
            if status in ('auto_matched', 'manual_matched') and product:
                ids.append(row.id)
        return ready.filtered(lambda row: row.id in ids)

    def action_review_products(self):
        self.ensure_one()
        self.check_access('read')
        return {'type': 'ir.actions.act_window', 'name': _('Product Identity Review'), 'res_model': ROW,
            'view_mode': 'list,form', 'views': [(self.env.ref('vendor_price_revision_impact_simulator.view_product_match_rows').id, 'list'),
                (self.env.ref('vendor_price_revision_impact_simulator.view_source_row_review_form').id, 'form')],
            'domain': [('batch_id', '=', self.id)], 'context': {'product_review_batch_id': self.id},
            'search_view_id': self.env.ref('vendor_price_revision_impact_simulator.view_product_match_search').id}


class RowProductResolution(models.Model):
    _inherit = ROW
    product_resolution_id = fields.Many2one(RESOLUTION, readonly=True, ondelete='restrict', copy=False)
    product_match_status = fields.Selection(STATUS, compute='_compute_product_outcome', search='_search_product_status')
    resolved_product_id = fields.Many2one('product.product', compute='_compute_product_outcome')
    product_candidate_snapshot = fields.Json(compute='_compute_candidates')
    product_proposal_ids = fields.One2many(REGISTRY, 'source_row_id', readonly=True)

    def export_data(self, fields_to_export):
        check_product_export(self.product_resolution_id, fields_to_export)
        check_product_export(self.product_proposal_ids, fields_to_export)
        return super().export_data(fields_to_export)

    @api.model
    def _search_product_status(self, operator, value):
        if operator not in ('=', '!=', 'in', 'not in'):
            return NotImplemented
        values = set(value if operator in ('in', 'not in') else [value])
        scope = [('batch_id', '=', self.env.context['product_review_batch_id'])] if self.env.context.get('product_review_batch_id') else []
        rows = self.search(scope, limit=20001)
        if len(rows) > 20000:
            raise UserError(_('Open one batch before filtering product matching status.'))
        found = []
        for batch in rows.batch_id:
            _, plans = batch._product_plans()
            for row in rows.filtered(lambda r: r.batch_id == batch):
                if row._current_product_outcome(plans[row.id])[0] in values:
                    found.append(row.id)
        return [('id', 'not in' if operator in ('!=', 'not in') else 'in', found)]

    def _original_product_code(self):
        self.ensure_one()
        mapping = self.batch_id.mapping_ids.filtered(lambda m: m.active and m.target == 'vendor_product_code')
        value = self.raw_cells[mapping.column_number-1].get('value') if mapping and mapping.column_number <= len(self.raw_cells) else ''
        return str(value or '')

    def _product_identity(self):
        self.ensure_one()
        values, provenance = self._effective_values(self.batch_id.mapping_ids.filtered('active'), self.correction_ids)
        raw_date = values.get('effective_date_raw', '')
        try:
            fmt = '%Y-%m-%d' if provenance.get('effective_date_raw', {}).get('type') == 'date' else lexical.DATE_FORMATS[self.batch_id.date_style]
            date = datetime.strptime(raw_date[:10] if provenance.get('effective_date_raw', {}).get('type') == 'date' else raw_date, fmt).date().isoformat()
        except (ValueError, KeyError):
            date = ''
        identity = {'company_id': self.company_id.id, 'vendor_id': self.batch_id.vendor_id.id,
            'code': key(values.get('vendor_product_code')), 'identifier': key(values.get('product_identifier_raw')), 'date': date}
        if not identity['code'] and not identity['identifier']:
            identity['description'] = key(values.get('vendor_product_name'))
        return identity

    def _current_product_outcome(self, plan):
        self.ensure_one()
        previous = self.product_resolution_id
        if self.excluded:
            return 'excluded', None
        if previous and previous.identity != plan['identity']:
            return 'stale', None
        if not self.batch_id.current_run_id or self.validation_status != 'structurally_ready':
            return 'pending_structure', None
        if not previous:
            return 'pending_match', None
        if previous.input_digest != plan['fingerprint']:
            return 'stale', None
        return previous.status, plan['product'] if previous.status in ('auto_matched', 'manual_matched') else None

    @api.depends('product_resolution_id', 'batch_id.current_run_id', 'batch_id.review_version', 'excluded',
        'product_resolution_id.product_id.active', 'product_resolution_id.product_id.default_code',
        'product_resolution_id.product_id.barcode', 'product_resolution_id.product_id.company_id',
        'product_resolution_id.product_id.purchase_ok', 'product_resolution_id.product_id.type',
        'product_resolution_id.product_id.product_tmpl_id.active', 'product_resolution_id.product_id.product_template_attribute_value_ids')
    def _compute_product_outcome(self):
        for batch in self.batch_id:
            _, plans = batch._product_plans()
            for row in self.filtered(lambda r: r.batch_id == batch):
                status, selected = row._current_product_outcome(plans[row.id])
                row.product_match_status = status
                row.resolved_product_id = selected.id if selected else False

    def _compute_candidates(self):
        for batch in self.batch_id:
            _, plans = batch._product_plans()
            for row in self.filtered(lambda r: r.batch_id == batch):
                row.product_candidate_snapshot = plans[row.id]['candidates'] if batch.current_run_id and row.validation_status == 'structurally_ready' else []

    def action_propose_product(self, product_id, reason, effective_from, effective_to, reusable=True):
        self.ensure_one()
        self.check_access('read')
        batch = self.batch_id
        batch._check_review_access()
        company_lock(self.env, batch.company_id)
        batch._lock()
        if self not in batch.get_structurally_ready_rows():
            raise UserError(_('Only current structurally-ready rows may propose a product identity.'))
        product = self.env['product.product'].browse(product_id)
        product.check_access('read')
        policy = batch._product_policy()
        if not policy or not eligible(product, batch.company_id, policy):
            raise ValidationError(_('Select an accessible eligible exact product variant under a configured company identity policy.'))
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
            raise ValidationError(_('A mapping evidence reason of 1–500 characters is required.'))
        begin, end = fields.Date.to_date(effective_from), fields.Date.to_date(effective_to)
        if not begin or not end or begin > end:
            raise ValidationError(_('A nonreversed finite identity-mapping period is required.'))
        identity = self._product_identity()
        kind = 'vendor_code' if identity['code'] else 'internal_identifier' if identity['identifier'] else 'row'
        if not reusable:
            kind = 'row'
        identifier = identity['code'] if kind == 'vendor_code' else identity['identifier'] if kind == 'internal_identifier' else f'row:{self.id}'
        previous = self.env[REGISTRY].search([('company_id', '=', batch.company_id.id), ('vendor_id', '=', batch.vendor_id.id),
            ('identifier_type', '=', kind), ('normalized_code', '=', identifier)], order='id desc', limit=1)
        mapping = super(ProductMapping, clean_defaults(self.env[REGISTRY])).create({
            'company_id': batch.company_id.id, 'vendor_id': batch.vendor_id.id, 'identifier_type': kind,
            'source_identifier': identifier, 'normalized_code': key(identifier), 'product_id': product.id,
            'source_row_id': self.id, 'source_evidence_id': batch.evidence_id.id, 'source_context': identity,
            'proposed_by': self.env.uid, 'proposed_at': fields.Datetime.now(), 'reason': reason.strip(),
            'state': 'proposed', 'effective_from': begin, 'effective_to': end,
            'previous_mapping_id': previous.id, 'source_type': 'manual_proposed'})
        mapping._audit('propose', reason.strip(), {'previous_product_id': previous.product_id.id if previous else False})
        return mapping

    def action_open_product_proposal(self):
        self.ensure_one()
        self.batch_id._check_review_access()
        if self not in self.batch_id.get_structurally_ready_rows():
            raise UserError(_('Validate row structure before proposing product identity.'))
        return {'type': 'ir.actions.act_window', 'name': _('Propose Exact Product Variant'), 'res_model': WIZARD,
            'view_mode': 'form', 'target': 'new', 'context': {'default_row_id': self.id, 'default_company_id': self.company_id.id}}


class ProductProposalWizard(models.TransientModel):
    _name = WIZARD
    _inherit = 'vendor.price.revision.intake.read.guard'
    _description = 'Propose or Verify Product Identity (not price approval)'
    row_id = fields.Many2one(ROW)
    mapping_id = fields.Many2one(REGISTRY)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    product_id = fields.Many2one('product.product', domain="[('company_id', 'in', [False, company_id]), ('active', '=', True), ('purchase_ok', '=', True)]")
    reason = fields.Char(required=True)
    effective_from = fields.Date(default=fields.Date.context_today)
    effective_to = fields.Date(default=lambda self: fields.Date.to_date('2099-12-31'))
    reusable = fields.Boolean(default=True)
    operation = fields.Selection([('propose', 'Propose identity'), ('verify', 'Independently verify'), ('retire', 'Reject / Supersede')], default='propose', required=True)

    @api.model
    def _check_links(self, values):
        company = self.env['res.company'].browse(values.get('company_id'))
        if not company or company not in self.env.companies:
            raise AccessError(_('Wizard company must be authorized and selected.'))
        for field, model in (('row_id', ROW), ('mapping_id', REGISTRY), ('product_id', 'product.product')):
            if values.get(field):
                linked = self.env[model].browse(values[field])
                linked.check_access('read')
                if linked.company_id and linked.company_id != company:
                    raise AccessError(_('Wizard references must belong to its company or an authorized shared product.'))

    @api.model_create_multi
    def create(self, vals_list):
        defaults = self.default_get(['company_id', 'row_id', 'mapping_id', 'product_id'])
        prepared = [dict(defaults, **vals) for vals in vals_list]
        for vals in prepared:
            self._check_links(vals)
        return super().create(prepared)

    def write(self, vals):
        self.check_access('write')
        for wizard in self:
            links = {field: wizard[field].id for field in ('company_id', 'row_id', 'mapping_id', 'product_id')}
            wizard._check_links(dict(links, **{field: value for field, value in vals.items() if field in links}))
        return super().write(vals)

    def action_submit(self):
        self.ensure_one()
        self.check_access('write')
        if self.operation == 'propose':
            if self.company_id != self.row_id.company_id:
                raise AccessError(_('Wizard company must match source company.'))
            self.row_id.action_propose_product(self.product_id.id, self.reason, self.effective_from, self.effective_to, self.reusable)
        elif self.operation == 'verify':
            if self.mapping_id.company_id != self.company_id:
                raise AccessError(_('Wizard and mapping companies must match.'))
            self.mapping_id.action_confirm_mapping(self.reason)
        else:
            if self.mapping_id.company_id != self.company_id:
                raise AccessError(_('Wizard and mapping companies must match.'))
            self.mapping_id.action_retire_mapping(self.reason)
        return {'type': 'ir.actions.act_window_close'}


class RegistryWizardActions(models.Model):
    _inherit = REGISTRY

    def action_open_mapping_review(self):
        self.ensure_one()
        self._manager()
        return {'type': 'ir.actions.act_window', 'name': _('Verify / Retire Product Mapping'),
            'res_model': WIZARD, 'view_mode': 'form', 'target': 'new',
            'context': {'default_mapping_id': self.id, 'default_company_id': self.company_id.id, 'default_operation': 'verify'}}
