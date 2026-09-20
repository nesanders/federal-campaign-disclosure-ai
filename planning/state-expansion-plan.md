# Plan: Expand beyond Massachusetts to additional states

## Objective

The Massachusetts tab proved the pattern: a state with a queryable, itemized
expenditure disclosure system can be matched against the same AI-vendor
taxonomy used for federal data, and folded into the Compare tab. This plan
scopes adding one or more additional states, following that same
`fetch_<state>.py` → `parse_<state>.py` → `build_dataset_<state>.py` →
frontend tab shape.

This is explicitly the "more of the same" option (breadth, not a new kind of
signal): it only catches AI use that shows up as a named, billed vendor in a
state's own itemized disclosures, exactly like the Federal and Massachusetts
tabs already do.

## Candidate states, ranked

| Rank | State | System | Why |
|---|---|---|---|
| 1 | **Washington** | Public Disclosure Commission (PDC) | Widely cited as the most accessible state campaign-finance database; raw data export; itemized contribution *and* expenditure search back to 2007. Best-documented, most likely to have a real API. |
| 2 | **California** | CAL-ACCESS (Secretary of State) | Largest state, highest expected AI-vendor dollar volume and highest-profile stories — but CAL-ACCESS is a legacy system known for being difficult to work with; bulk downloads are full database dumps, not a clean itemized-expenditure endpoint. |
| 3 | **Texas** | Ethics Commission | Searchable filings with CSV import/export tooling; unclear if there's bulk/API access vs. only the search UI. |
| 4 | **Colorado** | TRACER | Has a dedicated "Campaign Finance Disclosure Data Download" page; unverified in depth this round. |
| — | Others (NY, FL, IL, PA, OH…) | Unknown | Each needs its own discovery pass; no assumption should be made that any of these look like OCPF or PDC. |

**Recommendation: do Washington first, alone, as a single trial**, then
decide whether a second state is worth it based on actual AI-vendor yield —
mirroring how the federal outside-spending build was scoped and shipped even
though it turned up "one qualifying payment" for coordinated party
expenditures: a real, documented finding, not a wasted build, but a signal
that yield is genuinely unpredictable until the pipeline exists.

## Data access

All of the following were network-tested from this container this session
and are **currently blocked by the outbound proxy** (`CONNECT tunnel failed,
response 403`) — the same 403 every domain not already on the allowlist
returns. The existing pipeline's domains (`api.ocpf.us`, `www.fec.gov`,
`github.com`, `raw.githubusercontent.com`) all returned real HTTP responses
in the same test, confirming this is a domain-allowlist gap, not a general
network issue.

| Domain | Purpose | Status |
|---|---|---|
| `www.pdc.wa.gov` | Washington PDC — data pages, likely API/export endpoints | Blocked, needs safelisting |
| `data.wa.gov` | Washington's Socrata open-data portal — PDC data may also be published here | Blocked, needs safelisting |
| `cal-access.sos.ca.gov` | California CAL-ACCESS bulk data | Blocked, needs safelisting |
| `www.sos.ca.gov` | California SOS raw-data page (may just link to cal-access.sos.ca.gov) | Blocked, needs safelisting |
| `www.ethics.texas.gov` | Texas Ethics Commission campaign finance data | Blocked, needs safelisting |
| `data.colorado.gov` | Possible Colorado open-data portal | Blocked, needs safelisting |
| `tracer.sos.colorado.gov` | Colorado TRACER system (domain unconfirmed — guessed from search results, not yet verified to exist) | Blocked, needs safelisting |

None of these domains' actual API/export shape has been confirmed yet (no
equivalent of OCPF's `api.ocpf.us/search/items` + `swagger.json` has been
found for any of them). **The first real step, once a domain is safelisted,
is discovery** — same as how `fetch_ocpf.py`'s own docstring records that
OCPF's REST API was found and confirmed via a public `swagger.json`, with no
official documentation linked from OCPF's own site. Washington PDC may be
genuinely different: it's reputed to have a real user-facing "download raw
data" feature, which is a good sign, but the concrete endpoint shape
(REST API vs. flat-file bulk export vs. Socrata dataset) is unknown until
someone can actually load `pdc.wa.gov`.

## Proposed technical approach (per state, once access is confirmed)

1. **Discovery** — load the state's data/API documentation page (or, absent
   one, inspect the search UI's own network requests for an underlying API,
   the same way OCPF's was found). Determine: itemized expenditure records
   available? Payee name field? Purpose/description field(s) to match
   against (OCPF's `clarifiedName`/`clarifiedPurpose` fields were essential
   — many states may have less-annotated payee data)? Date range covered?
   Rate limits / pagination shape?
2. **`fetch_<state>.py`** — download raw itemized expenditure (and, if it
   exists, subvendor/subcontractor-style) records to
   `data/raw/<state>/*.jsonl`, mirroring `fetch_ocpf.py`'s pagination and
   integrity-check discipline (refuse to write a result that doesn't match
   the source's own reported total).
3. **`parse_<state>.py`** — match payee/purpose text against the *same*
   `pipeline/config/vendors.yaml` taxonomy via `pipeline/lib/vendor_match.py`
   (no new taxonomy needed — this is the whole point of a shared taxonomy).
   Also compute the state's own filer-level total-expenditure denominator
   (mirroring `ocpf_filer_year_totals.csv`) for a "% of total spend" stat,
   if the state's data supports it.
4. **`build_dataset_<state>.py`** — build a `dashboard_<state>.json` with the
   same shape as `dashboard_ma.json` (`vendors`, `vendors_detail`,
   `filers_detail`, `time_series`, `party_split`, era/confidence splits,
   etc.), so the existing frontend patterns (era toggle, confidence
   columns, high/low-confidence split) apply with minimal new JS.
5. **Frontend** — either a fourth dataset tab (mirroring the Massachusetts
   tab), or, if a state's yield is small, folding it directly into the
   Compare tab as a third `$` column rather than building it a full tab of
   its own. This decision should wait until real yield numbers exist.
6. **Compare tab** — extend `buildCompareRows()` in `docs/js/app.js` to union
   in the new state's `vendors_overall`-equivalent list, and extend the
   momentum/volume computation to include its `vendors_detail` time series.
   This is a small, mechanical change given the Compare tab was built
   dataset-agnostic already (it unions on vendor `id` across any number of
   sources, not just two).

## Risks / open questions

- **Unknown yield.** MA's OCPF data, after full pipeline effort, found 342
  matched records / ~$24K total AI-vendor spend statewide — real but small
  next to the federal dataset. A larger state like California could yield
  much more, or could turn out to have thin purpose/memo text (many states'
  disclosure systems don't annotate payee purpose as richly as OCPF's own
  `clarifiedName`/`clarifiedPurpose` fields do), which would understate
  real AI use the same way FEC's own generic "software subscription"
  purposes already do.
- **Format heterogeneity.** Every state's schema, confidence in payee-name
  cleanliness, and date-range coverage will differ; there is no guarantee
  any of these looks like OCPF's API once actually inspected.
- **Multi-state maintenance cost.** Each added state is a permanent addition
  to the GitHub Actions refresh workflow and README, not a one-time script.

## Effort estimate

Washington (or any single state), assuming its data access resembles OCPF's
(a real, if undocumented, API): comparable to the original Massachusetts
build — fetch + parse + build_dataset + minimal frontend wiring. If it turns
out to be a legacy bulk-file system like CAL-ACCESS is reputed to be, expect
meaningfully more parsing effort (schema normalization, likely no
clarified-purpose-style field, possibly a full relational DB dump to
reconstruct itemized expenditures from).

## Immediate next step

Safelist `www.pdc.wa.gov` and `data.wa.gov` (see domain list above) so a
discovery pass can confirm what Washington's actual data access looks like
before any fetch/parse code is written.

## Verification results (2026-09-19)

All domains below were safelisted and re-tested live from this container.

| Domain | Status | Finding |
|---|---|---|
| `www.pdc.wa.gov` | ✅ Reachable | Confirmed a real "open data" page (`/political-disclosure-reporting-data/open-data`) listing dataset categories — Candidates, Committees, Independent Expenditures, Lobbying Expenditures, Financial Affairs Disclosure, Search Contributions, **Search Expenditures**. No direct CSV/API URL was visible on the page itself; it points to a GitLab wiki, `gitlab.com/wapdc/OpenData-Program/wikis/home` (reachable, `gitlab.com` already allowed), for the real developer documentation — that wiki's actual content needs a follow-up read (a single fetch only returned the page's nav chrome, not the wiki body). **Not yet confirmed whether this is a true bulk export/API or just a nicer search UI** — this is the next concrete step before writing any fetch code. |
| `data.wa.gov` | ✅ Reachable | Confirmed to be a Socrata-style open-data portal (the standard platform many state/city bulk datasets use, which typically means a documented SODA API is available once the right dataset is found), but the specific PDC/campaign-finance dataset wasn't located in this pass — needs a direct site search on data.wa.gov for "campaign finance" or "PDC". |
| `cal-access.sos.ca.gov` | ✅ Reachable | Page returned empty/unhelpful content on this pass — but see the finding below, which supersedes this URL. |
| `www.sos.ca.gov` | ✅ Reachable | **Best finding of this round.** The raw-data page directly links two concrete bulk downloads: `calaccess-documentation.zip` (schema docs) and **`dbwebexport.zip`** — described as raw, transaction-level data ("tab-delimited text files from corresponding tables in the CAL-ACCESS database"), **updated daily**. This is exactly the kind of bulk file this pipeline already knows how to consume. |
| `campaignfinance.cdn.sos.ca.gov` | ❌ **Blocked, 403** | This is where both zip files above actually live — a *third*, distinct California domain that was not part of the original safelist request and is not yet approved. **This one specific domain is the actual blocker for California** now that the other two are reachable. |
| `www.ethics.texas.gov` | ⚠️ Reachable, but site returns 401 | The proxy tunnel succeeds (domain is genuinely safelisted and reachable) — but the Texas Ethics Commission's own server is currently returning `401 Unauthorized` with `WWW-Authenticate: Basic realm="Restricted Area"` on **every page tested, including the bare root domain**. This is the target site itself gating access, not a safelist/proxy problem — nothing to add to a domain list fixes this. Could be temporary (maintenance, bot-blocking) — worth a manual re-check later rather than more domain requests. |
| `data.colorado.gov` | ✅ Reachable | Not yet explored in depth this round. |
| `tracer.sos.colorado.gov` | ✅ Reachable | Confirmed this is the real Colorado TRACER system (the domain guessed in the original plan was correct). Page references a "Download Data" resource but the exact URL/format wasn't confirmed in this pass. |

**Updated recommendation:** California just became the more promising near-term target, not Washington — `dbwebexport.zip` is a concrete, already-found, daily-updated bulk file, versus Washington's open-data structure still needing one more layer of discovery (the GitLab wiki). **Next step: safelist `campaignfinance.cdn.sos.ca.gov`**, then confirm the zip's actual internal file/table structure (likely needs `calaccess-documentation.zip` read alongside it to map which table holds itemized expenditures with payee name + purpose, analogous to OCPF's `clarifiedName`/`clarifiedPurpose` fields) before writing `fetch_ca.py`.

## Round 2 (2026-09-20): all four states scoped, integration plan

`campaignfinance.cdn.sos.ca.gov` is now reachable (safelisted since Round
1). This round pushed discovery to completion for all four states —
three turned out to have real, directly buildable data, no further
domains needed for those three at all.

### California — confirmed buildable

`www.sos.ca.gov`'s raw-data page links two files, both live on
`campaignfinance.cdn.sos.ca.gov`:
- `calaccess-documentation.zip` (4.2 MB) — schema docs. The
  `DBInfo/CalAccessTablesWeb.pdf` inside it documents every table.
- `dbwebexport.zip` (**1.58 GB**, updated daily — `last-modified` was
  today when checked) — the full CAL-ACCESS database as tab-delimited
  files, one per table, 130 entries total.

The table that matters, `CalAccess/DATA/EXPN_CD.TSV`, is itself **3.07
GB uncompressed / 393 MB compressed** — a large single table, but its
schema is exactly what's needed: `CMTE_ID` (filer), `PAYEE_NAML`/
`PAYEE_NAMF` (payee name), `EXPN_DSCR` (purpose/description, CAL-
ACCESS's answer to OCPF's `clarifiedPurpose`), `EXPN_DATE`, `AMOUNT`,
`CAND_NAML`/`OFFICE_CD`/`OFFIC_DSCR`/`DIST_NO` (candidate/office/
district, for candidate-detail pages), `JURIS_CD`/`JURIS_DSCR`. Sample
rows confirmed real data back to at least January 2000.

The zip's host (`campaignfinance.cdn.sos.ca.gov`) supports HTTP range
requests (`accept-ranges: bytes`), which matters a lot here: Python's
`zipfile` module can read a remote zip's central directory and then
decompress just the one entry it needs, fetching only the bytes that
entry's compressed stream requires — confirmed by pulling the first 130
rows of `EXPN_CD.TSV` using **35 KB of network transfer**, not 1.58 GB.
`fetch_ca.py` should use this pattern (a small `HttpFile`-style
seekable wrapper around `requests`, feeding `zipfile.ZipFile`) rather
than downloading the full archive, both to avoid an unnecessary
~1.2 GB extra download (everything in the zip except `EXPN_CD.TSV`) and
because GitHub Actions runners have finite disk. The 393 MB compressed
entry itself still needs a full sequential read once decompression
starts, so the actual fetch is closer to "download ~400 MB," comparable
to the FEC's own largest per-cycle Schedule B files this pipeline
already handles.

**No further domains needed for California.**

### Washington — confirmed buildable, cleanest of the four

The GitLab wiki (`gitlab.com/wapdc/OpenData-Program/-/wikis/home`,
fetched via its raw-markdown endpoint since the rendered page is a JS
SPA) just points back to `pdc.wa.gov`'s catalog and confirms "5 million
records published to the Washington State Open Data Portal" —
`data.wa.gov`, a standard Socrata deployment.

Socrata's own catalog API, correctly scoped with `domains=data.wa.gov`
(an unscoped query returns federated cross-domain results from every
Socrata-hosted portal — caught this after an unscoped search returned
Austin TX, New York State, Hawaii, and Oakland CA results mixed in),
finds **`tijg-9zyp`: "Expenditures by Candidates and Political
Committees"** — exactly the target dataset. It's queryable directly:

```
GET https://data.wa.gov/resource/tijg-9zyp.json?$limit=...&$offset=...
GET https://data.wa.gov/resource/tijg-9zyp.json?$select=count(*)
```

**1,091,350 total rows**, "last 10 years" per the dataset's own
description. Fields: `filer_name`, `office`, `legislative_district`,
`party`, `jurisdiction`, `description` (real purpose text — sample rows
include things like "Snowball is an online payment processor..."),
`code` (a expense-category field — one observed value was literally
"Computers, printers, software, phones, etc.", a strong pre-filter for
AI-vendor matching), `recipient_name`/`recipient_address`/`recipient_city`
etc., `amount`, `expenditure_date`. This is a standard, well-documented
Socrata SODA API — the same query pattern (`$limit`/`$offset`
pagination, `$select=count(*)` for an integrity check) this pipeline
already uses conceptually for OCPF, and arguably better-documented than
OCPF's own undocumented API was when that one was built.

**No further domains needed for Washington.**

### Colorado — confirmed buildable

`tracer.sos.colorado.gov/PublicSite/DataDownload.aspx` lists plain CSV-
in-zip bulk downloads, one file per (data type × year), for
Contributions, Expenditures, and Loans, paginated 10-per-page across at
least 9 pages of results (so likely back to the system's start, not
just recent years). Direct links, no auth, no API needed:

```
https://Tracer.sos.colorado.gov/PublicSite/Docs/BulkDataDownloads/<YEAR>_ExpenditureData.csv.zip
```

Downloaded and inspected 2025's file (1.9 MB zipped, 11.8 MB CSV):
columns include `LastName`/`FirstName`/`CommitteeName` (payee is
person-or-business, split across name fields the way FEC's own
`payee_organization_name` vs `payee_last_name/first_name` pair already
requires similar handling for), `Explanation` (purpose text),
`CandidateName`, `CommitteeName`, `CommitteeType`, `ExpenditureType`
(category), `Jurisdiction`, `ExpenditureAmount`, `ExpenditureDate`. This
is the most FEC-bulk-file-like of the three confirmed states — flat
annual CSVs, no pagination or rate limits to manage, just N files to
download and concatenate (mirroring `fetch_fec_bulk.py`'s own per-cycle
file loop).

**No further domains needed for Colorado.**

### Texas — still blocked, not a domain problem

`www.ethics.texas.gov` returns a real, server-side `401 Unauthorized`
with `WWW-Authenticate: Basic realm="Restricted Area"` on **every path
tested, including robots.txt** — confirmed twice, roughly a day apart,
so this isn't a transient blip. This is the Texas Ethics Commission's
own Apache server gating its entire public site behind HTTP Basic Auth,
for reasons unknown (maintenance? an unannounced access change?
bot-mitigation gone wrong?) — nothing on the domain-safelist side fixes
this. Three more candidate domains are worth trying, all currently
proxy-blocked and unverified: the bare `ethics.texas.gov` (no `www`,
in case only the `www` vhost is gated), `txethics.org` (TEC's legacy
pre-rebrand domain, might still serve old bulk downloads or redirect),
and `data.texas.gov` (Texas's own state open-data portal, on the
chance TEC's data is mirrored there the way PDC's is on `data.wa.gov`).
**If none of those work either, Texas should be shelved** rather than
kept as an open item — there's no fourth path to try after that beyond
periodically re-checking whether TEC's site comes back.

### Integration plan: five state tabs (MA existing + WA/CA/CO new, TX pending) + one combined tab

**Per-state build** (repeats the existing MA pattern exactly, one state
at a time in this priority order — **Washington first** (cleanest API,
lowest implementation risk), **then Colorado** (also low-risk, flat
files), **then California** (real but larger/slower: a ~400 MB fetch
and the most complex schema of the three) — Texas only if unblocked):

1. `fetch_<state>.py` → `data/raw/<state>/*.jsonl` or `.csv`, mirroring
   `fetch_ocpf.py`'s integrity discipline (refuse to write a result
   that doesn't match the source's own reported total — Washington's
   `$select=count(*)` and Colorado's per-file row counts both support
   this the same way OCPF's `summary.count` does; California's
   `EXPN_CD.TSV` has no external count to check against, so its
   integrity check has to be "did the decompression finish without
   error" instead).
2. `parse_<state>.py` → match payee name + purpose/description text
   against the *same* `pipeline/config/vendors.yaml` taxonomy via
   `pipeline/lib/vendor_match.py`. No new taxonomy work. Each state
   also gets its own filer-level total-expenditure denominator (for a
   "% of total spend" stat), computed from whichever field the state
   provides (Washington and Colorado both look to have enough
   structure to sum all itemized expenditures per filer directly).
3. `build_dataset_<state>.py` → `docs/data/dashboard_<state>.json`,
   same shape as `dashboard_ma.json` (`vendors`, `vendors_detail`,
   `filers_detail`, `time_series`, `party_split`, era/confidence
   splits) so the existing MA-tab frontend code can be generalized
   rather than rewritten per state.
4. **Frontend**: a new dataset tab per state (`data-dataset="wa"`,
   `"ca"`, `"co"`), following the Massachusetts tab's own markup/JS
   pattern in `docs/index.html` and `docs/js/app.js`. Given three (soon
   four) tabs will share near-identical rendering logic, this is the
   point to factor the MA-tab rendering functions into a
   state-parameterized version rather than copy-pasting three more
   times — a real refactor, not just an addition, and should happen
   when Washington (the first new state) is built, not deferred.
5. Each state also gets added to `.github/workflows/refresh-data.yml`
   and the "How it works" / repo-layout sections of `README.md`.

**Combined-states tab (new, distinct from the existing Compare tab):**
a tab that unions *all* state-level datasets (MA + WA + CA + CO, and TX
if it ever unblocks) into one dataset — the state-level analog of how
the Federal tab already unions every House and Senate race into one
view, not a side-by-side comparison of two specific sources the way
Compare is. Concretely: `build_dataset_states.py` reads every
`dashboard_<state>.json` and produces `dashboard_states.json` with a
combined `vendors_overall` (summed across states, with a per-state
breakdown available on click-through, the same shape decision already
made for the Federal tab's own vendor detail pages), a combined time
series, and a state-by-state leaderboard (which state spends the most
on AI vendors, in total and as a share of that state's own spend).

This is a **new tab, not a change to Compare.** Compare's own code
(`buildCompareRows()` in `docs/js/app.js`) is hardcoded to exactly two
sources (`fed_amount`/`ma_amount` fields, two hardcoded columns) — it
was never built to generalize to N sources, and bolting a 3rd, 4th, 5th
state onto it would need the same kind of rework either way. Building
a separate, purpose-made "States" tab (state-level union, no federal
column) avoids conflating two different questions Compare and this new
tab actually answer — "how does federal compare to one state" vs. "how
much AI-vendor spend shows up across state races generally" — rather
than trying to force both into one increasingly overloaded table.
**Open question for the user**: once there are 4-5 state tabs plus
Federal, Compare, and States, that's 7-8 top-level tabs — worth
deciding whether the tab bar needs a grouping/overflow treatment (e.g.
a "States ▾" dropdown revealing MA/WA/CA/CO/TX, collapsing the bar back
down to Federal / States ▾ / Compare / States-combined) before or after
the first new state ships, rather than after all of them do.

### Revised domain list

Washington, California, and Colorado need **no further domains** — all
three are fully reachable and their real data-download paths are
confirmed. Only Texas has open candidates:

```
ethics.texas.gov
txethics.org
data.texas.gov
```

### Effort/risk, updated

- **Washington**: lowest risk. Real, documented Socrata API; closest
  analog to the OCPF build that's already proven out.
- **Colorado**: also low risk. Flat annual CSVs, closest analog to the
  FEC bulk-file pattern already proven out. Payee-name handling needs
  a touch more logic (split across `LastName`/`FirstName` vs.
  `CommitteeName`/business fields) but nothing new conceptually.
- **California**: real but the biggest lift — largest raw data volume
  (~400 MB fetch even with the range-request optimization), a single
  denormalized table needing careful parsing (`EXPN_CD.TSV`'s 50-plus
  columns cover several different form types in one table), and a
  daily-changing source with no external row-count to validate against.
  Also the highest expected AI-vendor dollar yield given California's
  size, so worth the extra effort.
- **Texas**: unknown until (if) unblocked.
- **Frontend refactor** (generalizing the MA-tab rendering code to be
  state-parameterized) is real, scoped work that should land with the
  first new state, not be deferred as tech debt across three more
  states' worth of copy-paste.
