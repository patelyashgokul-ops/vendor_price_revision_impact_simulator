"""One current anomaly across historical and current approved expectations."""
import json
from unittest.mock import patch
from odoo import api
from odoo.addons.vendor_price_revision_impact_simulator.models.execution import EXEC,LINE
from odoo.addons.vendor_price_revision_impact_simulator.models.monitor_models import INCIDENT
assert env.cr.dbname.startswith('codex_vpr_pr23_')
s=json.loads(env['ir.config_parameter'].get_str('app06.pr23.sample'))
with env.registry.cursor() as cr:
 a=api.Environment(cr,s['operator_id'],{'allowed_company_ids':[s['company_id']]})
 admin=api.Environment(cr,env.uid,{'allowed_company_ids':[s['company_id']]})
 old=a[EXEC].browse(s['execution_id']);target=admin['product.supplierinfo'].browse(old.line_ids.target_id)
 current=a[LINE].search([('target_id','=',target.id)],order='id desc',limit=1)
 assert current.execution_id!=old and target.price==112
 # Earlier episodes are valid retained history, but must not become duplicate
 # active cases for a new anomaly against the current approved expectation.
 prior=a[INCIDENT].search([('target_id','=',target.id),('status','!=','RESOLVED_VERIFIED')])
 for incident in prior:
  incident.action_revalidate_incident()
  incident.action_close_incident('Later independently approved expectation verified','synthetic-successor-resolution')
 target.price=115;admin.flush_all()
 with patch.object(type(target),'write',side_effect=AssertionError('MONITOR_NATIVE_WRITE')), \
      patch.object(type(target),'create',side_effect=AssertionError('MONITOR_NATIVE_CREATE')), \
      patch.object(type(target),'unlink',side_effect=AssertionError('MONITOR_NATIVE_UNLINK')):
  historical=old.action_check_applied_price_integrity().check_ids
  actual=current.execution_id.action_check_applied_price_integrity().check_ids
 incidents=a[INCIDENT].search([('target_id','=',target.id),('code','=','PRICE_DRIFT'),('status','!=','RESOLVED_VERIFIED')])
 assert 'PRICE_DRIFT' in historical.codes and 'PRICE_DRIFT' in actual.codes
 assert len(incidents)==1,('Duplicate current anomaly across superseded/current executions',len(incidents))
 assert incidents.execution_line_id==current
 assert historical.execution_line_id!=actual.execution_line_id
 assert old.line_ids.observed_after_values['price']=='109.0'
 cr.rollback()
print('PR23_CASE SUPERSEDED_AND_CURRENT_SHARE_ONE_CURRENT_INCIDENT=PASS',flush=True)
print('PR23_CASE ORIGINAL_OBSERVATIONS_AND_RESOLUTION_RETAINED=PASS',flush=True)
print('PR23_PROBE=PASS',flush=True)
