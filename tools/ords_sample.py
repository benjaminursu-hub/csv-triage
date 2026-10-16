"""Make a bounded, reproducible sample of an Open Repair aggregate release.

The aggregate is too large for the 5 MB audit limit. This keeps the first N
records of each data provider, in file order, so every provider is represented
and the same input always gives the same sample. It never edits values.

With --partner-ids the aggregator's provider prefix is removed from `id`
(`restart_73` -> `73`), which recreates the partner-level IDs that ORDS
describes. Use it to compare a naive unique-ID rule with the provider + ID key.

    python tools/ords_sample.py OpenRepairData_v0.3_aggregate_202507.csv sample.csv
    python tools/ords_sample.py OpenRepairData_v0.3_aggregate_202507.csv partner.csv --partner-ids

The data is licensed CC BY-SA 4.0 by the Open Repair Alliance. Keep samples out
of this repository (see CASE_STUDY.md).
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from pathlib import Path
import sys


def make_sample(source: Path, target: Path, per_provider: int, partner_ids: bool) -> Counter:
    counts: Counter = Counter()
    with source.open(encoding="utf-8", newline="") as infile, target.open("w", encoding="utf-8", newline="") as outfile:
        reader = csv.reader(infile)
        header = next(reader)
        if "data_provider" not in header or "id" not in header:
            raise ValueError("Expected an ORDS file with data_provider and id columns.")
        provider, ident = header.index("data_provider"), header.index("id")
        writer = csv.writer(outfile, lineterminator="\n")
        writer.writerow(header)
        for row in reader:
            if len(row) != len(header) or counts[row[provider]] >= per_provider:
                continue
            counts[row[provider]] += 1
            if partner_ids:
                row[ident] = row[ident].split("_", 1)[-1]
            writer.writerow(row)
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Sample an ORDS aggregate: first N records per provider.")
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--per-provider", type=int, default=2000)
    parser.add_argument("--partner-ids", action="store_true", help="Strip the aggregator's provider_ prefix from id.")
    args = parser.parse_args(argv)
    if args.per_provider < 1:
        parser.error("--per-provider must be at least 1")
    if args.target.resolve() == args.source.resolve():
        parser.error("target must differ from source")
    try:
        counts = make_sample(args.source, args.target, args.per_provider, args.partner_ids)
    except (OSError, UnicodeError, ValueError, csv.Error) as exc:
        print(f"ords_sample: {exc}", file=sys.stderr)
        return 2
    print(f"{sum(counts.values())} records from {len(counts)} providers -> {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
