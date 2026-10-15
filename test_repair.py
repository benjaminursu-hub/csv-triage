"""Regression tests for the ORDS v0.3 repair-data profile and the rules it relies on."""
import contextlib
import http.client
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from audit import AuditError, audit_csv, compare_reports, main
from server import ThreadingHTTPServer, make_handler

ROOT = Path(__file__).parent
PROFILE = json.loads((ROOT / 'profiles' / 'ords-v0.3.json').read_text(encoding='utf-8'))
HEADER = list(PROFILE['columns'])
BASE = {'id': '1', 'data_provider': 'The Restart Project', 'country': 'GBR', 'partner_product_category': 'Laptop',
        'product_category': 'Laptop', 'product_category_id': '16', 'brand': '', 'year_of_manufacture': '',
        'product_age': '', 'repair_status': 'Fixed', 'repair_barrier_if_end_of_life': '', 'group_identifier': '',
        'event_date': '2025-03-01', 'problem': 'synthetic', 'record_date': ''}
# Seeded record number -> expected rules; see fixtures/README.md.
SEEDED = {4: ['duplicate_key'], 5: ['pattern_mismatch'], 6: ['not_allowed'], 7: ['pair_mismatch'], 8: ['invalid_type'],
          9: ['required'], 10: ['conditional_value'], 11: ['date_order'], 12: ['not_allowed'], 13: ['pattern_mismatch'],
          15: ['date_order'], 16: ['required']}


def fixture(name):
    return (ROOT / 'fixtures' / name).read_text(encoding='utf-8')


def records(*changes):
    """Build a CSV with the ORDS header; each change dict overrides the BASE record."""
    rows = [','.join(HEADER)]
    for change in changes:
        values = {**BASE, **change}
        rows.append(','.join(values[name] for name in HEADER))
    return '\n'.join(rows) + '\n'


def rules(report):
    return report['counts_by_rule']


class RepairFixtureTests(unittest.TestCase):
    def test_seeded_fixture_findings_are_exact(self):
        report = audit_csv(fixture('repair-seeded.csv'), PROFILE)
        found = {}
        for issue in report['issues']:
            found.setdefault(issue['row'], []).append(issue['rule'])
        self.assertEqual(found, SEEDED)
        self.assertEqual(report['counts_by_severity'], {'error': 8, 'warning': 4})
        self.assertEqual(report['keys'][0]['records_incomplete'], 1)

    def test_corrected_fixture_has_fewer_findings_under_same_profile(self):
        before = audit_csv(fixture('repair-seeded.csv'), PROFILE)
        after = audit_csv(fixture('repair-corrected.csv'), PROFILE)
        self.assertEqual(rules(after), {'date_order': 1, 'not_allowed': 1})
        self.assertTrue(after['error_free'])
        self.assertFalse(after['valid'])
        delta = compare_reports(before, after)
        self.assertEqual(delta['issue_delta'], -10)
        self.assertEqual(delta['severity_delta'], {'error': -8, 'warning': -2})

    def test_valid_fixture_matches_expected_report(self):
        expected = json.loads(fixture('repair-valid.expected.json'))
        self.assertEqual(audit_csv(fixture('repair-valid.csv'), PROFILE), expected)
        self.assertTrue(expected['valid'])

    def test_reports_never_contain_free_text_or_unlisted_values(self):
        text = json.dumps(audit_csv(fixture('repair-seeded.csv'), PROFILE), ensure_ascii=False)
        for secret in ('SYNTHETIC-PROBLEM', 'SynthBrand', 'grp-0', 'Example Repair Group', 'Broken', '2025-02-30'):
            self.assertNotIn(secret, text)
        self.assertIn('(unlisted value)', text)


class CompositeKeyTests(unittest.TestCase):
    def test_same_id_in_two_providers_is_accepted(self):
        report = audit_csv(records({}, {'data_provider': 'Repair Café International'}), PROFILE)
        self.assertTrue(report['valid'])
        self.assertEqual(report['keys'][0]['duplicates'], 0)

    def test_repeated_provider_and_id_is_flagged_with_first_record(self):
        report = audit_csv(records({}, {}, {}), PROFILE)
        self.assertEqual(rules(report), {'duplicate_key': 2})
        self.assertEqual({i['message'] for i in report['issues']}, {'Same data_provider+id combination as record 2.'})

    def test_key_uses_trimmed_case_sensitive_values(self):
        self.assertEqual(rules(audit_csv(records({}, {'id': ' 1'}), PROFILE)), {'duplicate_key': 1, 'whitespace': 1})
        schema = {'columns': {'p': {}, 'id': {}}, 'unique_together': [{'columns': ['p', 'id']}]}
        self.assertTrue(audit_csv('p,id\nA,x\nA,X\n', schema)['valid'])

    def test_missing_component_policies(self):
        csv_text = 'p,id\nA,1\n,1\n,1\n'
        skip = audit_csv(csv_text, {'columns': {'p': {}, 'id': {}}, 'unique_together': [{'columns': ['p', 'id'], 'missing': 'skip'}]})
        self.assertTrue(skip['valid'])
        self.assertEqual(skip['keys'][0]['records_incomplete'], 2)
        report = audit_csv(csv_text, {'columns': {'p': {}, 'id': {}}, 'unique_together': [{'columns': ['p', 'id']}]})
        self.assertEqual(rules(report), {'key_incomplete': 2})
        # The profile skips incomplete keys because required already reports the blank.
        self.assertEqual(rules(audit_csv(records({'data_provider': ''}, {'data_provider': ''}), PROFILE)), {'required': 2})

    def test_key_not_checked_when_column_missing(self):
        report = audit_csv('p\nA\nA\n', {'columns': {'p': {}, 'id': {}}, 'unique_together': [{'columns': ['p', 'id']}]})
        self.assertFalse(report['keys'][0]['checked'])
        self.assertEqual(report['issues'][0]['severity'], 'warning')


class RepairRuleTests(unittest.TestCase):
    def test_blank_optional_fields_are_not_findings(self):
        report = audit_csv(records({}), PROFILE)
        self.assertTrue(report['valid'])
        self.assertEqual(report['completeness']['columns']['brand'], {'filled': 0, 'blank': 1, 'placeholder': 0, 'required': False})
        self.assertEqual(report['completeness']['columns']['problem']['filled'], 1)

    def test_missing_optional_column_is_warning_and_required_column_is_error(self):
        header = [h for h in HEADER if h not in {'record_date', 'problem'}]
        report = audit_csv(','.join(header) + '\n' + ','.join(BASE[h] for h in header) + '\n', PROFILE)
        self.assertEqual({i['column']: i['severity'] for i in report['issues']}, {'problem': 'error', 'record_date': 'warning'})
        self.assertFalse(report['error_free'])

    def test_code_lists_accept_codes_and_text(self):
        for change in ({'repair_status': '0'}, {'repair_status': 'End of life', 'repair_barrier_if_end_of_life': '6'},
                       {'repair_status': '3', 'repair_barrier_if_end_of_life': 'Item too worn out'}):
            with self.subTest(change=change):
                self.assertTrue(audit_csv(records(change), PROFILE)['valid'])

    def test_invalid_code_list_values(self):
        cases = [({'repair_status': 'fixed'}, 'error'), ({'product_category': 'Smartphone', 'product_category_id': ''}, 'error'),
                 ({'repair_status': 'End of life', 'repair_barrier_if_end_of_life': 'Too worn out'}, 'error'),
                 ({'data_provider': 'New Partner'}, 'warning')]
        for change, severity in cases:
            with self.subTest(change=change):
                report = audit_csv(records(change), PROFILE)
                self.assertEqual(rules(report), {'not_allowed': 1})
                self.assertEqual(report['issues'][0]['severity'], severity)

    def test_category_id_must_match_category(self):
        self.assertEqual(rules(audit_csv(records({'product_category_id': '19'}), PROFILE)), {'pair_mismatch': 1})
        self.assertTrue(audit_csv(records({'product_category': '', 'product_category_id': '19'}), PROFILE)['valid'])

    def test_barrier_only_expected_for_end_of_life(self):
        report = audit_csv(records({'repair_barrier_if_end_of_life': '1'}), PROFILE)
        self.assertEqual(rules(report), {'conditional_value': 1})
        self.assertEqual(report['warning_count'], 1)
        self.assertTrue(audit_csv(records({'repair_status': 'End of life'}), PROFILE)['valid'])

    def test_event_date_edge_cases(self):
        for value, ok in (('2024-02-29', True), ('2025-02-29', False), ('2025-3-1', False), ('2025-03-01T10:00:00', False),
                          ('20250301', False), ('01/03/2025', False)):
            with self.subTest(value=value):
                self.assertEqual(audit_csv(records({'event_date': value}), PROFILE)['valid'], ok)

    def test_year_and_record_date_order(self):
        cases = [({'year_of_manufacture': '2025'}, {}), ({'year_of_manufacture': '2026'}, {'date_order': 1}),
                 ({'year_of_manufacture': '25'}, {'invalid_type': 1}), ({'record_date': '2025-03-01'}, {}),
                 ({'record_date': '2025-02-28'}, {'date_order': 1}),
                 ({'record_date': '2025-02-28', 'event_date': 'unknown'}, {'invalid_type': 1})]
        for change, expected in cases:
            with self.subTest(change=change):
                self.assertEqual(rules(audit_csv(records(change), PROFILE)), expected)

    def test_product_age_precision(self):
        for value, expected in (('0', {}), ('1.5', {}), ('2.25', {'pattern_mismatch': 1}), ('-1', {'out_of_range': 1, 'pattern_mismatch': 1})):
            with self.subTest(value=value):
                self.assertEqual(rules(audit_csv(records({'product_age': value}), PROFILE)), expected)

    def test_country_shape(self):
        self.assertEqual(rules(audit_csv(records({'country': 'GB'}), PROFILE)), {'pattern_mismatch': 1})

    def test_group_completeness_uses_code_list_labels(self):
        report = audit_csv(records({}, {'id': '2', 'problem': ''}, {'id': '3', 'data_provider': 'Private Group'}), PROFILE)
        groups = report['completeness_by_group']['groups']
        self.assertEqual(set(groups), {'The Restart Project', '(unlisted value)'})
        self.assertEqual(groups['The Restart Project']['records'], 2)
        self.assertEqual(groups['The Restart Project']['filled']['problem'], 1)
        self.assertNotIn('Private Group', json.dumps(report))


class SchemaCompatibilityTests(unittest.TestCase):
    def test_legacy_schema_hash_and_report_fields_unchanged(self):
        report = audit_csv((ROOT / 'demo.csv').read_text(), json.loads((ROOT / 'demo-schema.json').read_text()))
        self.assertEqual(report['schema_sha256'], 'e845ec8b6ab5fb4a213b755e86b01308053e68876b761fd96f7f51eeea54ee72')
        for key in ('report_version', 'source_sha256', 'columns', 'row_count', 'complete', 'valid', 'issue_count',
                    'affected_rows', 'counts_by_rule', 'issues', 'examples_truncated', 'note'):
            self.assertIn(key, report)
        self.assertEqual(report['report_version'], 1)

    def test_old_reports_without_severity_still_compare(self):
        schema = {'columns': {'n': {'type': 'integer'}}}
        before = audit_csv('n\nbad\n', schema)
        for key in ('counts_by_severity', 'error_count', 'warning_count', 'error_free', 'completeness'):
            before.pop(key)
        result = compare_reports(before, audit_csv('n\n1\n', schema))
        self.assertEqual(result['issue_delta'], -1)
        self.assertNotIn('severity_delta', result)

    def test_invalid_new_rules_are_configuration_errors(self):
        bad = [{'columns': {'a': {'pattern': '('}}},
               {'columns': {'a': {'pattern': 'x' * 201}}},
               {'columns': {'a': {'allowed': []}, 'b': {}}, 'group_by': 'b'},
               {'columns': {'a': {'unlisted': 'warning'}}},
               {'columns': {'a': {'allowed': ['x', 'x']}}},
               {'columns': {'a': {'only_if': {'column': 'missing', 'in': ['x']}}}},
               {'columns': {'a': {'type': 'string', 'not_after': 'b'}, 'b': {'type': 'date'}}},
               {'columns': {'a': {'pairs_with': {'column': 'a', 'map': {'1': 'x'}}}}},
               {'columns': {'a': {}}, 'unique_together': [{'columns': ['a']}]},
               {'columns': {'a': {}, 'b': {}}, 'unique_together': [{'columns': ['a', 'b'], 'missing': 'ignore'}]},
               {'columns': {}, 'profile': {'name': 1}}]
        for schema in bad:
            with self.subTest(schema=schema), self.assertRaises(AuditError):
                audit_csv('a,b\n1,2\n', schema)

    def test_cli_fail_on_error_lets_warnings_pass(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            schema = Path(directory) / 'ords.json'
            schema.write_text(json.dumps(PROFILE), encoding='utf-8')
            corrected = str(ROOT / 'fixtures' / 'repair-corrected.csv')
            self.assertEqual(main([corrected, '--schema', str(schema)]), 1)
            self.assertEqual(main([corrected, '--schema', str(schema), '--fail-on', 'error']), 0)
            self.assertEqual(main([str(ROOT / 'fixtures' / 'repair-seeded.csv'), '--schema', str(schema), '--fail-on', 'error']), 1)
            self.assertEqual(main([str(ROOT / 'fixtures' / 'repair-valid.csv'), '--schema', str(schema)]), 0)


class RepairAPITests(unittest.TestCase):
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
        result = response.status, response.read()
        client.close()
        return result

    def audit(self, demo):
        status, body = self.request('POST', '/api/audit', json.dumps({'csv': demo['csv'], 'schema': demo['schema']}),
                                    {'Content-Type': 'application/json'})
        self.assertEqual(status, 200)
        return json.loads(body)

    def test_repair_demo_through_http_and_sqlite(self):
        status, body = self.request(path='/api/demo?preset=repair')
        self.assertEqual(status, 200)
        seeded = self.audit(json.loads(body))
        self.assertEqual(seeded['counts_by_severity'], {'error': 8, 'warning': 4})
        corrected = self.audit(json.loads(self.request(path='/api/demo?preset=repair-corrected')[1]))
        self.assertEqual(corrected['issue_count'], 2)
        self.assertEqual(corrected['schema_sha256'], seeded['schema_sha256'])
        with contextlib.closing(sqlite3.connect(self.database)) as connection:
            stored = ' '.join(row[0] for row in connection.execute('SELECT report FROM audits'))
        for secret in ('SYNTHETIC-PROBLEM', 'SynthBrand', 'Example Repair Group'):
            self.assertNotIn(secret, stored)

    def test_presets_are_an_allowlist(self):
        for preset in ('missing', '../server.py', 'fixtures/repair-seeded.csv'):
            self.assertEqual(self.request(path=f'/api/demo?preset={preset}')[0], 404)
        self.assertEqual(json.loads(self.request(path='/api/demo')[1])['preset'], 'sensor')
        status, body = self.request(path='/api/profiles/ords-v0.3')
        self.assertEqual((status, json.loads(body)), (200, PROFILE))


if __name__ == '__main__':
    unittest.main()
