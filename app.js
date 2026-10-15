'use strict';
const $ = id => document.getElementById(id);
let report = null;
let previous = null; // last complete report, for a same-rules comparison
const status = message => { $('status').textContent = message; };
const percent = (part, whole) => whole ? `${Math.round(100 * part / whole)}%` : '—';

$('demo').addEventListener('click', async () => {
  try {
    const response = await fetch(`/api/demo?preset=${encodeURIComponent($('preset').value)}`);
    if (!response.ok) throw new Error('Example could not load.');
    const demo = await response.json();
    $('csv').value = demo.csv;
    $('schema').value = JSON.stringify(demo.schema, null, 2);
    status(`${demo.description} Run the audit to see the findings.`);
  } catch (error) { status(error.message); }
});
$('profile').addEventListener('click', async () => {
  try {
    const response = await fetch('/api/profiles/ords-v0.3');
    if (!response.ok) throw new Error('Profile could not load.');
    $('schema').value = JSON.stringify(await response.json(), null, 2);
    status('ORDS v0.3 rules loaded. Your CSV content was not changed.');
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
  if (report && report.complete) previous = report;
  report = null;
  status('Checking records…');
  try {
    const schema = JSON.parse($('schema').value);
    const response = await fetch('/api/audit', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({csv: $('csv').value, schema})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Audit failed.');
    report = result;
    renderSummary();
    $('filter').replaceChildren(new Option('All rules', ''));
    Object.keys(report.counts_by_rule).forEach(rule => $('filter').add(new Option(`${rule} (${report.counts_by_rule[rule]})`, rule)));
    $('severity').value = '';
    $('provenance').textContent = `Report version: ${report.report_version}\nDecoded content SHA-256: ${report.source_sha256}\nSchema SHA-256: ${report.schema_sha256}`;
    renderIssues();
    renderCompleteness();
    renderGroups();
    $('results').hidden = false;
    $('results-title').focus();
    status(`Audit finished: ${report.error_count} errors and ${report.warning_count} warnings.`);
  } catch (error) { status(error.message); }
  finally { $('run').disabled = false; }
});

function renderSummary() {
  $('profile-name').textContent = report.profile ? `Rules: ${report.profile.name} (${report.profile.version}). Partial ORDS checks, not a conformance certificate.` : '';
  $('rows').textContent = report.row_count.toLocaleString();
  $('findings').textContent = report.issue_count.toLocaleString();
  $('errors').textContent = report.error_count.toLocaleString();
  $('warnings').textContent = report.warning_count.toLocaleString();
  $('affected').textContent = report.affected_rows.toLocaleString();
  $('verdict').textContent = !report.complete ? 'Header problems prevented record validation. Fix the header and rerun.'
    : report.valid ? 'No findings under these rules. Review whether your rules cover the intended use.'
    : report.error_free ? 'No errors. Review the warnings: they are quality observations, not rule violations.'
    : 'Errors break the configured rules. Correct the source if appropriate and rerun.';
  $('limit').textContent = report.examples_truncated ? 'Only the first 500 findings are shown. Counts cover the complete audit.' : 'All finding examples are shown.';
  const comparable = previous && report.complete && previous.schema_sha256 === report.schema_sha256 && previous.source_sha256 !== report.source_sha256;
  $('comparison').textContent = comparable
    ? `Compared with the previous run under the same rules: ${signed(report.issue_count - previous.issue_count)} findings (${signed(report.error_count - previous.error_count)} errors, ${signed(report.warning_count - previous.warning_count)} warnings). Counts only; this does not prove which records were fixed.`
    : '';
  $('keys').textContent = (report.keys || []).map(key => key.checked
    ? `Key ${key.columns.join(' + ')}: ${key.records_keyed} records keyed, ${key.duplicates} repeated, ${key.records_incomplete} with a blank component (${key.missing === 'skip' ? 'not keyed; blanks are reported by required' : 'reported'}).`
    : `Key ${key.columns.join(' + ')}: not checked because a column is missing.`).join(' ');
}
const signed = n => (n > 0 ? `+${n}` : String(n));

function cell(row, value, className) {
  const td = document.createElement('td');
  td.textContent = String(value); // CSV-controlled content must never become HTML.
  if (className) td.className = className;
  row.append(td);
}
function renderIssues() {
  $('issue-list').replaceChildren();
  for (const issue of report.issues) {
    if ($('filter').value && issue.rule !== $('filter').value) continue;
    if ($('severity').value && issue.severity !== $('severity').value) continue;
    const row = document.createElement('tr');
    cell(row, issue.row);
    cell(row, issue.severity, `sev-${issue.severity}`);
    cell(row, issue.column || '—');
    cell(row, issue.rule);
    cell(row, issue.message);
    $('issue-list').append(row);
  }
}
function renderCompleteness() {
  $('completeness-list').replaceChildren();
  const data = report.completeness;
  if (!data) return;
  for (const [name, c] of Object.entries(data.columns)) {
    const row = document.createElement('tr');
    cell(row, name);
    cell(row, c.required ? 'Yes' : 'No');
    cell(row, c.filled.toLocaleString());
    cell(row, c.blank.toLocaleString());
    cell(row, c.placeholder.toLocaleString());
    cell(row, percent(c.filled, data.records_considered));
    $('completeness-list').append(row);
  }
}
function renderGroups() {
  const data = report.completeness_by_group;
  $('group-section').hidden = !data;
  if (!data) return;
  $('group-column').textContent = data.column;
  const keep = $('group-field').value;
  $('group-field').replaceChildren(...report.columns.map(name => new Option(name, name)));
  $('group-field').value = report.columns.includes(keep) ? keep : (report.columns.includes('problem') ? 'problem' : report.columns[0]);
  renderGroupRows();
}
function renderGroupRows() {
  const data = report.completeness_by_group;
  const field = $('group-field').value;
  $('group-list').replaceChildren();
  for (const [label, group] of Object.entries(data.groups)) {
    const row = document.createElement('tr');
    cell(row, label);
    cell(row, group.records.toLocaleString());
    cell(row, (group.filled[field] || 0).toLocaleString());
    cell(row, percent(group.filled[field] || 0, group.records));
    $('group-list').append(row);
  }
}
$('filter').addEventListener('change', () => { if (report) renderIssues(); });
$('severity').addEventListener('change', () => { if (report) renderIssues(); });
$('group-field').addEventListener('change', () => { if (report && report.completeness_by_group) renderGroupRows(); });
$('download').addEventListener('click', () => {
  if (!report) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], {type: 'application/json'}));
  const link = document.createElement('a');
  link.href = url; link.download = 'csv-triage-report.json'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
