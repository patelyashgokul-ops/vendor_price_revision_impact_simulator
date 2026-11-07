"""Independent financial control evidence; never approval or operational repair."""
import hashlib
from collections import defaultdict
from decimal import Decimal, localcontext
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from .import_intake import BATCH
from .import_validation import PREFIX as IMPORT_PREFIX
from .financial_exposure import FINANCE
from .profitability import HEADER as MARGIN, nullable
from .allocation_policy import authorized as cost_authorized
from .sales_exposure import authorized as sales_authorized
from .product_resolution import company_lock
from .structural_validation import digest
from .commercial_math import number, rounded
from .reconciliation_controls import Controls, VERSION, STATUSES, metric, readiness, independent_profit, independent_risk

PREFIX='vendor.price.revision.reconciliation.'
HEADER,CHECK,ISSUE,REVIEW=[PREFIX+s for s in ('run','check','exception','review')]
LIMIT=10000


def finance_allowed(batch):
    batch.ensure_one();batch.check_access('read')
    if not batch.env.su and (not batch.env.user.active or not batch.env.user.has_group(FINANCE)):
        raise AccessError('An authorized Finance Manager must initiate financial reconciliation.')
    if batch.state!='extracted' or batch.revision_id.state!='draft':
        raise UserError('Reconciliation requires an active extracted draft revision.')


def sum_known(rows,key):
    values=[nullable(row[key]) for row in rows]
    return str(sum((number(v) for v in values),Decimal(0))) if all(v is not None for v in values) else None


class Reconciler:
    def __init__(self,batch,margin_id):
        if type(margin_id) is not int or margin_id<=0: raise ValidationError('Select an exact profitability snapshot ID.')
        self.batch,self.env=batch,batch.env
        batch.check_access('read')
        self.m=self.env[MARGIN].browse(margin_id).exists()
        if not self.m:raise UserError('Profitability source is missing.')
        self.m.check_access('read')
        if self.m.batch_id!=batch:raise AccessError('Profitability source belongs to another revision batch.')
        self.f=self.m.financial_id;self.c=self.f.cost_id;self.a=self.c.allocation_id
        self.s=self.f.sales_id
        # An optional source created with integer0 can remain browse(0) in the
        # current Odoo20 relation cache until reload; it is not a source record.
        self.p=self.c.purchase_id if self.c.purchase_id.id else self.env['vendor.price.revision.purchase.snapshot']
        self.supply=self.a.supply_snapshot_id
        for rec in (self.f,self.c,self.a,self.s,self.p,self.supply):rec.check_access('read')
        self.company=batch.company_id
        cost_authorized(batch,self.a.warehouse_ids.ids,True)
        sales_authorized(self.env,self.company,self.a.warehouse_ids,self.s.order_ids)
        self.controls=Controls();self.scope=dict(margin_id=margin_id)
        self.currency=self.company.currency_id;self.money=str(self.currency.rounding)
        self.quantity_tolerance=str(Decimal(10) ** -self.env['decimal.precision'].precision_get('Product Unit'))

    def build(self):
        with localcontext() as ctx:
            ctx.prec=38
            return self._build()

    def _build(self):
        b=self.batch;m=self.m;c=self.controls
        self.sources=[v for v in (self.supply,self.a,self.s,self.p,self.c,self.f,m) if v]
        c.truth('COMPANY_REVISION_SCOPE','company_security','header',all(r.company_id==self.company for r in self.sources) and all(r.batch_id==b for r in (self.supply,self.a,self.p,self.c,self.f,m) if r) and self.s.batch_source_id==b.id)
        purchase_ok=(self.p.allocation_source_id==self.a.id and self.p.supply_snapshot_id==self.supply) if self.p else not any(v.allocation_type in ('protected_incoming_po','incoming_cost_unverified') for v in self.a.entry_ids)
        c.truth('EXACT_SNAPSHOT_LINKS','source_integrity','header',m.sales_id==self.s and m.allocation_id==self.a and self.s.allocation_source_id==self.a.id and purchase_ok)
        c.truth('SCENARIO_IDENTITY','scenario_consistency','header',m.scenario==self.f.scenario==self.a.scenario)
        self.stale_reason=None
        try:
            current=b.get_current_profitability(**m.scope)
            current_ok=current==m
        except (UserError,ValidationError) as exc:
            current_ok=False;self.stale_reason=str(exc)
        # AccessError/serialization/database errors must propagate, never be
        # converted into a readable cross-company diagnostic or successful run.
        c.record('UPSTREAM_CURRENT','snapshot_freshness','header','pass' if current_ok else 'stale',True,current_ok,
            severity='high',message=self.stale_reason or 'Exact PR08-15 source and policy freshness checked once for this run')
        self.source_checks()
        self.quantity_checks()
        self.cost_checks()
        self.financial_checks()
        self.margin_checks()
        self.completeness()
        self.outcome=readiness(c.checks,bool(self.a.demand_ids))
        for check in c.checks:
            if check['unit']=='currency':check.setdefault('currency_id',self.currency.id)
            source=check['source_key'];prefix,_,identity=source.partition(':')
            if identity.isdecimal():
                record={'margin':self.m.line_ids,'financial':self.f.line_ids,'cost':self.c.line_ids,
                    'demand':self.a.demand_ids,'bucket':self.supply.bucket_ids,'entry':self.a.entry_ids}.get(prefix)
                if record is not None:
                    row=record.filtered(lambda v:v.id==int(identity))
                    if row:
                        if check['unit']=='quantity':
                            unit=row.comparison_uom_id if 'comparison_uom_id' in row._fields else row.uom_id if 'uom_id' in row._fields else row.demand_id.uom_id
                            check['comparison_uom_id']=unit.id
                        if prefix=='margin':stable='sale_line:'+str(row.sale_line_id.id)
                        elif prefix=='bucket':stable=row.source_key
                        elif prefix=='demand':stable='sale_line:'+str(row.sale_line_id)
                        else:
                            entry=row if prefix=='entry' else row.allocation_entry_id
                            stable='sale_line:'+str(entry.demand_id.sale_line_id)+'|'+entry.capacity_key
                        check['check_key']=check['code']+'|'+stable
        check_keys=[v['check_key'] for v in c.checks]
        if len(check_keys)!=len(set(check_keys)):raise ValidationError('Reconciliation control identities must be unique.')
        if len(check_keys)>100000:raise UserError('Narrow the reconciliation scope; control limit exceeded.')
        self.provenance=dict(version=VERSION,source_versions=[dict(model=r._name,id=r.id,version=r.version,
            fingerprint=r.input_digest if r==self.supply else r.fingerprint) for r in self.sources],
            commercial_ids=b.row_ids.commercial_result_id.ids,validation_run=b.current_run_id.id,
            source_sha256=b.sha256_digest,risk_policy=m.provenance['risk_policy'],
            basis='Projected affected remaining product scope; not GL audit, approval, sign-off or application',
            stale_reason=self.stale_reason,metrics=self.metrics)
        self.fingerprint=digest(dict(version=VERSION,scope=self.scope,checks=c.checks,provenance=self.provenance,outcome=self.outcome))
        return self

    def source_checks(self):
        b=self.batch;c=self.controls
        attachment=b.attachment_id
        attachment.check_access('read')
        raw=attachment.raw.content if attachment else b''
        c.truth('SOURCE_FILE_SHA256','source_integrity','batch:'+str(b.id),bool(raw) and hashlib.sha256(raw).hexdigest()==b.sha256_digest and len(raw)==b.file_size)
        c.truth('SOURCE_REVISION_LINK','source_integrity','batch:'+str(b.id),b.evidence_id.import_batch_id==b and b.evidence_id.revision_id==b.revision_id and b.evidence_id in b.revision_id.evidence_ids)
        c.equation('SOURCE_ROW_COVERAGE','source_integrity','batch:'+str(b.id),b.extracted_row_count,len(b.row_ids),'0','count')
        c.truth('VALIDATION_RUN_CURRENT','source_integrity','batch:'+str(b.id),bool(b.current_run_id) and b.current_run_id.is_current)
        try:
            valid=b.get_commercially_valid_rows();valid_ids=set(valid.ids)
            c.record('COMMERCIAL_CURRENT','commercial_pricing','batch:'+str(b.id),'pass')
        except (UserError,ValidationError):
            valid_ids=set();c.record('COMMERCIAL_CURRENT','commercial_pricing','batch:'+str(b.id),'stale',severity='high')
        self.valid_ids=valid_ids
        for row in b.row_ids:
            key='row:'+str(row.id)
            excluded=row.excluded
            if excluded:
                c.record('SOURCE_ROW_DISPOSITION','source_integrity',key,'not_applicable' if row.correction_ids else 'blocked',observed=row.effective_values,message='Explicit upstream exclusion with retained reason/evidence required; never silently omitted')
                continue
            result=row.commercial_result_id
            c.record('SOURCE_ROW_DISPOSITION','product_identity',key,'pass' if row.id in valid_ids else 'blocked',True,row.id in valid_ids,severity='high',message='Every nonexcluded source row needs current verified exact product/commercial evidence')
            if result:
                snap=result.snapshot
                product=snap.get('proposal',{}).get('product_id')
                product_record=self.env['product.product'].browse(product).exists() if product else self.env['product.product']
                product_record.check_access('read')
                c.truth('EXACT_VARIANT_VENDOR','product_identity',key,bool(product_record) and row.resolved_product_id==product_record and product_record.company_id in (self.company,self.env['res.company']),
                    message='Exact commercial variant must correspond to affected scope; no SKU/name inference')
        # All source rows are represented. Product rows without selected demand
        # remain source-complete but do not acquire fictional financial amounts.

    def quantity_checks(self):
        c=self.controls;sup=self.supply
        c.unique('UNIQUE_SUPPLY_BUCKET','supply_allocation','supply',sup.bucket_ids.mapped('source_key'))
        c.unique('UNIQUE_PHYSICAL_QUANT','supply_allocation','supply',[v.evidence['quant']['id'] for v in sup.bucket_ids if v.source_key.startswith('quant:')])
        c.unique('UNIQUE_PO_REMAINDER','supply_allocation','supply',[v.evidence['line']['id'] for v in sup.bucket_ids if v.source_key.startswith('po_line:')])
        for bucket in sup.bucket_ids:
            key='bucket:'+str(bucket.id);tol=self.quantity_tolerance
            if bucket.source_key.startswith('quant:'):
                c.equation('STOCK_PHYSICAL_SPLIT','quantity_integrity',key,nullable(bucket.physical),str(number(bucket.reserved)+number(bucket.unreserved)) if bucket.reserved and bucket.unreserved else None,tol,'quantity')
                known=bucket.eligible_free and bucket.unreserved
                c.record('ELIGIBLE_FREE_CAPACITY','quantity_integrity',key,'pass' if known and 0<=number(bucket.eligible_free)<=number(bucket.unreserved) else 'blocked' if not known else 'fail',
                    expected=nullable(bucket.unreserved),observed=nullable(bucket.eligible_free),tolerance=tol,unit='quantity')
            if bucket.source_key.startswith('po_line:'):
                e=bucket.evidence;ordered=e.get('ordered');received=e.get('gross_received');cancelled=e.get('cancelled')
                expected=str(max(Decimal(0),number(ordered)-number(received)-number(cancelled))) if all(v is not None for v in (ordered,received,cancelled)) else None
                c.equation('PO_SUPPLIER_UNRECEIVED','purchase_commitment',key,expected,nullable(bucket.incoming),tol,'quantity')
                legs=e.get('supplier_boundary',[])
                c.unique('UNIQUE_EXTERNAL_RECEIPT_LEG','supply_allocation',key,[v['id'] for v in legs])
        a=self.a
        c.unique('UNIQUE_DEMAND_LINE','quantity_integrity','allocation',a.demand_ids.mapped('sale_line_id'))
        c.unique('UNIQUE_ALLOCATION_ENTRY','supply_allocation','allocation',[(v.demand_id.id,v.capacity_key) for v in a.entry_ids])
        used=defaultdict(Decimal)
        for d in a.demand_ids:
            key='demand:'+str(d.id);tol=self.quantity_tolerance
            outstanding=nullable(d.outstanding)
            c.equation('DEMAND_ORDERED_DELIVERED','quantity_integrity',key,str(max(Decimal(0),number(d.ordered)-number(d.delivered))) if d.ordered and d.delivered else None,outstanding,tol,'quantity')
            c.equation('ALLOCATION_QUANTITY_MISMATCH','quantity_integrity',key,outstanding,sum_known(d.entry_ids,'quantity'),tol,'quantity')
            c.record('UNRESOLVED_QUANTITY','financial_completeness',key,'pass' if d.status!='unresolved' and d.unresolved and number(d.unresolved)==0 else 'blocked',severity='high',message='Unresolved demand is never balanced into procurement or counted complete')
            for entry in d.entry_ids:
                if entry.capacity_key in (a.source_capacities or {}):
                    cap=a.source_capacities[entry.capacity_key];used[entry.capacity_key]+=number(entry.quantity)
                    owners=cap.get('linked_sale_line_ids',[])
                    c.truth('CAPACITY_DIMENSIONS_OWNER','supply_allocation','entry:'+str(entry.id),cap['product_id']==d.product_id and cap['warehouse_id']==d.warehouse_id.id and (not owners or d.sale_line_id in owners))
                elif entry.allocation_type not in ('new_procurement_requirement','unresolved'):
                    c.record('CAPACITY_SOURCE_MISSING','supply_allocation','entry:'+str(entry.id),'fail')
        for key,cap in (a.source_capacities or {}).items():
            amount=used[key]
            c.record('SUPPLY_CAPACITY_EXCEEDED','supply_allocation',key,'pass' if amount<=number(cap['initial']) else 'fail',cap['initial'],str(amount),unit='quantity')
            c.equation('CAPACITY_ALLOCATED_TOTAL','supply_allocation',key,cap['allocated'],str(amount),'0','quantity')
            c.equation('CAPACITY_REMAINDER','supply_allocation',key,cap['initial'],str(number(cap['allocated'])+number(cap['remaining'])),'0','quantity')
        self.cap_totals=used

    def cost_checks(self):
        controls=self.controls;c=self.c
        controls.unique('UNIQUE_COST_ALLOCATION','cost_attribution','cost',c.line_ids.allocation_entry_id.ids)
        controls.truth('COST_ENTRY_COVERAGE','cost_attribution','cost',set(c.line_ids.allocation_entry_id.ids)==set(self.a.entry_ids.ids))
        for line in c.line_ids:
            key='cost:'+str(line.id);e=line.allocation_entry_id;d=e.demand_id
            controls.equation('COST_QUANTITY','cost_attribution',key,e.quantity,line.quantity,self.quantity_tolerance,'quantity')
            controls.truth('COST_VARIANT_UOM_CURRENCY','cost_attribution',key,line.product_id==d.product_id and line.comparison_uom_id==d.uom_id and line.currency_id==self.currency)
            controls.equation('COST_SEGMENTS_TOTAL','cost_attribution',key,line.quantity,str(sum((number(v['quantity']) for v in line.segments),Decimal(0))),self.quantity_tolerance,'quantity')
            controls.unique('UNIQUE_COST_SEGMENT','cost_attribution',key,[(v.get('capacity_key'),v.get('move_id'),v.get('lot_id')) for v in line.segments])
            unit=nullable(line.unit_cost)
            controls.equation('COST_UNIT_EXTENSION','cost_attribution',key,str(number(line.quantity)*number(unit)) if unit is not None else None,nullable(line.reference_value),self.money)
            if e.allocation_type in ('protected_incoming_po','incoming_cost_unverified'):
                poid=int(e.supply_bucket_id.source_key.split(':')[1]);rows=self.p.line_ids.filtered(lambda v:v.po_line_id==poid)
                protected=len(rows)==1 and rows.protection_status=='protected_verified' and rows.amendment_status not in ('amendment_pending','disputed') and rows.commitment_type=='confirmed'
                controls.record('PO_PROTECTION_UNVERIFIED','purchase_commitment',key,'pass' if protected else 'blocked',True,protected,severity='high')
                if protected:controls.equation('PROTECTED_PO_COST_BASIS','purchase_commitment',key,nullable(rows.company_unit_price),unit,self.money)

    def financial_checks(self):
        f=self.f;c=self.controls
        c.unique('UNIQUE_FINANCIAL_CONTRIBUTION','financial_exposure','financial',f.line_ids.allocation_entry_id.ids)
        c.truth('FINANCIAL_ENTRY_COVERAGE','financial_exposure','financial',set(f.line_ids.allocation_entry_id.ids)==set(self.a.entry_ids.ids))
        commercial={row.commercial_result_id.id:row.commercial_result_id.snapshot for row in self.batch.row_ids if row.commercial_result_id}
        for line in f.line_ids:
            key='financial:'+str(line.id);cost=line.cost_line_id;e=line.allocation_entry_id;d=e.demand_id
            c.truth('FINANCIAL_EXACT_COST_SOURCE','financial_exposure',key,cost.snapshot_id==self.c and cost.allocation_entry_id==e and line.product_id==d.product_id and line.sale_line_id==d.sale_line_id and line.comparison_uom_id==d.uom_id and line.currency_id==self.currency and line.vendor_id==self.batch.vendor_id.id)
            c.equation('FINANCIAL_QUANTITY','financial_exposure',key,e.quantity,line.quantity,self.quantity_tolerance,'quantity')
            b,r=nullable(line.baseline_unit_cost),nullable(line.revised_unit_cost)
            for stage,unit in (('baseline',b),('revised',r)):
                c.equation('FINANCIAL_'+stage.upper()+'_EXTENSION','financial_exposure',key,str(number(unit)*number(line.quantity)) if unit is not None else None,nullable(line[stage+'_extended_cost']),self.money)
            delta=str((number(r)-number(b))*number(line.quantity)) if b is not None and r is not None else '0' if line.verified_delta else None
            c.equation('SIGNED_INCREMENTAL_COST','financial_exposure',key,delta,nullable(line.incremental_extended_cost),self.money)
            if e.allocation_type in ('existing_reserved_for_demand','eligible_free_stock','protected_incoming_po') or (e.allocation_type=='incoming_cost_unverified' and cost.confidence=='verified_commercial_basis'):
                for stage,unit in (('BASELINE',b),('REVISED',r)):
                    c.equation('UNCHANGED_'+stage+'_SOURCE_COST','financial_exposure',key,nullable(cost.unit_cost),unit,self.money)
            if e.allocation_type=='new_procurement_requirement':
                basis=line.evidence.get('pricing',{});new=cost.evidence;result=commercial.get(new.get('commercial_result_id'))
                before=basis.get('timing')=='before_revision_effective_date'
                c.record('PROCUREMENT_APPLICABILITY','commercial_pricing',key,'pass' if result and basis.get('planning_date') and (before or cost.unit_cost) else 'blocked',severity='high')
                if result:
                    c.truth('COMMERCIAL_RESULT_EXACT','commercial_pricing',key,result['proposal']['product_id']==line.product_id and (before or new.get('commercial_result_id')==basis.get('commercial_result_id')))
                    proposals=[v['proposal'] for v in commercial.values() if v['proposal']['product_id']==line.product_id and v['proposal']['comparison_uom_id']==line.comparison_uom_id.id and v['proposal']['effective_date']<=(basis.get('planning_date') or '') and (not v['proposal'].get('end_date') or v['proposal']['end_date']>=basis['planning_date']) and number(v['proposal']['normalized_min_qty'])<=number(line.quantity)]
                    if not before:
                        selected=result['proposal']
                        eligible=bool(proposals) and number(selected['normalized_min_qty'])==max(number(v['normalized_min_qty']) for v in proposals)
                        c.truth('APPLICABLE_MOQ_DATE_TIER','commercial_pricing',key,eligible)
                        rate=new.get('fx',{}).get('rate')
                        c.equation('NEW_PROPOSAL_FX_CONVERSION','commercial_pricing',key,str(number(selected['net_comparable'])*number(rate)) if rate is not None else None,nullable(cost.unit_cost),self.money)
                if b is not None:
                    old=basis.get('applicable_old_tier',{}).get('net_comparable');fx=basis.get('old_fx',{}).get('rate')
                    c.equation('OLD_TIER_FX_CONVERSION','commercial_pricing',key,str(number(old)*number(fx)) if old is not None and fx is not None else None,b,self.money)
                if not before:c.equation('NEW_PROCUREMENT_COST_SOURCE','commercial_pricing',key,nullable(cost.unit_cost),r,self.money)
            price=nullable(line.supplier_price_component);fx=nullable(line.fx_component)
            if price is not None and fx is not None:
                c.equation('PRICE_FX_DECOMPOSITION','financial_exposure',key,line.incremental_extended_cost,str(number(price)+number(fx)),self.money)
        for header,field in (('baseline_total','baseline_extended_cost'),('revised_total','revised_extended_cost'),('incremental_total','incremental_extended_cost')):
            c.equation('FINANCIAL_TOTAL_'+header.upper(),'financial_exposure','header',sum_known(f.line_ids,field),nullable(f[header]),self.money)
        c.equation('TOTAL_REVISED_MINUS_BASELINE','financial_exposure','header',str(number(f.revised_total)-number(f.baseline_total)) if f.revised_total and f.baseline_total else None,nullable(f.incremental_total),self.money)

    def check_profit(self,record,values,policy,protections,source):
        c=self.controls
        current=self.env['vendor.price.revision.margin.policy'].browse(policy['id']).exists() if policy else self.env['vendor.price.revision.margin.policy']
        c.record('RISK_POLICY_THRESHOLD_BASIS','risk_classification',source,'pass' if current and str(current.minimum_margin_percent)==policy['minimum'] and str(current.target_margin_percent)==policy['target'] and current.company_id==self.company and current.config_id.id==self.m.provenance['risk_policy']['id'] and current.erosion_enabled==policy['erosion_enabled'] and str(current.erosion_warning_points)==policy['erosion_points'] and current.negative_profit_critical==policy['negative_profit_critical'] else 'blocked',severity='high')
        for key,expected in values.items():
            unit='percentage_points' if key=='margin_erosion_points' else 'percent' if 'percent' in key else 'currency'
            tol='0.000000000001' if unit!='currency' else self.money
            c.equation('PROFIT_'+key.upper(),'margin_profitability',source,expected,nullable(record[key]),tol,unit)
        rules=self.m.provenance['risk_policy']['rules']
        risk,codes=independent_risk(values,policy,rules,record.complete,protections)
        for key,value in risk.items():c.truth('RISK_'+key.upper(),'risk_classification',source,record[key]==value,value,record[key])
        actual=sorted(set((v['code'],v['stage']) for v in (record.risk_reasons or [])))
        c.truth('RISK_REASON_SET','risk_classification',source,actual==codes,codes,actual)

    def margin_checks(self):
        m=self.m;c=self.controls
        c.unique('UNIQUE_REVENUE_SALES_LINE','sales_revenue','sales',self.s.line_ids.sale_line_id.ids)
        c.unique('UNIQUE_MARGIN_SALES_LINE','margin_profitability','margin',m.line_ids.sale_line_id.ids)
        c.truth('MARGIN_SALES_COVERAGE','margin_profitability','margin',set(m.line_ids.sales_line_id.ids)==set(self.s.line_ids.ids))
        consumed=[]
        self.line_values={}
        for line in m.line_ids:
            source=line.sales_line_id;key='margin:'+str(line.id)
            rows=self.f.line_ids.filtered(lambda v:v.sale_line_id==source.sale_line_id.id)
            consumed.extend(line.source_financial_line_ids)
            c.truth('MARGIN_CONTRIBUTION_SET','margin_profitability',key,set(line.source_financial_line_ids)==set(rows.ids) and len(line.source_financial_line_ids)==len(rows))
            c.truth('MARGIN_CUSTOMER_VARIANT_IDENTITY','margin_profitability',key,line.sale_line_id==source.sale_line_id and line.customer_id==source.customer_id and line.product_id==source.product_id and line.currency_id==source.company_currency_id)
            q=nullable(source.outstanding_qty);unit=nullable(source.net_sales_unit_price)
            expected=rounded(number(q)*number(unit),source.sales_currency_id.rounding) if q is not None and unit is not None and source.valuation_status=='verified' else None
            c.equation('SALES_NET_UNIT_EXTENSION','sales_revenue',key,expected,nullable(source.outstanding_sales_value),str(source.sales_currency_id.rounding))
            c.checks[-1]['currency_id']=source.sales_currency_id.id
            rate=source.fx_evidence.get('rate')
            revenue=rounded(number(expected)*number(rate),self.money) if expected is not None and rate is not None else None
            c.equation('SALES_COMPANY_FX','sales_revenue',key,revenue,nullable(source.company_sales_value),self.money)
            c.equation('REVENUE_SOURCE_MATCH','sales_revenue',key,nullable(source.company_sales_value),nullable(line.net_revenue),self.money)
            values=independent_profit(nullable(source.company_sales_value),sum_known(rows,'baseline_extended_cost'),sum_known(rows,'revised_extended_cost'))
            self.line_values[line.id]=values
            self.check_profit(line,values,line.policy_evidence,[line.price_protection],key)
            c.equation('PROFIT_CHANGE_COST_DELTA','margin_profitability',key,str(-number(sum_known(rows,'incremental_extended_cost'))) if sum_known(rows,'incremental_extended_cost') is not None else None,nullable(line.gross_profit_change),self.money)
        c.unique('UNIQUE_CONSUMED_FINANCIAL_LINE','margin_profitability','margin',consumed)
        c.truth('ALL_FINANCIAL_LINES_CONSUMED','margin_profitability','margin',set(consumed)==set(self.f.line_ids.ids))
        seen=[]
        for aggregate in m.aggregate_ids:
            key='aggregate:'+str(aggregate.id);dimension=aggregate.dimension
            field={'order':'sale_order_id','product':'product_id','customer':'customer_id'}.get(dimension)
            rows=m.line_ids.filtered(lambda v:v.demand_type==aggregate.demand_type and (v[field].id==aggregate.source_id if field else self.company.id==aggregate.source_id))
            seen.append((dimension,aggregate.source_id,aggregate.demand_type))
            c.equation('AGGREGATE_LINE_COUNT','margin_profitability',key,len(rows),aggregate.line_count,'0','count')
            values=independent_profit(sum_known(rows,'net_revenue'),sum_known(rows,'baseline_cost'),sum_known(rows,'revised_cost'))
            self.check_profit(aggregate,values,aggregate.policy_evidence,rows.mapped('price_protection'),key)
        c.unique('UNIQUE_AGGREGATE_DIMENSION','margin_profitability','margin',seen)
        expected_groups=set()
        for line in m.line_ids:
            for dim,identity in (('company',self.company.id),('order',line.sale_order_id.id),('product',line.product_id.id),('customer',line.customer_id.id)):
                expected_groups.add((dim,identity,line.demand_type))
        c.truth('AGGREGATE_SCOPE_COVERAGE','margin_profitability','margin',set(seen)==expected_groups)
        if m.line_ids:
            self.check_profit(m,independent_profit(sum_known(m.line_ids,'net_revenue'),sum_known(m.line_ids,'baseline_cost'),sum_known(m.line_ids,'revised_cost')),m.policy_evidence,m.line_ids.mapped('price_protection'),'margin_header')
        else:
            c.record('NO_ELIGIBLE_DEMAND','financial_completeness','margin_header','not_applicable',message='No selected affected demand: no margin/risk percentage assessment and no financial review readiness')
        if m.scenario!='confirmed_baseline':
            c.truth('CONDITIONAL_EXACT_BASELINE','scenario_consistency','margin',bool(m.confirmed_id) and m.confirmed_id.financial_id==self.f.confirmed_id and self.a.baseline_id==self.f.confirmed_id.cost_id.allocation_id)
            expected=str(number(m.revised_gross_profit)-number(m.confirmed_id.revised_gross_profit)) if m.complete and m.confirmed_id.complete else None
            c.equation('CONDITIONAL_INCREMENTAL_PROFIT','scenario_consistency','margin',expected,nullable(m.conditional_incremental_profit),self.money)
        c.truth('ALTERNATIVES_NONADDITIVE','scenario_consistency','margin',m.provenance.get('alternatives_additive') is False and self.f.reconciliation.get('alternatives_additive') is False)

    def completeness(self):
        c=self.controls;m=self.m
        groups=defaultdict(list)
        for line in self.c.line_ids:groups[(line.product_id,line.comparison_uom_id.id)].append(line)
        quantities=[]
        for (pid,uid),rows in sorted(groups.items()):
            quantities.append(dict(product_id=pid,uom_id=uid,**metric(sum((number(v.quantity) for v in rows if v.unit_cost),Decimal(0)),sum((number(v.quantity) for v in rows),Decimal(0)),'Known-cost quantity in this exact product/UoM only')))
        excluded=self.batch.row_ids.filtered('excluded')
        self.metrics=dict(source_rows=metric(len(self.valid_ids)+len(excluded),len(self.batch.row_ids),'Current verified or explicitly excluded dispositions / all imported rows'),
            commercial_rows=metric(len(self.valid_ids),len(self.batch.row_ids)-len(excluded),'Current commercially valid rows / eligible nonexcluded source rows'),
            excluded_source_rows=[dict(row_id=row.id,correction_ids=row.correction_ids.ids) for row in excluded],
            demand_lines=metric(sum(d.status!='unresolved' for d in self.a.demand_ids),len(self.a.demand_ids),'Resolved exact demand lines / selected demand lines'),
            cost_lines=metric(sum(bool(v.unit_cost) for v in self.c.line_ids),len(self.c.line_ids),'Cost-known allocation entries / all entries'),
            revenue_lines=metric(sum(bool(v.company_sales_value) for v in self.s.line_ids),len(self.s.line_ids),'Company-revenue-known PR11 lines / all selected sales lines'),
            margin_lines=metric(sum(v.complete for v in m.line_ids),len(m.line_ids),'Numerically complete PR15 lines / all selected sales lines'),quantity_cost_coverage=quantities)
        c.record('NUMERICAL_COMPLETENESS','financial_completeness','header','pass' if m.complete and self.f.cost_complete else 'blocked',True,bool(m.complete and self.f.cost_complete),severity='high')
        # Projection-readiness is explicitly governed by the existing dated PR04
        # configuration; default strict mode never upgrades unknown/estimated cost.
        policy=self.env['vendor.price.revision.config'].browse(m.provenance['risk_policy']['id']).exists()
        policy.check_access('read')
        self.projection_policy=policy.reconciliation_basis_policy if policy else 'strict_verified'
        basis_ok=m.state=='fully_verified' or (self.projection_policy=='documented_projection' and m.state in ('estimated','scenario_only') and m.complete)
        c.record('FINANCIAL_BASIS_READINESS','financial_completeness','header','pass' if basis_ok else 'blocked',
            expected=self.projection_policy,observed=m.state,severity='high',message='Documented projected review is permitted only by the dated governed company policy; not approval or recognized accounting cost')
        self.metrics['readiness_basis_policy']=self.projection_policy
        self.metrics['checks']=metric(sum(v['status']=='pass' for v in c.checks),sum(v['status']!='not_applicable' for v in c.checks),'PASS / all applicable executed and required controls; blocked/stale/not-run never pass')


class ReconciliationPolicy(models.Model):
    _inherit='vendor.price.revision.config'
    reconciliation_basis_policy=fields.Selection([('strict_verified','Verified cost basis only'),('documented_projection','Permit documented complete projected cost basis for financial review')],
        default='strict_verified',required=True,help='Readiness is evidence for review only; never approval, price application or accounting sign-off.')


class ReconciliationRun(models.Model):
    _name=HEADER
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Immutable Financial Reconciliation Evidence (not approval)'
    _order='id desc'
    _unique=models.Constraint('UNIQUE(batch_id,scope_key,version)','One reconciliation evidence version per exact source scope.')
    name=fields.Char(required=True)
    margin_id=fields.Many2one(MARGIN,required=True,ondelete='restrict')
    warehouse_ids=fields.Many2many('stock.warehouse')
    order_ids=fields.Many2many('sale.order')
    currency_id=fields.Many2one('res.currency',required=True)
    scenario=fields.Char(required=True,index=True)
    scope=fields.Json(required=True)
    scope_key=fields.Char(required=True,index=True)
    fingerprint=fields.Char(required=True)
    version=fields.Integer(required=True)
    previous_id=fields.Many2one(HEADER,ondelete='restrict')
    collected_at=fields.Datetime(required=True)
    collected_by=fields.Many2one('res.users',required=True)
    policy_version=fields.Char(required=True)
    state=fields.Char(required=True,index=True)
    readiness=fields.Char(required=True,index=True,string='Stored readiness (check current sources)')
    provenance=fields.Json(required=True)
    metrics=fields.Json(required=True)
    check_counts=fields.Json(required=True)
    critical_exception_count=fields.Integer()
    high_exception_count=fields.Integer()
    check_ids=fields.One2many(CHECK,'snapshot_id')
    exception_ids=fields.One2many(ISSUE,'snapshot_id')
    freshness=fields.Selection([('current','Current'),('stale','Stale / review required')],compute='_freshness')
    current_readiness=fields.Char(compute='_freshness',string='Current readiness (live source check)')

    def _freshness(self):
        cache={}
        for rec in self:
            key=(rec.batch_id.id,rec.scope_key)
            if key not in cache:
                try:
                    e=Reconciler(rec.batch_id,**rec.scope).build()
                    latest=self.search([('batch_id','=',rec.batch_id.id),('scope_key','=',rec.scope_key)],limit=1)
                    cache[key]=(e.fingerprint,latest.id,e.outcome['state'])
                except (AccessError,UserError,ValidationError):cache[key]=(None,0,'stale')
            fp,identity,state=cache[key]
            rec.freshness='current' if (fp,identity)==(rec.fingerprint,rec.id) and state!='stale' else 'stale'
            rec.current_readiness=rec.readiness if rec.freshness=='current' else 'not_ready'

    def action_check_current(self):
        self.ensure_one();self.check_access('read')
        if self.freshness!='current':raise UserError('Historical reconciliation is stale. Revalidate sources and run again; stored readiness grants no authority.')
        return dict(type='ir.actions.client',tag='display_notification',params=dict(message=self.current_readiness+'; not management approval',type='info'))


class ReconciliationCheck(models.Model):
    _name=CHECK
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Named Independent Reconciliation Check'
    _unique=models.Constraint('UNIQUE(snapshot_id,check_key)','A control/source pair contributes once per run.')
    snapshot_id=fields.Many2one(HEADER,required=True,ondelete='restrict',index=True)
    check_key=fields.Char(required=True,index=True)
    code=fields.Char(required=True,index=True)
    category=fields.Char(required=True,index=True)
    source_key=fields.Char(required=True)
    status=fields.Selection([(s,s.replace('_',' ').title()) for s in STATUSES],required=True,index=True)
    required=fields.Boolean(default=True)
    severity=fields.Char(required=True)
    unit=fields.Char(required=True)
    numeric_known=fields.Boolean()
    expected_numeric=fields.Float(digits=(32,12))
    observed_numeric=fields.Float(digits=(32,12))
    difference=fields.Float(digits=(32,12))
    tolerance=fields.Float(digits=(32,12))
    currency_id=fields.Many2one('res.currency',string='Exact comparison currency')
    comparison_uom_id=fields.Many2one('uom.uom',string='Exact comparison UoM')
    values=fields.Json(required=True,help='Exact decimal/categorical evidence; numeric_known distinguishes missing numeric values from zero.')
    message=fields.Text(required=True)

    def action_open_source(self):
        self.ensure_one();self.check_access('read')
        run=self.snapshot_id;m=run.margin_id
        prefix,_,value=self.source_key.partition(':')
        collections={'margin':m.line_ids,'financial':m.financial_id.line_ids,'cost':m.financial_id.cost_id.line_ids,
            'demand':m.allocation_id.demand_ids,'bucket':m.allocation_id.supply_snapshot_id.bucket_ids,'entry':m.allocation_id.entry_ids,
            'aggregate':m.aggregate_ids}
        records=collections.get(prefix)
        source=records.filtered(lambda v:v.id==int(value)) if records is not None and value.isdecimal() else m
        if not source:raise UserError('The exact recorded source is not available within this authorized run.')
        source.check_access('read')
        # Only exact retained analytical sources; native operational drilldown
        # remains in their existing native-permission actions.
        return dict(type='ir.actions.act_window',res_model=source._name,res_id=source.id,view_mode='form')


class ReconciliationException(models.Model):
    _name=ISSUE
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Immutable Financial Exception with Append-Only Review History'
    snapshot_id=fields.Many2one(HEADER,required=True,ondelete='restrict',index=True)
    check_id=fields.Many2one(CHECK,required=True,ondelete='restrict')
    code=fields.Char(required=True,index=True)
    severity=fields.Char(required=True,index=True)
    source_key=fields.Char(required=True)
    description=fields.Text(required=True)
    resolution_action=fields.Text(required=True)
    assigned_group_id=fields.Many2one('res.groups',required=True)
    review_ids=fields.One2many(REVIEW,'exception_id')
    status=fields.Char(compute='_review_state',search='_search_review_status')
    assigned_user_id=fields.Many2one('res.users',compute='_review_state',search='_search_owner')

    def _search_review_status(self,operator,value):
        if operator not in ('=','!=','in','not in'):raise UserError('Use an equality or membership review-state filter.')
        rows=self.search([],limit=1001)
        if len(rows)>1000:raise UserError('Narrow exception history before filtering review events.')
        values=value if operator in ('in','not in') else [value]
        ids=rows.filtered(lambda v:v.status in values).ids
        return [('id','not in' if operator in ('!=','not in') else 'in',ids)]

    def _search_owner(self,operator,value):
        if operator not in ('=','!='):raise UserError('Use an explicit owner equality filter.')
        rows=self.search([],limit=1001)
        if len(rows)>1000:raise UserError('Narrow exception history before filtering owners.')
        ids=rows.filtered(lambda v:(v.assigned_user_id.id or False)==value).ids
        return [('id','in' if operator=='=' else 'not in',ids)]

    @api.depends('review_ids','review_ids.event','review_ids.owner_id')
    def _review_state(self):
        for rec in self:
            events=rec.review_ids.sorted('id')
            rec.status=events[-1].event if events else 'open'
            assigned=events.filtered('owner_id')
            rec.assigned_user_id=assigned[-1].owner_id if assigned else False

    def action_record_review(self,event,reason,evidence,owner_id=0,verification_run_id=0):
        self.ensure_one();self.check_access('read')
        env=self.env;batch=self.batch_id
        allowed=env.su or env.user.has_group(FINANCE) or env.user.has_group('vendor_price_revision_impact_simulator.group_vpr_purchase_manager') or env.user.has_group('vendor_price_revision_impact_simulator.group_vpr_sales_manager')
        if not env.user.active or not allowed:raise AccessError('A scoped Finance, Purchase or Sales Manager must review exceptions; auditors are read-only.')
        if event not in ('assigned','in_review','revalidation_required','closed_verified','reopened') or not str(reason or '').strip() or not str(evidence or '').strip():
            raise ValidationError('Choose a supported review action and provide reason and traceable evidence. Waiving required integrity controls is not supported.')
        if type(owner_id) is not int or owner_id<0 or type(verification_run_id) is not int or verification_run_id<0:raise ValidationError('Owner and verification source IDs must be exact integers.')
        owner=env['res.users'].browse(owner_id).exists()
        if owner_id and (not owner or not owner.active or owner.share or self.company_id not in owner.company_ids):raise AccessError('Owner must be an active internal user of the exception company. Assignment grants no data access.')
        if event=='assigned' and not owner:raise ValidationError('Assignment requires an explicit owner.')
        company_lock(env,self.company_id);batch._lock()
        # Review notes never rewrite check results or readiness. Closure requires
        # a current independently executed matching control PASS in a later run.
        run=env[HEADER].browse(verification_run_id).exists()
        if event=='closed_verified':
            if not run:raise ValidationError('A current revalidation run with actual matching PASS is required.')
            run.check_access('read')
            if run.batch_id!=batch or run.scenario!=self.snapshot_id.scenario or run.id<=self.snapshot_id.id:raise ValidationError('Closure requires a later run for this exact batch/scenario.')
            current=batch.get_current_reconciliation(**run.scope)
            matching=current.check_ids.filtered(lambda v:v.check_key==self.check_id.check_key)
            if len(matching)!=1 or matching.status!='pass':raise UserError('The corresponding independent control has not passed current revalidation.')
        previous=env[REVIEW].search([('exception_id','=',self.id)],order='id desc',limit=1)
        if previous and (previous.event,previous.reason,previous.evidence,previous.owner_id.id,previous.verification_run_id.id)==(event,reason.strip(),evidence.strip(),owner_id,verification_run_id):return previous
        return env[REVIEW]._record(dict(batch_id=batch.id,snapshot_id=self.snapshot_id.id,exception_id=self.id,event=event,
            reason=reason.strip(),evidence=evidence.strip(),owner_id=owner_id,verification_run_id=verification_run_id,
            actor_id=env.uid,recorded_at=fields.Datetime.now()))

    def action_open_review(self):
        self.ensure_one();self.check_access('read')
        return dict(type='ir.actions.act_window',res_model=PREFIX+'review.wizard',view_mode='form',target='new',context=dict(default_exception_id=self.id,default_batch_id=self.batch_id.id))


class ReconciliationReview(models.Model):
    _name=REVIEW
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Append-Only Financial Exception Review Event (not resolution override)'
    snapshot_id=fields.Many2one(HEADER,required=True,ondelete='restrict')
    exception_id=fields.Many2one(ISSUE,required=True,ondelete='restrict')
    event=fields.Char(required=True)
    reason=fields.Text(required=True)
    evidence=fields.Text(required=True)
    owner_id=fields.Many2one('res.users')
    verification_run_id=fields.Many2one(HEADER,ondelete='restrict')
    actor_id=fields.Many2one('res.users',required=True)
    recorded_at=fields.Datetime(required=True)


class BatchReconciliation(models.Model):
    _inherit=BATCH

    def action_run_reconciliation(self,margin_id):
        self.ensure_one();finance_allowed(self)
        e=Reconciler(self,margin_id)
        company_lock(self.env,self.company_id);self._lock()
        with self.env.cr.savepoint():
            e.build();key=digest(e.scope)
            previous=self.env[HEADER].search([('batch_id','=',self.id),('scope_key','=',key)],limit=1)
            if previous and previous.fingerprint==e.fingerprint:return previous
            failures=[v for v in e.controls.checks if v['status'] not in ('pass','not_applicable')]
            result=self.env[HEADER]._record(dict(batch_id=self.id,name='Financial reconciliation / '+str(margin_id),margin_id=margin_id,
                warehouse_ids=[(6,0,e.a.warehouse_ids.ids)],order_ids=[(6,0,e.s.order_ids.ids)],currency_id=e.currency.id,
                scenario=e.m.scenario,scope=e.scope,scope_key=key,fingerprint=e.fingerprint,version=previous.version+1 if previous else 1,
                previous_id=previous.id,collected_at=fields.Datetime.now(),collected_by=self.env.uid,policy_version=VERSION,
                provenance=e.provenance,metrics=e.metrics,critical_exception_count=sum(v['severity']=='critical' for v in failures),
                high_exception_count=sum(v['severity']=='high' for v in failures),**e.outcome))
            for row in e.controls.checks:
                check=self.env[CHECK]._record(dict(row,batch_id=self.id,snapshot_id=result.id))
                if row['status'] not in ('pass','not_applicable'):
                    group='group_vpr_purchase_manager' if row['category'] in ('product_identity','commercial_pricing','purchase_commitment') else 'group_vpr_sales_manager' if row['category']=='sales_revenue' else 'group_vpr_finance_manager'
                    self.env[ISSUE]._record(dict(batch_id=self.id,snapshot_id=result.id,check_id=check.id,code=row['code'],severity=row['severity'],source_key=row['source_key'],
                        description=row['message'],assigned_group_id=self.env.ref('vendor_price_revision_impact_simulator.'+group).id,
                        resolution_action='Review exact source evidence with its authorized owner; correct through the standard source process, rebuild affected upstream snapshots, then rerun this control. A note cannot create PASS or readiness.'))
            return result

    def get_current_reconciliation(self,margin_id):
        self.ensure_one();e=Reconciler(self,margin_id).build()
        result=self.env[HEADER].search([('batch_id','=',self.id),('scope_key','=',digest(e.scope))],limit=1)
        if not result or result.fingerprint!=e.fingerprint or result.state=='stale':raise UserError('Reconciliation missing/stale. Revalidate sources and run again before using readiness evidence.')
        return result


class MarginReconciliationAction(models.Model):
    _inherit=MARGIN
    def action_open_reconciliation(self):
        self.ensure_one();self.check_access('read');finance_allowed(self.batch_id)
        return dict(type='ir.actions.act_window',res_model=PREFIX+'wizard',view_mode='form',target='new',context=dict(default_batch_id=self.batch_id.id,default_margin_source_id=self.id))


class ReconciliationWizard(models.TransientModel):
    _name=PREFIX+'wizard'
    _inherit='vendor.price.revision.purchase.wizard.boundary'
    _description='Exact Financial Reconciliation Inputs'
    batch_id=fields.Many2one(BATCH,required=True)
    company_id=fields.Many2one(related='batch_id.company_id',store=True)
    margin_source_id=fields.Integer(required=True)
    def action_run(self):
        self.ensure_one();self.check_access('read')
        result=self.batch_id.action_run_reconciliation(self.margin_source_id)
        return dict(type='ir.actions.act_window',res_model=HEADER,res_id=result.id,view_mode='form')


class ReconciliationReviewWizard(models.TransientModel):
    _name=PREFIX+'review.wizard'
    _inherit='vendor.price.revision.purchase.wizard.boundary'
    _description='Controlled Exception Review Inputs'
    batch_id=fields.Many2one(BATCH,required=True)
    company_id=fields.Many2one(related='batch_id.company_id',store=True)
    exception_id=fields.Many2one(ISSUE,required=True)
    event=fields.Selection([(v,v.replace('_',' ').title()) for v in ('assigned','in_review','revalidation_required','closed_verified','reopened')],required=True)
    reason=fields.Text(required=True)
    evidence=fields.Text(required=True)
    owner_id=fields.Many2one('res.users')
    verification_run_id=fields.Many2one(HEADER)
    def action_run(self):
        self.ensure_one();self.check_access('read')
        if self.exception_id.batch_id!=self.batch_id:raise AccessError('Review exception must belong to the exact selected batch.')
        self.exception_id.action_record_review(self.event,self.reason,self.evidence,self.owner_id.id or 0,self.verification_run_id.id or 0)
        return dict(type='ir.actions.act_window_close')
