"""Deterministic CSV checks. No network calls and no automatic data repair."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date
import hashlib
import io
import json
import math
from pathlib import Path
import sys

MAX_BYTES = 5_000_000
MAX_ROWS = 100_000
MAX_ISSUES = 500


class AuditError(ValueError):
    """Invalid input or configuration, rather than a data-quality finding."""


def validate_schema(schema: dict) -> dict:
    if not isinstance(schema, dict) or set(schema) - {"columns", "delimiter"}:
        raise AuditError("Schema must contain only columns and optional delimiter.")
    columns = schema.get("columns", {})
    if not isinstance(columns, dict):
        raise AuditError("columns must be an object keyed by column name.")
    delimiter = schema.get("delimiter", ",")
    if not isinstance(delimiter, str) or len(delimiter) != 1 or delimiter in '\r\n"':
        raise AuditError("delimiter must be one character other than newline or quote.")
    for name, rules in columns.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(rules, dict):
            raise AuditError("Each column needs a nonblank name and an object of rules.")
        if set(rules) - {"type", "required", "unique", "min", "max", "sentinels"}:
            raise AuditError("Unknown column rule.")
        kind = rules.get("type", "string")
        if kind not in {"string", "integer", "number", "date"}:
            raise AuditError("Supported types: string, integer, number, date.")
        for key in ("required", "unique"):
            if key in rules and not isinstance(rules[key], bool):
                raise AuditError(f"{key} must be true or false.")
        for key in ("min", "max"):
            if key in rules:
                value = rules[key]
                try:
                    finite = isinstance(value, (int, float)) and math.isfinite(value)
                except OverflowError:
                    finite = False
                if kind not in {"integer", "number"} or isinstance(value, bool) or not finite:
                    raise AuditError("Bounds require a numeric type and a finite number.")
        if "min" in rules and "max" in rules and rules["min"] > rules["max"]:
            raise AuditError("min cannot exceed max.")
        sentinels = rules.get("sentinels", [])
        if not isinstance(sentinels, list) or any(not isinstance(v, str) for v in sentinels):
            raise AuditError("sentinels must be a list of strings.")
    return {"columns": columns, "delimiter": delimiter}


def audit_csv(text: str, schema: dict | None = None) -> dict:
    """Row numbers are CSV record numbers, header=1, not physical line numbers.

    Issue examples never include cell values. Rules are explicit: zero is not
    missing and negative values are not sentinels unless configured as such.
    """
    if not isinstance(text, str):
        raise AuditError("CSV must be text.")
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise AuditError("CSV exceeds the 5 MB limit.")
    if "\x00" in text:
        raise AuditError("CSV contains a NUL character.")
    config = validate_schema(schema if schema is not None else {})
    reader = csv.reader(io.StringIO(text.lstrip("\ufeff"), newline=""), delimiter=config["delimiter"], strict=True)
    issues: list[dict] = []
    counts: Counter = Counter()
    affected: set[int] = set()
    total = 0

    def add(rule: str, row: int, column: str | None, message: str):
        nonlocal total
        total += 1
        counts[rule] += 1
        if row > 1:
            affected.add(row)
        if len(issues) < MAX_ISSUES:
            issues.append({"rule": rule, "row": row, "column": column, "message": message})

    try:
        header = next(reader, None)
        if header is None or not header or all(not x.strip() for x in header):
            raise AuditError("CSV needs a nonblank header row.")
        for index, name in enumerate(header):
            if not name.strip():
                add("blank_header", 1, None, f"Column {index + 1} has no name.")
        for name, count in Counter(header).items():
            if count > 1:
                add("duplicate_header", 1, name, "Column name occurs more than once; rename before validating values.")
        if counts["duplicate_header"] or counts["blank_header"]:
            # Ambiguous columns cannot safely be mapped to schema rules.
            return _report(text, config, header, 0, issues, counts, total, affected, False)
        rules_by_column = config["columns"]
        for name in rules_by_column:
            if name not in header:
                add("missing_column", 1, name, "Configured column is absent from the CSV header.")
        unique_seen: dict[str, set[str]] = {name: set() for name, rules in rules_by_column.items() if rules.get("unique")}
        row_count = 0
        for row_number, values in enumerate(reader, start=2):
            row_count += 1
            if row_count > MAX_ROWS:
                raise AuditError("CSV exceeds the 100,000 record limit.")
            if not values or all(not v.strip() for v in values):
                add("blank_row", row_number, None, "Record is empty.")
                continue
            if len(values) != len(header):
                add("row_width", row_number, None, "Record has a different number of fields than the header.")
                continue
            for name, raw in zip(header, values):
                rules = rules_by_column.get(name, {})
                value = raw.strip()
                if raw != value:
                    add("whitespace", row_number, name, "Leading or trailing whitespace; review before trimming.")
                if not value:
                    if rules.get("required"):
                        add("required", row_number, name, "Required value is blank.")
                    continue
                if value in rules.get("sentinels", []):
                    add("sentinel", row_number, name, "Configured placeholder value; check source documentation.")
                    continue
                if rules.get("unique"):
                    if value in unique_seen[name]:
                        add("duplicate_value", row_number, name, "Value repeats in a column configured as unique.")
                    unique_seen[name].add(value)
                kind = rules.get("type", "string")
                try:
                    if kind == "integer":
                        numeric = int(value)
                    elif kind == "number":
                        numeric = float(value)
                        if not math.isfinite(numeric):
                            raise ValueError
                    elif kind == "date":
                        # Strict ISO calendar date, not a timestamp or compact date.
                        parsed = date.fromisoformat(value)
                        if parsed.isoformat() != value:
                            raise ValueError
                    if kind in {"integer", "number"}:
                        if "min" in rules and numeric < rules["min"] or "max" in rules and numeric > rules["max"]:
                            add("out_of_range", row_number, name, "Value falls outside configured inclusive bounds.")
                except (ValueError, OverflowError):
                    add("invalid_type", row_number, name, f"Expected {kind}; review the source value.")
        return _report(text, config, header, row_count, issues, counts, total, affected, True)
    except csv.Error as exc:
        raise AuditError("Malformed CSV or field exceeds the parser limit.") from exc


def _report(text, config, header, rows, issues, counts, total, affected, complete):
    return {
        "report_version": 1,
        "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "schema_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
        "columns": header,
        "row_count": rows,
        "complete": complete,
        "valid": complete and total == 0,
        "issue_count": total,
        "affected_rows": len(affected),
        "counts_by_rule": dict(sorted(counts.items())),
        "issues": issues,
        "examples_truncated": total > len(issues),
        "note": "Passing these configured checks does not establish accuracy or fitness for use.",
    }


def compare_reports(before: dict, after: dict) -> dict:
    """Compare counts, not row identity: reordering records must not invent fixes."""
    if before.get("report_version") != 1 or after.get("report_version") != 1:
        raise AuditError("Both reports must use report_version 1.")
    if before.get("schema_sha256") != after.get("schema_sha256"):
        raise AuditError("Reports use different schemas; their rule counts are not comparable.")
    if not before.get("complete") or not after.get("complete"):
        raise AuditError("Cannot compare incomplete reports.")
    old, new = before["counts_by_rule"], after["counts_by_rule"]
    return {"delta_by_rule": {rule: new.get(rule, 0) - old.get(rule, 0) for rule in sorted(old.keys() | new.keys())},
            "issue_delta": after["issue_count"] - before["issue_count"],
            "note": "Negative means fewer findings, not proof that particular records were fixed."}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Audit a local UTF-8 CSV without uploading or modifying it.")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--schema", type=Path)
    parser.add_argument("--output", type=Path, help="Write a JSON report instead of stdout.")
    parser.add_argument("--baseline", type=Path, help="Compare with a previous JSON report using the same schema.")
    args = parser.parse_args(argv)
    try:
        if args.csv.stat().st_size > MAX_BYTES:
            raise AuditError("CSV exceeds the 5 MB limit.")
        schema = json.loads(args.schema.read_text(encoding="utf-8")) if args.schema else {}
        report = audit_csv(args.csv.read_text(encoding="utf-8"), schema)
        if args.baseline:
            report["comparison"] = compare_reports(json.loads(args.baseline.read_text(encoding="utf-8")), report)
        rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            if args.output.resolve() in {args.csv.resolve(), args.schema.resolve() if args.schema else None, args.baseline.resolve() if args.baseline else None}:
                raise AuditError("Output must not overwrite a source, schema or baseline file.")
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
        return 0 if report["valid"] else 1
    except (AuditError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"csv-triage: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
