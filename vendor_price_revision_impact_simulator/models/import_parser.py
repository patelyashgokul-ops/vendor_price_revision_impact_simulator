"""Bounded source extraction only. Values here are untrusted, unmapped data."""
import csv
import hashlib
import io
import json
import math
import re
import time
import zipfile
import zlib
from datetime import date, datetime, time as datetime_time
from pathlib import PurePosixPath

from lxml import etree

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None

DEFAULT_LIMITS = dict(upload_mib=10, max_rows=10000, max_columns=100,
    max_cell_chars=16384, uncompressed_mib=64, max_members=256,
    max_ratio=200, max_seconds=20)
ENCODINGS = ('utf-8-sig', 'cp1252', 'utf-16')
DELIMITERS = {'comma': ',', 'semicolon': ';', 'tab': '\t'}
SHEET_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'


class IntakeError(Exception):
    """Only controlled codes/messages may be shown to users or retained in audit."""
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def fail(code, message):
    raise IntakeError(code, message)


def fingerprint(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_filename(name):
    name = str(name or '').replace('\\', '/').split('/')[-1]
    name = ''.join(c for c in name if ord(c) >= 32 and ord(c) != 127).strip()
    if not name or len(name) > 200:
        fail('filename', 'Supply a filename of at most 200 characters.')
    return name


def deadline_check(started, limits):
    if time.monotonic() - started > limits['max_seconds']:
        fail('time_limit', 'Extraction exceeded the configured processing time budget.')


def inspect_source(raw, filename, limits):
    if not raw or len(raw) > limits['upload_mib'] * 1024 * 1024:
        fail('upload_size', 'The source file is empty or exceeds the configured upload limit.')
    extension = PurePosixPath(safe_filename(filename)).suffix.lower()
    if extension == '.csv':
        if raw.startswith((b'PK', b'MZ', b'%PDF', b'\xd0\xcf\x11\xe0')):
            fail('format', 'The file content is not a supported CSV text source.')
        # UTF-16 is supported only with an explicit BOM and encoding selection.
        sample = raw[:8192]
        if not raw.startswith((b'\xff\xfe', b'\xfe\xff')) and any(c < 9 or 13 < c < 32 for c in sample):
            fail('format', 'CSV contains unsupported binary control bytes.')
        if sample.lstrip().lower().startswith((b'<!doctype html', b'<html', b'<?xml', b'#!')):
            fail('format', 'An HTML, XML or executable script is not a CSV price file.')
        return {'format': 'csv', 'mimetype': 'text/csv', 'sheets': []}
    if extension != '.xlsx':
        fail('format', 'Only CSV and non-macro XLSX files are supported.')
    if load_workbook is None:
        fail('parser_unavailable', 'XLSX extraction requires the openpyxl Python dependency.')
    started = time.monotonic()
    safe_container = io.BytesIO()
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive, zipfile.ZipFile(safe_container, 'w', zipfile.ZIP_DEFLATED) as vetted:
            members = archive.infolist()
            if not members or len(members) > limits['max_members']:
                fail('archive_limit', 'XLSX archive member count exceeds the configured limit.')
            names = [m.filename for m in members]
            if len(set(names)) != len(names):
                fail('archive_structure', 'XLSX contains ambiguous duplicate archive members.')
            required = {'[Content_Types].xml', '_rels/.rels', 'xl/workbook.xml', 'xl/_rels/workbook.xml.rels'}
            if not required.issubset(names) or not any(n.startswith('xl/worksheets/') and n.endswith('.xml') for n in names):
                fail('archive_structure', 'The ZIP does not contain a supported OOXML spreadsheet.')
            if sum(m.file_size for m in members) > limits['uncompressed_mib'] * 1024 * 1024:
                fail('archive_limit', 'XLSX expanded content exceeds the configured limit.')
            for member in members:
                deadline_check(started, limits)
                path = PurePosixPath(member.filename)
                lower = member.filename.lower()
                if path.is_absolute() or '..' in path.parts or '\\' in member.filename or ':' in member.filename:
                    fail('archive_structure', 'XLSX contains an unsafe archive member path.')
                if member.flag_bits & 1 or member.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    fail('archive_structure', 'Encrypted or unsupported compressed XLSX content is not accepted.')
                if member.file_size > max(1, member.compress_size) * limits['max_ratio']:
                    fail('archive_limit', 'XLSX compression ratio exceeds the configured limit.')
                if lower.endswith(('.bin', '.exe')) or '/externallinks/' in lower or '/embeddings/' in lower:
                    fail('archive_structure', 'Macros, embedded programs and external workbook links are unsupported.')
                # Preflight EVERY XML part before openpyxl's stdlib iterparse sees it.
                # No DTD/entity resolution, network access or huge-tree relaxation.
                chunks, expanded = [], 0
                with archive.open(member) as part:
                    while chunk := part.read(65536):
                        expanded += len(chunk)
                        deadline_check(started, limits)
                        if expanded > min(member.file_size, limits['uncompressed_mib'] * 1024 * 1024):
                            fail('archive_limit', 'Expanded archive member exceeds its supported size.')
                        chunks.append(chunk)
                data = b''.join(chunks)
                if len(data) != member.file_size:
                    fail('archive_structure', 'Archive member length does not match its declared size.')
                # openpyxl receives a bounded, rebuilt ZIP directory, never the
                # supplier's unchecked ZIP size metadata. XML bytes stay intact;
                # the ORIGINAL upload is separately retained unchanged as evidence.
                vetted.writestr(member.filename, data)
                if not lower.endswith(('.xml', '.rels')):
                    continue
                tree = etree.parse(io.BytesIO(data), etree.XMLParser(
                    resolve_entities=False, load_dtd=False, no_network=True, huge_tree=False))
                if tree.docinfo.doctype:
                    fail('unsafe_xml', 'DTD and entity declarations are not accepted in XLSX files.')
                for node_index, element in enumerate(tree.iter()):
                    if node_index % 256 == 0:
                        deadline_check(started, limits)
                    if not isinstance(element.tag, str):
                        continue
                    if element.get('TargetMode', '').lower() == 'external':
                        fail('external_link', 'External workbook relationships are unsupported.')
                    if 'macroenabled' in element.get('ContentType', '').lower():
                        fail('macro', 'Macro-enabled spreadsheets are unsupported.')
                    if element.tag == '{' + SHEET_NS + '}row':
                        if int(element.get('r', '0')) > limits['max_rows'] + 1000:
                            fail('row_limit', 'Worksheet row positions exceed the supported scan limit.')
                    if element.tag == '{' + SHEET_NS + '}c':
                        match = re.fullmatch(r'([A-Z]+)([1-9][0-9]*)', element.get('r', ''))
                        if not match:
                            fail('archive_structure', 'Worksheet contains an unsupported cell reference.')
                        col = 0
                        for char in match[1]:
                            col = col * 26 + ord(char) - 64
                        if col > limits['max_columns']:
                            fail('column_limit', 'Worksheet exceeds the configured column limit.')
                    if element.text and len(element.text) > limits['max_cell_chars']:
                        fail('cell_limit', 'Workbook text exceeds the configured cell limit.')
                if member.filename == '[Content_Types].xml' and not any(
                    e.get('ContentType') == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'
                    for e in tree.getroot()):
                    fail('archive_structure', 'The workbook type is not a supported XLSX spreadsheet.')
                del tree
        safe_bytes = safe_container.getvalue()
        with_workbook = load_workbook(io.BytesIO(safe_bytes), read_only=True, data_only=False, keep_links=False)
        try:
            sheets = [{'name': s.title, 'index': n, 'state': s.sheet_state} for n, s in enumerate(with_workbook.worksheets)]
        finally:
            with_workbook.close()
        deadline_check(started, limits)
        return {'format': 'xlsx', 'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'sheets': sheets, '_safe_workbook': safe_bytes}
    except IntakeError:
        raise
    except (zipfile.BadZipFile, zlib.error, etree.XMLSyntaxError, ValueError, KeyError, TypeError, OSError, RuntimeError, EOFError):
        fail('invalid_xlsx', 'The workbook is corrupt or uses an unsupported structure.')


def extract(raw, filename, options, limits):
    started = time.monotonic()
    info = inspect_source(raw, filename, limits)
    header_number = options.get('header_row_number', 0)
    if not isinstance(header_number, int) or not 0 <= header_number <= 100:
        fail('header', 'Header row must be automatic (0) or a source row from 1 to 100.')
    workbook = None
    if info['format'] == 'csv':
        encoding = options.get('csv_encoding', 'utf-8-sig')
        delimiter = options.get('csv_delimiter', 'comma')
        if encoding not in ENCODINGS or delimiter not in DELIMITERS:
            fail('csv_options', 'Select an explicit supported CSV encoding and delimiter.')
        try:
            text = raw.decode(encoding, errors='strict')
        except UnicodeError:
            fail('encoding', 'The file cannot be decoded using the selected encoding; no lossy fallback is used.')
        if not text.strip():
            fail('empty', 'The source contains no nonblank data.')
        if '\x00' in text:
            fail('encoding', 'Decoded CSV contains NUL bytes; verify its encoding.')
        reader = csv.reader(io.StringIO(text, newline=''), delimiter=DELIMITERS[delimiter], quotechar='"', strict=True)
        def source_rows():
            previous_line = 0
            for ordinal, cells in enumerate(reader, 1):
                yield ordinal, previous_line + 1, reader.line_num, cells, []
                previous_line = reader.line_num
        iterator = source_rows()
        selected_sheet = ''
        sheet_index = -1
    else:
        visible = [s for s in info['sheets'] if s['state'] == 'visible']
        selected_sheet = options.get('worksheet_name') or (visible[0]['name'] if len(info['sheets']) == 1 and visible else '')
        selected = next((s for s in visible if s['name'] == selected_sheet), None)
        if not selected:
            fail('worksheet', 'Choose an existing visible worksheet explicitly when the workbook contains multiple sheets.')
        sheet_index = selected['index']
        workbook = load_workbook(io.BytesIO(info['_safe_workbook']), read_only=True, data_only=False, keep_links=False)
        sheet = workbook[selected_sheet]
        sheet.reset_dimensions()  # Do not trust a supplier's understated dimensions.
        def source_rows():
            for ordinal, cells in enumerate(sheet.iter_rows(), 1):
                values, formulas = [], []
                for index, cell in enumerate(cells):
                    value = cell.value
                    kind = 'blank' if value is None else 'formula' if cell.data_type == 'f' else 'boolean' if isinstance(value, bool) else 'date' if isinstance(value, (date, datetime, datetime_time)) else 'number' if isinstance(value, (int, float)) else 'text'
                    if isinstance(value, float) and not math.isfinite(value):
                        fail('cell_value', 'Workbook contains an unsupported nonfinite numeric value.')
                    if kind == 'date':
                        value = value.isoformat()
                    elif value is not None and not isinstance(value, (str, bool, int, float)):
                        fail('cell_value', 'Workbook contains an unsupported cell value type.')
                    values.append({'value': value, 'type': kind})
                    if kind == 'formula':
                        formulas.append(index + 1)
                # Streaming cells may be padded by formatting; retain explicit blanks
                # through the header width later, without materializing huge ranges.
                while values and values[-1]['value'] is None:
                    values.pop()
                yield ordinal, ordinal, ordinal, values, formulas
        iterator = source_rows()
    rows, headers, skipped, total, preamble, warnings, json_bytes = [], None, 0, 0, 0, 0, 0
    try:
        for ordinal, start_line, end_line, cells, formulas in iterator:
            deadline_check(started, limits)
            total += 1
            if total > limits['max_rows'] + 1000:
                fail('row_limit', 'The source exceeds the supported logical-row scan limit.')
            if len(cells) > limits['max_columns']:
                fail('column_limit', 'The source exceeds the configured column limit.')
            if info['format'] == 'csv':
                cells = [{'value': v, 'type': 'text'} for v in cells]
                formulas = [i + 1 for i, c in enumerate(cells) if c['value'].startswith(('=', '+', '-', '@'))]
            if any(isinstance(c['value'], str) and len(c['value']) > limits['max_cell_chars'] for c in cells):
                fail('cell_limit', 'A cell exceeds the configured character limit.')
            if not any(c['value'] is not None and str(c['value']).strip() for c in cells):
                skipped += 1
                continue
            serialized_size = len(json.dumps(cells, ensure_ascii=False).encode('utf-8'))
            json_bytes += serialized_size
            if serialized_size > 256 * 1024 or json_bytes > 64 * 1024 * 1024:
                fail('staging_limit', 'Raw staging data exceeds the supported row or total JSON size limit.')
            if headers is None:
                if header_number and ordinal < header_number:
                    preamble += 1
                    continue
                if header_number and ordinal != header_number:
                    fail('header', 'The selected header source row is blank or missing.')
                headers = cells
                header_number = ordinal
                warnings += bool(formulas)
                continue
            if len(rows) >= limits['max_rows']:
                fail('row_limit', 'The source exceeds the configured extracted-data row limit.')
            if info['format'] == 'xlsx' and len(cells) < len(headers):
                cells.extend({'value': None, 'type': 'blank'} for _ in range(len(headers) - len(cells)))
                padded_size = len(json.dumps(cells, ensure_ascii=False).encode('utf-8'))
                json_bytes += padded_size - serialized_size
                if padded_size > 256 * 1024 or json_bytes > 64 * 1024 * 1024:
                    fail('staging_limit', 'Raw staging data exceeds the supported row or total JSON size limit.')
            warnings += bool(formulas)
            rows.append(dict(source_row=ordinal, physical_start=start_line, physical_end=end_line,
                raw_cells=cells, column_count=len(cells), formula_columns=formulas,
                status='review' if formulas else 'raw'))
        if not rows:
            fail('no_data', 'No data rows were extracted; the source is empty, header-only or has no usable selected header.')
        return dict(rows=rows, headers=headers, header_row_number=header_number, total_logical_rows=total,
            skipped_blank_rows=skipped, preamble_rows=preamble, warning_count=warnings,
            worksheet_name=selected_sheet, sheet_index=sheet_index, available_sheets=info['sheets'])
    except csv.Error:
        fail('csv_syntax', 'CSV quoting or field length is invalid; verify the selected CSV options.')
    finally:
        if workbook is not None:
            workbook.close()
