#!/usr/bin/env python3
"""Scrape AI-relevant signal from campaign job postings on six boards:
the DCCC's House Campaign Job Board, Campaigns & Elections' jobs archive,
RepublicanJobs.gop's opportunities page, the DLCC's careers page,
Democracy Jobs, and EMILY's List's Lever-hosted board.

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
  - DLCC (www.dlcc.org/careers/): its "Work in the States" section lists
    real state-legislative and individual-campaign postings (e.g. "Kevin
    Hertel for State Senate -- Finance Director"), grouped under an <h5>
    per state, each linking to a PDF or an external org's own page for
    the full description. Most of those linked domains (actionnetwork.org,
    mainedems.org, vahousedems.org) are now fetched for body text via
    _fetch_external_body_text(); jobs.gusto.com is Cloudflare-blocked and
    falls back to title-only for the one posting that links there.
  - Democracy Jobs (www.democracyjobs.org): a general democracy/civic-tech
    job board, title/company/type/location/salary inline via a WordPress
    job-board plugin, each posting's own page (on the same domain, no
    extra fetch needed) carries the full description. Skews nonprofit/
    advocacy rather than campaign-specific -- included for genuine
    Democratic-aligned volume, not because every posting is a campaign.
  - EMILY's List (jobs.lever.co/emilyslist): a standard Lever board,
    server-rendered (no headless browser needed), title/type/location
    inline plus a per-posting detail page on the same domain for the full
    description. This is EMILY's List's own organizational hiring
    (development, comms, internships), not a feed of individual campaign
    postings the way DLCC's page is -- included for the same
    genuine-volume reason as Democracy Jobs.
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


def _fetch_external_body_text(session: requests.Session, url: str, label: str) -> str | None:
    """Best-effort fetch of a linked posting's full text, whether it's a
    PDF or an ordinary HTML page, for postings whose source only gives a
    title inline and links out to another organization's own site for the
    description (e.g. DLCC's "Work in the States"). Not every domain a
    posting links to is necessarily reachable -- this degrades to None on
    any failure (timeout, 403, DNS) exactly like fetch_dccc's own PDF
    fetch already does, rather than letting one unreachable link fail the
    whole run.
    """
    if not url:
        return None
    try:
        resp = session.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        url_lower = url.lower()
        if url_lower.endswith(".pdf") or "application/pdf" in content_type:
            tmp_path = STATE_DIR / "_tmp_external.pdf"
            tmp_path.write_bytes(resp.content)
            from pdfminer.high_level import extract_text

            text = extract_text(str(tmp_path))
            tmp_path.unlink(missing_ok=True)
            return text
        if url_lower.endswith(".docx") or "wordprocessingml.document" in content_type:
            import io

            from docx import Document

            doc = Document(io.BytesIO(resp.content))
            return "\n".join(p.text for p in doc.paragraphs)
        if "html" not in content_type and not url_lower.endswith((".htm", ".html")):
            # Anything else (old-style .doc, an octet-stream, some other
            # binary format we haven't seen yet) can't be reliably
            # text-extracted -- feeding its raw bytes to BeautifulSoup as
            # if it were HTML produces decoded-binary garbage that can
            # spuriously match the AI regex, which is worse than no body
            # text at all, so this degrades to None exactly like an
            # unreachable link does.
            print(f"  [{label}] skipping unrecognized content type {content_type!r} for {url!r}", file=sys.stderr)
            return None
        return BeautifulSoup(resp.text, "lxml").get_text(" ", strip=True)
    except Exception as exc:  # noqa: BLE001 - an unreachable link shouldn't kill the run
        print(f"  [{label}] could not fetch external body text from {url!r}: {exc}", file=sys.stderr)
        return None


def _posting_id(source: str, *parts: str) -> str:
    raw = source + "|" + "|".join(p or "" for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _merge_jsonl(path: Path, new_records: list[dict]) -> int:
    """Append-only merge keyed by `id`: a posting already on disk is never
    *dropped*, even once it's gone from the source (that's the whole
    point -- postings get removed once filled, and this is the only
    record that it ever existed). But its fields *do* refresh from this
    run's copy, with one exception -- first_seen stays pinned to whenever
    the posting was originally found, not today's date. Without that
    refresh, a field that starts out empty because a linked domain wasn't
    reachable yet (e.g. DLCC's body_text, before actionnetwork.org was
    approved) would stay empty forever even after the domain is added and
    a later run successfully fetches it.
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
        prior = existing.get(rec["id"])
        if prior is None:
            existing[rec["id"]] = rec
            added += 1
        else:
            updated = dict(rec)
            if prior.get("first_seen"):
                updated["first_seen"] = prior["first_seen"]
            existing[rec["id"]] = updated
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

        body_text = _fetch_external_body_text(session, href, "dccc") if fetch_pdfs and href else None

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


def fetch_dlcc(session: requests.Session, fetch_details: bool = True) -> list[dict]:
    url = "https://www.dlcc.org/careers/"
    resp = session.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    today = time.strftime("%Y-%m-%d")
    records = []
    # "Work in the States" is a series of <h5>State</h5> headings each
    # immediately followed by a <ul> of postings -- confirmed by reading
    # the real page source, not assumed. Iterating every <h5> on the page
    # (rather than trying to scope to one container div, whose class names
    # are WordPress block-editor boilerplate not worth depending on) and
    # checking whether a <ul> of links directly follows it is a robust
    # enough proxy: nothing else on this page has that shape.
    for h5 in soup.find_all("h5"):
        state = h5.get_text(strip=True)
        sib = h5.find_next_sibling()
        if not sib or sib.name != "ul":
            continue
        for li in sib.find_all("li"):
            link = li.find("a")
            if not link:
                continue
            title_text = link.get_text(strip=True)
            href = link.get("href")
            if not title_text:
                continue
            # DLCC's own list format is "Org - Title" (an en-dash), same
            # convention RepublicanJobs.gop uses in its own header text.
            org, _, title = title_text.partition("–")
            org = org.strip() or None
            title = title.strip() or title_text
            # The linked PDFs/pages live on other organizations' own
            # sites (actionnetwork.org, individual state party/campaign
            # sites, jobs.gusto.com) -- fetched best-effort; some of
            # those domains aren't reachable (e.g. jobs.gusto.com is
            # Cloudflare-blocked), in which case this just falls back to
            # title-only classification for that one posting.
            body_text = _fetch_external_body_text(session, href, "dlcc") if fetch_details else None
            records.append(
                {
                    "id": _posting_id("dlcc", state, title_text),
                    "source": "dlcc",
                    "party": "Democratic",
                    "title": title,
                    "org": org,
                    "office": None,
                    "location": state,
                    "posted_date": None,
                    "url": href,
                    "body_text": body_text,
                    "first_seen": today,
                }
            )
    return records


def fetch_democracyjobs(session: requests.Session, fetch_details: bool = True) -> list[dict]:
    url = "https://www.democracyjobs.org/jobs"
    resp = session.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    today = time.strftime("%Y-%m-%d")
    records = []
    for item in soup.find_all(class_="job-listings-item"):
        link = item.find(class_="job-details-link")
        title = link.get_text(strip=True) if link else None
        href = link.get("href") if link else None
        if href and href.startswith("/"):
            href = "https://www.democracyjobs.org" + href
        info_links = item.find_all(class_="job-info-link-item")
        org = info_links[0].get_text(strip=True) if info_links else None
        if not title:
            continue

        body_text = None
        if fetch_details and href:
            try:
                detail_resp = session.get(href, headers=HEADERS, timeout=30)
                detail_resp.raise_for_status()
                detail_soup = BeautifulSoup(detail_resp.text, "lxml")
                body_text = detail_soup.get_text(" ", strip=True)
            except Exception as exc:  # noqa: BLE001 - one bad detail page shouldn't kill the run
                print(f"  [democracyjobs] could not fetch detail for {title!r}: {exc}", file=sys.stderr)

        records.append(
            {
                "id": _posting_id("democracyjobs", title, org or ""),
                "source": "democracyjobs",
                "party": None,  # general democracy/civic-tech board, not partisan-tagged
                "title": title,
                "org": org,
                "office": None,
                "location": None,
                "posted_date": None,
                "url": href,
                "body_text": body_text,
                "first_seen": today,
            }
        )
    return records


def fetch_emilyslist(session: requests.Session, fetch_details: bool = True) -> list[dict]:
    """EMILY's List's own Lever-hosted board -- its own organizational
    hiring (development/comms/internship roles), not a feed of individual
    campaign postings the way DLCC's page is. Included for genuine
    Democratic-aligned volume, same rationale as Democracy Jobs, not
    because every posting here is a campaign job.
    """
    url = "https://jobs.lever.co/emilyslist"
    resp = session.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    today = time.strftime("%Y-%m-%d")
    records = []
    for posting in soup.find_all(class_="posting"):
        title_el = posting.find(attrs={"data-qa": "posting-name"})
        title = title_el.get_text(strip=True) if title_el else None
        link = posting.find(class_="posting-title")
        href = link.get("href") if link else None
        cats = [c.get_text(strip=True) for c in posting.find_all(class_="posting-category")]
        location = next((c for c in cats if c and c not in ("Full Time", "Part Time", "Intern")), None)
        if not title:
            continue

        body_text = _fetch_external_body_text(session, href, "emilyslist") if fetch_details and href else None
        records.append(
            {
                "id": _posting_id("emilyslist", title, href or ""),
                "source": "emilyslist",
                "party": "Democratic",
                "title": title,
                "org": "EMILY's List",
                "office": None,
                "location": location,
                "posted_date": None,
                "url": href,
                "body_text": body_text,
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
        ("dlcc", fetch_dlcc),
        ("democracyjobs", fetch_democracyjobs),
        ("emilyslist", fetch_emilyslist),
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
