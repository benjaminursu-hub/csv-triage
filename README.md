# CSV Triage

**Understand a CSV's problems before importing or analysing it.**

A local data-quality workbench with a Python validation engine, command-line interface, JSON API, browser dashboard and optional SQLite report history. It checks explicit rules and produces reproducible evidence without editing the source data or sending it to external services.

It includes a documented **repair-data profile** for partner records in the [Open Repair Data Standard](https://standard.openrepair.org/standard.html) v0.3: provider-scoped IDs, code lists, date rules, errors versus warnings and completeness per field and provider. See [ORDS.md](ORDS.md) for exactly what it does and does not check.

Status: **working prototype**. The demos are synthetic. No user adoption, official endorsement, ORDS conformance certification or production readiness is claimed.

![Repair-data audit: 8 errors, 4 warnings, completeness by field and provider](demo-screenshot.png)

## Try it

Requires Python 3.11+; **no third-party dependencies or API keys**.

```sh
python server.py
```

Open <http://127.0.0.1:8765>. Choose an example and select **Load example**, then **Run audit**:

- **Repair records, ORDS v0.3 (seeded defects)**: 15 synthetic records, 12 findings (8 errors, 4 warnings), described in [fixtures/README.md](fixtures/README.md).
- **Repair records, ORDS v0.3 (corrected)**: the same records after corrections. Run it straight after the seeded example and the dashboard shows the change under the same rules: −10 findings, 0 errors.
- **Sensor readings (generic CSV)**: the original seven-record demo with eight findings.

Filter by rule or severity, compare field completeness by provider and export the JSON report. **Use ORDS v0.3 rules** applies the profile to your own CSV without changing it.

```sh
python audit.py fixtures/repair-seeded.csv --schema profiles/ords-v0.3.json --output seeded.json
python audit.py fixtures/repair-corrected.csv --schema profiles/ords-v0.3.json --baseline seeded.json
python audit.py fixtures/repair-corrected.csv --schema profiles/ords-v0.3.json --fail-on error
python audit.py demo.csv --schema demo-schema.json
python audit.py input.csv --schema rules.json --output report.json
python audit.py corrected.csv --schema rules.json --baseline report.json
python server.py --db reports.sqlite
python -m unittest -v
```

CLI exit codes: `0` = complete audit with no findings; `1` = findings or ambiguous header; `2` = invalid input, configuration or I/O error. With `--fail-on error`, warnings no longer cause exit `1`. This makes it usable in CI. A zero exit code means only that the configured checks passed.

## What it catches

- Duplicate/blank headers and missing configured columns
- Blank records and inconsistent record widths
- Leading/trailing whitespace, with no automatic trimming of the source
- Missing required values and repeated values in unique columns
- Explicitly configured sentinel values such as `-9999`
- Invalid integers, finite numbers and ISO calendar dates
- Values outside inclusive numeric bounds, including coordinate ranges
- Values outside an exact code list (`allowed`), optionally as warnings for open lists
- Formats such as a 3-letter country shape (`pattern`, full match) and four-digit years (`type: year`)
- Repeated composite keys (`unique_together`), such as provider + record ID
- Cross-field rules: mapped pairs (`pairs_with`), values only expected for some statuses (`only_if`), date/year order (`not_after`, `not_before`)

Every finding has a **severity**. Errors break a configured rule; warnings (whitespace, placeholders, blank records, conditional values, date order, open code lists, missing optional columns) are observations to review. Blank optional values are not findings. They appear in a per-column completeness summary, and per group when `group_by` names a column with a code list.

Zero is a legitimate value. Negative values are not assumed to be missing. Unconfigured columns are not assigned inferred types. A date is a calendar date (`YYYY-MM-DD`), not a timestamp. Unique-value checks use trimmed text and are case sensitive; for numeric uniqueness, `01` and `1` are distinct.

## Configure rules

```json
{
  "delimiter": ",",
  "columns": {
    "id": {"required": true, "unique": true},
    "observed_on": {"type": "date", "required": true},
    "measurement": {"type": "number", "min": 0, "sentinels": ["-9999"]}
  }
}
```

See [demo-schema.json](demo-schema.json) and the larger [ORDS profile](profiles/ords-v0.3.json). A composite key and grouped completeness look like this:

```json
{
  "columns": {
    "data_provider": {"required": true, "allowed": ["Provider A", "Provider B"], "unlisted": "warning"},
    "id": {"required": true},
    "event_date": {"required": true, "type": "date"},
    "record_date": {"type": "date", "not_before": "event_date"}
  },
  "unique_together": [{"columns": ["data_provider", "id"], "missing": "skip"}],
  "group_by": "data_provider"
}
```

`missing` decides what happens when a key component is blank: `report` (default) adds a `key_incomplete` error, while `skip` leaves the record out of the key check and counts it. `pattern` is a Python regular expression (max 200 characters) from your own rules file. Avoid catastrophic backtracking patterns, because the tool is local and does not time out a regex. The schema is a deliberately small custom format, not a Frictionless Table Schema implementation. The demo's unique station ID rule is illustrative: a real time-series dataset normally needs a composite station/date key. Always adapt rules to source documentation.

## Architecture

```text
CSV + explicit schema -> audit.py -> versioned JSON report
                              ^              |
CLI --------------------------|              +-> optional SQLite
Browser -> POST /api/audit ----|              +-> export / baseline counts
```

`audit.py` is independent of the UI and HTTP layer. `server.py` serves a fixed asset allowlist and a small API. `app.js` renders untrusted fields with `textContent`, not HTML. Reports contain counts, record positions, severities, rule names, column names, remediation hints and completeness counts, without raw cell values. Group labels in grouped completeness come from the configured code list; unlisted values become `(unlisted value)`.

### Report contract

Reports remain `report_version: 1`. This milestone **adds** fields: `severity` on each issue, `error_count`, `warning_count`, `error_free`, `counts_by_severity`, `completeness`, and, when configured, `profile`, `keys` and `completeness_by_group`. No existing field was removed or renamed and `valid` keeps its meaning (no findings at all). Schemas that do not use the new keys produce the same `schema_sha256` as before, so older reports remain comparable. Comparison adds `severity_delta` when both reports have severities.

`GET /api/health` returns status; `GET /api/demo?preset=sensor|repair|repair-corrected` returns a synthetic fixture and its rules (a fixed allowlist, never a file path); `GET /api/profiles/ords-v0.3` returns the profile; `POST /api/audit` accepts `{"csv":"...","schema":{...}}` and returns a report. Invalid requests return a 4xx JSON error. Raw CSV is not written to SQLite; persistence is opt-in. SQLite can be queried directly for saved reports; there is no history browser yet.

## Why this problem

Open data is available through [Belgium's portal](https://data.gov.be/en) and the [EU data portal](https://data.europa.eu/en/news-events/news/open-data-portals-around-europe-unveiling-belgiums-open-data-landscape). Structural and semantic CSV errors are documented in the [Frictionless validation guide](https://framework.frictionlessdata.io/docs/guides/validating-data.html). Mature tools such as Frictionless and Great Expectations already address validation. This project explores a small, dependency-free local workflow and explainable reports; it does not claim to replace them or fill a proven market gap.

See [RESEARCH.md](RESEARCH.md) for the opportunity review and [ROADMAP.md](ROADMAP.md) for the next milestones. The hypothesis that students or small civic-data teams need this workflow still requires interviews and real-data trials.

## Validation and limitations

See [VALIDATION.md](VALIDATION.md). UTF-8 CSV only; configurable one-character delimiter; 5 MB, 100,000 records and at most 500 stored finding examples. Counts cover all findings. Record numbers count CSV records, not physical lines, so quoted multiline values remain one record. Blank lines count as records.

Hashes cover decoded CSV text and canonical configuration. Reading files can normalise line endings, so `source_sha256` is **not necessarily the original file-byte hash**. Baseline comparison requires matching schema hashes and complete reports; it compares aggregate rule counts and does not establish which individual records were fixed. Duplicate/blank headers stop value validation with `complete=false`.

This is a local development server: no authentication, TLS or deployment hardening. Bind it to loopback and do not expose it publicly. No URL fetching or scraping is implemented. Reports still expose column names and record positions; review them before sharing. Huge files, Excel, automatic repair, inferred schemas, timestamps, freshness against today's date and production hosting are outside the current scope. The ORDS profile is a partial check of partner records. [ORDS.md](ORDS.md) lists the unsupported parts. It cannot audit the full Open Repair release, which exceeds the size limits.

## Contributing

Run `python -m unittest -v` before changes (56 tests). Include a failing fixture and a regression test for a validation bug. Discuss source licences before adding real datasets: Open Repair data is CC BY-SA 4.0, separate from this repository's MIT code licence, and no real records are committed. Keep demo records synthetic, and never commit private data, reports, databases, tokens or `.env` files.

Code licensed under MIT. ORDS code-list values are reproduced from Open Repair Data (Open Repair Alliance, CC BY-SA 4.0).
