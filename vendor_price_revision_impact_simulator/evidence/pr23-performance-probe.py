"""Measured monitoring over genuine previously committed PR22 applied lines."""
import json
import time
import tracemalloc
from odoo import api
from odoo.addons.vendor_price_revision_impact_simulator.models.execution import EXEC
assert env.cr.dbname.startswith('codex_vpr_pr23_')
results=[]
for size in (10,100,500,2000):
 with env.registry.cursor() as cr:
  admin=api.Environment(cr,env.uid,{})
  candidates=admin[EXEC].search([('verified_line_count','=',size)],order='id')
  assert candidates,'Missing real committed '+str(size)+'-line PR22 fixture'
  e=candidates[-1];uid=e.operator_id.id;cid=e.company_id.id;eid=e.id
 with env.registry.cursor() as cr:
  a=api.Environment(cr,uid,{'allowed_company_ids':[cid],'tz':'UTC'});e=a[EXEC].browse(eid)
  assert e.state=='VERIFIED'
  started=time.perf_counter();queries=cr.sql_log_count;tracemalloc.start()
  after=0;processed=0;pages=[];statuses={};budget_seconds=180
  while processed<size:
   page_start=time.perf_counter();run=e._monitor23(after_line=after,limit=100,run_type='PERFORMANCE_BOUNDED_REVALIDATION')
   assert run.processed_count>0
   assert run.passed_count+run.failed_count+run.blocked_count==run.processed_count
   processed+=run.processed_count;after=run.last_processed_reference
   pages.append(dict(processed=run.processed_count,duration_seconds=time.perf_counter()-page_start,state=run.state,has_more=run.has_more))
   for check in run.check_ids:statuses[check.status]=statuses.get(check.status,0)+1
   if not run.has_more:break
   if time.perf_counter()-started>budget_seconds:break
  _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
  assert all(status in ('PASS','EXPECTED_CHANGE') for status in statuses),statuses
  item=dict(historical_execution_id=eid,actual_applied_lines=size,observed_lines=processed,
   coverage='COMPLETE' if processed==size else 'PARTIAL_REMAINING_NOT_RUN',duration_seconds=time.perf_counter()-started,
   sql_client_count=cr.sql_log_count-queries,python_traced_peak_bytes=peak,counts=statuses,pages=pages,
   methodology='Warm installed registry; genuine committed PR22 ledger; native selectors; original source user; tracemalloc overhead included; client SQL only; no financial rebuild; atomic pages rolled back after measurement.',
   scope_limit='180 second cooperative benchmark budget per workload; a single page may exceed it. Partial coverage is not a full integrity PASS.')
  results.append(item);print('PR23_PERFORMANCE='+json.dumps(item,sort_keys=True),flush=True)
  assert processed<=size and processed>0
  print('PR23_CASE PERFORMANCE_'+str(size)+'=PASS',flush=True)
  cr.rollback()
with env.registry.cursor() as cr:
 from odoo.addons.vendor_price_revision_impact_simulator.models.execution import LINE
 a=api.Environment(cr,uid,{'allowed_company_ids':[cid]})
 ids=a[LINE].search([('execution_id','=',eid)],order='id').ids
 references=(ids*((10000//len(ids))+1))[:10000]
 started=time.perf_counter();queries=cr.sql_log_count
 # These are repeated references to actual authorized immutable lines. This
 # measures indexed reference lookup only, not10000 distinct application events.
 cr.execute('SELECT count(*) FROM unnest(%s::int[]) AS ref(id) JOIN vendor_price_revision_application_execution_line AS line ON line.id=ref.id',[references])
 assert cr.fetchone()[0]==10000
 print('PR23_PERFORMANCE_REFERENCE_LOOKUP='+json.dumps(dict(reference_count=10000,distinct_authorized_lines=len(set(references)),
   duration_seconds=time.perf_counter()-started,sql_client_count=cr.sql_log_count-queries,
   coverage='LOOKUP_ONLY; repeated real references; not10000 distinct historical applications or full integrity checks')),flush=True)
 print('PR23_CASE PERFORMANCE_10000_REAL_REFERENCE_LOOKUPS=PASS',flush=True)
print('PR23_PROBE=PASS',flush=True)
