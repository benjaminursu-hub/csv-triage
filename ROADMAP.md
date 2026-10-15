# Roadmap

## Delivered first slice

Python rule engine; local CLI; loopback JSON API; browser upload/paste; synthetic demo; filtering/export; reproducible schema/content hashes; optional SQLite persistence; meaningful core and HTTP regression tests.

## Week 1: validate the problem

- Interview three potential users (students, civic-data volunteers or data publishers); show the prototype and record actual pain points rather than leading questions.
- Choose one real dataset with a verified reuse licence and documented fields. Record provenance and limitations; do not assume every publicly downloadable dataset is open-licensed.
- Add composite unique keys and explicit timestamp parsing if the selected dataset needs them.
- Define a useful acceptance scenario with the users. Measure actual results before publishing speed or accuracy claims.

## Week 2: useful comparisons

- Add SQLite run-history browsing and a baseline picker.
- Distinguish rule/schema changes from data changes.
- Add stable record keys for per-record comparisons where a dataset supports them.
- Add integration tests for reordered records, schema migration and repeated imports.

## Week 3: better review workflow

- Add a schema editor, severity configuration and plain-language rule help.
- Add downloadable accessible HTML reports and keyboard/screen-reader testing.
- Ask users whether findings are actionable; track false positives and confusing messages.
- Profile memory and execution time on bounded real fixtures.

## Week 4: portfolio release

- Publish a reproducible demo recording with source provenance, before/after results and explicit limitations.
- Compare the workflow against Frictionless; document why someone would choose either tool.
- Add CI on Linux and Windows and supported Python versions.
- Package a versioned release; include engineering decisions and unresolved issues.

Success is a small workflow someone can demonstrate and explain, not a large list of unfinished features.
