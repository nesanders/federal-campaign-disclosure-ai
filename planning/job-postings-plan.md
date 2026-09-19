# Plan: AI-related campaign job postings as a signal

## Objective

Every signal the site currently tracks (Federal, Massachusetts, and the
Compare tab) is a named, billed vendor showing up in a disbursement record.
That structurally misses AI use that never generates a vendor line item: a
staffer using a personal or free-tier ChatGPT account, an in-house tool, or
— most directly relevant here — a campaign's own *investment decision* to
hire for AI capability before any tool purchase shows up in a filing.
Tracking AI-titled campaign job postings is a genuinely different kind of
evidence: intent and capability-building, not historical spend.

This is explicitly **not an extension of the existing pipeline**. It doesn't
join against `vendors.yaml`, it doesn't produce a dollar figure, and it
can't be backfilled the way FEC/OCPF filings can (postings are removed once
filled, so there's no equivalent of "download every filing since 2020").

## Candidate sources

| Source | Coverage | Notes |
|---|---|---|
| **DCCC House Campaign Job Board** (`dccc.org/campaign-job-board/`) | Democratic House races | Centralized, single-party, single-chamber — narrowest but cleanest source |
| **Campaigns & Elections jobs archive** (`campaignsandelections.com/jobs/`) | Bipartisan, industry trade press | Broadest legitimate single source; C&E is the trade publication of record for the campaign-tech industry |
| **RepublicanJobs.gop** (`www.republicanjobs.gop/opportunities/`) | Republican-aligned | Needed for partisan balance — the same rationale that led `vendors.yaml`'s own "third pass" to specifically research GOP-aligned tools after noticing a Democratic skew in the discovery process |
| LinkedIn Jobs, Indeed, ZipRecruiter | General, high-volume | Broadest reach but noisiest; general-purpose job boards, not political-specific, and likely to require API keys / have restrictive scraping terms of service — lower priority |

**Recommendation:** start with DCCC + Campaigns & Elections + RepublicanJobs.gop
only. That's a real bipartisan sample without the ToS and volume problems of
the general-purpose boards.

## Data access

All three primary domains were network-tested this session and are
**currently blocked by the outbound proxy** (`CONNECT tunnel failed,
response 403`), the same block every non-allowlisted domain returned.

| Domain | Purpose | Status |
|---|---|---|
| `dccc.org` | DCCC House Campaign Job Board | Blocked, needs safelisting |
| `campaignsandelections.com` | C&E jobs archive | Blocked, needs safelisting |
| `www.republicanjobs.gop` | GOP-aligned job board | Blocked, needs safelisting |

None of these expose a documented API — this would be HTML scraping of a
jobs-listing page, not a structured feed. Each page's actual markup needs
to be inspected once reachable to confirm it's scrapable at all (some job
boards render listings client-side via JS, which would need a headless
browser rather than a plain HTTP fetch).

## Proposed technical approach

This doesn't fit `fetch_*.py` → `parse_*.py` → `build_dataset_*.py`, because
there's no taxonomy match against a payee name — the "match" here is a
judgment call on a job title and description. Proposed shape instead:

1. **`fetch_job_postings.py`** — scrape (or headless-browser-render, if
   listings are JS-rendered) each source on a schedule (e.g. weekly, via the
   existing GitHub Actions refresh workflow), writing every posting's title,
   org/campaign name, description text, and posting date to
   `data/raw/job_postings/<source>_<date>.jsonl`. Since postings disappear
   once filled, **this file needs to be append-only and never overwritten**
   — each run adds newly-seen postings to a running log, rather than
   replacing the previous snapshot, or historical postings are lost forever
   the moment they're taken down.
2. **AI-relevance judgment.** A simple keyword match ("AI", "artificial
   intelligence", "machine learning", "generative", "LLM") in title or
   description will over-match: it will catch "familiarity with AI tools a
   plus" boilerplate alongside a real "Director of AI Strategy" role, the
   same false-positive problem `vendors.yaml`'s own patterns file works hard
   to avoid for vendor names. This needs its own confidence tiers, mirroring
   the existing high/medium-confidence vendor-match pattern:
   - **High confidence**: "AI" (or a specific product/technique) appears in
     the *job title itself* (e.g. "AI-Driven Data Analyst," "Automated
     Content Strategist").
   - **Medium/lower confidence**: "AI" appears only in the description body,
     not the title — likely a general digital/data role that merely
     mentions AI tools as a skill.
3. **`build_dataset_jobs.py`** — aggregate into counts over time (postings
   per month, by party/source, by role category), not a dollar figure. This
   is the first dataset on the site that wouldn't have a `$` column at all.
4. **Frontend** — a new page/section, not a fourth dataset tab in the
   existing Federal/MA/Compare pattern (those are all spend-based). Likely
   shape: a simple time series ("AI-titled campaign job postings per month")
   plus a browsable/sortable list of postings found, each linking back to
   the original listing. This is closer in spirit to the "weekly disclosure
   timeline" chart than to the vendor tables.

## Risks / open questions

- **Scraping fragility.** Job board HTML changes without notice; this would
  need to be one of the more maintenance-heavy pieces of the pipeline,
  unlike FEC/OCPF's stable APIs.
- **JS-rendered listings.** If any of these boards render postings
  client-side, a plain `requests`-based fetch (the pattern every existing
  `fetch_*.py` uses) won't work — would need Playwright/a headless browser
  in the fetch step, a new dependency for this pipeline.
- **No historical backfill.** Unlike every other signal on this site, there
  is no way to reconstruct "AI job postings in 2023" after the fact — this
  dataset only starts accumulating from whenever the scraper first runs.
  Worth being explicit with users that any resulting chart's early history
  will look artificially flat/empty, since it's a collection-start artifact,
  not a real trend.
- **Legal/ToS considerations.** Scraping frequency and terms of service
  should be checked per site before building a recurring scraper (this plan
  does not clear that; it should happen before writing `fetch_job_postings.py`).
- **Judgment-call confidence tiers** will need the same kind of "considered
  and rejected" documentation `vendors.yaml` already models, once real
  postings are seen and some inevitably turn out to be false positives.

## Effort estimate

Meaningfully different shape of work than the rest of the pipeline: less
"parse structured records," more "build and maintain a scraper, then design
a judgment-call classifier." Should be scoped as its own small project, not
folded into a state-expansion or vendor-mining sprint. Recommend a small
time-boxed prototype against Campaigns & Elections alone (broadest single
source) before committing to all three.

## Immediate next step

Safelist `campaignsandelections.com` first (broadest, most likely to have
enough postings to judge feasibility quickly) and load its jobs page to
confirm (a) it's static HTML vs. JS-rendered, and (b) whether AI-titled
roles actually appear there in meaningful numbers before investing in a
scraper.
