"""Deterministic, inspectable CRM-data cleaning. Python 3.10+, standard library."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

FIELDS = ("record_id", "name", "email", "country", "joined_on", "plan")
COUNTRIES = {"us": "US", "usa": "US", "united states": "US", "uk": "GB",
             "gb": "GB", "united kingdom": "GB", "cn": "CN", "china": "CN",
             "ae": "AE", "uae": "AE", "united arab emirates": "AE"}
PLANS = {"basic", "pro", "enterprise"}


def normalize(row: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Apply an explicit demo policy. Do not guess missing values or fuzzy-merge."""
    cleaned = {k: unicodedata.normalize("NFKC", row.get(k, "")).strip() for k in FIELDS}
    errors = []
    cleaned["record_id"] = cleaned["record_id"].upper()
    cleaned["name"] = " ".join(cleaned["name"].split())
    # This project's documented policy treats email addresses case-insensitively.
    cleaned["email"] = cleaned["email"].lower()
    cleaned["country"] = COUNTRIES.get(cleaned["country"].lower(), cleaned["country"])
    cleaned["plan"] = cleaned["plan"].lower()
    if not re.fullmatch(r"C\d{5}", cleaned["record_id"]):
        errors.append("invalid_record_id")
    if not cleaned["name"]:
        errors.append("missing_name")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", cleaned["email"]):
        errors.append("invalid_email")
    if cleaned["country"] not in set(COUNTRIES.values()):
        errors.append("unknown_country")
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned["joined_on"]):
            raise ValueError("ISO date required")
        date.fromisoformat(cleaned["joined_on"])
    except ValueError:
        errors.append("invalid_iso_date")
    if cleaned["plan"] not in PLANS:
        errors.append("unknown_plan")
    return cleaned, errors


def process(rows: list[dict[str, str]]) -> dict:
    ledger = []
    groups = defaultdict(list)
    for line, raw in enumerate(rows, start=2):
        if set(raw) != set(FIELDS) or any(not isinstance(v, str) for v in raw.values()):
            raise ValueError("Input rows must have exactly the documented string-valued columns")
        cleaned, errors = normalize(raw)
        item = {"source_line": line, "raw": dict(raw), "cleaned": cleaned,
                "status": "quarantined", "reasons": errors,
                "normalized_fields": [k for k in FIELDS if raw[k] != cleaned[k]]}
        ledger.append(item)
        if "invalid_record_id" not in errors:
            groups[cleaned["record_id"]].append(item)
    for members in groups.values():
        if any(m["reasons"] for m in members):
            for m in members:
                if not m["reasons"]:
                    m["reasons"] = ["same_id_has_invalid_record"]
            continue
        variants = {tuple(m["cleaned"][k] for k in FIELDS) for m in members}
        if len(variants) != 1:
            for m in members:
                m["reasons"] = ["conflicting_record_id"]
            continue
        members[0]["status"] = "accepted"
        for m in members[1:]:
            m["status"] = "duplicate"
            m["reasons"] = ["exact_normalized_duplicate"]
            m["duplicate_of_line"] = members[0]["source_line"]
    counts = Counter(m["status"] for m in ledger)
    accepted = [m["cleaned"] for m in ledger if m["status"] == "accepted"]
    assert len({r["record_id"] for r in accepted}) == len(accepted)
    assert sum(counts.values()) == len(rows)
    return {"policy_version": "1.0", "input_rows": len(rows),
            "counts": {s: counts[s] for s in ("accepted", "duplicate", "quarantined")},
            "normalized_rows": sum(bool(m["normalized_fields"]) for m in ledger),
            "accepted": accepted, "ledger": ledger}


def read_input(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or len(reader.fieldnames) != len(FIELDS) or set(reader.fieldnames) != set(FIELDS):
            raise ValueError("CSV header must contain each of the six documented columns exactly once")
        return list(reader)


def safe_cell(value: object) -> str:
    text = str(value)
    # Preserve exact data in JSON. Human-facing CSV neutralizes formula prefixes.
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r")) else text


def write_csv(path: Path, fields: tuple | list, rows: list[dict]) -> None:
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: safe_cell(row.get(k, "")) for k in fields} for row in rows)


def render_report(result: dict) -> str:
    counts = result["counts"]
    table_rows = []
    for m in result["ledger"]:
        values = [m["source_line"], m["raw"]["record_id"], m["raw"]["email"],
                  m["cleaned"]["email"], m["status"], ", ".join(m["reasons"])]
        cells = "".join("<td>" + html.escape(str(v)) + "</td>" for v in values)
        table_rows.append('<tr data-status="' + m["status"] + '">' + cells + '</tr>')
    cards = "".join(f'<div class="metric"><span>{label}</span><strong>{n:,}</strong></div>' for label, n in
                    [("Input records", result["input_rows"]), ("Accepted", counts["accepted"]),
                     ("Duplicates", counts["duplicate"]), ("Needs review", counts["quarantined"])])
    return """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Data Quality Workbench - synthetic demonstration</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f6f8fb;color:#182338;font:15px/1.6 system-ui,sans-serif}main{max-width:1280px;margin:auto;padding:40px 28px}.eyebrow{color:#4263b1;font-weight:650;font-size:12px;letter-spacing:.12em}h1{font-size:38px;line-height:1.15;margin:14px 0}p{max-width:850px;color:#52617a}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:28px 0}.metric{background:white;padding:20px;border:1px solid #dce3ef;border-radius:10px}.metric span{display:block;color:#52617a}.metric strong{font-size:32px}section{background:white;border:1px solid #dce3ef;border-radius:10px;padding:20px;margin-top:22px}label{font-weight:600}select{margin-left:12px;padding:8px 12px;font:inherit;border:1px solid #cbd5e1;border-radius:6px}.scroll{overflow-x:auto;max-height:540px;margin-top:18px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;padding:10px 12px;border-bottom:1px solid #e7ecf4;white-space:nowrap}th{background:#eff3fa;position:sticky;top:0}tr[data-status=quarantined] td:last-child{color:#9f450d}.note{font-size:13px;color:#53647f}@media(max-width:700px){main{padding:24px 16px}h1{font-size:30px}.metrics{grid-template-columns:1fr 1fr}}</style>
<main><div class="eyebrow">INDEPENDENT DEMO / SYNTHETIC DATA</div><h1>Data Quality Workbench</h1>
<p>From a messy export to traceable, import-ready records. Exact duplicates are removed; conflicting IDs and invalid fields are held for review, never silently guessed.</p>
<div class="metrics">""" + cards + """</div><p class="note">Reconciliation: every source row has exactly one outcome. This report demonstrates a documented cleaning policy, not verification of real customer identities.</p>
<section><label for="status">Row-level evidence</label><select id="status"><option value="all">All outcomes</option><option value="accepted">Accepted</option><option value="duplicate">Duplicates</option><option value="quarantined">Needs review</option></select><span id="shown" aria-live="polite"></span>
<div class="scroll"><table><thead><tr><th>Source line</th><th>Record ID</th><th>Original email</th><th>Normalized email</th><th>Outcome</th><th>Reason</th></tr></thead><tbody>""" + "".join(table_rows) + """</tbody></table></div></section>
<section><h2>Policy and limits</h2><p>Countries use an explicit US/GB/CN/AE mapping. Dates must be ISO YYYY-MM-DD. Email syntax is checked, not mailbox ownership or deliverability. No fuzzy entity matching, external enrichment or live CRM writes. JSON preserves original values; CSV exports neutralize spreadsheet-formula prefixes.</p></section></main>
<script>const filter=document.getElementById('status');const rows=Array.from(document.querySelectorAll('tbody tr'));function update(){let n=0;rows.forEach(r=>{r.hidden=filter.value!=='all'&&r.dataset.status!==filter.value;if(!r.hidden)n++});document.getElementById('shown').textContent='  '+n.toLocaleString()+' rows';}filter.addEventListener('change',update);update();</script></html>"""


def run(source: Path, output: Path) -> dict:
    result = process(read_input(source))
    result["input_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    output.mkdir(parents=True, exist_ok=False)
    (output / "evidence.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    write_csv(output / "cleaned.csv", FIELDS, result["accepted"])
    ledger_rows = [{"source_line": m["source_line"], **m["raw"], "outcome": m["status"],
                    "reason": "; ".join(m["reasons"])} for m in result["ledger"]]
    write_csv(output / "row_ledger.csv", ["source_line", *FIELDS, "outcome", "reason"], ledger_rows)
    (output / "report.html").write_text(render_report(result), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", required=True, type=Path, help="New directory; existing outputs are never overwritten")
    args = parser.parse_args()
    try:
        result = run(args.input, args.output)
    except (OSError, ValueError, csv.Error) as exc:
        parser.exit(2, f"Data-quality run stopped: {exc}\n")
    print(json.dumps({"input_rows": result["input_rows"], **result["counts"]}))


if __name__ == "__main__":
    main()
