"""Versioned structural mapping/correction/revalidation; immutable source retained."""
from collections import Counter, defaultdict

from psycopg2 import DatabaseError
from psycopg2.errors import SerializationFailure, DeadlockDetected

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from . import structural_validation as lexical
from .import_intake import BATCH, ROW, ImportBatch, ImportRow, clean_defaults

PREFIX = 'vendor.price.revision.import.'
MAPPING, RUN, RESULT, ISSUE, CORRECTION = [PREFIX + n for n in ('mapping', 'validation.run', 'validation.result', 'issue', 'correction')]
EVENT = PREFIX + 'review.event'
OPTIONS = {'number_style', 'date_style', 'inherit_currency', 'inherit_date'}
STATUSES = [('pending_mapping', 'Pending mapping'), ('pending_validation', 'Pending validation'),
    ('structurally_ready', 'Structurally ready only'), ('needs_review', 'Needs review'),
    ('blocked', 'Blocked'), ('excluded', 'Excluded')]


class ImmutableReview(models.AbstractModel):
    _name = PREFIX + 'review.guard'
    _inherit = 'vendor.price.revision.intake.read.guard'
    _description = 'Immutable Validation History Guard'
    batch_id = fields.Many2one(BATCH, required=True, ondelete='restrict', index=True)
    company_id = fields.Many2one(related='batch_id.company_id', store=True, readonly=True, index=True)

    def export_data(self, fields_to_export):
        result = super().export_data(fields_to_export)
        # Output-boundary protection only; original/corrected evidence is untouched.
        for row in result.get('datas', []):
            for index, value in enumerate(row):
                if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
                    row[index] = "'" + value
        return result

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Validation evidence is created only by authorized review actions.'))

    @api.model
    def _record(self, values):
        return super(ImmutableReview, clean_defaults(self)).create(values)

    def write(self, vals):
        raise AccessError(_('Validation and correction history cannot be overwritten.'))

    def unlink(self):
        raise AccessError(_('Validation and correction history is retained.'))

    def copy(self, default=None):
        raise AccessError(_('Validation evidence cannot be copied or reassigned.'))


class Mapping(models.Model):
    _name = MAPPING
    _inherit = PREFIX + 'review.guard'
    _description = 'Batch Column Mapping (one-based ordinal)'
    _order = 'column_number, id'
    _target_unique = models.Constraint('UNIQUE(batch_id, target)', 'Each canonical field has at most one source column.')
    _column_unique = models.Constraint('UNIQUE(batch_id, column_number)', 'A source column can map to only one canonical field.')
    column_number = fields.Integer(required=True)
    target = fields.Selection([(s, s.replace('_', ' ').title()) for s in lexical.TARGETS], required=True)
    header_text = fields.Char(compute='_compute_header')
    active = fields.Boolean(default=True)

    @api.depends('column_number', 'batch_id.headers')
    def _compute_header(self):
        for rec in self:
            headers = rec.batch_id.headers or []
            value = headers[rec.column_number - 1].get('value') if 0 < rec.column_number <= len(headers) else None
            rec.header_text = '' if value is None else str(value)

    @api.constrains('column_number', 'batch_id', 'target')
    def _check_column(self):
        for rec in self:
            if not 1 <= rec.column_number <= len(rec.batch_id.headers or []):
                raise ValidationError(_('Mapping must reference an existing one-based source header column.'))

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        seen_targets, seen_columns = set(), set()
        for vals in vals_list:
            if set(vals) - {'batch_id', 'column_number', 'target', 'active'}:
                raise AccessError(_('Mapping ownership/provenance cannot be forged.'))
            batch = self.env[BATCH].browse(vals.get('batch_id'))
            batch._check_review_access()
            batch._lock()
            column, target = vals.get('column_number'), vals.get('target')
            if target not in lexical.TARGETS:
                raise ValueError('Unsupported canonical mapping target')
            if not isinstance(column, int) or not 1 <= column <= len(batch.headers or []):
                raise ValidationError(_('Mapping must reference an existing one-based source header column.'))
            if (batch.id, target) in seen_targets or (batch.id, column) in seen_columns or any(
                    row.target == target or row.column_number == column for row in batch.mapping_ids):
                raise ValidationError(_('A canonical field and source column must each be mapped only once. Edit the existing definition.'))
            seen_targets.add((batch.id, target))
            seen_columns.add((batch.id, column))
            prepared.append(vals)
        records = super(ImmutableReview, clean_defaults(self)).create(prepared)
        records.batch_id._invalidate_review('mapping_create')
        return records

    def write(self, vals):
        self.check_access('write')
        if set(vals) - {'column_number', 'target', 'active'}:
            raise AccessError(_('Mapping ownership cannot change.'))
        self.batch_id._check_review_access()
        self.batch_id._lock()
        proposed = set()
        for row in self:
            column, target = vals.get('column_number', row.column_number), vals.get('target', row.target)
            if not isinstance(column, int) or not 1 <= column <= len(row.batch_id.headers or []):
                raise ValidationError(_('Mapping must reference an existing source column.'))
            if target not in lexical.TARGETS:
                raise ValueError('Unsupported canonical mapping target')
            keys = {(row.batch_id.id, 'column', column), (row.batch_id.id, 'target', target)}
            if keys & proposed or any(other.column_number == column or other.target == target for other in row.batch_id.mapping_ids - self):
                raise ValidationError(_('A canonical field and source column must each be mapped only once.'))
            proposed.update(keys)
        before = self.read(['column_number', 'target', 'active'])
        result = super(ImmutableReview, self).write(vals)
        if before != self.read(['column_number', 'target', 'active']):
            self.batch_id._invalidate_review('mapping_change')
        return result


class ValidationRun(models.Model):
    _name = RUN
    _inherit = PREFIX + 'review.guard'
    _description = 'Structural Validation Snapshot'
    _order = 'id desc'
    input_digest = fields.Char(required=True, index=True)
    review_version = fields.Integer(required=True)
    mapping_snapshot = fields.Json(required=True)
    input_snapshot = fields.Json(required=True)
    actor_id = fields.Many2one('res.users', required=True)
    started_at = fields.Datetime(required=True)
    completed_at = fields.Datetime()
    state = fields.Selection([('running', 'Running'), ('complete', 'Complete'), ('failed', 'Failed')], required=True)
    error_summary = fields.Text()
    result_ids = fields.One2many(RESULT, 'run_id', readonly=True)
    is_current = fields.Boolean(compute='_compute_current', search='_search_current')

    @api.depends('batch_id.current_run_id', 'batch_id.review_version', 'review_version', 'state')
    def _compute_current(self):
        for rec in self:
            rec.is_current = rec.batch_id.current_run_id == rec and rec.batch_id.review_version == rec.review_version and rec.state == 'complete'

    @api.model
    def _search_current(self, operator, value):
        if operator not in ('=', '!='):
            return NotImplemented
        ids = self.search([]).filtered('is_current').ids
        return [('id', 'in' if (operator == '=') == bool(value) else 'not in', ids)]

    def _finish(self, values):
        return super(ImmutableReview, self).write(values)


class ValidationResult(models.Model):
    _name = RESULT
    _inherit = PREFIX + 'review.guard'
    _description = 'Immutable Structural Row Result'
    _order = 'row_id, id'
    _row_run_unique = models.Constraint('UNIQUE(run_id, row_id)', 'One result per row per validation snapshot.')
    run_id = fields.Many2one(RUN, required=True, ondelete='restrict', index=True)
    row_id = fields.Many2one(ROW, required=True, ondelete='restrict', index=True)
    status = fields.Selection(STATUSES, required=True, index=True)
    effective_values = fields.Json(required=True)
    provenance = fields.Json(required=True)
    parsed_candidates = fields.Json()
    duplicate_rows = fields.Json()
    has_duplicates = fields.Boolean(compute='_compute_has_duplicates', store=True, index=True)
    issue_ids = fields.One2many(ISSUE, 'result_id', readonly=True)
    is_current = fields.Boolean(related='run_id.is_current', readonly=True)

    @api.depends('duplicate_rows')
    def _compute_has_duplicates(self):
        for rec in self:
            rec.has_duplicates = bool(rec.duplicate_rows)


class ValidationIssue(models.Model):
    _name = ISSUE
    _inherit = PREFIX + 'review.guard'
    _description = 'Structural Validation Issue (historical)'
    _order = 'row_id, id'
    result_id = fields.Many2one(RESULT, required=True, ondelete='restrict', index=True)
    run_id = fields.Many2one(related='result_id.run_id', store=True, readonly=True)
    row_id = fields.Many2one(related='result_id.row_id', store=True, readonly=True, index=True)
    field_name = fields.Char()
    code = fields.Char(required=True, index=True)
    severity = fields.Selection([(s, s.title()) for s in ('error', 'warning', 'review_required', 'info')], required=True)
    message = fields.Char(required=True)
    is_current = fields.Boolean(related='run_id.is_current', readonly=True)


class Correction(models.Model):
    _name = CORRECTION
    _inherit = PREFIX + 'review.guard'
    _description = 'Append-only Row Correction and Exclusion Evidence'
    _order = 'id'
    row_id = fields.Many2one(ROW, required=True, ondelete='restrict', index=True)
    field_name = fields.Selection([(s, s.replace('_', ' ').title()) for s in lexical.TARGETS])
    operation = fields.Selection([('correct', 'Correct'), ('exclude', 'Exclude'), ('reinstate', 'Reinstate')], required=True)
    original_value = fields.Text()
    previous_value = fields.Text()
    new_value = fields.Text()
    reason = fields.Char(required=True)
    actor_id = fields.Many2one('res.users', required=True)
    corrected_at = fields.Datetime(required=True)
    review_version = fields.Integer(required=True)


class ReviewEvent(models.Model):
    _name = EVENT
    _inherit = PREFIX + 'review.guard'
    _description = 'Immutable Mapping and Review Input Version Evidence'
    _order = 'id'
    reason = fields.Char(required=True)
    actor_id = fields.Many2one('res.users', required=True)
    review_version = fields.Integer(required=True)
    input_snapshot = fields.Json(required=True)


class BatchValidation(models.Model):
    _inherit = BATCH
    mapping_ids = fields.One2many(MAPPING, 'batch_id', context={'active_test': False})
    validation_run_ids = fields.One2many(RUN, 'batch_id', readonly=True)
    correction_ids = fields.One2many(CORRECTION, 'batch_id', readonly=True)
    review_event_ids = fields.One2many(EVENT, 'batch_id', readonly=True)
    current_run_id = fields.Many2one(RUN, readonly=True, copy=False, ondelete='restrict')
    review_version = fields.Integer(default=0, readonly=True, copy=False)
    number_style = fields.Selection([(s, s.replace('_', ' ').title()) for s in ('plain', 'comma_group', 'dot_group', 'space_group')], default='plain', required=True)
    date_style = fields.Selection([('iso', 'ISO YYYY-MM-DD'), ('dmy', 'DD/MM/YYYY'), ('mdy', 'MM/DD/YYYY')], default='iso', required=True)
    inherit_currency = fields.Boolean(default=False, help='Explicitly use revision currency only when no currency column is mapped.')
    inherit_date = fields.Boolean(default=False, help='Explicitly use revision proposed effective date only when no date column is mapped.')
    mapping_status = fields.Char(compute='_compute_mapping_status')
    mapping_errors = fields.Text(compute='_compute_mapping_status')
    validation_state = fields.Selection([(s, s.replace('_', ' ').title()) for s in ('not_started', 'mapping_incomplete', 'pending_validation', 'validation_running', 'review_required', 'structural_validation_complete', 'validation_failed', 'validation_stale')], default='not_started', readonly=True, copy=False)
    ready_rows = fields.Integer(readonly=True)
    blocked_rows = fields.Integer(readonly=True)
    review_rows = fields.Integer(readonly=True)
    excluded_rows = fields.Integer(readonly=True)
    pending_rows = fields.Integer(compute='_compute_pending_rows')
    rows_with_warnings = fields.Integer(readonly=True)
    active_error_issues = fields.Integer(readonly=True)
    active_warning_issues = fields.Integer(readonly=True)
    active_review_issues = fields.Integer(readonly=True)

    @api.depends('extracted_row_count', 'ready_rows', 'blocked_rows', 'review_rows', 'excluded_rows')
    def _compute_pending_rows(self):
        for rec in self:
            rec.pending_rows = max(0, rec.extracted_row_count - rec.ready_rows - rec.blocked_rows - rec.review_rows - rec.excluded_rows)

    def _check_review_access(self):
        if not self:
            raise ValidationError(_('Select an existing extracted batch.'))
        self._check_intake_access()
        if any(rec.state != 'extracted' for rec in self):
            raise UserError(_('Only successfully extracted batches on editable drafts can be structurally reviewed.'))

    def write(self, vals):
        if set(vals) <= OPTIONS | {'mapping_ids'}:
            self._check_review_access()
            self._lock()
            for command in vals.get('mapping_ids', []):
                if command[0] not in (0, 1):
                    raise AccessError(_('Mapping definitions are retained; disable a row instead of deleting/relinking.'))
                if command[0] == 1:
                    child = self.env[MAPPING].browse(command[1])
                    child.check_access('write')
                    if len(self) != 1 or child.batch_id != self:
                        raise AccessError(_('Nested edits must target this batch\'s own mapping.'))
                elif 'batch_id' in command[2]:
                    raise AccessError(_('Nested mapping ownership follows its parent.'))
            result = super(ImportBatch, self).write(vals)
            if OPTIONS.intersection(vals):
                self._invalidate_review('settings_change')
            return result
        return super().write(vals)

    def _mapping_problems(self):
        self.ensure_one()
        targets = set(self.mapping_ids.filtered('active').mapped('target'))
        errors = []
        if not targets.intersection(lexical.IDENTIFIERS):
            errors.append('Map at least one supplier identifier or description column.')
        for target in lexical.REQUIRED:
            inherited = target == 'currency_raw' and self.inherit_currency or target == 'effective_date_raw' and self.inherit_date
            if target not in targets and not inherited:
                errors.append('Map required field: ' + target)
            if target in targets and inherited:
                errors.append('Choose a column or revision inheritance, not both: ' + target)
        if self.inherit_date and not self.revision_id.proposed_effective_date:
            errors.append('Revision proposed effective date is missing for explicit inheritance.')
        return errors

    @api.depends('mapping_ids.active', 'mapping_ids.column_number', 'mapping_ids.target', 'inherit_currency', 'inherit_date', 'revision_id.proposed_effective_date')
    def _compute_mapping_status(self):
        for rec in self:
            errors = rec._mapping_problems()
            rec.mapping_status = 'not_mapped' if not rec.mapping_ids else 'incomplete' if errors else 'ready'
            rec.mapping_errors = '\n'.join(errors)

    def _invalidate_review(self, reason):
        for rec in self:
            rec._set({'review_version': rec.review_version + 1, 'current_run_id': False,
                'validation_state': 'validation_stale' if rec.validation_run_ids else 'pending_validation',
                'ready_rows': 0, 'blocked_rows': 0, 'review_rows': 0,
                'excluded_rows': len(rec.row_ids.filtered('excluded')),
                'rows_with_warnings': 0, 'active_error_issues': 0, 'active_warning_issues': 0, 'active_review_issues': 0})
            self.env[EVENT]._record({'batch_id': rec.id, 'reason': reason,
                'actor_id': self.env.uid, 'review_version': rec.review_version,
                'input_snapshot': rec._review_input()})
            for rows, status in [(rec.row_ids.filtered('excluded'), 'excluded'),
                                 (rec.row_ids.filtered(lambda r: not r.excluded), 'pending_validation')]:
                rows._review_set({'validation_status': status, 'current_result_id': False})

    def _review_input(self):
        self.ensure_one()
        return {'source_hash': self.sha256_digest, 'sheet': self.worksheet_name,
            'headers': self.headers, 'mapping': [(r.id, r.column_number, r.target, r.active) for r in self.mapping_ids],
            'options': {key: self[key] for key in sorted(OPTIONS)}, 'review_version': self.review_version,
            'revision_currency': self.revision_id.currency_id.name if self.inherit_currency else None,
            'revision_date': str(self.revision_id.proposed_effective_date) if self.inherit_date else None,
            'corrections': self.correction_ids.ids}

    def action_validate_structure(self):
        self.ensure_one()
        self._check_review_access()
        self._lock()
        problems = self._mapping_problems()
        if problems:
            self._set({'validation_state': 'mapping_incomplete'})
            self.row_ids.filtered(lambda r: not r.excluded)._review_set({'validation_status': 'pending_mapping', 'current_result_id': False})
            return False
        snapshot = self._review_input()
        fingerprint = lexical.digest(snapshot)
        if self.current_run_id and self.current_run_id.input_digest == fingerprint and self.current_run_id.state == 'complete':
            return True
        run = self.env[RUN]._record({'batch_id': self.id, 'review_version': self.review_version,
            'input_digest': fingerprint, 'input_snapshot': snapshot,
            'mapping_snapshot': snapshot['mapping'], 'actor_id': self.env.uid,
            'started_at': fields.Datetime.now(), 'state': 'running'})
        self._set({'validation_state': 'validation_running', 'current_run_id': False})
        try:
            with self.env.cr.savepoint():
                candidates, groups = [], defaultdict(list)
                mappings = self.mapping_ids.filtered('active')
                corrections = defaultdict(list)
                for event in self.correction_ids:
                    corrections[event.row_id.id].append(event)
                for row in self.row_ids:
                    values, provenance = row._effective_values(mappings, corrections[row.id])
                    status, parsed, issues = lexical.validate_values(values, provenance, self.number_style, self.date_style)
                    if row.excluded:
                        status, issues = 'excluded', []
                    else:
                        groups[lexical.duplicate_key(values, parsed)].append(row.source_row)
                    candidates.append((row, values, provenance, status, parsed, issues))
                counts, severities, warnings = Counter(), Counter(), 0
                for row, values, provenance, status, parsed, issues in candidates:
                    duplicate = groups.get(lexical.duplicate_key(values, parsed), []) if not row.excluded else []
                    if len(duplicate) > 1:
                        issues.append(dict(field_name='', code='DUPLICATE_ROW_CANDIDATE', severity='review_required',
                            message='Matching commercial candidates in source rows ' + ', '.join(map(str, duplicate[:30])) + '; exclude or correct after review.'))
                        if status != 'blocked':
                            status = 'needs_review'
                    result = self.env[RESULT]._record({'batch_id': self.id, 'run_id': run.id, 'row_id': row.id,
                        'status': status, 'effective_values': values, 'provenance': provenance,
                        'parsed_candidates': parsed, 'duplicate_rows': duplicate if len(duplicate) > 1 else []})
                    for issue in issues:
                        self.env[ISSUE]._record(dict(issue, batch_id=self.id, result_id=result.id))
                        severities[issue['severity']] += 1
                    counts[status] += 1
                    warnings += any(i['severity'] == 'warning' for i in issues)
                    row._review_set({'current_result_id': result.id, 'validation_status': status})
                run._finish({'state': 'complete', 'completed_at': fields.Datetime.now()})
                self._set({'current_run_id': run.id, 'validation_state': 'structural_validation_complete' if counts['structurally_ready'] and not counts['blocked'] and not counts['needs_review'] else 'review_required',
                    'ready_rows': counts['structurally_ready'], 'blocked_rows': counts['blocked'],
                    'review_rows': counts['needs_review'], 'excluded_rows': counts['excluded'],
                    'active_error_issues': severities['error'], 'active_warning_issues': severities['warning'],
                    'active_review_issues': severities['review_required'], 'rows_with_warnings': warnings})
        except (SerializationFailure, DeadlockDetected):
            raise  # Odoo must retry a fresh transaction, never conceal a conflict.
        except (DatabaseError, ValueError, TypeError, RuntimeError) as exc:
            run._finish({'state': 'failed', 'completed_at': fields.Datetime.now(),
                'error_summary': 'Structural validation failed atomically; no partial current snapshot was retained. Retry is available.'})
            self._invalidate_review('validation_failed')
            self._set({'validation_state': 'validation_failed'})
            return False
        return True

    def action_review_rows(self):
        self.ensure_one()
        self.check_access('read')
        return {'type': 'ir.actions.act_window', 'name': _('Source Row Structural Review'),
            'res_model': ROW, 'view_mode': 'list,form', 'domain': [('batch_id', '=', self.id)]}

    def get_structurally_ready_rows(self):
        self.ensure_one()
        self.check_access('read')
        if not self.current_run_id or self.current_run_id.input_digest != lexical.digest(self._review_input()):
            raise UserError(_('Current structural validation is missing or stale.'))
        return self.row_ids.filtered(lambda r: r.validation_status == 'structurally_ready' and not r.excluded)


class RowValidation(models.Model):
    _inherit = ROW
    validation_status = fields.Selection(STATUSES, default='pending_mapping', readonly=True, index=True)
    current_result_id = fields.Many2one(RESULT, readonly=True, copy=False, ondelete='restrict')
    effective_values = fields.Json(compute='_compute_effective')
    current_issue_ids = fields.One2many(related='current_result_id.issue_ids', readonly=True)
    issue_count = fields.Integer(compute='_compute_issue_count')
    correction_ids = fields.One2many(CORRECTION, 'row_id', readonly=True)
    excluded = fields.Boolean(default=False, readonly=True)
    corrected = fields.Boolean(default=False, readonly=True, index=True)

    @api.depends('current_result_id.issue_ids')
    def _compute_issue_count(self):
        for row in self:
            row.issue_count = len(row.current_issue_ids)

    @api.depends('correction_ids', 'batch_id.mapping_ids', 'batch_id.review_version')
    def _compute_effective(self):
        for row in self:
            row.effective_values = row._effective_values(row.batch_id.mapping_ids.filtered('active'), row.correction_ids)[0]

    def _review_set(self, values):
        return super(ImportRow, self).write(values)

    def _effective_values(self, mappings, events):
        self.ensure_one()
        values, provenance = {}, {}
        for mapping in mappings:
            index = mapping.column_number - 1
            cell = self.raw_cells[index] if index < len(self.raw_cells) else {'value': None, 'type': 'blank'}
            value = cell.get('value')
            values[mapping.target] = '' if value is None else str(value).strip()
            provenance[mapping.target] = {'source': 'FILE_COLUMN', 'column': mapping.column_number,
                'header': mapping.header_text, 'type': cell.get('type'), 'sheet': self.batch_id.worksheet_name}
        for target, allowed, value in [('currency_raw', self.batch_id.inherit_currency, self.batch_id.revision_id.currency_id.name),
                ('effective_date_raw', self.batch_id.inherit_date, self.batch_id.revision_id.proposed_effective_date)]:
            if allowed and target not in values:
                values[target] = str(value or '')
                provenance[target] = {'source': 'REVISION_HEADER', 'type': 'date' if target == 'effective_date_raw' else 'text'}
        for event in events:
            if event.operation == 'correct':
                values[event.field_name] = event.new_value or ''
                provenance[event.field_name] = {'source': 'CORRECTION', 'correction_id': event.id, 'type': 'text'}
        return values, provenance

    def action_correct(self, field_name, new_value, reason):
        self.ensure_one()
        self.check_access('read')
        batch = self.batch_id
        batch._check_review_access()
        batch._lock()
        if field_name not in lexical.TARGETS or not isinstance(new_value, str) or len(new_value) > 4000:
            raise ValidationError(_('Choose a supported canonical field and bounded text value.'))
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
            raise ValidationError(_('A correction reason of 1–500 characters is required.'))
        effective = self._effective_values(batch.mapping_ids.filtered('active'), self.correction_ids)[0]
        original = self._effective_values(batch.mapping_ids.filtered('active'), [])[0]
        mapping = batch.mapping_ids.filtered(lambda r: r.active and r.target == field_name)
        if mapping and mapping.column_number <= len(self.raw_cells):
            source = self.raw_cells[mapping.column_number - 1].get('value')
            original[field_name] = '' if source is None else str(source)
        if effective.get(field_name, '') == new_value:
            return True
        self.env[CORRECTION]._record({'batch_id': batch.id, 'row_id': self.id, 'operation': 'correct',
            'field_name': field_name, 'original_value': original.get(field_name, ''),
            'previous_value': effective.get(field_name, ''), 'new_value': new_value,
            'reason': reason.strip(), 'actor_id': self.env.uid, 'corrected_at': fields.Datetime.now(),
            'review_version': batch.review_version + 1})
        self._review_set({'corrected': True})
        batch._invalidate_review('correction')
        return True

    def action_set_excluded(self, excluded, reason):
        self.ensure_one()
        self.check_access('read')
        self.batch_id._check_review_access()
        self.batch_id._lock()
        if not isinstance(excluded, bool) or not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
            raise ValidationError(_('Exclusion/reinstatement requires a reason of 1–500 characters.'))
        if self.excluded == excluded:
            return True
        self.env[CORRECTION]._record({'batch_id': self.batch_id.id, 'row_id': self.id,
            'operation': 'exclude' if excluded else 'reinstate', 'previous_value': str(self.excluded),
            'new_value': str(excluded), 'reason': reason.strip(), 'actor_id': self.env.uid,
            'corrected_at': fields.Datetime.now(), 'review_version': self.batch_id.review_version + 1})
        self._review_set({'excluded': excluded})
        self.batch_id._invalidate_review('exclusion')
        return True

    def action_open_correction(self):
        self.ensure_one()
        self.batch_id._check_review_access()
        return {'type': 'ir.actions.act_window', 'name': _('Correct or Exclude Source Row'),
            'res_model': PREFIX + 'review.wizard', 'view_mode': 'form', 'target': 'new',
            'context': {'default_row_id': self.id}}


class ReviewWizard(models.TransientModel):
    _name = PREFIX + 'review.wizard'
    _inherit = 'vendor.price.revision.intake.read.guard'
    _description = 'Controlled Source Row Correction'
    row_id = fields.Many2one(ROW, required=True)
    company_id = fields.Many2one(related='row_id.company_id', store=True, readonly=True)
    operation = fields.Selection([('correct', 'Correct effective value'), ('exclude', 'Exclude row'), ('reinstate', 'Reinstate row')], default='correct', required=True)
    field_name = fields.Selection([(s, s.replace('_', ' ').title()) for s in lexical.TARGETS], default='proposed_price_raw')
    new_value = fields.Text()
    reason = fields.Char(required=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            row_id = vals.get('row_id') or self.default_get(['row_id']).get('row_id')
            row = self.env[ROW].browse(row_id)
            row.check_access('read')
            row.batch_id._check_review_access()
            if set(vals) - {'row_id', 'operation', 'field_name', 'new_value', 'reason'}:
                raise AccessError(_('Review wizard ownership is derived from its source row.'))
            vals['row_id'] = row.id
        return super().create(vals_list)

    def write(self, vals):
        self.check_access('write')
        self.row_id.batch_id._check_review_access()
        if 'row_id' in vals or 'company_id' in vals:
            raise AccessError(_('A review wizard cannot be moved to another source row.'))
        return super().write(vals)

    def action_save_review(self):
        self.ensure_one()
        self.check_access('write')
        self.row_id.check_access('read')
        if self.operation == 'correct':
            self.row_id.action_correct(self.field_name, self.new_value or '', self.reason)
        else:
            self.row_id.action_set_excluded(self.operation == 'exclude', self.reason)
        return {'type': 'ir.actions.act_window_close'}


class RevisionReviewContext(models.Model):
    _inherit = 'vendor.price.revision'

    def write(self, vals):
        batches = self.env[BATCH].search([('revision_id', 'in', self.ids), ('state', '=', 'extracted')]) if 'proposed_effective_date' in vals else self.env[BATCH]
        batches._lock()
        result = super().write(vals)
        batches.filtered('inherit_date')._invalidate_review('revision_date_change')
        return result
