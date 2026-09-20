#!/usr/bin/env python3
"""Download California CAL-ACCESS itemized expenditure records (the EXPN
table -- Form 460 Schedules D/E/G, Form 450 Part 5, Form 461 Part 5, Form
465 Part 3) from the Secretary of State's daily bulk export.

The full export (campaignfinance.cdn.sos.ca.gov/dbwebexport.zip) is a
1.5+ GB zip of the entire CAL-ACCESS database, 130 tables, of which only
one -- CalAccess/DATA/EXPN_CD.TSV, itself ~3 GB uncompressed / ~400 MB
compressed -- is relevant here. Downloading and unzipping the whole
archive would need ~5 GB of disk for no reason, so this instead:
  1. Fetches just the zip's central directory over HTTP range requests
     (confirmed the host supports `Accept-Ranges: bytes`), to find
     EXPN_CD.TSV's location without downloading anything else.
  2. Streams that one entry's compressed bytes through zipfile's own
     decompression, row by row, via a seekable HTTP-range file object
     (fetching only the ranges actually read, not the whole entry
     up front).
  3. Keeps only rows with EXPN_DATE on/after --start-date, since
     CAL-ACCESS offers no server-side date filter and the whole table
     spans back to 2000 -- filtering happens during this one sequential
     pass rather than after materializing the full 3 GB file.

Output: data/raw/ca/expn.jsonl (gitignored, like all of data/raw/) --
already filtered to the target window, one JSON object per row using the
TSV's own column names verbatim (PAYEE_NAML, EXPN_DSCR, CMTE_ID, etc.),
left for parse_ca.py to normalize.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import zipfile
from pathlib import Path

import requests

ZIP_URL = "https://campaignfinance.cdn.sos.ca.gov/dbwebexport.zip"
ENTRY_NAME = "CalAccess/DATA/EXPN_CD.TSV"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "ca"

HEADERS = {"User-Agent": "federal-campaign-disclosure-ai/1.0 (research pipeline)"}


MIN_FETCH = 8 * 1024 * 1024  # 8 MB per HTTP request, regardless of how
# small a read zipfile's own DEFLATE decompressor asks for -- its
# ZipExtFile reads in small chunks internally (tens of KB at a time),
# which without this read-ahead buffer turns into one HTTP round trip
# per chunk: tens of thousands of requests to pull ~400 MB, each paying
# full request latency for a few KB of payload. A local buffer answers
# most read() calls for free and only refills over the network every
# 8 MB, cutting the request count by roughly two orders of magnitude.


class HttpRangeFile:
    """A minimal seekable, buffered file-like object over HTTP range
    requests, so zipfile can read a remote zip's central directory and
    then decompress one entry without downloading the whole archive.
    """

    def __init__(self, url: str):
        self.url = url
        self.session = requests.Session()
        resp = self.session.head(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        self.size = int(resp.headers["content-length"])
        self.pos = 0
        self._buf = b""
        self._buf_start = 0  # absolute file offset of self._buf[0]

    def seekable(self) -> bool:
        return True

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self.pos = offset
        elif whence == 1:
            self.pos += offset
        elif whence == 2:
            self.pos = self.size + offset
        return self.pos

    def tell(self) -> int:
        return self.pos

    def _fill_buffer(self, min_len: int) -> None:
        end = min(self.pos + max(min_len, MIN_FETCH) - 1, self.size - 1)
        resp = self.session.get(self.url, headers={**HEADERS, "Range": f"bytes={self.pos}-{end}"}, timeout=60)
        resp.raise_for_status()
        self._buf = resp.content
        self._buf_start = self.pos

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = self.size - self.pos

        buf_end = self._buf_start + len(self._buf)
        # Buffer doesn't cover the current position (a seek jumped
        # elsewhere, or it's empty) -- refetch from here.
        if self.pos < self._buf_start or self.pos >= buf_end:
            self._fill_buffer(n)
            buf_end = self._buf_start + len(self._buf)

        start_in_buf = self.pos - self._buf_start
        available = self._buf[start_in_buf : start_in_buf + n]
        # Buffer had enough left to satisfy this read in full.
        if len(available) >= n or buf_end >= self.size:
            self.pos += len(available)
            return available

        # Buffer ran out mid-read (near its end, asked for more than
        # remained) -- top up and concatenate rather than returning a
        # short read, since zipfile expects read(n) to return exactly n
        # bytes except at true EOF.
        self.pos += len(available)
        self._fill_buffer(n - len(available))
        rest = self.read(n - len(available))
        return available + rest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start-date",
        default="2023-01-01",
        help="Keep only rows on/after this date (default: 2023-01-01, covering the 2024 and 2026 cycles)",
    )
    args = parser.parse_args()
    start_date = args.start_date

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / "expn.jsonl"

    print(f"Opening remote zip central directory: {ZIP_URL}")
    remote = HttpRangeFile(ZIP_URL)
    zf = zipfile.ZipFile(remote)
    info = zf.getinfo(ENTRY_NAME)
    print(f"  {ENTRY_NAME}: {info.file_size:,} bytes uncompressed, {info.compress_size:,} compressed")

    kept = 0
    total = 0
    with zf.open(ENTRY_NAME) as raw_entry, open(out_path, "w", encoding="utf-8") as f_out:
        text_stream = io.TextIOWrapper(raw_entry, encoding="utf-8", errors="replace", newline="")
        reader = csv.DictReader(text_stream, delimiter="\t")
        for row in reader:
            total += 1
            date = (row.get("EXPN_DATE") or "").strip()
            # CAL-ACCESS dates are "M/D/YYYY H:MM:SS AM/PM" -- compare the
            # year portion only (cheap, and this pipeline's date window
            # is always a full-year boundary anyway).
            year = None
            if date:
                try:
                    year = int(date.split("/")[-1].split(" ")[0])
                except (ValueError, IndexError):
                    year = None
            if year is not None and year >= int(start_date[:4]):
                f_out.write(json.dumps(row) + "\n")
                kept += 1
            if total % 200000 == 0:
                print(f"  ...{total:,} rows scanned, {kept:,} kept so far", file=sys.stderr)

    print(f"{total:,} rows scanned, {kept:,} kept (>= {start_date}) -> {out_path}")


if __name__ == "__main__":
    main()
