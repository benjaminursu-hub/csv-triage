# ORDS v0.3 repair-data profile

[`profiles/ords-v0.3.json`](profiles/ords-v0.3.json) is a CSV Triage rule set for **partner-level** repair records described by the Open Repair Data Standard (ORDS) v0.3. It implements a documented subset of the standard. **Passing it is not ORDS conformance**; see the gaps below.

## Pinned sources

Checked on 15 October 2026.

| Source | Pinned to | Used for |
|---|---|---|
| [ORDS v0.3 standard](https://standard.openrepair.org/standard.html) | [`openrepair/datastandard@c1a1f29`](https://github.com/openrepair/datastandard/tree/c1a1f2979937a3a481782d3afbde1b62f9b24b58) (`standard.rst`, last commit 30 May 2024) | Field names, required/optional modules, formats, repair status and barrier code lists |
| [Open Repair data repository](https://github.com/openrepair/data) | [`openrepair/data@3d968a7`](https://github.com/openrepair/data/tree/3d968a71cb717d129a62b1161f20757380d53aa3), release `aggregated/202507` | Product category code list (40 values), data provider names, real-data sample check |
| Aggregate release 202507 | `OpenRepairData_v0.3_aggregate_202507.csv`, 58,453,790 bytes, SHA-256 `364d741b39b40ce955a5a9f83adf9776b3f40f2f857cc2cd96b6ae1818aabe82` (matches the Git LFS pointer) | Bounded sample check only, not committed |

Release facts from the data repository README: published October 2025 with data to the end of July 2025; 305,649 powered items; ORDS v0.3; licensed **CC BY-SA 4.0**. The Open Repair site links newer reporting with higher totals, so this project refers to "release 202507", not "the current total". The downloads page (`openrepair.org/open-data/downloads`) returned a redirect loop to our fetch tool on 15 October 2026, so its contents were not re-checked here.

## Field rules

| Field | Standard (v0.3) | Profile rule | Severity |
|---|---|---|---|
| `id` | Required. Unique within the partner's data, not across partners | Required; **unique together with `data_provider`** | error |
| `data_provider` | Required. Option from a code list that the standard does not print | Required; exact match against the 8 providers in release 202507 | unlisted = **warning** (a new partner is not wrong) |
| `country` | Required. 3-letter ISO code | Required; shape `^[A-Z]{3}$` | error |
| `partner_product_category` | Required. Partner code list or free text | Required only | error |
| `product_category` | Optional. ORDS code list | Exact match against the 40 categories | error |
| `product_category_id` | Field reference only (not in the module table) | Exact match `1`–`40`, must correspond to `product_category` when both are filled | error |
| `brand` | Optional free text | Completeness only | — |
| `year_of_manufacture` | Optional. `YYYY` | Four-digit year; later than the event year | error / **warning** |
| `product_age` | Optional. Float with 0–1 decimal places | Number ≥ 0 with at most one decimal place | error |
| `repair_status` | Required. Code list 0–3 or text | Required; `0`–`3`, `Unknown`, `Fixed`, `Repairable`, `End of life` (exact) | error |
| `repair_barrier_if_end_of_life` | Optional. Code list 1–6 or text; only relevant for End of life | Code or code-list text; present when status is not End of life | error / **warning** |
| `group_identifier` | Optional. Identifies a group | Completeness only (it legitimately repeats across records) | — |
| `problem` | Required free text; remove personal data | Required; **never copied into reports** | error |
| `event_date` | Required. `YYYY-MM-DD` | Required strict calendar date | error |
| `record_date` | Optional. `YYYY-MM-DD`, last updated | Strict calendar date; earlier than `event_date` | error / **warning** |

A missing **required** column is an error. A missing **optional** column is a warning: its checks did not run. Blank optional values are never findings; they appear in the completeness table. Unconfigured extra columns are allowed and only receive structural and whitespace checks.

**Errors** break a rule the profile states as a requirement. **Warnings** are observations that may be correct (a new partner, an estimated year after the event date, a barrier recorded for a non-End of life item). `--fail-on error` lets warnings pass in CI.

## Decisions and discrepancies

- **Provider-scoped IDs.** In the sampled release, after removing the aggregator's `provider_` prefix, a naive unique-`id` rule produced **2,781 false duplicates in 15,033 records**; the `data_provider`+`id` key produced 0. Across the full release, 90,563 numeric local IDs occur under more than one provider. Records with a blank key component are skipped by the key check (counted in `keys.records_incomplete`) because `required` already reports the blank; generic schemas can choose `"missing": "report"` instead.
- **Aggregate IDs differ from partner IDs.** The aggregate prefixes IDs (`restart_73`), while its `tableschema.json` declares the pattern `^[a-z]+-[0-9]+$` (hyphen). Every one of the 305,649 IDs uses an underscore. The profile targets partner records and does not impose either pattern.
- **Barrier wording.** The standard's code-list table says *No way to open product* and *Item too worn out*; its narrative section says *the product* / *Product too worn out*; the aggregate `tableschema.json` enum says *Too worn out*. The released data uses the code-list table wording, so the profile accepts exactly those six strings plus codes 1–6. Other spellings are flagged rather than guessed.
- **Blank repair status.** The module table makes `repair_status` required, while the code-list note says an empty or zero value is recorded as Unknown. The profile follows the module table (blank = error) and accepts `0`.
- **`problem` is required by v0.3** but is optional in the aggregate's `tableschema.json`. On the bounded sample, the profile's only high-volume finding was 4,698 blank `problem` values (31%). This is reported as a finding about partner-level requirements, not as a defect in the published aggregate.
- **No inferred dates.** "Today" is not used, so future event dates are not detected and the same input always gives the same report.

## Real-data check (bounded, not committed)

Profile run on the first ≤2,000 records per provider from release 202507 (15,033 records, 2.7 MB), on a Linux container with Python 3.13:

| Result | Count |
|---|---|
| Code-list violations (`not_allowed`, `pair_mismatch`) | 0 |
| Invalid dates, years, ages or country shapes | 0 |
| Blank `problem` (required in v0.3) | 4,698 errors |
| `record_date` column absent | 1 warning |
| Whitespace in `group_identifier` | 1 warning |
| `brand` recorded as `Unknown` | 6,357 (counted as filled; see gaps) |

Zero code-list findings on real data is evidence that the lists were transcribed correctly, not proof that the sample is accurate. The sample is first-N per provider, not random. Timing is not reported as a benchmark.

## Not implemented

- Membership in the ISO 3166-1 alpha-3 list (only the shape is checked).
- `product_age` and `year_of_manufacture` consistency with each other.
- `partner_product_category` mappings to ORDS categories.
- `group_identifier` uniqueness across partners (needs data from several partners and a group register).
- Personal data detection in `problem`, such as e-mail addresses.
- Provider-specific placeholders such as `brand = Unknown` (configure `sentinels` if your source uses one).
- Future-date checks, licence or package-manifest checks, and the aggregate (prefixed) layout.
- Files over 5 MB or 100,000 records, so the full release cannot be audited yet.

## Data licence

The repository's code is MIT. ORDS data is CC BY-SA 4.0. **No Open Repair records are committed.** The fixtures are synthetic; real provider names appear only as code-list values. The code lists (product categories, provider names) are reproduced as identifiers with attribution: *Open Repair Data, Open Repair Alliance, CC BY-SA 4.0*.
