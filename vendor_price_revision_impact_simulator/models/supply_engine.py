"""Bounded, read-only analytical projection. Never call operational actions here.

Privilege boundary: explicit grant -> fixed company/product/location domains ->
fixed field projections -> immutable app evidence. Not a generic source RPC.
"""
from collections import defaultdict
from decimal import Decimal

from odoo import fields
from odoo.exceptions import AccessError, UserError

from . import commercial_math as math
from .commercial_engine import CommercialEngine, POLICY_FIELDS, uom_snapshot
from .supply_governance import authorize, LOCATION, PREFIX
from .structural_validation import digest

LIMIT = 10000
SNAPSHOT, BUCKET, ISSUE, TERMS = [PREFIX + s for s in ('snapshot', 'bucket', 'issue', 'terms')]


class SupplyEngine:
    def __init__(self, batch, warehouses, costs, prepare=False):
        self.batch, self.env, self.costs = batch, batch.env, costs
        self.wh = authorize(batch, warehouses, costs, prepare)
        self.company = batch.company_id
        self.rows = batch.get_commercially_valid_rows()
        if not self.rows:
            raise UserError('No current commercially valid PR08 rows. Revalidate commercial evidence first.')
        # Product identity comes from immutable, current PR08 results, never raw SKU text.
        self.product_ids = sorted({r.commercial_result_id.snapshot['proposal']['product_id'] for r in self.rows})
        self.service = self.env(su=True, context=dict(self.env.context, allowed_company_ids=self.company.ids,
            force_company=self.company.id, active_test=False, prefetch_fields=False))
        self.sources, self.locked = {}, []
        self.buckets, self.issues = [], []
        self.scope_complete = True
        self.commercial = CommercialEngine(batch)

    def read(self, model, domain, names):
        records = self.service[model].with_company(self.company).search(domain, order='id', limit=LIMIT + 1)
        if len(records) > LIMIT:
            raise UserError('Supply source limit exceeded; narrow warehouse scope. No partial snapshot was created.')
        values = records.read(names, load=None)
        # Date/datetime evidence uses explicit ISO representations, not language formatting.
        for row in values:
            for key, value in row.items():
                if hasattr(value, 'isoformat'):
                    row[key] = value.isoformat()
        self.sources.setdefault(model, []).append(values)
        if records:
            self.locked.append((records._table, tuple(records.ids)))
        return {v['id']: v for v in values}

    def issue(self, code, key, message, quantity=False):
        self.issues.append({'code': code, 'source_key': key, 'message': message,
                            'quantity_blocking': quantity})

    def build(self):
        cid = self.company.id
        self.warehouses = self.read('stock.warehouse', [('company_id', '=', cid)],
            ['company_id', 'active', 'view_location_id', 'lot_stock_id', 'reception_steps'])
        self.locations = self.read('stock.location', [('company_id', '=', cid)],
            ['company_id', 'active', 'usage', 'parent_path'])
        classifications = self.read(LOCATION, [('company_id', '=', cid), ('warehouse_id', 'in', self.wh.ids)],
            ['warehouse_id', 'location_id', 'classification', 'active', 'version'])
        self.classes = {v['location_id']: v for v in classifications.values() if v['active']}
        self.location_wh = {}
        for lid, loc in self.locations.items():
            path = (loc['parent_path'] or '').split('/')
            matches = [wid for wid, wh in self.warehouses.items() if str(wh['view_location_id']) in path]
            if lid in self.classes and loc['usage'] == 'transit':
                matches = [self.classes[lid]['warehouse_id']]
            if len(matches) == 1 and matches[0] in self.wh.ids:
                self.location_wh[lid] = matches[0]
            elif len(matches) > 1 and set(matches) & set(self.wh.ids):
                self.scope_complete = False
                self.issue('WAREHOUSE_LOCATION_AMBIGUOUS', 'location:'+str(lid),
                    'Overlapping warehouse roots require configuration review; coverage is incomplete.', True)
        if self.costs:
            # Refresh delegated nonstored company cost context for same-session changes.
            self.env['product.template'].invalidate_model(['cost_method'])
            self.env['product.product'].invalidate_model(['cost_method'])
        self.products = self.read('product.product', [('id', 'in', self.product_ids), ('company_id', 'in', [False, cid])],
            ['company_id', 'active', 'uom_id', 'is_storable', 'type', 'tracking', 'categ_id'] +
            (['cost_method', 'standard_price', 'lot_valuated'] if self.costs else []))
        if set(self.products) != set(self.product_ids):
            raise UserError('A resolved product is missing or outside this company.')
        if self.costs:
            self.read('product.category', [('id', 'in', sorted({p['categ_id'] for p in self.products.values()}))],
                ['property_cost_method'])
        self.quants = self.read('stock.quant', [('company_id', '=', cid), ('product_id', 'in', self.product_ids),
            ('location_id', 'in', sorted(self.location_wh))],
            ['company_id', 'product_id', 'location_id', 'quantity', 'reserved_quantity', 'lot_id', 'package_id', 'owner_id'])
        lot_fields = ['product_id', 'company_id']
        if 'expiration_date' in self.service['stock.lot']._fields:
            lot_fields += ['expiration_date']
        self.lots = self.read('stock.lot', [('id', 'in', sorted({q['lot_id'] for q in self.quants.values() if q['lot_id']})),
            ('company_id', 'in', [False, cid])], lot_fields)
        self.lines = self.read('purchase.order.line', [('company_id', '=', cid), ('product_id', 'in', self.product_ids),
            ('order_id.picking_type_id.warehouse_id', 'in', self.wh.ids), ('display_type', '=', False),
            ('order_id.state', 'in', ['purchase', 'cancel'])],
            ['company_id', 'order_id', 'product_id', 'product_qty', 'qty_received', 'qty_received_method',
             'uom_id', 'date_planned', 'date_promised'] + (['price_unit', 'discount', 'tax_ids'] if self.costs else []))
        self.orders = self.read('purchase.order', [('id', 'in', sorted({v['order_id'] for v in self.lines.values()})),
            ('company_id', '=', cid)], ['company_id', 'state', 'locked', 'date_approve', 'currency_id',
            'picking_type_id', 'dest_address_id', 'partner_id', 'name'])
        self.types = self.read('stock.picking.type', [('id', 'in', sorted({o['picking_type_id'] for o in self.orders.values()})),
            ('company_id', '=', cid)], ['warehouse_id', 'code', 'company_id'])
        # Related internal moves are provenance only. Other internal transfers in
        # this scope are also retained without incrementing company supply.
        self.moves = self.read('stock.move', [('company_id', '=', cid), ('product_id', 'in', self.product_ids),
            '|', ('purchase_line_id', 'in', list(self.lines)), '&', ('state', 'not in', ['done', 'cancel']),
            '|', ('location_id', 'in', sorted(self.location_wh)), ('location_dest_id', 'in', sorted(self.location_wh))],
            ['company_id', 'product_id', 'purchase_line_id', 'picking_id', 'state', 'uom_id', 'quantity',
             'product_uom_qty', 'location_id', 'location_dest_id', 'origin_returned_move_id', 'to_refund', 'date'])
        # External boundary metadata contains no quantities or foreign cost. It is
        # needed to distinguish supplier, customer, transit and company locations.
        endpoints = {v[k] for v in self.moves.values() for k in ('location_id', 'location_dest_id')}
        self.endpoints = self.read('stock.location', [('id', 'in', sorted(endpoints))], ['usage', 'company_id', 'active'])
        for move in self.moves.values():
            if not move['purchase_line_id']:
                continue
            src, dst = self.endpoints[move['location_id']], self.endpoints[move['location_dest_id']]
            physical_endpoint = move['location_dest_id'] if src['usage'] == 'supplier' else move['location_id'] if dst['usage'] == 'supplier' else None
            if (physical_endpoint and self.endpoints[physical_endpoint]['usage'] == 'internal' and
                    physical_endpoint not in self.location_wh):
                # A PO's configured warehouse is not authority over a redirected
                # physical receipt/return in an unselected warehouse. Do not
                # publish its quantity or cost evidence through the PO lineage.
                raise AccessError('A linked physical receipt or return is outside the selected warehouse scope. Select an authorized scope for review.')
        uids = {p['uom_id'] for p in self.products.values()} | {l['uom_id'] for l in self.lines.values()} | {m['uom_id'] for m in self.moves.values()}
        units = self.env['uom.uom'].with_context(active_test=False).browse(sorted(uids))
        ancestor_ids = {int(i) for u in units for i in (u.parent_path or '').split('/') if i}
        units |= self.env['uom.uom'].browse(sorted(ancestor_ids))
        self.commercial.uoms |= units
        self.commercial.by_uom.update({u.id: u for u in units})
        self.units = {u.id: u for u in units}
        self.sources['uom.evidence'] = [uom_snapshot(u) for u in units.sorted('id')]
        self.sources['quantity_precision'] = {'Product Unit digits': self.env['decimal.precision'].precision_get('Product Unit'),
            'raw_quantities': 'preserved as reported; no integer truncation', 'reconciliation': 'target Odoo UoM is_zero'}
        self.locked.append(('uom_uom', tuple(units.ids)))
        self.sources['commercial'] = [{'row': r.id, 'result': r.commercial_result_id.id,
            'digest': r.commercial_result_id.input_digest} for r in self.rows]
        self.sources['policy'] = []
        self.policies = {}
        for row in self.rows:
            snap = row.commercial_result_id.snapshot
            date = fields.Date.to_date(snap['proposal']['effective_date'])
            policy = self.commercial.policy(date)
            if not policy:
                raise UserError('No current complete published company financial policy.')
            pid = row.commercial_result_id.snapshot['proposal']['product_id']
            selection = (policy, date)
            if pid in self.policies and self.policies[pid] != selection:
                self.policies[pid] = None
            else:
                self.policies[pid] = selection
            self.sources['policy'].append(dict(id=policy.id, **{k: str(policy[k]) for k in POLICY_FIELDS}))
        if self.costs:
            self.taxes = self.read('account.tax', [('id', 'in', sorted({t for l in self.lines.values() for t in l['tax_ids']})),
                ('company_id', '=', cid)], ['company_id', 'price_include', 'amount', 'amount_type', 'active'])
            currencies = self.env['res.currency'].with_context(active_test=False).browse(sorted({o['currency_id'] for o in self.orders.values()}))
            self.commercial.currencies |= currencies
            self.commercial.rates = self.env['res.currency.rate'].search([
                ('company_id', 'in', [False, self.company.root_id.id]),
                ('currency_id', 'in', self.commercial.currencies.ids), ('name', '<=', self.commercial.today)],
                order='company_id.id, name desc, id', limit=LIMIT + 1)
            if len(self.commercial.rates) > LIMIT:
                raise UserError('FX evidence limit exceeded.')
            self.sources['fx'] = self.commercial.rates.read(['currency_id', 'company_id', 'name', 'rate'], load=None)
            for v in self.sources['fx']: v['name'] = str(v['name'])
            self.locked.append(('res_currency_rate', tuple(self.commercial.rates.ids)))
        self.terms = self.env[TERMS].search([('batch_id', '=', self.batch.id), ('warehouse_id', 'in', self.wh.ids)], order='id') if self.costs else self.env[TERMS]
        self.sources['attestations'] = self.terms.read(['po_line_id', 'terms_digest', 'classification', 'state', 'verified_by'], load=None)
        for q in self.quants.values(): self.quant(q)
        moves_by_line = defaultdict(list)
        for m in self.moves.values(): moves_by_line[m['purchase_line_id']].append(m)
        for line in self.lines.values(): self.purchase(line, moves_by_line[line['id']])
        for move in self.moves.values():
            src, dst = self.endpoints[move['location_id']], self.endpoints[move['location_dest_id']]
            if (move['state'] not in ('done', 'cancel') and src['usage'] in ('internal', 'transit') and
                dst['usage'] in ('internal', 'transit')):
                whid = self.location_wh.get(move['location_id']) or self.location_wh.get(move['location_dest_id'])
                if whid:
                    self.buckets.append(dict(source_key='transfer:'+str(move['id']), product_id=move['product_id'],
                        warehouse_id=whid, kind='internal_transfer_reference', physical=None, reserved=None,
                        eligible_free='0', incoming='0', protected='0', contributes_quantity=False,
                        quantity_verified=True, cost_basis='not_incremental_supply', evidence=move))
        self.totals = self.aggregate()
        labels = {r.commercial_result_id.snapshot['proposal']['product_id']:
                  r.commercial_result_id.snapshot['proposal']['product_name'] for r in self.rows}
        for b in self.buckets:
            b['uom_id'] = self.products[b['product_id']]['uom_id']
            b['product_name'] = labels[b['product_id']]
            cost = b['evidence'].get('cost', {})
            b['unit_cost_reference'] = cost.get('unit_cost')
            b['confidence'] = 'quantity_verified' if b['quantity_verified'] else 'review_required'
        self.input_digest = digest({'scope': self.wh.ids, 'costs': self.costs, 'sources': self.sources,
            'buckets': self.buckets, 'issues': self.issues})
        authorize(self.batch, self.wh.ids, self.costs)
        return self

    def lock(self):
        self.env.flush_all()
        # Existing rows only; future inserts are caught by the fresh consumer
        # fingerprint. MVCC serialization/deadlocks abort, never partial success.
        for table, ids in sorted(set(self.locked)):
            if ids:
                self.env.cr.execute('SELECT id FROM '+table+' WHERE id IN %s ORDER BY id FOR SHARE', [ids])

    def convert(self, value, uid, product_id):
        source, target = self.units[uid], self.units[self.products[product_id]['uom_id']]
        self.commercial.pair(source, target)
        return math.quantity(value, source.factor, target.factor)

    def quant(self, q):
        key = 'quant:'+str(q['id']); p = self.products[q['product_id']]
        whid = self.location_wh[q['location_id']]; loc = self.locations[q['location_id']]
        role = self.classes.get(q['location_id'], {}).get('classification', 'unclassified')
        physical, reserved = math.number(q['quantity']), math.number(q['reserved_quantity'])
        free = physical - reserved
        reasons = []
        if physical < 0 or reserved < 0 or reserved > max(physical, 0): reasons.append('QUANT_ANOMALY')
        if role == 'unclassified': reasons.append('LOCATION_UNCLASSIFIED')
        if not p['active'] or not p['is_storable'] or p['type'] != 'consu': reasons.append('PRODUCT_NOT_TRACKED')
        if p['tracking'] in ('lot', 'serial') and not q['lot_id']: reasons.append('LOT_MISSING')
        lot = self.lots.get(q['lot_id'], {})
        expiry = lot.get('expiration_date')
        if expiry and fields.Datetime.to_datetime(expiry) <= fields.Datetime.now(): reasons.append('LOT_EXPIRED')
        if q['lot_id'] and (not lot or lot.get('product_id') != q['product_id']): reasons.append('LOT_INVALID')
        eligible = (role == 'saleable' and loc['usage'] == 'internal' and loc['active'] and
                    not q['owner_id'] and not reasons)
        kind = ('consignment_excluded' if q['owner_id'] else
                'received_pending_putaway' if role in ('receiving', 'quality') else
                'on_hand_free' if eligible and free > 0 else 'on_hand_reserved' if eligible else role)
        cost = {'state': 'not_requested', 'unit_cost': None}
        if self.costs:
            cost = {'state': 'unavailable', 'basis': p['cost_method'], 'unit_cost': None,
                'currency_id': self.company.currency_id.id, 'exact_acquisition_cost': False}
            if not q['owner_id'] and p['cost_method'] in ('standard', 'average') and math.number(p['standard_price']) > 0:
                cost.update(state='reference_only', unit_cost=str(p['standard_price']),
                    basis='standard_accounting_reference' if p['cost_method'] == 'standard' else 'company_avco_reference')
            elif not q['owner_id']: self.issue('STOCK_COST_UNAVAILABLE', key, 'Exact acquisition cost unavailable; no FIFO quant/location allocation inferred.')
        for reason in reasons: self.issue(reason, key, 'Physical evidence retained; eligible quantity withheld.', True)
        self.buckets.append(dict(source_key=key, product_id=q['product_id'], warehouse_id=whid, kind=kind,
            physical=str(physical), reserved=str(reserved), unreserved=str(free), eligible_free=str(max(free, 0)) if eligible else '0',
            incoming='0', protected='0', contributes_quantity=True, quantity_verified=not reasons,
            cost_basis=cost.get('basis', cost['state']), evidence=dict(quant=q, location=loc, classification=role, cost=cost)))

    def terms_evidence(self, line):
        order = self.orders[line['order_id']]
        unit_ids = {line['uom_id'], self.products[line['product_id']]['uom_id']}
        ancestors = {int(i) for uid in unit_ids for i in (self.units[uid].parent_path or '').split('/') if i}
        return {k: line[k] for k in ('id', 'product_id', 'product_qty', 'uom_id', 'price_unit', 'discount', 'tax_ids')} | {
            'normalization_units': [uom_snapshot(self.units[uid]) for uid in sorted(unit_ids | ancestors)],
            'order': {k: order[k] for k in ('id', 'company_id', 'state', 'currency_id', 'date_approve', 'picking_type_id', 'partner_id')}}

    def purchase(self, line, moves):
        key = 'po_line:'+str(line['id']); pid = line['product_id']; p = self.products[pid]
        order = self.orders[line['order_id']]; whid = self.types[order['picking_type_id']]['warehouse_id']
        errors, boundary, internal, returns = [], [], [], []
        incoming = done = cancelled = Decimal(0)
        try:
            ordered = self.convert(line['product_qty'], line['uom_id'], pid)
            for move in moves:
                src, dst = self.endpoints[move['location_id']], self.endpoints[move['location_dest_id']]
                if src['usage'] == 'supplier' and dst['usage'] in ('internal', 'transit'):
                    boundary.append(move)
                    if move['origin_returned_move_id']:
                        # Replacement chains need their own validated return balance.
                        # Retain evidence but withhold candidate quantity conservatively.
                        errors.append('REPLACEMENT_CHAIN_REVIEW')
                    if self.location_wh.get(move['location_dest_id']) != whid:
                        errors.append('RECEIPT_SCOPE_UNCERTAIN')
                    qty = self.convert(move['quantity'] if move['state'] == 'done' else move['product_uom_qty'], move['uom_id'], pid)
                    if move['state'] == 'done':
                        done += qty
                        # Odoo20 short-closing without a backorder keeps the done
                        # boundary's original demand; ordinary backorders split it.
                        planned = self.convert(move['product_uom_qty'], move['uom_id'], pid)
                        cancelled += max(planned - qty, Decimal(0))
                    elif move['state'] == 'cancel': cancelled += qty
                    else: incoming += qty
                elif dst['usage'] == 'supplier': returns.append(move)
                elif src['usage'] == 'supplier' and dst['usage'] == 'customer': errors.append('DROPSHIP_EXCLUDED')
                else: internal.append(move)
            if not boundary and ordered > 0: errors.append('RECEIPT_BOUNDARY_MISSING')
            if not self.units[p['uom_id']].is_zero(float(ordered - done - incoming - cancelled)):
                errors.append('RECEIPT_RECONCILIATION_REQUIRED')
            returned = sum((self.convert(m['quantity'], m['uom_id'], pid) for m in returns
                if m['state'] == 'done' and (not m['origin_returned_move_id'] or m['to_refund'])), Decimal(0))
            reported_received = self.convert(line['qty_received'], line['uom_id'], pid) if line['qty_received'] >= 0 else None
            if reported_received is None or not self.units[p['uom_id']].is_zero(float(done-returned-reported_received)):
                errors.append('RECEIVED_TOTAL_MISMATCH')
            if not p['active'] or not p['is_storable'] or line['qty_received_method'] != 'stock_moves': errors.append('NON_STOCK_COMMITMENT')
            if order['state'] == 'cancel' and incoming: errors.append('CANCELLED_ORDER_ACTIVE_RECEIPT')
        except (ValueError, KeyError):
            errors.append('RECEIPT_UOM_INVALID'); ordered = None
        cost = {'state': 'not_requested', 'unit_cost': None}
        protected = Decimal(0)
        if self.costs:
            terms = self.terms_evidence(line); td = digest(terms)
            attest = self.terms.filtered(lambda t: t.po_line_id == line['id'])[-1:]
            firm = bool(attest and attest.state == 'verified' and attest.classification == 'firm' and
                        attest.terms_digest == td and attest.verified_by.active and
                        attest.verified_by.has_group('vendor_price_revision_impact_simulator.group_vpr_purchase_manager') and
                        self.company in attest.verified_by.company_ids)
            cost = dict(state='incomplete', unit_cost=None, original_terms=terms,
                terms_digest=td, firm_verified=firm, attestation_id=attest.id if attest else None)
            try:
                if not self.policies[pid]: raise ValueError('COMMERCIAL_COST_DATE_AMBIGUOUS')
                policy, effective = self.policies[pid]
                if any(t not in self.taxes or self.taxes[t]['price_include'] for t in line['tax_ids']):
                    raise ValueError('TAX_INCLUSIVE_COST_UNSUPPORTED')
                if policy.additional_cost_policy != 'exclude': raise ValueError('ADDITIONAL_CHARGES_UNRESOLVED')
                self.commercial.pair(self.units[line['uom_id']], self.units[p['uom_id']])
                net = math.net_price(line['price_unit'], self.units[line['uom_id']].factor,
                    self.units[p['uom_id']].factor, line['discount'])
                date = policy.currency_reference_date if policy.currency_rate_policy == 'company_reference_date' else effective
                fx = self.commercial.fx(self.env['res.currency'].browse(order['currency_id']), date, policy)
                if fx['hypothetical']: raise ValueError('HYPOTHETICAL_COMMITMENT_FX')
                cost.update(state='agreed_reference', unit_cost=str(math.converted(net, fx['rate'])),
                    currency_id=self.company.currency_id.id, fx=fx, policy_id=policy.id)
                if firm and not errors and policy.commitment_policy == 'preserve_agreed_prices': protected = incoming
            except (ValueError, KeyError) as exc:
                self.issue(str(exc), key, 'Incoming quantity retained separately from incomplete cost.')
            if not firm: self.issue('COMMITMENT_NOT_VERIFIED_FIRM', key, 'Confirmed or locked PO is not proof of guaranteed price.')
        for error in sorted(set(errors)): self.issue(error, key, 'Source retained; incoming quantity requires review.', True)
        self.buckets.append(dict(source_key=key, product_id=pid, warehouse_id=whid, kind='incoming_purchase',
            physical='0', reserved='0', eligible_free='0', incoming=None if errors else str(incoming),
            protected=str(protected), contributes_quantity=True, quantity_verified=not errors,
            cost_basis=cost['state'], evidence=dict(line=line, order=order, supplier_boundary=boundary,
                nonadditive_internal=internal, nonadditive_returns=returns, observed_pending=str(incoming),
                ordered=None if ordered is None else str(ordered), gross_received=str(done), cancelled=str(cancelled), cost=cost)))

    def aggregate(self):
        totals = {}
        grouped = defaultdict(list)
        for b in self.buckets:
            if b['contributes_quantity']: grouped[(b['product_id'], b['warehouse_id'])].append(b)
        for pid, product in self.products.items():
            for wh in self.wh:
                items = grouped[(pid, wh.id)]
                known = self.scope_complete and all(b['quantity_verified'] for b in items) and product['is_storable'] and product['active']
                row = dict(product_id=pid, warehouse_id=wh.id, uom_id=product['uom_id'], quantity_verified=bool(known))
                for field in ('physical', 'reserved', 'eligible_free', 'incoming', 'protected'):
                    values = [b.get(field) for b in items]
                    row[field] = str(sum((math.number(v) for v in values if v is not None), Decimal(0))) if all(v is not None for v in values) and product['is_storable'] else None
                row['candidate_supply'] = str(math.number(row['eligible_free']) + math.number(row['incoming'])) if known else None
                row['free_plus_protected'] = str(math.number(row['eligible_free']) + math.number(row['protected'])) if known else None
                row['unverified_incoming'] = str(math.number(row['incoming'])-math.number(row['protected'])) if row['incoming'] is not None else None
                row['received_pending_putaway'] = str(sum((math.number(b['physical']) for b in items
                    if b['kind'] == 'received_pending_putaway'), Decimal(0))) if product['is_storable'] else None
                if not self.scope_complete:
                    row['physical'] = row['reserved'] = None
                totals[str(pid)+':'+str(wh.id)] = row
        return totals
