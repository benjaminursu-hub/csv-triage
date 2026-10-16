# Case study: auditing a real Open Repair release

Checked on 16 October 2026 against the Open Repair Alliance's aggregate release **202507** (305,649 repair records, ORDS v0.3). Every number below comes from the commands in [Reproduce it](#reproduce-it).

## What the audit found

1. **Two providers send no fault descriptions at all.** All 29,929 records from Repair Café Denmark and all 5,567 from Repair Café Toronto have a blank `problem`, a field ORDS v0.3 requires. They account for 49% of the release's 71,779 blank descriptions. Any analysis of what breaks silently leaves these two providers out.
2. **IDs are only unique per provider.** With partner-level IDs, a naive "`id` must be unique" rule reports **2,781 duplicates** in a 15,033-record sample. The provider + ID key that the standard implies reports **0**. The naive rule would have flagged thousands of valid records.
3. **The coded fields are clean.** In the same sample there were **0** code-list violations (repair status, barrier, 40 product categories), 0 invalid dates and 0 badly shaped country codes.

## The data

| | |
| --- | --- |
| Release | `aggregated/202507` in [openrepair/data](https://github.com/openrepair/data/tree/3d968a71cb717d129a62b1161f20757380d53aa3/aggregated/202507), commit `3d968a7`. Published October 2025, data to the end of July 2025 |
| File | `OpenRepairData_v0.3_aggregate_202507.csv`, 58,453,790 bytes, SHA-256 `364d741b39b40ce955a5a9f83adf9776b3f40f2f857cc2cd96b6ae1818aabe82` |
| Licence | CC BY-SA 4.0. *Open Repair Data, Open Repair Alliance.* No records are committed to this repository; only counts derived from them |
| Sample | First 2,000 records per provider in file order (Fixit Clinic has 1,033), 15,033 records, 2.7 MB. First-N per provider, **not random** |

## Findings in detail

### Blank descriptions are concentrated in two providers

The audit of the sample reported 4,698 `required` errors, all for `problem`. The whole-release summary shows where they come from:

| Data provider | Records | No problem text | Brand "Unknown" | End of life with barrier |
| --- | ---: | ---: | ---: | ---: |
| The Restart Project | 107,836 | 26,920 (25%) | 46% | 8,623 of 22,960 (38%) |
| Repair Café International | 105,485 | 9,295 (9%) | 29% | 8,300 of 33,018 (25%) |
| anstiftung | 32,724 | 14 (0%) | 47% | 3,356 of 7,611 (44%) |
| Repair Café Denmark | 29,929 | 29,929 (100%) | 37% | 5,942 of 9,096 (65%) |
| Repair Cafe Wales | 20,190 | 54 (0%) | 27% | 3,261 of 4,001 (82%) |
| Repair Café Toronto | 5,567 | 5,567 (100%) | 100% | 0 of 469 (0%) |
| Repair Connects | 2,885 | 0 (0%) | 0% | 400 of 433 (92%) |
| Fixit Clinic | 1,033 | 0 (0%) | 18% | 29 of 121 (24%) |
| **All** | 305,649 | 71,779 (23%) | 39% | 29,911 of 77,709 (38%) |

The data does not say why these fields are empty. A provider may not collect descriptions, or may remove them before publishing (ORDS asks for personal data to be removed). It should be asked, not assumed.

### Placeholders hide missing values

`brand` looks 100% complete, but 39% of brands are the placeholder `Unknown` (the aggregate's own schema lists it as a missing value). CSV Triage counts it as filled unless you say otherwise: add `"sentinels": ["Unknown"]` to `brand` in your rules. The completeness table then counts it as a placeholder, and each one is listed as a `sentinel` warning (6,357 in the sample).

### Optional fields are sparse

In the sample, `year_of_manufacture` and `product_age` are filled for 24.5% of records. A repair barrier is given for 38% of End of life records in the whole release. These are optional in ORDS, so the audit reports them as completeness, not as errors.

### Two observations about the release format

- The aggregate has no `record_date` column (an optional ORDS field), so the audit warns once that its checks did not run.
- In the sample, one `group_identifier` value has leading or trailing whitespace.

## What this means for an analyst

- Before analysing fault descriptions, filter or report by provider: two of eight providers contribute nothing to that field.
- Count duplicates on `data_provider` + `id`, never on `id` alone.
- Treat `brand = Unknown` as missing.

## Limits of this case study

- The audit ran on a first-N sample because CSV Triage is limited to 5 MB. The per-provider table covers the whole release, counted by a separate streaming script.
- The aggregate is not what partners submit: its IDs carry a provider prefix and it has no `record_date`. Partner-level IDs were recreated by removing the prefix.
- These checks are a partial ORDS profile ([ORDS.md](ORDS.md)), not a conformance test. No provider was contacted, and the reasons for the gaps are unknown.

## Reproduce it

PowerShell on Windows (Python 3.11+, from the repository folder; the data goes in a folder outside it):

```powershell
New-Item -ItemType Directory -Force ..\ords-data | Out-Null
curl.exe -L -o ..\ords-data\aggregate.csv "https://media.githubusercontent.com/media/openrepair/data/3d968a71cb717d129a62b1161f20757380d53aa3/aggregated/202507/OpenRepairData_v0.3_aggregate_202507.csv"
(Get-FileHash ..\ords-data\aggregate.csv).Hash   # 364D741B…AABE82

# Whole release, streamed: the per-provider table
python tools/ords_provider_summary.py ..\ords-data\aggregate.csv

# Sample, audited with the ORDS profile: 4,698 required errors, 0 code-list errors
python tools/ords_sample.py ..\ords-data\aggregate.csv ..\ords-data\sample.csv
python audit.py ..\ords-data\sample.csv --schema profiles/ords-v0.3.json --output ..\ords-data\report.json

# Partner-level IDs: naive unique ID (2,781 duplicates) vs provider + ID key (0)
python tools/ords_sample.py ..\ords-data\aggregate.csv ..\ords-data\partner.csv --partner-ids
'{"columns": {"id": {"unique": true}}}' | Set-Content ..\ords-data\naive.json
python audit.py ..\ords-data\partner.csv --schema ..\ords-data\naive.json --output ..\ords-data\naive-report.json
python audit.py ..\ords-data\partner.csv --schema profiles/ords-v0.3.json --output ..\ords-data\key-report.json
```

The audits exit with code 1 because they have findings. Expected SHA-256 of the samples: `sample.csv` `5abd7952d65f2c37b90c78e64698d80ea264298a6f108dd969dcdaa758f94f99`, `partner.csv` `018997e45ee4bd0a004bd289c502cb362dad3f3e2c02293b94ba224c05e3d571`. Open a report's `counts_by_rule`, `keys` and `completeness_by_group` to see the numbers above.
