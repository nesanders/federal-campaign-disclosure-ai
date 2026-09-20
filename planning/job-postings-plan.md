# Plan: AI-related campaign job postings as a signal

**Status: implemented, then retired (2026-09-20).** A live "Job Postings"
tab shipped on the site (2026-09-19), was extended across four more
rounds of source-hunting and a fifth round of targeted candidate-site
scraping, and was then removed from the site (2026-09-20) once the
findings themselves (see "Retired" at the very bottom of this file) made
clear the signal couldn't support the kind of reading a dashboard
implies. The pipeline code and scraped data remain in the repository.
See "Implementation notes" further down for what was actually built and
how it differs from the original plan below, which is otherwise left
intact for the record.

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

## Round 3 (2026-09-19): actionnetwork.org, Lever, and a real merge bug

The two levers identified at the end of Round 2, plus the domains needed
to unblock the two leads left dangling there, were safelisted and
investigated:

- **`actionnetwork.org` + `mainedems.org` + `vahousedems.org`**: all three
  now reachable, unlocking full description text for 10 of DLCC's 11
  postings (the 11th links to `jobs.gusto.com`, which -- like GAIN Power's
  career center, tried again this round -- turned out to be
  Cloudflare-blocked at the origin, same dead-end pattern as Indeed/DSCC).
- **`jobs.lever.co`** (EMILY's List): a real, server-rendered Lever board
  -- no headless browser needed, postings are in the initial HTML. Added
  as a sixth source. Turned out to be EMILY's List's own organizational
  hiring (development, comms, internships), not a feed of individual
  campaign postings -- a modest, honest addition (4 postings), not the
  breakthrough DLCC was.
- **`careercenter.gainpower.org`**: confirmed Cloudflare-blocked
  (`cf-mitigated: challenge`), same as the other bot-walled sources.
  Dead end, consistent with the first attempt.
- **`mattlockshin.com`**: the bare domain resolves and redirects to
  `www.mattlockshin.com`, which wasn't part of what got added -- still
  unfetched, carried forward in the tab's own "Recommended additional
  sources" card.

**Found and fixed a real bug while wiring this up**: `_merge_jsonl`'s
append-only design (never overwrite an existing record, only add new
ones) was written to protect a posting's history once it disappears from
the source -- but it was *also* silently preventing any existing
posting's fields from ever refreshing, including `body_text`. The first
attempt to backfill DLCC's newly-reachable descriptions produced "0 new"
every time, because the 11 DLCC postings already existed in the merged
file from Round 2 with `body_text: null`, and the merge logic kept that
null forever rather than replacing it with the now-successfully-fetched
text. Fixed by updating existing records' fields on every run while still
pinning `first_seen` to its original value -- the only field that
actually needs append-only permanence. This matters beyond DLCC: any
future domain addition that unlocks previously-missing body text for an
*already-seen* posting needs this fix to actually take effect, not just
new postings going forward.

**Result**: 191 -> 195 postings, 24 -> 27 with AI signal. Democratic
total 29 -> 33 (DLCC's newly-unlocked body text found one additional
skill-mention hit; EMILY's List added 4 postings with none AI-relevant).
The Republican/Democratic gap (150 vs. 33) is now believed to reflect the
real state of public, scrapable campaign-hiring data rather than
remaining source-hunting headroom -- the two sources added this round
were the last concrete leads from Round 2, and this round's new dead
ends (GAIN Power, Gusto) were already-known Cloudflare/ATS patterns, not
new categories of blocker.

## Round 4 (2026-09-19): the last lead

`www.mattlockshin.com` (the redirect target left dangling at the end of
Round 3) was safelisted and fetched. Confirmed dead end: its "Job Board"
page (`/job-board`) is entirely a multi-step newsletter signup form
("Tell me more about you... Sign up for my newsletter about job
placement and recruitment") -- no individual postings anywhere on the
page, just one example outbound link to a single Breezy HR posting. Same
lead-capture pattern as Sujata Strategies' email-only digest, not a
public listing to scrape. No new source added; no pipeline changes.

This closes out the list of candidate sources surfaced across all four
rounds. Nothing scrapable is known to remain unexplored at this point --
future progress on the Republican/Democratic gap would need either a
genuinely new source (not yet identified) or a different approach to the
Cloudflare-walled boards (headless browser + real fingerprint), which
raises its own ToS questions this project has chosen not to pursue.

## Round 5 (2026-09-20): targeted competitive-race candidate sites

Prompted by two findings from the entity-type breakdown added this
round (see below): (1) only 19 of 195 postings are tied to a specific,
named candidate committee -- everything else is a party/caucus
committee, a PAC's own hiring, or (for RepublicanJobs.gop specifically)
anonymized entirely -- and (2) that gap is structural, not a gap in
source-hunting: individual campaigns mostly don't run their own
scrapable job boards, and the one place their hiring probably *does*
show up in volume, LinkedIn, is CAPTCHA-walled. A targeted sweep of
competitive races' own campaign websites was proposed as the next
concrete step, rather than more general job-board hunting.

**Methodology**: `ballotpedia.org` was safelisted. Ballotpedia's own
"U.S. House battlegrounds, 2026" and "U.S. Senate battlegrounds, 2026"
pages list this cycle's competitive races -- 50 House districts + 12
Senate seats (13 listed, one a special election), current as of the
scrape date, not a static list carried over from a prior cycle. For
each of the 62 individual race pages, the major-party (Democratic/
Republican) candidates were pulled from that page's own FEC-sourced
fundraising table (`table.sortable` with `Name`/`Party` columns) --
186 unique candidates. For each candidate, their own Ballotpedia bio
page was fetched and its infobox "Campaign website" link extracted.

One real wrinkle worth recording: a plain sequential fetch loop (one
`requests.Session` reused across all ~186 bio-page requests) returned
wildly inconsistent results between runs on the *identical* set of
URLs -- 57 websites found in one full run, 0 in a same-code rerun
restricted to the House half, 37 in a same-code rerun restricted to
the Senate half -- while a single one-off fetch of any specific
"failing" URL, run in isolation immediately after, reliably found the
link every time. The cause wasn't pinned down (a connection-reuse or
edge-cache interaction is suspected, not proven), but the fix was:
open a **fresh `requests.Session` per attempt** and retry up to 3
times before concluding a candidate genuinely has no listed website.
That took the result from unreliable/near-zero to a stable **167 of
186 candidates (90%)** with a campaign website on file, consistent
across the two chambers (111 of ~124 House, 56 of ~62 Senate) and
roughly balanced by party (88 Democratic, 79 Republican). Full roster
saved to `planning/research/2026_battleground_candidate_sites.json`.

**Result**: 167 unique campaign-website domains, one per candidate.
None of these have been checked for an actual jobs/careers page yet --
that requires each domain to be individually safelisted first (this
sandbox's egress proxy blocks any domain not explicitly approved, and
there's no way to peek at a site's structure before that happens).
Given the volume, the realistic expectation is a **low hit rate**:
most single-candidate campaign sites are small, template-based
(Squarespace/NationBuilder/WordPress), and built around donate/volunteer
CTAs, not a dedicated careers page -- but at 167 sites, even a modest
percentage would meaningfully close the individual-candidate-committee
gap the entity-type breakdown surfaced. Domain list requested from the
user next; once safelisted, the plan is to check each site's homepage
for a careers/jobs/"join our team" link before attempting to scrape
anything, and only build a per-site scraper for ones that actually have
listings (there is no common platform/structure to assume across 167
independent campaign sites the way there was for the aggregators).

**Domain rounds and dead ends found while checking**: the 166 usable
domains (167 minus `lawhelpak.com`, a Ballotpedia data error -- see
below) were safelisted in two rounds. The first batch surfaced the same
"www vs. bare-domain redirect target not separately approved" pattern
seen throughout this project -- 20 sites needed their alternate form
added. Homepage-scanning those sites for a careers/jobs nav link also
found `apply.workable.com` (used by at least two Senate candidates, Jon
Ossoff and James Talarico) as a second-round addition. One roster entry
was a genuine data error, not a site issue: Ballotpedia's own
"Campaign website" link for perennial write-in candidate Dustin Darden
(AK Senate) points to `lawhelpak.com`, a legal-aid nonprofit unrelated
to his candidacy -- dropped rather than requested as a domain.

An earlier, exploratory pass (a looser keyword regex against every
link's full text and href, not just nav-style labels) had flagged 16
candidates with a "career-like link" -- almost all false positives on
inspection: economic-policy pages that happen to say "jobs" ("Bring
Good-Paying Jobs to Southern Arizona"), not a hiring page at all. The
production scraper's link-matching was tightened to nav-style labels
only (`CAREER_NAV_RE`/`CAREER_HREF_RE` -- "Careers", "Jobs", "Current
Openings," or a `/careers/`-style URL path), which found 9 candidates
with a real careers/jobs link. Of those: Roy Cooper's Lever board
(`jobs.lever.co/roy-cooper`) is real but currently has zero open
postings; Jon Ossoff's and James Talarico's Workable boards couldn't be
read (see the "known gap" note above); Graham Platner's "Careers" page
is a real nav link to an empty stub with no content; Abdul El-Sayed's
"Jobs" page is a generic "submit your resume, we'll keep you posted"
intake form, not an open listing (initially misclassified as real by
an early version of the content-indicator check, since its role-type
dropdown menu contained the words "Full-time" and "Part-time" -- fixed
by requiring either a strong, posting-specific phrase ("Reports to:",
"Responsibilities") or several weak indicators together, plus a hard
veto on intake-form language like "keep you in the loop"). Only **one**
of the 166 sites -- Maura Sullivan (D, NH-01) -- had an actual open,
individually-written posting: a Regional Organizing Director role, no
AI-related terms in the text.

**Result**: 195 -> 196 postings; named-candidate-committee postings
19 -> 20. A single new posting from 166 targeted candidate sites is a
real, if modest, result -- it confirms the structural read from before
this round's research (most individual campaigns do not run a public
job board at all) rather than reflecting a gap in this round's own
search. Every campaign-site posting gets a durable HTML snapshot saved
to `docs/data/job_snapshots/campaign_sites/` (committed, alongside its
live URL) since, unlike DCCC or RepublicanJobs.gop, a single candidate's
website has no institutional permanence and can vanish entirely once a
race ends.

## Retired (2026-09-20)

The Job Postings tab was removed from the live site. The decision came
out of a direct conversation about what the dataset could and couldn't
support, prompted by the user asking whether it was enough to conclude
anything about (1) what fraction of posted campaign roles require AI
skills, (2) what roles typically require them, or (3) trends over time,
across parties, or across campaign types. Working through those
questions surfaced problems serious enough that continuing to present
the tab as a dashboard -- something a reader skims for a number or a
trend -- would have been misleading, even with methodology notes
attached:

1. **The sample isn't a sample of "campaign roles."** 150 of ~196
   postings (77%) came from one board, RepublicanJobs.gop, that mixes
   actual campaigns with political consulting firms, law firms, 501(c)
   advocacy orgs, and think tanks. DCCC and DLCC only list races those
   committees choose to feature. The one source built specifically to
   escape this bias -- a targeted scrape of 166 individual competitive-
   race campaign sites (Round 5, above) -- found exactly **one** real
   posting. Individual campaigns, it turns out, overwhelmingly don't run
   a public job board at all; the aggregators exist because of that gap,
   not in spite of it.

2. **The party comparison was apples-to-oranges by construction.**
   RepublicanJobs.gop anonymizes every employer to a generic category
   ("Law Firm," "Political Consulting Firm," literally "Campaign") --
   none of its 150 postings name an actual candidate, committee, or
   organization. The Democratic-tagged postings, by contrast, mostly
   came from DCCC and DLCC and mostly did name one. The entity-type
   breakdown added to the tab (`classify_entity_type()`) was an attempt
   to fix this in place; it helped, but it couldn't fix the underlying
   sample-size and source-mix problem, and a reader who skipped the
   methodology notes would still walk away with "Republicans post 4-5x
   more" as the takeaway, which the data doesn't actually support.

3. **A large share of the "AI-relevant" hits were tautological.**
   Checking the org field on all AI-relevant postings found that 15 of
   26 (58%) came from just seven organizations whose name or category is
   literally about AI ("501c3 AI Think Tank," "AI Policy Organization,"
   "Political AI & Research Technology," "AI-Focused 501c3," "AI-Powered
   Advocacy Tech," "Political Technology Platform (Campaign Data & AI
   Infrastructure Company)," "LockedIn AI"). An AI think tank's social
   media internship mentioning AI isn't evidence campaigns are adopting
   AI -- it's an AI org hiring, a different phenomenon the site's
   title/skill-mention framing had no way to separate out. Net of that
   and a couple of other weak hits (a vendor-brand-name coincidence,
   one line of generic HR boilerplate), the real "ordinary political
   employer wants an AI skill" signal was about 7-8 postings out of
   ~196 -- enough to sketch a qualitative shape (AI shows up in digital/
   content roles first, not field/finance/ops), nowhere near enough to
   support a rate, a trend, or a "typical role" claim.

4. **No time-series is possible at all.** This was always a single-
   snapshot dataset by design (postings vanish once filled), so "trends
   over time" was never answerable and the site said so -- but it's
   worth restating here as part of why the feature's remaining value
   (a cross-sectional snapshot) wasn't enough to justify keeping it live
   once 1-3 above were accounted for.

None of this means the underlying question -- do campaigns' own hiring
decisions show AI adoption the disclosure data can't see -- is a bad one.
It means public job-board data, at least the sources reachable from this
environment, can't answer it at a scale or specificity worth publishing.
The code, the scraped data, and this document all stay in the repository
in case a better source (LinkedIn access, a much larger and more
diverse candidate-site sweep, a multi-cycle collection window) makes
this worth revisiting.

**What was removed from the site**: the "Job Postings" tab button, view,
and all its rendering code in `docs/js/app.js` and `docs/css/style.css`;
`docs/data/dashboard_jobs.json` and `docs/data/job_snapshots/` (both
regenerable from the pipeline); the two GitHub Actions workflow steps
that fetched and rebuilt this data. **What was kept**: every pipeline
script (`pipeline/fetch_job_postings.py`, `pipeline/build_dataset_jobs.py`,
`pipeline/lib/job_ai_match.py`), the scraped data
(`data/processed/job_postings/*.jsonl`), the candidate roster
(`pipeline/config/battleground_candidates_2026.json`), and this entire
planning document.
