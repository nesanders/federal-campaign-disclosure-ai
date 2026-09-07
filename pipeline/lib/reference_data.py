"""Load FEC reference tables (candidate master, committee-candidate linkage,
committee master) and the congress-legislators birthdate crosswalk."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import requests

from .fec_schema import fetch_header

ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = ROOT / "data" / "raw"

PARTY_MAP = {
    "DEM": "Democratic",
    "REP": "Republican",
    "DFL": "Democratic",  # MN Democratic-Farmer-Labor
    "IND": "Independent",
    "LIB": "Libertarian",
    "GRE": "Green",
}


def normalize_party(code: str) -> str:
    code = (code or "").strip().upper()
    return PARTY_MAP.get(code, "Other" if code else "Unknown")


def _read_pipe_file(path: Path, header: list[str]) -> list[dict]:
    rows = []
    with open(path, encoding="latin-1", errors="replace", newline="") as f:
        for line in csv.reader(f, delimiter="|"):
            if len(line) < len(header):
                continue
            rows.append(dict(zip(header, line[: len(header)])))
    return rows


def load_candidate_master(cycle: int, session: requests.Session) -> dict[str, dict]:
    """CAND_ID -> {party, office, ici, name, state, district}."""
    header = fetch_header("cn", RAW_DIR / "_headers", session)
    path = next((RAW_DIR / str(cycle)).glob("cn*.txt"))
    out = {}
    for row in _read_pipe_file(path, header):
        out[row["CAND_ID"]] = {
            "name": row.get("CAND_NAME", ""),
            "party": normalize_party(row.get("CAND_PTY_AFFILIATION", "")),
            "office": row.get("CAND_OFFICE", ""),  # H / S / P
            "district": row.get("CAND_OFFICE_DISTRICT", ""),
            "state": row.get("CAND_OFFICE_ST", ""),
            "ici": row.get("CAND_ICI", ""),  # I / C / O
        }
    return out


def load_committee_candidate_linkage(cycle: int, session: requests.Session) -> dict[str, str]:
    """CMTE_ID -> CAND_ID (prefers principal-committee designation 'P')."""
    header = fetch_header("ccl", RAW_DIR / "_headers", session)
    path = next((RAW_DIR / str(cycle)).glob("ccl*.txt"))
    best: dict[str, tuple[str, str]] = {}
    for row in _read_pipe_file(path, header):
        cmte_id = row["CMTE_ID"]
        dsgn = row.get("CMTE_DSGN", "")
        cand_id = row["CAND_ID"]
        # Prefer principal committee links; keep first-seen otherwise.
        if cmte_id not in best or dsgn == "P":
            best[cmte_id] = (cand_id, dsgn)
    return {cmte_id: cand_id for cmte_id, (cand_id, _) in best.items()}


def load_committee_master(cycle: int, session: requests.Session) -> dict[str, dict]:
    """CMTE_ID -> {name, type, party} for committees (PACs, parties, etc.)."""
    header = fetch_header("cm", RAW_DIR / "_headers", session)
    path = next((RAW_DIR / str(cycle)).glob("cm*.txt"))
    out = {}
    for row in _read_pipe_file(path, header):
        out[row["CMTE_ID"]] = {
            "name": row.get("CMTE_NM", ""),
            "type": row.get("CMTE_TP", ""),
            "party": normalize_party(row.get("CMTE_PTY_AFFILIATION", "")),
        }
    return out


def load_legislator_birthdates() -> dict[str, str]:
    """FEC candidate ID -> ISO birthdate string, from congress-legislators."""
    out = {}
    leg_dir = RAW_DIR / "legislators"
    for fname in ("legislators-current.json", "legislators-historical.json"):
        path = leg_dir / fname
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            people = json.load(f)
        for person in people:
            birthday = person.get("bio", {}).get("birthday")
            fec_ids = person.get("id", {}).get("fec", [])
            if not birthday or not fec_ids:
                continue
            for fec_id in fec_ids:
                out[fec_id] = birthday
    return out


def age_bucket(age: int | None) -> str:
    if age is None:
        return "Unknown"
    if age < 40:
        return "Under 40"
    if age < 50:
        return "40-49"
    if age < 60:
        return "50-59"
    if age < 70:
        return "60-69"
    return "70+"
