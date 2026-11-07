"""Real 500/2000-line cohorts; measure recommendation generation, not fixture setup."""
import json,time,threading,psutil
from odoo import Command,api
from odoo.tools.binary import BinaryBytes
from odoo.addons.vendor_price_revision_impact_simulator.models.supply_governance import GRANT,LOCATION
from odoo.addons.vendor_price_revision_impact_simulator.models.sales_exposure import GRANT as SALES_GRANT
assert env.cr.dbname.startswith('codex_vpr_pr18_')
module='vendor_price_revision_impact_simulator'
measurements=[]
for size in (500,2000):
 company=env['res.company'].with_context(install_demo=True).create(dict(name='PR18 Workload '+str(size)+' '+str(time.time_ns()),currency_id=env.ref('base.INR').id))
 ctx=dict(allowed_company_ids=company.ids,tracking_disable=True,mail_create_nosubscribe=True,mail_notrack=True)
 ops=api.Environment(env.cr,env.uid,ctx)
 groups=[ops.ref(module+'.'+v).id for v in ('group_vendor_price_revision_user','group_vpr_finance_manager','group_vpr_purchase_manager','group_vpr_sales_manager')]+ops.ref('sales_team.group_sale_salesman_all_leads').ids
 actor=ops['res.users'].with_context(no_reset_password=True).create(dict(name='PR18 Performance Finance',login='pr18perf'+str(time.time_ns())+'@example.invalid',company_id=company.id,company_ids=[Command.set(company.ids)],group_ids=[Command.set(groups)]))
 wh=ops['stock.warehouse'].search([('company_id','=',company.id)],limit=1)
 if not wh:wh=ops['stock.warehouse'].create(dict(name='PR18 Performance',code='P'+str(company.id),company_id=company.id))
 wh.out_type_id.reservation_method='manual'
 ops[GRANT].create(dict(company_id=company.id,user_id=actor.id,warehouse_ids=[Command.set(wh.ids)],allow_cost=True,allow_demand=True,reason='Explicit isolated workload scope'))
 ops[SALES_GRANT].create(dict(company_id=company.id,user_id=actor.id,warehouse_ids=[Command.set(wh.ids)],reason='Explicit customer financial workload scope'))
 ops[LOCATION].create(dict(company_id=company.id,warehouse_id=wh.id,location_id=wh.lot_stock_id.id,classification='saleable',reason='Known saleable stock scope'))
 policy=ops['vendor.price.revision.config'].create(dict(company_id=company.id,policy_version='workload1',effective_from='2025-01-01',effective_to='2030-12-31',change_reason='Explicit synthetic projection policy',reconciliation_basis_policy='documented_projection',
  margin_ids=[Command.create(dict(scope='company',minimum_margin_percent=15,target_margin_percent=25,reason='Workload target'))],
  risk_ids=[Command.create(dict(name='Workload band',risk_level='low',currency_id=company.currency_id.id,open_ended=True,reason='Workload interval'))],
  approval_ids=[Command.create(dict(name='Workload role definition only',currency_id=company.currency_id.id,open_ended=True,reason='No approval execution',required_role_ids=[Command.set(ops.ref(module+'.group_vpr_finance_manager').ids)]))]))
 policy.action_publish()
 ops['vendor.price.revision.product.policy'].create(dict(company_id=company.id,change_reason='Exact workload product identity'))
 unit=ops.ref('uom.product_uom_unit');vendor=ops['res.partner'].create(dict(name='PR18 Workload Supplier'))
 product=ops['product.product'].create(dict(name='PR18 Workload Product',default_code='PR18-PERF-'+str(size)+'-'+str(company.id),company_id=company.id,is_storable=True,standard_price=100,taxes_id=[Command.clear()],supplier_taxes_id=[Command.clear()]))
 ops['product.supplierinfo'].create(dict(partner_id=vendor.id,company_id=company.id,product_id=product.id,uom_id=unit.id,currency_id=company.currency_id.id,price=100,min_qty=1,date_start='2025-01-01',date_end='2026-10-31'))
 finance=api.Environment(env.cr,actor.id,ctx)
 revision=finance['vendor.price.revision'].create(dict(company_id=company.id,vendor_id=vendor.id))
 raw=f'Code,Price,Currency,UoM,MOQ,Date\n{product.default_code},115,INR,PCS,1,2026-11-01\n'.encode()
 wizard=finance['vendor.price.revision.import.wizard'].create(dict(company_id=company.id,revision_id=revision.id,upload_file=BinaryBytes(raw),upload_filename='pr18-workload.csv'))
 wizard.action_upload_extract();batch=wizard.result_batch_id
 finance['vendor.price.revision.import.mapping'].create([dict(batch_id=batch.id,column_number=i,target=t) for i,t in enumerate(('vendor_product_code','proposed_price_raw','currency_raw','purchase_uom_raw','min_qty_raw','effective_date_raw'),1)])
 batch.action_validate_structure();batch.action_match_products()
 interpretation=batch.action_propose_commercial_context(dict(uom_aliases={'PCS':unit.id},price_basis='net_exclusive'),'Known supplier source unit and net price')
 # Independent context checker remains a different actual actor.
 checker=ops['res.users'].with_context(no_reset_password=True).create(dict(name='PR18 Performance Independent Checker',login='pr18checker'+str(time.time_ns())+'@example.invalid',company_id=company.id,company_ids=[Command.set(company.ids)],group_ids=[Command.set(groups)]))
 interpretation.with_user(checker).action_verify_context('Independent supplier interpretation verified')
 batch.action_validate_commercial_prices();assert batch.row_ids.commercial_status=='commercially_valid'
 pl=ops['product.pricelist'].create(dict(name='PR18 Workload INR',company_id=company.id,currency_id=company.currency_id.id))
 def order(qty):
  return ops['sale.order'].create(dict(company_id=company.id,partner_id=vendor.id,warehouse_id=wh.id,pricelist_id=pl.id,commitment_date='2026-11-05 10:00:00',validity_date='2026-11-30',order_line=[Command.create(dict(product_id=product.id,product_uom_qty=1,product_uom_id=unit.id,price_unit=140,tax_ids=[Command.clear()])) for _ in range(qty)]))
 confirmed=order(1);confirmed.action_confirm();quote=order(size-1)
 partial=quote.order_line[0];partial.write(dict(product_uom_qty=2,price_unit=140))
 batch.action_collect_supply(wh.ids)
 def inputs(allocation):
  purchase=batch.action_collect_purchase_terms(wh.ids,True,allocation.id,False)
  cost=batch.action_attribute_costs(allocation.id,purchase.id,'2026-11-05')
  sales=allocation.action_collect_sales_terms()
  return cost,sales
 a=batch.action_run_allocation(wh.ids);c,ss=inputs(a)
 ss.line_ids.action_review_price_protection('fixed_price_verified','Exact synthetic fixed commitment','Independent workload customer evidence')
 ss=a.action_collect_sales_terms();f=batch.action_calculate_financial_exposure(c.id,ss.id);m=batch.action_calculate_profitability(f.id)
 qa=batch.action_run_allocation(wh.ids,True,quotation_ids=quote.ids);qc,qs=inputs(qa)
 qf=batch.action_calculate_financial_exposure(qc.id,qs.id,f.id);qm=batch.action_calculate_profitability(qf.id,m.id)
 reconciliation=batch.action_run_reconciliation(qm.id)
 scenario=batch.action_create_vendor_scenario(reconciliation.id,'PR18 '+str(size)+' source-linked customer targets')
 result=scenario.action_calculate_scenario();assert result.state=='financially_verified',result.controls
 references={'PR11_sales':len(qs.line_ids),'PR13_cost':len(qc.line_ids),'PR14_financial':len(qf.line_ids),'PR15_margin':len(qm.line_ids),'PR17_detail':len(result.detail_ids)}
 assert all(v==size for v in references.values()),references
 native_fields={
  'product.supplierinfo':['price','discount','currency_id','uom_id','min_qty','date_start','date_end','write_date'],
  'product.product':['standard_price','list_price','uom_id','write_date'],
  'product.template':['list_price','uom_id','categ_id','write_date'],'product.value':['value','quantity','move_id','write_date'],
  'product.pricelist':['currency_id','write_date'],'product.pricelist.item':['fixed_price','write_date'],
  'purchase.order':['state','write_date'],'purchase.order.line':['price_unit','product_qty','uom_id','write_date'],
  'sale.order':['state','write_date'],'sale.order.line':['price_unit','discount','tax_ids','product_uom_qty','product_uom_id','write_date'],
  'stock.quant':['quantity','reserved_quantity','write_date'],
  'stock.move.line':['move_id','quantity','quantity_product_uom','state','lot_id','package_id','owner_id','write_date'],
  'stock.picking':['state','location_id','location_dest_id','write_date'],
  'stock.move':['state','quantity','value','price_unit','remaining_value','write_date'],
  'account.move':['state','date','write_date'],'account.move.line':['debit','credit','balance','write_date'],
  'res.currency.rate':['rate','name','write_date'],'mail.mail':['state','write_date'],
  'mail.message':['write_date'],'mail.activity':['write_date'],'ir.cron':['write_date'],
  ops['stock.quant']._fields['package_id'].comodel_name:['name','write_date']}
 if 'stock.valuation.layer' in ops:native_fields['stock.valuation.layer']=['quantity','value','write_date']
 def native_snapshot():
  return {name:ops[name].search([],order='id').read([f for f in names if f in ops[name]._fields]) for name,names in native_fields.items()}
 before_native=native_snapshot()
 env.flush_all();process=psutil.Process();rss_start=process.memory_info().rss;rss_peak=[rss_start];stop=threading.Event()
 def sample():
  while not stop.wait(.02):rss_peak[0]=max(rss_peak[0],process.memory_info().rss)
 sampler=threading.Thread(target=sample);sampler.start();queries=env.cr.sql_log_count;started=time.perf_counter()
 try:recommendation=scenario.action_generate_recommendations([dict(sale_line_id=partial.id,eligible_qty='1',reason='Restrict analytical review to one of two draft units; preserve the other source price')])
 finally:
  elapsed=time.perf_counter()-started;queries=env.cr.sql_log_count-queries
  rss_peak[0]=max(rss_peak[0],process.memory_info().rss);stop.set();sampler.join(5)
 assert recommendation.complete and len(recommendation.line_ids)==size,recommendation.controls
 assert sum(float(v.eligible_qty) for v in recommendation.line_ids)==size-1
 assert len(recommendation.line_ids.filtered(lambda v:bool(v.display_price_unit)))==size-1
 partial_result=recommendation.line_ids.filtered(lambda v:v.sale_line_id.id==partial.id)
 assert float(partial_result.values['unchanged_price_evidence']['comparison_qty'])==1
 assert float(partial_result.values['unchanged_price_evidence']['company_revenue'])==140
 assert confirmed.state=='sale' and quote.state=='draft'
 assert before_native==native_snapshot(),'Eligible native pricing changed an operational/master/communication record'
 values=dict(affected_lines=size,eligible_draft_lines=size-1,partial_draft_lines=1,protected_confirmed_lines=1,unchanged_native_models=len(native_fields),seconds=round(elapsed,3),sql_queries=queries,rss_start_bytes=rss_start,sampled_rss_peak_bytes=rss_peak[0],sampled_rss_growth_bytes=rss_peak[0]-rss_start,source_reference_counts=references,source_references=sum(references.values()),measurement_scope='warm same-process generation incl current-source validation, one native partial remainder and immutable publication; fixture setup and before/after native assertions excluded; RSS sampled every20ms')
 measurements.append(values);print('PR18_PERFORMANCE_'+str(size)+'='+json.dumps(values,sort_keys=True),flush=True)
 assert sum(references.values())==5*size
print('PR18_PERFORMANCE=PASS '+json.dumps(measurements,sort_keys=True),flush=True)
env.cr.rollback()
