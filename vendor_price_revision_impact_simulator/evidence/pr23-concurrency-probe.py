"""Real PostgreSQL transactions: overlap, retry, review and coherent observation."""
import json
import threading
import time
from odoo import api
from odoo.exceptions import UserError
from psycopg2.errors import SerializationFailure,LockNotAvailable
from odoo.addons.vendor_price_revision_impact_simulator.models.execution import EXEC
from odoo.addons.vendor_price_revision_impact_simulator.models.monitor_models import RUN,INCIDENT
from odoo.addons.vendor_price_revision_impact_simulator.models.monitor_policy import POLICY
assert env.cr.dbname.startswith('codex_vpr_pr23_')
sample=json.loads(env['ir.config_parameter'].get_str('app06.pr23.sample'))
uid,cid,eid=sample['operator_id'],sample['company_id'],sample['execution_id']
ctx={'allowed_company_ids':[cid],'tz':'UTC'}
with env.registry.cursor() as cr:
 a=api.Environment(cr,uid,ctx);e=a[EXEC].browse(eid);target_id=e.line_ids.target_id
 admin=api.Environment(cr,env.uid,ctx);target=admin['product.supplierinfo'].browse(target_id);original=target.price
 target.price=original+3;target.flush_recordset()
 policy=a[POLICY].create({'company_id':cid,'batch_size':1,'enabled':True});policy_id=policy.id
 cr.commit()

def overlap(first,second):
 held=threading.Event();attempted=threading.Event();release=threading.Event();out={}
 def worker1():
  try:
   with env.registry.cursor() as cr:
    a=api.Environment(cr,uid,ctx);first(a);held.set();assert attempted.wait(30);assert release.wait(30);cr.commit();out['first']='committed'
  except Exception as exc:out['first']=repr(exc);held.set()
 def worker2():
  assert held.wait(30)
  try:
   with env.registry.cursor() as cr:
    a=api.Environment(cr,uid,ctx);attempted.set();second(a);cr.commit();out['second']='committed'
  except UserError:out['second']='controlled_retry'
  except SerializationFailure:out['second']='serialization_retry'
  except LockNotAvailable:out['second']='lock_retry'
  except Exception as exc:out['second']=repr(exc)
  finally:release.set()
 threads=[threading.Thread(target=worker1),threading.Thread(target=worker2)]
 for t in threads:t.start()
 for t in threads:t.join(90)
 assert not any(t.is_alive() for t in threads),out
 assert out['first']=='committed',out
 return out

try:
 out=overlap(lambda a:a[EXEC].browse(eid).action_check_applied_price_integrity(),
             lambda a:a[EXEC].browse(eid).action_check_applied_price_integrity())
 assert out['second'] in ('controlled_retry','serialization_retry'),out
 with env.registry.cursor() as cr:
  a=api.Environment(cr,uid,ctx);e=a[EXEC].browse(eid);run=e.action_check_applied_price_integrity()
  incidents=a[INCIDENT].search([('execution_line_id','in',e.line_ids.ids),('code','=','PRICE_DRIFT')]);assert len(incidents)==1
  cr.commit()
 print('PR23_CASE MANUAL_MANUAL_OVERLAP_AND_RETRY=PASS',flush=True)
 out=overlap(lambda a:a[EXEC].browse(eid).action_check_applied_price_integrity(),
             lambda a:a[POLICY].browse(policy_id).action_run_batch())
 assert out['second'] in ('controlled_retry','serialization_retry'),out
 print('PR23_CASE MANUAL_CRON_OVERLAP=PASS',flush=True)
 out=overlap(lambda a:a[POLICY].browse(policy_id).action_run_batch(),
             lambda a:a[POLICY].browse(policy_id).action_run_batch())
 assert out['second'] in ('controlled_retry','serialization_retry','lock_retry'),out
 print('PR23_CASE TWO_CRON_WORKERS_PROGRESS_LOCK=PASS',flush=True)
 # An external writer can commit while a read-only monitor's transaction remains
 # open. Repeatable-read must retain one whole observation, never mixed fields.
 captured={}
 def first(a):
  r=a[EXEC].browse(eid).action_check_applied_price_integrity();captured['check']=r.check_ids.observed
 def external(a):
  admin=api.Environment(a.cr,env.uid,ctx);target=admin['product.supplierinfo'].browse(target_id)
  target.write({'price':original+6,'min_qty':77});target.flush_recordset()
 out=overlap(first,external);assert out['second']=='committed',out
 assert float(captured['check']['price'])==original+3 and float(captured['check']['min_qty'])!=77
 with env.registry.cursor() as cr:
  a=api.Environment(cr,uid,ctx);check=a[EXEC].browse(eid).action_check_applied_price_integrity().check_ids
  assert float(check.observed['price'])==original+6 and float(check.observed['min_qty'])==77
  cr.commit()
 print('PR23_CASE EXTERNAL_CHANGE_COHERENT_REPEATABLE_READ=PASS',flush=True)
 # Reviews use the same execution barrier and versioned incident writes.
 with env.registry.cursor() as cr:
  a=api.Environment(cr,uid,ctx);incident=a[INCIDENT].search([('execution_id','=',eid),('code','=','PRICE_DRIFT')]);iid=incident.id
 out=overlap(lambda a:a[INCIDENT].browse(iid).action_review('investigate','Concurrent authorized review','synthetic-review'),
             lambda a:a[EXEC].browse(eid).action_check_applied_price_integrity())
 assert out['second'] in ('controlled_retry','serialization_retry'),out
 print('PR23_CASE REVIEW_OBSERVATION_SERIALIZATION=PASS',flush=True)
finally:
 # Test harness cleanup restores synthetic setup terms only; no monitoring
 # method has price authority, and retained incident evidence is never deleted.
 with env.registry.cursor() as cr:
  admin=api.Environment(cr,env.uid,ctx)
  admin['product.supplierinfo'].browse(target_id).write({'price':original,'min_qty':float(sample['original_evidence']['lines'][0]['observed_after']['min_qty'])})
  a=api.Environment(cr,uid,ctx);a[POLICY].browse(policy_id).write({'enabled':False});cr.commit()
print('PR23_PROBE=PASS',flush=True)
