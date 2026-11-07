"""Shared, versioned natural-scope barriers for APP06 and native price writers."""
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


def scopes(env, pairs):
    """No prices or privileges: a bounded internal concurrency metadata barrier.

    Updating the epoch, rather than just taking an advisory lock, makes an old
    Odoo Repeatable Read snapshot serialize/retry after a competing commit.
    Parent/contact scopes intersect; companies/variants share a template barrier
    so shared/template-wide native edits cannot evade a variant plan's lock.
    """
    pairs = set(pairs)
    if len(pairs) > 10000:
        raise ValidationError('PRICE_SCOPE_LIMIT: narrow the operation.')
    vendors = env['res.partner'].browse(sorted({v for v, _ in pairs})).exists()
    vendors.check_access('read')
    ids = sorted(set(vendors.ids + vendors.parent_id.ids + vendors.commercial_partner_id.ids))
    if ids:
        env.cr.execute('SELECT id FROM res_partner WHERE id IN %s ORDER BY id FOR SHARE', [tuple(ids)])
        vendors.invalidate_recordset()
    keys = set()
    for vendor_id, template_id in pairs:
        vendor = vendors.browse(vendor_id)
        if not vendor.exists() or not template_id:
            raise ValidationError('PRICE_SCOPE_IDENTITY_REQUIRED')
        template = env['product.template'].browse(template_id).exists()
        template.check_access('read')
        if not template:
            raise ValidationError('PRICE_SCOPE_TEMPLATE_REQUIRED')
        keys.update((p, template_id) for p in (vendor | vendor.parent_id | vendor.commercial_partner_id).ids)
    for vendor_id, template_id in sorted(keys):
        env.cr.execute('''INSERT INTO vendor_price_revision_application_scope (partner_id, product_tmpl_id, epoch)
            VALUES (%s,%s,1) ON CONFLICT (partner_id,product_tmpl_id)
            DO UPDATE SET epoch=vendor_price_revision_application_scope.epoch+1''', [vendor_id, template_id])


class PriceScope(models.Model):
    _name = 'vendor.price.revision.application.scope'
    _description = 'Internal Native Vendor Price Scope Epoch (No Prices)'
    _log_access = False
    _key = models.Constraint('UNIQUE(partner_id,product_tmpl_id)', 'One native scope epoch.')
    partner_id = fields.Many2one('res.partner', required=True, ondelete='cascade')
    product_tmpl_id = fields.Many2one('product.template', required=True, ondelete='cascade')
    epoch = fields.Integer(required=True)

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError('Internal transaction metadata is not user-authored.')

    def write(self, vals):
        raise AccessError('Internal transaction metadata is not editable.')

    def unlink(self):
        raise AccessError('Internal transaction metadata is retained.')


class NativePriceBarrier(models.Model):
    _inherit = 'product.supplierinfo'

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access('create')
        # Native permissions stay unchanged. All normal native writers take the
        # same metadata barrier; this hook never grants price-writing authority.
        prepared = [dict(v) for v in vals_list]
        defaults = self.default_get(['partner_id','product_id','product_tmpl_id'])
        for vals in prepared:
            for key, value in defaults.items():
                vals.setdefault(key, value)
            self._sanitize_vals(vals)
        scopes(self.env, {(v.get('partner_id'), v.get('product_tmpl_id')) for v in prepared})
        return super().create(prepared)

    def write(self, vals):
        self.check_access('write')
        pairs = {(r.partner_id.id, r.product_tmpl_id.id) for r in self}
        new_template = vals.get('product_tmpl_id')
        if vals.get('product_id'):
            new_template = self.env['product.product'].browse(vals['product_id']).product_tmpl_id.id
        pairs.update((vals.get('partner_id', r.partner_id.id), new_template or r.product_tmpl_id.id) for r in self)
        scopes(self.env, pairs)
        return super().write(vals)

    def unlink(self):
        self.check_access('unlink')
        scopes(self.env, {(r.partner_id.id, r.product_tmpl_id.id) for r in self})
        return super().unlink()
