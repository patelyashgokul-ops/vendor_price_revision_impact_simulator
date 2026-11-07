"""Opt-in original-user scheduled revalidation with transaction-safe cursors."""
import time
from datetime import timedelta
from itertools import groupby
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from .execution import LINE
from .monitor_models import MODULE
from .monitor_service import MAX_LINES
from .import_intake import clean_defaults

POLICY = 'vendor.price.revision.application.monitor.policy'


def policy_authority(env, company):
    if not env.user.active or env.user.share or not any(env.user.has_group(MODULE+r) for r in
            ('group_vpr_purchase_manager','group_vpr_finance_manager')) or company not in env.companies or company not in env.user.company_ids:
        raise AccessError('An active company-authorized monitoring manager is required.')


class MonitorPolicy(models.Model):
    _name = POLICY
    _inherit = 'vendor.price.revision.intake.read.guard'
    _description = 'Optional Company Monitoring Schedule — No Price Application'
    _unique = models.Constraint('UNIQUE(company_id,user_id)', 'One schedule per company and authenticated monitor.')
    name = fields.Char(default='Periodic applied price integrity', required=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda s:s.env.company)
    user_id = fields.Many2one('res.users', required=True, default=lambda s:s.env.user, readonly=True)
    enabled = fields.Boolean(default=False)
    interval_hours = fields.Integer(default=24, required=True)
    batch_size = fields.Integer(default=25, required=True)
    version = fields.Integer(default=1, readonly=True)
    cursor_line_id = fields.Integer(readonly=True)
    cycle = fields.Integer(default=1, readonly=True)
    next_run_at = fields.Datetime(default=fields.Datetime.now, readonly=True)
    last_run_at = fields.Datetime(readonly=True)
    last_error = fields.Char(readonly=True)

    @api.constrains('batch_size','interval_hours')
    def _bounds(self):
        for p in self:
            if not 1 <= p.batch_size <= MAX_LINES or not 1 <= p.interval_hours <= 168:
                raise ValidationError('Batch size must be 1–100 and frequency 1–168 hours.')

    @api.model_create_multi
    def create(self, vals_list):
        prepared=[]
        for vals in vals_list:
            if set(vals)-{'name','company_id','enabled','interval_hours','batch_size'}:
                raise AccessError('Schedule identity, version and progress are server-owned.')
            company=self.env['res.company'].browse(vals.get('company_id',self.env.company.id))
            policy_authority(self.env,company)
            prepared.append(dict(vals,company_id=company.id,user_id=self.env.uid,version=1,cursor_line_id=0,cycle=1,
                next_run_at=fields.Datetime.now()))
        return super(MonitorPolicy,clean_defaults(self)).create(prepared)

    def write(self, values):
        if set(values)-{'name','enabled','interval_hours','batch_size'}:
            raise AccessError('Schedule source and progress cannot be reassigned.')
        for p in self:
            p.check_access('write'); policy_authority(self.env,p.company_id)
            if p.user_id != self.env.user:
                raise AccessError('Only the authenticated schedule owner may configure it.')
            super(MonitorPolicy,p).write(dict(values,version=p.version+1))
        return True

    def unlink(self):
        raise AccessError('Monitoring schedules and cursors are retained; disable the schedule instead.')

    def copy(self,default=None):
        raise AccessError('Create a new authorized schedule explicitly.')

    def action_run_batch(self):
        self.ensure_one(); self.check_access('read'); policy_authority(self.env,self.company_id)
        if self.user_id != self.env.user:
            raise AccessError('Scheduled observations execute only as their authenticated owner.')
        with self.env.cr.savepoint():
            self.env.cr.execute('SELECT id FROM '+self._table+' WHERE id=%s FOR UPDATE NOWAIT',[self.id])
            self.invalidate_recordset(); self._bounds()
            clean=api.Environment(self.env.cr,self.env.uid,{'allowed_company_ids':self.company_id.ids,'tz':'UTC'})
            domain=[('company_id','=',self.company_id.id),('id','>',self.cursor_line_id)]
            lines=clean[LINE].search(domain,order='id',limit=self.batch_size+1)
            if not lines:
                super(MonitorPolicy,self).write(dict(cursor_line_id=0,cycle=self.cycle+1,last_run_at=fields.Datetime.now(),
                    next_run_at=fields.Datetime.now()+timedelta(hours=self.interval_hours),last_error=False))
                return []
            more=len(lines)>self.batch_size; lines=lines[:self.batch_size]; runs=[]; last=self.cursor_line_id; start=time.monotonic()
            # IDs define a deterministic watermark; execution groups may be split
            # across pages. No target write_date dependency. Every cycle rechecks
            # older targets; newly inserted lines follow the same cursor.
            for execution_id, values in groupby(lines,key=lambda l:l.execution_id.id):
                if runs and time.monotonic()-start>20:
                    more=True; break
                group=list(values)
                run=group[0].execution_id._monitor23(line_ids=[l.id for l in group],run_type='SCHEDULED_REVALIDATION')
                runs.append(run.id); last=run.last_processed_reference
                if run.has_more:
                    more=True; break
            super(MonitorPolicy,self).write(dict(cursor_line_id=last if more else 0,
                cycle=self.cycle if more else self.cycle+1,last_run_at=fields.Datetime.now(),last_error=False,
                next_run_at=fields.Datetime.now()+timedelta(hours=self.interval_hours)))
            return runs

    @api.model
    def _cron_monitor23(self):
        # No impersonation, sudo, commits, remote messages or broad company loop.
        # Configure ir.cron.user_id to the same explicit manager as this schedule.
        policies=self.search([('enabled','=',True),('user_id','=',self.env.uid),
            ('company_id','in',self.env.companies.ids),('next_run_at','<=',fields.Datetime.now())],order='id',limit=5)
        for policy in policies:
            try:
                with self.env.cr.savepoint():
                    policy.action_run_batch()
            except (AccessError,UserError,ValidationError):
                super(MonitorPolicy,policy).write(dict(last_error='Monitoring blocked; verify owner/source access and retry.',
                    next_run_at=fields.Datetime.now()+timedelta(hours=policy.interval_hours)))
