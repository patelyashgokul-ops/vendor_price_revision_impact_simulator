"""Creator-bound preapproval intent input and read-only analytical navigation."""
from odoo import fields, models
from odoo.exceptions import AccessError
from .application_plan import PLAN


class ApplicationIntentWizard(models.TransientModel):
    _name = 'vendor.price.revision.application.intent.wizard'
    _inherit = 'vendor.price.revision.purchase.wizard.boundary'
    _description = 'Declare Exact Vendor Rule Intent Before Approval'
    request_id = fields.Many2one('vendor.price.revision.approval.request', required=True)
    batch_id = fields.Many2one(related='request_id.batch_id')
    row_id = fields.Many2one('vendor.price.revision.import.row', required=True)
    operation = fields.Selection([('update','Exact Existing Variant Rule'),('create','New Company/Variant Rule - Planned Only')], required=True)
    target_id = fields.Many2one('product.supplierinfo')
    close_previous_id = fields.Many2one('product.supplierinfo', string='Explicitly Close Previous Rule (Future Boundary Only)')
    target_uom_id = fields.Many2one('uom.uom', required=True)
    allow_discount_change = fields.Boolean()
    vendor_component = fields.Boolean(string='Explicit Vendor Component of a Commercial Package')
    delay = fields.Integer(string='Explicit New-Rule Lead Time')
    sequence = fields.Integer(string='Explicit New-Rule Sequence')
    product_code = fields.Char(string='Explicit New Vendor Code')
    product_name = fields.Char(string='Explicit New Vendor Product Name')
    calendar_timezone = fields.Char(required=True, string='Company Planning Calendar (IANA timezone)')
    reason = fields.Text(required=True)

    def action_declare(self):
        self.ensure_one(); self.check_access('write')
        if self.create_uid != self.env.user:
            raise AccessError('Application intent input belongs to its authenticated creator.')
        spec = dict(row_id=self.row_id.id, operation=self.operation, target_uom_id=self.target_uom_id.id,
                    allow_discount_change=self.allow_discount_change)
        if self.operation == 'update':
            spec['target_id'] = self.target_id.id
        else:
            spec['create_values'] = dict(delay=self.delay, sequence=self.sequence,
                product_code=self.product_code or False, product_name=self.product_name or False)
            spec['close_previous_id'] = self.close_previous_id.id or False
        previous = []
        for old in (self.request_id.vendor_application_scope or {}).get('lines', []):
            if old['row_id'] != self.row_id.id:
                previous.append({k:v for k,v in old.items() if k in ('row_id','operation','target_id','target_uom_id','create_values','allow_discount_change','close_previous_id')})
        self.request_id.action_set_vendor_application_scope(previous + [spec], self.reason, self.vendor_component, self.calendar_timezone)
        return dict(type='ir.actions.act_window', res_model=self.request_id._name, res_id=self.request_id.id, view_mode='form')


class ApplicationNavigation(models.Model):
    _inherit = 'vendor.price.revision.approval.request'

    def action_open_vendor_application_intent(self):
        self.ensure_one(); self.check_access('read')
        return dict(type='ir.actions.act_window', res_model='vendor.price.revision.application.intent.wizard',
            view_mode='form', target='new', context=dict(default_request_id=self.id))

    def action_view_application_plans(self):
        self.ensure_one(); self.check_access('read')
        return dict(type='ir.actions.act_window', res_model=PLAN, view_mode='list,form', domain=[('request_id','=',self.id)])
