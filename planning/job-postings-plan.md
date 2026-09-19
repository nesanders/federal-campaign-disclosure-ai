# Plan: AI-related campaign job postings as a signal

**Status: implemented (2026-09-19).** A live "Job Postings" tab now ships
on the site, built on this plan's own re-prioritized source order
(RepublicanJobs.gop, DCCC, Campaigns & Elections). See "Implementation
notes" at the bottom of this file for what was actually built and how it
differs from the original plan below, which is otherwise left intact for
the record.

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

## Verification results (2026-09-19)

All three domains were safelisted and re-tested live; all three are static
HTML (no headless-browser dependency needed — good news for effort
estimate). Actual content changed the priority ranking:

| Domain | Status | What was actually found |
|---|---|---|
| `campaignsandelections.com` | ✅ Reachable, static HTML | Only **one** listing visible on `/jobs/` right now: "LLM Developer" at LockedIn AI. This board is thinner than expected in practice — likely because it's an employer-paid posting board with low current volume, not a comprehensive feed. Lower priority than originally ranked. |
| `dccc.org` | ✅ Reachable, static HTML | 19 real, live postings (field organizers, finance directors, political directors, a digital director — typical campaign-staff roles). **Zero AI-titled roles** in the current listing. Confirms AI-specific hiring isn't yet common in this specific, Democratic-House-race-only source — a real (if early) data point, not a scraping failure. |
| `www.republicanjobs.gop` | ✅ Reachable, static HTML | **Best yield of the three.** Found a real on-title hit — "Director of Product Development/AI Director" at a political consulting firm — plus a "Social Media Manager" role at an explicitly "AI-Focused 501c3," and multiple other listings citing "AI tool proficiency" as a listed skill. |

**Updated recommendation:** flip the original priority order. Start with
`republicanjobs.gop`, not Campaigns & Elections — it's the only source of
the three that actually surfaced an unambiguous AI-titled role in this
pass. Keep DCCC as a standing bipartisan-balance check (even a "zero found"
result is worth logging over time, since the interesting story may end up
being an asymmetry in *when* each party's postings start naming AI roles).
Campaigns & Elections is real but thin; worth keeping in the source list
but not worth prioritizing engineering effort on it first.

This is still a single-snapshot read, not a trend — the plan's core caveat
holds: there's no way to backfill history, so whatever scraper gets built
should start logging now rather than waiting for a "better" moment.

## Implementation notes (2026-09-19)

What actually got built, and where it differs from the plan above:

- **Confidence tiers**, not just a single "AI-titled" flag: `pipeline/lib/
  job_ai_match.py` classifies each posting as `title` (an AI term in the
  job title itself) or `skill_mention` (an AI term only in the body/
  description of an otherwise ordinary role) — the ground-level signal
  explicitly requested, distinct from AI leadership hiring. First real run
  found 6 title-level and 18 skill-mention postings out of 168 scraped,
  including genuine "county organizer"-adjacent examples (a DCCC "Finance
  Assistant" listing that names Calltime.ai as required call-time
  software — corroborating that same vendor's spend already tracked on
  the Federal tab).
- **Body text availability differs by source**, discovered only by
  actually fetching real HTML: RepublicanJobs.gop has the full
  description inline on its one archive page (by far the richest source);
  DCCC's description is a linked PDF per posting, fetched and
  text-extracted separately (`pdfminer.six`); Campaigns & Elections'
  individual job pages are Cloudflare-gated and could not be scraped at
  all, so that source is title-only, a real and documented data gap, not
  an oversight.
- **State storage moved from `data/raw/` to `data/processed/job_postings/`**,
  a correction to this plan's own original assumption. `data/raw/` is
  gitignored (by design, for FEC/OCPF's always-redownloadable full dumps),
  but this feature's append-only merge needs to *survive* between GitHub
  Actions runs to mean anything, since postings genuinely disappear at the
  source and a fresh checkout has no memory of them otherwise. The merged
  JSONL files are committed to git.
- **New pipeline dependencies**: `beautifulsoup4`, `lxml`, `pdfminer.six`
  (added to `pipeline/requirements.txt`). Confirmed working in this
  environment after a local `cryptography`/`cffi` binding conflict was
  resolved via `pip install --force-reinstall cffi` — worth knowing if a
  fresh environment hits the same import error.
- **Frontend**: a fourth dataset tab (`#/jobs`), following the same
  pattern as Compare — its own accent color, banner, stat tiles, a
  breakdown-by-source-and-party table, the full sortable postings table
  (AI-relevant sorted first by default, each title linking to the original
  listing with the matched snippet shown inline), and methodology/sources/
  recommended-additional-sources cards. No legacy-vendor toggle or search
  bar on this tab (neither concept applies to this dataset).
- **Recommended additional sources** (not yet built, carried into the
  live tab's own "Recommended additional sources" card so it's visible to
  readers, not just this plan): NRCC/DSCC/NRSC as direct parallels to
  DCCC; DLCC/RSLC for state-legislative (more ground-level) postings;
  state party job boards; Indeed/LinkedIn/ZipRecruiter for broader,
  noisier reach; individual campaign career pages for the most granular
  but least scalable source.

## Round 2 (2026-09-19): chasing the Federal/Democratic imbalance

The user flagged that RepublicanJobs.gop (150 postings) dwarfs every
Democratic-aligned source (29 total across DCCC, DLCC, and one
Campaigns & Elections posting) and asked to keep looking, especially for
campaign-level (not just national-committee-curated) postings. Thirteen
candidate domains were safelisted and investigated one at a time by
actually fetching each and reading real HTML, not assuming a common
shape. Results:

**Added and shipped:**
- **DLCC "Work in the States"** (`www.dlcc.org/careers/`) — the best find
  of this round. Real individual-campaign and state-legislative postings
  ("Kevin Hertel for State Senate -- Finance Director," "Sue Shink for
  State Senate -- Campaign Manager"), grouped by state under `<h5>`
  headings, the direct Democratic-side counterpart to RepublicanJobs.gop's
  ground-level detail. 11 postings on first run. Full descriptions live on
  other orgs' own sites (`actionnetwork.org` hosts most of them) that
  aren't fetched yet, so these postings are currently title-only --
  the single highest-value next domain to add if more signal is wanted
  from this source specifically.
- **Democracy Jobs** (`www.democracyjobs.org`) — a general democracy/
  civic-tech board, not partisan-tagged, skewing nonprofit/advocacy over
  campaign roles, but real, fully scrapable (including detail-page body
  text on the same domain), and it already surfaced two genuine
  skill-mention hits ("Experience leveraging AI-powered tools..." for a
  Digital Content Manager role). 12 postings on first run.

**Investigated and confirmed as genuine dead ends, not gaps left
unaddressed:**
- **LinkedIn** -- serves a Google reCAPTCHA challenge page, not content.
  Not scrapable without solving a CAPTCHA, which this project won't
  attempt.
- **Indeed, DSCC, ZipRecruiter, Arena Careers (careers.arena.run)** -- all
  four are reachable at the network level but return a Cloudflare
  bot-block 403 at the origin itself. No amount of domain-safelisting
  fixes this; it would need a full headless-browser fingerprint, which
  raises its own ToS questions this project isn't pursuing.
- **NRCC's "campaign jobs" page** -- turned out to be a general
  resume-submission form (name, state/position preferences, upload a
  resume), not a list of individual open postings. Nothing to scrape.
- **NRSC and RSLC** -- neither appears to publish a public jobs/careers
  page at all (no matching nav links or content found on either
  homepage).
- **Sujata Strategies** -- its "Jobs" page turned out to be a description
  of an email-digest product (join a mailing list to receive postings),
  not a public web listing. The postings themselves only ever go out by
  email, which is out of scope for a web scraper.

**Found but not yet added** (real, promising, but hosted on domains not
yet safelisted): GAIN Power's actual job board lives on a separate
subdomain, `careercenter.gainpower.org` (its marketing page at
`gainpower.org` is not the board itself); EMILY's List runs its board on
Lever (`jobs.lever.co/emilyslist`) -- Lever is also a shared ATS used by
many other organizations, so approving `jobs.lever.co` once could unlock
more than just this one board; Matt Lockshin's Progressive Job Board
(`mattlockshin.com/job-board`) was found via Social Justice Leadership's
resource page but not yet fetched.

**Honest takeaway**: after this round, the Republican/Democratic
imbalance looks like it reflects genuine data availability more than
uneven effort -- RepublicanJobs.gop is simply a larger, richer single
board than anything found on the Democratic side so far, even after
adding DLCC and Democracy Jobs and investigating nine other candidate
sources. The next real lever for narrowing the gap is `actionnetwork.org`
(unlocks DLCC body text) and `jobs.lever.co` (EMILY's List, and
potentially more), not more source-hunting on faith.
