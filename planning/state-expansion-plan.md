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
