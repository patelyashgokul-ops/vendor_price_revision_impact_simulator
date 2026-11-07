import io
import zipfile
import zlib
from datetime import datetime
from unittest.mock import patch

from openpyxl import Workbook

from odoo.tests import TransactionCase, tagged

from ..models import import_parser as parser


def workbook_bytes(rows=None, sheets=None):
    book = Workbook()
    first = book.active
    first.title = 'PRICES'
    for row in rows or [['Code', 'Price'], ['000123', 115]]:
        first.append(row)
    for name, content in (sheets or {}).items():
        sheet = book.create_sheet(name)
        for row in content:
            sheet.append(row)
    stream = io.BytesIO()
    book.save(stream)
    book.close()
    return stream.getvalue()


@tagged('post_install', '-at_install')
class TestImportParser(TransactionCase):
    def _extract(self, raw, name='prices.csv', **options):
        return parser.extract(raw, name, options, dict(parser.DEFAULT_LIMITS))

    def test_csv_utf8_bom_unicode_leading_zero_and_quoted_delimiter(self):
        raw = '\ufeffCode,Description,Price\r\n000123,"LED, उजाला",115\r\n'.encode()
        result = self._extract(raw)
        self.assertEqual([c['value'] for c in result['rows'][0]['raw_cells']], ['000123', 'LED, उजाला', '115'])
        self.assertEqual(result['header_row_number'], 1)
        self.assertEqual(result['rows'][0]['source_row'], 2)
        self.assertEqual(result['total_logical_rows'], 2)

    def test_csv_delimiters_encodings_and_no_lossy_fallback(self):
        for delimiter, char in parser.DELIMITERS.items():
            with self.subTest(delimiter=delimiter):
                self.assertEqual(self._extract(f'Code{char}Price\n000045{char}0\n'.encode(), csv_delimiter=delimiter)['rows'][0]['raw_cells'][0]['value'], '000045')
        self.assertEqual(self._extract('Code,Desc\n1,café\n'.encode('cp1252'), csv_encoding='cp1252')['rows'][0]['raw_cells'][1]['value'], 'café')
        self.assertEqual(self._extract('Code,Price\n1,15\n'.encode('utf-16'), csv_encoding='utf-16')['rows'][0]['raw_cells'][1]['value'], '15')
        with self.assertRaises(parser.IntakeError):
            self._extract(b'Code,Desc\n1,\xff\n')
        for choice in ('auto', 'ambiguous'):
            with self.assertRaises(parser.IntakeError):
                self._extract(b'Code,Price\n1,2\n', csv_delimiter=choice)

    def test_csv_multiline_logical_and_physical_positions(self):
        result = self._extract(b'Code,Desc\n001,"line one\nline two"\n002,ok\n')
        first, second = result['rows']
        self.assertEqual((first['source_row'], first['physical_start'], first['physical_end']), (2, 2, 3))
        self.assertEqual((second['source_row'], second['physical_start'], second['physical_end']), (3, 4, 4))
        self.assertEqual(first['raw_cells'][1]['value'], 'line one\nline two')

    def test_csv_blanks_headers_duplicates_and_formula_text(self):
        result = self._extract(b'\nA,A,C\n\n000123,,=100*1.15\n002,0,@untrusted\n\n')
        self.assertEqual([c['value'] for c in result['headers']], ['A', 'A', 'C'])
        self.assertEqual(result['skipped_blank_rows'], 3)
        self.assertEqual(result['header_row_number'], 2)
        self.assertEqual(result['rows'][0]['raw_cells'][1]['value'], '')
        self.assertEqual(result['rows'][1]['raw_cells'][1]['value'], '0')
        self.assertEqual(result['rows'][0]['formula_columns'], [3])
        self.assertEqual(result['rows'][0]['status'], 'review')

    def test_csv_empty_header_only_malformed_and_bounded_fields(self):
        for raw in (b'', b'  \r\n', b'Code,Price\n', b'Code,Price\n1,"unterminated'):
            with self.subTest(source_length=len(raw)), self.assertRaises(parser.IntakeError):
                self._extract(raw)
        for limits, raw in [(dict(max_cell_chars=3), b'Code,Price\n00001,15\n'),
                            (dict(max_columns=1), b'A,B\n1,2\n'),
                            (dict(max_rows=1), b'A\n1\n2\n')]:
            with self.assertRaises(parser.IntakeError):
                parser.extract(raw, 'p.csv', {}, dict(parser.DEFAULT_LIMITS, **limits))
        for header in (-1, 101):
            with self.assertRaises(parser.IntakeError):
                self._extract(b'A\n1\n', header_row_number=header)
        result = self._extract(b'Instructions\nCode,Price\n1,15\n', header_row_number=2)
        self.assertEqual(result['preamble_rows'], 1)
        self.assertEqual(result['rows'][0]['source_row'], 3)

    def test_format_inspection_and_filename_safety(self):
        self.assertEqual(parser.safe_filename('../../private\\prices.csv'), 'prices.csv')
        for name, raw in [('p.xls', b'123'), ('p.xlsm', workbook_bytes()), ('p.pdf', b'%PDF'),
                          ('p.csv', b'MZprogram'), ('p.csv', b'%PDF-1'), ('p.csv', b'\x00binary'),
                          ('p.csv', b'<html>not a price file'), ('p.xlsx', b'not zip')]:
            with self.subTest(name=name), self.assertRaises(parser.IntakeError):
                parser.inspect_source(raw, name, parser.DEFAULT_LIMITS)

    def test_xlsx_cells_types_formulas_dates_and_blank_zero(self):
        raw = workbook_bytes([['Code', 'Price', 'Date', 'Formula', 'Empty'],
            ['000045', 0, datetime(2026, 11, 1), '=100*1.15', None]])
        result = self._extract(raw, 'p.xlsx')
        row = result['rows'][0]
        self.assertEqual(result['worksheet_name'], 'PRICES')
        self.assertEqual(row['source_row'], 2)
        self.assertEqual(row['raw_cells'][0], {'value': '000045', 'type': 'text'})
        self.assertEqual(row['raw_cells'][1], {'value': 0, 'type': 'number'})
        self.assertEqual(row['raw_cells'][2]['type'], 'date')
        self.assertEqual(row['raw_cells'][3], {'value': '=100*1.15', 'type': 'formula'})
        self.assertEqual(row['raw_cells'][4], {'value': None, 'type': 'blank'})
        self.assertEqual(row['formula_columns'], [4])

    def test_xlsx_explicit_sheets_missing_hidden_and_empty(self):
        raw = workbook_bytes(sheets={'INSTRUCTIONS': [['Instructions'], ['Do not import']]})
        for sheet in ('', 'missing'):
            with self.assertRaises(parser.IntakeError):
                self._extract(raw, 'p.xlsx', worksheet_name=sheet)
        self.assertEqual(len(self._extract(raw, 'p.xlsx', worksheet_name='PRICES')['rows']), 1)
        empty = workbook_bytes([['Header']])
        with self.assertRaises(parser.IntakeError):
            self._extract(empty, 'p.xlsx')
        book = Workbook()
        book.active.title = 'Visible'
        hidden = book.create_sheet('Hidden')
        hidden.sheet_state = 'hidden'
        stream = io.BytesIO()
        book.save(stream)
        book.close()
        with self.assertRaises(parser.IntakeError):
            self._extract(stream.getvalue(), 'p.xlsx', worksheet_name='Hidden')

    def test_xlsx_archive_limits_xml_entities_external_relationships(self):
        original = workbook_bytes()
        for limit in ({'max_members': 1}, {'uncompressed_mib': 0}, {'max_ratio': 1}, {'max_columns': 1}):
            with self.assertRaises(parser.IntakeError):
                parser.inspect_source(original, 'p.xlsx', dict(parser.DEFAULT_LIMITS, **limit))
        def modified(name, content):
            stream = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as target:
                for member in source.infolist():
                    target.writestr(member.filename, content if member.filename == name else source.read(member))
            return stream.getvalue()
        attacks = [modified('xl/workbook.xml', b'<!DOCTYPE w [<!ENTITY x "secret">]><w>&x;</w>'),
            modified('xl/workbook.xml', '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE w [<!ENTITY x "boom">]><w>&x;</w>'.encode('utf-16')),
            modified('xl/_rels/workbook.xml.rels', b'<Relationships><Relationship TargetMode="External" Target="https://example.invalid"/></Relationships>'),
            modified('xl/worksheets/sheet1.xml', b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1048576"><c r="A1048576"/></row></sheetData></worksheet>')]
        for name in ('xl/vbaProject.bin', '../outside.xml', 'xl/embeddings/payload.bin'):
            stream = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as target:
                for member in source.infolist():
                    target.writestr(member.filename, source.read(member))
                target.writestr(name, b'not executed')
            attacks.append(stream.getvalue())
        for raw in attacks:
            with self.assertRaises(parser.IntakeError):
                parser.inspect_source(raw, 'p.xlsx', parser.DEFAULT_LIMITS)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('random.txt', 'not workbook')
        with self.assertRaises(parser.IntakeError):
            parser.inspect_source(stream.getvalue(), 'p.xlsx', parser.DEFAULT_LIMITS)

    def test_xlsx_resources_closed_and_missing_dependency_explicit(self):
        real_loader = parser.load_workbook
        books = []
        def tracked(*args, **kwargs):
            book = real_loader(*args, **kwargs)
            books.append(book)
            return book
        raw = workbook_bytes()
        with patch.object(parser, 'load_workbook', tracked):
            self._extract(raw, 'p.xlsx')
        self.assertTrue(books)
        self.assertTrue(all(book._archive.fp is None for book in books))
        with patch.object(parser, 'load_workbook', None), self.assertRaises(parser.IntakeError) as caught:
            self._extract(raw, 'p.xlsx')
        self.assertEqual(caught.exception.code, 'parser_unavailable')
        with patch.object(parser.zipfile.ZipFile, 'open', side_effect=zlib.error('private parser context')):
            with self.assertRaises(parser.IntakeError) as caught:
                parser.inspect_source(raw, 'p.xlsx', parser.DEFAULT_LIMITS)
        self.assertEqual(caught.exception.code, 'invalid_xlsx')
        self.assertNotIn('private', str(caught.exception))

    def test_fingerprint_original_bytes_and_bounded_time(self):
        raw = b'Code,Price\r\n000123,115\r\n'
        self.assertEqual(parser.fingerprint(raw), parser.fingerprint(bytes(raw)))
        self.assertNotEqual(parser.fingerprint(raw), parser.fingerprint(raw.replace(b'\r\n', b'\n')))
        self.assertNotEqual(parser.fingerprint(raw), parser.fingerprint(raw.replace(b'115', b'116')))
        with patch.object(parser.time, 'monotonic', return_value=100), self.assertRaises(parser.IntakeError):
            parser.deadline_check(0, parser.DEFAULT_LIMITS)
