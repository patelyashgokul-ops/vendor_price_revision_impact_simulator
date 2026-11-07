"""Secure intake lifecycle. No price mapping, calculation or application."""
import time

from psycopg2 import DatabaseError

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.binary import BinaryValue

from . import import_parser as parser
from .vendor_price_revision import MODULE, PURCHASE_USER, PURCHASE_MANAGER, CONFIDENTIAL_GROUPS

BATCH = 'vendor.price.revision.import.batch'
ROW = 'vendor.price.revision.import.row'
ATTEMPT = 'vendor.price.revision.import.attempt'
WIZARD = 'vendor.price.revision.import.wizard'
EVIDENCE = 'vendor.price.revision.evidence'
ADMIN = MODULE + '.group_vpr_configuration_admin'


def clean_defaults(record):
    """Internal system-authored values must not inherit user default_* payloads."""
    return record.with_context({key: value for key, value in record.env.context.items()
                               if not key.startswith('default_')})


def binary_bytes(value):
    if not isinstance(value, BinaryValue):
        raise ValidationError(_('A supported Odoo binary upload is required.'))
    return value.content


class ImportLimits(models.Model):
    _name = 'vendor.price.revision.import.limit'
    _description = 'Company Supplier File Resource Limits'
    _check_company_auto = True
    _company_unique = models.Constraint('UNIQUE(company_id)', 'Only one intake resource policy is allowed per company.')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    upload_mib = fields.Integer(default=10, required=True)
    max_rows = fields.Integer(default=10000, required=True)
    max_columns = fields.Integer(default=100, required=True)
    max_cell_chars = fields.Integer(default=16384, required=True)
    uncompressed_mib = fields.Integer(default=64, required=True)
    max_members = fields.Integer(default=256, required=True)
    max_ratio = fields.Integer(default=200, required=True)
    max_seconds = fields.Integer(default=20, required=True)

    def read(self, fields=None, load='_classic_read'):
        self.check_access('read')
        return super().read(fields=fields, load=load)

    def export_data(self, fields_to_export):
        self.check_access('read')
        return super().export_data(fields_to_export)

    def _admin(self):
        if not self.env.su and (not self.env.user.active or not self.env.user.has_group(ADMIN)):
            raise AccessError(_('Only Configuration Administrators may manage intake resource limits.'))

    @api.model_create_multi
    def create(self, vals_list):
        self._admin()
        for vals in vals_list:
            company_id = vals.get('company_id', self.default_get(['company_id']).get('company_id'))
            if company_id not in self.env.companies.ids:
                raise AccessError(_('Unauthorized company resource policy.'))
            vals['company_id'] = company_id
        return super().create(vals_list)

    def write(self, vals):
        self._admin()
        self.check_access('write')
        if 'company_id' in vals:
            raise AccessError(_('Resource policy ownership cannot be changed.'))
        return super().write(vals)

    def unlink(self):
        raise AccessError(_('Resource policies are retained; edit their limits instead.'))

    @api.constrains(*parser.DEFAULT_LIMITS)
    def _check_bounds(self):
        bounds = dict(upload_mib=(1, 25), max_rows=(1, 20000), max_columns=(1, 200),
            max_cell_chars=(32, 32768), uncompressed_mib=(1, 128), max_members=(8, 1024),
            max_ratio=(10, 500), max_seconds=(1, 60))
        for rec in self:
            if any(not lower <= rec[key] <= upper for key, (lower, upper) in bounds.items()):
                raise ValidationError(_('Intake resource limits exceed supported administrator-controlled bounds.'))

    @api.model
    def for_company(self, company):
        if company not in self.env.companies:
            raise AccessError(_('Unauthorized company resource lookup.'))
        rec = self.search([('company_id', '=', company.id)])
        return {key: rec[key] for key in parser.DEFAULT_LIMITS} if rec else dict(parser.DEFAULT_LIMITS)


class IntakeReadGuard(models.AbstractModel):
    _name = 'vendor.price.revision.intake.read.guard'
    _description = 'Intake explicit ID/read/export protection'

    def read(self, fields=None, load='_classic_read'):
        self.check_access('read')
        return super().read(fields=fields, load=load)

    def export_data(self, fields_to_export):
        self.check_access('read')
        return super().export_data(fields_to_export)


class ImportBatch(models.Model):
    _name = BATCH
    _inherit = 'vendor.price.revision.intake.read.guard'
    _description = 'Supplier Source Extraction Batch'
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(required=True, readonly=True)
    revision_id = fields.Many2one('vendor.price.revision', required=True, ondelete='restrict', index=True)
    company_id = fields.Many2one(related='revision_id.company_id', store=True, readonly=True, index=True)
    vendor_id = fields.Many2one(related='revision_id.vendor_id', store=True, readonly=True)
    evidence_id = fields.Many2one(EVIDENCE, readonly=True, ondelete='restrict', copy=False)
    attachment_id = fields.Many2one(related='evidence_id.attachment_id', readonly=True)
    original_filename = fields.Char(required=True, readonly=True)
    detected_format = fields.Selection([('csv', 'CSV'), ('xlsx', 'XLSX')], required=True, readonly=True)
    mimetype = fields.Char(readonly=True)
    file_size = fields.Integer(readonly=True)
    sha256_digest = fields.Char(required=True, readonly=True, index=True)
    uploaded_by = fields.Many2one('res.users', required=True, readonly=True)
    uploaded_at = fields.Datetime(required=True, readonly=True)
    state = fields.Selection([(s, s.replace('_', ' ').title()) for s in
        ('uploaded', 'extracting', 'extracted', 'extraction_failed', 'duplicate_review', 'cancelled')], required=True, readonly=True)
    csv_encoding = fields.Selection([(s, s) for s in parser.ENCODINGS], default='utf-8-sig', required=True)
    csv_delimiter = fields.Selection([(s, s.title()) for s in parser.DELIMITERS], default='comma', required=True)
    worksheet_name = fields.Char()
    sheet_index = fields.Integer(readonly=True, default=-1)
    available_sheets = fields.Json(readonly=True)
    header_row_number = fields.Integer(default=0, help='0: first nonblank logical row; otherwise source row 1–100.')
    headers = fields.Json(readonly=True)
    total_logical_rows = fields.Integer(readonly=True)
    extracted_row_count = fields.Integer(readonly=True)
    skipped_blank_rows = fields.Integer(readonly=True)
    preamble_rows = fields.Integer(readonly=True)
    warning_count = fields.Integer(readonly=True)
    technical_error_count = fields.Integer(readonly=True)
    error_code = fields.Char(readonly=True)
    error_summary = fields.Text(readonly=True)
    started_at = fields.Datetime(readonly=True)
    completed_at = fields.Datetime(readonly=True)
    notes = fields.Text(readonly=True)
    row_ids = fields.One2many(ROW, 'batch_id', readonly=True)
    attempt_ids = fields.One2many(ATTEMPT, 'batch_id', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Import batches are created only by authorized source intake.'))

    def write(self, vals):
        self._check_intake_access()
        if any(rec.state != 'extraction_failed' for rec in self) or set(vals) - {
            'csv_encoding', 'csv_delimiter', 'worksheet_name', 'header_row_number'}:
            raise AccessError(_('Only failed-batch extraction settings may be corrected. Source and history are immutable.'))
        self._lock()
        return super().write(vals)

    def unlink(self):
        raise AccessError(_('Import batches and evidence must be retained.'))

    def copy(self, default=None):
        raise AccessError(_('Upload a new source instead of copying a batch.'))

    def _check_intake_access(self):
        self.check_access('write')
        if not self.env.su and (not self.env.user.active or not self.env.user.has_group(PURCHASE_USER)):
            raise AccessError(_('Only authorized purchase preparers may perform intake.'))
        self.revision_id._check_draft_edit_access()

    def _lock(self):
        for rec in self.sorted('id'):
            self.env.cr.execute('UPDATE vendor_price_revision_import_batch SET id = id WHERE id = %s', [rec.id])
        self.invalidate_recordset()

    def _set(self, values):
        return super().write(values)

    @api.model
    def _accept(self, wizard, raw, info, limits):
        revision = wizard.revision_id
        revision._check_draft_edit_access()
        # Company serialization also covers duplicate checks across revisions.
        # A row version forces repeatable-read competitors to retry fresh.
        self.env.cr.execute('UPDATE res_company SET id = id WHERE id = %s', [revision.company_id.id])
        # Serialize revision changes and acceptance without intermediate commits.
        self.env.cr.execute('UPDATE vendor_price_revision SET id = id WHERE id = %s', [revision.id])
        digest = parser.fingerprint(raw)
        duplicate = bool(self.search_count([('company_id', '=', revision.company_id.id),
            ('vendor_id', '=', revision.vendor_id.id), ('sha256_digest', '=', digest)]))
        batch = super(ImportBatch, clean_defaults(self)).create({
            'name': 'Source ' + digest[:12], 'revision_id': revision.id,
            'original_filename': parser.safe_filename(wizard.upload_filename),
            'detected_format': info['format'], 'mimetype': info['mimetype'], 'file_size': len(raw),
            'sha256_digest': digest, 'uploaded_by': self.env.uid, 'uploaded_at': fields.Datetime.now(),
            'state': 'duplicate_review' if duplicate else 'uploaded',
            'csv_encoding': wizard.csv_encoding, 'csv_delimiter': wizard.csv_delimiter,
            'worksheet_name': wizard.worksheet_name, 'available_sheets': info['sheets'],
            'header_row_number': wizard.header_row_number, 'notes': wizard.import_notes,
        })
        evidence = self.env[EVIDENCE]._create_source(batch, raw)
        batch._set({'evidence_id': evidence.id})
        if not duplicate:
            batch.action_extract()
        return batch

    def action_extract(self):
        self.ensure_one()
        self._check_intake_access()
        self._lock()
        if self.state == 'extracted':
            return True  # A repeat click never creates another attempt or row.
        if self.state not in ('uploaded', 'extraction_failed', 'extracting'):
            raise UserError(_('This batch is not eligible for extraction. Duplicate sources require later review.'))
        if self.row_ids:
            raise UserError(_('Existing staged data requires administrator investigation; extraction cannot duplicate it.'))
        limits = self.env['vendor.price.revision.import.limit'].for_company(self.company_id)
        options = {key: self[key] for key in ('csv_encoding', 'csv_delimiter', 'worksheet_name', 'header_row_number')}
        attempt = self.env[ATTEMPT]._start(self, options, limits)
        self._set({'state': 'extracting', 'started_at': fields.Datetime.now(), 'completed_at': False,
                   'error_code': False, 'error_summary': False})
        began = time.monotonic()
        try:
            with self.env.cr.savepoint():
                raw = binary_bytes(self.attachment_id.raw)
                if len(raw) != self.file_size or parser.fingerprint(raw) != self.sha256_digest:
                    raise parser.IntakeError('source_integrity', 'Original source integrity verification failed.')
                result = parser.extract(raw, self.original_filename, options, limits)
                rows = result.pop('rows')
                for offset in range(0, len(rows), 250):
                    parser.deadline_check(began, limits)
                    self.env[ROW]._stage(self, rows[offset:offset + 250])
                result.update(state='extracted', extracted_row_count=len(rows),
                    completed_at=fields.Datetime.now(), error_code=False, error_summary=False)
                self._set(result)
        except (parser.IntakeError, DatabaseError, OSError, ValueError, KeyError, TypeError, RuntimeError, OverflowError) as exc:
            # Savepoint has already rolled back incomplete rows. Never persist raw
            # parser/SQL messages, workbook text, paths or secrets.
            code = exc.code if isinstance(exc, parser.IntakeError) else 'technical_failure'
            message = str(exc) if isinstance(exc, parser.IntakeError) else _('Technical extraction failed. No partial rows were retained; an authorized retry is available.')
            self._set({'state': 'extraction_failed', 'completed_at': fields.Datetime.now(),
                'technical_error_count': self.technical_error_count + 1, 'error_code': code,
                'error_summary': message, 'extracted_row_count': 0})
            attempt._finish('failed', code, message)
            return False
        attempt._finish('extracted')
        return True

    def action_cancel(self):
        self._check_intake_access()
        self._lock()
        if any(rec.state == 'extracted' for rec in self):
            raise UserError(_('Successfully extracted evidence is retained; cancellation cannot discard staging.'))
        self._set({'state': 'cancelled', 'completed_at': fields.Datetime.now()})


class ImportRow(models.Model):
    _name = ROW
    _inherit = 'vendor.price.revision.intake.read.guard'
    _description = 'Untrusted Supplier Source Row (not a validated price)'
    _order = 'batch_id, source_row, id'
    _row_unique = models.Constraint('UNIQUE(batch_id, source_row)', 'A source row can be staged only once per batch.')
    batch_id = fields.Many2one(BATCH, required=True, ondelete='restrict', index=True)
    revision_id = fields.Many2one(related='batch_id.revision_id', store=True, readonly=True)
    company_id = fields.Many2one(related='batch_id.company_id', store=True, readonly=True, index=True)
    source_row = fields.Integer(required=True)
    physical_start = fields.Integer(required=True)
    physical_end = fields.Integer(required=True)
    worksheet_name = fields.Char(related='batch_id.worksheet_name', readonly=True)
    column_count = fields.Integer(required=True)
    raw_cells = fields.Json(required=True)
    formula_columns = fields.Json()
    status = fields.Selection([('raw', 'Unvalidated raw data'), ('review', 'Untrusted formula/text requires review')], required=True)

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Raw rows can only be created by controlled extraction.'))

    @api.model
    def _stage(self, batch, rows):
        batch._check_intake_access()
        return super(ImportRow, clean_defaults(self)).create([dict(row, batch_id=batch.id) for row in rows])

    def write(self, vals):
        raise AccessError(_('Raw source rows are immutable and cannot be reassigned.'))

    def unlink(self):
        raise AccessError(_('Raw source rows are retained.'))


class ImportAttempt(models.Model):
    _name = ATTEMPT
    _inherit = 'vendor.price.revision.intake.read.guard'
    _description = 'Immutable Extraction Attempt History'
    _order = 'id desc'
    batch_id = fields.Many2one(BATCH, required=True, ondelete='restrict', index=True)
    company_id = fields.Many2one(related='batch_id.company_id', store=True, readonly=True, index=True)
    started_by = fields.Many2one('res.users', required=True)
    started_at = fields.Datetime(required=True)
    completed_at = fields.Datetime()
    options = fields.Json(required=True)
    limits = fields.Json(required=True)
    state = fields.Selection([('extracting', 'Extracting'), ('failed', 'Failed'), ('extracted', 'Extracted')], required=True)
    error_code = fields.Char()
    error_summary = fields.Text()

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_('Extraction attempt history is system-authored.'))

    @api.model
    def _start(self, batch, options, limits):
        batch._check_intake_access()
        return super(ImportAttempt, clean_defaults(self)).create({'batch_id': batch.id, 'started_by': self.env.uid,
            'started_at': fields.Datetime.now(), 'options': options, 'limits': limits, 'state': 'extracting'})

    def _finish(self, state, code=False, message=False):
        return super().write({'state': state, 'completed_at': fields.Datetime.now(),
                              'error_code': code, 'error_summary': message})

    def write(self, vals):
        raise AccessError(_('Extraction attempt history is immutable.'))

    def unlink(self):
        raise AccessError(_('Extraction attempt history is retained.'))


class ImportWizard(models.TransientModel):
    _name = WIZARD
    _inherit = 'vendor.price.revision.intake.read.guard'
    _description = 'Upload and Extract Supplier Source'
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    revision_id = fields.Many2one('vendor.price.revision', required=True)
    vendor_id = fields.Many2one(related='revision_id.vendor_id', readonly=True)
    upload_file = fields.Binary(attachment=False)
    upload_filename = fields.Char()
    file_format = fields.Selection([('csv', 'CSV'), ('xlsx', 'XLSX')], required=True, default='csv')
    csv_encoding = fields.Selection([(s, s) for s in parser.ENCODINGS], default='utf-8-sig', required=True)
    csv_delimiter = fields.Selection([(s, s.title()) for s in parser.DELIMITERS], default='comma', required=True)
    worksheet_name = fields.Char()
    available_sheets = fields.Json(readonly=True)
    header_row_number = fields.Integer(default=0)
    import_notes = fields.Text()
    result_batch_id = fields.Many2one(BATCH, readonly=True, copy=False)

    def _authorize(self):
        self.check_access('write')
        if not self.env.su and (not self.env.user.active or not self.env.user.has_group(PURCHASE_USER)):
            raise AccessError(_('Only purchase preparers may upload supplier files.'))
        if self.company_id not in self.env.companies:
            raise AccessError(_('Unauthorized company for source intake.'))
        if not self.revision_id.exists():
            raise ValidationError(_('Select an existing draft revision.'))
        self.revision_id._check_draft_edit_access()
        if self.revision_id.company_id != self.company_id:
            raise AccessError(_('Wizard company must match the selected revision.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('result_batch_id') or vals.get('available_sheets'):
                raise AccessError(_('Wizard result metadata is system-authored.'))
            vals.update(result_batch_id=False, available_sheets=False)
            self._validate_upload_values(vals)
        records = super().create(vals_list)
        records._authorize()
        return records

    def write(self, vals):
        self._authorize()
        if {'result_batch_id', 'available_sheets'}.intersection(vals) or any(self.mapped('result_batch_id')):
            raise AccessError(_('Completed upload wizards cannot be changed or replayed with a different source.'))
        for record in self:
            record._validate_upload_values(vals)
        result = super().write(vals)
        self._authorize()
        return result

    def _validate_upload_values(self, vals):
        if not vals.get('upload_file'):
            return
        company_id = vals.get('company_id') or (self.company_id.id if self else self.default_get(['company_id']).get('company_id'))
        company = self.env['res.company'].browse(company_id)
        limits = self.env['vendor.price.revision.import.limit'].for_company(company)
        value = vals['upload_file']
        if isinstance(value, str) and len(value) > (limits['upload_mib'] * 1024 * 1024 + 2) // 3 * 4:
            raise ValidationError(_('Upload exceeds the configured file-size limit.'))
        binary = self._fields['upload_file'].convert_to_cache(value, self)
        if binary and binary.size > limits['upload_mib'] * 1024 * 1024:
            raise ValidationError(_('Upload exceeds the configured file-size limit.'))

    def _inspect(self):
        self.ensure_one()
        self._authorize()
        limits = self.env['vendor.price.revision.import.limit'].for_company(self.company_id)
        if not self.upload_file or self.upload_file.size > limits['upload_mib'] * 1024 * 1024:
            raise ValidationError(_('Upload an original source within the configured file-size limit.'))
        raw = binary_bytes(self.upload_file)
        try:
            info = parser.inspect_source(raw, self.upload_filename, limits)
        except parser.IntakeError as exc:
            raise ValidationError(str(exc)) from None
        if info['format'] != self.file_format:
            raise ValidationError(_('Selected file format must match the detected supported source format.'))
        super().write({'available_sheets': info['sheets']})
        return raw, info, limits

    def action_inspect(self):
        self._inspect()
        return self._reopen()

    def _reopen(self):
        return {'type': 'ir.actions.act_window', 'name': _('Import Supplier Price File'),
            'res_model': WIZARD, 'res_id': self.id, 'view_mode': 'form', 'target': 'new'}

    def action_upload_extract(self):
        self.ensure_one()
        self._authorize()
        self.env.cr.execute('UPDATE vendor_price_revision_import_wizard SET id = id WHERE id = %s', [self.id])
        self.invalidate_recordset()
        if self.result_batch_id:
            return self._batch_action()
        raw, info, limits = self._inspect()
        if info['format'] == 'xlsx':
            visible = [s['name'] for s in info['sheets'] if s['state'] == 'visible']
            if not visible:
                raise ValidationError(_('The workbook has no visible worksheet suitable for extraction.'))
            selected = self.worksheet_name or (visible[0] if len(info['sheets']) == 1 and visible else '')
            if self.worksheet_name and selected not in visible:
                raise ValidationError(_('The selected worksheet is missing or hidden. Inspect and select an existing visible worksheet.'))
            if selected not in visible:
                return self._reopen()  # sheet names retained for explicit selection
            super().write({'worksheet_name': selected})
        with self.env.cr.savepoint():
            batch = self.env[BATCH]._accept(self, raw, info, limits)
            super().write({'result_batch_id': batch.id, 'upload_file': False})
        return self._batch_action()

    def _batch_action(self):
        self.result_batch_id.check_access('read')
        return {'type': 'ir.actions.act_window', 'name': _('Source Extraction Batch'),
            'res_model': BATCH, 'res_id': self.result_batch_id.id, 'view_mode': 'form'}


class RevisionIntake(models.Model):
    _inherit = 'vendor.price.revision'

    def action_import_supplier_file(self):
        self.ensure_one()
        self._check_draft_edit_access()
        return {'type': 'ir.actions.act_window', 'name': _('Import Supplier Price File'),
            'res_model': WIZARD, 'view_mode': 'form', 'target': 'new',
            'context': {'default_revision_id': self.id, 'default_company_id': self.company_id.id}}


class SourceEvidence(models.Model):
    _inherit = EVIDENCE
    import_batch_id = fields.Many2one(BATCH, readonly=True, ondelete='restrict', copy=False)
    attachment_id = fields.Many2one('ir.attachment', readonly=True, ondelete='restrict', copy=False, groups=CONFIDENTIAL_GROUPS)
    sha256_digest = fields.Char(readonly=True, copy=False, index=True, groups=CONFIDENTIAL_GROUPS)
    file_size = fields.Integer(readonly=True, copy=False)
    detected_format = fields.Selection([('csv', 'CSV'), ('xlsx', 'XLSX')], readonly=True, copy=False)
    mimetype = fields.Char(readonly=True, copy=False)
    uploaded_by = fields.Many2one('res.users', readonly=True, copy=False)
    uploaded_at = fields.Datetime(readonly=True, copy=False)

    @api.model
    def _source_fields(self):
        return ('import_batch_id', 'attachment_id', 'sha256_digest', 'file_size',
                'detected_format', 'mimetype', 'uploaded_by', 'uploaded_at')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if any(vals.get(key) for key in self._source_fields()):
                raise AccessError(_('Uploaded evidence metadata can only be generated by source intake.'))
            vals.update({key: False for key in self._source_fields()})
        return super().create(vals_list)

    def write(self, vals):
        self.check_access('write')
        if any(self.mapped('import_batch_id')) or set(self._source_fields()).intersection(vals):
            raise AccessError(_('Original uploaded evidence is immutable. Upload a corrected source as a new batch.'))
        return super().write(vals)

    @api.model
    def _create_source(self, batch, raw):
        batch._check_intake_access()
        evidence = super(SourceEvidence, clean_defaults(self)).create({
            'revision_id': batch.revision_id.id, 'evidence_type': 'supplier_price_file',
            'name': batch.original_filename, 'filename': batch.original_filename,
            'import_batch_id': batch.id, 'sha256_digest': batch.sha256_digest,
            'file_size': batch.file_size, 'detected_format': batch.detected_format,
            'mimetype': batch.mimetype, 'uploaded_by': self.env.uid,
            'uploaded_at': batch.uploaded_at,
        })
        attachment = self.env['ir.attachment']._create_supplier_source(evidence, raw)
        super(SourceEvidence, evidence).write({'attachment_id': attachment.id})
        return evidence


class SourceAttachment(models.Model):
    _inherit = 'ir.attachment'
    vpr_source_evidence_id = fields.Many2one(EVIDENCE, ondelete='restrict', copy=False, index=True)

    def _protected_sources(self):
        # Metadata-only elevation identifies protected files even for ID attacks.
        # Content and business access always use the requesting user's environment.
        return self.sudo().filtered('vpr_source_evidence_id').with_env(self.env)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            defaults = self.default_get(['vpr_source_evidence_id', 'res_model'])
            if vals.get('vpr_source_evidence_id', defaults.get('vpr_source_evidence_id')) or vals.get('res_model', defaults.get('res_model')) in (EVIDENCE, BATCH, ROW, ATTEMPT):
                raise AccessError(_('Supplier source attachments are created only through authorized intake.'))
        return super().create(vals_list)

    def write(self, vals):
        if self._protected_sources() or vals.get('vpr_source_evidence_id') or vals.get('res_model') in (EVIDENCE, BATCH, ROW, ATTEMPT):
            raise AccessError(_('Original supplier attachments cannot be replaced, shared, reassigned or given access tokens.'))
        return super().write(vals)

    def unlink(self):
        if self._protected_sources():
            raise AccessError(_('Original supplier attachments are retained.'))
        return super().unlink()

    def copy_data(self, default=None):
        if self._protected_sources():
            raise AccessError(_('Original supplier attachments cannot be copied to another security scope.'))
        return super().copy_data(default)

    def read(self, fields=None, load='_classic_read'):
        self._protected_sources().check_access('read')
        return super().read(fields=fields, load=load)

    def export_data(self, fields_to_export):
        self._protected_sources().check_access('read')
        return super().export_data(fields_to_export)

    def _can_return_content(self, field_name=None, access_token=None):
        if self._protected_sources():
            self.sudo(False).check_access('read')
            if access_token:
                raise AccessError(_('Supplier source files do not support public access tokens.'))
        return super()._can_return_content(field_name, access_token)

    def _to_http_stream(self):
        if self._protected_sources():
            self.sudo(False).check_access('read')
        return super()._to_http_stream()

    @api.model
    def _create_supplier_source(self, evidence, raw):
        evidence.revision_id._check_draft_edit_access()
        return super(SourceAttachment, clean_defaults(self)).create({'name': evidence.filename, 'raw': raw,
            'mimetype': evidence.mimetype, 'type': 'binary', 'res_model': EVIDENCE,
            'res_id': evidence.id, 'company_id': evidence.company_id.id,
            'public': False, 'access_token': False, 'vpr_source_evidence_id': evidence.id})
