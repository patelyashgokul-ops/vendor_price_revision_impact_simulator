"""Read-only, reservation-aware quantity allocation. No operational actions."""
from collections import defaultdict, deque
from decimal import Decimal as D, localcontext
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError

from . import commercial_math as math
from .allocation_policy import PREFIX, POLICY, authorized
from .supply_engine import SupplyEngine, SNAPSHOT
from .structural_validation import digest

HEADER, DEMAND, LEDGER, ISSUE = [PREFIX+s for s in ('snapshot','demand','entry','issue')]
ACTIVE = ('waiting','confirmed','partially_available','assigned')
ZERO = D(0)


def datetime_value(value):
    """PR09 JSON stores ISO dates; Odoo Datetime ORM expects a space separator."""
    return fields.Datetime.to_datetime(value.replace('T',' ') if isinstance(value,str) else value)


def take(remaining, capacity):
    """Finite nonnegative Decimal consumption, no negative balancing adjustment."""
    need, available = math.number(remaining, True), math.number(capacity, True)
    with localcontext() as context:
        context.prec=38
        used = min(need, available)
        return used, need-used, available-used


class AllocationEngine:
    def __init__(self, batch, warehouse_ids, costs=True, horizon=None, confirmed_ids=None, quote_ids=None, reason=None):
        self.batch, self.env = batch, batch.env
        self.wh = authorized(batch, warehouse_ids, costs)
        self.costs = costs
        self.confirmed = self.ids(confirmed_ids, 'Confirmed orders', optional=True)
        self.quotes = self.ids(quote_ids, 'Quotations')
        self.reason = (reason or '').strip()
        if len(self.quotes)>1 and not self.reason:
            raise ValidationError('An explicit justification is required for a quotation portfolio, including alternative proposals.')
        if self.confirmed and set(self.confirmed)&set(self.quotes):
            raise ValidationError('The same source cannot be committed and conditional.')
        self.horizon = datetime_value(horizon) if horizon else None
        self.scenario = 'confirmed_baseline' if not self.quotes else 'single_quotation' if len(self.quotes)==1 else 'quotation_portfolio'
        self.scope = dict(warehouses=self.wh.ids,costs=costs,horizon=str(self.horizon) if self.horizon else None,
            confirmed_ids=self.confirmed,quote_ids=self.quotes,portfolio_reason=self.reason)
        self.scope_key = digest(self.scope)
        self.lines, self.entries, self.issues, self.capacities = [], [], [], {}
        self.now = fields.Datetime.now()

    @staticmethod
    def ids(value, label, optional=False):
        if value is None: return None if optional else []
        if not isinstance(value,(list,tuple)) or any(type(i) is not int or i<=0 for i in value):
            raise ValidationError(label+' require explicit positive integer IDs.')
        return sorted(set(value))

    def issue(self, code, key, message, severity='review'):
        self.issues.append(dict(code=code,source_key=key,message=message,severity=severity))

    def build(self):
        with localcontext() as context:
            context.prec=38
            return self._build()

    def _build(self):
        # Reuse PR09's exact current gateway, never a latest-ID-only stock read.
        self.supply = self.batch.get_current_supply(self.wh.ids,self.costs)
        self.reader = SupplyEngine(self.batch,self.wh.ids,self.costs).build()
        self.reader.lock()
        read = self.reader.read
        cid = self.batch.company_id.id
        policies = read(POLICY,[('company_id','=',cid),('active','=',True)],['version','priority','company_id','allow_receiving_buffer','receiving_buffer_hours'])
        self.policy = next(iter(policies.values()),dict(id=None,version='conservative_default_v1',priority='required_date',
            allow_receiving_buffer=False,receiving_buffer_hours=0))
        self.policy['date_basis_policy']='pr11_stored_commitment_or_confirmed_expected_v1'
        selection = [('order_id.state','=','sale')]
        if self.confirmed is not None: selection += [('order_id','in',self.confirmed)]
        domain = [('company_id','=',cid),('product_id','in',self.reader.product_ids),
            ('order_id.warehouse_id','in',self.wh.ids),('display_type','=',False),('is_downpayment','=',False)]
        # First collect confirmed scope, then explicitly selected quotations.
        self.sales = read('sale.order.line',domain+selection,
            ['company_id','order_id','product_id','product_uom_qty','product_uom_id','qty_delivered',
             'qty_delivered_method','route_ids'])
        if self.quotes:
            quotes = read('sale.order.line',domain+[('order_id','in',self.quotes),('order_id.state','in',['draft','sent'])],
                ['company_id','order_id','product_id','product_uom_qty','product_uom_id','qty_delivered',
                 'qty_delivered_method','route_ids'])
            self.sales.update(quotes)
        order_ids = sorted({l['order_id'] for l in self.sales.values()})
        self.orders = read('sale.order',[('id','in',order_ids),('company_id','=',cid),('warehouse_id','in',self.wh.ids)],
            ['company_id','state','warehouse_id','partner_id','name','date_order','commitment_date','expected_date','validity_date'])
        for order in self.orders.values():
            # Odoo20 draft/sent expected_date rolls with Datetime.now(). It is
            # neither a stored commitment nor a material input when an explicit
            # commitment is present. The reader's retained dictionaries share
            # these rows, so unused volatile values are absent from provenance
            # and freshness as well. Confirmed fallback remains date_order based.
            if order['commitment_date'] or order['state'] in ('draft','sent'):
                order.pop('expected_date',None)
        if (self.confirmed is not None and set(self.confirmed)-set(self.orders)) or set(self.quotes)-set(self.orders):
            raise AccessError('Selected sales sources must be current eligible affected-product orders within the approved company/warehouse scope.')
        for oid in self.quotes:
            order=self.orders[oid]
            if order['state'] not in ('draft','sent'):
                raise UserError('Selected quotation is no longer conditional. Rebuild the confirmed baseline.')
            if order['validity_date'] and fields.Date.to_date(order['validity_date']) < fields.Date.context_today(self.batch):
                raise ValidationError('Expired quotations are excluded by this current-scenario policy.')
        locids=sorted(self.reader.location_wh)
        names=['company_id','product_id','sale_line_id','purchase_line_id','state','uom_id','quantity','product_uom_qty',
            'location_id','location_dest_id','origin_returned_move_id','to_refund','move_orig_ids','move_dest_ids',
            'date','date_deadline','procure_method','rule_id']
        self.moves = read('stock.move',[('company_id','=',cid),('product_id','in',self.reader.product_ids),
            '|','|','|',('sale_line_id','in',list(self.sales)),('purchase_line_id','in',list(self.reader.lines)),
            ('location_id','in',locids),('location_dest_id','in',locids)],names)
        # Follow exact graph references in bounded bulk rounds, not per-line searches.
        for depth in range(12):
            missing={i for m in self.moves.values() for k in ('move_orig_ids','move_dest_ids') for i in m[k]}-set(self.moves)
            if not missing: break
            more=read('stock.move',[('id','in',sorted(missing)),('company_id','=',cid),('product_id','in',self.reader.product_ids)],names)
            if not more:break
            self.moves.update(more)
            if len(self.moves)>10000:raise UserError('Allocation movement graph exceeds the safe source bound.')
        else: raise UserError('Procurement lineage exceeds twelve levels; review the source graph.')
        endpoints={m[k] for m in self.moves.values() for k in ('location_id','location_dest_id')}
        self.locations=read('stock.location',[('id','in',sorted(endpoints))],['company_id','usage','active'])
        for location_id, location in self.locations.items():
            if location['usage']=='internal' and location_id not in self.reader.location_wh:
                raise AccessError('A linked fulfillment or procurement movement crosses an unselected warehouse. Select an authorized combined scope for review.')
        # Every active reservation in selected physical locations is projected,
        # including reservations for excluded demand. No customer prices are read.
        self.reservations=read('stock.move.line',[('company_id','=',cid),('product_id','in',self.reader.product_ids),
            ('location_id','in',locids),('state','in',list(ACTIVE))],
            ['company_id','product_id','move_id','uom_id','quantity','quantity_product_uom','location_id','lot_id','package_id','owner_id','state'])
        self._extend_units()
        self._demand()
        self._supply_pools()
        self._reservations()
        self._allocate()
        self.totals=self._totals()
        self.reader.lock()
        self.fingerprint=digest(dict(scope=self.scope,supply_id=self.supply.id,supply_digest=self.supply.input_digest,
            sources=self.reader.sources,policy=self.policy,demands=self.lines,ledger=self.entries,capacities=self.capacities,issues=self.issues))
        authorized(self.batch,self.wh.ids,self.costs)
        return self

    def _extend_units(self):
        ids={l['product_uom_id'] for l in self.sales.values()}|{m['uom_id'] for m in self.moves.values()}|{m['uom_id'] for m in self.reservations.values()}
        units=self.env['uom.uom'].with_context(active_test=False).browse(sorted(ids))
        ids|={int(i) for u in units for i in (u.parent_path or '').split('/') if i}
        units=self.env['uom.uom'].with_context(active_test=False).browse(sorted(ids))
        self.reader.units.update({u.id:u for u in units});self.reader.commercial.by_uom.update(self.reader.units)
        self.reader.locked.append(('uom_uom',tuple(units.ids)))
        from .commercial_engine import uom_snapshot
        self.reader.sources['allocation_units']=[uom_snapshot(u) for u in units.sorted('id')]

    def qty(self,value,uid,pid):
        return self.reader.convert(value,uid,pid)

    def same(self,a,b,pid):
        unit=self.reader.units[self.reader.products[pid]['uom_id']]
        return unit.is_zero(float(a-b))

    def owners(self,mid):
        """All downstream sale-line owners; no first-match procurement winner."""
        if not hasattr(self,'owner_cache'):self.owner_cache={}
        if mid in self.owner_cache:return self.owner_cache[mid]
        queue=deque([mid]);seen=set();owners=set();unknown=False
        while queue:
            current=queue.popleft()
            if current in seen:continue
            seen.add(current);m=self.moves.get(current)
            if not m:unknown=True;continue
            if m['sale_line_id']:owners.add(m['sale_line_id'])
            for child in m['move_dest_ids']:queue.append(child)
        self.owner_cache[mid]=(owners,unknown)
        return owners,unknown

    def _demand(self):
        grouped=defaultdict(list)
        for m in self.moves.values():
            if m['sale_line_id']:grouped[m['sale_line_id']].append(m)
        labels={r.commercial_result_id.snapshot['proposal']['product_id']:r.commercial_result_id.snapshot['proposal']['product_name'] for r in self.reader.rows}
        for lid,source in self.sales.items():
            order=self.orders[source['order_id']];pid=source['product_id'];product=self.reader.products[pid]
            required=order['commitment_date'] or order.get('expected_date')
            required=datetime_value(required) if required else None
            codes=[];outstanding=None;delivered=None;ordered=None
            if not product['is_storable'] or product['type']!='consu' or not product['active']:
                codes.append('NON_STOCK_DEMAND')
            try:
                ordered=self.qty(source['product_uom_qty'],source['product_uom_id'],pid)
                if order['state']=='sale':
                    if source['qty_delivered_method']!='stock_move':codes.append('DELIVERY_METHOD_UNSUPPORTED')
                    moves=grouped[lid];gross=ZERO;pending=ZERO;cancelled=ZERO;returns=False;boundaries=0
                    for m in moves:
                        src,dst=self.locations[m['location_id']],self.locations[m['location_dest_id']]
                        if src['usage']=='customer':returns=True
                        if dst['usage']!='customer' or src['usage']=='customer':continue
                        boundaries+=1
                        if m['origin_returned_move_id']:returns=True
                        if src['company_id']!=self.batch.company_id.id or m['location_id'] not in self.reader.location_wh:
                            codes.append('DELIVERY_WAREHOUSE_UNCERTAIN')
                        amount=self.qty(m['quantity'] if m['state']=='done' else m['product_uom_qty'],m['uom_id'],pid)
                        if m['state']=='done':
                            gross+=amount
                            cancelled+=max(self.qty(m['product_uom_qty'],m['uom_id'],pid)-amount,ZERO)
                        elif m['state']=='cancel':cancelled+=amount
                        else:pending+=amount
                    delivered=self.qty(source['qty_delivered'],source['product_uom_id'],pid)
                    if returns:codes.append('RETURN_REPLACEMENT_REVIEW')
                    if not self.same(gross,delivered,pid):codes.append('DELIVERY_TOTAL_MISMATCH')
                    # Operational cancellation is not a commercial quantity
                    # amendment. Closed delivery remainder cannot erase an
                    # unchanged confirmed sales obligation. Historical cancelled
                    # flows are nonadditive when a replacement route exists.
                    if not boundaries or not self.same(ordered,gross+pending,pid):
                        codes.append('DELIVERY_BOUNDARY_MISMATCH')
                        if cancelled:codes.append('CANCELLED_DELIVERY_COMMITMENT_REVIEW')
                    if gross>ordered and not self.same(gross,ordered,pid):codes.append('DELIVERY_EXCEEDS_ORDER')
                    outstanding=max(ordered-gross,ZERO) if not codes else max(ordered-min(delivered,ordered),ZERO)
                else:
                    delivered=ZERO;outstanding=ordered
                if not required and outstanding:codes.append('DEMAND_DATE_UNKNOWN')
            except (ValueError,KeyError):codes.append('DEMAND_UOM_OR_QUANTITY_INVALID')
            if self.horizon and required and required>self.horizon:continue
            if outstanding==0 and not codes:continue
            row=dict(source_key='sale_line:'+str(lid),sale_line_id=lid,sale_order_id=source['order_id'],
                order_name=order['name'],customer_id=order['partner_id'],product_id=pid,
                product_name=labels[pid],
                warehouse_id=order['warehouse_id'],uom_id=product['uom_id'],demand_type='confirmed' if order['state']=='sale' else 'conditional',
                ordered=None if ordered is None else str(ordered),delivered=None if delivered is None else str(delivered),
                outstanding=None if outstanding is None else str(outstanding),required_date=str(required) if required else None,
                date_basis='customer_commitment' if order['commitment_date'] else 'order_expected_estimate',
                confirmation_date=fields.Datetime.to_string(datetime_value(order['date_order'])),reserved='0',free_stock='0',incoming='0',protected_incoming='0',
                new_procurement='0',unresolved=None if outstanding is None else '0',issues=sorted(set(codes)),
                status='unresolved' if codes else 'uncovered',source_fingerprint=digest(dict(line=source,order=order,moves=grouped[lid])))
            self.lines.append(row)
            for code in sorted(set(codes)):self.issue(code,row['source_key'],'Source demand requires review; no definite procurement is inferred for the unresolved portion.')
        def priority(row):
            required=row['required_date'] or '9999';confirmed=row['confirmation_date'] or '9999'
            dates=(required,confirmed) if self.policy['priority']=='required_date' else (confirmed,required)
            return (row['demand_type']!='confirmed',*dates,row['sale_order_id'],row['sale_line_id'])
        self.lines.sort(key=priority)
        self.by_line={l['sale_line_id']:l for l in self.lines}

    def _supply_pools(self):
        self.pools=defaultdict(list);self.uncertain=defaultdict(lambda:ZERO);self.reserved_pools={}
        for b in self.supply.bucket_ids:
            group=(b.product_id,b.warehouse_id.id)
            if b.source_key.startswith('quant:'):
                q=b.evidence['quant'];amount=math.number(b.eligible_free or '0')
                key='free:'+b.source_key
                self.pool(key,amount,b,group,'eligible_free_stock',str(self.supply.collected_at),set())
                if not b.quantity_verified:self.uncertain[group]+=max(math.number(q['quantity']),ZERO)
            elif b.kind=='incoming_purchase':
                evidence=b.evidence
                if not b.quantity_verified or b.incoming is False or b.incoming is None:
                    observed=math.number(evidence.get('observed_pending','0'))
                    self.uncertain[group]+=max(observed,ZERO);self.issue('INCOMING_QUANTITY_UNRESOLVED',b.source_key,'PR09 cannot verify this incoming quantity.')
                    continue
                # Split pending receipt legs, sharing the single PR09 PO-line cap.
                total=ZERO
                for leg in evidence['supplier_boundary']:
                    if leg['state'] in ('done','cancel'):continue
                    m=self.moves.get(leg['id'])
                    amount=self.qty(leg['product_uom_qty'],leg['uom_id'],b.product_id)
                    owners,unknown=self.owners(leg['id'])
                    if not m or unknown or len(owners)>1 or (m['procure_method']=='make_to_order' and not owners):
                        self.uncertain[group]+=amount;self.issue('PROCUREMENT_LINK_AMBIGUOUS',b.source_key,'Incoming lineage is incomplete or has multiple demand owners.');continue
                    eta=leg.get('date')
                    if not eta:
                        self.uncertain[group]+=amount;self.issue('ARRIVAL_DATE_UNKNOWN',b.source_key,'Undated incoming is not verified on-time supply.');continue
                    role=self.reader.classes.get(leg['location_dest_id'],{}).get('classification')
                    if role=='receiving' and self.policy['allow_receiving_buffer']:
                        eta=fields.Datetime.to_string(datetime_value(eta)+timedelta(hours=self.policy['receiving_buffer_hours']))
                    elif role!='saleable':
                        self.uncertain[group]+=amount
                        self.issue('SALEABLE_AVAILABILITY_UNVERIFIED',b.source_key,
                            'Receipt into Input/quality/staging/transit is not saleable availability. Input requires a documented planning delay; other holds require review.')
                        continue
                    key='incoming:move:'+str(leg['id'])
                    kind='protected_incoming_po' if math.number(b.protected or '0')>0 else 'incoming_cost_unverified'
                    self.pool(key,amount,b,group,kind,eta,owners);total+=amount
                    self.capacities[key]['date_basis']='supplier_receipt_plus_documented_input_delay' if role=='receiving' else 'supplier_receipt_to_saleable_location'
                if total>math.number(b.incoming):raise ValidationError('Incoming receipt capacity exceeds its PR09 PO-line bucket.')
        # Known ambiguous or unclassified scope never becomes definite new demand.
        for key,total in self.supply.totals.items():
            group=(total['product_id'],total['warehouse_id'])
            if not total['quantity_verified'] and self.uncertain[group]==0:
                self.uncertain[group]=None

    def pool(self,key,amount,bucket,group,kind,eta,owners):
        if key in self.capacities:raise ValidationError('Duplicate analytical source identity.')
        self.capacities[key]=dict(initial=str(amount),allocated='0',remaining=str(amount),source_key=bucket.source_key,
            supply_bucket_id=bucket.id,product_id=group[0],warehouse_id=group[1],allocation_type=kind,
            available_date=fields.Datetime.to_string(datetime_value(eta)),linked_sale_line_ids=sorted(owners))
        self.pools[group].append(key)

    @staticmethod
    def dimensions(row):
        return tuple(row.get(k) or False for k in ('product_id','location_id','lot_id','package_id','owner_id'))

    def _reservations(self):
        quants=defaultdict(list);mls=defaultdict(list)
        for b in self.supply.bucket_ids:
            if b.source_key.startswith('quant:'):quants[self.dimensions(b.evidence['quant'])].append(b)
        for ml in self.reservations.values():mls[self.dimensions(ml)].append(ml)
        for dims,buckets in quants.items():
            reserved=sum((math.number(b.reserved or '0') for b in buckets),ZERO)
            if not reserved:continue
            group=(dims[0],buckets[0].warehouse_id.id)
            rows=mls[dims];actual=sum((self.qty(m['quantity'],m['uom_id'],dims[0]) for m in rows),ZERO)
            if len(buckets)!=1 or not self.same(actual,reserved,dims[0]) or not buckets[0].quantity_verified:
                self.issue('RESERVATION_LINEAGE_UNKNOWN',buckets[0].source_key,'Quant reservations cannot be reconciled to exact active move-line dimensions.')
                if self.uncertain[group] is not None:self.uncertain[group]+=reserved
                continue
            b=buckets[0]
            if b.evidence['classification']!='saleable' or dims[4]:
                self.issue('RESERVED_LOCATION_REVIEW',b.source_key,'Reserved stock is outside verified usable location/ownership policy.')
                # Known ineligible Input/quality/consignment is not uncertain
                # usable capacity. Do not turn a known exclusion into coverage.
                continue
            for ml in rows:
                amount=self.qty(ml['quantity'],ml['uom_id'],dims[0]);owners,unknown=self.owners(ml['move_id'])
                if unknown or len(owners)!=1:
                    self.issue('RESERVATION_LINEAGE_UNKNOWN','move_line:'+str(ml['id']),'Reservation has no unique verifiable sale demand owner.')
                    if self.uncertain[group] is not None:self.uncertain[group]+=amount
                    continue
                owner=next(iter(owners))
                # Excluded owners' stock stays reserved and unavailable.
                if owner not in self.by_line:continue
                if self.by_line[owner]['demand_type']!='confirmed':
                    self.issue('RESERVATION_NONCONFIRMED_OWNER','move_line:'+str(ml['id']),
                        'A reservation linked to a draft/sent source is retained as unavailable; only confirmed commitments receive reservation-backed coverage.')
                    continue
                key='reserved:move_line:'+str(ml['id'])
                self.pool(key,amount,b,group,'existing_reserved_for_demand',str(self.supply.collected_at),owners)

    def entry(self,row,key,amount,kind):
        cap=self.capacities.get(key) if key else None
        self.entries.append(dict(demand_source_key=row['source_key'],capacity_key=key or kind+':'+row['source_key'],
            supply_bucket_id=cap['supply_bucket_id'] if cap else None,allocation_type=kind,quantity=str(amount),
            available_date=cap['available_date'] if cap else None,required_date=row['required_date'],
            source_evidence=cap.copy() if cap else {'basis':'calculated mutually exclusive remainder; not existing supply'},
            cost_confidence='protected_agreed_price' if kind=='protected_incoming_po' else 'price_unverified' if kind=='incoming_cost_unverified' else 'not_a_price_guarantee'))

    def _allocate(self):
        for index,row in enumerate(self.lines):
            row['priority']=index+1
            if row['outstanding'] is None:continue
            remaining=math.number(row['outstanding']);group=(row['product_id'],row['warehouse_id'])
            if row['issues']:
                row['unresolved']=str(remaining)
                if remaining:self.entry(row,None,remaining,'unresolved')
                continue
            keys=sorted(self.pools[group],key=lambda k:(
                0 if k.startswith('reserved:') else 1 if self.capacities[k]['linked_sale_line_ids'] else
                2 if k.startswith('free:') else 3,self.capacities[k]['available_date'] or '9999',k))
            for key in keys:
                cap=self.capacities[key];owners=cap['linked_sale_line_ids'];kind=cap['allocation_type']
                if owners and row['sale_line_id'] not in owners:continue
                if not remaining:break
                available=math.number(cap['remaining'])
                if not available:continue
                date=datetime_value(cap['available_date'])
                if date>datetime_value(row['required_date']):
                    self.issue('ARRIVAL_AFTER_REQUIRED_DATE',key,'Late potential supply is retained but not on-time coverage for '+row['source_key'])
                    continue
                used,remaining,left=take(remaining,available)
                if not used:continue
                cap['remaining']=str(left);cap['allocated']=str(math.number(cap['allocated'])+used)
                field='reserved' if key.startswith('reserved:') else 'free_stock' if key.startswith('free:') else 'incoming'
                row[field]=str(math.number(row[field])+used)
                if kind=='protected_incoming_po':row['protected_incoming']=str(math.number(row['protected_incoming'])+used)
                self.entry(row,key,used,kind)
            uncertain=self.uncertain[group]
            unresolved=remaining if uncertain is None else min(remaining,uncertain)
            if uncertain is not None:self.uncertain[group]-=unresolved
            row['unresolved']=str(unresolved);row['new_procurement']=str(remaining-unresolved)
            if unresolved:self.entry(row,None,unresolved,'unresolved')
            if remaining-unresolved:self.entry(row,None,remaining-unresolved,'new_procurement_requirement')
            covered=sum((math.number(row[k]) for k in ('reserved','free_stock','incoming')),ZERO)
            if not self.same(math.number(row['outstanding']),covered+math.number(row['new_procurement'])+unresolved,row['product_id']):
                raise ValidationError('Demand allocation does not reconcile.')
            row['status']='unresolved' if unresolved else 'fully_covered' if not remaining else 'partially_covered' if covered else 'uncovered'
        for cap in self.capacities.values():
            if math.number(cap['allocated'])+math.number(cap['remaining'])!=math.number(cap['initial']):
                raise ValidationError('Source allocation capacity does not reconcile.')
        # Unused ambiguous capacity is not a free source; never counted twice.

    def _totals(self):
        totals={}
        for row in self.lines:
            key=f"{row['product_id']}:{row['warehouse_id']}:{row['demand_type']}"
            total=totals.setdefault(key,dict(product_id=row['product_id'],warehouse_id=row['warehouse_id'],
                uom_id=row['uom_id'],demand_type=row['demand_type'],outstanding='0',reserved='0',free_stock='0',incoming='0',protected_incoming='0',new_procurement='0',unresolved='0'))
            for field in ('outstanding','reserved','free_stock','incoming','protected_incoming','new_procurement','unresolved'):
                total[field]=str(math.number(total[field])+math.number(row[field])) if total[field] is not None and row[field] is not None else None
        return totals
