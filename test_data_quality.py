import csv
import tempfile
import unittest
from pathlib import Path
from data_quality import FIELDS, normalize, process, read_input, render_report, run, safe_cell
from demo import fixture


def valid(**changes):
    return {**dict(zip(FIELDS, ["C00001", "Demo Contact", "demo@example.test", "US", "2025-01-01", "basic"])), **changes}


class DataQualityTests(unittest.TestCase):
    def test_fixture_conservation(self):
        r = process(fixture())
        self.assertEqual(r["input_rows"], 1180)
        self.assertEqual(r["counts"], {"accepted": 980, "duplicate": 100, "quarantined": 100})
    def test_normalization(self):
        r, e = normalize(valid(name=" Demo   Contact ", country=" united kingdom ", email="DEMO@EXAMPLE.TEST"))
        self.assertEqual((r["name"], r["country"], r["email"], e), ("Demo Contact", "GB", "demo@example.test", []))
    def test_exact_duplicate_only(self):
        self.assertEqual(process([valid(), valid()])["counts"]["duplicate"], 1)
    def test_conflicts_quarantine_all(self):
        self.assertEqual(process([valid(), valid(plan="pro")])["counts"]["quarantined"], 2)
    def test_invalid_peer_holds_other_record(self):
        self.assertEqual(process([valid(), valid(email="bad")])["counts"]["quarantined"], 2)
    def test_missing_id(self):
        self.assertEqual(process([valid(record_id="")])["counts"]["accepted"], 0)
    def test_dates(self):
        for d in ["02/03/2025", "2025-02-29", "2025-1-1", ""]:
            self.assertIn("invalid_iso_date", normalize(valid(joined_on=d))[1])
        self.assertEqual(normalize(valid(joined_on="2024-02-29"))[1], [])
    def test_unknown_country(self):
        self.assertIn("unknown_country", normalize(valid(country="Mars"))[1])
    def test_unknown_plan(self):
        self.assertIn("unknown_plan", normalize(valid(plan="premium"))[1])
    def test_no_input_mutation(self):
        row = valid(email=" DEMO@EXAMPLE.TEST ")
        process([row])
        self.assertEqual(row["email"], " DEMO@EXAMPLE.TEST ")
    def test_stable_reprocessing(self):
        cleaned = process(fixture())["accepted"]
        self.assertEqual(process(cleaned)["accepted"], cleaned)
    def test_formula_neutralization(self):
        for value in ["=1+1", "+1", "-1", "@SUM(A1)", "  =1", "\t123"]:
            self.assertTrue(safe_cell(value).startswith("'"))
    def test_html_escaped(self):
        report = render_report(process([valid(email='<script>alert(1)</script>')]))
        self.assertNotIn('<script>alert(1)</script>', report)
        self.assertIn('&lt;script&gt;', report)
    def test_empty_input(self):
        self.assertEqual(process([])["counts"], {"accepted": 0, "duplicate": 0, "quarantined": 0})
    def test_reject_wrong_columns(self):
        with self.assertRaises(ValueError):
            process([{"record_id": "C00001"}])
    def test_reject_duplicate_header(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "bad.csv"
            p.write_text("record_id,record_id,email,country,joined_on,plan\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_input(p)
    def test_outputs_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as t:
            p, out = Path(t) / "in.csv", Path(t) / "out"
            with p.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerow(valid())
            run(p, out)
            self.assertTrue((out / "report.html").is_file())
            before = (out / "evidence.json").read_bytes()
            with self.assertRaises(FileExistsError):
                run(p, out)
            self.assertEqual((out / "evidence.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
