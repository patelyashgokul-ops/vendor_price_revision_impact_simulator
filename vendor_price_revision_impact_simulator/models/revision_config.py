"""Company policy definitions only; no financial or approval execution."""
import json
import math

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

MODULE = 'vendor_price_revision_impact_simulator'
ADMIN = MODULE + '.group_vpr_configuration_admin'
APPROVER_ROLES = ('group_vpr_purchase_manager', 'group_vpr_finance_manager',
                  'group_vpr_sales_manager', 'group_vpr_director')


def choices(*values):
    return [(value, value.replace('_', ' ').capitalize()) for value in values]


class PolicyGuard(models.AbstractModel):
    _name = 'vendor.price.revision.policy.guard'
    _description = 'Policy mutation and audit guard'

    def read(self, fields=None, load='_classic_read'):
        self.check_access('read')
        return super().read(fields=fields, load=load)

    def export_data(self, fields_to_export):
        self.check_access('read')
        return super().export_data(fields_to_export)

    def _authorize(self, operation):
        self.check_access(operation)
        if not self.env.su and (not self.env.user.active or not self.env.user.has_group(ADMIN)):
            raise AccessError(_('Only a Configuration Administrator may change policies.'))

    def _lock_companies(self, companies):
        # Serialize all policy mutations for each company, including publication.
        for company in companies.sorted('id'):
            # A no-op UPDATE also creates a row version: under Odoo's repeatable
            # read isolation concurrent publishers must retry with a fresh snapshot.
            self.env.cr.execute('UPDATE res_company SET id = id WHERE id = %s', [company.id])

    def _parents(self):
        return self if self._name == 'vendor.price.revision.config' else self.config_id

    def _audit_snapshot(self):
        result = {}
        for record in self:
            result[str(record.id)] = record.read([
                name for name, field in self._fields.items()
                if field.store and name not in ('write_date', 'write_uid', '__last_update')
                and field.type != 'one2many'
            ])[0]
        return result

    def _audit(self, before, operation):
        # Narrow elevation appends system-authored audit only, after business access
        # checks. No policy retrieval/mutation is elevated, and context cannot enable it.
        for record in self:
            parent = record._parents()
            self.env['vendor.price.revision.config.audit']._append({
                'config_id': parent.id, 'company_id': parent.company_id.id,
                'actor_id': self.env.uid, 'model_name': self._name,
                'record_reference': record.id, 'operation': operation,
                'before_json': json.dumps(before.get(str(record.id)), default=str, sort_keys=True),
                'after_json': json.dumps(record._audit_snapshot()[str(record.id)], default=str, sort_keys=True),
            })

    @api.model_create_multi
    def create(self, vals_list):
        self._authorize('create')
        for vals in vals_list:
            if self._name == 'vendor.price.revision.config':
                if 'company_id' in vals and not vals['company_id']:
                    raise ValidationError(_('Company ownership is required.'))
                company = self.env['res.company'].browse(vals.get('company_id') or self.default_get(['company_id']).get('company_id'))
                vals['company_id'] = company.id
                vals.setdefault('currency_id', company.currency_id.id)
                if vals.get('state', 'draft') != 'draft' or vals.get('published_by') or vals.get('published_at'):
                    raise AccessError(_('Use configuration publication to validate a draft.'))
                # Ignore forged context defaults as well as explicit metadata.
                vals.update(state='draft', published_by=False, published_at=False)
            else:
                parent = self.env['vendor.price.revision.config'].browse(vals.get('config_id'))
                parent.check_access('write')
                if not parent or parent.state != 'draft':
                    raise UserError(_('Policy definitions require an editable draft configuration.'))
                company = parent.company_id
                if 'company_id' in vals and vals['company_id'] != company.id:
                    raise AccessError(_('Child company must match its configuration.'))
                vals['company_id'] = company.id
            if company not in self.env.companies:
                raise AccessError(_('Company is outside your authorized selected companies.'))
            self._lock_companies(company)
        records = super().create(vals_list)
        records._audit({}, 'create')
        return records

    def write(self, vals):
        self._authorize('write')
        self._lock_companies(self.company_id)
        if any(parent.state != 'draft' for parent in self._parents()):
            raise UserError(_('Published policy versions are immutable. Create a new dated version.'))
        if {'company_id', 'config_id', 'state', 'published_by', 'published_at'}.intersection(vals):
            raise AccessError(_('Policy ownership and publication metadata cannot be reassigned.'))
        before = self._audit_snapshot()
        result = super().write(vals)
        self._audit(before, 'write')
        return result

    def unlink(self):
        self._authorize('unlink')
        raise UserError(_('Policy records and their history are retained. Archive a draft instead.'))

    def copy(self, default=None):
        self.ensure_one()
        self.check_access('read')
        self._authorize('create')
        if self._name != 'vendor.price.revision.config':
            raise UserError(_('Copy the configuration version, not individual policy definitions.'))
        defaults = dict(default or {})
        if defaults.get('company_id', self.company_id.id) != self.company_id.id:
            raise AccessError(_('Copy does not transfer company policy ownership.'))
        defaults.update(state='draft', published_by=False, published_at=False,
                        policy_version=self.policy_version + ' (copy)')
        return super().copy(defaults)


class RevisionConfig(models.Model):
    _name = 'vendor.price.revision.config'
    _inherit = 'vendor.price.revision.policy.guard'
    _description = 'Company Vendor Price Revision Policy Version'
    _order = 'effective_from desc, id desc'
    _check_company_auto = True

    _version_unique = models.Constraint('UNIQUE(company_id, policy_version)', 'Policy version must be unique per company.')
    name = fields.Char(required=True, default='Vendor price revision policies')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    currency_id = fields.Many2one('res.currency', required=True, readonly=True,
        help='Currency captured for this policy version; amounts are normalized to it.')
    policy_version = fields.Char(required=True)
    state = fields.Selection(choices('draft', 'published'), default='draft', required=True, copy=False)
    active = fields.Boolean(default=True)
    effective_from = fields.Date(required=True, default=fields.Date.context_today, index=True)
    effective_to = fields.Date(required=True, help='Inclusive end date; published periods cannot be edited.')
    change_reason = fields.Text(required=True)
    published_by = fields.Many2one('res.users', readonly=True, copy=False)
    published_at = fields.Datetime(readonly=True, copy=False)
    cost_basis = fields.Selection(choices('current_vendor_price', 'proposed_vendor_price', 'negotiated_vendor_price',
        'existing_stock_cost', 'estimated_replacement_cost', 'estimated_landed_cost'), required=True, default='proposed_vendor_price')
    replacement_cost_policy = fields.Selection(choices('explicit_procurement_estimate'), default='explicit_procurement_estimate', required=True)
    stock_cost_policy = fields.Selection(choices('company_accounting_context'), default='company_accounting_context', required=True)
    commitment_policy = fields.Selection(choices('preserve_agreed_prices'), default='preserve_agreed_prices', required=True)
    additional_cost_policy = fields.Selection(choices('exclude', 'evidenced_nonrecoverable_charges'), default='exclude', required=True)
    rounding_policy = fields.Selection(choices('odoo_currency_precision'), default='odoo_currency_precision', required=True)
    currency_rate_policy = fields.Selection(choices('simulation_effective_date', 'company_reference_date', 'authorized_scenario_rate'), default='simulation_effective_date', required=True)
    currency_reference_date = fields.Date()
    fx_override_policy = fields.Selection(choices('disabled', 'finance_governed'), default='disabled', required=True)
    uom_policy = fields.Selection(choices('comparable_purchase_unit', 'verified_reference_unit_conversion'), default='comparable_purchase_unit', required=True)
    quantity_tier_basis = fields.Selection(choices('normalized_purchase_unit'), default='normalized_purchase_unit', required=True)
    tax_basis = fields.Selection(choices('net_revenue_recoverable_tax_excluded'), default='net_revenue_recoverable_tax_excluded', required=True)
    tax_inclusive_policy = fields.Selection(choices('explicit_odoo_tax_context'), default='explicit_odoo_tax_context', required=True)
    unknown_tax_policy = fields.Selection(choices('incomplete'), default='incomplete', required=True)
    missing_mapping_policy = fields.Selection(choices('block_line'), default='block_line', required=True)
    missing_fx_policy = fields.Selection(choices('block_calculation'), default='block_calculation', required=True)
    invalid_uom_policy = fields.Selection(choices('block_comparison'), default='block_comparison', required=True)
    ambiguous_price_policy = fields.Selection(choices('explicit_review'), default='explicit_review', required=True)
    missing_cost_policy = fields.Selection(choices('incomplete'), default='incomplete', required=True)
    missing_approval_role_policy = fields.Selection(choices('block_eligibility'), default='block_eligibility', required=True)
    negative_margin_policy = fields.Selection(choices('finance_review'), default='finance_review', required=True)
    missing_financial_data_policy = fields.Selection(choices('block_decision'), default='block_decision', required=True)
    contract_conflict_policy = fields.Selection(choices('commercial_review'), default='commercial_review', required=True)
    unauthorized_application_policy = fields.Selection(choices('block_and_audit'), default='block_and_audit', required=True)
    missing_approval_policy = fields.Selection(choices('block_application'), default='block_application', required=True)
    invalid_effective_date_policy = fields.Selection(choices('block_application'), default='block_application', required=True)
    allow_future_dated_revisions = fields.Boolean(default=True)
    backdated_proposal_policy = fields.Selection(choices('draft_evidence_review', 'block'), default='draft_evidence_review', required=True)
    backdated_application_policy = fields.Selection(choices('restricted_review', 'block'), default='restricted_review', required=True)
    overlap_conflict_policy = fields.Selection(choices('conflict_review'), default='conflict_review', required=True)
    stale_revision_policy = fields.Selection(choices('revalidate'), default='revalidate', required=True)
    expired_offer_policy = fields.Selection(choices('commercial_review'), default='commercial_review', required=True)
    validity_policy = fields.Selection(choices('dates_and_quantity_tiers'), default='dates_and_quantity_tiers', required=True)
    require_independent_approver = fields.Boolean(default=True)
    allow_same_user_multiple_stages = fields.Boolean(default=False)
    minimum_distinct_approvers = fields.Integer(default=1, required=True)
    delegation_policy = fields.Selection(choices('disabled'), default='disabled', required=True)
    notify_high_exposure = fields.Boolean(default=True)
    notify_negative_margin = fields.Boolean(default=True)
    notify_pending_approval = fields.Boolean(default=True)
    notify_application_failure = fields.Boolean(default=True)
    notification_owner_policy = fields.Selection(choices('authorized_company_users'), default='authorized_company_users', required=True)
    duplicate_alert_policy = fields.Selection(choices('deduplicate_business_event'), default='deduplicate_business_event', required=True)
    margin_ids = fields.One2many('vendor.price.revision.margin.policy', 'config_id', copy=True)
    risk_ids = fields.One2many('vendor.price.revision.risk.rule', 'config_id', copy=True)
    approval_ids = fields.One2many('vendor.price.revision.approval.policy', 'config_id', copy=True)
    audit_ids = fields.One2many('vendor.price.revision.config.audit', 'config_id', readonly=True)
    readiness = fields.Char(compute='_compute_readiness')

    def _check_commands(self, vals):
        for name in ('margin_ids', 'risk_ids', 'approval_ids'):
            model = self.env[self._fields[name].comodel_name]
            for command in vals.get(name, []):
                if command[0] not in (0, 1):
                    raise AccessError(_('Only new definitions and edits of this draft\'s own definitions are allowed.'))
                if command[0] == 1:
                    child = model.browse(command[1])
                    child.check_access('write')
                    if child.config_id not in self:
                        raise AccessError(_('Nested edit must belong to this configuration.'))
        if 'audit_ids' in vals:
            raise AccessError(_('Audit entries are system-authored.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_commands(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._check_commands(vals)
        return super().write(vals)

    @api.constrains('effective_from', 'effective_to', 'minimum_distinct_approvers',
                    'require_independent_approver', 'allow_same_user_multiple_stages',
                    'currency_rate_policy', 'currency_reference_date', 'fx_override_policy', 'currency_id')
    def _validate_settings(self):
        for rec in self:
            if rec.currency_id != rec.company_id.currency_id:
                raise ValidationError(_('Policy currency must match the owning company currency.'))
            if not rec.effective_from or not rec.effective_to or rec.effective_from > rec.effective_to:
                raise ValidationError(_('Policy start must be on or before its inclusive end date.'))
            if rec.minimum_distinct_approvers < 1 or not rec.require_independent_approver or rec.allow_same_user_multiple_stages:
                raise ValidationError(_('Governed approvals require distinct independent approvers; stage reuse is disabled.'))
            if rec.currency_rate_policy == 'company_reference_date' and not rec.currency_reference_date:
                raise ValidationError(_('A company reference date is required for this FX policy.'))
            if rec.currency_rate_policy == 'authorized_scenario_rate' and rec.fx_override_policy != 'finance_governed':
                raise ValidationError(_('Scenario rates require finance-governed FX overrides.'))

    def _setup_errors(self):
        self.ensure_one()
        errors = []
        if not self.margin_ids.filtered(lambda r: r.active and r.scope == 'company'):
            errors.append(_('Company default margin policy is missing.'))
        # Recheck dependent values when the parent minimum or company currency changes.
        for label, rows in [('Risk', self.risk_ids.filtered('active')),
                            ('Finance approval', self.approval_ids.filtered(lambda r: r.active and r.category == 'finance_exposure'))]:
            if not rows:
                errors.append(_('%s complete amount scale is missing.', label))
        try:
            self.margin_ids._validate_margin()
            self.risk_ids._validate_intervals()
            self.approval_ids._validate_roles()
            self.risk_ids.filtered('active')._check_complete_scale()
            for category in set(self.approval_ids.filtered('active').mapped('category')):
                self.approval_ids.filtered(lambda r: r.active and r.category == category)._check_complete_scale()
        except ValidationError as exc:
            errors.append(str(exc))
        return errors

    @api.depends('state', 'minimum_distinct_approvers',
                 'margin_ids.active', 'margin_ids.scope', 'margin_ids.minimum_margin_percent',
                 'margin_ids.target_margin_percent', 'risk_ids.active', 'risk_ids.minimum_amount',
                 'risk_ids.maximum_amount', 'risk_ids.open_ended', 'approval_ids.active',
                 'approval_ids.category', 'approval_ids.minimum_amount', 'approval_ids.maximum_amount',
                 'approval_ids.open_ended', 'approval_ids.required_role_ids', 'approval_ids.required_independent_approvers')
    def _compute_readiness(self):
        for rec in self:
            errors = rec._setup_errors()
            rec.readiness = '; '.join(errors) if errors else _('Configuration structurally valid; financial/application engines deferred.')

    def action_publish(self):
        self._authorize('write')
        self._lock_companies(self.company_id)
        for rec in self:
            if rec.state != 'draft' or not rec.active:
                raise UserError(_('Only active drafts can be published.'))
            if rec.effective_from < fields.Date.context_today(rec) and not self.env.su and not self.env.user.has_group('base.group_system'):
                raise AccessError(_('Backdated publication requires an access-rights administrator with configuration authority.'))
            errors = rec._setup_errors()
            if errors:
                raise ValidationError('\n'.join(errors))
            conflicts = self.with_context(active_test=False).search([
                ('id', '!=', rec.id), ('company_id', '=', rec.company_id.id),
                ('state', '=', 'published'), ('effective_from', '<=', rec.effective_to),
                ('effective_to', '>=', rec.effective_from)])
            if conflicts:
                raise ValidationError(_('Published company policy periods cannot overlap.'))
        before = self._audit_snapshot()
        # Skip only our immutability guard after full authorization/validation.
        super(PolicyGuard, self).write({'state': 'published', 'published_by': self.env.uid,
                                       'published_at': fields.Datetime.now()})
        self._audit(before, 'publish')
        return True

    @api.model
    def get_company_revision_config(self, company, date):
        company = self.env['res.company'].browse(company.id)
        if company not in self.env.companies:
            raise AccessError(_('Unauthorized company policy lookup.'))
        if not date:
            raise ValidationError(_('An explicit policy date is required.'))
        date = fields.Date.to_date(date)
        records = self.search([('company_id', '=', company.id), ('state', '=', 'published'),
                               ('effective_from', '<=', date), ('effective_to', '>=', date)])
        if len(records) != 1:
            raise UserError(_('No unique published company policy exists for this date.'))
        if records.currency_id != company.currency_id:
            raise UserError(_('Company currency changed; policy requires revalidation.'))
        if records._setup_errors():
            raise UserError(_('Policy dependencies changed; configuration requires revalidation.'))
        return records

    def get_applicable_margin_policy(self, product):
        self.ensure_one()
        self.check_access('read')
        product.check_access('read')
        if product.company_id and product.company_id != self.company_id:
            raise ValidationError(_('Product belongs to another company.'))
        rows = self.margin_ids.filtered('active')
        for scope, key, value in [('product', 'product_id', product), ('category', 'category_id', product.categ_id), ('company', None, None)]:
            selected = rows.filtered(lambda r: r.scope == scope and (not key or r[key] == value))
            if len(selected) > 1:
                raise ValidationError(_('Ambiguous margin policy.'))
            if selected:
                return selected
        raise UserError(_('Margin policy is missing.'))

    def get_applicable_risk_rules(self):
        self.ensure_one()
        self.check_access('read')
        rows = self.risk_ids.filtered('active').sorted('minimum_amount')
        rows._check_complete_scale()
        return rows

    def get_applicable_approval_policy(self, category, amount, currency):
        self.ensure_one()
        self.check_access('read')
        if currency != self.currency_id:
            raise ValidationError(_('Amount must already be normalized to the policy company currency; no FX conversion is performed.'))
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
            raise ValidationError(_('A finite nonnegative normalized amount is required.'))
        rows = self.approval_ids.filtered(lambda r: r.active and r.category == category)
        rows._check_complete_scale()
        result = rows.filtered(lambda r: currency.compare_amounts(amount, r.minimum_amount) >= 0 and
                               (r.open_ended or currency.compare_amounts(amount, r.maximum_amount) < 0))
        if len(result) != 1:
            raise UserError(_('No unique approval definition covers this amount.'))
        return result


class PolicyChild(models.AbstractModel):
    _name = 'vendor.price.revision.policy.child'
    _inherit = 'vendor.price.revision.policy.guard'
    _description = 'Version-owned policy definition'
    _check_company_auto = True

    config_id = fields.Many2one('vendor.price.revision.config', required=True, ondelete='restrict', index=True)
    company_id = fields.Many2one(related='config_id.company_id', store=True, readonly=True, index=True)
    active = fields.Boolean(default=True)
    reason = fields.Char(required=True)


class MarginPolicy(models.Model):
    _name = 'vendor.price.revision.margin.policy'
    _inherit = 'vendor.price.revision.policy.child'
    _description = 'Gross Margin Policy (percentage points, not markup)'
    scope = fields.Selection(choices('company', 'category', 'product'), required=True, default='company')
    product_id = fields.Many2one('product.product', check_company=True)
    category_id = fields.Many2one('product.category', check_company=True)
    minimum_margin_percent = fields.Float(required=True, string='Minimum gross margin (%)')
    target_margin_percent = fields.Float(required=True, string='Target gross margin (%)')

    @api.model_create_multi
    def create(self, vals_list):
        self._authorize('create')
        for values in vals_list:
            if values.get('config_id'):
                self.env['vendor.price.revision.config'].browse(values['config_id']).check_access('write')
            if any(key not in values for key in ('minimum_margin_percent', 'target_margin_percent')):
                raise ValidationError(_('Explicit minimum and target margins are required; missing data is not zero.'))
            self._validate_margin_input(values)
        return super().create(vals_list)

    @api.model
    def _validate_margin_input(self, values):
        for key in ('minimum_margin_percent', 'target_margin_percent'):
            if key in values and (isinstance(values[key], bool) or not isinstance(values[key], (int, float)) or not math.isfinite(values[key])):
                raise ValidationError(_('Margin thresholds must be explicit finite numbers; missing data is not zero.'))

    def write(self, vals):
        self._authorize('write')
        self._validate_margin_input(vals)
        return super().write(vals)

    @api.constrains('scope', 'product_id', 'category_id', 'minimum_margin_percent', 'target_margin_percent', 'active', 'config_id')
    def _validate_margin(self):
        for rec in self:
            minimum, target = rec.minimum_margin_percent, rec.target_margin_percent
            if not all(math.isfinite(v) for v in (minimum, target)) or not 0 <= minimum <= target < 100:
                raise ValidationError(_('Gross margin percentages require 0 <= minimum <= target < 100 (20 means 20%).'))
            if (bool(rec.product_id), bool(rec.category_id)) != {'company': (False, False), 'category': (False, True), 'product': (True, False)}[rec.scope]:
                raise ValidationError(_('Scope requires exactly its product/category reference, or neither for company default.'))
            if rec.active and self.search_count([('id', '!=', rec.id), ('config_id', '=', rec.config_id.id),
                ('active', '=', True), ('scope', '=', rec.scope), ('product_id', '=', rec.product_id.id), ('category_id', '=', rec.category_id.id)]):
                raise ValidationError(_('Duplicate active margin scope in this policy version.'))


class AmountScale(models.AbstractModel):
    _name = 'vendor.price.revision.policy.scale'
    _inherit = 'vendor.price.revision.policy.child'
    _description = 'Company-currency [minimum, maximum) policy intervals'
    _order = 'minimum_amount, id'
    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    currency_id = fields.Many2one('res.currency', required=True,
        default=lambda self: self.env.company.currency_id, help='Must equal the owning company currency at definition time.')
    minimum_amount = fields.Monetary(required=True, default=0)
    maximum_amount = fields.Monetary(default=0)
    open_ended = fields.Boolean(default=False)

    @api.model
    def _validate_finite_input(self, vals):
        for key in ('minimum_amount', 'maximum_amount'):
            if key in vals and (isinstance(vals[key], bool) or not isinstance(vals[key], (int, float)) or not math.isfinite(vals[key])):
                raise ValidationError(_('Amount boundaries must be finite numbers.'))

    @api.model_create_multi
    def create(self, vals_list):
        self._authorize('create')
        for vals in vals_list:
            self._validate_finite_input(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._authorize('write')
        self._validate_finite_input(vals)
        return super().write(vals)

    def _scale_key(self):
        return [('config_id', '=', self.config_id.id)]

    @api.constrains('minimum_amount', 'maximum_amount', 'open_ended', 'currency_id', 'config_id', 'active')
    def _validate_intervals(self):
        for rec in self:
            cur = rec.currency_id
            if cur != rec.company_id.currency_id:
                raise ValidationError(_('Thresholds must be defined in the owning company currency.'))
            if not all(math.isfinite(v) for v in (rec.minimum_amount, rec.maximum_amount)) or rec.minimum_amount < 0:
                raise ValidationError(_('Amount boundaries must be finite and nonnegative.'))
            if rec.open_ended and rec.maximum_amount != 0:
                raise ValidationError(_('An open-ended interval has no maximum; leave maximum at zero.'))
            if not rec.open_ended and cur.compare_amounts(rec.maximum_amount, rec.minimum_amount) <= 0:
                raise ValidationError(_('Exclusive maximum must exceed inclusive minimum at currency precision.'))
            if rec.active:
                others = self.search(rec._scale_key() + [('active', '=', True), ('id', '!=', rec.id)])
                for other in others:
                    if (rec.open_ended or cur.compare_amounts(other.minimum_amount, rec.maximum_amount) < 0) and (other.open_ended or cur.compare_amounts(rec.minimum_amount, other.maximum_amount) < 0):
                        raise ValidationError(_('Active amount intervals cannot overlap.'))

    def _check_complete_scale(self):
        rows = self.sorted('minimum_amount')
        if not rows or rows[0].currency_id.compare_amounts(rows[0].minimum_amount, 0) != 0 or not rows[-1].open_ended:
            raise ValidationError(_('A complete scale must start at zero and end with an open-ended tier.'))
        for left, right in zip(rows, rows[1:]):
            if left.open_ended or left.currency_id.compare_amounts(left.maximum_amount, right.minimum_amount) != 0:
                raise ValidationError(_('Amount scale contains a gap or overlap.'))


class RiskRule(models.Model):
    _name = 'vendor.price.revision.risk.rule'
    _inherit = 'vendor.price.revision.policy.scale'
    _description = 'Positive Exposure Risk Threshold Definition'
    risk_level = fields.Selection(choices('low', 'medium', 'high', 'critical'), required=True)


class ApprovalPolicy(models.Model):
    _name = 'vendor.price.revision.approval.policy'
    _inherit = 'vendor.price.revision.policy.scale'
    _description = 'Approval Requirement Definition (categories additive)'
    category = fields.Selection(choices('purchase_commercial', 'finance_exposure', 'margin_exception', 'senior_management', 'customer_repricing'), required=True, default='finance_exposure')
    required_role_ids = fields.Many2many('res.groups', string='All required roles')
    required_independent_approvers = fields.Integer(required=True, default=1)

    def _scale_key(self):
        return super()._scale_key() + [('category', '=', self.category)]

    @api.constrains('required_role_ids', 'required_independent_approvers', 'category')
    def _validate_roles(self):
        supported = self.env['res.groups'].concat(*(self.env.ref(MODULE + '.' + role) for role in APPROVER_ROLES))
        for rec in self:
            if not rec.required_role_ids or rec.required_role_ids - supported:
                raise ValidationError(_('Select existing supported commercial, finance, sales manager or director roles; configuration/audit/operator roles are not approval authorities.'))
            if rec.required_independent_approvers < max(1, rec.config_id.minimum_distinct_approvers, len(rec.required_role_ids)):
                raise ValidationError(_('Distinct approver count must cover each required role and the company minimum.'))
        self._validate_intervals()


class ConfigAudit(models.Model):
    _name = 'vendor.price.revision.config.audit'
    _description = 'Append-only Configuration Change Audit'
    _order = 'id desc'
    config_id = fields.Many2one('vendor.price.revision.config', required=True, ondelete='restrict', index=True)
    company_id = fields.Many2one('res.company', required=True, index=True)
    actor_id = fields.Many2one('res.users', required=True)
    model_name = fields.Char(required=True)
    record_reference = fields.Integer(required=True)
    operation = fields.Char(required=True)
    before_json = fields.Text(required=True)
    after_json = fields.Text(required=True)

    def read(self, fields=None, load='_classic_read'):
        self.check_access('read')
        return super().read(fields=fields, load=load)

    def export_data(self, fields_to_export):
        self.check_access('read')
        return super().export_data(fields_to_export)

    @api.model
    def _append(self, values):
        return super(ConfigAudit, self.sudo()).create(values)

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Audit entries can only be appended by policy operations.'))

    def write(self, vals):
        raise AccessError(_('Configuration audit history is immutable.'))

    def unlink(self):
        raise AccessError(_('Configuration audit history is retained.'))
