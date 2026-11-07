"""Authorized retained-fact reports. No operational actions or sudo reads.

Explicit source IDs are intentional: this first reporting contract never silently
chooses one of several overlapping analytical versions for the reader.
"""
import re
from decimal import Decimal, InvalidOperation, localcontext
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.binary import BinaryBytes

from . import reporting_data as report_data
from .profitability_math import AMOUNTS

MODULE = 'vendor_price_revision_impact_simulator'
WIZARD = 'vendor.price.revision.report.wizard'
P = 'vendor.price.revision.'
MON = P + 'application.monitor.'
# Report code: (label, exact source model, optional detail relation, fields,
#              source timestamp, finance-only).
CATALOG = {
    'VENDOR_REVISION_SUMMARY': ('Vendor revision summary', P+'commercial.validation', None,
        'product_id version status classification proposal_normalized validated_at', 'validated_at', False),
    'FINANCIAL_IMPACT': ('Financial impact', P+'financial.snapshot', 'line_ids',
        'product_id vendor_id warehouse_id comparison_uom_id currency_id quantity demand_type source_type baseline_extended_cost revised_extended_cost incremental_extended_cost status cost_complete delta_complete', 'collected_at', True),
    'GROSS_PROFIT_MARGIN': ('Gross profit and margin', P+'margin.snapshot', 'line_ids',
        'product_id customer_id sale_order_id warehouse_id comparison_uom_id currency_id quantity demand_type complete '+ ' '.join(AMOUNTS), 'collected_at', True),
    'PRODUCT_IMPACT': ('Product impact', P+'margin.snapshot', 'line_ids',
        'product_id customer_id sale_order_id comparison_uom_id currency_id quantity demand_type complete '+' '.join(AMOUNTS), 'collected_at', True),
    'VENDOR_IMPACT': ('Vendor impact', P+'financial.snapshot', 'line_ids',
        'vendor_id product_id comparison_uom_id currency_id quantity demand_type baseline_extended_cost revised_extended_cost incremental_extended_cost status', 'collected_at', True),
    'CUSTOMER_EXPOSURE': ('Customer exposure', P+'margin.snapshot', 'line_ids',
        'customer_id product_id sale_order_id comparison_uom_id currency_id quantity demand_type price_protection complete '+' '.join(AMOUNTS), 'collected_at', True),
    'SALES_ORDER_EXPOSURE': ('Sales order exposure', P+'margin.snapshot', 'line_ids',
        'sale_order_id customer_id product_id comparison_uom_id currency_id quantity demand_type price_protection complete '+' '.join(AMOUNTS), 'collected_at', True),
    'SUPPLY_COST_BREAKDOWN': ('Supply cost breakdown', P+'financial.snapshot', 'line_ids',
        'source_type product_id warehouse_id comparison_uom_id currency_id quantity demand_type baseline_unit_cost revised_unit_cost baseline_extended_cost revised_extended_cost incremental_extended_cost cost_confidence delta_method', 'collected_at', True),
    'SCENARIO_COMPARISON': ('Scenario alternatives (not additive)', P+'scenario.result', None,
        'scenario_id input_id currency_id version state complete cost_known projected_cost projected_profit projected_margin improvement_vs_proposal margin_improvement_points risk_status', 'collected_at', True),
    'COMMERCIAL_RECOMMENDATIONS': ('Commercial recommendations (not execution)', P+'recommendation', 'line_ids',
        'sale_line_id product_id customer_id comparison_uom_id sales_currency_id sales_uom_id eligibility eligible_qty recommended_net_price financial_net_unit_reference display_price_unit', 'collected_at', True),
    'FINANCIAL_RECONCILIATION': ('Financial reconciliation', P+'reconciliation.run', 'check_ids',
        'code category source_key status required severity unit numeric_known expected_numeric observed_numeric difference tolerance currency_id comparison_uom_id values message', 'collected_at', True),
    'APPROVAL_COMPLIANCE': ('Approval decisions (not application)', P+'approval.request', 'decision_ids',
        'stage_id reviewer_id acting_user_id decision_type decided_at resulting_stage_status policy_version request_version', 'submitted_at', False),
    'APPLIED_PRICE_AUDIT': ('Committed price application audit', P+'application.execution', 'line_ids',
        'plan_line_id row_id target_id operation before_values approved_after_values observed_after_values fingerprint_before fingerprint_after', 'verified_at', False),
    'PRICE_INTEGRITY_MONITORING': ('Retained price observations', MON+'run', 'check_ids',
        'execution_line_id target_id successor_line_id checked_at status classification expected observed differences codes', 'started_at', False),
    'INCIDENT_ANALYTICS': ('Distinct pricing incidents', MON+'incident', None,
        'execution_line_id target_id code severity status first_detected_at last_detected_at latest_check_id assigned_user_id resolved_by resolved_at', 'first_detected_at', False),
    'CORRECTION_GOVERNANCE': ('Analytical correction plans (not executed)', MON+'correction', None,
        'incident_id check_id status created_at created_by requires_new_approval requires_new_dry_run', 'created_at', False),
    'HISTORICAL_TRACEABILITY': ('Retained incident chronology', MON+'event', None,
        'incident_id action actor_id recorded_at resulting_status check_id', 'recorded_at', False),
}
NUMERIC = set(AMOUNTS) | {'quantity', 'eligible_qty', 'recommended_net_price', 'financial_net_unit_reference',
    'display_price_unit', 'baseline_unit_cost', 'revised_unit_cost', 'baseline_extended_cost',
    'revised_extended_cost', 'incremental_extended_cost', 'expected_numeric', 'observed_numeric',
    'difference', 'tolerance', 'projected_cost', 'projected_profit', 'projected_margin',
    'improvement_vs_proposal', 'margin_improvement_points', 'outstanding_qty', 'net_sales_unit_price',
    'outstanding_sales_value', 'company_sales_value', 'baseline_price', 'proposed_price',
    'price_delta', 'price_change_percent', 'comparison_quantity'}
COMMERCIAL_FIELDS = ('vendor_id', 'currency_id', 'currency_code', 'comparison_uom_id', 'comparison_quantity',
    'baseline_price', 'proposed_price', 'price_delta', 'price_change_percent', 'comparison_method',
    'effective_date', 'end_date', 'baseline_status')
SALES_SPEC = ('Restricted customer commercial exposure', P+'sales.snapshot', 'line_ids',
    'sale_order_id sale_line_id customer_id product_id warehouse_id sales_currency_id company_currency_id source_uom_id comparison_uom_id outstanding_qty demand_type net_sales_unit_price outstanding_sales_value company_sales_value price_protection opportunity_status valuation_status',
    'collected_at', False)


def utc_window(start, end, tz):
    """Inclusive local start; exclusive next-local-day end, including DST."""
    zone = ZoneInfo(tz)
    return tuple(datetime.combine(day, time.min, zone).astimezone(timezone.utc).replace(tzinfo=None)
        for day in (start, end + timedelta(days=1)))


class ReportWizard(models.TransientModel):
    _name = WIZARD
    _description = 'Authorized Financial and Audit Report'
    _transient_max_hours = 1

    report_type = fields.Selection([(k, v[0]) for k, v in CATALOG.items()], required=True, default='GROSS_PROFIT_MARGIN')
    company_ids = fields.Many2many('res.company', required=True, default=lambda self: self.env.company)
    source_ids_text = fields.Char(required=True, string='Exact source record IDs',
        help='Comma-separated retained snapshot/run IDs for the selected report. Versions remain separate.')
    product_ids = fields.Many2many('product.product', string='Products')
    vendor_ids = fields.Many2many('res.partner', 'vpr24_report_vendor_rel', string='Vendors')
    customer_ids = fields.Many2many('res.partner', 'vpr24_report_customer_rel', string='Customers')
    group_by = fields.Selection([('none', 'Snapshot totals'), ('product_id', 'Product'), ('vendor_id', 'Vendor'),
        ('customer_id', 'Customer'), ('sale_order_id', 'Sales order'), ('warehouse_id', 'Warehouse')], default='none', required=True)
    demand_scope = fields.Selection([('all', 'Confirmed and conditional (separate)'), ('confirmed', 'Confirmed only'),
        ('conditional', 'Conditional only')], default='all', required=True)
    date_from = fields.Date()
    date_to = fields.Date()
    timezone_name = fields.Char(required=True, default=lambda self: self.env.user.tz or 'UTC', string='Date filter timezone')
    date_basis = fields.Char(compute='_presentation', string='Source date basis')
    source_model = fields.Char(compute='_presentation', string='Source record type')
    output_format = fields.Selection([('csv', 'CSV'), ('xlsx', 'Excel')], default='xlsx', required=True)
    download = fields.Binary(compute='_download', attachment=False)
    filename = fields.Char(compute='_filename')

    def _authorize(self):
        self.ensure_one()
        self.check_access('read')
        user = self.env.user
        if not user.active or user.share or self.create_uid != user:
            raise AccessError('Reports require the original active internal owner.')
        spec = self._spec()
        if spec is None:
            raise ValidationError('Unknown report type.')
        roles = ('group_vpr_finance_manager', 'group_vpr_director', 'group_vpr_auditor')
        if not spec[5]:
            roles += ('group_vpr_purchase_manager',)
        if spec == SALES_SPEC:
            roles += ('group_vpr_sales_manager',)
        if not any(user.has_group(MODULE+'.'+role) for role in roles):
            raise AccessError('This report requires a source-authorized reporting role.')
        if not self.company_ids or self.company_ids - self.env.companies:
            raise AccessError('Choose only currently authorized companies.')
        return spec

    def _spec(self):
        spec = CATALOG.get(self.report_type)
        finance = any(self.env.user.has_group(MODULE+'.'+role) for role in (
            'group_vpr_finance_manager', 'group_vpr_director', 'group_vpr_auditor'))
        if not finance and self.report_type in ('CUSTOMER_EXPOSURE', 'SALES_ORDER_EXPOSURE') and self.env.user.has_group(MODULE+'.group_vpr_sales_manager'):
            return SALES_SPEC
        return spec

    def _dataset(self):
        # Native ir.binary may elevate a record for a valid signed field URL.
        # Such transport authority never grants source financial authority.
        self = self.with_env(self.env(su=False))
        spec = self._authorize()
        if len(self.source_ids_text or '') > 2048 or not re.fullmatch(r'[0-9]+(?:\s*,\s*[0-9]+)*', self.source_ids_text or ''):
            raise ValidationError('Provide explicit comma-separated positive source IDs.')
        ids = [int(v.strip()) for v in self.source_ids_text.split(',')]
        if len(ids) > 100 or len(ids) != len(set(ids)) or min(ids) <= 0:
            raise ValidationError('Select at most 100 distinct positive source IDs.')
        sources = self.env[spec[1]].browse(sorted(ids)).exists()
        if len(sources) != len(ids):
            raise AccessError('Some selected sources are unavailable.')
        sources.check_access('read')
        if sources.mapped('company_id') - self.company_ids:
            raise AccessError('Every source must belong to the selected companies.')
        if bool(self.date_from) != bool(self.date_to) or (self.date_from and self.date_from > self.date_to):
            raise ValidationError('Provide a valid inclusive start/end date pair.')
        try:
            window = utc_window(self.date_from, self.date_to, self.timezone_name) if self.date_from else None
            ZoneInfo(self.timezone_name)
        except (ValueError, KeyError, TypeError):
            raise ValidationError('Use a valid IANA timezone.') from None
        rows, evidence = [], []
        fields_list = spec[3].split()
        commercial = self.report_type == 'VENDOR_REVISION_SUMMARY'
        available = fields_list + list(COMMERCIAL_FIELDS) if commercial else fields_list
        dimensions = () if self.group_by == 'none' else (self.group_by,)
        filter_specs = [('product_id', self.product_ids), ('vendor_id', self.vendor_ids), ('customer_id', self.customer_ids)]
        for key, selected in filter_specs:
            selected.check_access('read')
            if selected and key not in available:
                raise ValidationError('The selected report does not support the '+key+' filter.')
        if dimensions and (self.group_by not in fields_list or spec[1] not in (P+'margin.snapshot', P+'financial.snapshot')):
            raise ValidationError('Select a grouping supported by this financial report.')
        if self.demand_scope != 'all' and 'demand_type' not in fields_list:
            raise ValidationError('This report has no demand classification filter.')
        filtered_count = 0
        processed_count = 0
        payload_bytes = 0
        for source in sources:
            instant = source[spec[4]]
            if window and (not instant or not window[0] <= instant < window[1]):
                continue
            if self.report_type == 'APPLIED_PRICE_AUDIT' and source.state != 'VERIFIED':
                raise UserError('Only committed verified execution receipts are application evidence.')
            details = source[spec[2]] if spec[2] else source
            details.check_access('read')
            if 'line_count' in source._fields and spec[2] == 'line_ids' and len(details) != source.line_count:
                raise AccessError('The selected source detail is incomplete or no longer fully authorized.')
            processed_count += len(details)
            if processed_count > report_data.MAX_ROWS:
                raise UserError('Report exceeds 50,000 rows. Narrow the exact source selection; no rows were truncated.')
            raw = details.read(fields_list + (['snapshot'] if commercial else []))
            for record in raw:
                row = dict(source_model=details._name, source_id=record['id'], snapshot_id=source.id,
                    company_id=source.company_id.id, company_name=source.company_id.name, source_date=str(instant or ''),
                    scenario=source.scenario if 'scenario' in source._fields else str(source.id),
                    currency_id=source.currency_id.id if 'currency_id' in source._fields else None,
                    currency_code=source.currency_id.name if 'currency_id' in source._fields else None)
                for key in fields_list:
                    value = record[key]
                    field = details._fields[key]
                    if field.type == 'many2one':
                        row[key+'_label'] = value[1] if value else None
                        value = value[0] if value else None
                    elif field.type in ('date', 'datetime'):
                        value = str(value) if value else None
                    elif field.type == 'char' and value is False:
                        value = None
                    # Reconciliation Float fields use numeric_known; unknown is not zero.
                    if key in ('expected_numeric', 'observed_numeric', 'difference', 'tolerance') and not record.get('numeric_known'):
                        value = None
                    if key == 'projected_cost' and not record.get('cost_known'):
                        value = None
                    if key in NUMERIC and value is not None:
                        value = str(value)
                    row[key] = value
                if commercial:
                    source.batch_id.check_access('read')
                    frozen = record['snapshot'] or {}
                    proposal, baseline, comparison = (frozen.get(k) or {} for k in ('proposal', 'baseline', 'comparison'))
                    row.update(vendor_id=source.batch_id.vendor_id.id, currency_id=proposal.get('company_currency_id'),
                        currency_code=proposal.get('company_currency_code'), comparison_uom_id=proposal.get('comparison_uom_id'),
                        comparison_quantity=proposal.get('normalized_min_qty'),
                        baseline_price=baseline.get('company_price') if baseline.get('status') == 'selected' else None,
                        proposed_price=proposal.get('company_price'), price_delta=comparison.get('delta'),
                        price_change_percent=comparison.get('percent'), comparison_method=comparison.get('method'),
                        effective_date=proposal.get('effective_date'), end_date=proposal.get('end_date'), baseline_status=baseline.get('status'))
                if self.report_type == 'SCENARIO_COMPARISON':
                    # PR17 keeps authoritative Decimal strings in profit; its
                    # projected_cost Float is only a legacy UI convenience.
                    row['projected_cost'] = source.profit.get('revised_cost') if source.cost_known else None
                if any(selected and row.get(key) not in selected.ids for key, selected in filter_specs) or (
                    self.demand_scope != 'all' and row.get('demand_type') != self.demand_scope):
                    filtered_count += 1
                    continue
                payload_bytes += len(report_data.canonical(row).encode('utf-8'))
                if payload_bytes > 32*1024*1024:
                    raise UserError('Report exceeds the 32 MiB canonical detail budget. Narrow the selected sources.')
                rows.append(row)
            evidence.append(dict(model=source._name, id=source.id, date=str(instant or ''), audit_context=self._audit_context(source),
                fingerprint=source.fingerprint if 'fingerprint' in source._fields else source.input_digest if 'input_digest' in source._fields else None,
                version=source.version if 'version' in source._fields else None,
                detail_count=len(raw), detail_hash=report_data.fingerprint(raw)))
        metadata = dict(contract=report_data.VERSION, report_type=self.report_type, title=spec[0],
            owner_id=self.env.uid, company_ids=sorted(self.company_ids.ids),
            companies=[dict(id=company.id, name=company.name) for company in self.company_ids.sorted('id')],
            role_contract='RESTRICTED_COMMERCIAL' if spec == SALES_SPEC else 'AUTHORIZED_SOURCE_FACTS', source_model=spec[1],
            source_mode='RETAINED_SOURCE_FACTS', freshness='NOT_CHECKED',
            recorded_instant_basis='UTC',
            date_basis=spec[4], timezone=self.timezone_name, date_from=str(self.date_from or ''), date_to=str(self.date_to or ''),
            requested_source_ids=sorted(ids), product_ids=sorted(self.product_ids.ids), vendor_ids=sorted(self.vendor_ids.ids),
            customer_ids=sorted(self.customer_ids.ids), group_by=self.group_by, demand_scope=self.demand_scope,
            sources=evidence, row_count=len(rows), filtered_out_count=filtered_count, projected_not_realized=True)
        keys = list(dict.fromkeys(['source_model', 'source_id', 'snapshot_id', 'company_name', 'company_id', 'currency_code', 'currency_id', 'source_date', 'scenario'] + available))
        columns = [{'key': k, 'label': k.replace('_', ' ').title() + (' (UTC)' if k == 'source_date' or k.endswith('_at') else ' (pp)' if 'points' in k else ' (%)' if 'percent' in k or k=='projected_margin' else ''), 'numeric': k in NUMERIC} for k in keys]
        result = dict(metadata=metadata, columns=columns, rows=rows,
            totals=report_data.totals(rows, dimensions) if spec[1] == P+'margin.snapshot' else report_data.cost_totals(rows, dimensions) if spec[1] == P+'financial.snapshot' else [],
            issues=['Retained source facts; current freshness and current approval validity have not been revalidated.',
                'Projected financial results are not realized savings or accounting valuation.',
                'Snapshot versions and alternative scenarios are separate; quantities have no cross-unit grand total.'])
        metadata['dataset_fingerprint'] = report_data.fingerprint(result)
        # Generation time is presentation metadata, excluded from logical identity.
        metadata['generated_at_utc'] = fields.Datetime.now().isoformat()
        return result

    def _audit_context(self, source):
        if self.report_type == 'APPROVAL_COMPLIANCE':
            source.stage_ids.check_access('read')
            return dict(request=source.read(['state', 'request_type', 'version', 'requested_by', 'maker_id', 'submitted_by',
                'submitted_at', 'approved_at', 'approved_by', 'approval_valid_from', 'approval_valid_until',
                'approval_invalidated_at', 'approval_expired_at', 'policy_version'], load=None)[0],
                stages=source.stage_ids.read(['sequence', 'code', 'assigned_ids', 'quorum', 'stage_status',
                    'assigned_by', 'assigned_at', 'policy_version'], load=None),
                interpretation='Recorded stages and actual decisions; not live validity or evidence of application.')
        if self.report_type == 'APPLIED_PRICE_AUDIT':
            for related in (source.plan_id, source.request_id, source.authorization_id):
                related.check_access('read')
            return source.read(['plan_id', 'request_id', 'authorization_id', 'operator_id', 'verified_at',
                'create_count', 'update_count', 'no_change_count', 'verified_line_count', 'source_fingerprint',
                'target_fingerprint_before', 'target_fingerprint_after'], load=None)[0]
        if self.report_type == 'PRICE_INTEGRITY_MONITORING':
            return source.read(['run_type', 'state', 'started_at', 'completed_at', 'expected_count', 'processed_count',
                'passed_count', 'failed_count', 'blocked_count', 'has_more', 'policy_version'], load=None)[0]
        if self.report_type == 'COMMERCIAL_RECOMMENDATIONS':
            return source.read(['state', 'complete', 'required_revenue', 'revenue_gap', 'supplier_ceiling', 'summary', 'controls'], load=None)[0]
        if self.report_type == 'SCENARIO_COMPARISON':
            source.scenario_id.baseline_id.check_access('read')
            return dict(exact_baseline_id=source.scenario_id.baseline_id.id,
                baseline_fingerprint=source.scenario_id.baseline_id.fingerprint,
                state=source.state, complete=source.complete, ranking='NOT_RANKED',
                controls=source.controls, provenance=source.provenance, issues=source.issues)
        return {}

    def _presentation(self):
        for rec in self:
            spec = rec._spec()
            rec.date_basis = spec[4] if spec else False
            rec.source_model = spec[1] if spec else False

    def action_preview(self):
        self.ensure_one()
        dataset = self._dataset()
        if len(dataset['rows']) > report_data.PDF_ROWS:
            raise UserError('Preview is limited to 500 rows. Narrow the report or export all rows to XLSX/CSV.')
        action = self.env.ref(MODULE+'.action_financial_audit_pdf').report_action(self)
        action['report_type'] = 'qweb-html'
        return action

    @api.depends('report_type', 'output_format')
    def _filename(self):
        for rec in self:
            rec.filename = '%s.%s' % (rec.report_type or 'report', rec.output_format or 'xlsx')

    @api.depends('report_type', 'company_ids', 'source_ids_text', 'product_ids', 'vendor_ids', 'customer_ids',
        'group_by', 'demand_scope', 'date_from', 'date_to', 'timezone_name', 'output_format')
    @api.depends_context('uid', 'allowed_company_ids')
    def _download(self):
        for rec in self:
            dataset = rec._dataset()
            try:
                content = report_data.xlsx_bytes(dataset) if rec.output_format == 'xlsx' else report_data.csv_bytes(dataset)
            except ValueError as exc:
                raise UserError(str(exc)) from None
            rec.download = BinaryBytes(content, filename=rec.filename)

    def read(self, fields=None, load='_classic_read'):
        if fields is None or 'download' in fields:
            for rec in self:
                rec._dataset()
        return super().read(fields=fields, load=load)

    def export_data(self, fields_to_export):
        if 'download' in fields_to_export:
            for rec in self:
                rec._dataset()
        return super().export_data(fields_to_export)

    def action_download(self):
        self._dataset()  # Rechecked again by the computed download field at retrieval.
        return dict(type='ir.actions.act_url', url='/web/content/%s/%s/download/%s?download=true' % (WIZARD, self.id, self.filename), target='self')

    def action_pdf(self):
        self._dataset()
        return self.env.ref(MODULE+'.action_financial_audit_pdf').report_action(self)

    def action_source(self, source_id):
        dataset = self._dataset()
        if type(source_id) is not int:
            raise AccessError('Select an exact authorized report detail.')
        row = next((row for row in dataset['rows'] if row['source_id'] == source_id), None)
        if row is None:
            raise AccessError('Source is outside the authorized report detail.')
        record = self.env[row['source_model']].browse(source_id)
        record.check_access('read')
        return dict(type='ir.actions.act_window', res_model=record._name, res_id=record.id, view_mode='form')


class FinancialAuditPdf(models.AbstractModel):
    _name = 'report.'+MODULE+'.financial_audit_pdf'
    _table = 'vpr24_report_context'
    _description = 'Authorized financial report PDF context'

    def _get_report_values(self, docids, data=None):
        if not isinstance(docids, list) or len(docids) != 1:
            raise AccessError('Render exactly one owned report.')
        wizard = self.env[WIZARD].browse(docids).exists()
        if not wizard:
            raise AccessError('Report expired or unavailable.')
        dataset = wizard._dataset()
        if len(dataset['rows']) > report_data.PDF_ROWS:
            raise UserError('PDF is limited to 500 detail rows. Narrow the selection or use XLSX/CSV.')
        currency_ids = {row.get('currency_id') for row in dataset['rows']} | {row.get('sales_currency_id') for row in dataset['rows']} | {row.get('company_currency_id') for row in dataset['rows']}
        currencies = self.env['res.currency'].browse(sorted(identity for identity in currency_ids if identity))
        currencies.check_access('read')
        rounding = {currency.id: Decimal(str(currency.rounding)) for currency in currencies}

        def display_value(row, key):
            value = row.get(key)
            if value is None:
                return 'Unavailable'
            if row.get(key+'_label'):
                return '%s (#%s)' % (row[key+'_label'], value)
            if isinstance(value, bool):
                return 'Yes' if value else 'No'
            if key in NUMERIC or key.endswith('_verified_subset'):
                try:
                    with localcontext() as ctx:
                        ctx.prec = 50
                        if 'percent' in key or 'points' in key or key == 'projected_margin':
                            digits = Decimal('.0001')
                        elif key in ('quantity', 'outstanding_qty', 'eligible_qty', 'comparison_quantity'):
                            digits = Decimal('.0001')
                        else:
                            currency = row.get('sales_currency_id') if key in ('outstanding_sales_value', 'net_sales_unit_price') else row.get('currency_id') or row.get('company_currency_id')
                            digits = rounding.get(currency)
                        return format(Decimal(str(value)).quantize(digits), ',f') if digits else str(value)
                except (InvalidOperation, ValueError):
                    return str(value)
            return report_data.canonical(value) if isinstance(value, (dict, list)) else str(value)
        return dict(doc_ids=docids, doc_model=WIZARD, docs=wizard, report=dataset, display_value=display_value,
            audit_summary=report_data.audit_summary)
