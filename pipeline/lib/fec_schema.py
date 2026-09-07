"""Helpers for resolving FEC bulk-data column layouts.

The FEC publishes bulk data files as headerless, pipe-delimited text next to
a separate one-line CSV "header file" that names the columns for that
release. Column sets have shifted slightly across cycles, so rather than
hardcoding column names we fetch the matching header file at run time and
use it verbatim. This keeps the pipeline correct even if the FEC adds or
reorders columns in a future cycle.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

import requests

HEADER_BASE = "https://www.fec.gov/files/bulk-downloads/data_dictionaries"

HEADER_FILES = {
    "cn": "cn_header_file.csv",
    "ccl": "ccl_header_file.csv",
    "cm": "cm_header_file.csv",
    "oppexp": "oppexp_header_file.csv",
    "weball": "weball_header_file.csv",
}


def fetch_header(dataset: str, cache_dir: Path, session: requests.Session) -> list[str]:
    """Return the column names for a dataset ('cn', 'ccl', 'oppexp', 'weball')."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{dataset}_header.csv"
    if cache_path.exists():
        text = cache_path.read_text()
    else:
        url = f"{HEADER_BASE}/{HEADER_FILES[dataset]}"
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
        text = resp.text
        cache_path.write_text(text)
    row = next(csv.reader(io.StringIO(text)))
    return [c.strip() for c in row]
