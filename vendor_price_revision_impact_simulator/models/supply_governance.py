"""Explicit analytical grants and exact-location eligibility; no operational ACLs."""
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError

from .import_intake import ADMIN, PURCHASE_USER, PURCHASE_MANAGER
from .product_resolution import company_lock

PREFIX = 'vendor.price.revision.supply.'
GRANT, LOCATION, AUDIT = [PREFIX + s for s in ('grant', 'location', 'governance.audit')]


class GovernanceAudit(models.Model):
    _name = AUDIT
    _description = 'Retained Supply Governance Changes'
    company_id = fields.Many2one('res.company', required=True, index=True)
    actor_id = fields.Many2one('res.users', required=True)
    source_model = fields.Char(required=True)
    source_id = fields.Integer(required=True)
    before = fields.Json()
    after = fields.Json(required=True)

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Governance audit is system authored.'))

    def write(self, vals):
        raise AccessError(_('Governance audit is immutable.'))

    def unlink(self):
        raise AccessError(_('Governance audit is retained.'))


class Governance(models.AbstractModel):
    _name = PREFIX + 'governance'
    _description = 'Supply Governance Guard'
    company_id = fields.Many2one('res.company', required=True, default=lambda s: s.env.company, index=True)
    active = fields.Boolean(default=True)
    reason = fields.Char(required=True)
    version = fields.Integer(default=1, readonly=True)

    def _admin(self):
        if not self.env.su and (not self.env.user.active or not self.env.user.has_group(ADMIN)):
            raise AccessError(_('Only Configuration Administrators manage analytical supply grants and locations.'))

    def _evidence(self):
        names = ['company_id', 'active', 'reason', 'version']
        names += ['user_id', 'warehouse_ids', 'allow_cost'] if self._name == GRANT else ['warehouse_id', 'location_id', 'classification']
        return self.read(names, load=None)[0]

    def _audit(self, before=None):
        model = self.env[AUDIT]
        for rec in self:
            super(GovernanceAudit, model).create({'company_id': rec.company_id.id,
                'actor_id': self.env.uid, 'source_model': self._name, 'source_id': rec.id,
                'before': before, 'after': rec._evidence()})
        self.env['res.users'].invalidate_model(['vpr_supply_warehouse_ids', 'vpr_supply_cost_warehouse_ids'])
        self.env['ir.access']._clear_caches()

    @api.model_create_multi
    def create(self, vals_list):
        self._admin()
        for vals in vals_list:
            if vals.get('company_id', self.env.company.id) not in self.env.companies.ids or 'version' in vals:
                raise AccessError(_('Selected company required; version is system authored.'))
        company_lock(self.env, self.env.companies)
        records = super().create(vals_list)
        records._audit()
        return records

    def write(self, vals):
        self._admin()
        self.check_access('write')
        if 'company_id' in vals or 'version' in vals or not vals.get('reason', '').strip():
            raise AccessError(_('Company and version are immutable; each change requires a reason.'))
        company_lock(self.env, self.company_id)
        for rec in self:
            before = rec._evidence()
            super(Governance, rec).write(dict(vals, version=rec.version + 1))
            rec._audit(before)
        return True

    def unlink(self):
        raise AccessError(_('Archive governance records with a reason; history is retained.'))

    def copy(self, default=None):
        raise AccessError(_('Create an explicit new governance record.'))


class SupplyGrant(models.Model):
    _name = GRANT
    _inherit = PREFIX + 'governance'
    _description = 'Approved Supply Analytical Service Scope'
    _unique = models.Constraint('UNIQUE(company_id,user_id)', 'One retained analytical grant per company and user.')
    user_id = fields.Many2one('res.users', required=True)
    warehouse_ids = fields.Many2many('stock.warehouse', required=True)
    allow_cost = fields.Boolean(default=False)

    @api.constrains('company_id', 'user_id', 'warehouse_ids', 'active')
    def _validate_scope(self):
        for rec in self:
            user = rec.user_id
            if (not user.active or user.share or rec.company_id not in user.company_ids or
                not (user.has_group(PURCHASE_USER) or user.has_group(
                    'vendor_price_revision_impact_simulator.group_vpr_confidential_reader'))):
                raise ValidationError(_('Grant requires an active internal commercial app role in this company.'))
            if not rec.warehouse_ids or any(w.company_id != rec.company_id or not w.active for w in rec.warehouse_ids):
                raise ValidationError(_('Select active warehouses belonging to this company.'))


class SupplyLocation(models.Model):
    _name = LOCATION
    _inherit = PREFIX + 'governance'
    _description = 'Exact Supply Location Classification'
    _unique = models.Constraint('UNIQUE(company_id,location_id)', 'Classify an exact location only once per company.')
    warehouse_id = fields.Many2one('stock.warehouse', required=True)
    location_id = fields.Many2one('stock.location', required=True)
    classification = fields.Selection([(s, s.replace('_', ' ').title()) for s in
        ('saleable', 'receiving', 'quality', 'staging', 'transit', 'excluded')], required=True)

    @api.constrains('company_id', 'warehouse_id', 'location_id', 'classification')
    def _validate_location(self):
        for rec in self:
            wh, loc = rec.warehouse_id, rec.location_id
            descendant = str(wh.view_location_id.id) in (loc.parent_path or '').split('/')
            if (wh.company_id != rec.company_id or loc.company_id != rec.company_id or
                not (descendant or loc.usage == 'transit') or
                (rec.classification == 'saleable' and loc.usage != 'internal')):
                raise ValidationError(_('Location must belong to this company and warehouse; saleable locations must be internal.'))


class Users(models.Model):
    _inherit = 'res.users'
    vpr_supply_warehouse_ids = fields.Many2many('stock.warehouse', compute='_compute_supply_scope')
    vpr_supply_cost_warehouse_ids = fields.Many2many('stock.warehouse', compute='_compute_supply_scope')

    def _compute_supply_scope(self):
        # Narrow privilege: grant metadata only. This never reads stock or cost.
        grants = self.env[GRANT].sudo().search([('user_id', 'in', self.ids), ('active', '=', True)])
        for user in self:
            own = grants.filtered(lambda g: g.user_id == user and g.company_id in user.company_ids)
            user.vpr_supply_warehouse_ids = own.warehouse_ids if user.active else False
            user.vpr_supply_cost_warehouse_ids = own.filtered('allow_cost').warehouse_ids if user.active else False

    def write(self, vals):
        if {'vpr_supply_warehouse_ids', 'vpr_supply_cost_warehouse_ids'} & vals.keys():
            raise AccessError(_('Supply scope is managed by explicit audited grants.'))
        return super().write(vals)


def authorize(batch, warehouse_ids, costs, prepare=False):
    batch.ensure_one()
    batch.check_access('read')
    if prepare:
        batch._check_review_access()
    if (type(costs) is not bool or not isinstance(warehouse_ids, (list, tuple)) or not warehouse_ids or
        any(type(i) is not int or i <= 0 for i in warehouse_ids)):
        raise ValidationError(_('An explicit warehouse selection and Boolean cost mode are required.'))
    env = batch.env
    if batch.company_id not in env.companies or not env.user.active:
        raise AccessError(_('Selected company access required.'))
    granted = env.user.vpr_supply_cost_warehouse_ids if costs else env.user.vpr_supply_warehouse_ids
    wh = env['stock.warehouse'].browse(sorted(set(warehouse_ids))).exists()
    if (len(wh) != len(set(warehouse_ids)) or any(w not in granted or w.company_id != batch.company_id or not w.active for w in wh)):
        raise AccessError(_('Every selected warehouse requires an active analytical grant for this cost mode.'))
    return wh
