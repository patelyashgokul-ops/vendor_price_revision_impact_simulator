"""Demand service authorization and small, auditable allocation policy."""
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

from .supply_governance import GRANT, Governance, authorize

PREFIX = 'vendor.price.revision.allocation.'
POLICY = PREFIX+'policy'


class Grant(models.Model):
    _inherit = GRANT
    allow_demand = fields.Boolean(default=False, help='Explicit permission for warehouse-scoped customer/order quantity projections. No selling prices are returned.')

    def _evidence(self):
        return dict(super()._evidence(), allow_demand=self.allow_demand)

    def _audit(self, before=None):
        result = super()._audit(before)
        self.env['res.users'].invalidate_model(['vpr_allocation_warehouse_ids'])
        return result


class Users(models.Model):
    _inherit = 'res.users'
    vpr_allocation_warehouse_ids = fields.Many2many('stock.warehouse', compute='_compute_allocation_scope')

    def _compute_allocation_scope(self):
        # Grant metadata only, matching the PR09 narrow metadata trust boundary.
        grants = self.env[GRANT].sudo().search([('user_id','in',self.ids),('active','=',True),('allow_demand','=',True)])
        for user in self:
            user.vpr_allocation_warehouse_ids = grants.filtered(lambda g:g.user_id==user and g.company_id in user.company_ids).warehouse_ids if user.active else False

    def write(self, vals):
        if 'vpr_allocation_warehouse_ids' in vals:
            raise AccessError('Allocation scope requires an explicit audited analytical grant.')
        return super().write(vals)


class AllocationPolicy(models.Model):
    _name = POLICY
    _inherit = 'vendor.price.revision.supply.governance'
    _description = 'Versioned Analytical Demand Allocation Policy'
    priority = fields.Selection([('required_date','Earliest required date, confirmation date, source line ID'),
        ('confirmation','Confirmation date, required date, source line ID')], default='required_date', required=True)
    allow_receiving_buffer = fields.Boolean(string='Use documented Input-to-stock planning delay', default=False)
    receiving_buffer_hours = fields.Float(string='Input-to-saleable planning hours', default=0)
    _unique = models.Constraint('UNIQUE(company_id)', 'Retain one versioned allocation policy per company.')

    def _evidence(self):
        return self.read(['company_id','active','reason','version','priority','allow_receiving_buffer','receiving_buffer_hours'],load=None)[0]

    @api.constrains('allow_receiving_buffer','receiving_buffer_hours')
    def _check_buffer(self):
        from .commercial_math import number
        for rec in self:
            try:hours=number(rec.receiving_buffer_hours, True)
            except ValueError:raise ValidationError('Receiving planning hours must be finite and nonnegative.')
            if hours>744:raise ValidationError('Receiving planning delay must not exceed 744 hours.')

    def _audit(self, before=None):
        # Reuse the retained governance audit; invalidate new metadata scope too.
        result = super()._audit(before)
        self.env['res.users'].invalidate_model(['vpr_allocation_warehouse_ids'])
        return result


def authorized(batch, warehouse_ids, costs, prepare=False):
    warehouses = authorize(batch, warehouse_ids, costs, prepare)
    if any(w not in batch.env.user.vpr_allocation_warehouse_ids for w in warehouses):
        raise AccessError('Every warehouse requires an explicit active customer-demand analytical grant.')
    return warehouses
