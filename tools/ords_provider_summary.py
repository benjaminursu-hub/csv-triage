"""Count per-provider gaps in a whole Open Repair aggregate release.

CSV Triage's audit is limited to 5 MB, but a release is about 58 MB. This
script streams the file one record at a time (constant memory) and prints, per
data provider, how many records have no `problem` text, how many brands are the
placeholder "Unknown", and how many End of life records name a repair barrier.
It prints counts only, never cell values.

    python tools/ords_provider_summary.py OpenRepairData_v0.3_aggregate_202507.csv
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from pathlib import Path
import sys

FIELDS = ("data_provider", "problem", "brand", "repair_status", "repair_barrier_if_end_of_life")


def summarise(source: Path) -> dict[str, Counter]:
    stats: dict[str, Counter] = {}
    with source.open(encoding="utf-8", newline="") as infile:
        reader = csv.DictReader(infile)
        missing = [f for f in FIELDS if f not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"Missing ORDS columns: {', '.join(missing)}")
        for row in reader:
            c = stats.setdefault(row["data_provider"], Counter())
            c["records"] += 1
            c["no_problem"] += not (row["problem"] or "").strip()
            c["brand_unknown"] += (row["brand"] or "").strip() == "Unknown"
            if (row["repair_status"] or "").strip() in {"End of life", "3"}:
                c["end_of_life"] += 1
                c["with_barrier"] += bool((row["repair_barrier_if_end_of_life"] or "").strip())
    return stats


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "-"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Per-provider gaps in a whole ORDS release (streamed).")
    parser.add_argument("source", type=Path)
    args = parser.parse_args(argv)
    try:
        stats = summarise(args.source)
    except (OSError, UnicodeError, ValueError, csv.Error) as exc:
        print(f"ords_provider_summary: {exc}", file=sys.stderr)
        return 2
    print("| Data provider | Records | No problem text | Brand \"Unknown\" | End of life with barrier |")
    print("| --- | ---: | ---: | ---: | ---: |")
    total = Counter()
    for name, c in sorted(stats.items(), key=lambda item: -item[1]["records"]):
        total.update(c)
        print(f"| {name} | {c['records']:,} | {c['no_problem']:,} ({pct(c['no_problem'], c['records'])}) | "
              f"{pct(c['brand_unknown'], c['records'])} | {c['with_barrier']:,} of {c['end_of_life']:,} "
              f"({pct(c['with_barrier'], c['end_of_life'])}) |")
    print(f"| **All** | {total['records']:,} | {total['no_problem']:,} ({pct(total['no_problem'], total['records'])}) | "
          f"{pct(total['brand_unknown'], total['records'])} | {total['with_barrier']:,} of {total['end_of_life']:,} "
          f"({pct(total['with_barrier'], total['end_of_life'])}) |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
