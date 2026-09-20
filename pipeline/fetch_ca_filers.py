#!/usr/bin/env python3
"""Download California CAL-ACCESS's per-filing cover-page table
(CVR_CAMPAIGN_DISCLOSURE_CD.TSV) and reduce it to a FILING_ID -> filer
identity lookup.

fetch_ca.py's EXPN_CD.TSV (itemized expenditures) leaves CMTE_ID blank
on nearly all rows -- CAL-ACCESS's real filer identity for an
expenditure lives on the filing's own cover page, keyed by FILING_ID,
not on the expenditure line item itself. This script fetches that
much smaller table (~222MB uncompressed vs. EXPN's ~3GB) using the
same HTTP-range-request approach as fetch_ca.py, and writes
data/raw/ca/filer_lookup.json: {filing_id: {filer_id, filer_name}}.

filer_name prefers CAND_NAML (the candidate's own name, when the
filer is a candidate-controlled committee) since that's the
human-readable identity voters would recognize; falls back to
FILER_NAML (the committee's registered name) for PAC/party/
ballot-measure filers with no candidate.
"""
from __future__ import annotations

import csv
import io
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_ca import ZIP_URL, HttpRangeFile  # noqa: E402

ENTRY_NAME = "CalAccess/DATA/CVR_CAMPAIGN_DISCLOSURE_CD.TSV"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "ca"


def _name(row: dict) -> str:
    cand_first = (row.get("CAND_NAMF") or "").strip()
    cand_last = (row.get("CAND_NAML") or "").strip()
    if cand_last:
        return f"{cand_first} {cand_last}".strip()
    return (row.get("FILER_NAML") or "").strip()


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / "filer_lookup.json"

    print(f"Opening remote zip central directory: {ZIP_URL}")
    remote = HttpRangeFile(ZIP_URL)
    zf = zipfile.ZipFile(remote)
    info = zf.getinfo(ENTRY_NAME)
    print(f"  {ENTRY_NAME}: {info.file_size:,} bytes uncompressed, {info.compress_size:,} compressed")

    lookup: dict[str, dict] = {}
    total = 0
    with zf.open(ENTRY_NAME) as raw_entry:
        text_stream = io.TextIOWrapper(raw_entry, encoding="utf-8", errors="replace", newline="")
        reader = csv.DictReader(text_stream, delimiter="\t")
        for row in reader:
            total += 1
            filing_id = (row.get("FILING_ID") or "").strip()
            if not filing_id:
                continue
            name = _name(row)
            if not name:
                continue
            # Later amendments overwrite earlier ones for the same
            # FILING_ID -- last-row-wins is fine here since the table
            # isn't guaranteed amendment-ordered and a filer's own name
            # essentially never changes between amendments of the same
            # filing.
            lookup[filing_id] = {
                "filer_id": (row.get("FILER_ID") or "").strip(),
                "filer_name": name,
            }
            if total % 200000 == 0:
                print(f"  ...{total:,} rows scanned, {len(lookup):,} filings resolved so far", file=sys.stderr)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(lookup, f)

    print(f"{total:,} rows scanned, {len(lookup):,} filings resolved -> {out_path}")


if __name__ == "__main__":
    main()
