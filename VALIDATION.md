# Validation record

Checked locally on 15 October 2026, Windows, Python 3.12.14.

## Automated checks

`python -m unittest -v` exercises the engine, CLI, real loopback HTTP requests and SQLite persistence. The suite covers the exact eight demo defects, zero/negative semantics, UTF-8 BOM, semicolon delimiters, quoted multiline fields, header ambiguity, record width, invalid dates/numbers, inclusive bounds, capped finding examples with complete counts, deterministic reports, schema-compatible comparison, input/configuration limits, source-overwrite prevention, API request rejection and SQLite storage without raw cell values.

The initial verification found an open SQLite connection on Windows; it was fixed using explicit connection closure and the suite was rerun. Sandboxed loopback connection restrictions required running the HTTP integration checks outside the sandbox. They were not skipped or replaced with mocks.

## Browser checks

- Local dashboard loaded from `http://127.0.0.1:8765`.
- **Load demo -> Run audit** produced 7 records, 8 findings and 6 affected records.
- Filtering to `invalid_type` showed precisely three rows.
- **Export JSON** downloaded a version 1 report.
- Result rendering and layout were visually inspected.

## Not yet verified

Real-user usefulness, production hosting, full assistive-technology compatibility, very large files, non-UTF-8 CSVs, Excel support and dataset-specific validation accuracy. No performance benchmark is claimed.

The demo is synthetic, not a copy of an official dataset. Reports intentionally contain no cell values, but column names and record positions can still be sensitive. The local server is a development tool, not a hosted upload service.
