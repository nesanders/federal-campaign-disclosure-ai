#!/usr/bin/env python3
"""Scrape AI-relevant signal from campaign job postings on three boards:
the DCCC's House Campaign Job Board, Campaigns & Elections' jobs archive,
and RepublicanJobs.gop's opportunities page.

This is a different kind of signal from every other fetch_*.py in this
pipeline: it isn't itemized disclosure data with a stable historical
record, it's a scrape of *currently open* postings on job boards that
remove listings once filled. There is no equivalent of "download every
filing since 2020" -- a posting seen today may be gone tomorrow, and
there's no way to retroactively see what was posted last year. Because of
that, output is **append-only**: each run merges newly-seen postings into
the existing per-source JSONL files, keyed by a stable id per posting, so
re-running this script is idempotent and never loses a posting that later
gets taken down. See planning/job-postings-plan.md for the full rationale.

Unlike every other fetch_*.py, this state lives under data/processed/,
not data/raw/: data/raw/ is gitignored and treated as an ephemeral,
always-redownloadable full dump (safe for FEC/OCPF, which never remove
old filings), but that would silently defeat the whole point of the
append-only merge here -- a GitHub Actions runner starts from a fresh
checkout every run, so anything not committed to git is lost between
runs, and job postings genuinely disappear at the source. The merged
JSONL files must be committed (see .github/workflows/refresh-data.yml)
for "append-only" to mean anything.

Sources and what each actually offers (confirmed by inspecting real
fetched HTML, not assumed):
  - DCCC (dccc.org/campaign-job-board/): title/campaign/office/date/
    location inline; full job description is a linked PDF per posting,
    fetched and text-extracted separately.
  - Campaigns & Elections (campaignsandelections.com/jobs/): title/
    company/location/type inline, plus a political-affiliation tag
    baked into the article's own CSS class. Individual job detail pages
    are Cloudflare-gated and return a bot-block page, not the posting
    body -- so C&E postings never get body_text, and are only ever
    classified on their title.
  - RepublicanJobs.gop (www.republicanjobs.gop/opportunities/): title,
    org type, location, and the *full* description (responsibilities,
    requirements, compensation) all inline in the archive page itself --
    no per-posting fetch needed, and by far the richest single source.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "data" / "processed" / "job_postings"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}


def _posting_id(source: str, *parts: str) -> str:
    raw = source + "|" + "|".join(p or "" for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _merge_jsonl(path: Path, new_records: list[dict]) -> int:
    """Append-only merge keyed by `id` -- existing records are never
    overwritten (a posting's scraped_at/first-seen date should stay the
    date it was first found, not reset every run), only new ids are added.
    """
    existing: dict[str, dict] = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                existing[rec["id"]] = rec
    added = 0
    for rec in new_records:
        if rec["id"] not in existing:
            existing[rec["id"]] = rec
            added += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rec in sorted(existing.values(), key=lambda r: r["id"]):
            f.write(json.dumps(rec) + "\n")
    return added


def fetch_dccc(session: requests.Session, fetch_pdfs: bool = True) -> list[dict]:
    url = "https://dccc.org/campaign-job-board/"
    resp = session.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    records = []
    today = time.strftime("%Y-%m-%d")
    for item in soup.find_all(class_="campaign-jobitem"):
        h3 = item.find("h3")
        link = h3.find("a") if h3 else None
        title = link.get_text(strip=True) if link else None
        href = link.get("href") if link else None
        campaign = item.find(class_="campaign-job-campaign-name")
        office = item.find(class_="campaign-job-office")
        date = item.find(class_="campaign-job-date")
        location = item.find(class_="campaign-job-location")
        if not title:
            continue

        body_text = None
        if fetch_pdfs and href and href.lower().endswith(".pdf"):
            try:
                pdf_resp = session.get(href, headers=HEADERS, timeout=30)
                pdf_resp.raise_for_status()
                tmp_path = STATE_DIR / "_tmp_dccc.pdf"
                tmp_path.write_bytes(pdf_resp.content)
                from pdfminer.high_level import extract_text

                body_text = extract_text(str(tmp_path))
                tmp_path.unlink(missing_ok=True)
            except Exception as exc:  # noqa: BLE001 - a single bad PDF shouldn't kill the run
                print(f"  [dccc] could not extract PDF text for {title!r}: {exc}", file=sys.stderr)

        records.append(
            {
                "id": _posting_id("dccc", title, campaign.get_text(strip=True) if campaign else ""),
                "source": "dccc",
                "party": "Democratic",
                "title": title,
                "org": campaign.get_text(strip=True) if campaign else None,
                "office": office.get_text(strip=True) if office else None,
                "location": location.get_text(strip=True) if location else None,
                "posted_date": date.get_text(strip=True) if date else None,
                "url": href,
                "body_text": body_text,
                "first_seen": today,
            }
        )
    return records


def fetch_campaigns_and_elections(session: requests.Session) -> list[dict]:
    url = "https://campaignsandelections.com/jobs/"
    resp = session.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    party_by_class = {"democrat": "Democratic", "republican": "Republican", "nonpartisan": "Nonpartisan"}
    today = time.strftime("%Y-%m-%d")
    records = []
    for art in soup.find_all("article", class_="ce_job"):
        classes = art.get("class", [])
        h2 = art.find(class_="entry-position")
        link = h2.find("a") if h2 else None
        title = link.get_text(strip=True) if link else None
        href = link.get("href") if link else None
        company = art.find(class_="entry-company")
        location = art.find(class_="entry-location")
        job_type = art.find(class_="entry-job-type")
        time_el = art.find(class_="entry-time")
        party = None
        for c in classes:
            for key, label in party_by_class.items():
                if c.endswith(f"political_aff-{key}"):
                    party = label
        if not title:
            continue
        records.append(
            {
                "id": _posting_id("ce", title, company.get_text(strip=True) if company else ""),
                "source": "campaigns_and_elections",
                "party": party,
                "title": title,
                "org": company.get_text(strip=True) if company else None,
                "office": None,
                "location": location.get_text(strip=True) if location else None,
                "posted_date": time_el.get_text(" ", strip=True).replace("Posted", "").strip() if time_el else None,
                "url": href,
                # Individual job pages on this site are Cloudflare-gated
                # (confirmed: a bare fetch returns a bot-block page, not
                # the posting), so body text is never available here --
                # classification for this source is title-only.
                "body_text": None,
                "first_seen": today,
            }
        )
    return records


def fetch_republicanjobs(session: requests.Session) -> list[dict]:
    url = "https://www.republicanjobs.gop/opportunities/"
    resp = session.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    today = time.strftime("%Y-%m-%d")
    records = []
    for block in soup.find_all(class_="new_job_opning_block"):
        h4 = block.find("h4")
        if not h4:
            continue
        header_text = h4.get_text(strip=True)
        # Consistent "Title | Org description | Location | #ReqID" format,
        # confirmed across a sample of the real page; defensively handles
        # a header with more or fewer than 4 parts rather than assuming
        # exactly 4.
        parts = [p.strip() for p in header_text.split("|")]
        title = parts[0] if parts else header_text
        req_id = parts[-1] if len(parts) > 1 and parts[-1].startswith("#") else None
        location = parts[-2] if req_id and len(parts) >= 3 else (parts[-1] if not req_id and len(parts) >= 2 else None)
        org = parts[1] if len(parts) > 1 else None

        detail = block.find(class_="job_opning_detail")
        body_text = detail.get_text(" ", strip=True) if detail else None

        tags = [a.get_text(strip=True) for a in block.select(".category_btn a")]

        records.append(
            {
                "id": _posting_id("gop", header_text),
                "source": "republicanjobs_gop",
                "party": "Republican",
                "title": title,
                "org": org,
                "office": None,
                "location": location,
                "posted_date": None,  # not exposed per-posting on this board
                "url": url,
                "body_text": body_text,
                "tags": tags,
                "req_id": req_id,
                "first_seen": today,
            }
        )
    return records


def main() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    total_added = 0
    for name, fetch_fn in (
        ("dccc", fetch_dccc),
        ("campaigns_and_elections", fetch_campaigns_and_elections),
        ("republicanjobs_gop", fetch_republicanjobs),
    ):
        try:
            records = fetch_fn(session)
        except Exception as exc:  # noqa: BLE001 - one source failing shouldn't kill the others
            print(f"[{name}] fetch failed: {exc}", file=sys.stderr)
            continue
        added = _merge_jsonl(STATE_DIR / f"{name}.jsonl", records)
        total_added += added
        print(f"[{name}] {len(records)} postings seen this run, {added} new -> data/processed/job_postings/{name}.jsonl")

    print(f"Total new postings added this run: {total_added}")


if __name__ == "__main__":
    main()
