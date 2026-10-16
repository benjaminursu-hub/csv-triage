"""Tests for the Open Repair helper scripts in tools/. Synthetic data only."""
import contextlib
import csv
import io
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parent / "tools"))
import ords_provider_summary  # noqa: E402
import ords_sample  # noqa: E402

HEADER = ["id", "data_provider", "brand", "repair_status", "repair_barrier_if_end_of_life", "problem"]
ROWS = [
    ["a_1", "A", "Unknown", "Fixed", "", "PRIVATE TEXT one"],
    ["a_2", "A", "Acme", "End of life", "Lack of equipment", ""],
    ["a_3", "A", "Acme", "End of life", "", "PRIVATE TEXT three"],
    ["b_1", "B", "Unknown", "3", "", ""],
    ["b_2", "B", "Beta", "Repairable", "", ""],
]


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.source = Path(self.temp.name) / "agg.csv"
        with self.source.open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerows([HEADER, *ROWS])

    def tearDown(self):
        self.temp.cleanup()

    def read(self, path):
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.reader(handle))

    def test_sample_keeps_first_records_per_provider_in_order(self):
        target = Path(self.temp.name) / "sample.csv"
        counts = ords_sample.make_sample(self.source, target, per_provider=2, partner_ids=False)
        self.assertEqual(counts, {"A": 2, "B": 2})
        self.assertEqual([row[0] for row in self.read(target)], ["id", "a_1", "a_2", "b_1", "b_2"])

    def test_partner_ids_strip_only_the_prefix(self):
        target = Path(self.temp.name) / "partner.csv"
        ords_sample.make_sample(self.source, target, per_provider=1, partner_ids=True)
        rows = self.read(target)
        self.assertEqual([row[0] for row in rows[1:]], ["1", "1"])
        self.assertEqual(rows[1][1:], ROWS[0][1:])

    def test_sample_refuses_overwriting_its_source(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            ords_sample.main([str(self.source), str(self.source)])

    def test_summary_counts_per_provider(self):
        stats = ords_provider_summary.summarise(self.source)
        self.assertEqual(dict(stats["A"]), {"records": 3, "no_problem": 1, "brand_unknown": 1, "end_of_life": 2, "with_barrier": 1})
        self.assertEqual(dict(stats["B"]), {"records": 2, "no_problem": 2, "brand_unknown": 1, "end_of_life": 1, "with_barrier": 0})

    def test_summary_prints_counts_never_cell_values(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(ords_provider_summary.main([str(self.source)]), 0)
        self.assertIn("| A | 3 | 1 (33%) | 33% | 1 of 2 (50%) |", out.getvalue())
        self.assertNotIn("PRIVATE TEXT", out.getvalue())
        self.assertNotIn("Acme", out.getvalue())

    def test_summary_rejects_non_ords_file(self):
        other = Path(self.temp.name) / "other.csv"
        other.write_text("a,b\n1,2\n", encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ords_provider_summary.main([str(other)]), 2)


if __name__ == "__main__":
    unittest.main()
