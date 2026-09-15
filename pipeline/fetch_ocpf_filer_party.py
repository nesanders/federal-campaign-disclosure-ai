#!/usr/bin/env python3
"""Fetch each OCPF filer's party affiliation for every filer that shows up
in an AI-vendor-matched expenditure record.

OCPF's `filer/payload/{cpfId}` endpoint returns `filer.partyAffiliation`
directly -- confirmed by inspecting a real response. This is a small,
separate fetch (one call per distinct filer, not per record -- a few dozen
filers even when hundreds of expenditure records match) so the Massachusetts
tab can compute the same Democratic-vs-Republican spending split the
federal dashboard does per vendor.

Reads data/processed/ocpf_matches.csv for its distinct filer_cpf_id values
and writes data/processed/ocpf_filer_party.csv (filer_cpf_id, party).
"""
from __future__ import annotations

import csv
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
API_BASE = "https://api.ocpf.us/filer/payload"

OUT_FIELDS = ["filer_cpf_id", "party"]


def distinct_filer_ids() -> set[str]:
    path = PROCESSED_DIR / "ocpf_matches.csv"
    ids: set[str] = set()
    for row in csv.DictReader(open(path, encoding="utf-8")):
        cpf_id = row.get("filer_cpf_id")
        if cpf_id:
            ids.add(cpf_id)
    return ids


def fetch_party(cpf_id: str, session: requests.Session) -> str:
    resp = session.get(f"{API_BASE}/{cpf_id}", timeout=30)
    if resp.status_code >= 400:
        return ""
    payload = resp.json()
    return (payload.get("filer") or {}).get("partyAffiliation") or ""


def main() -> None:
    filer_ids = sorted(distinct_filer_ids(), key=lambda x: int(x))
    print(f"Fetching party affiliation for {len(filer_ids)} distinct filers...")

    session = requests.Session()
    session.headers.update({"User-Agent": "federal-campaign-disclosure-ai/1.0 (research pipeline)"})

    out_path = PROCESSED_DIR / "ocpf_filer_party.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=OUT_FIELDS)
        writer.writeheader()
        fetched = 0
        for cpf_id in filer_ids:
            party = fetch_party(cpf_id, session)
            writer.writerow({"filer_cpf_id": cpf_id, "party": party})
            fetched += 1
            time.sleep(0.05)

    print(f"Done: {fetched} filers -> {out_path}")


if __name__ == "__main__":
    main()
