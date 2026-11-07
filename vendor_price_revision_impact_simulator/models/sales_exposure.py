"""Immutable customer commercial evidence, deliberately separate from supplier ACLs.

Collection requires existing allocation access AND native access to every source
order/line AND a separate audited sales grant. Sales readers receive only a fixed
sales projection, never allocation provenance, supplier costs or raw attachments.
"""
from collections import defaultdict
from decimal import Decimal, localcontext

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.orm.domains import Domain

from .commercial_math import number, quantity, rounded
from .commercial_engine import CommercialEngine
from .structural_validation import digest
from .import_intake import clean_defaults
from .product_resolution import company_lock
from .allocation_engine import HEADER as ALLOCATION

PREFIX = 'vendor.price.revision.sales.'
HEADER, LINE, ISSUE, REVIEW, GRANT = [PREFIX+s for s in ('snapshot','line','issue','review','grant')]
MODULE = 'vendor_price_revision_impact_simulator.'
ROLES = ('group_vpr_sales_user','group_vpr_finance_manager','group_vpr_director','group_vpr_auditor','group_vpr_purchase_manager')
PROTECTION = [(s,s.replace('_',' ').title()) for s in ('fixed_price_verified','price_adjustment_allowed_verified',
    'offer_validity_review','contract_review_required','price_protection_unknown','not_applicable')]
POLICY = 'sales_v1_native_tax_unrounded_unit_currency_rounded_values_unallocated_adjustments'
LIMIT = 10000
LABEL_FIELDS = {'id','name','display_name'}


def projection_path(model, path):
    """Do not turn the analytical projection into a live native cost join."""
    parts=path.split(':',1)[0].replace('/','.').split('.')
    current=model
    for index, name in enumerate(parts):
        if not current._name.startswith(PREFIX) and (name not in LABEL_FIELDS or index!=len(parts)-1):
            raise AccessError('Sales analytics permits only native source identity/labels. Use the captured commercial fields.')
        field=current._fields.get(name)
        if not field:return  # Native ORM reports malformed/unknown expressions.
        if index<len(parts)-1:
            if not field.relational:return
            current=current.env[field.comodel_name]


def projection_domain(model, domain):
    for leaf in Domain(domain).iter_conditions():
        projection_path(model,leaf.field_expr)
        if leaf.operator in ('any','not any','any!','not any!'):
            current=model
            for name in leaf.field_expr.split('.'):
                field=current._fields.get(name)
                if not field or not field.relational:break
                current=current.env[field.comodel_name]
            else:projection_domain(current,leaf.value)


def role(env, names):
    return env.su or (env.user.active and any(env.user.has_group(MODULE+n) for n in names))


def authorized(env, company, warehouses, orders=None):
    if not role(env, ROLES) or company not in env.companies:
        raise AccessError('An active company sales analytical role is required.')
    if not env.su and any(w not in env.user.vpr_sales_warehouse_ids for w in warehouses):
        raise AccessError('Every warehouse requires an explicit audited sales-commercial grant.')
    if orders is not None:
        orders.check_access('read')
        orders.order_line.check_access('read')
        if any(o.company_id != company or o.warehouse_id not in warehouses for o in orders):
            raise AccessError('Sales sources are outside the selected company/warehouse scope.')


class SalesGrant(models.Model):
    _name = GRANT
    _inherit = 'vendor.price.revision.supply.governance'
    _description = 'Explicit Customer Commercial Analytical Scope'
    user_id = fields.Many2one('res.users', required=True)
    warehouse_ids = fields.Many2many('stock.warehouse', required=True)
    _unique = models.Constraint('UNIQUE(company_id,user_id)', 'One retained customer-commercial grant per company/user.')

    def _evidence(self):
        return self.read(['company_id','user_id','warehouse_ids','active','reason','version'],load=None)[0]

    @api.constrains('company_id','user_id','warehouse_ids','active')
    def _scope(self):
        for rec in self:
            if (not rec.user_id.active or rec.user_id.share or rec.company_id not in rec.user_id.company_ids
                or not any(rec.user_id.has_group(MODULE+n) for n in ROLES)
                or not rec.warehouse_ids or any(w.company_id != rec.company_id or not w.active for w in rec.warehouse_ids)):
                raise ValidationError('Select an internal sales-commercial role, its company and active company warehouses.')

    def _audit(self, before=None):
        result = super()._audit(before)
        self.env['res.users'].invalidate_model(['vpr_sales_warehouse_ids','vpr_sales_order_ids'])
        return result


class SalesUsers(models.Model):
    _inherit = 'res.users'
    vpr_sales_warehouse_ids = fields.Many2many('stock.warehouse', compute='_compute_vpr_sales_scope')
    vpr_sales_order_ids = fields.Many2many('sale.order', compute='_compute_vpr_sales_scope')

    def _compute_vpr_sales_scope(self):
        # sudo is confined to grant metadata. Operational Sales rights are never
        # elevated. Rules on snapshots require access to ALL constituent orders.
        grants = self.env[GRANT].sudo().search([('user_id','in',self.ids),('active','=',True)])
        for user in self:
            wh = grants.filtered(lambda g:g.user_id==user and g.company_id in user.company_ids).warehouse_ids
            user.vpr_sales_warehouse_ids = wh if user.active else False
            native = self.env['sale.order'].with_user(user).with_context(allowed_company_ids=user.company_ids.ids)
            try:
                orders = native.search([('company_id','in',user.company_ids.ids),('warehouse_id','in',wh.ids)],limit=LIMIT+1)
                user.vpr_sales_order_ids = orders if user.active and len(orders)<=LIMIT else False
            except AccessError:
                user.vpr_sales_order_ids = False

    def write(self, vals):
        if {'vpr_sales_warehouse_ids','vpr_sales_order_ids'} & vals.keys():
            raise AccessError('Commercial scope is governed by audited grants and native Sales access.')
        return super().write(vals)


class SalesGuard(models.AbstractModel):
    _name = PREFIX+'guard'
    _inherit = 'vendor.price.revision.intake.read.guard'
    _description = 'Immutable Sales Evidence Guard'
    company_id = fields.Many2one('res.company', required=True, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError('Use authorized sales evidence collection/review actions.')

    @api.model
    def _record(self, values):
        return super(SalesGuard, clean_defaults(self)).create(values)

    def write(self, vals):
        raise AccessError('Sales commercial evidence is immutable; create a new version.')

    def unlink(self):
        raise AccessError('Sales commercial history is retained.')

    def copy(self, default=None):
        raise AccessError('Sales evidence cannot be copied.')

    def _search(self, domain, offset=0, limit=None, order=None, *, active_test=True, bypass_access=False):
        projection_domain(self,domain)
        for term in (order or '').split(','):
            if term.strip():projection_path(self,term.strip().split()[0])
        return super()._search(domain,offset,limit,order,active_test=active_test,bypass_access=bypass_access)

    def _read_group_select(self, table, aggregate_spec):
        projection_path(self,aggregate_spec)
        return super()._read_group_select(table,aggregate_spec)

    def _read_group_groupby(self, table, groupby_spec):
        projection_path(self,groupby_spec)
        return super()._read_group_groupby(table,groupby_spec)

    def _validate_web_projection(self, specification):
        for name, options in specification.items():
            projection_path(self,name)
            field=self._fields.get(name)
            if field and field.relational and options.get('fields'):
                target=self.env[field.comodel_name]
                if target._name.startswith(PREFIX):target._validate_web_projection(options['fields'])
                else:
                    for nested, settings in options['fields'].items():
                        projection_path(target,nested)
                        if settings.get('fields'):raise AccessError('Nested native source traversal is outside the sales projection.')

    def web_read(self, specification):
        self.check_access('read');self._validate_web_projection(specification)
        return super().web_read(specification)

    def _add_groupby_values(self, specification, groupby, current_groups):
        for name, spec in (specification or {}).items():
            projection_path(self,name)
            field=self._fields.get(name.split(':',1)[0])
            if field and field.relational:
                target=self.env[field.comodel_name]
                if target._name.startswith(PREFIX):target._validate_web_projection(spec)
                else:
                    for nested, settings in spec.items():
                        projection_path(target,nested)
                        if settings.get('fields'):raise AccessError('Nested native source traversal is outside the sales projection.')
        return super()._add_groupby_values(specification,groupby,current_groups)

    @api.model
    def search_panel_select_range(self, field_name, **kwargs):
        raise AccessError('Use the documented sales projection filters; generic native search panels are not exposed.')

    @api.model
    def search_panel_select_multi_range(self, field_name, **kwargs):
        raise AccessError('Use the documented sales projection filters; generic native search panels are not exposed.')

    def export_data(self, names):
        for name in names:
            if name!='.id':projection_path(self,name)
        result = super().export_data(names)
        for row in result.get('datas',[]):
            for i, value in enumerate(row):
                if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')): row[i]="'"+value
        return result


class SalesSnapshot(models.Model):
    _name = HEADER
    _inherit = PREFIX+'guard'
    _description = 'Sales Commercial Value Reference (not recognized revenue)'
    _order = 'id desc'
    _unique = models.Constraint('UNIQUE(allocation_source_id,version)', 'One commercial version per allocation.')
    name = fields.Char(required=True)
    batch_source_id = fields.Integer(required=True, index=True)
    allocation_source_id = fields.Integer(required=True, index=True)
    allocation_version = fields.Integer(required=True)
    allocation_digest = fields.Char(required=True)
    supply_source_id = fields.Integer(required=True)
    scenario = fields.Char(required=True)
    warehouse_ids = fields.Many2many('stock.warehouse',required=True)
    order_ids = fields.Many2many('sale.order')
    version = fields.Integer(required=True)
    previous_id = fields.Many2one(HEADER,ondelete='restrict')
    fingerprint = fields.Char(required=True,index=True)
    policy_version = fields.Char(required=True)
    collected_at = fields.Datetime(required=True)
    collected_by = fields.Many2one('res.users',required=True)
    fx_date = fields.Date(string='Explicit sales FX reference date')
    state = fields.Selection([('sales_terms_verified','Sales values verified; inspect independent protection status'),
        ('review_required','Commercial basis / evidence review')],required=True)
    totals = fields.Json(help='Currency AND confirmed/conditional groups; never add scenario alternatives.')
    order_context = fields.Json(help='Full order references and separate non-demand adjustments; not outstanding revenue.')
    confirmed_line_count = fields.Integer()
    conditional_line_count = fields.Integer()
    exception_count = fields.Integer()
    line_ids = fields.One2many(LINE,'snapshot_id')
    issue_ids = fields.One2many(ISSUE,'snapshot_id')
    freshness = fields.Selection([('current','Current'),('stale','Stale / source access unavailable')],compute='_freshness',search='_search_freshness')

    def _current(self):
        self.ensure_one(); self.check_access('read')
        # A Sales-only reader cannot traverse the supplier allocation. Explicit
        # collector authorization remains necessary to attest full freshness.
        allocation = self.env[ALLOCATION].browse(self.allocation_source_id)
        engine = SalesEngine(allocation,self.fx_date).build()
        latest = self.search([('allocation_source_id','=',allocation.id)],limit=1)
        return latest==self and engine.fingerprint==self.fingerprint

    def _freshness(self):
        for rec in self:
            try: current=rec._current()
            except (AccessError,UserError,ValidationError): current=False
            rec.freshness='current' if current else 'stale'

    def _search_freshness(self, operator, value):
        if operator not in ('=','!=') or value not in ('current','stale'): return [('id','=',0)]
        rows=self.search([],limit=1001)
        if len(rows)>1000: raise UserError('Narrow commercial history before searching freshness.')
        return [('id','in' if operator=='=' else 'not in',[r.id for r in rows if r.freshness==value])]

    def action_check_current(self):
        if not self._current(): raise UserError('Sales source/allocation/policy evidence is stale. Recollect current evidence.')
        return True


class SalesLine(models.Model):
    _name = LINE
    _inherit = PREFIX+'guard'
    _description = 'Exact Customer Sales Line Commercial Evidence'
    _unique = models.Constraint('UNIQUE(snapshot_id,sale_line_id)', 'An exact sales line contributes once per scenario.')
    snapshot_id = fields.Many2one(HEADER,required=True,ondelete='restrict',index=True)
    sale_order_id = fields.Many2one('sale.order',required=True,ondelete='restrict')
    sale_line_id = fields.Many2one('sale.order.line',required=True,ondelete='restrict',index=True)
    customer_id = fields.Many2one('res.partner',required=True)
    product_id = fields.Many2one('product.product',required=True)
    warehouse_id = fields.Many2one('stock.warehouse',required=True)
    demand_type = fields.Selection([('confirmed','Confirmed commitment'),('conditional','Conditional quotation')],required=True)
    source_order_state = fields.Char(required=True)
    sales_currency_id = fields.Many2one('res.currency',required=True)
    company_currency_id = fields.Many2one('res.currency',required=True)
    source_uom_id = fields.Many2one('uom.uom',required=True)
    comparison_uom_id = fields.Many2one('uom.uom',required=True)
    source_unit_price = fields.Char(required=True)
    source_discount_percent = fields.Char(required=True)
    ordered_qty = fields.Char()
    delivered_qty = fields.Char()
    outstanding_qty = fields.Char()
    net_sales_unit_price = fields.Char(string='Tax-excluded net price per comparison UoM')
    outstanding_sales_value = fields.Char(string='Outstanding commercial value (blank = incomplete)')
    company_sales_value = fields.Char(string='Company-currency reference (blank = incomplete)')
    price_protection = fields.Selection(PROTECTION,required=True)
    opportunity_status = fields.Char(required=True)
    valuation_status = fields.Selection([('verified','Sales-value basis verified'),('incomplete','Revenue basis incomplete')],required=True)
    allocation_demand_source_id = fields.Integer(required=True)
    allocation_values = fields.Json()
    source_terms = fields.Json(required=True)
    source_digest = fields.Char(required=True)
    protection_evidence = fields.Json()
    fx_evidence = fields.Json(required=True)
    issue_codes = fields.Json()
    review_ids = fields.One2many(REVIEW,'line_id')

    def action_open_source(self):
        self.ensure_one();self.check_access('read')
        authorized(self.env,self.company_id,self.warehouse_id,self.sale_order_id)
        self.sale_line_id.check_access('read')
        return {'type':'ir.actions.act_window','res_model':'sale.order','res_id':self.sale_order_id.id,'view_mode':'form'}

    def action_review_price_protection(self, classification, evidence_reference, reason, effective_start=None, effective_end=None):
        self.ensure_one();self.check_access('read')
        if not role(self.env,('group_vpr_sales_manager',)):
            raise AccessError('A company-authorized Sales Manager must review documented customer terms.')
        authorized(self.env,self.company_id,self.warehouse_id,self.sale_order_id)
        if classification not in dict(PROTECTION) or not str(evidence_reference or '').strip() or not str(reason or '').strip():
            raise ValidationError('Classification, traceable evidence reference and reason are required.')
        start=fields.Date.to_date(effective_start);end=fields.Date.to_date(effective_end)
        if start and end and start>end: raise ValidationError('Invalid contractual effective interval.')
        company_lock(self.env,self.company_id)
        # Narrow privilege: lifecycle metadata for this already-authorized,
        # immutable snapshot's batch only. No supplier values are returned.
        batch=self.env['vendor.price.revision.import.batch'].sudo().search([
            ('id','=',self.snapshot_id.batch_source_id),('company_id','=',self.company_id.id)],limit=1)
        if not batch or batch.state!='extracted' or batch.revision_id.state!='draft':
            raise UserError('Customer review requires an active extracted batch on a draft revision.')
        self.env.flush_all()
        for table, identifier in [('vendor_price_revision',batch.revision_id.id),
            ('vendor_price_revision_import_batch',batch.id),('sale_order',self.sale_order_id.id),('sale_order_line',self.sale_line_id.id)]:
            self.env.cr.execute('SELECT id FROM '+table+' WHERE id = %s FOR SHARE',[identifier])
        current=sales_terms(self.sale_line_id)
        if digest(current)!=self.source_digest:
            raise UserError('Sales terms changed; collect current commercial evidence before review.')
        return self.env[REVIEW]._record(dict(company_id=self.company_id.id,line_id=self.id,
            sale_order_id=self.sale_order_id.id,sale_line_id=self.sale_line_id.id,warehouse_id=self.warehouse_id.id,
            source_digest=self.source_digest,classification=classification,evidence_reference=evidence_reference,
            reason=reason,effective_start=start,effective_end=end,reviewed_at=fields.Datetime.now(),reviewed_by=self.env.uid))

    def action_open_review(self):
        self.ensure_one();self.check_access('read')
        if not role(self.env,('group_vpr_sales_manager',)):raise AccessError('Sales Manager review required.')
        return {'type':'ir.actions.act_window','res_model':PREFIX+'review.wizard','view_mode':'form','target':'new','context':{'default_line_id':self.id}}


class SalesIssue(models.Model):
    _name = ISSUE
    _inherit = PREFIX+'guard'
    _description = 'Retained Sales Commercial Exception'
    snapshot_id = fields.Many2one(HEADER,required=True,ondelete='restrict',index=True)
    sale_line_id = fields.Many2one('sale.order.line',required=True,ondelete='restrict')
    code = fields.Char(required=True,index=True)
    severity = fields.Char(required=True)
    message = fields.Text(required=True)


class ProtectionReview(models.Model):
    _name = REVIEW
    _inherit = PREFIX+'guard'
    _description = 'Retained Customer Price Protection Assessment (not repricing authority)'
    _order = 'id desc'
    line_id = fields.Many2one(LINE,required=True,ondelete='restrict')
    sale_order_id = fields.Many2one('sale.order',required=True,ondelete='restrict')
    sale_line_id = fields.Many2one('sale.order.line',required=True,ondelete='restrict',index=True)
    warehouse_id = fields.Many2one('stock.warehouse',required=True)
    source_digest = fields.Char(required=True)
    classification = fields.Selection(PROTECTION,required=True)
    evidence_reference = fields.Char(required=True)
    reason = fields.Text(required=True)
    effective_start = fields.Date()
    effective_end = fields.Date()
    reviewed_at = fields.Datetime(required=True)
    reviewed_by = fields.Many2one('res.users',required=True)


def sales_terms(line):
    o=line.order_id;c=o.currency_id;unit=line.product_uom_id
    return dict(order_id=o.id,line_id=line.id,customer_id=o.partner_id.id,company_id=o.company_id.id,
                product_id=line.product_id.id,warehouse_id=o.warehouse_id.id,state=o.state,currency_id=c.id,
                unit_price=str(line.price_unit),discount=str(line.discount),tax_ids=line.tax_ids.ids,
                ordered_source=str(line.product_uom_qty),source_uom_id=unit.id,pricelist_context_id=o.pricelist_id.id,
                price_source='actual_sale_order_line; current pricelist is context, not historical rule proof',
                order_date=str(o.date_order),validity_date=str(o.validity_date) if o.validity_date else None,
                customer_reference=o.client_order_ref or None,payment_term_id=o.payment_term_id.id,fiscal_position_id=o.fiscal_position_id.id,
                document_tax_mode=o.document_tax_mode,full_line_tax_excluded=str(line.price_subtotal),
                historical_original_price='unavailable_without_prior_snapshot_or_explicit_amendment_evidence')


class SalesEngine:
    def __init__(self, allocation, fx_date=None):
        allocation.ensure_one();allocation.check_access('read')
        self.allocation,self.env=allocation,allocation.env
        self.company=allocation.company_id
        self.fx_date=fields.Date.to_date(fx_date)
        self.lines,self.issues,self.order_context=[],[],[]
        self.sources={};self.locked=[];self.fx_cache={}

    def read(self, model, domain, names):
        # Native permissions only; unlike quantity service no sales sudo.
        recs=self.env[model].with_company(self.company).search(domain,order='id',limit=LIMIT+1)
        if len(recs)>LIMIT:raise UserError('Sales source limit exceeded. Narrow the allocation scope.')
        data=recs.read(names,load=None)
        for row in data:
            for k,v in row.items():
                if hasattr(v,'isoformat'):row[k]=v.isoformat()
        self.sources.setdefault(model,[]).append(data)
        if recs:self.locked.append((recs._table,tuple(recs.ids)))
        return recs

    def issue(self,line,code,message,severity='review'):
        self.issues.append(dict(sale_line_id=line.id,code=code,message=message,severity=severity))

    def fx(self,currency):
        key=currency.id
        if key in self.fx_cache:return self.fx_cache[key]
        company_currency=self.company.currency_id
        e=dict(source_currency_id=currency.id,target_currency_id=company_currency.id,company_id=self.company.id,
            requested_date=str(self.fx_date) if self.fx_date else None,rate=None,method='sales_explicit_date_guarded_odoo20_rates')
        if currency==company_currency:e.update(rate='1',method='same_currency_identity',rate_records=[])
        elif self.fx_date and self.fx_date<=fields.Date.today():
            # Match verified PR08 Odoo20 strict-before cutoff and root preference;
            # reject absent/earliest/1:1 fallbacks. Never reuse supplier FX date.
            if self.company.root_id!=self.company and self.company.root_id not in self.env.companies:
                self.fx_cache[key]=e
                return e
            rates=self.read('res.currency.rate',[('currency_id','in',(currency|company_currency).ids),
                ('company_id','in',[False,self.company.root_id.id]),('name','<',self.fx_date)],
                ['currency_id','company_id','name','rate'])
            chosen=[]
            for curr in currency|company_currency:
                choices=rates.filtered(lambda r:r.currency_id==curr).sorted(key=lambda r:(bool(r.company_id),r.name,r.id),reverse=True)
                if not choices or number(choices[0].rate)<=0:break
                rate=choices[0];chosen.append(dict(id=rate.id,currency_id=curr.id,company_id=rate.company_id.id,date=str(rate.name),technical_rate=str(rate.rate)))
            if len(chosen)==2:
                by={v['currency_id']:v for v in chosen}
                e.update(rate=str(number(by[company_currency.id]['technical_rate'])/number(by[currency.id]['technical_rate'])),rate_records=chosen)
        self.fx_cache[key]=e;return e

    def build(self):
        with localcontext() as ctx:
            ctx.prec=38
            return self._build()

    def _build(self):
        a=self.allocation;s=a.scope
        authorized(self.env,self.company,a.warehouse_ids)
        current=a.batch_id.get_current_allocation(s['warehouses'],s['costs'],s['horizon'],s['confirmed_ids'],s['quote_ids'],s['portfolio_reason'])
        if current!=a:raise UserError('Allocation is superseded; collect sales terms from the current allocation.')
        demands=a.demand_ids
        ids=demands.mapped('sale_line_id')
        if len(ids)!=len(set(ids)):raise ValidationError('Duplicate exact sales line in allocation.')
        lines=self.read('sale.order.line',[('id','in',ids),('company_id','=',self.company.id)],
            ['order_id','product_id','product_uom_id','product_uom_qty','qty_delivered','qty_invoiced','price_unit','discount','tax_ids','price_subtotal','price_total','display_type','is_downpayment','extra_tax_data'])
        if set(lines.ids)!=set(ids):raise AccessError('Every exact allocation sales line must be natively readable.')
        orders=self.read('sale.order',[('id','in',lines.order_id.ids),('company_id','=',self.company.id)],
            ['name','company_id','partner_id','warehouse_id','currency_id','pricelist_id','state','date_order','validity_date','client_order_ref','commitment_date','user_id','payment_term_id','fiscal_position_id','document_tax_mode','amount_untaxed','amount_tax','amount_total','currency_rate'])
        authorized(self.env,self.company,a.warehouse_ids,orders)
        self.orders=orders
        all_lines=self.read('sale.order.line',[('order_id','in',orders.ids)],
            ['order_id','product_id','product_uom_qty','price_unit','discount','price_subtotal','display_type','is_downpayment','extra_tax_data'])
        reviews=self.read(REVIEW,[('sale_line_id','in',ids),('company_id','=',self.company.id)],
            ['sale_line_id','source_digest','classification','evidence_reference','reason','effective_start','effective_end','reviewed_by','reviewed_at'])
        self.read('res.company',[('id','=',self.company.id)],['currency_id','tax_calculation_rounding_method','sale_discount_product_id'])
        self.read('res.currency',[('id','in',(orders.currency_id|self.company.currency_id).ids)],['rounding','active','name'])
        taxes=lines.tax_ids
        # Groups' descendants and definitions are material even if the order's
        # stored subtotal has not recomputed after a tax configuration amendment.
        for _ in range(12):
            expanded=taxes|taxes.children_tax_ids
            if expanded==taxes:break
            taxes=expanded
        else:raise UserError('Tax graph limit exceeded; review tax configuration.')
        self.read('account.tax',[('id','in',taxes.ids)],['company_id','amount','amount_type','price_include','price_include_override','include_base_amount','is_base_affected','sequence','children_tax_ids','active'])
        tax_evidence={v['id']:v for group in self.sources['account.tax'] for v in group}
        commercial=CommercialEngine(a.batch_id)
        sales_units=lines.product_uom_id|demands.uom_id
        ancestors={int(i) for u in sales_units for i in (u.parent_path or '').split('/') if i}
        units=self.read('uom.uom',[('id','in',sorted(set(sales_units.ids)|ancestors))],
            ['factor','relative_factor','relative_uom_id','parent_path','active','name'])
        commercial.by_uom.update({u.id:u for u in units})
        for o in orders:
            ol=all_lines.filtered(lambda l:l.order_id==o and not l.display_type)
            adjustments=ol.filtered(lambda l:l._is_discount_line() or l._is_global_discount() or l.price_subtotal<0 or l.is_downpayment)
            self.order_context.append(dict(order_id=o.id,currency_id=o.currency_id.id,full_order_tax_excluded=str(o.amount_untaxed),
                adjustment_lines=[dict(id=l.id,subtotal=str(l.price_subtotal),source_unit_price=str(l.price_unit),
                    source_discount_percent=str(l.discount),source_quantity=str(l.product_uom_qty),
                    downpayment=l.is_downpayment,global_discount=bool(l._is_global_discount()),discount_product=bool(l._is_discount_line())) for l in adjustments],
                policy='Order-only adjustment reference; no invented product apportionment. Shipping/services excluded from demand values.'))
        by={l.id:l for l in lines};totals=defaultdict(lambda:dict(value=Decimal(0),incomplete_lines=0,line_count=0))
        for d in demands:
            line=by[d.sale_line_id];o=line.order_id;c=o.currency_id
            if (line.product_id.id!=d.product_id or o.warehouse_id!=d.warehouse_id or
                (d.demand_type=='confirmed' and o.state!='sale') or (d.demand_type=='conditional' and o.state not in ('draft','sent'))):
                raise UserError('Exact allocation/source state or variant changed. Revalidate allocation.')
            unit=line.product_uom_id;target=d.uom_id
            terms=sales_terms(line)
            terms_digest=digest(terms)
            line_taxes=line.tax_ids
            for _ in range(12):
                expanded=line_taxes|line_taxes.children_tax_ids
                if expanded==line_taxes:break
                line_taxes=expanded
            terms['tax_evidence']=[tax_evidence[t.id] for t in line_taxes if t.id in tax_evidence]
            terms['rounding_policy']=dict(source_currency_rounding=str(c.rounding),
                company_currency_rounding=str(self.company.currency_id.rounding),
                tax_rounding_method=self.company.tax_calculation_rounding_method,
                value_rounding='Decimal HALF_UP to currency increment; unrounded unit retained')
            candidates=reviews.filtered(lambda r:r.sale_line_id==line)
            review=candidates.sorted('id',reverse=True)[:1]
            protection='offer_validity_review' if o.state=='sent' else 'contract_review_required' if o.state=='sale' else 'price_protection_unknown'
            protection_evidence={}
            today=fields.Date.today();order_date=o.date_order.date()
            if review:
                applicable=(review.source_digest==terms_digest and (not review.effective_start or review.effective_start<=order_date)
                    and (not review.effective_end or order_date<=review.effective_end) and (not review.effective_end or today<=review.effective_end))
                if applicable:
                    protection=review.classification
                    protection_evidence=dict(review_id=review.id,reviewed_by=review.reviewed_by.id,reviewed_at=str(review.reviewed_at),reference=review.evidence_reference,reason=review.reason,
                        effective_start=str(review.effective_start) if review.effective_start else None,effective_end=str(review.effective_end) if review.effective_end else None)
                else:self.issue(line,'PRICE_AMENDMENT_UNVERIFIED','Latest assessment is expired or bound to different source terms; retain history and review again.')
            if protection not in ('fixed_price_verified','price_adjustment_allowed_verified','not_applicable'):
                self.issue(line,'PRICE_PROTECTION_UNVERIFIED','Recorded price is available; contractual adjustment rights require documented commercial review.')
            opportunity='confirmed_commitment' if d.demand_type=='confirmed' else 'unsent_draft_reviewable'
            if d.demand_type=='conditional':
                if o.validity_date and o.validity_date<today:
                    opportunity='expired_offer_review';self.issue(line,'QUOTATION_EXPIRED','Historical selected quote remains conditional; expiration requires commercial review.')
                elif o.state=='sent':opportunity='sent_valid_offer_review' if o.validity_date else 'contractual_restriction_unknown'
            net=value=company_value=None;attribution=[];status='verified'
            fx=self.fx(c)
            try:
                pair=commercial.pair(unit,target);terms['uom_basis']=pair
                price=number(line.price_unit);discount=number(line.discount)
                if price<0 or discount>100 or not c.active:raise ValueError('SALES_PRICE_BASIS_REVIEW')
                if price==0:self.issue(line,'ZERO_PRICE_REVIEW','Explicit source zero retained as a free-price reference; not substituted from a pricelist.')
                if any(t.company_id!=self.company or not t.active for t in taxes):raise ValueError('TAX_BASIS_UNVERIFIED')
                # Native Odoo20 tax base-line service respects document price mode,
                # included/division/fixed/group taxes and negative line discounts.
                discounted=price*(1-discount/100)
                base=line._prepare_base_line_for_taxes_computation(quantity=1.0,price_unit=float(discounted),discount=0.0)
                self.env['account.tax']._add_tax_details_in_base_line(base,self.company)
                source_net=number(base['tax_details']['raw_total_excluded_currency'])
                net=source_net*number(target.factor)/number(unit.factor)
                ordered=quantity(line.product_uom_qty,unit.factor,target.factor)
                if number(d.ordered)!=ordered:raise ValueError('DELIVERY_QTY_MISMATCH')
                if not d.outstanding:raise ValueError('OUTSTANDING_QTY_UNVERIFIED')
                if d.status=='unresolved' and d.issues:raise ValueError('DEMAND_INTERPRETATION_REVIEW')
                adjustments=next(v['adjustment_lines'] for v in self.order_context if v['order_id']==o.id)
                if adjustments:raise ValueError('GLOBAL_DISCOUNT_UNALLOCATED')
                # Detect custom totals differing from native unit semantics before
                # extrapolating a stable line price to outstanding quantities.
                expected=number(rounded(net*ordered,c.rounding))
                if abs(expected-number(line.price_subtotal))>number(c.rounding):raise ValueError('TAX_BASIS_UNVERIFIED')
                value=rounded(net*number(d.outstanding),c.rounding)
                entries=d.entry_ids
                if sum((number(e.quantity) for e in entries),Decimal(0))!=number(d.outstanding):raise ValueError('ALLOCATION_RECONCILIATION_FAILED')
                raw=[]
                for e in entries:
                    raw.append(net*number(e.quantity))
                    attribution.append(dict(entry_id=e.id,capacity_key=e.capacity_key,allocation_type=e.allocation_type,
                        quantity=e.quantity,value=rounded(raw[-1],c.rounding)))
                # No invented balancing income. Preserve exact unrounded values,
                # rounded category values and explicit rounding residual separately.
                residual=number(value)-sum((number(v['value']) for v in attribution),Decimal(0))
                for i,v in enumerate(attribution):v['unrounded_value']=str(raw[i])
                terms['rounding_residual']=str(residual)
                if fx['rate']:company_value=rounded(number(value)*number(fx['rate']),self.company.currency_id.rounding)
                else:self.issue(line,'SALES_FX_RATE_MISSING','Source-currency reference remains valid; explicit sales date and verified company rates required for conversion.')
            except (ValueError,KeyError,TypeError) as exc:
                code=str(exc);self.issue(line,code,'Sales-value basis is incomplete; preserve source terms without fabricated attributable revenue.','blocking')
                status='incomplete';value=company_value=None;attribution=[]
            self.lines.append(dict(company_id=self.company.id,sale_order_id=o.id,sale_line_id=line.id,customer_id=o.partner_id.id,
                product_id=line.product_id.id,warehouse_id=o.warehouse_id.id,demand_type=d.demand_type,source_order_state=o.state,
                sales_currency_id=c.id,company_currency_id=self.company.currency_id.id,source_uom_id=unit.id,comparison_uom_id=target.id,
                source_unit_price=str(line.price_unit),source_discount_percent=str(line.discount),ordered_qty=d.ordered,delivered_qty=d.delivered,
                outstanding_qty=d.outstanding,net_sales_unit_price=str(net) if net is not None else None,outstanding_sales_value=value,
                company_sales_value=company_value,price_protection=protection,opportunity_status=opportunity,valuation_status=status,
                allocation_demand_source_id=d.id,allocation_values=attribution,source_terms=terms,source_digest=terms_digest,
                protection_evidence=protection_evidence,fx_evidence=fx,issue_codes=[i['code'] for i in self.issues if i['sale_line_id']==line.id]))
            total=totals[str(c.id)+':'+d.demand_type];total['line_count']+=1
            if value is None:total['incomplete_lines']+=1
            else:total['value']+=number(value)
        self.totals={k:dict(v,known_value=str(v['value']),value=str(v['value']) if not v['incomplete_lines'] else None,complete=not v['incomplete_lines'],basis='Known source-currency outstanding commercial references; incomplete lines excluded, not zero') for k,v in totals.items()}
        # Fingerprint includes calendar only through validity/review outcomes, not
        # unrelated notes/write_date. The same inputs reuse one current version.
        self.fingerprint=digest(dict(policy=POLICY,allocation=a.fingerprint,fx_date=str(self.fx_date),sources=self.sources,
            lines=self.lines,issues=self.issues,orders=self.order_context))
        self.env.flush_all()
        for table,ids in sorted(set(self.locked)):
            self.env.cr.execute('SELECT id FROM '+table+' WHERE id IN %s ORDER BY id FOR SHARE',[ids])
        authorized(self.env,self.company,a.warehouse_ids,orders)
        return self


class AllocationSales(models.Model):
    _inherit = ALLOCATION

    def action_collect_sales_terms(self, fx_date=None):
        self.ensure_one();self.check_access('read')
        if not role(self.env,('group_vpr_sales_manager','group_vpr_finance_manager')):
            raise AccessError('Sales Manager or Finance Manager is required to collect commercial evidence.')
        self.batch_id._check_review_access()
        company_lock(self.env,self.company_id);self.batch_id._lock()
        with self.env.cr.savepoint(), localcontext() as ctx:
            ctx.prec=38
            e=SalesEngine(self,fx_date).build()
            previous=self.env[HEADER].search([('allocation_source_id','=',self.id)],limit=1)
            if previous and previous.fingerprint==e.fingerprint:return previous
            header=self.env[HEADER]._record(dict(company_id=self.company_id.id,name='Sales commercial reference / '+str(self.id),
                batch_source_id=self.batch_id.id,allocation_source_id=self.id,allocation_version=self.version,allocation_digest=self.fingerprint,
                supply_source_id=self.supply_snapshot_id.id,scenario=self.scenario,warehouse_ids=[(6,0,self.warehouse_ids.ids)],
                order_ids=[(6,0,e.orders.ids)],version=previous.version+1 if previous else 1,previous_id=previous.id,
                fingerprint=e.fingerprint,policy_version=POLICY,collected_at=fields.Datetime.now(),collected_by=self.env.uid,fx_date=e.fx_date,
                state='review_required' if e.issues else 'sales_terms_verified',totals=e.totals,order_context=e.order_context,
                confirmed_line_count=sum(r['demand_type']=='confirmed' for r in e.lines),conditional_line_count=sum(r['demand_type']=='conditional' for r in e.lines),exception_count=len(e.issues)))
            for row in e.lines:self.env[LINE]._record(dict(row,snapshot_id=header.id))
            for issue in e.issues:self.env[ISSUE]._record(dict(issue,company_id=self.company_id.id,snapshot_id=header.id))
            return header

    def get_current_sales_terms(self, fx_date=None):
        self.ensure_one();e=SalesEngine(self,fx_date).build()
        snapshot=self.env[HEADER].search([('allocation_source_id','=',self.id)],limit=1)
        if not snapshot or snapshot.fingerprint!=e.fingerprint:raise UserError('Sales commercial snapshot missing/stale; recollect current evidence.')
        return snapshot

    def action_open_sales_collection(self):
        self.ensure_one();self.check_access('read')
        return {'type':'ir.actions.act_window','res_model':PREFIX+'wizard','view_mode':'form','target':'new','context':{'default_allocation_id':self.id}}


class SalesWizardSurface(models.AbstractModel):
    _name = PREFIX+'wizard.surface'
    _description = 'Customer Review Wizard Projection Boundary'

    def _search(self, domain, offset=0, limit=None, order=None, *, active_test=True, bypass_access=False):
        projection_domain(self,domain)
        for term in (order or '').split(','):
            if term.strip():projection_path(self,term.strip().split()[0])
        return super()._search(domain,offset,limit,order,active_test=active_test,bypass_access=bypass_access)

    def _validate_web_projection(self, specification):
        return SalesGuard._validate_web_projection(self,specification)

    def web_read(self, specification):
        self.check_access('read');self._validate_web_projection(specification)
        return super().web_read(specification)

    def export_data(self, names):
        raise AccessError('Transient review forms are not export surfaces. Export authorized immutable sales evidence instead.')

    def _read_group_select(self, table, aggregate_spec):
        projection_path(self,aggregate_spec)
        return super()._read_group_select(table,aggregate_spec)

    def _read_group_groupby(self, table, groupby_spec):
        projection_path(self,groupby_spec)
        return super()._read_group_groupby(table,groupby_spec)

    @api.model
    def web_read_group(self, *args, **kwargs):
        raise AccessError('Transient review forms are not grouped analytical data.')

    @api.model
    def search_panel_select_range(self, field_name, **kwargs):
        raise AccessError('Transient review forms have no generic native search panels.')

    @api.model
    def search_panel_select_multi_range(self, field_name, **kwargs):
        raise AccessError('Transient review forms have no generic native search panels.')


class SalesWizard(models.TransientModel):
    _name = PREFIX+'wizard'
    _inherit = PREFIX+'wizard.surface'
    _description = 'Collect Sales Commercial Terms'
    allocation_id = fields.Many2one(ALLOCATION,required=True)
    fx_date = fields.Date(string='Explicit sales FX reference date (optional)')

    def action_run(self):
        self.ensure_one();self.check_access('read')
        result=self.allocation_id.action_collect_sales_terms(self.fx_date)
        return {'type':'ir.actions.act_window','res_model':HEADER,'res_id':result.id,'view_mode':'form'}


class ProtectionWizard(models.TransientModel):
    _name = PREFIX+'review.wizard'
    _inherit = PREFIX+'wizard.surface'
    _description = 'Document Customer Price Protection Assessment'
    line_id = fields.Many2one(LINE,required=True)
    classification = fields.Selection(PROTECTION,required=True)
    evidence_reference = fields.Char(required=True)
    reason = fields.Text(required=True)
    effective_start = fields.Date()
    effective_end = fields.Date()

    def action_record(self):
        self.ensure_one();self.check_access('read')
        self.line_id.action_review_price_protection(self.classification,self.evidence_reference,self.reason,self.effective_start,self.effective_end)
        return {'type':'ir.actions.act_window_close'}
