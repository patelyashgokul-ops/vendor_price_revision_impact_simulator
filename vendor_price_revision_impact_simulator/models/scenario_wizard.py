"""Bounded Community UI for immutable scenario revisions."""
from copy import deepcopy
from odoo import api, fields, models
from .vendor_scenario import PREFIX, HEADER, BASE
from .scenario_math import MODES
from .commercial_math import price

class ScenarioCreateWizard(models.TransientModel):
    _name=PREFIX+'.create.wizard'
    _inherit='vendor.price.revision.purchase.wizard.boundary'
    _description='Create Hypothetical Vendor Alternative'
    baseline_id=fields.Many2one(BASE,required=True)
    parent_id=fields.Many2one(HEADER)
    name=fields.Char(required=True)
    def action_create(self):
        self.ensure_one();r=self.parent_id.action_clone_scenario(self.name) if self.parent_id else self.baseline_id.batch_id.action_create_vendor_scenario(self.baseline_id.id,self.name)
        return dict(type='ir.actions.act_window',res_model=HEADER,res_id=r.id,view_mode='form')

class ScenarioSelectionWizard(models.TransientModel):
    _name=PREFIX+'.selection.wizard'
    _inherit='vendor.price.revision.purchase.wizard.boundary'
    _description='Analytical Selection Only'
    scenario_id=fields.Many2one(HEADER,required=True)
    event=fields.Selection([(v,v.replace('_',' ').title()) for v in ('shortlisted','preferred_for_review','not_selected','archived')],required=True)
    reason=fields.Text(required=True)
    def action_record(self):
        self.ensure_one();self.scenario_id.action_select_for_review(self.event,self.reason)
        return dict(type='ir.actions.act_window',res_model=HEADER,res_id=self.scenario_id.id,view_mode='form')

class ScenarioWizard(models.TransientModel):
    _name=PREFIX+'.wizard'
    _inherit='vendor.price.revision.purchase.wizard.boundary'
    _description='Version an Exact Product Commercial Assumption'
    scenario_id=fields.Many2one(HEADER,required=True)
    product_id=fields.Many2one('product.product',required=True)
    source_basis=fields.Text(string='Stored source net price, currency, unit and eligible quantity',compute='_source_basis')
    mode=fields.Selection([(v,v.replace('_',' ').title()) for v in MODES],required=True,default='original')
    value=fields.Char(string='Explicit price or discount (blank unknown)')
    discount_base=fields.Selection([('proposal','Original proposal'),('old','Pre-revision price')],default='proposal',required=True)
    row_id=fields.Many2one('vendor.price.revision.import.row',string='Verified MOQ tier row')
    grouped=fields.Boolean(string='Consolidate exact residual requirements within one warehouse')
    group_reason=fields.Text()
    fx_method=fields.Selection([(v,v.replace('_',' ').title()) for v in ('price_only_common_fx','combined_price_and_fx','fx_only_sensitivity')],default='price_only_common_fx',required=True)
    fx_rate=fields.Char(string='Company currency per1 source currency (hypothetical)')
    fx_date=fields.Date()
    effective_date=fields.Date()
    commitment_date=fields.Date(string='Hypothetical commercial commitment date (not delivery)')
    timing_evidence=fields.Text()
    po_line_id=fields.Integer(string='Exact protected PO line ID (hypothetical amendment only)')
    po_evidence=fields.Text()
    reason=fields.Text(required=True)
    landed_components=fields.Json(string='Future nonrecoverable components with exact unit/currency/evidence')

    @api.depends('scenario_id','product_id','po_line_id')
    def _source_basis(self):
        for wizard in self:
            scenario=wizard.scenario_id
            if not scenario or not wizard.product_id:
                wizard.source_basis='Select a baseline product. Prices and fixed discounts use the original supplier currency per purchase unit.'
                continue
            scenario.check_access('read');scenario.baseline_id.check_access('read')
            financial=scenario.baseline_id.margin_id.financial_id;financial.check_access('read')
            rows=financial.line_ids.filtered(lambda r:r.product_id==wizard.product_id.id)
            labels=[]
            for row in rows:
                if wizard.po_line_id:
                    basis=row.cost_line_id.evidence
                    if basis.get('po_line_id')!=wizard.po_line_id:continue
                    value=basis.get('recorded_source_unit_cost');currency=basis.get('source_currency_id');unit=row.comparison_uom_id
                else:
                    if row.source_type!='new_procurement_requirement':continue
                    basis=row.evidence.get('pricing',{}).get('proposal') or row.cost_line_id.evidence.get('proposal')
                    if not basis:continue
                    unit=wizard.env['uom.uom'].browse(basis['source_uom_id'])
                    currency=basis['source_currency_id']
                    value=str(price(basis['net_comparable'],row.comparison_uom_id.factor,unit.factor))
                currency=wizard.env['res.currency'].browse(currency).display_name if currency else 'Unavailable currency'
                labels.append('Original net '+str(value if value is not None else 'unavailable')+' '+currency+' per '+unit.display_name+'; allocated eligible quantity '+row.quantity+' '+row.comparison_uom_id.display_name+'; '+row.warehouse_id.display_name)
            wizard.source_basis='\n'.join(labels) if labels else 'No eligible new procurement or matching protected PO quantity in this stored source. Do not infer a zero exposure.'

    def action_save(self):
        self.ensure_one();s=self.scenario_id;s._edit()
        spec=dict(product_id=self.product_id.id,mode=self.mode,reason=self.reason,discount_base=self.discount_base,fx_method=self.fx_method)
        if self.value:spec['value']=self.value
        if self.row_id:spec['row_id']=self.row_id.id
        if self.grouped:spec.update(grouped=True,group_reason=self.group_reason)
        if self.fx_rate:spec['fx_rate']=self.fx_rate
        if self.fx_date:spec['fx_date']=str(self.fx_date)
        if self.effective_date:spec['effective_date']=str(self.effective_date)
        if self.commitment_date:spec.update(commitment_date=str(self.commitment_date),timing_evidence=self.timing_evidence)
        if self.po_line_id:spec.update(po_line_id=self.po_line_id,po_evidence=self.po_evidence)
        if self.landed_components:spec['landed']=self.landed_components
        values=[deepcopy(r.values) for r in s._inputs().line_ids if (r.product_id.id,r.po_line_id or 0)!=(self.product_id.id,self.po_line_id or 0)]
        s.action_set_assumptions(values+[spec],self.reason)
        return dict(type='ir.actions.act_window',res_model=HEADER,res_id=s.id,view_mode='form')
