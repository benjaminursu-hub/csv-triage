"""Regression tests for data semantics, boundary handling, CLI and real HTTP API."""
import contextlib
import http.client
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from audit import AuditError, audit_csv, compare_reports, main
from server import ThreadingHTTPServer, make_handler


class AuditTests(unittest.TestCase):
    def test_demo_detects_all_seeded_defects(self):
        root = Path(__file__).parent
        report = audit_csv((root / 'demo.csv').read_text(), json.loads((root / 'demo-schema.json').read_text()))
        self.assertEqual(report['row_count'], 7)
        self.assertEqual(report['counts_by_rule'], {'duplicate_value': 1, 'invalid_type': 3, 'out_of_range': 1, 'required': 1, 'sentinel': 1, 'whitespace': 1})
        self.assertEqual(report['issue_count'], 8)

    def test_zero_is_not_missing(self):
        self.assertTrue(audit_csv('n\n0\n', {'columns': {'n': {'type': 'integer', 'required': True}}})['valid'])

    def test_negative_is_not_automatically_a_sentinel(self):
        self.assertTrue(audit_csv('n\n-9999\n', {'columns': {'n': {'type': 'number'}}})['valid'])

    def test_whitespace_and_unicode(self):
        report = audit_csv('name\n București \n')
        self.assertEqual(report['counts_by_rule'], {'whitespace': 1})
        self.assertNotIn('București', json.dumps(report))

    def test_bom_is_accepted(self):
        self.assertEqual(audit_csv('\ufeffid\n1\n')['columns'], ['id'])

    def test_semicolon_dialect(self):
        self.assertEqual(audit_csv('id;name\n1;test\n', {'delimiter': ';'})['columns'], ['id', 'name'])

    def test_quoted_multiline_is_one_record(self):
        self.assertEqual(audit_csv('id,name\n1,"two\nlines"\n')['row_count'], 1)

    def test_ambiguous_header_stops_validation(self):
        report = audit_csv('id,id\n1,2\n')
        self.assertFalse(report['complete'])
        self.assertEqual(report['counts_by_rule'], {'duplicate_header': 1})

    def test_blank_header(self):
        self.assertEqual(audit_csv('id,\n1,x\n')['counts_by_rule'], {'blank_header': 1})

    def test_missing_schema_column(self):
        self.assertEqual(audit_csv('id\n1\n', {'columns': {'absent': {'required': True}}})['counts_by_rule'], {'missing_column': 1})

    def test_row_width_and_blank_record(self):
        report = audit_csv('a,b\n1\n\n2,3,4\n')
        self.assertEqual(report['counts_by_rule'], {'blank_row': 1, 'row_width': 2})

    def test_nonfinite_numbers_rejected(self):
        report = audit_csv('n\nNaN\ninf\n-inf\n', {'columns': {'n': {'type': 'number'}}})
        self.assertEqual(report['issue_count'], 3)

    def test_integer_rejects_fraction(self):
        self.assertEqual(audit_csv('n\n1.5\n', {'columns': {'n': {'type': 'integer'}}})['issue_count'], 1)

    def test_date_requires_iso_calendar_date(self):
        report = audit_csv('d\n2026-02-30\n20260101\n2026-01-01T00:00:00\n2026-01-01\n', {'columns': {'d': {'type': 'date'}}})
        self.assertEqual(report['issue_count'], 3)

    def test_bounds_are_inclusive(self):
        self.assertTrue(audit_csv('n\n-90\n90\n', {'columns': {'n': {'type': 'number', 'min': -90, 'max': 90}}})['valid'])

    def test_examples_capped_but_counts_complete(self):
        report = audit_csv('n\n' + 'bad\n' * 600, {'columns': {'n': {'type': 'integer'}}})
        self.assertEqual(report['issue_count'], 600)
        self.assertEqual(len(report['issues']), 500)
        self.assertTrue(report['examples_truncated'])

    def test_invalid_input_is_an_error_not_a_clean_report(self):
        for text in ('', '   \n', 'id\n"unclosed', 'id\n\x00'):
            with self.subTest(text=text), self.assertRaises(AuditError):
                audit_csv(text)

    def test_invalid_schemas(self):
        for schema in ([], {'column': {}}, {'columns': []}, {'delimiter': ';;'}, {'columns': {'id': {'type': 'magic'}}}, {'columns': {'n': {'required': 'yes'}}}, {'columns': {'n': {'type': 'number', 'min': 2, 'max': 1}}}, {'columns': {'n': {'type': 'number', 'min': float('nan')}}}):
            with self.subTest(schema=schema), self.assertRaises(AuditError):
                audit_csv('id\n1\n', schema)

    def test_report_deterministic(self):
        self.assertEqual(audit_csv('n\n1\n'), audit_csv('n\n1\n'))

    def test_extreme_bound_is_rejected_cleanly(self):
        with self.assertRaises(AuditError):
            audit_csv('n\n1\n', {'columns': {'n': {'type': 'number', 'min': 10 ** 400}}})

    def test_size_and_record_limits(self):
        with patch('audit.MAX_BYTES', 4), self.assertRaises(AuditError):
            audit_csv('n\n123\n')
        with patch('audit.MAX_ROWS', 1), self.assertRaises(AuditError):
            audit_csv('n\n1\n2\n')

    def test_comparison_and_schema_guard(self):
        schema = {'columns': {'n': {'type': 'integer'}}}
        before, after = audit_csv('n\nbad\n', schema), audit_csv('n\n1\n', schema)
        self.assertEqual(compare_reports(before, after)['issue_delta'], -1)
        with self.assertRaises(AuditError):
            compare_reports(before, audit_csv('n\n1\n'))

    def test_incomplete_reports_not_comparable(self):
        with self.assertRaises(AuditError):
            compare_reports(audit_csv('n,n\n1,2\n'), audit_csv('n\n1\n'))

    def test_cli_exit_codes_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            source = Path(directory) / 'input.csv'
            source.write_text('id\n1\n')
            self.assertEqual(main([str(source)]), 0)
            self.assertEqual(main([str(source), '--output', str(source)]), 2)
            self.assertEqual(source.read_text(), 'id\n1\n')
            source.write_text('id,id\n1,2\n')
            self.assertEqual(main([str(source)]), 1)
            self.assertEqual(main([str(source) + '.missing']), 2)


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / 'history.sqlite'
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.database))
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()
        self.temp.cleanup()

    def request(self, method='GET', path='/api/health', body=None, headers=None):
        client = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        client.request(method, path, body=body, headers=headers or {})
        response = client.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        client.close()
        return result

    def test_health_and_static_allowlist(self):
        self.assertEqual(self.request()[0], 200)
        self.assertEqual(self.request(path='/audit.py')[0], 404)
        status, headers, body = self.request(path='/')
        self.assertEqual(status, 200)
        self.assertIn('Content-Security-Policy', headers)
        self.assertIn(b'CSV Triage', body)

    def test_audit_and_sqlite_store_no_raw_cells(self):
        status, _, body = self.request('POST', '/api/audit', json.dumps({'csv': 'name\n secret value \n'}), {'Content-Type': 'application/json'})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['run_id'], 1)
        with contextlib.closing(sqlite3.connect(self.database)) as connection:
            stored = connection.execute('SELECT report FROM audits').fetchone()[0]
        self.assertNotIn('secret value', stored)

    def test_invalid_json_and_schema(self):
        for body in ('not json', '[]', '{"csv":"id\\n1","schema":{"columns":[]}}'):
            self.assertEqual(self.request('POST', '/api/audit', body, {'Content-Type': 'application/json'})[0], 400)

    def test_cross_origin_and_rebinding_rejected(self):
        self.assertEqual(self.request(headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.request('POST', '/api/audit', '{}', {'Content-Type': 'application/json', 'Origin': 'https://evil.example'})[0], 403)

    def test_content_type_and_request_limit(self):
        self.assertEqual(self.request('POST', '/api/audit', '{}')[0], 415)
        self.assertEqual(self.request('POST', '/api/audit', '{}', {'Content-Type': 'application/json', 'Content-Length': '6000000'})[0], 413)

    def test_demo_is_synthetic_and_reproducible(self):
        status, _, body = self.request(path='/api/demo')
        demo = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(audit_csv(demo['csv'], demo['schema'])['issue_count'], 8)


if __name__ == '__main__':
    unittest.main()
