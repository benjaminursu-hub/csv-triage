# Roadmap

## Delivered first slice

Python rule engine; local CLI; loopback JSON API; browser upload/paste; synthetic demo; filtering/export; reproducible schema/content hashes; optional SQLite persistence; meaningful core and HTTP regression tests; Windows/Linux CI for Python 3.11 and 3.12.

## Delivered: repair-data profile (ORDS v0.3)

Composite keys with a missing-component policy; code lists; format, year and cross-field rules; error/warning severity with `--fail-on error`; completeness per field and per provider; a pinned ORDS v0.3 profile; seeded, corrected and valid synthetic fixtures; dashboard presets; 26 new tests; a bounded real-data check. Details in [ORDS.md](ORDS.md).

## Delivered: real-data case study

A reproducible audit of Open Repair release 202507 with per-provider findings ([CASE_STUDY.md](CASE_STUDY.md)) and two helper scripts in `tools/`.

## Next: make the repair profile trustworthy on real files

- Ask one or two repair-data practitioners to review [ORDS.md](ORDS.md) and a report from their own export. Record which findings were useful or wrong. Do not contact organisations without the maintainer's approval.
- Add streaming so the full 202507 release (58 MB) can be audited. Measure memory and time before claiming either.
- Decide whether an aggregate-layout profile is useful (prefixed IDs, no `record_date`).
- Add ISO 3166-1 alpha-3 membership from a pinned, licensed list.

## Week 1: validate the problem

- Interview three potential users (students, civic-data volunteers or data publishers); show the prototype and record actual pain points rather than leading questions.
- Choose one real dataset with a verified reuse licence and documented fields. Record provenance and limitations; do not assume every publicly downloadable dataset is open-licensed.
- ~~Map ORDS v0.3 fields, partner-scoped identifiers and code lists on a bounded sample.~~ Done; streaming is still needed for the full aggregate.
- Define a useful acceptance scenario with the users. Measure actual results before publishing speed or accuracy claims.

## Week 2: useful comparisons

- Add SQLite run-history browsing and a baseline picker.
- Distinguish rule/schema changes from data changes.
- Add stable record keys for per-record comparisons where a dataset supports them.
- Add integration tests for reordered records, schema migration and repeated imports.

## Week 3: better review workflow

- Add a schema editor, per-rule severity overrides and plain-language rule help.
- Add downloadable accessible HTML reports and keyboard/screen-reader testing.
- Ask users whether findings are actionable; track false positives and confusing messages.
- Profile memory and execution time on bounded real fixtures.

## Week 4: portfolio release

- Publish a reproducible demo recording with source provenance, before/after results and explicit limitations.
- Compare the workflow against Frictionless; document why someone would choose either tool.
- Extend the existing CI matrix and add automated browser-flow checks.
- Package a versioned release; include engineering decisions and unresolved issues.

Success is a small workflow someone can demonstrate and explain, not a large list of unfinished features.
