"""Generate a fully synthetic 1,180-row fixture and process it."""
import argparse
import csv
import json
from pathlib import Path
from data_quality import FIELDS, run


def fixture():
    rows = []
    countries = [" USA ", "United Kingdom", "China", "UAE"]
    for i in range(1, 1001):
        rows.append(dict(zip(FIELDS, [f" c{i:05d} ", f" Demo   Contact {i:04d} ",
                    f" CONTACT{i:04d}@EXAMPLE.TEST ", countries[i % 4],
                    f"2025-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}", [" Basic ", "PRO", "enterprise"][i % 3]])))
    rows.extend(dict(r) for r in rows[100:200])
    for i in range(20):
        rows.append({**rows[i], "plan": "basic" if rows[i]["plan"].strip().lower() != "basic" else "pro"})
    for i in range(60):
        r = {**rows[250 + i], "record_id": f"C{2001+i:05d}"}
        r[["record_id", "email", "country"][i // 20]] = ["", "not-an-email", "Unknownland"][i // 20]
        rows.append(r)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("demo-output"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = args.output / "synthetic_input.csv"
    with source.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(fixture())
    result = run(source, args.output / "results")
    expected = {"accepted": 980, "duplicate": 100, "quarantined": 100}
    assert result["input_rows"] == 1180 and result["counts"] == expected
    print(json.dumps({"fixture": "synthetic", "expected_counts_verified": True, **result["counts"]}))


if __name__ == "__main__":
    main()
