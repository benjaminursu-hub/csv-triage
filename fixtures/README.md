# Repair-data fixtures

All records are **synthetic**. Provider names are ORDS code-list values; these organisations did not supply these records. Problem texts are markers (`SYNTHETIC-PROBLEM-nn`) so tests can prove they never reach a report.

Record numbers count the header as record 1. Profile: [`../profiles/ords-v0.3.json`](../profiles/ords-v0.3.json).

## `repair-seeded.csv`: 15 records, 12 findings (8 errors, 4 warnings)

| Record | Seeded defect | Expected rule | Severity |
|---|---|---|---|
| 2 | — (The Restart Project, ID 101) | — | — |
| 3 | Same ID 101 under a **different provider**: valid | — | — |
| 4 | The Restart Project + 101 again | `duplicate_key` | error |
| 5 | `country` = `be` | `pattern_mismatch` | error |
| 6 | `repair_status` = `Broken` | `not_allowed` | error |
| 7 | `product_category_id` 19 (Mobile) with category Laptop | `pair_mismatch` | error |
| 8 | `event_date` = 2025-02-30 | `invalid_type` | error |
| 9 | `problem` blank | `required` | error |
| 10 | Barrier given while status is Fixed | `conditional_value` | warning |
| 11 | `year_of_manufacture` 2026, event in 2025 | `date_order` | warning |
| 12 | Provider `Example Repair Group` not in the list | `not_allowed` | warning |
| 13 | `product_age` = 2.25 (two decimals) | `pattern_mismatch` | error |
| 14 | End of life, all optional fields blank: valid | — | — |
| 15 | `record_date` before `event_date` | `date_order` | warning |
| 16 | `id` blank (key skipped, counted as incomplete) | `required` | error |

## `repair-corrected.csv`: same records, 2 findings (0 errors, 2 warnings)

Corrections: record 4 gets ID 103; `country` BEL; status `Unknown` (the true outcome is not known); category ID 16; date 2025-02-28; problem text added; barrier removed; age 2.3; record date 2025-06-15; missing ID 115. Records 11 and 12 are deliberately left as they are because the warnings may be legitimate (an estimated year, a new partner). Nothing is dropped.

## `repair-valid.csv` and `repair-valid.expected.json`

Six records with no findings. They cover the same ID under two providers, numeric codes (`2`, `3`, `0`, barrier `6`), barrier text, leap day 2024-02-29, a record date on the event day, a half-year age and blank optional fields. The expected file is the complete deterministic report. Regenerate it only for an intentional, documented report change.
