"""Read-only purchase commercial references; no purchase/accounting execution.

The fixed source service requires company/warehouse cost grants and existing APP
roles. Native PO opening remains separately authorized. Bill detail additionally
requires native accounting read rights and is never fetched through sudo.
"""
from collections import defaultdict
from decimal import Decimal, localcontext

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .import_intake import BATCH, PURCHASE_USER, PURCHASE_MANAGER, clean_defaults
from .import_validation import PREFIX as IMPORT_PREFIX, ImmutableReview
from .product_resolution import company_lock
from .supply_governance import authorize
from .supply_engine import SupplyEngine
from .commercial_engine import POLICY_FIELDS
from .commercial_math import number, quantity, rounded
from .structural_validation import digest
from .allocation_engine import datetime_value

PREFIX='vendor.price.revision.purchase.'
HEADER,LINE,ISSUE,EVIDENCE=[PREFIX+s for s in ('snapshot','line','issue','evidence')]
POLICY='purchase_v1_ordered_tier_native_net_separate_commitment_amendment_billing'
KINDS=[(s,s.replace('_',' ').title()) for s in ('fixed','adjustable','amendment_pending','disputed','accepted_recorded','unknown')]
LIMIT=10000


def billing_allowed(env):
    return bool(env.su or (env.user.active and env['account.move'].has_access('read') and env['account.move.line'].has_access('read')))


class PurchaseUsers(models.Model):
    _inherit='res.users'
    vpr_purchase_bill_access=fields.Boolean(compute='_compute_purchase_bill_access')
    vpr_purchase_bill_ids=fields.Many2many('account.move',compute='_compute_purchase_bill_scope')
    vpr_purchase_bill_line_ids=fields.Many2many('account.move.line',compute='_compute_purchase_bill_scope')

    @api.depends_context('uid')
    def _compute_purchase_bill_access(self):
        for user in self:
            user.vpr_purchase_bill_access=bool((self.env.su or user==self.env.user) and user.active and billing_allowed(self.env(user=user.id,su=False)))

    @api.depends_context('uid')
    def _compute_purchase_bill_scope(self):
        for user in self:
            if not self.env.su and user!=self.env.user:
                raise AccessError('Another user cannot enumerate operational bill-scope metadata.')
            native=self.env(user=user.id,su=False,context=dict(self.env.context,allowed_company_ids=user.company_ids.ids))
            if not user.active or not billing_allowed(native):
                user.vpr_purchase_bill_ids=False;user.vpr_purchase_bill_line_ids=False;continue
            orders=native['account.move'].search([('company_id','in',user.company_ids.ids),('move_type','in',['in_invoice','in_refund'])],limit=LIMIT+1)
            lines=native['account.move.line'].search([('company_id','in',user.company_ids.ids),('move_id','in',orders.ids),('purchase_line_id','!=',False)],limit=LIMIT+1)
            user.vpr_purchase_bill_ids=orders if len(orders)<=LIMIT else False
            user.vpr_purchase_bill_line_ids=lines if len(lines)<=LIMIT else False

    def write(self,vals):
        if {'vpr_purchase_bill_access','vpr_purchase_bill_ids','vpr_purchase_bill_line_ids'} & vals.keys():raise AccessError('Billing visibility follows native accounting permissions.')
        return super().write(vals)


class PurchaseSnapshot(models.Model):
    _name=HEADER
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Purchase Commercial Commitment Reference (not payable or final exposure)'
    _order='id desc'
    _unique=models.Constraint('UNIQUE(batch_id,scope_key,version)','One immutable purchase version per scope.')
    name=fields.Char(required=True)
    warehouse_ids=fields.Many2many('stock.warehouse',required=True)
    supply_snapshot_id=fields.Many2one('vendor.price.revision.supply.snapshot',required=True,ondelete='restrict')
    allocation_source_id=fields.Integer(string='One analytical scenario ID; alternatives are not additive')
    contains_bills=fields.Boolean()
    bill_source_ids=fields.Many2many('account.move',string='Authorized exact bill IDs')
    bill_line_source_ids=fields.Many2many('account.move.line',string='Authorized exact bill-line IDs')
    scope_key=fields.Char(required=True,index=True)
    scope=fields.Json(required=True)
    version=fields.Integer(required=True)
    previous_id=fields.Many2one(HEADER,ondelete='restrict')
    fingerprint=fields.Char(required=True,index=True)
    collected_at=fields.Datetime(required=True)
    collected_by=fields.Many2one('res.users',required=True)
    policy_version=fields.Char(required=True)
    state=fields.Selection([('collected','Commercial values collected; inspect protection separately'),('review_required','Review required')],required=True)
    totals=fields.Json()
    provenance=fields.Json(required=True)
    line_ids=fields.One2many(LINE,'snapshot_id')
    issue_ids=fields.One2many(ISSUE,'snapshot_id')
    freshness=fields.Selection([('current','Current'),('stale','Stale / current source access unavailable')],compute='_freshness',search='_search_freshness')

    def _current(self):
        self.ensure_one();self.check_access('read')
        engine=PurchaseEngine(self.batch_id,**self.scope).build()
        latest=self.search([('batch_id','=',self.batch_id.id),('scope_key','=',self.scope_key)],limit=1)
        return latest==self and engine.fingerprint==self.fingerprint

    def _freshness(self):
        for rec in self:
            try:current=rec._current()
            except (AccessError,UserError,ValidationError):current=False
            rec.freshness='current' if current else 'stale'

    def _search_freshness(self,operator,value):
        if operator not in ('=','!=') or value not in ('current','stale'):return [('id','=',0)]
        records=self.search([],limit=1001)
        if len(records)>1000:raise UserError('Narrow purchase history before searching source freshness.')
        return [('id','in' if operator=='=' else 'not in',[r.id for r in records if r.freshness==value])]

    def action_check_current(self):
        if not self._current():raise UserError('Purchase/supply/allocation/evidence has changed. Recollect current purchase terms.')
        return {'type':'ir.actions.client','tag':'display_notification','params':{'message':'Current purchase commercial evidence','type':'success'}}


class PurchaseLine(models.Model):
    _name=LINE
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Exact RFQ/PO Line Commercial Evidence'
    _unique=models.Constraint('UNIQUE(snapshot_id,po_line_id)','An exact purchase line contributes once per scope.')
    snapshot_id=fields.Many2one(HEADER,required=True,ondelete='restrict',index=True)
    po_line_id=fields.Integer(required=True,index=True)
    po_order_id=fields.Integer(required=True)
    order_name=fields.Char(required=True)
    vendor_id=fields.Integer(required=True)
    product_id=fields.Integer(required=True,index=True)
    product_name=fields.Char(required=True)
    warehouse_id=fields.Many2one('stock.warehouse',required=True)
    source_order_state=fields.Char(required=True)
    commitment_type=fields.Selection([('confirmed','Confirmed commitment'),('conditional','Conditional RFQ / pending approval')],required=True)
    ordered_qty=fields.Char()
    received_qty=fields.Char()
    cancelled_qty=fields.Char()
    open_qty=fields.Char(string='Verified supplier-unreceived quantity; blank = not verified')
    conditional_qty=fields.Char()
    billed_qty=fields.Char(string='Native billed quantity, not receipt quantity')
    source_uom_id=fields.Many2one('uom.uom',required=True)
    comparison_uom_id=fields.Many2one('uom.uom',required=True)
    source_currency_id=fields.Many2one('res.currency',required=True)
    company_currency_id=fields.Many2one('res.currency',required=True)
    source_unit_price=fields.Char(required=True)
    source_discount_percent=fields.Char(required=True)
    normalized_agreed_unit_price=fields.Char(string='Net recorded price in source currency / base UoM')
    company_unit_price=fields.Char()
    open_commitment_value=fields.Char(string='Commercial open PO value; not accounts payable')
    conditional_value=fields.Char(string='Conditional RFQ value; not confirmed commitment')
    company_open_value=fields.Char()
    protected_unit_price=fields.Char(string='Source-currency protected reference; blank = unverified')
    proposed_unit_price=fields.Char(string='Applicable proposed price in comparison currency / base UoM')
    comparison_currency_id=fields.Many2one('res.currency')
    conditional_unit_difference=fields.Char()
    conditional_open_difference=fields.Char(string='Conditional price difference; not approved payable or final exposure')
    hypothetical_amended_value=fields.Char()
    protection_status=fields.Char(required=True)
    amendment_status=fields.Char(required=True)
    date_conflict_status=fields.Char(required=True)
    valuation_status=fields.Selection([('verified','Recorded commercial value verified'),('incomplete','Value basis incomplete')],required=True)
    source_digest=fields.Char(required=True)
    source_terms=fields.Json(required=True)
    quantity_evidence=fields.Json(required=True)
    price_evidence=fields.Json(required=True)
    protection_evidence=fields.Json()
    amendment_evidence=fields.Json()
    allocation_evidence=fields.Json()
    bill_evidence=fields.Json(required=True)
    historical_evidence=fields.Json()
    issue_codes=fields.Json()

    def action_open_source(self):
        self.ensure_one();self.check_access('read')
        authorize(self.batch_id,self.snapshot_id.warehouse_ids.ids,True)
        source=self.env['purchase.order.line'].browse(self.po_line_id).exists()
        if not source:raise UserError('Purchase source no longer exists.')
        source.check_access('read');source.order_id.check_access('read')
        if source.company_id!=self.company_id or source.order_id.picking_type_id.warehouse_id!=self.warehouse_id:
            raise AccessError('Source is outside the recorded authorized scope.')
        return {'type':'ir.actions.act_window','res_model':'purchase.order','res_id':source.order_id.id,'view_mode':'form'}

    def action_propose_evidence(self,kind,reference,reason,requested_price=None,effective_start=None,effective_end=None,date_basis='confirmation'):
        self.ensure_one();self.check_access('read');self.batch_id._check_review_access()
        authorize(self.batch_id,self.snapshot_id.warehouse_ids.ids,True,prepare=True)
        if kind not in dict(KINDS) or not str(reference or '').strip() or not str(reason or '').strip():
            raise ValidationError('Explicit assessment, traceable supplier reference and reason are required.')
        if date_basis not in ('confirmation','delivery'):raise ValidationError('Choose a documented confirmation or delivery date basis.')
        start=fields.Date.to_date(effective_start);end=fields.Date.to_date(effective_end)
        if start and end and start>end:raise ValidationError('Invalid supplier agreement interval.')
        price=None if requested_price in (None,False,'') else str(number(requested_price,True))
        if kind in ('amendment_pending','accepted_recorded') and price is None:raise ValidationError('An explicit source-currency/source-UoM amendment price is required.')
        company_lock(self.env,self.company_id);self.batch_id._lock()
        if not self.snapshot_id._current():raise UserError('Purchase snapshot is stale; recollect before recording evidence.')
        if self.commitment_type!='confirmed' and kind in ('fixed','adjustable','accepted_recorded'):
            raise ValidationError('An RFQ is not a confirmed protected purchase commitment.')
        if kind=='accepted_recorded' and number(price)!=number(self.source_unit_price):
            raise ValidationError('This is evidence of an already recorded amendment, never authorization to change the PO.')
        return self.env[EVIDENCE]._record(dict(batch_id=self.batch_id.id,warehouse_id=self.warehouse_id.id,
            po_line_id=self.po_line_id,source_line_snapshot_id=self.id,terms_digest=self.source_digest,
            terms=self.source_terms,kind=kind,reference=reference,reason=reason,requested_price=price,
            effective_start=start,effective_end=end,date_basis=date_basis,proposed_by=self.env.uid,
            proposed_at=fields.Datetime.now(),state='proposed'))

    def action_open_evidence(self):
        self.ensure_one();self.check_access('read');self.batch_id._check_review_access()
        return {'type':'ir.actions.act_window','res_model':PREFIX+'evidence.wizard','view_mode':'form','target':'new','context':{'default_line_id':self.id}}


class PurchaseIssue(models.Model):
    _name=ISSUE
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Immutable Purchase Commercial Exception'
    snapshot_id=fields.Many2one(HEADER,required=True,ondelete='restrict',index=True)
    po_line_id=fields.Integer(required=True)
    code=fields.Char(required=True,index=True)
    severity=fields.Char(required=True)
    message=fields.Text(required=True)


class PurchaseEvidence(models.Model):
    _name=EVIDENCE
    _inherit=IMPORT_PREFIX+'review.guard'
    _description='Independent Supplier Commitment/Amendment Assessment (not approval)'
    _order='id desc'
    warehouse_id=fields.Many2one('stock.warehouse',required=True)
    po_line_id=fields.Integer(required=True,index=True)
    source_line_snapshot_id=fields.Integer(required=True)
    terms_digest=fields.Char(required=True)
    terms=fields.Json(required=True)
    kind=fields.Selection(KINDS,required=True)
    reference=fields.Char(required=True)
    reason=fields.Text(required=True)
    requested_price=fields.Char()
    effective_start=fields.Date()
    effective_end=fields.Date()
    date_basis=fields.Selection([('confirmation','PO confirmation / RFQ deadline'),('delivery','Stored arrival date')],required=True)
    state=fields.Selection([('proposed','Evidence proposed'),('verified','Independently assessed evidence')],required=True)
    proposed_by=fields.Many2one('res.users',required=True)
    proposed_at=fields.Datetime(required=True)
    verified_by=fields.Many2one('res.users')
    verified_at=fields.Datetime()
    verification_reason=fields.Text()

    def action_verify(self,reason=None):
        self.ensure_one();self.check_access('read')
        if not self.env.user.active or not self.env.user.has_group(PURCHASE_MANAGER):raise AccessError('Purchase Manager assessment required.')
        if self.proposed_by==self.env.user or self.state!='proposed' or not str(reason or '').strip():
            raise ValidationError('Independent reviewer, proposed evidence and a verification reason are required.')
        if not self.proposed_by.active or not self.proposed_by.has_group(PURCHASE_USER) or self.company_id not in self.proposed_by.company_ids:
            raise AccessError('Evidence author must remain an authorized active company preparer.')
        self.batch_id._check_review_access();authorize(self.batch_id,[self.warehouse_id.id],True)
        company_lock(self.env,self.company_id);self.batch_id._lock()
        engine=PurchaseEngine(self.batch_id,[self.warehouse_id.id]).build()
        line=next((r for r in engine.lines if r['po_line_id']==self.po_line_id),None)
        if not line or line['source_digest']!=self.terms_digest:raise UserError('Purchase terms changed; retain this evidence and propose a current assessment.')
        super(ImmutableReview,clean_defaults(self)).write(dict(state='verified',verified_by=self.env.uid,
            verified_at=fields.Datetime.now(),verification_reason=reason))
        return True


class PurchaseEngine:
    def __init__(self,batch,warehouses,include_rfqs=True,allocation_id=0,include_bills=False,fx_date=None,comparison_date=None):
        self.batch,self.env=batch,batch.env
        self.wh=authorize(batch,warehouses,True)
        if type(include_rfqs) is not bool or type(include_bills) is not bool or type(allocation_id) is not int or allocation_id<0:
            raise ValidationError('Use explicit Boolean scope options and one positive allocation ID, or zero.')
        if include_bills and not billing_allowed(self.env):raise AccessError('Native company accounting read permission is required for bill detail.')
        self.scope=dict(warehouses=self.wh.ids,include_rfqs=include_rfqs,allocation_id=allocation_id,include_bills=include_bills,
            fx_date=str(fields.Date.to_date(fx_date)) if fx_date else None,comparison_date=str(fields.Date.to_date(comparison_date)) if comparison_date else None)
        self.company=batch.company_id;self.lines=[];self.issues=[];self.fx_cache={}
        self.reader=SupplyEngine(batch,self.wh.ids,True)
        self.commercial=self.reader.commercial

    def issue(self,lid,code,message,severity='review'):
        self.issues.append(dict(po_line_id=lid,code=code,message=message,severity=severity))

    def native_read(self,model,domain,names):
        records=self.env[model].with_company(self.company).search(domain,order='id',limit=LIMIT+1)
        if len(records)>LIMIT:raise UserError('Bill source limit exceeded; narrow the scope.')
        values=records.read(names,load=None)
        for row in values:
            for k,v in row.items():
                if hasattr(v,'isoformat'):row[k]=v.isoformat()
        self.reader.sources.setdefault(model,[]).append(values)
        if records:self.reader.locked.append((records._table,tuple(records.ids)))
        return records

    def fx(self,currency,date):
        key=(currency.id,str(date))
        if key in self.fx_cache:return self.fx_cache[key]
        target=self.company.currency_id
        result=dict(source_currency_id=currency.id,target_currency_id=target.id,company_id=self.company.id,
            requested_date=str(date) if date else None,rate=None,method='guarded_odoo20_target_divided_by_source',rate_records=[])
        if currency==target:result.update(rate='1',method='same_currency_identity')
        elif date and date<=fields.Date.context_today(self.batch) and (self.company.root_id==self.company or self.company.root_id in self.env.companies):
            rows=self.reader.read('res.currency.rate',[('currency_id','in',(currency|target).ids),('company_id','in',[False,self.company.root_id.id]),('name','<',date)],['currency_id','company_id','name','rate'])
            chosen={}
            for curr in currency|target:
                options=sorted((r for r in rows.values() if r['currency_id']==curr.id),key=lambda r:(bool(r['company_id']),r['name'],r['id']),reverse=True)
                if not options or number(options[0]['rate'])<=0:break
                chosen[curr.id]=options[0]
            if len(chosen)==2:result.update(rate=str(number(chosen[target.id]['rate'])/number(chosen[currency.id]['rate'])),rate_records=list(chosen.values()))
        self.fx_cache[key]=result;return result

    def net(self,line,currency,unit,target):
        self.commercial.pair(unit,target)
        price,discount=number(line.price_unit),number(line.discount)
        if price<0 or discount>100 or not currency.active:raise ValueError('PURCHASE_PRICE_BASIS_UNVERIFIED')
        base=line._prepare_base_line_for_taxes_computation()
        # Purchase's native method takes no kwargs. Rebuild the returned native
        # base with exact Decimal discount input, retaining its document context.
        base.update(quantity=1.0,price_unit=float(price*(1-discount/100)),discount=0.0)
        line.env['account.tax']._add_tax_details_in_base_line(base,self.company)
        value=number(base['tax_details']['raw_total_excluded_currency'])*number(target.factor)/number(unit.factor)
        if any(not t.active or t.company_id!=self.company for t in line.tax_ids):raise ValueError('TAX_BASIS_INCOMPLETE')
        return value

    def build(self):
        with localcontext() as ctx:
            ctx.prec=38
            return self._build()

    def _build(self):
        self.supply=self.batch.get_current_supply(self.wh.ids,True)
        self.allocation=self.env['vendor.price.revision.allocation.snapshot']
        if self.scope['allocation_id']:
            a=self.env['vendor.price.revision.allocation.snapshot'].browse(self.scope['allocation_id']);a.check_access('read')
            if a.batch_id!=self.batch or set(a.warehouse_ids.ids)!=set(self.wh.ids) or not a.contains_costs or a.supply_snapshot_id!=self.supply:
                raise AccessError('Allocation must be one current cost-authorized scenario for this exact batch/supply/warehouse scope.')
            s=a.scope
            if self.batch.get_current_allocation(s['warehouses'],s['costs'],s['horizon'],s['confirmed_ids'],s['quote_ids'],s['portfolio_reason'])!=a:
                raise UserError('Allocation source is stale.')
            self.allocation=a
        read=self.reader.read;cid=self.company.id
        states=['purchase']+(['draft','sent','to approve'] if self.scope['include_rfqs'] else [])
        orders=read('purchase.order',[('company_id','=',cid),('state','in',states),
            ('picking_type_id.warehouse_id','in',self.wh.ids),('partner_id.commercial_partner_id','=',self.batch.vendor_id.commercial_partner_id.id),
            ('order_line.product_id','in',self.reader.product_ids)],
            ['name','company_id','partner_id','currency_id','date_order','date_approve','partner_ref','state','locked','picking_type_id','dest_address_id','fiscal_position_id','payment_term_id','document_tax_mode','amount_untaxed','amount_total'])
        lines=read('purchase.order.line',[('order_id','in',list(orders)),('product_id','in',self.reader.product_ids),('display_type','=',False)],
            ['order_id','product_id','product_qty','qty_received','qty_received_method','qty_invoiced','uom_id','price_unit','discount','tax_ids','price_subtotal','date_planned','date_promised'])
        all_lines=read('purchase.order.line',[('order_id','in',list(orders)),('display_type','=',False)],
            ['order_id','product_id','product_qty','price_unit','discount','price_subtotal'])
        products=read('product.product',[('id','in',sorted(set(self.reader.product_ids)|{v['product_id'] for v in all_lines.values() if v['product_id']})),('company_id','in',[False,cid])],['uom_id','is_storable','active','type'])
        units=set(v['uom_id'] for v in lines.values())|{p['uom_id'] for p in products.values()}
        native_units=self.env['uom.uom'].with_context(active_test=False).browse(sorted(units))
        units|={int(v) for u in native_units for v in (u.parent_path or '').split('/') if v}
        data=read('uom.uom',[('id','in',sorted(units))],['factor','relative_factor','relative_uom_id','parent_path','active','name'])
        self.commercial.by_uom.update({i:self.env['uom.uom'].browse(i) for i in data})
        read('res.currency',[('id','in',sorted({o['currency_id'] for o in orders.values()}|{self.company.currency_id.id}))],['rounding','active','name'])
        read('res.company',[('id','=',cid)],['currency_id','tax_calculation_rounding_method'])
        taxes=self.reader.service['account.tax'].browse(sorted({i for l in lines.values() for i in l['tax_ids']}))
        for _ in range(12):
            expanded=taxes|taxes.children_tax_ids
            if expanded==taxes:break
            taxes=expanded
        else:raise UserError('Tax graph exceeds supported bound.')
        tax_data=read('account.tax',[('id','in',taxes.ids)],['company_id','amount','amount_type','price_include','price_include_override','include_base_amount','is_base_affected','sequence','children_tax_ids','active'])
        evidence=self.env[EVIDENCE].search([('batch_id','=',self.batch.id),('warehouse_id','in',self.wh.ids),('po_line_id','in',list(lines))],order='id',limit=LIMIT+1)
        if len(evidence)>LIMIT:raise UserError('Narrow evidence history before collecting purchase commitments.')
        ev=evidence.read(['po_line_id','terms_digest','kind','state','reference','reason','requested_price','effective_start','effective_end','date_basis','proposed_by','verified_by','verified_at'],load=None)
        self.evidence=evidence
        # JSON conversion preserves only real dates and trusted IDs.
        self.reader.sources['purchase_assessments']=[[dict(row,**{k:v.isoformat() for k,v in row.items() if hasattr(v,'isoformat')}) for row in ev]]
        if evidence:self.reader.locked.append((evidence._table,tuple(evidence.ids)))
        history=self.env[LINE].search([('batch_id','=',self.batch.id),('po_line_id','in',list(lines))],order='id desc',limit=LIMIT+1)
        if len(history)>LIMIT:raise UserError('Purchase history limit exceeded; narrow the scope.')
        latest_history={}
        for h in history:latest_history.setdefault(h.po_line_id,h)
        bills=self.env['account.move.line']
        if self.scope['include_bills']:
            bills=self.native_read('account.move.line',[('company_id','=',cid),('purchase_line_id','in',list(lines)),('move_id.move_type','in',['in_invoice','in_refund'])],
                ['purchase_line_id','product_id','product_uom_id','quantity','price_unit','discount','tax_ids','price_subtotal','move_id','currency_id'])
            self.native_read('account.move',[('id','in',bills.move_id.ids),('company_id','=',cid)],['state','move_type','currency_id','invoice_date','reversed_entry_id'])
        self.bills=bills
        buckets={int(b.source_key.split(':')[1]):b for b in self.supply.bucket_ids if b.source_key.startswith('po_line:')}
        entries=defaultdict(list)
        for entry in self.allocation.entry_ids:
            if entry.supply_bucket_id and entry.supply_bucket_id.source_key.startswith('po_line:'):
                entries[int(entry.supply_bucket_id.source_key.split(':')[1])].append(entry)
        totals=defaultdict(lambda:dict(known_value=Decimal(0),incomplete_lines=0,line_count=0))
        proposals=[dict(row_id=r.id,validation_id=r.commercial_result_id.id,proposal=r.commercial_result_id.snapshot['proposal'],baseline=r.commercial_result_id.snapshot.get('baseline')) for r in self.batch.get_commercially_valid_rows()]
        self.proposals=proposals
        labels={p['proposal']['product_id']:p['proposal']['product_name'] for p in proposals}
        for lid,src in lines.items():
            order=orders[src['order_id']];product=products[src['product_id']]
            native=self.reader.service['purchase.order.line'].browse(lid)
            unit=self.env['uom.uom'].browse(src['uom_id']);target=self.env['uom.uom'].browse(product['uom_id'])
            currency=self.env['res.currency'].browse(order['currency_id']);confirmed=order['state']=='purchase'
            warehouse=native.order_id.picking_type_id.warehouse_id
            if warehouse not in self.wh:raise AccessError('Purchase warehouse changed outside authorized scope.')
            terms=dict(line=src|{'qty_received':None,'qty_invoiced':None},order=order,
                uom=self.commercial.pair(unit,target),taxes=[v for v in tax_data.values() if v['id'] in (native.tax_ids|native.tax_ids.children_tax_ids).ids],
                price_source='actual_purchase_order_line; not current supplierinfo',supplier_offer_validity='not_recorded_by_core_purchase_order',
                rounding=dict(source=str(currency.rounding),company=str(self.company.currency_id.rounding),tax_method=self.company.tax_calculation_rounding_method))
            # Order totals vary with unrelated lines/receipts. They are separate
            # full-order references, not protection binding or open commitments.
            terms['order']={k:v for k,v in order.items() if k not in ('amount_untaxed','amount_total')}
            td=digest(terms);bucket=buckets.get(lid)
            ordered=quantity(src['product_qty'],unit.factor,target.factor)
            q=dict(kind='confirmed_supplier_unreceived' if confirmed else 'conditional_requested_only',
                supplier_bucket_id=bucket.id if bucket else None,ordered=str(ordered),received=None,cancelled=None,open=None,
                authoritative_supply_id=self.supply.id,quantity_verified=False)
            if confirmed and bucket:
                q.update(received=bucket.evidence.get('gross_received'),cancelled=bucket.evidence.get('cancelled'),
                    open=bucket.incoming if bucket.quantity_verified else None,quantity_verified=bucket.quantity_verified,
                    boundary=bucket.evidence.get('supplier_boundary'),returns=bucket.evidence.get('nonadditive_returns'),
                    nonadditive_putaway=bucket.evidence.get('nonadditive_internal'))
            elif confirmed:self.issue(lid,'RECEIPT_RECONCILIATION_CONFLICT','No current PR09 bucket verifies this source quantity.','blocking')
            linked=entries[lid];allocated=sum((number(e.quantity) for e in linked),Decimal(0))
            if q['open'] is not None and allocated>number(q['open']):raise ValidationError('Allocation exceeds the exact open purchase source.')
            allocation=dict(scenario_id=self.allocation.id or None,scenario=self.allocation.scenario if self.allocation else None,
                allocated=str(allocated) if self.allocation else None,unattributed=str(number(q['open'])-allocated) if self.allocation and q['open'] is not None else None,
                entries=[dict(id=e.id,capacity_key=e.capacity_key,quantity=e.quantity,allocation_type=e.allocation_type) for e in linked],
                semantics='One scenario only; not a second supply allocation. Dedicated/source uncertainty remains in PR09/PR10.')
            local=evidence.filtered(lambda e:e.po_line_id==lid)
            protection,protect=self.assessment(local,td,order,src,('fixed','adjustable','unknown'))
            amendment,amend=self.assessment(local,td,order,src,('amendment_pending','disputed','accepted_recorded'),pending=True)
            pstatus={'fixed':'protected_verified','adjustable':'price_adjustable_verified'}.get(protection,'protection_unknown')
            if not local.filtered(lambda e:e.kind in ('fixed','adjustable','unknown')) and bucket and bucket.evidence.get('cost',{}).get('firm_verified'):
                pstatus='protected_verified';protect=dict(source='pr09_independently_verified_exact_terms',attestation_id=bucket.evidence['cost'].get('attestation_id'))
            if not confirmed:pstatus='not_applicable'
            if pstatus=='protection_unknown':self.issue(lid,'PO_PRICE_PROTECTION_UNKNOWN','Internal PO confirmation is not proof of supplier fixed-price acceptance.')
            astatus=amendment or 'no_documented_amendment'
            if amendment in ('amendment_pending','disputed'):self.issue(lid,'PO_AMENDMENT_PENDING','Supplier-requested amendment is conditional evidence, never an accepted payable increase.')
            old=latest_history.get(lid)
            historical=dict(status='historical_original_price_unverified',previous_observation_id=None)
            if old and old.source_digest==td:
                historical=old.historical_evidence or historical
                if 'PO_PRICE_CHANGED' in (old.issue_codes or []):self.issue(lid,'PO_PRICE_CHANGED','Current PO price differs from the retained earlier observation; amendment authorization is not inferred.')
            elif old:
                historical=dict(status='prior_observed_snapshot_not_legal_original',previous_observation_id=old.id,source_price=old.source_unit_price)
                if number(old.source_unit_price)!=number(src['price_unit']):self.issue(lid,'PO_PRICE_CHANGED','Current PO price differs from the retained earlier observation; amendment authorization is not inferred.')
            net=value=conditional=company_price=company_value=None;comparison={};fx={};status='verified';proposed=None;delta=potential=hypothetical=None
            date=fields.Date.to_date(self.scope['comparison_date']) if self.scope['comparison_date'] else datetime_value(src['date_planned']).date() if src['date_planned'] else None
            policy=self.commercial.policy(date or fields.Date.context_today(self.batch))
            if not policy:raise UserError('Current complete PR04 company commercial policy is required.')
            policy_evidence=policy.read(list(POLICY_FIELDS),load=None)[0]
            policy_evidence={k:v.isoformat() if hasattr(v,'isoformat') else v for k,v in policy_evidence.items()}
            try:
                net=self.net(native,currency,unit,target)
                adjustments=[v for v in all_lines.values() if v['order_id']==order['id'] and (number(v['price_subtotal'])<0 or v['product_id'] not in products or not products[v['product_id']]['is_storable'])]
                if adjustments:raise ValueError('ORDER_CHARGES_UNALLOCATED')
                if abs(number(rounded(net*ordered,currency.rounding))-number(src['price_subtotal']))>number(currency.rounding):raise ValueError('TAX_BASIS_INCOMPLETE')
                if confirmed:
                    if q['open'] is None:raise ValueError('PO_QUANTITY_UNVERIFIED')
                    value=rounded(net*number(q['open']),currency.rounding)
                else:conditional=rounded(net*ordered,currency.rounding)
                fxdate=fields.Date.to_date(self.scope['fx_date']) if self.scope['fx_date'] else policy.currency_reference_date if policy.currency_rate_policy=='company_reference_date' else datetime_value(order['date_approve'] or order['date_order']).date()
                fx=self.fx(currency,fxdate)
                if fx['rate']:
                    company_price=str(net*number(fx['rate']))
                    company_value=rounded(number(value)*number(fx['rate']),self.company.currency_id.rounding) if value is not None else None
                else:self.issue(lid,'PO_FX_RATE_MISSING','Source-currency value is retained; missing company FX is never 1:1.')
                eligible=[p for p in proposals if p['proposal']['product_id']==src['product_id'] and date and
                    p['proposal']['effective_date']<=str(date) and (not p['proposal']['end_date'] or str(date)<=p['proposal']['end_date']) and number(p['proposal']['normalized_min_qty'])<=ordered]
                if eligible:
                    tier=max(number(p['proposal']['normalized_min_qty']) for p in eligible)
                    chosen=[p for p in eligible if number(p['proposal']['normalized_min_qty'])==tier]
                    if len(chosen)!=1:raise ValueError('PROPOSED_TIER_AMBIGUOUS')
                    chosen=chosen[0];p=chosen['proposal'];same=p['source_currency_id']==currency.id
                    pfx=self.fx(self.env['res.currency'].browse(p['source_currency_id']),fxdate)
                    comparison=dict(chosen,comparison_date=str(date),quantity_tier_basis='original_ordered_base_quantity_no_cross_order_aggregation',quantity=str(ordered),common_fx_date=str(fxdate),proposal_comparison_fx=pfx)
                    if same:proposed=number(p['net_comparable']);agreed=net;compcurrency=currency.id
                    elif pfx['rate'] and fx['rate']:proposed=number(p['net_comparable'])*number(pfx['rate']);agreed=net*number(fx['rate']);compcurrency=self.company.currency_id.id
                    else:agreed=None;compcurrency=None;self.issue(lid,'COMPARISON_CURRENCY_UNVERIFIED','PO/proposal comparison requires a verified common currency context.')
                    comparison['currency_id']=compcurrency
                    if proposed is not None and agreed is not None:
                        delta=str(proposed-agreed)
                        if confirmed and q['open'] is not None:
                            rc=self.env['res.currency'].browse(compcurrency)
                            potential=rounded(number(q['open'])*(proposed-agreed),rc.rounding)
                            hypothetical=rounded(number(q['open'])*proposed,rc.rounding)
                else:self.issue(lid,'PROPOSED_PRICE_NOT_APPLICABLE','No unique current PR08 proposal is applicable to this exact date and original quantity tier.')
            except (ValueError,KeyError,TypeError) as exc:
                self.issue(lid,str(exc),'Purchase value basis is incomplete; source evidence is retained without zero-filled financial amounts.','blocking')
                status='incomplete';value=conditional=company_value=None
            conflict='price_applicability_unknown'
            if comparison:
                effective=comparison['proposal']['effective_date'];confirmation=datetime_value(order['date_approve']).date() if order['date_approve'] else None
                if confirmed and not confirmation:self.issue(lid,'PO_CONFIRMATION_DATE_MISSING','Confirmation date is unavailable; no legal applicability date is invented.')
                if confirmed and confirmation and str(confirmation)<effective and str(date)>=effective:
                    conflict='revision_after_protected_commitment' if pstatus=='protected_verified' else 'revision_within_adjustable_period' if pstatus=='price_adjustable_verified' else 'price_applicability_unknown'
                    self.issue(lid,'REVISION_EFFECTIVE_DATE_CONFLICT','Delivery overlaps the proposed effective period; agreed PO terms remain recorded and no increase is automatically accepted.')
                elif confirmed and confirmation and str(confirmation)>=effective:
                    conflict='backdated_revision_review' if effective<str(fields.Date.context_today(self.batch)) else 'contract_date_conflict'
                    self.issue(lid,'REVISION_EFFECTIVE_DATE_CONFLICT','Confirmation/effective-date boundary requires documented agreement review, not automatic repricing.')
            bill=self.bill_context(bills.filtered(lambda b:b.purchase_line_id.id==lid),native,net,currency,target,lid)
            if amend.get('requested_price') is not None and net is not None and q['open'] is not None:
                # Reference-only request basis is explicitly tax-exclusive; never
                # accept a gross supplier request as a verified net amendment.
                if native.tax_ids.filtered('price_include'):
                    amend['scenario_status']='requested_tax_basis_unverified'
                else:
                    request=number(amend['requested_price'])*(1-number(src['discount'])/100)*number(target.factor)/number(unit.factor)
                    amend.update(scenario_status='conditional_request_not_accepted',source_currency_id=currency.id,
                        normalized_request=str(request),hypothetical_open_value=rounded(number(q['open'])*request,currency.rounding),
                        conditional_difference=rounded(number(q['open'])*(request-net),currency.rounding))
            self.lines.append(dict(batch_id=self.batch.id,po_line_id=lid,po_order_id=order['id'],order_name=order['name'],vendor_id=order['partner_id'],
                product_id=src['product_id'],product_name=labels[src['product_id']],warehouse_id=warehouse.id,source_order_state=order['state'],
                commitment_type='confirmed' if confirmed else 'conditional',ordered_qty=str(ordered),received_qty=q['received'],cancelled_qty=q['cancelled'],open_qty=q['open'],
                conditional_qty=None if confirmed else str(ordered),billed_qty=str(src['qty_invoiced']),source_uom_id=unit.id,comparison_uom_id=target.id,
                source_currency_id=currency.id,company_currency_id=self.company.currency_id.id,source_unit_price=str(src['price_unit']),source_discount_percent=str(src['discount']),
                normalized_agreed_unit_price=str(net) if net is not None else None,company_unit_price=company_price,open_commitment_value=value,
                conditional_value=conditional,company_open_value=company_value,protected_unit_price=str(net) if pstatus=='protected_verified' and net is not None else None,
                proposed_unit_price=str(proposed) if proposed is not None else None,comparison_currency_id=comparison.get('currency_id'),conditional_unit_difference=delta,
                conditional_open_difference=potential,hypothetical_amended_value=hypothetical,protection_status=pstatus,amendment_status=astatus,date_conflict_status=conflict,
                valuation_status=status,source_digest=td,source_terms=terms,quantity_evidence=q,price_evidence=dict(comparison=comparison,fx=fx,policy=policy_evidence,
                    full_order_reference=dict(tax_excluded=str(order['amount_untaxed']),currency_id=currency.id),historical_original_price='unverified_without_earlier_snapshot_or_documented_evidence'),
                protection_evidence=protect,amendment_evidence=amend,allocation_evidence=allocation,bill_evidence=bill,historical_evidence=historical,
                issue_codes=[i['code'] for i in self.issues if i['po_line_id']==lid]))
            total=totals[str(currency.id)+(':confirmed' if confirmed else ':conditional')];total['line_count']+=1
            chosen_value=value if confirmed else conditional
            if chosen_value is None:total['incomplete_lines']+=1
            else:total['known_value']+=number(chosen_value)
        self.totals={k:dict(v,known_value=str(v['known_value']),value=None if v['incomplete_lines'] else str(v['known_value']),complete=not v['incomplete_lines']) for k,v in totals.items()}
        # History navigation is not a material input: publishing a snapshot must
        # not itself invalidate that same snapshot or generate endless versions.
        material=[{k:v for k,v in row.items() if k!='historical_evidence'} for row in self.lines]
        self.fingerprint=digest(dict(policy=POLICY,scope=self.scope,supply_id=self.supply.id,supply_digest=self.supply.input_digest,
            allocation_digest=self.allocation.fingerprint if self.allocation else None,sources=self.reader.sources,proposals=proposals,lines=material,issues=self.issues))
        self.reader.lock();authorize(self.batch,self.wh.ids,True)
        return self

    def assessment(self,evidence,td,order,line,kinds,pending=False):
        selected=evidence.filtered(lambda e:e.kind in kinds).sorted('id',reverse=True)[:1]
        if not selected:return None,{}
        ref=dict(id=selected.id,kind=selected.kind,state=selected.state,reference=selected.reference,requested_price=selected.requested_price or None,
            proposed_by=selected.proposed_by.id,verified_by=selected.verified_by.id,reason=selected.reason,date_basis=selected.date_basis,
            effective_start=str(selected.effective_start) if selected.effective_start else None,effective_end=str(selected.effective_end) if selected.effective_end else None)
        if selected.terms_digest!=td:
            self.issue(line['id'],'UNVERIFIED_HISTORICAL_PRICE','Latest assessment is bound to different commercial terms; an older favorable assessment is not revived.')
            return None,ref
        rawdate=order['date_approve'] or order['date_order'] if selected.date_basis=='confirmation' else line['date_planned']
        date=datetime_value(rawdate).date() if rawdate else None
        if not date or (selected.effective_start and date<selected.effective_start) or (selected.effective_end and (date>selected.effective_end or fields.Date.context_today(self.batch)>selected.effective_end)):
            self.issue(line['id'],'AGREEMENT_EXPIRED','Evidence is outside its documented date interval; commercial rights require review.');return None,ref
        valid=(selected.state=='verified' and selected.verified_by.active and selected.verified_by.has_group(PURCHASE_MANAGER)
            and self.company in selected.verified_by.company_ids and selected.proposed_by.active
            and selected.proposed_by.has_group(PURCHASE_USER) and self.company in selected.proposed_by.company_ids)
        if pending and selected.kind in ('amendment_pending','disputed'):return selected.kind,ref
        if not valid:return None,ref
        return selected.kind,ref

    def bill_context(self,records,line,net,currency,target,lid):
        if not self.scope['include_bills']:return dict(status='not_verified_not_requested',bills=[])
        result=[]
        for b in records:
            unit=b.product_uom_id;move=b.move_id
            row=dict(line_id=b.id,bill_id=move.id,state=move.state,move_type=move.move_type,date=str(move.invoice_date) if move.invoice_date else None,
                quantity=str(b.quantity),source_unit_price=str(b.price_unit),discount=str(b.discount),currency_id=b.currency_id.id,uom_id=unit.id,
                reversed_entry_id=move.reversed_entry_id.id or None,comparison='not_verified')
            if move.state!='cancel' and b.product_id==line.product_id and b.currency_id==currency and net is not None:
                try:
                    extra={int(i) for i in (unit.parent_path or '').split('/') if i}|set(unit.ids)
                    self.commercial.by_uom.update({u.id:u for u in self.env['uom.uom'].browse(sorted(extra))})
                    self.commercial.pair(unit,target)
                    base=move._prepare_product_base_line_for_taxes_computation(b)
                    base.update(quantity=1.0,price_unit=float(number(b.price_unit)*(1-number(b.discount)/100)),discount=0.0)
                    b.env['account.tax']._add_tax_details_in_base_line(base,self.company)
                    value=number(base['tax_details']['raw_total_excluded_currency'])*number(target.factor)/number(unit.factor)
                    row.update(uom_basis=self.commercial.pair(unit,target),tax_ids=b.tax_ids.ids,net_comparable=str(value),difference=str(value-net),comparison='credit_note_reference_only' if move.move_type=='in_refund' else 'matched' if abs(value-net)<=number(currency.rounding) else 'bill_price_mismatch_review')
                    if row['comparison']=='bill_price_mismatch_review':self.issue(lid,'BILL_PO_PRICE_MISMATCH','Comparable bill price differs from the recorded PO; this is not an accepted PO amendment.')
                except (ValueError,KeyError):row['comparison']='uom_tax_basis_unverified'
            result.append(row)
        return dict(status='linked_read_only' if records else 'no_authorized_linked_bill_evidence',bills=result,
            semantics='Billed quantity never replaces PR09 supplier-boundary receipts. Credits do not amend POs.')


class BatchPurchase(models.Model):
    _inherit=BATCH

    def action_collect_purchase_terms(self,warehouse_ids,include_rfqs=True,allocation_id=0,include_bills=False,fx_date=None,comparison_date=None):
        self.ensure_one();authorize(self,warehouse_ids,True,prepare=True)
        company_lock(self.env,self.company_id);self._lock()
        with self.env.cr.savepoint():
            e=PurchaseEngine(self,warehouse_ids,include_rfqs,allocation_id,include_bills,fx_date,comparison_date).build()
            key=digest(e.scope);previous=self.env[HEADER].search([('batch_id','=',self.id),('scope_key','=',key)],limit=1)
            if previous and previous.fingerprint==e.fingerprint:return previous
            result=self.env[HEADER]._record(dict(batch_id=self.id,name='Purchase commercial reference / '+str(self.id),warehouse_ids=[(6,0,e.wh.ids)],
                supply_snapshot_id=e.supply.id,allocation_source_id=allocation_id,contains_bills=include_bills,scope_key=key,scope=e.scope,
                version=previous.version+1 if previous else 1,previous_id=previous.id,fingerprint=e.fingerprint,collected_at=fields.Datetime.now(),collected_by=self.env.uid,
                **(dict(bill_source_ids=[(6,0,e.bills.move_id.ids)],bill_line_source_ids=[(6,0,e.bills.ids)]) if e.bills else {}),
                policy_version=POLICY,state='review_required' if e.issues else 'collected',totals=e.totals,
                provenance=dict(sources=e.reader.sources,proposals=e.proposals,upstream_supply_digest=e.supply.input_digest,
                    allocation_digest=e.allocation.fingerprint if e.allocation else None,semantics='Source-specific commercial references only; no total company exposure, payable approval or repricing.')))
            for row in e.lines:self.env[LINE]._record(dict(row,snapshot_id=result.id))
            for issue in e.issues:self.env[ISSUE]._record(dict(issue,batch_id=self.id,snapshot_id=result.id))
            return result

    def get_current_purchase_terms(self,warehouse_ids,include_rfqs=True,allocation_id=0,include_bills=False,fx_date=None,comparison_date=None):
        self.ensure_one();e=PurchaseEngine(self,warehouse_ids,include_rfqs,allocation_id,include_bills,fx_date,comparison_date).build()
        result=self.env[HEADER].search([('batch_id','=',self.id),('scope_key','=',digest(e.scope))],limit=1)
        if not result or result.fingerprint!=e.fingerprint:raise UserError('Purchase commercial snapshot is missing or stale; collect current evidence.')
        return result

    def action_open_purchase_collection(self):
        self.ensure_one();self._check_review_access()
        return {'type':'ir.actions.act_window','res_model':PREFIX+'wizard','view_mode':'form','target':'new','context':{'default_batch_id':self.id}}


class PurchaseWizardBoundary(models.AbstractModel):
    _name=PREFIX+'wizard.boundary'
    _description='Purchase Input Forms Are Not Alternate Source Projections'

    def _search(self,domain,offset=0,limit=None,order=None,*,active_test=True,bypass_access=False):
        from odoo.orm.domains import Domain
        for leaf in Domain(domain).iter_conditions():
            if '.' in leaf.field_expr or leaf.operator in ('any','not any','any!','not any!'):
                raise AccessError('Use immutable purchase evidence for source filtering; input forms expose no source joins.')
        if order and any('.' in term for term in order.split(',')):raise AccessError('Native source ordering is outside input-form scope.')
        return super()._search(domain,offset,limit,order,active_test=active_test,bypass_access=bypass_access)

    def web_read(self,specification):
        self.check_access('read')
        for name,settings in specification.items():
            nested=settings.get('fields',{})
            if any(key not in ('id','name','display_name') or value.get('fields') for key,value in nested.items()):
                raise AccessError('Input forms expose only source identity/labels. Review the authorized immutable snapshot.')
        return super().web_read(specification)

    def export_data(self,names):
        raise AccessError('Export authorized purchase evidence, not transient input forms.')

    @api.model
    def web_read_group(self,*args,**kwargs):
        raise AccessError('Input forms are not analytical grouping surfaces.')

    @api.model
    def search_panel_select_range(self,*args,**kwargs):
        raise AccessError('Generic source search panels are not exposed on input forms.')

    @api.model
    def search_panel_select_multi_range(self,*args,**kwargs):
        raise AccessError('Generic source search panels are not exposed on input forms.')


class PurchaseWizard(models.TransientModel):
    _name=PREFIX+'wizard'
    _inherit=PREFIX+'wizard.boundary'
    _description='Collect Read-only Purchase Commitments'
    batch_id=fields.Many2one(BATCH,required=True)
    warehouse_ids=fields.Many2many('stock.warehouse',required=True)
    include_rfqs=fields.Boolean(default=True)
    allocation_id=fields.Integer(string='Optional exact PR10 scenario ID')
    include_bills=fields.Boolean(default=False)
    fx_date=fields.Date()
    comparison_date=fields.Date()

    def action_run(self):
        self.ensure_one();self.check_access('read')
        result=self.batch_id.action_collect_purchase_terms(self.warehouse_ids.ids,self.include_rfqs,self.allocation_id,self.include_bills,self.fx_date,self.comparison_date)
        return {'type':'ir.actions.act_window','res_model':HEADER,'res_id':result.id,'view_mode':'form'}


class EvidenceWizard(models.TransientModel):
    _name=PREFIX+'evidence.wizard'
    _inherit=PREFIX+'wizard.boundary'
    _description='Reference Supplier Commercial Evidence (not PO editor)'
    line_id=fields.Many2one(LINE,required=True)
    kind=fields.Selection(KINDS,required=True)
    reference=fields.Char(required=True)
    reason=fields.Text(required=True)
    requested_price=fields.Char()
    effective_start=fields.Date()
    effective_end=fields.Date()
    date_basis=fields.Selection([('confirmation','Confirmation'),('delivery','Stored delivery date')],default='confirmation',required=True)
    verification_id=fields.Many2one(EVIDENCE)

    @api.model_create_multi
    def create(self,vals_list):
        for vals in vals_list:
            source=self.env[LINE].browse(vals.get('line_id')).exists()
            if not source:raise ValidationError('Select an authorized immutable purchase line.')
            source.check_access('read')
        return super().create(vals_list)

    def action_propose(self):
        self.ensure_one();self.check_access('read')
        result=self.line_id.action_propose_evidence(self.kind,self.reference,self.reason,self.requested_price,self.effective_start,self.effective_end,self.date_basis)
        return {'type':'ir.actions.act_window','res_model':EVIDENCE,'res_id':result.id,'view_mode':'form'}

    def action_verify(self):
        self.ensure_one();self.check_access('read')
        if self.verification_id.batch_id!=self.line_id.batch_id or self.verification_id.po_line_id!=self.line_id.po_line_id:raise AccessError('Evidence must belong to this exact purchase source.')
        self.verification_id.action_verify(self.reason)
        return {'type':'ir.actions.act_window_close'}
