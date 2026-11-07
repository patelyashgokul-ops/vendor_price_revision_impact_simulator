"""A genuinely new Odoo shell process checks the previously committed receipt."""
import json
from unittest.mock import patch
from odoo import api
from odoo.exceptions import UserError
from odoo.addons.vendor_price_revision_impact_simulator.models.execution import EXEC
assert env.cr.dbname.startswith('codex_vpr_pr22_')
s=json.loads(env['ir.config_parameter'].get_str('vendor_price_revision_impact_simulator.pr22_commit_probe'))
a=api.Environment(env.cr,s['operator_id'],{'allowed_company_ids':[s['company_id']]})
e=a[EXEC].browse(s['execution_id']);assert e.state=='VERIFIED' and e.executed_at
p=e.plan_id;native=type(a['product.supplierinfo'])
with patch.object(native,'create',side_effect=AssertionError('COLD_REPLAY_CREATE')),patch.object(native,'write',side_effect=AssertionError('COLD_REPLAY_WRITE')):
 assert p.action_apply_approved_vendor_prices(True,p.fingerprint)==e
assert a[EXEC].search_count([('authorization_id','=',e.authorization_id.id)])==1
print('PR22_COLD_REPLAY=PASS separate process, committed database receipt, no second write',flush=True)
# External native edit is a fixture mutation under an explicitly native admin.
root=api.Environment(env.cr,env.uid,{'allowed_company_ids':[s['company_id']]})
t=root['product.supplierinfo'].browse(e.line_ids.target_id);t.price=12
e.invalidate_recordset()
try:p.action_apply_approved_vendor_prices(True,p.fingerprint)
except UserError as exc:assert 'ALREADY_APPLIED_TARGET_CHANGED' in str(exc)
else:raise AssertionError('Old approval overwrote an external edit')
t.invalidate_recordset();assert t.price==12
assert e.line_ids.observed_after_values['price']=='11.0'
print('PR22_EXTERNAL_EDIT=PASS readonly conflict, old11 never overwrites12, immutable evidence retained',flush=True)
env.cr.rollback()
