"""Additional dimensions on the existing governed PR04 margin policy."""
import math
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MarginPolicy(models.Model):
    _inherit = 'vendor.price.revision.margin.policy'
    erosion_enabled = fields.Boolean(string='Evaluate material erosion (pp)', default=False)
    erosion_warning_points = fields.Float(string='Material erosion warning (percentage points)')
    negative_profit_critical = fields.Boolean(default=True, string='Negative profit is critical')

    @api.constrains('erosion_enabled', 'erosion_warning_points')
    def _check_erosion(self):
        for rec in self:
            if not math.isfinite(rec.erosion_warning_points) or rec.erosion_warning_points < 0 or (rec.erosion_enabled and rec.erosion_warning_points <= 0):
                raise ValidationError('An enabled erosion rule requires an explicit positive finite percentage-point threshold.')

    @api.model
    def _validate_margin_input(self, values):
        super()._validate_margin_input(values)
        if 'erosion_warning_points' in values and (isinstance(values['erosion_warning_points'], bool) or not isinstance(values['erosion_warning_points'], (int,float)) or not math.isfinite(values['erosion_warning_points'])):
            raise ValidationError('Erosion threshold must be an explicit finite number of percentage points.')
