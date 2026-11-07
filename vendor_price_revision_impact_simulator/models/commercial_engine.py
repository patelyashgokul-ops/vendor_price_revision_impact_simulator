"""Scoped read-only commercial resolver. No master writes or RFQ cost fallback."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, localcontext

from odoo import fields
from odoo.exceptions import UserError, AccessError

from . import commercial_math as money
from .structural_validation import digest

LIMIT = 10000
MATERIAL = ('vendor_product_code', 'product_identifier_raw', 'proposed_price_raw',
            'currency_raw', 'purchase_uom_raw', 'min_qty_raw', 'effective_date_raw')
POLICY_FIELDS = ('policy_version', 'currency_rate_policy', 'currency_reference_date',
    'cost_basis', 'stock_cost_policy', 'replacement_cost_policy', 'commitment_policy', 'validity_policy',
    'fx_override_policy', 'uom_policy', 'tax_basis', 'tax_inclusive_policy',
    'unknown_tax_policy', 'additional_cost_policy', 'rounding_policy',
    'allow_future_dated_revisions', 'backdated_proposal_policy', 'expired_offer_policy',
    'quantity_tier_basis', 'ambiguous_price_policy')


def uom_snapshot(uom):
    return {'id': uom.id, 'name': uom.with_context(lang=None).name,
        'factor': str(uom.factor), 'relative_factor': str(uom.relative_factor),
        'relative_uom_id': uom.relative_uom_id.id, 'parent_path': uom.parent_path,
        'active': uom.active}


def supplier_snapshot(rule):
    return {'id': rule.id, 'company_id': rule.company_id.id, 'vendor_id': rule.partner_id.id,
        'product_id': rule.product_id.id, 'template_id': rule.product_tmpl_id.id,
        'min_qty': str(rule.min_qty), 'price': str(rule.price), 'discount': str(rule.discount),
        'currency_id': rule.currency_id.id, 'currency_code': rule.currency_id.name, 'uom_id': rule.uom_id.id,
        'date_start': str(rule.date_start) if rule.date_start else None,
        'date_end': str(rule.date_end) if rule.date_end else None,
        'sequence': rule.sequence, 'write_date': str(rule.write_date)}


class CommercialEngine:
    def __init__(self, batch):
        batch.ensure_one()
        batch.check_access('read')
        self.batch, self.env = batch, batch.env
        self.company, self.vendor = batch.company_id, batch.vendor_id
        self.today = fields.Date.context_today(batch)
        self.context = batch.current_commercial_context_id
        self.settings = self.context.assumptions if self.context else {}
        _, self.product_plans = batch._product_plans()
        self.products = {}
        for row in batch.row_ids:
            state, product = row._current_product_outcome(self.product_plans[row.id])
            if state in ('auto_matched', 'manual_matched') and product:
                self.products[row.id] = product
        product_ids = [p.id for p in self.products.values()]
        self.product_records = self.env['product.product'].browse(product_ids)
        self.suppliers = self.env['product.supplierinfo'].search([
            ('partner_id', '=', self.vendor.id), ('company_id', 'in', [False, self.company.id]),
            ('product_tmpl_id', 'in', self.product_records.product_tmpl_id.ids)], limit=LIMIT + 1)
        supplier_ids = defaultdict(list)
        for supplier in self.suppliers:
            supplier_ids[supplier.product_tmpl_id.id].append(supplier.id)
        self.suppliers_by_template = {tid: self.env['product.supplierinfo'].browse(ids)
                                      for tid, ids in supplier_ids.items()}
        codes = {r.effective_values.get('currency_raw', '').strip() for r in batch.row_ids}
        self.currencies = self.env['res.currency'].with_context(active_test=False).search([
            '|', ('name', 'in', list(codes)), ('id', 'in', (self.suppliers.currency_id | self.company.currency_id).ids)])
        self.by_currency = {c.name: c for c in self.currencies}
        names = {r.effective_values.get('purchase_uom_raw', '').strip() for r in batch.row_ids}
        aliases = self.settings.get('uom_aliases', {})
        self.uoms = self.env['uom.uom'].with_context(active_test=False, lang=None).search([
            '|', ('name', 'in', list(names)), ('id', 'in', list(aliases.values()) +
                (self.product_records.uom_id | self.suppliers.uom_id).ids)], limit=LIMIT + 1)
        ancestor_ids = {int(i) for u in self.uoms for i in (u.parent_path or '').split('/') if i}
        self.uoms |= self.env['uom.uom'].browse(sorted(ancestor_ids))
        self.by_uom = {u.id: u for u in self.uoms}
        self.by_name = defaultdict(list)
        for uom in self.uoms:
            self.by_name[uom.with_context(lang=None).name].append(uom)
        root = self.company.root_id
        self.rate_company_allowed = root == self.company or root in self.env.companies
        self.rates = self.env['res.currency.rate'].search([
            ('company_id', 'in', [False, root.id]), ('currency_id', 'in', self.currencies.ids),
            ('name', '<=', self.today)], order='company_id.id, name desc, id', limit=LIMIT + 1
        ) if self.rate_company_allowed else self.env['res.currency.rate']
        self.overflow = any(len(records) > LIMIT for records in (self.suppliers, self.rates, self.uoms))
        self.policy_cache, self.fx_cache, self.uom_cache = {}, {}, {}
        self.context_valid = bool(self.context and self.context.state == 'verified' and
            self.context.verified_by.active and
            self.context.source_digest == batch._commercial_scope_digest() and
            all(uom_snapshot(self.by_uom[int(uid)]) == evidence
                for uid, evidence in (self.context.uom_evidence or {}).items() if int(uid) in self.by_uom) and
            all(int(uid) in self.by_uom for uid in (self.context.uom_evidence or {})) and
            (not self.settings.get('historical_attestation') or
             (self.context.baseline_evidence or []) == [supplier_snapshot(s) for s in self.suppliers]))

    def policy(self, date):
        if date not in self.policy_cache:
            try:
                self.policy_cache[date] = self.env['vendor.price.revision.config'].get_company_revision_config(self.company, date)
            except (UserError, AccessError):
                self.policy_cache[date] = self.env['vendor.price.revision.config']
        return self.policy_cache[date]

    def pair(self, source, target):
        cache_key = (source.id, target.id)
        if cache_key not in self.uom_cache:
            if not source or not target or not source.active or not target.active or not source._has_common_reference(target):
                raise ValueError('UOM_INCOMPATIBLE')
            ancestors = {int(i) for u in (source | target) for i in (u.parent_path or '').split('/') if i}
            evidence = [uom_snapshot(self.by_uom[i]) for i in sorted(ancestors)]
            if any(money.number(v['factor']) <= 0 or money.number(v['relative_factor']) <= 0 or not v['active'] for v in evidence):
                raise ValueError('UOM_FACTOR_MISSING')
            self.uom_cache[cache_key] = {'source': uom_snapshot(source), 'comparison': uom_snapshot(target),
                'ancestors': evidence, 'method': 'odoo20_common_reference_and_inverse_price_factor'}
        return self.uom_cache[cache_key]

    def fx(self, currency, date, policy):
        cache_key = (currency.id, date, policy.id)
        if cache_key in self.fx_cache:
            return self.fx_cache[cache_key]
        company_currency = self.company.currency_id
        evidence = {'source_currency_id': currency.id, 'target_currency_id': company_currency.id,
            'company_id': self.company.id, 'requested_date': str(date), 'hypothetical': False}
        if currency == company_currency:
            evidence.update(rate='1', method='same_currency_identity', rate_records=[])
        elif policy.currency_rate_policy == 'authorized_scenario_rate':
            scenario = self.settings.get('scenario_rates', {}).get(currency.name)
            finance = self.context.verified_by.has_group('vendor_price_revision_impact_simulator.group_vpr_finance_manager')
            if not scenario or not finance or policy.fx_override_policy != 'finance_governed' or not self.settings.get('scenario_reference'):
                raise ValueError('FX_RATE_MISSING')
            rate = money.number(scenario)
            if rate <= 0:
                raise ValueError('FX_RATE_MISSING')
            evidence.update(rate=str(rate), method='finance_verified_scenario_company_units_per_source_unit',
                hypothetical=True, reference=self.settings['scenario_reference'],
                context_id=self.context.id, verified_by=self.context.verified_by.id, rate_records=[])
        else:
            if date > self.today:
                raise ValueError('FX_DATE_UNSUPPORTED')
            if not self.rate_company_allowed:
                raise ValueError('FX_RATE_MISSING')
            selected = []
            for curr in (currency | company_currency):
                # Odoo20 _get_rates uses a strict before-date cutoff and prefers
                # root-company rates over shared rates. Never its 1/earliest fallback.
                choices = self.rates.filtered(lambda r: r.currency_id == curr and r.name < date)
                chosen = choices[:1]
                if not chosen or money.number(chosen.rate) <= 0:
                    raise ValueError('FX_RATE_MISSING')
                selected.append({'id': chosen.id, 'currency_id': curr.id, 'date': str(chosen.name),
                    'company_id': chosen.company_id.id, 'technical_rate': str(chosen.rate)})
            indexed = {s['currency_id']: s for s in selected}
            with localcontext() as ctx:
                ctx.prec = 38
                rate = money.number(indexed[company_currency.id]['technical_rate']) / money.number(indexed[currency.id]['technical_rate'])
            evidence.update(rate=str(rate), rate_records=selected, method='odoo20_guarded_target_rate_divided_by_source_rate',
                rate_company_id=self.company.root_id.id)
        self.fx_cache[cache_key] = evidence
        return evidence

    def tier(self, product, quantity, quantity_uom, date, policy):
        self.pair(quantity_uom, product.uom_id)
        normalized = money.quantity(quantity, quantity_uom.factor, product.uom_id.factor)
        # Reuse the target-version company/variant/partner eligibility helper on
        # an already bulk-scoped recordset, never unrestricted seller lookup.
        pool = self.suppliers_by_template.get(product.product_tmpl_id.id, self.env['product.supplierinfo'])
        rules = pool._get_filtered_supplier(self.company, product, {'partner_id': self.vendor})
        candidates, rejected = [], []
        for rule in rules:
            if rule.product_tmpl_id != product.product_tmpl_id or (rule.date_start and rule.date_start > date) or (rule.date_end and rule.date_end < date):
                continue
            try:
                pair = self.pair(rule.uom_id, product.uom_id)
                threshold = money.quantity(rule.min_qty, rule.uom_id.factor, product.uom_id.factor)
                if normalized < threshold:
                    continue
                discount = money.number(rule.discount, True)
                if discount > 100 or not rule.currency_id.active:
                    raise ValueError('DISCOUNT_BASIS_UNKNOWN' if discount > 100 else 'CURRENCY_INACTIVE')
                net = money.net_price(rule.price, rule.uom_id.factor, product.uom_id.factor, discount)
                candidates.append({'record': rule, 'evidence': supplier_snapshot(rule), 'uom': pair,
                    'threshold': str(threshold), 'net': net})
            except ValueError as exc:
                rejected.append({'id': rule.id, 'code': str(exc)})
        if rejected:
            return {'status': 'baseline_conflict', 'code': 'BASELINE_INVALID_TERMS', 'rejected': rejected, 'candidates': []}
        if not candidates:
            return {'status': 'baseline_unavailable', 'code': 'BASELINE_UNAVAILABLE', 'candidates': []}
        # APP06's explicit conservative scope/specificity contract is stricter
        # than RFQ's unrestricted cheapest-price fallback. Within that scope use
        # the verified Odoo20 discounted-price/sequence order, with conflict gates.
        if any(c['record'].company_id for c in candidates):
            candidates = [c for c in candidates if c['record'].company_id == self.company]
        if any(c['record'].product_id == product for c in candidates):
            candidates = [c for c in candidates if c['record'].product_id == product]
        thresholds = defaultdict(list)
        for c in candidates:
            thresholds[(money.number(c['threshold']), c['record'].sequence)].append(c)
        evidence = [dict(c['evidence'], normalized_min_qty=c['threshold'], net_comparable=str(c['net']), uom=c['uom']) for c in candidates]
        if any(len(v) > 1 for v in thresholds.values()):
            return {'status': 'baseline_conflict', 'code': 'BASELINE_CONFLICT', 'candidates': evidence}
        currencies = {c['record'].currency_id.id for c in candidates}
        try:
            for c in candidates:
                rate = self.fx(c['record'].currency_id, date, policy) if len(currencies) > 1 else None
                c['ranking_price'] = money.converted(c['net'], rate['rate']) if rate else c['net']
                c['ranking_fx'] = rate
        except ValueError as exc:
            return {'status': 'baseline_conflict', 'code': str(exc), 'candidates': evidence}
        candidates.sort(key=lambda c: (c['ranking_price'], c['record'].sequence))
        if len(candidates) > 1 and (candidates[0]['ranking_price'], candidates[0]['record'].sequence) == (candidates[1]['ranking_price'], candidates[1]['record'].sequence):
            return {'status': 'baseline_conflict', 'code': 'BASELINE_CONFLICT', 'candidates': evidence}
        chosen = candidates[0]
        return {'status': 'selected', 'code': None, 'selected': chosen['evidence'],
            'net_comparable': str(chosen['net']), 'normalized_quantity': str(normalized),
            'normalized_min_qty': chosen['threshold'], 'uom': chosen['uom'], 'candidates': evidence,
            'ranking_fx': chosen['ranking_fx'],
            'precedence': 'exact_vendor;company_before_shared;variant_before_template;eligible_discounted_price;sequence;ties_review',
            'source_classification': 'observed_vendor_pricelist_terms_not_PO_or_accounting_cost'}

    def plans(self):
        plans = {row.id: self.row_plan(row) for row in self.batch.row_ids}
        groups = defaultdict(list)
        for row in self.batch.row_ids:
            plan = plans[row.id]
            if plan.get('proposal'):
                p = plan['proposal']
                groups[(p['product_id'], money.number(p['normalized_min_qty']))].append(plan)
        for group in groups.values():
            cluster, through = [], ''
            def finish_cluster():
                if len(cluster) > 1:
                    ids = sorted(p['row_id'] for p in cluster)
                    for plan in cluster:
                        self.issue(plan, 'TIER_AMBIGUOUS', 'tier_conflict', 'Overlapping proposed rows have the same normalized tier threshold; review all rows, currencies and units.')
                        plan['tier_conflict_rows'] = ids[:40]
                        plan['tier_conflict_count'] = len(ids)
            for plan in sorted(group, key=lambda p: p['proposal']['effective_date']):
                if cluster and plan['proposal']['effective_date'] > through:
                    finish_cluster()
                    cluster, through = [], ''
                cluster.append(plan)
                through = max(through, plan['proposal']['end_date'] or '9999-12-31')
            finish_cluster()
        for plan in plans.values():
            plan['fingerprint'] = digest({k: v for k, v in plan.items() if k != 'fingerprint'})
        return plans

    @staticmethod
    def issue(plan, code, status, message, severity='error'):
        plan['issues'].append({'code': code, 'severity': severity, 'message': message})
        if severity != 'info' and plan['status'] in ('commercially_valid', 'pending_validation'):
            plan['status'] = status

    def row_plan(self, row):
        values = row.effective_values
        plan = {'row_id': row.id, 'status': 'pending_validation', 'issues': [],
            'inputs': {k: values.get(k) for k in MATERIAL}, 'company_id': self.company.id,
            'vendor_id': self.vendor.id, 'context_id': self.context.id,
            'context_state': self.context.state if self.context else None,
            'context_valid': self.context_valid, 'context_assumptions': self.settings,
            'today': str(self.today), 'product_digest': self.product_plans[row.id]['fingerprint'],
            'source_hash': self.batch.sha256_digest}
        if row.excluded:
            plan['status'] = 'excluded'
            return plan
        if row.id not in self.products:
            self.issue(plan, 'PRODUCT_MAPPING_STALE', 'pending_product', 'Current structural and product-resolution gates must both pass.')
            return plan
        if not self.context_valid:
            self.issue(plan, 'COMMERCIAL_CONTEXT_UNVERIFIED', 'needs_review', 'Independently verify unchanged commercial context and UoM aliases before comparison.')
            return plan
        if self.overflow:
            self.issue(plan, 'EVIDENCE_LIMIT', 'blocked', 'Commercial evidence exceeds the supported bound; narrow the batch.')
            return plan
        product = self.products[row.id]
        parsed = row.current_result_id.parsed_candidates
        try:
            effective = fields.Date.to_date(parsed.get('effective_date_raw'))
            end = fields.Date.to_date(self.settings.get('end_date'))
            baseline_date = fields.Date.to_date(self.settings.get('baseline_date')) if self.settings.get('baseline_mode') == 'explicit' else effective - timedelta(days=1)
            if (end and end < effective) or baseline_date >= effective:
                raise ValueError('INVALID_EFFECTIVE_PERIOD')
        except (ValueError, TypeError, OverflowError):
            self.issue(plan, 'INVALID_EFFECTIVE_PERIOD', 'date_conflict', 'Use ordered inclusive proposal dates and an old baseline date before the proposed start.')
            return plan
        plan.update(effective_date=str(effective), baseline_date=str(baseline_date), end_date=str(end) if end else None)
        policy = self.policy(effective)
        if not policy:
            self.issue(plan, 'POLICY_UNAVAILABLE', 'needs_review', 'A unique complete published PR04 company policy is required.')
            return plan
        plan['policy'] = dict({name: str(policy[name]) if policy._fields[name].type == 'date' else policy[name] for name in POLICY_FIELDS}, id=policy.id, company_currency_id=policy.currency_id.id)
        if (effective > self.today and not policy.allow_future_dated_revisions) or (effective < self.today and policy.backdated_proposal_policy == 'block'):
            self.issue(plan, 'DATE_POLICY', 'date_conflict', 'Proposed date is not allowed by the published company policy.')
        elif effective < self.today or (end and end < self.today):
            self.issue(plan, 'HISTORICAL_OFFER_REVIEW', 'needs_review', 'Historical/expired proposal is evidence only and requires commercial review; no backdated application is authorized.')
        if self.settings.get('price_basis') != 'net_exclusive' or policy.additional_cost_policy != 'exclude':
            self.issue(plan, 'TAX_BASIS_UNKNOWN', 'needs_review', 'Only explicitly verified tax-exclusive net supplier prices without unevidenced additional charges can complete comparison.')
            return plan
        source_text = values.get('purchase_uom_raw', '').strip()
        alias_id = self.settings.get('uom_aliases', {}).get(source_text)
        choices = [self.by_uom[alias_id]] if alias_id in self.by_uom else self.by_name.get(source_text, [])
        if len(choices) != 1:
            self.issue(plan, 'UOM_UNKNOWN' if not choices else 'UOM_AMBIGUOUS', 'uom_invalid', 'Supplier UoM must resolve to one verified reference; aliases are never guessed.')
            return plan
        source_uom = choices[0]
        try:
            pair = self.pair(source_uom, product.uom_id)
        except ValueError as exc:
            self.issue(plan, str(exc), 'uom_invalid', 'Source and product units need active positive factors and a common Odoo20 reference hierarchy.')
            return plan
        currency = self.by_currency.get(values.get('currency_raw', '').strip())
        if not currency or not currency.active or not self.company.currency_id.active:
            self.issue(plan, 'CURRENCY_INACTIVE' if currency else 'CURRENCY_UNKNOWN', 'blocked', 'Use an active exact currency code and active company currency.')
            return plan
        try:
            raw_price = money.number(parsed.get('proposed_price_raw'), True)
            qty = money.number(parsed.get('min_qty_raw'), True)
            discount = money.number(self.settings.get('discount_percent', '0'), True)
            if discount > 100:
                raise ValueError('discount')
            normalized = money.net_price(raw_price, source_uom.factor, product.uom_id.factor, discount)
            threshold = money.quantity(qty, source_uom.factor, product.uom_id.factor)
        except ValueError:
            self.issue(plan, 'INVALID_PRICE_MOQ_DISCOUNT', 'blocked', 'Price, MOQ and discount must be finite, nonnegative and on the verified net price basis.')
            return plan
        plan['proposal'] = {'product_id': product.id, 'product_name': product.display_name,
            'source_uom_id': source_uom.id, 'comparison_uom_id': product.uom_id.id, 'uom': pair,
            'source_currency_id': currency.id, 'company_currency_id': self.company.currency_id.id,
            'source_currency_code': currency.name, 'company_currency_code': self.company.currency_id.name,
            'source_price': str(raw_price), 'discount_percent': str(discount), 'net_comparable': str(normalized),
            'source_min_qty': str(qty), 'normalized_min_qty': str(threshold), 'effective_date': str(effective),
            'end_date': str(end) if end else None, 'price_basis': self.settings['price_basis'],
            'currency_rounding': str(self.company.currency_id.rounding)}
        fx_date = policy.currency_reference_date if policy.currency_rate_policy == 'company_reference_date' else effective
        try:
            new_fx = self.fx(currency, fx_date, policy)
            proposed_company = money.converted(normalized, new_fx['rate'])
            plan['proposal'].update(fx=new_fx, company_price=str(proposed_company),
                reported_company_price=money.rounded(proposed_company, self.company.currency_id.rounding))
            plan['proposal_normalized'] = True
        except ValueError as exc:
            self.issue(plan, str(exc), 'fx_rate_missing', 'Explicit authorized company/date FX evidence is missing; no 1:1 or forecast fallback is used.')
        baseline = self.tier(product, qty, source_uom, baseline_date, policy)
        plan['baseline'] = baseline
        if baseline['status'] != 'selected':
            self.issue(plan, baseline['code'], baseline['status'], 'No unique authorized applicable vendor-pricelist baseline exists for this quantity/date.')
            return plan
        if baseline_date < self.today and not self.settings.get('historical_attestation'):
            baseline['status'] = 'unverified'
            self.issue(plan, 'BASELINE_UNVERIFIED', 'baseline_unavailable', 'Current supplierinfo contents do not prove historical agreement. Independent documented historical attestation is required.')
            return plan
        elif baseline_date < self.today:
            baseline['historical_attestation'] = self.settings['historical_attestation']
            baseline['attestation_context_id'] = self.context.id
        baseline_currency = self.env['res.currency'].browse(baseline['selected']['currency_id'])
        try:
            old_date = fx_date if self.settings.get('comparison_mode') == 'same_rate' else baseline_date
            old_fx = self.fx(baseline_currency, old_date, policy)
            old_company = money.converted(baseline['net_comparable'], old_fx['rate'])
            baseline.update(fx=old_fx, company_price=str(old_company),
                reported_company_price=money.rounded(old_company, self.company.currency_id.rounding),
                observed_at=str(self.today), as_of=str(baseline_date))
            if plan.get('proposal_normalized'):
                comparison = money.comparison(old_company, proposed_company)
                comparison.update(method=self.settings['comparison_mode'], comparison_uom_id=product.uom_id.id,
                    comparison_quantity=str(threshold), currency_id=self.company.currency_id.id)
                if baseline_currency == currency:
                    comparison['decomposition'] = money.decomposition(baseline['net_comparable'], normalized, old_fx['rate'], new_fx['rate'])
                    comparison['source_currency_comparison'] = money.comparison(baseline['net_comparable'], normalized)
                else:
                    comparison['decomposition'] = {'method': 'not_comparable_source_currencies',
                        'supplier_component': None, 'fx_component': None, 'total': comparison['delta']}
                plan['comparison'] = comparison
        except ValueError as exc:
            self.issue(plan, str(exc), 'fx_rate_missing', 'Old-price conversion requires its own documented rate evidence.')
        future = self.suppliers.filtered(lambda s: s.product_tmpl_id == product.product_tmpl_id and
            (not s.product_id or s.product_id == product) and s.date_start and s.date_start >= effective and
            (not end or s.date_start <= end))
        if future:
            plan['overlapping_future_rules'] = [supplier_snapshot(s) for s in future]
            self.issue(plan, 'PRICE_RULE_OVERLAP', 'date_conflict', 'Existing future vendor rules overlap the proposed period; resolve commercial intent before completing comparison.')
        if not plan['issues'] and plan.get('comparison'):
            plan['status'] = 'commercially_valid'
        return plan
