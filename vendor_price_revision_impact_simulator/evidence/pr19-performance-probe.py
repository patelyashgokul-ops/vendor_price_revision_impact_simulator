"""PR19 no-side-effect probe over isolated synthetic native and analytical history."""
import threading
import time
from datetime import date
from unittest.mock import patch
from psycopg2.errors import SerializationFailure
from odoo import Command, api, fields
from odoo.exceptions import UserError
from odoo.tools.binary import BinaryBytes

assert env.cr.dbname.startswith('codex_vpr_pr19_')
clock_patch=patch.object(fields.Date,'context_today',return_value=date(2026,10,28));clock_patch.start()
module='vendor_price_revision_impact_simulator'
company=env['res.company'].with_context(install_demo=True).create({'name':'PR19 Races '+str(time.time_ns()),'currency_id':env.ref('base.INR').id})
ctx={'allowed_company_ids':company.ids}
users=env['res.users'].with_context(no_reset_password=True).create([
 {'name':'PR19 Race '+role,'login':role+str(time.time_ns())+'@example.invalid','company_id':company.id,'company_ids':[Command.set(company.ids)],'group_ids':[Command.set(env.ref(module+'.'+group).ids)]}
 for role,group in [('preparer','group_vendor_price_revision_user'),('manager','group_vpr_purchase_manager')]])
preparer,manager=users
vendor=env['res.partner'].create({'name':'PR19 Race Vendor'})
policy=env['vendor.price.revision.config'].with_company(company).create({'company_id':company.id,'policy_version':'race1','effective_from':'2025-01-01','effective_to':'2030-12-31','change_reason':'Explicit race fixture','currency_rate_policy':'company_reference_date','currency_reference_date':'2026-10-28','reconciliation_basis_policy':'documented_projection',
 'workflow_enabled':True,'workflow_types':['vendor_revision','supplier_scenario'],
 'workflow_high_group_ids':[Command.set(env.ref(module+'.group_vpr_finance_manager').ids)],
 'workflow_critical_group_ids':[Command.set((env.ref(module+'.group_vpr_finance_manager')|env.ref(module+'.group_vpr_director')).ids)],
 'workflow_contract_group_ids':[Command.set(env.ref(module+'.group_vpr_purchase_manager').ids)],
 'margin_ids':[Command.create({'scope':'company','minimum_margin_percent':20,'target_margin_percent':25,'reason':'Fixture'})],
 'risk_ids':[Command.create({'name':'Fixture scale','risk_level':'low','currency_id':company.currency_id.id,'open_ended':True,'reason':'Fixture'})],
 'approval_ids':[Command.create({'name':'Fixture finance','workflow_types':['vendor_revision','supplier_scenario'],'currency_id':company.currency_id.id,'open_ended':True,'reason':'Fixture','required_role_ids':[Command.set(env.ref(module+'.group_vpr_finance_manager').ids)]})]})
policy.action_publish()
env['vendor.price.revision.product.policy'].with_company(company).create({'company_id':company.id,'change_reason':'Exact race identities'})
unit=env.ref('uom.product_uom_unit');usd=env.ref('base.USD');usd.active=True
rates=env['res.currency.rate'].with_company(company).create([{'currency_id':c.id,'company_id':company.id,'name':'2026-10-27','rate':v} for c,v in [(company.currency_id,94),(usd,1)]])
rate_id=rates.filtered(lambda r:r.currency_id==company.currency_id).id
batch_ids=[];products=[];rules=[];boxes=[]
labels=['OPERATIONS']
for n,label in enumerate(labels):
 product=env['product.product'].create({'name':'PR19 Race '+label,'default_code':f'RACE-{company.id}-{n}','company_id':company.id})
 box=env['uom.uom'].create({'name':f'PR19 Race Box10 {company.id}-{n}','relative_uom_id':unit.id,'relative_factor':10})
 rule=env['product.supplierinfo'].with_company(company).create({'partner_id':vendor.id,'company_id':company.id,'product_id':product.id,'uom_id':box.id,'currency_id':usd.id,'price':100,'min_qty':1,'date_end':'2026-10-31'})
 revision=env['vendor.price.revision'].with_user(preparer).with_context(**ctx).create({'company_id':company.id,'vendor_id':vendor.id})
 source=f'Code,Price,Currency,UoM,MOQ,Date,Note\n{product.default_code},110,USD,BOX,1,2026-11-01,{n}\n'.encode()
 wizard=env['vendor.price.revision.import.wizard'].with_user(preparer).with_context(**ctx).create({'company_id':company.id,'revision_id':revision.id,'upload_file':BinaryBytes(source),'upload_filename':f'race-{n}.csv'})
 wizard.action_upload_extract();batch=wizard.result_batch_id
 env['vendor.price.revision.import.mapping'].with_user(preparer).with_context(**ctx).create([{'batch_id':batch.id,'column_number':i,'target':t} for i,t in enumerate(['vendor_product_code','proposed_price_raw','currency_raw','purchase_uom_raw','min_qty_raw','effective_date_raw'],1)])
 batch.action_validate_structure();batch.action_match_products()
 interpretation=batch.action_propose_commercial_context({'uom_aliases':{'BOX':box.id},'price_basis':'net_exclusive'},'Explicit supplier units and net price')
 interpretation.with_user(manager).action_verify_context('Independent interpretation review')
 batch_ids.append(batch.id);products.append(product.id);rules.append(rule.id);boxes.append(box.id)
registry=env.registry;uid=preparer.id;mid=manager.id;company_id=company.id;unit_id=unit.id
env.cr.commit()


# All document/master mutations below are synthetic fixture preparation only.
ops=api.Environment(env.cr,env.uid,dict(ctx,tracking_disable=True,mail_create_nosubscribe=True,mail_notrack=True))
assert all(model in ops for model in ('purchase.order','sale.order','stock.move','stock.quant','account.move'))
product=ops['product.product'].browse(products[0])
product.write({'is_storable':True,'standard_price':70,'list_price':150,'taxes_id':[Command.clear()],'supplier_taxes_id':[Command.clear()]})
warehouse=ops['stock.warehouse'].search([('company_id','=',company_id)],limit=1)
if not warehouse:warehouse=ops['stock.warehouse'].create({'name':'PR19 Operational Warehouse','code':'P8W','company_id':company_id})
receipt=ops['stock.move'].create({'product_id':product.id,'product_uom_qty':50,'uom_id':unit_id,'location_id':ops.ref('stock.stock_location_suppliers').id,'location_dest_id':warehouse.lot_stock_id.id,'company_id':company_id,'price_unit':70})
receipt._action_confirm();receipt._action_assign();receipt.quantity=50;receipt.picked=True;receipt._action_done()
assert receipt.state=='done' and receipt.value>0
package_model=ops['stock.quant']._fields['package_id'].comodel_name
package=ops[package_model].create({'name':'PR19 Retained Package'})
owned_quant=ops['stock.quant'].search([('product_id','=',product.id),('location_id','=',warehouse.lot_stock_id.id),('quantity','>',0)])
owned_quant.write({'package_id':package.id})
pricelist=ops['product.pricelist'].create({'name':'PR19 Operational INR','currency_id':company.currency_id.id,'company_id':company_id})
sale=ops['sale.order'].create({'partner_id':vendor.id,'company_id':company_id,'warehouse_id':warehouse.id,'pricelist_id':pricelist.id,'commitment_date':'2026-11-05 10:00:00','order_line':[Command.create({'product_id':product.id,'product_uom_qty':.3,'product_uom_id':boxes[0],'price_unit':1500,'tax_ids':[Command.clear()]})]})
sale.action_confirm();assert sale.state=='sale'
purchase=ops['purchase.order'].create({'partner_id':vendor.id,'company_id':company_id,'currency_id':company.currency_id.id,'order_line':[Command.create({'product_id':product.id,'product_qty':4,'uom_id':unit_id,'price_unit':100,'name':'PR19 Existing commitment','date_planned':'2026-11-01 00:00:00','tax_ids':[Command.clear()]})]})
purchase.button_confirm();assert purchase.state=='purchase'
accounts=ops['account.account'].create([{'name':'PR19 Fixture Debit','code':'P8D','account_type':'asset_current','company_ids':[Command.set([company_id])]}, {'name':'PR19 Fixture Credit','code':'P8C','account_type':'liability_current','company_ids':[Command.set([company_id])]}])
journal=ops['account.journal'].create({'name':'PR19 Fixture General','code':'P8J','type':'general','company_id':company_id})
entry=ops['account.move'].create({'move_type':'entry','journal_id':journal.id,'date':'2026-10-28','line_ids':[Command.create({'name':'PR19 Debit','account_id':accounts[0].id,'debit':100,'credit':0}),Command.create({'name':'PR19 Credit','account_id':accounts[1].id,'debit':0,'credit':100})]})
entry.action_post();assert entry.state=='posted'
assert ops['stock.quant'].search_count([('product_id','=',product.id),('quantity','>',0)])>0
batch=ops['vendor.price.revision.import.batch'].browse(batch_ids[0]).with_user(uid)
# Master setup may change identity evidence; explicitly refresh upstream gates.
batch.action_validate_structure();batch.action_match_products()
interpretation=batch.action_propose_commercial_context({'uom_aliases':{'BOX':boxes[0]},'price_basis':'net_exclusive'},'Operational safety comparison context')
interpretation.with_user(mid).action_verify_context('Independent operational reference review')
from odoo.addons.vendor_price_revision_impact_simulator.models.supply_governance import GRANT,LOCATION
for user in users:
 ops[GRANT].create({'company_id':company_id,'user_id':user.id,'warehouse_ids':[Command.set(warehouse.ids)],'allow_cost':True,'allow_demand':True,'reason':'Explicit operational safety analytical scope'})
ops[LOCATION].create({'company_id':company_id,'warehouse_id':warehouse.id,'location_id':warehouse.lot_stock_id.id,'classification':'saleable','reason':'Verified saleable operational fixture location'})
batch.action_validate_commercial_prices()
assert batch.row_ids.commercial_status=='commercially_valid'

models={
 'product.supplierinfo':['price','discount','currency_id','uom_id','min_qty','date_start','date_end','write_date'],
 'product.product':['standard_price','list_price','uom_id','write_date'],
 'purchase.order':['state','write_date'], 'purchase.order.line':['price_unit','product_qty','uom_id','write_date'],
 'sale.order':['state','write_date'], 'sale.order.line':['price_unit','product_uom_qty','product_uom_id','write_date'],
 'stock.quant':['quantity','reserved_quantity','write_date'],
 'stock.move.line':['move_id','quantity','quantity_product_uom','state','lot_id','package_id','owner_id','write_date'],
 'stock.picking':['state','location_id','location_dest_id','write_date'],
 'stock.move':['state','quantity','value','price_unit','remaining_value','write_date'],
 'account.move':['state','date','write_date'],'account.move.line':['debit','credit','balance','write_date'],
 'res.currency.rate':['rate','name','write_date'],
 'mail.mail':['state','write_date'],'mail.message':['write_date'],'mail.activity':['write_date'],'ir.cron':['write_date']}
models[package_model]=['name','write_date']
if 'stock.valuation.layer' in ops:models['stock.valuation.layer']=['quantity','value','write_date']
def snapshot():
 return {name:ops[name].search([],order='id').read([field for field in names if field in ops[name]._fields]) for name,names in models.items()}
from odoo.addons.vendor_price_revision_impact_simulator.models.sales_exposure import GRANT as SALES_GRANT
users.write({'group_ids':[Command.link(ops.ref(module+'.group_vpr_sales_manager').id),Command.link(ops.ref('sales_team.group_sale_salesman_all_leads').id)]})
for user in users:
 ops[SALES_GRANT].create({'company_id':company_id,'user_id':user.id,'warehouse_ids':[Command.set(warehouse.ids)],'reason':'Explicit customer scope for PR19 safety'})
models['product.pricelist']=['currency_id','write_date']
models['product.pricelist.item']=['fixed_price','write_date']
models['sale.order.line']+=['discount','tax_ids']
portal=ops['res.users'].with_context(no_reset_password=True).create({'name':'PR19 Portal Negative','login':'pr19portal'+str(time.time_ns())+'@example.invalid','company_id':company_id,'company_ids':[Command.set([company_id])],'group_ids':[Command.set(ops.ref('base.group_portal').ids)]})
models['product.template']=['list_price','uom_id','categ_id','write_date']
models['product.value']=['value','quantity','move_id','write_date']
# Complete authorization fixture setup before capturing native immutability.
# Native group changes can produce their own audit mail.message.
setup_messages=ops['mail.message'].search([])
finance=env['res.users'].browse(mid)
finance.group_ids=[Command.link(env.ref(module+'.group_vpr_finance_manager').id)]
new_messages=ops['mail.message'].search([])-setup_messages
print('PR19_AUTHORIZATION_SETUP_MESSAGES='+repr(new_messages.read(['model','res_id','body'])))
# Independent checkers are synthetic setup, never source collectors.
checkers=ops['res.users'].with_context(no_reset_password=True).create([
 dict(name='PR19 Independent '+role,login='pr19check'+role+str(time.time_ns())+'@example.invalid',company_id=company_id,company_ids=[Command.set([company_id])],group_ids=[Command.set([ops.ref(module+'.group_vpr_'+role).id,ops.ref(module+'.group_vpr_confidential_reader').id,ops.ref('sales_team.group_sale_salesman_all_leads').id])])
 for role in ('purchase_manager','finance_manager','director')])
for checker in checkers:
 ops[GRANT].create(dict(company_id=company_id,user_id=checker.id,warehouse_ids=[Command.set(warehouse.ids)],allow_cost=True,allow_demand=True,reason='Explicit PR19 checker scope'))
 ops[SALES_GRANT].create(dict(company_id=company_id,user_id=checker.id,warehouse_ids=[Command.set(warehouse.ids)],reason='Explicit PR19 customer source scope'))
before=snapshot()
supply=batch.action_collect_supply(warehouse.ids)
assert supply.quantity_verified and supply.bucket_ids
quant_buckets=supply.bucket_ids.filtered(lambda b:b.source_key.startswith('quant:'))
assert len(quant_buckets)==1 and quant_buckets.evidence['quant']['package_id']==package.id
assert float(quant_buckets.physical)==50 and float(quant_buckets.reserved)==3 and float(quant_buckets.eligible_free)==47
assert batch.get_current_supply(warehouse.ids)==supply
assert batch.action_collect_supply(warehouse.ids)==supply
terms=batch.action_propose_supply_terms(warehouse.id,purchase.order_line.id,'firm','Signed supplier commitment in synthetic fixture')
terms.with_user(mid).action_verify_terms('Independent synthetic contract check')
updated=batch.action_collect_supply(warehouse.ids)
assert updated.version==2 and updated.previous_id==supply
allocation=batch.action_run_allocation(warehouse.ids)
assert allocation.demand_ids and float(allocation.demand_ids.outstanding)==3
assert float(allocation.demand_ids.reserved)==3
assert sale.order_line.product_uom_id.id==boxes[0] and sale.order_line.product_uom_qty==.3
print('PR19_MIXED_UOM ordered_boxes=.3 box_factor=10 normalized_outstanding=3 reservation_backed=3')
assert batch.get_current_allocation(warehouse.ids)==allocation
assert batch.action_run_allocation(warehouse.ids)==allocation
commercial=allocation.action_collect_sales_terms()
assert commercial.line_ids and float(commercial.line_ids.outstanding_sales_value)==450
assert allocation.action_collect_sales_terms()==commercial
assert allocation.get_current_sales_terms()==commercial
assert commercial.line_ids.sale_line_id==sale.order_line
purchase_snapshot=batch.action_collect_purchase_terms(warehouse.ids,allocation_id=allocation.id)
assert purchase_snapshot.line_ids and float(purchase_snapshot.line_ids.open_qty)==4
assert float(purchase_snapshot.line_ids.normalized_agreed_unit_price)==100
assert batch.action_collect_purchase_terms(warehouse.ids,allocation_id=allocation.id)==purchase_snapshot
assert batch.get_current_purchase_terms(warehouse.ids,allocation_id=allocation.id)==purchase_snapshot
evidence=purchase_snapshot.line_ids.action_propose_evidence('amendment_pending','Supplier synthetic request','Not accepted by buyer','115')
evidence.with_user(mid).action_verify('Independent reference-only request review')
updated_purchase=batch.action_collect_purchase_terms(warehouse.ids,allocation_id=allocation.id)
assert updated_purchase.line_ids.amendment_status=='amendment_pending'
assert float(updated_purchase.line_ids.amendment_evidence['conditional_difference'])==60
costs=batch.action_attribute_costs(allocation.id,updated_purchase.id,'2026-11-05')
assert costs.line_ids and float(costs.line_ids.quantity)==3
assert costs.line_ids.allocation_type=='existing_reserved_for_demand'
assert costs.line_ids.confidence=='supported_estimate'
assert float(costs.line_ids.unit_cost)==70
assert batch.action_attribute_costs(**costs.scope)==costs
assert batch.get_current_costs(**costs.scope)==costs
upstream_models={'vendor.price.revision.supply.snapshot':['input_digest','version','write_date'],
 'vendor.price.revision.allocation.snapshot':['fingerprint','version','write_date'],
 'vendor.price.revision.sales.snapshot':['fingerprint','version','write_date'],
 'vendor.price.revision.purchase.snapshot':['fingerprint','version','write_date'],
 'vendor.price.revision.cost.snapshot':['fingerprint','version','write_date'],
 'vendor.price.revision.cost.line':['quantity','unit_cost','write_date']}
def upstream_state():return {m:ops[m].search([],order='id').read(names,load=None) for m,names in upstream_models.items()}
upstream_before=upstream_state()
financial=batch.with_user(mid).action_calculate_financial_exposure(costs.id,commercial.id)
assert float(financial.baseline_total)==210 and float(financial.revised_total)==210 and float(financial.incremental_total)==0
assert financial.cost_complete and financial.delta_complete and financial.state=='estimated'
assert batch.with_user(mid).action_calculate_financial_exposure(**financial.scope)==financial
assert batch.with_user(mid).get_current_financial_exposure(**financial.scope)==financial
assert upstream_state()==upstream_before,'Financial simulation changed upstream analytical records'
upstream_models.update({'vendor.price.revision.financial.snapshot':['fingerprint','version','write_date'],
 'vendor.price.revision.financial.line':['quantity','baseline_extended_cost','revised_extended_cost','write_date'],
 'vendor.price.revision.financial.issue':['code','write_date']})
upstream_before=upstream_state()
margin=batch.with_user(mid).action_calculate_profitability(financial.id)
assert float(margin.net_revenue)==450 and float(margin.baseline_gross_profit)==240 and float(margin.revised_gross_profit)==240
assert margin.state=='estimated' and margin.risk_status=='normal'
assert batch.with_user(mid).action_calculate_profitability(financial.id)==margin
assert batch.with_user(mid).get_current_profitability(financial.id)==margin
assert upstream_state()==upstream_before,'Profitability simulation changed upstream evidence'
upstream_models.update({'vendor.price.revision.margin.snapshot':['fingerprint','version','write_date'],
 'vendor.price.revision.margin.line':['net_revenue','revised_cost','risk_status','write_date'],
 'vendor.price.revision.margin.aggregate':['net_revenue','risk_status','write_date'],
 'vendor.price.revision.margin.risk':['code','severity','write_date']})
upstream_before=upstream_state()
reconciliation=batch.with_user(mid).action_run_reconciliation(margin.id)
assert reconciliation.check_ids and reconciliation.readiness=='ready_for_financial_review', (reconciliation.readiness,reconciliation.check_ids.filtered(lambda c:c.status not in ('pass','not_applicable')).read())
assert reconciliation.margin_id==margin
assert batch.with_user(mid).action_run_reconciliation(margin.id)==reconciliation
assert batch.with_user(mid).get_current_reconciliation(margin.id)==reconciliation
assert upstream_state()==upstream_before,'Reconciliation changed upstream evidence'
for suffix in ('run','check','exception','review'):
 upstream_models['vendor.price.revision.reconciliation.'+suffix]=['write_date']
upstream_before=upstream_state()
scenario=batch.with_user(mid).action_create_vendor_scenario(reconciliation.id,'Native immutability scenario')
result=scenario.action_calculate_scenario()
assert result.state=='financially_verified' and result.detail_ids
assert scenario.action_calculate_scenario()==result
assert scenario.get_current_scenario()==result
alternative=scenario.action_clone_scenario('Isolated hypothetical price change')
alternative.action_set_assumptions([dict(product_id=product.id,mode='explicit',value='112',reason='Hypothetical discussion only')],'Immutable scenario input')
alternative.action_calculate_scenario()
assert upstream_state()==upstream_before,'Scenario changed upstream evidence'
for suffix in ('','input','line','result','detail','event'):
 name='vendor.price.revision.scenario'+('.'+suffix if suffix else '')
 upstream_models[name]=['write_date']
upstream_before=upstream_state()
recommendation=scenario.action_generate_recommendations()
assert recommendation.line_ids and recommendation.complete
assert scenario.action_generate_recommendations()==recommendation
assert recommendation.get_current_recommendation()==recommendation
review=recommendation.action_record_review('reviewed','Commercial reference examined','Incomplete basis remains review-required')
assert recommendation.complete and review
assert upstream_state()==upstream_before,'Recommendation altered upstream analytical history'
assert len(upstream_models)==23
print('PR19_UPSTREAM_MODELS='+','.join(sorted(upstream_models)))
print('PR19_UPSTREAM_IMMUTABILITY=PASS twenty_three upstream analytical models unchanged')
from odoo.exceptions import AccessError
for forbidden in (portal,ops.ref('base.public_user')):
 for model,ids in (('vendor.price.revision.recommendation',recommendation.ids),('vendor.price.revision.recommendation.line',recommendation.line_ids.ids),('vendor.price.revision.recommendation.option',recommendation.option_ids.ids),('vendor.price.revision.recommendation.review',review.ids)):
  try:ops[model].with_user(forbidden).browse(ids).read(['id'])
  except AccessError:pass
  else:raise AssertionError('Portal/public financial disclosure')
print('PR19_PORTAL_PUBLIC=PASS direct_header_and_line_reads_denied')
# Freeze all PR08-18 evidence before creating/submitting/withdrawing PR19.
for suffix in ('','line','option','review'):
 upstream_models['vendor.price.revision.recommendation'+('.'+suffix if suffix else '')]=['write_date']
assert len(upstream_models)==27
approval_upstream=upstream_state()
request=ops['vendor.price.revision.approval.request'].with_user(mid).create(dict(baseline_id=reconciliation.id,request_type='vendor_revision',reason='Synthetic management review; no decision'))
assert request.action_validate_request()
request.action_submit_for_review();request.action_submit_for_review()
assert request.state=='awaiting_review' and request.get_current_request()==request
assert request.stage_ids[:1].stage_status=='ready_for_review'
assert all(stage.stage_status=='waiting_predecessor' for stage in request.stage_ids[1:])
assert not request.stage_ids.activity_ids
assert set(request.stage_ids.assigned_ids.ids)<=set(checkers.ids)
assert request.evidence_id and request.evidence_id.data['money']
request.action_withdraw_request('Synthetic withdrawal before any management decision')
assert request.state=='withdrawn' and upstream_state()==approval_upstream
for forbidden in (portal,ops.ref('base.public_user')):
 for name,records in (('request',request),('stage',request.stage_ids),('evidence',request.evidence_id),('event',request.event_ids)):
  try:records.with_user(forbidden).read(['id'])
  except AccessError:pass
  else:raise AssertionError('Approval financial disclosure '+name)
attachment=ops['ir.attachment'].with_user(mid).create(dict(name='PR19 protected review evidence.txt',res_model=request._name,res_id=request.id,raw=BinaryBytes(b'Synthetic approval evidence only')))
for forbidden in (portal,ops.ref('base.public_user')):
 try:attachment.with_user(forbidden).read(['raw'])
 except AccessError:pass
 else:raise AssertionError('Protected approval attachment disclosed')
print('PR19_PROTECTED_ATTACHMENT=PASS portal_public_denied')
print('PR19_APPROVAL_UPSTREAM_IMMUTABILITY=PASS twenty_seven models unchanged')
print('PR19_APPROVAL_ROUTE=PASS immutable distinct current route, idempotent submit, preserved withdrawal')
after=snapshot()
for model in models:
 if before[model]!=after[model]:
  print('PR19_OPERATIONAL_DIFFERENCE '+model+' before_count='+str(len(before[model]))+' after_count='+str(len(after[model])))
assert after==before,'Financial analysis modified operational/master records or counts'
assert entry.state=='posted' and sale.state=='sale' and purchase.state=='purchase'
print('PR19_OPERATIONAL_FIXTURES confirmed_SO='+str(sale.id)+' confirmed_PO='+str(purchase.id)+' posted_entry='+str(entry.id)+' valued_done_move='+str(receipt.id)+' move_value='+str(receipt.value))
print('PR19_OPERATIONAL_MODELS='+','.join(models))
print('PR19_OPERATIONAL_SVL_MODEL='+('PRESENT' if 'stock.valuation.layer' in ops else 'NOT_APPLICABLE_Odoo20_stock_move_value'))
print('PR19_OPERATIONAL_SAFETY=PASS')
print('PR19_PROBE=PASS')

# Actual prepare/submit/withdraw services, same verified source, 500 independent
# immutable request versions. Historical load below is explicitly fixture-only.
import json,psutil
sample=dict(request_id=request.id,reference=request.name,version=request.version,company_id=request.company_id.id,currency_id=request.currency_id.id,financial_readiness_at_submission=request.financial_readiness,retained_state=request.state,policy_id=request.policy_id.id,policy_version=request.policy_version,source_fingerprint=request.source_fingerprint,submission_fingerprint=request.submission_fingerprint,evidence_id=request.evidence_id.id,evidence_fingerprint=request.evidence_id.fingerprint,source_refs=request.evidence_id.data['source_refs'],money=request.financial_values,frozen_route=request.evidence_id.data['route'],retained_stage_states=request.stage_ids.mapped('stage_status'),event_ids=request.event_ids.ids,excluded_reviewers=request.evidence_id.data['excluded_reviewers'])
print('PR19_APPROVAL_SAMPLE='+json.dumps(sample,sort_keys=True),flush=True)
proc=psutil.Process()
start=time.perf_counter();sql_start=env.cr.sql_log_count;rss_start=proc.memory_info().rss;peak=rss_start
actual_ids=[]
for index in range(1,501):
 r=ops['vendor.price.revision.approval.request'].with_user(mid).create(dict(baseline_id=reconciliation.id,request_type='vendor_revision',reason='Executed synthetic performance request '+str(index)))
 r.action_submit_for_review();assert r.evidence_id and r.stage_ids
 r.action_withdraw_request('Performance fixture withdrawn without decision');actual_ids.append(r.id)
 peak=max(peak,proc.memory_info().rss)
 if index in (100,500):
  measured=dict(requests=index,seconds=round(time.perf_counter()-start,3),sql_queries=env.cr.sql_log_count-sql_start,rss_start_bytes=rss_start,observed_rss_peak_bytes=peak,rss_sampling='after each withdrawal; not intra-call peak',measurement_scope='warm sequential actual prepare+submit+withdraw, exact same financial source, activities disabled; fixture preparation excluded')
  print('PR19_PERFORMANCE_'+str(index)+'='+json.dumps(measured,sort_keys=True),flush=True)
assert len(set(actual_ids))==500
H='vendor.price.revision.approval.request';S='vendor.price.revision.approval.stage'
seed_start=time.perf_counter()
headers=ops[H].with_context(tracking_disable=True,mail_create_nolog=True,mail_create_nosubscribe=True)._record([
 dict(batch_id=batch.id,baseline_id=reconciliation.id,currency_id=company.currency_id.id,request_type='vendor_revision',reason='LOAD FIXTURE ONLY: not submitted or approved',requested_by=mid,maker_id=uid,name='PR19-LOAD-'+str(company_id)+'-'+str(i),scope_key='pr19-load-'+str(company_id)+'-'+str(i),version=1,state='withdrawn') for i in range(2000)])
stages=ops[S]._record([dict(batch_id=batch.id,request_id=header.id,sequence=level+1,code='load-fixture-'+str(level),quorum=1,stage_status='cancelled',plan={'fixture':'historical pagination only','submitted':False},assigned_by=mid,assigned_at=fields.Datetime.now(),policy_version='LOAD-FIXTURE-NO-AUTHORITY') for header in headers for level in range(5)])
assert len(headers)==2000 and len(stages)==10000
seed_seconds=round(time.perf_counter()-seed_start,3)
# Inactive source-linked headers/stages have no active authority or financial
# assertions. Fixture creation is reported separately from paginated reads.
query_start=time.perf_counter();query_sql=env.cr.sql_log_count
for offset in (0,960,1920):
 rows=ops[H].with_user(mid).search([('id','in',headers.ids)],order='id',limit=80,offset=offset)
 assert rows.read(['name','state','current_state'])
for offset in (0,4960,9920):
 rows=ops[S].with_user(mid).search([('request_id','in',headers.ids)],order='id',limit=80,offset=offset)
 assert rows.read(['sequence','stage_status','effective_status'])
assert ops[H].with_user(mid).search_count([('id','in',headers.ids)])==2000
assert ops[S].with_user(mid).search_count([('request_id','in',headers.ids)])==10000
measured=dict(historical_requests=2000,historical_stages=10000,fixture_seed_seconds=seed_seconds,paginated_read_seconds=round(time.perf_counter()-query_start,3),sql_queries=env.cr.sql_log_count-query_sql,rss_bytes=proc.memory_info().rss,measurement_scope='explicitly seeded inactive history, not 2000 executed submissions; three 80-row header pages and three 80-row stage pages plus exact scoped counts')
print('PR19_PERFORMANCE_2000='+json.dumps(measured,sort_keys=True),flush=True)
assert snapshot()==before and upstream_state()==approval_upstream
print('PR19_PERFORMANCE=PASS',flush=True)
env.cr.rollback();clock_patch.stop()
