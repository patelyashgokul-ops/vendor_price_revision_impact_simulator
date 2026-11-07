"""Optional company SoD controls, using existing immutable policy publication."""
from odoo import fields, models

EXECUTION_FIELDS = frozenset(('application_distinct_maker', 'application_distinct_approver'))


class ExecutionPolicy(models.Model):
    _inherit = 'vendor.price.revision.config'
    application_distinct_maker = fields.Boolean(string='Application operator must differ from maker/requester')
    application_distinct_approver = fields.Boolean(string='Application operator must differ from approval actors/principals')

    def _approval_routing_snapshot(self):
        # Preserve signed PR19-21 source packages. Execution controls are audited
        # by PR04 and read from the exact immutable published policy at execution.
        return {k: v for k, v in super()._approval_routing_snapshot().items() if k not in EXECUTION_FIELDS}

    def _execution_snapshot22(self):
        self.ensure_one()
        return dict(id=self.id, version=self.policy_version, **{k: bool(self[k]) for k in EXECUTION_FIELDS})
