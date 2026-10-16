# Validation record

## Real-data case study: 16 October 2026

Checked in a Linux container, Python 3.13. Results are in [CASE_STUDY.md](CASE_STUDY.md).

- Downloaded release 202507 by its pinned URL; SHA-256 matched the published Git LFS pointer.
- `tools/ords_sample.py` reproduced the earlier 15,033-record sample byte for byte. The sample's SHA-256 is recorded in the case study.
- Audit results matched the milestone check: 4,698 `required` errors (all `problem`), 0 code-list errors; 2,781 vs 0 duplicates for naive vs provider + ID keys on partner-level IDs.
- `tools/ords_provider_summary.py` streamed the whole 58 MB file in about 2 seconds.
- 6 new tests in `test_tools.py` (sampling order, prefix removal, overwrite refusal, per-provider counts, no cell values in output, rejection of non-ORDS files): **62 tests pass**.
- The README demo GIF was recorded from the real local dashboard with Playwright.

Not verified: the commands on Windows (written for PowerShell, not yet run there), and why two providers publish no problem text.

## Windows connection-reset fix: 16 October 2026

Checked locally on Windows, Python 3.13 (64-bit).

**Symptom.** `test_content_type_and_request_limit` failed intermittently on Windows with `ConnectionAbortedError` (WinError 10053), never on Linux. Running only that test 20 times failed **3 of 20**. It had passed in GitHub CI and in an earlier local run, which is why it went unnoticed.

**Cause.** The server rejects some requests (403, 404, 413, 415) before reading their body. On Windows, closing a socket that still holds unread incoming bytes sends a TCP reset instead of a normal close. When that reset reaches the client before it has read the reply, the client sees an aborted connection instead of the status code. It is a race between reply and reset, so it fails only some of the time.

**Fix.** A lingering close in `server.py`: after every reply the server shuts down its sending side, then reads and discards whatever the client still sends until the client closes. This is bounded to 1 second and 64 KB, so a slow or dishonest client cannot hold a thread. One mechanism covers every early reply, including a client that announces 6 MB but sends 2 bytes.

**Rejected attempt.** Reading the body before the 403, 404 and 415 replies only (not 413, to avoid waiting for bytes a dishonest client never sends) still failed 11 of 100, because the test's 413 request was left exposed.

**Measurement.** A diagnostic script ran two servers at once, the unchanged one and one with the lingering close, and sent the same requests to both, interleaved, on fresh connections (400 rounds, file versions confirmed by hash):

| Request | Without lingering close | With lingering close |
|---|---|---|
| Missing `Content-Type` (415) | 26 / 400 | 0 / 400 |
| Says 6 MB, sends 2 bytes (413) | 32 / 400 | 0 / 400 |
| Honest body over a lowered limit (413) | 35 / 400 | 0 / 400 |

Earlier single-server runs were discarded: afterwards, it could not be confirmed which version of `server.py` was on disk during them.

**After the fix:** the unchanged test, run 100 times in a row, failed **0 of 100** times, and the full suite passed (56 tests).


## Repair-data milestone: 15 October 2026

Checked in a Linux cloud container (Python 3.13.16, Chromium via Playwright), not on Windows. GitHub CI then passed the same suite on Windows and Ubuntu with Python 3.11 and 3.12.

### Automated checks

- Baseline before changes: 30 tests passed at `2c872c1`.
- After changes: **56 tests pass** (`python -m unittest -v`): the original 30 unchanged plus 26 in `test_repair.py`.
- The new tests cover the exact seeded findings per record, the corrected fixture (−10 findings, −8 errors, −2 warnings under the same profile), the valid fixture against its complete expected report, the same ID under two providers (accepted), repeated provider/ID (flagged with the first record), both missing-component policies, blank optional fields, missing optional and required columns, code lists (codes, text, case, the *Too worn out* spelling, an unlisted provider as a warning), category pairing, conditional barrier, date edge cases (leap day, 29 February 2025, unpadded, timestamp, compact and day-first dates), year/record-date order, age precision, invalid new rule configurations, the unchanged legacy schema hash, comparison with reports that predate severities, `--fail-on error`, real HTTP requests for the repair presets, a preset allowlist that rejects path-like names, and SQLite/JSON reports without free text or unlisted values.
- **Mutation check:** making the composite key ignore `data_provider` caused 7 repair tests to fail. Restored afterwards.

### Browser checks (Playwright, real local server on port 8766)

- **Repair records (seeded) → Load example → Run audit**: 15 records, 12 findings, 8 errors, 4 warnings, 12 affected records. Focus moved to the results heading.
- Severity filter *Warnings only* showed 4 rows; rule filter `duplicate_key` showed one row: record 4, "Same data_provider+id combination as record 2."
- Key summary: 14 records keyed, 1 repeated, 1 with a blank component.
- Completeness listed 15 columns. Completeness by provider for `problem`: The Restart Project 7 of 8 (88%), Repair Café International 6 of 6, `(unlisted value)` 1 of 1.
- **Export JSON** downloaded a version 1 report with `{"error": 8, "warning": 4}` and no `SYNTHETIC` problem marker.
- **Repair records (corrected)** run next: 2 findings, 0 errors, 2 warnings. The comparison line read "−10 findings (−8 errors, −2 warnings)".
- The generic sensor demo still produced 8 findings (6 errors, 2 warnings) and hid the provider section.
- Keyboard: Tab order from the page start was brand link → example select → Load example → Use ORDS v0.3 rules → file → CSV.
- No console errors. The content security policy blocked Playwright's string-eval waits, as intended, so the script used selector-based waits.
- **Layout:** at 390 px wide, the new example select initially caused horizontal page scrolling (442 px). The baseline did not. This was fixed and rechecked: no horizontal overflow. Desktop layout was inspected from a full-page screenshot.

### Real-data check

A bounded sample from Open Repair release 202507 (15,033 records, not committed) was audited with the profile. Results and caveats are in [ORDS.md](ORDS.md#real-data-check-bounded-not-committed).

### Not verified in this milestone

Screen-reader output, Firefox/Safari, the full 305,649-record release, partner-level files from any real provider, and whether repair-data practitioners find the findings useful. No performance claim is made.

## Initial prototype: 15 October 2026

Checked locally on Windows, Python 3.12.14.

### Automated checks

`python -m unittest -v` exercises the engine, CLI, real loopback HTTP requests and SQLite persistence. The suite covers the exact eight demo defects, zero/negative semantics, UTF-8 BOM, semicolon delimiters, quoted multiline fields, header ambiguity, record width, invalid dates/numbers, inclusive bounds, capped finding examples with complete counts, deterministic reports, schema-compatible comparison, input/configuration limits, source-overwrite prevention, API request rejection and SQLite storage without raw cell values.

The initial verification found an open SQLite connection on Windows; it was fixed using explicit connection closure and the suite was rerun. Sandboxed loopback connection restrictions required running the HTTP integration checks outside the sandbox. They were not skipped or replaced with mocks.

### Browser checks

- Local dashboard loaded from `http://127.0.0.1:8765`.
- **Load demo -> Run audit** produced 7 records, 8 findings and 6 affected records.
- Filtering to `invalid_type` showed precisely three rows.
- **Export JSON** downloaded a version 1 report.
- Result rendering and layout were visually inspected.

### Not yet verified

Real-user usefulness, production hosting, full assistive-technology compatibility, very large files, non-UTF-8 CSVs, Excel support and dataset-specific validation accuracy. No performance benchmark is claimed.

The demo is synthetic, not a copy of an official dataset. Reports intentionally contain no cell values, but column names and record positions can still be sensitive. The local server is a development tool, not a hosted upload service.
