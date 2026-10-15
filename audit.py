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
import re
import sys

MAX_BYTES = 5_000_000
MAX_ROWS = 100_000
MAX_ISSUES = 500
MAX_PATTERN = 200
MAX_ALLOWED = 1000

ERROR, WARNING = "error", "warning"
# Hard errors break a configured contract; warnings are quality observations to review.
RULE_SEVERITY = {
    "blank_header": ERROR, "duplicate_header": ERROR, "row_width": ERROR, "required": ERROR,
    "duplicate_value": ERROR, "invalid_type": ERROR, "out_of_range": ERROR, "pattern_mismatch": ERROR,
    "pair_mismatch": ERROR, "duplicate_key": ERROR, "key_incomplete": ERROR,
    "blank_row": WARNING, "whitespace": WARNING, "sentinel": WARNING,
    "conditional_value": WARNING, "date_order": WARNING,
    # missing_column and not_allowed depend on the column configuration.
}
COLUMN_RULES = {"type", "required", "unique", "min", "max", "sentinels", "allowed", "unlisted",
                "pattern", "pairs_with", "only_if", "not_after", "not_before", "description"}
TOP_LEVEL = {"columns", "delimiter", "profile", "unique_together", "group_by"}


class AuditError(ValueError):
    """Invalid input or configuration, rather than a data-quality finding."""


def _string_list(value, name, limit):
    if not isinstance(value, list) or len(value) > limit or any(not isinstance(v, str) or not v.strip() for v in value):
        raise AuditError(f"{name} must be a list of at most {limit} nonblank strings.")
    if len(set(value)) != len(value):
        raise AuditError(f"{name} contains a repeated value.")


def validate_schema(schema: dict) -> dict:
    if not isinstance(schema, dict) or set(schema) - TOP_LEVEL:
        raise AuditError("Schema may contain only columns, delimiter, profile, unique_together and group_by.")
    columns = schema.get("columns", {})
    if not isinstance(columns, dict):
        raise AuditError("columns must be an object keyed by column name.")
    delimiter = schema.get("delimiter", ",")
    if not isinstance(delimiter, str) or len(delimiter) != 1 or delimiter in '\r\n"':
        raise AuditError("delimiter must be one character other than newline or quote.")
    for name, rules in columns.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(rules, dict):
            raise AuditError("Each column needs a nonblank name and an object of rules.")
        if set(rules) - COLUMN_RULES:
            raise AuditError("Unknown column rule.")
        kind = rules.get("type", "string")
        if kind not in {"string", "integer", "number", "date", "year"}:
            raise AuditError("Supported types: string, integer, number, date, year.")
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
        if "allowed" in rules:
            _string_list(rules["allowed"], "allowed", MAX_ALLOWED)
        if "unlisted" in rules and ("allowed" not in rules or rules["unlisted"] not in {ERROR, WARNING}):
            raise AuditError("unlisted must be error or warning and requires allowed.")
        if "pattern" in rules:
            pattern = rules["pattern"]
            if not isinstance(pattern, str) or not pattern or len(pattern) > MAX_PATTERN:
                raise AuditError(f"pattern must be a nonempty string of at most {MAX_PATTERN} characters.")
            try:
                re.compile(pattern)
            except re.error as exc:
                raise AuditError("pattern is not a valid regular expression.") from exc
        if "description" in rules and not isinstance(rules["description"], str):
            raise AuditError("description must be text.")
        if "pairs_with" in rules:
            pair = rules["pairs_with"]
            if (not isinstance(pair, dict) or set(pair) != {"column", "map"} or not isinstance(pair["map"], dict)
                    or not pair["map"] or any(not isinstance(k, str) or not isinstance(v, str) for k, v in pair["map"].items())):
                raise AuditError("pairs_with needs a column and a nonempty map of text to text.")
            _referenced(columns, pair["column"], name)
        if "only_if" in rules:
            condition = rules["only_if"]
            if not isinstance(condition, dict) or set(condition) != {"column", "in"}:
                raise AuditError("only_if needs a column and an in list.")
            _string_list(condition["in"], "only_if.in", MAX_ALLOWED)
            _referenced(columns, condition["column"], name)
        for key in ("not_after", "not_before"):
            if key in rules:
                other = _referenced(columns, rules[key], name)
                if kind not in {"date", "year"} or other.get("type") not in {"date", "year"}:
                    raise AuditError(f"{key} compares date or year columns only.")
    config = {"columns": columns, "delimiter": delimiter}
    # New keys are included only when used, so existing schema hashes stay stable.
    if "profile" in schema:
        profile = schema["profile"]
        if (not isinstance(profile, dict) or set(profile) - {"name", "version", "source"}
                or any(not isinstance(v, str) or len(v) > 300 for v in profile.values())):
            raise AuditError("profile may contain name, version and source text only.")
        config["profile"] = profile
    if "unique_together" in schema:
        keys = schema["unique_together"]
        if not isinstance(keys, list) or not keys or len(keys) > 10:
            raise AuditError("unique_together must be a list of 1 to 10 key definitions.")
        for key in keys:
            if not isinstance(key, dict) or set(key) - {"columns", "missing"} or "columns" not in key:
                raise AuditError("Each unique_together entry needs columns and optional missing policy.")
            _string_list(key["columns"], "unique_together.columns", 10)
            if len(key["columns"]) < 2:
                raise AuditError("A composite key needs at least two columns.")
            for column in key["columns"]:
                _referenced(columns, column, "unique_together")
            if key.get("missing", "report") not in {"report", "skip"}:
                raise AuditError("missing must be report or skip.")
        config["unique_together"] = keys
    if "group_by" in schema:
        group = schema["group_by"]
        if not isinstance(group, str) or "allowed" not in columns.get(group, {}):
            raise AuditError("group_by must name a configured column with an allowed list.")
        config["group_by"] = group
    return config


def _referenced(columns, other, owner):
    if not isinstance(other, str) or other not in columns or other == owner:
        raise AuditError("A rule refers to a column that is not configured.")
    return columns[other]


def _year_or_date(kind, value):
    """Parse a value for date-order comparison; None when it does not parse."""
    try:
        if kind == "year":
            return int(value) if re.fullmatch(r"[0-9]{4}", value) else None
        parsed = date.fromisoformat(value)
        return parsed if parsed.isoformat() == value else None
    except ValueError:
        return None


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
    severity_counts: Counter = Counter({ERROR: 0, WARNING: 0})
    affected: set[int] = set()
    total = 0

    def add(rule: str, row: int, column: str | None, message: str, severity: str | None = None):
        nonlocal total
        severity = severity or RULE_SEVERITY[rule]
        total += 1
        counts[rule] += 1
        severity_counts[severity] += 1
        if row > 1:
            affected.add(row)
        if len(issues) < MAX_ISSUES:
            issues.append({"rule": rule, "severity": severity, "row": row, "column": column, "message": message})

    def finish(header, rows, complete, extra=None):
        return _report(text, config, header, rows, issues, counts, severity_counts, total, affected, complete, extra or {})

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
            return finish(header, 0, False)
        rules_by_column = config["columns"]
        for name, rules in rules_by_column.items():
            if name not in header:
                if rules.get("required"):
                    add("missing_column", 1, name, "Required column is absent from the CSV header.", ERROR)
                else:
                    add("missing_column", 1, name, "Optional configured column is absent; its checks were not run.", WARNING)
        unique_seen: dict[str, set[str]] = {name: set() for name, rules in rules_by_column.items() if rules.get("unique")}
        key_defs = config.get("unique_together", [])
        key_state = [{"columns": k["columns"], "missing": k.get("missing", "report"),
                      "checked": all(c in header for c in k["columns"]), "records_keyed": 0,
                      "records_incomplete": 0, "duplicates": 0, "seen": {}} for k in key_defs]
        fill = {name: Counter() for name in header}
        group_column = config.get("group_by")
        group_values = set(rules_by_column.get(group_column, {}).get("allowed", []))
        groups: dict[str, dict] = {}
        considered = 0
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
            considered += 1
            trimmed = {}
            for name, raw in zip(header, values):
                rules = rules_by_column.get(name, {})
                value = raw.strip()
                trimmed[name] = value
                if raw != value:
                    add("whitespace", row_number, name, "Leading or trailing whitespace; review before trimming.")
                if not value:
                    fill[name]["blank"] += 1
                    if rules.get("required"):
                        add("required", row_number, name, "Required value is blank.")
                    continue
                if value in rules.get("sentinels", []):
                    fill[name]["placeholder"] += 1
                    add("sentinel", row_number, name, "Configured placeholder value; check source documentation.")
                    continue
                fill[name]["filled"] += 1
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
                    elif kind in {"date", "year"}:
                        # Strict ISO calendar date or four-digit year, not a timestamp or compact date.
                        if _year_or_date(kind, value) is None:
                            raise ValueError
                    if kind in {"integer", "number"}:
                        if "min" in rules and numeric < rules["min"] or "max" in rules and numeric > rules["max"]:
                            add("out_of_range", row_number, name, "Value falls outside configured inclusive bounds.")
                except (ValueError, OverflowError):
                    add("invalid_type", row_number, name, f"Expected {kind}; review the source value.")
                if "allowed" in rules and value not in rules["allowed"]:
                    add("not_allowed", row_number, name, "Value is not in the configured code list (exact match).",
                        rules.get("unlisted", ERROR))
                if "pattern" in rules and not re.fullmatch(rules["pattern"], value):
                    add("pattern_mismatch", row_number, name, "Value does not match the configured format.")
            for name, rules in rules_by_column.items():
                value = trimmed.get(name, "")
                if not value or value in rules.get("sentinels", []):
                    continue
                pair = rules.get("pairs_with")
                if pair and pair["column"] in trimmed and value in pair["map"]:
                    other = trimmed[pair["column"]]
                    if other and other != pair["map"][value]:
                        add("pair_mismatch", row_number, name, f"Does not correspond to {pair['column']} in the configured mapping.")
                condition = rules.get("only_if")
                if condition and condition["column"] in trimmed and trimmed[condition["column"]] not in condition["in"]:
                    add("conditional_value", row_number, name, f"Value is only expected for specific {condition['column']} values.")
                for key, later in (("not_after", True), ("not_before", False)):
                    other_name = rules.get(key)
                    if not other_name or not trimmed.get(other_name):
                        continue
                    mine = _year_or_date(rules.get("type"), value)
                    theirs = _year_or_date(rules_by_column[other_name].get("type"), trimmed[other_name])
                    if mine is None or theirs is None:
                        continue
                    if isinstance(mine, date) != isinstance(theirs, date):
                        mine, theirs = (m.year if isinstance(m, date) else m for m in (mine, theirs))
                    if (mine > theirs) if later else (mine < theirs):
                        add("date_order", row_number, name, f"{'Later' if later else 'Earlier'} than {other_name}; check both dates.")
            for state in key_state:
                if not state["checked"]:
                    continue
                parts = tuple(trimmed[c] for c in state["columns"])
                if not all(parts):
                    state["records_incomplete"] += 1
                    if state["missing"] == "report":
                        add("key_incomplete", row_number, None, f"Key {'+'.join(state['columns'])} has a blank component.")
                    continue
                state["records_keyed"] += 1
                if parts in state["seen"]:
                    state["duplicates"] += 1
                    add("duplicate_key", row_number, None,
                        f"Same {'+'.join(state['columns'])} combination as record {state['seen'][parts]}.")
                else:
                    state["seen"][parts] = row_number
            if group_column and group_column in trimmed:
                value = trimmed[group_column]
                label = value if value in group_values else "(blank)" if not value else "(unlisted value)"
                group = groups.setdefault(label, {"records": 0, "filled": Counter()})
                group["records"] += 1
                for name in header:
                    if trimmed[name] and trimmed[name] not in rules_by_column.get(name, {}).get("sentinels", []):
                        group["filled"][name] += 1
        extra = {"completeness": {
            "records_considered": considered,
            "note": "Counts well-formed records. Blank optional values are not findings.",
            "columns": {name: {"filled": fill[name]["filled"], "blank": fill[name]["blank"],
                               "placeholder": fill[name]["placeholder"],
                               "required": bool(rules_by_column.get(name, {}).get("required"))} for name in header}}}
        if key_state:
            extra["keys"] = [{k: v for k, v in state.items() if k != "seen"} for state in key_state]
        if group_column:
            extra["completeness_by_group"] = {
                "column": group_column,
                "note": "Group labels come from the configured code list, never from unlisted cell values.",
                "groups": {label: {"records": g["records"], "filled": {n: g["filled"][n] for n in header}}
                           for label, g in sorted(groups.items())}}
        return finish(header, row_count, True, extra)
    except csv.Error as exc:
        raise AuditError("Malformed CSV or field exceeds the parser limit.") from exc


def _report(text, config, header, rows, issues, counts, severity_counts, total, affected, complete, extra):
    report = {
        "report_version": 1,
        "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "schema_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
        "columns": header,
        "row_count": rows,
        "complete": complete,
        "valid": complete and total == 0,
        "error_free": complete and severity_counts[ERROR] == 0,
        "issue_count": total,
        "error_count": severity_counts[ERROR],
        "warning_count": severity_counts[WARNING],
        "affected_rows": len(affected),
        "counts_by_rule": dict(sorted(counts.items())),
        "counts_by_severity": {ERROR: severity_counts[ERROR], WARNING: severity_counts[WARNING]},
        "issues": issues,
        "examples_truncated": total > len(issues),
        "note": "Passing these configured checks does not establish accuracy or fitness for use.",
    }
    if "profile" in config:
        report["profile"] = config["profile"]
    report.update(extra)
    return report


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
            **({"severity_delta": {k: after["counts_by_severity"][k] - before["counts_by_severity"][k] for k in (ERROR, WARNING)}}
               if "counts_by_severity" in before and "counts_by_severity" in after else {}),
            "note": "Negative means fewer findings, not proof that particular records were fixed."}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Audit a local UTF-8 CSV without uploading or modifying it.")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--schema", type=Path)
    parser.add_argument("--output", type=Path, help="Write a JSON report instead of stdout.")
    parser.add_argument("--baseline", type=Path, help="Compare with a previous JSON report using the same schema.")
    parser.add_argument("--fail-on", choices=["any", "error"], default="any",
                        help="Exit 1 on any finding (default) or only on errors; warnings are quality observations.")
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
        return 0 if report["valid" if args.fail_on == "any" else "error_free"] else 1
    except (AuditError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"csv-triage: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
