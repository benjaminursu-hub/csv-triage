'use strict';
const $ = id => document.getElementById(id);
let report = null;
const status = message => { $('status').textContent = message; };
$('demo').addEventListener('click', async () => {
  try {
    const response = await fetch('/api/demo');
    if (!response.ok) throw new Error('Demo could not load.');
    const demo = await response.json();
    $('csv').value = demo.csv;
    $('schema').value = JSON.stringify(demo.schema, null, 2);
    status('Synthetic sensor data loaded. Run the audit to find seeded defects.');
  } catch (error) { status(error.message); }
});
$('file').addEventListener('change', async event => {
  const file = event.target.files[0];
  if (!file) return;
  if (file.size > 5000000) { status('File exceeds the 5 MB limit.'); return; }
  try {
    const bytes = await file.arrayBuffer();
    $('csv').value = new TextDecoder('utf-8', {fatal: true}).decode(bytes);
    status('File loaded locally. Review rules before auditing.');
  } catch (_) { status('Could not decode file as UTF-8. Convert it before auditing.'); }
});
$('audit-form').addEventListener('submit', async event => {
  event.preventDefault();
  $('run').disabled = true;
  $('results').hidden = true;
  report = null;
  status('Checking records…');
  try {
    const schema = JSON.parse($('schema').value);
    const response = await fetch('/api/audit', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({csv: $('csv').value, schema})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Audit failed.');
    report = result;
    $('rows').textContent = report.row_count.toLocaleString();
    $('findings').textContent = report.issue_count.toLocaleString();
    $('affected').textContent = report.affected_rows.toLocaleString();
    $('verdict').textContent = !report.complete ? 'Header problems prevented record validation. Fix the header and rerun.' : report.valid ? 'No findings under these rules. Review whether your rules cover the intended use.' : 'Review the findings below, correct the source if appropriate, and rerun.';
    $('limit').textContent = report.examples_truncated ? 'Only the first 500 findings are shown. Counts cover the complete audit.' : 'All finding examples are shown.';
    $('filter').replaceChildren(new Option('All rules', ''));
    Object.keys(report.counts_by_rule).forEach(rule => $('filter').add(new Option(`${rule} (${report.counts_by_rule[rule]})`, rule)));
    $('provenance').textContent = `Report version: ${report.report_version}\nDecoded content SHA-256: ${report.source_sha256}\nSchema SHA-256: ${report.schema_sha256}`;
    renderIssues();
    $('results').hidden = false;
    $('results-title').focus();
    status(`Audit finished: ${report.issue_count} findings.`);
  } catch (error) { status(error.message); }
  finally { $('run').disabled = false; }
});
function renderIssues() {
  $('issue-list').replaceChildren();
  for (const issue of report.issues) {
    if ($('filter').value && issue.rule !== $('filter').value) continue;
    const row = document.createElement('tr');
    for (const value of [issue.row, issue.column || '—', issue.rule, issue.message]) {
      const cell = document.createElement('td');
      cell.textContent = String(value); // CSV-controlled content must never become HTML.
      row.append(cell);
    }
    $('issue-list').append(row);
  }
}
$('filter').addEventListener('change', () => { if (report) renderIssues(); });
$('download').addEventListener('click', () => {
  if (!report) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], {type: 'application/json'}));
  const link = document.createElement('a');
  link.href = url; link.download = 'csv-triage-report.json'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
