"""Explicit preapproval coverage for a future close-old/create-new transition."""
from types import SimpleNamespace
from datetime import timedelta
from odoo import models, fields
from odoo.exceptions import AccessError, ValidationError
from .application_engine import ApplicationEngine, snapshot
from .application_math import MATERIAL, same
from .approval_decisions import safe_json
from .structural_validation import digest


def boundary_plan(engine, row, desired, intent, candidates):
    proof = intent.get('boundary')
    if not proof:
        return candidates, None, []
    frozen = proof.get('before') or {}; target_id = frozen.get('id')
    before = next((v for v in engine.targets if v['id']==target_id), None)
    after = {k:frozen.get(k) for k in MATERIAL}; after['date_end']=proof.get('date_end')
    codes = []
    start=fields.Date.to_date(desired['date_start']); expected=str(start-timedelta(days=1))
    identity=('partner_id','product_id','product_tmpl_id','company_id','currency_id','uom_id','min_qty')
    if (proof.get('contract') != 'pr22_explicit_future_boundary_v1' or not before or not same(before,frozen) or
            not same(frozen,desired,identity) or not frozen.get('company_id') or not frozen.get('product_id') or
            proof.get('date_end') != expected or start <= engine.analysis_date or
            (frozen.get('date_start') and frozen['date_start']>=str(start)) or
            (frozen.get('date_end') and frozen['date_end']<expected)):
        codes.append('APPROVED_DATE_BOUNDARY_STALE_OR_UNSAFE')
    operation=('BLOCKED' if codes else 'NO_CHANGE' if frozen.get('date_end')==expected else 'UPDATE_CANDIDATE')
    line=dict(row_id=row['row_id'],commercial_result_id=row['commercial_result_id'],product_id=desired['product_id'],
        target_id=target_id,operation=operation,before=before,after=after,boundary=True,
        changed_fields=[] if operation=='NO_CHANGE' else ['date_end'],unchanged_fields=[k for k in MATERIAL if k!='date_end'],
        conflicts=codes,selection=dict(meaning='Explicit approved future closure; old price and all other fields retained.'),
        intent=intent,target_fingerprint=digest(before),source_fingerprint=digest([row,proof]))
    # Analytical override only; actual targets remain untouched in evidence.
    adjusted=[dict(v,date_end=expected) if v['id']==target_id and not codes else v for v in candidates]
    return adjusted,line,codes


class ApprovedDateBoundary(models.Model):
    _inherit = 'vendor.price.revision.approval.request'

    def action_set_vendor_application_scope(self, lines, reason, vendor_component=False, calendar_timezone=None):
        previous={v['row_id']:v for v in (self.vendor_application_scope or {}).get('lines',[])}
        if not isinstance(lines,list):
            return super().action_set_vendor_application_scope(lines,reason,vendor_component,calendar_timezone)
        plain=[{k:v for k,v in s.items() if k!='close_previous_id'} if isinstance(s,dict) else s for s in lines]
        with self.env.cr.savepoint():
            result=super().action_set_vendor_application_scope(plain,reason,vendor_component,calendar_timezone)
            saved=safe_json(self.vendor_application_scope);by_row={v['row_id']:v for v in saved['lines']}
            if not any(s.get('close_previous_id',previous.get(s.get('row_id'),{}).get('close_previous_id')) for s in lines):
                return result
            builder=self._builder(route=False);payload=self._payload20(builder)
            engine=ApplicationEngine(self);engine.payload=payload
            engine.analysis_date=fields.Date.context_today(self.with_context(tz=saved['calendar_timezone']))
            source={v['row_id']:v for v in payload['source_rows']}
            used=set()
            for spec in lines:
                rid=spec['row_id'];close_id=spec.get('close_previous_id',previous.get(rid,{}).get('close_previous_id'))
                if not close_id:continue
                if type(close_id) is not int or close_id in used or spec.get('operation')!='create':
                    raise ValidationError('One explicit existing rule per future creation boundary required.')
                used.add(close_id);intent=by_row[rid]
                target=self.env['product.supplierinfo'].browse(close_id).exists();target.check_access('read')
                if not target or target.company_id!=self.company_id or target.partner_id!=self.batch_id.vendor_id or not target.product_id:
                    raise AccessError('Shared/template/foreign rules cannot acquire implicit closure coverage.')
                desired=engine.terms(source[rid],target.product_id,intent)
                proof=dict(contract='pr22_explicit_future_boundary_v1',before=snapshot(target)[0],
                    date_end=str(fields.Date.to_date(desired['date_start'])-timedelta(days=1)))
                intent.update(close_previous_id=close_id,boundary=proof)
                engine.targets=snapshot(target)
                _,_,codes=boundary_plan(engine,source[rid],desired,intent,engine.targets)
                if codes:raise ValidationError('APPROVED_DATE_BOUNDARY_UNSAFE: preserve past periods and exact commercial identity.')
            self._update({'vendor_application_scope':saved})
            self._event('explicit_future_boundary_declared',reason,dict(scope_fingerprint=digest(saved)),self.state)
            return result
