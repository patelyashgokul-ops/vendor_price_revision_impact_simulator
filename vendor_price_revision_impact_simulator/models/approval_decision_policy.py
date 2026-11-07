"""PR20 opt-in controls on the existing immutable published PR04 policy."""
from odoo import fields, models
from .approval_math import ROLES
from .approval_decision_math import expiry

DECISION_FIELDS = frozenset((
    'decision_enabled', 'decision_require_reason', 'decision_review_hours',
    'decision_validity_mode', 'decision_valid_days', 'decision_valid_date',
    'decision_timezone', 'decision_delegation_enabled', 'decision_governance_group_ids',
))


class DecisionPolicy(models.Model):
    _inherit = 'vendor.price.revision.config'

    decision_enabled = fields.Boolean(default=False, string='Enable management approval decisions')
    decision_require_reason = fields.Boolean(default=True, string='Require approval justification')
    decision_review_hours = fields.Integer(default=0, help='Zero means no fixed review deadline; source freshness is always mandatory.')
    decision_validity_mode = fields.Selection([
        ('source_only', 'While exact sources and authority remain current'),
        ('days', 'Fixed elapsed days from final approval'),
        ('date', 'Through an explicit local business date'),
    ], default='source_only', required=True)
    decision_valid_days = fields.Integer()
    decision_valid_date = fields.Date()
    decision_timezone = fields.Char(help='Explicit IANA business timezone for a date-only expiry.')
    decision_delegation_enabled = fields.Boolean(default=False)
    decision_governance_group_ids = fields.Many2many('res.groups', relation='vpr_decision_governance_rel', string='Delegation / invalidation governance roles')

    def _approval_routing_snapshot(self):
        self.ensure_one()
        # New decision controls do not rewrite PR19 financial/routing evidence.
        # The full PR04 audit still includes these fields; PR20 freezes and
        # compares their own explicit snapshot at submission and every decision.
        return {k: v for k, v in self._audit_snapshot()[str(self.id)].items() if k not in DECISION_FIELDS}

    def _decision_snapshot(self):
        self.ensure_one()
        data = self.read(sorted(DECISION_FIELDS))[0]
        data.pop('id', None)
        data['decision_governance_group_ids'] = sorted(self.decision_governance_group_ids.ids)
        return data

    def _setup_errors(self):
        errors = super()._setup_errors()
        if not self.decision_enabled:
            return errors
        if not self.workflow_enabled:
            errors.append('Decision execution requires explicit management routing.')
        if self.decision_review_hours < 0:
            errors.append('Review hours cannot be negative.')
        supported = self.env['res.groups'].concat([self.env.ref('vendor_price_revision_impact_simulator.' + role) for role in ROLES])
        if not self.decision_governance_group_ids or self.decision_governance_group_ids - supported:
            errors.append('Select explicit supported governance roles for approval invalidation/delegation authorization.')
        try:
            expiry(fields.Datetime.now(), self.decision_validity_mode, self.decision_valid_days,
                   self.decision_valid_date or None, self.decision_timezone or None)
        except ValueError as exc:
            errors.append(str(exc))
        return errors
