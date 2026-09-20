# Federal Campaign Disclosure AI Dashboard

A GitHub Pages dashboard that reads public FEC campaign-finance disclosures for
U.S. House and Senate candidates to see how AI vendors show up in campaign
spending: which vendors, what they're reportedly used for, how usage differs
by party/incumbency/candidate age/chamber, and how each has changed across
recent election cycles.

Beyond the summary charts, the site supports drilling in: every vendor bar,
and every candidate name in the leaderboard tables, is a link to a detail
page (spend over time, by candidate, by committee, by party/incumbency) --
click through from a vendor to see exactly which committees are driving its
total, or from a candidate to their race. A `$` / `% of total spend` toggle
on the party/incumbency/chamber/age and time-series charts shows AI spend
against each slice's total reported campaign expenditure, not just a raw
dollar figure. Section 5 ("Leaderboards") is sortable/filterable (by cycle
and functional area) tables of the biggest AI spenders in dollar terms and
as a share of their budget.

A vendor's detail page also shows its own Democratic-vs-Republican spending
split (a pie chart, a "spending over time" line chart, and the underlying
ratio, restricted like the rest of the party breakdown to House/Senate
candidate committees), and every vendor table on the site carries a "D:R
ratio" column. Both a vendor's and a candidate's detail page list every
individual matched disbursement -- date, counterparty, amount, and the
FEC-filed **stated purpose** text itself (not just an aggregate) -- capped
at the 300 largest per entity.

A "Weekly disclosure timeline" chart (in the Trends section, and on the
Massachusetts tab) bins every matched disbursement by week two ways: when
the expenditure itself happened, and when the disclosure report that
covers it was filed. On Massachusetts these are both real OCPF-reported
dates; on the federal side there is no per-record filed date in the FEC's
bulk data, so the report date is a calendar-rule approximation from the
report type and year (see Methodology).

A **vendor co-occurrence matrix** (Section 1) shows which AI vendors tend to
get paid by the same committees, normalized as Jaccard similarity -- of the
committees that pay either vendor in a pair, the share that pay both --
rather than a raw shared-committee count, so a vendor with many payers
doesn't dominate the matrix just by being widely used. Covers the top 15
generative-era vendors by high-confidence spend.

Every vendor is also tagged with an **era**: `generative` (built on modern
LLM/diffusion/voice-clone AI) or `legacy` (a company that predates the
generative-AI wave and either still runs on older, non-generative technology
or bolted a generative feature onto a much older product -- e.g. Amplify.ai,
Prompt.io, CallTime.AI, Numero, EyesOver, Otter.ai, Chatfuel, Grammarly, and
Descript). Legacy-era vendors are **excluded from every chart and table by
default**, since lumping a 2014-era chatbot or a 2009 grammar checker in with
a campaign's ChatGPT or Claude subscription overstates how much reported
spending reflects current frontier-AI adoption. A toggle at the top of the
page adds them back into every chart and table; a vendor's own detail page
always shows its full history regardless, labeled with its era.

Section 6 ("Outside spending") covers a fundamentally different kind of
money: AI-vendor payments by Super PACs, hybrid PACs, and party committees on
a candidate's behalf, not the candidate's own campaign. Independent
expenditures (Schedule E) are legally uncoordinated with the candidate;
coordinated party expenditures (Schedule F) are a national/state party
committee spending on a candidate's behalf up to a statutory cap. Both use
the same vendor taxonomy and confidence tiers as the rest of the site, and a
matching candidate's own detail page calls out any outside AI spend found for
or against them.

The vendor taxonomy (see `pipeline/config/vendors.yaml` for sourcing) started
from vendors named in press coverage of AI usage in campaign filings, then was
substantially expanded by empirically mining the disclosures themselves for
AI-indicative language and researching the payee names that turned up.

**Live site:** enable GitHub Pages for this repo (Settings -> Pages -> Deploy
from branch -> `main` / `/docs`) and it will serve `docs/index.html`.

## State tabs (Massachusetts, Washington, Colorado, California)

Beyond Federal, the site has four fully separate state datasets, one tab
each (switcher at the top of the page, defaulting to **Federal**), each
reading a different state disclosure system and rendered by the same
shared, state-parameterized code in `docs/js/app.js`:

| State | Source | Bulk/API access |
| --- | --- | --- |
| Massachusetts | OCPF (Office of Campaign and Political Finance) | Public API, `api.ocpf.us` -- no bulk-file distribution |
| Washington | PDC (Public Disclosure Commission) | Public Socrata API, `data.wa.gov` |
| Colorado | TRACER (Secretary of State) | Plain annual bulk CSV.zip downloads, no auth |
| California | CAL-ACCESS (Secretary of State) | Daily bulk database export (a single ~1.5GB zip covering the entire legacy system); this pipeline reads only the one table it needs via HTTP range requests rather than downloading the whole archive |

Every state tab uses the same vendor taxonomy as the Federal tab, applied
unmodified, over each state's own date window (Massachusetts covers a
fixed window through the 2026 cycle; Washington/Colorado/California start
2023-01-01 with no fixed end, since none of the three uses federal-style
two-year cycles). None of the five datasets (Federal + 4 states) are ever
merged, and none are directly comparable dollar-for-dollar to each other --
different disclosure regime, different itemization floor, vastly different
scale. Every card carries its own "\<Dataset\> &middot; \<Source\>" pill so
which dataset a given chart belongs to is never ambiguous.

Two real, state-specific gaps, both documented on that state's own tab
(and in each `pipeline/build_dataset_<state>.py`'s methodology notes) rather
than worked around: Colorado's and California's bulk sources carry **no
party-affiliation field at all**, so every record on those two tabs shows
as "Unknown" party; and only Massachusetts's OCPF exposes a real per-report
filed date and a subcontractor-disclosure ("subvendor") layer, so the
weekly disclosure timeline and the "Subvendor payments tested" stat are
Massachusetts-only -- the other three tabs simply don't render those
cards/tiles rather than faking equivalents.

Like the Federal tab, every vendor name and filer name on a state tab is a
link to its own detail page (`#/<state>/vendor/<id>` /
`#/<state>/candidate/<id>`, e.g. `#/wa/vendor/openai` -- each state's
disclosure system calls the payer entity a "filer," almost always a
candidate committee, so it's labeled "candidate" here for consistency with
the Federal tab): spend over time, a Democratic-vs-Republican party split
(where the state has one), and every individual matched disbursement,
sortable, with a one-click link back to that record's own state filing.

The search bar at the top of the page is shared across all five datasets:
on a state tab it searches that state's own candidates and vendors only
(no "Races" filter, since state candidates aren't grouped into races here)
and its results link to that state's own detail pages instead of the
Federal ones.

Like the Federal tab's breakdown/trend charts, each state's yearly trend
chart has a `$` / `% of total spend` toggle. The denominator is each
filer's own total reported expenditure that year on that state's own
system -- every itemized record, not just AI-vendor matches -- summed, per
year, across the filers who show at least one AI-vendor disbursement that
year specifically, matching the Federal dashboard's "relative to AI-using
campaigns" framing. A filer's own detail page shows the same "AI as % of
total spend" stat the Federal candidate page does.

The legacy-vendor toggle (top of the page) is shared across every tab: off
by default, it hides legacy-era vendors (e.g. CallTime.AI, Grammarly,
Otter.ai) from each state's aggregate views the same way it does on
Federal -- the vendor chart and table, the yearly spending trend, and (on
Massachusetts) the party split pie and party-spending-over-time chart. As
on Federal, it does *not* filter the "Individual disclosed payments" table
(always shows every matched record, all eras and confidence tiers) nor a
vendor's or candidate's own detail page, which always shows its full
history regardless of the toggle.

Every record-level table on every tab (a vendor's or candidate's own
disbursement history, and the overview's notable-payments table) carries a
Confidence column alongside any legacy-vendor pill, so a reader can always
tell whether a given row is a high-confidence vendor-name match or a
lower-confidence match on an ambiguous word.

## States tab (combined)

A sixth tab unions all four state datasets into one view -- the state-level
analog of how the Federal tab already unions House and Senate races into
one view. Every figure on this tab is a **real sum of each state's own
already-disclosed records**, built by `pipeline/build_dataset_states.py`
from the four states' own dashboard JSON files, not an estimate: a combined
vendor table (each vendor's dollar total broken out by state, with each
state's own $ column linking to that vendor's detail page on that state's
tab), a combined year-over-year trend, a combined Democratic-vs-Republican
party split (Colorado and California contribute entirely to "Unknown,"
since neither discloses a party field), and a state-by-state leaderboard
(which state discloses the most AI-vendor spend, in total and as a share
of that state's own reported spend). There is no separate combined-states
vendor or candidate detail page -- drill-down always happens on the
relevant state's own tab.

## Compare tab

A seventh tab puts every AI vendor found on either the Federal or
Massachusetts tab into one sortable table: high-confidence dollars on each
dataset side by side, a "Combined volume" column (the two summed -- the
only place the two datasets' dollars are added together, since they cover
different offices, timeframes, and itemization rules), and a "Momentum"
column. Momentum splits a vendor's own time series (Federal: election
cycles; Massachusetts: calendar years) into an earlier and a more recent
half by period count, and compares the two halves' totals -- weighted
toward whichever dataset carries more of that vendor's spend when it
appears on both -- shown as a percentage, or as a multiplier ("14.2x")
once growth passes 3x, since a five- or six-digit percentage off a small
real base stops being a readable number. A vendor whose earlier half had
under $25 to compare against is labeled "New" instead, since a rate isn't
meaningfully computable that close to zero. Each row's `$` figures link to
that vendor's own Federal or Massachusetts detail page. (Compare stays
pinned to Federal vs. Massachusetts specifically, unlike the States tab
above -- it predates the other three states and was never generalized to
an N-way comparison.)

The table also carries two fields that exist only for this tab: a
`description` (one line, present tense, on how a campaign actually uses
the product) and 1-2 `tags` drawn from the same use-case-category
vocabulary already used to label disbursement purpose text elsewhere on
the site (see `pipeline/config/vendors.yaml`). Both are hand-written per
vendor, characterizing the product itself rather than any one payment's
stated purpose. Clicking a category tag filters the table to every vendor
carrying that tag (click it again, or the "Clear filter" button that
appears, to undo); every column header carries hover text spelling out
exactly what that column measures. Respects the same legacy-vendor toggle
as every other tab.

Below the vendor table, a **population-based national projection**
(`pipeline/build_projection.py`) scales this project's combined findings
across the four states it covers up to the full U.S. population, using
U.S. Census Bureau Vintage 2024 state population estimates
(`pipeline/config/state_population.py`): projected national AI-vendor
spend, projected candidate committees using AI, and a "vendor-adoption
instances" figure, each shown alongside the real covered-state numbers
they're scaled from. This is explicitly **not** a statistical estimate --
the four covered states skew toward itemization-rich disclosure systems
and Democratic-leaning delegations, California concentrates a
disproportionate share of the AI industry itself, and the vendor-count
figure in particular assumes linear growth with population rather than
the saturation a real 50-state count would show. The section's own
methodology notes (rendered in full on the page) spell out each caveat;
see them before citing any of these numbers.

## Job Postings tab (retired)

A fourth tab, scraping public campaign job boards for AI-related hiring
signal, was built and shipped, then retired: it's no longer on the live
site, and the GitHub Actions workflow no longer fetches or rebuilds its
data. The pipeline code (`pipeline/fetch_job_postings.py`,
`pipeline/build_dataset_jobs.py`, `pipeline/lib/job_ai_match.py`), the
scraped data (`data/processed/job_postings/*.jsonl`), and the full
methodology and findings (`planning/job-postings-plan.md`, including a
closing "Retired" section) all remain in the repository if anyone wants
to pick this back up.

Short version of why: across ~200 postings scraped, the signal was too
thin and too confounded to support the kind of claims a reader would
naturally draw from a dashboard. The large majority of postings came
from one source (RepublicanJobs.gop) that anonymizes every employer, so
its "Republican" tag couldn't be compared against the mostly-named
Democratic-side postings without comparing different kinds of evidence.
Within the AI-relevant postings themselves, most turned up at
organizations whose name or mission is literally about AI (an "AI think
tank," an "AI policy organization") rather than at ordinary campaigns
adopting AI as a tool -- a tautology that inflated the headline rate. And
a dedicated sweep of 166 individual competitive-race campaign sites,
built specifically to get past the aggregators' selection bias, turned
up exactly one real posting. See `planning/job-postings-plan.md` for the
full detail on all of the above.

## How it works

```
pipeline/fetch_fec_bulk.py           downloads FEC bulk data (candidate master,
                                      committee master, committee-candidate
                                      linkage, itemized Schedule B disbursements,
                                      the committee-to-committee "oth" file, and
                                      the independent-expenditure file) for each
                                      two-year cycle
pipeline/fetch_legislators.py        downloads unitedstates/congress-legislators
                                      (birthdates, for the age breakdown)
pipeline/parse_disbursements.py      scans Schedule B text for AI-vendor matches,
                                      and separately totals each committee's
                                      overall reported spending that cycle (the
                                      denominator for "% of total spend")
pipeline/parse_outside_spending.py   scans independent expenditures (Schedule E)
                                      and, within the "oth" file, coordinated
                                      party expenditures (Schedule F, transaction
                                      type 24C) for AI-vendor matches
pipeline/build_dataset.py            joins matches to candidate/committee
                                      reference data, aggregates, builds the
                                      vendor/candidate/race detail pages' data,
                                      and writes docs/data/dashboard.json
pipeline/fetch_ocpf.py               downloads Massachusetts OCPF itemized
                                      expenditure and subvendor records via
                                      api.ocpf.us for the 2024+2026 cycle window
pipeline/parse_ocpf.py               scans those records for AI-vendor matches;
                                      totals how many distinct filers reported
                                      any expenditure activity at all, and each
                                      filer's own total spend by year (every
                                      record, not just AI-vendor matches -- the
                                      % of total spend toggle's denominator)
pipeline/fetch_ocpf_report_dates.py  fetches each matched record's real
                                      report-filed date from OCPF's
                                      report/{reportId} endpoint, for the
                                      weekly disclosure timeline
pipeline/fetch_ocpf_filer_party.py   fetches each matched filer's major-party
                                      affiliation from OCPF's
                                      filer/payload/{cpfId} endpoint, for the
                                      Democratic-vs-Republican split
pipeline/build_dataset_ma.py         aggregates OCPF matches and writes
                                      docs/data/dashboard_ma.json (a separate
                                      file/schema from the federal dataset)
pipeline/fetch_wa.py                 downloads Washington PDC expenditure
                                      records via data.wa.gov's Socrata API
pipeline/parse_wa.py                 scans those records for AI-vendor
                                      matches; totals each filer's own total
                                      spend by year
pipeline/build_dataset_wa.py         aggregates WA matches (via the shared
                                      pipeline/lib/build_state_dataset.py,
                                      below) and writes
                                      docs/data/dashboard_wa.json
pipeline/fetch_co.py                 downloads Colorado TRACER's plain
                                      annual bulk expenditure CSV.zip files
pipeline/parse_co.py                 scans those records for AI-vendor
                                      matches; totals each filer's own total
                                      spend by year
pipeline/build_dataset_co.py         aggregates CO matches (shared
                                      aggregator) and writes
                                      docs/data/dashboard_co.json
pipeline/fetch_ca.py                 downloads just the EXPN (itemized
                                      expenditure) table out of California
                                      CAL-ACCESS's daily bulk export, via
                                      HTTP range requests against the zip's
                                      central directory -- avoids
                                      downloading the ~1.5GB full archive
pipeline/fetch_ca_filers.py          downloads CAL-ACCESS's much smaller
                                      per-filing cover-page table (needed
                                      because EXPN's own filer-id column is
                                      blank on nearly every row) to resolve
                                      each record's real filer identity
pipeline/parse_ca.py                 scans EXPN records for AI-vendor
                                      matches (joined against the filer
                                      lookup above); totals each filer's own
                                      total spend by year
pipeline/build_dataset_ca.py         aggregates CA matches (shared
                                      aggregator) and writes
                                      docs/data/dashboard_ca.json
pipeline/lib/build_state_dataset.py  shared vendor/filer/time-series rollup
                                      logic used by WA/CO/CA's own
                                      build_dataset_<state>.py (Massachusetts
                                      predates this and has its own OCPF-only
                                      extras -- subvendor payments, the
                                      weekly report-filed histogram -- with
                                      no equivalent elsewhere, so it isn't
                                      rebuilt on top of this shared function)
pipeline/build_dataset_states.py     unions all four state dashboards into
                                      docs/data/dashboard_states.json (a real
                                      sum of each state's own records, for
                                      the combined States tab)
pipeline/build_projection.py         scales the four states' combined
                                      findings up to the full U.S. population
                                      (pipeline/config/state_population.py,
                                      Census Bureau Vintage 2024 estimates)
                                      and writes
                                      docs/data/dashboard_projection.json,
                                      for the Compare tab's population
                                      projection section
docs/                                the static site (GitHub Pages source);
                                      reads docs/data/dashboard.json and
                                      each docs/data/dashboard_<id>.json
                                      client-side
```

(`pipeline/fetch_job_postings.py` and `pipeline/build_dataset_jobs.py`
also exist but are no longer run by the workflow -- see "Job Postings
tab (retired)" above.)

Run the whole pipeline locally:

```
pip install -r pipeline/requirements.txt
python pipeline/fetch_fec_bulk.py
python pipeline/fetch_legislators.py
python pipeline/parse_disbursements.py
python pipeline/parse_outside_spending.py
python pipeline/build_dataset.py
python pipeline/fetch_ocpf.py
python pipeline/parse_ocpf.py
python pipeline/fetch_ocpf_report_dates.py
python pipeline/fetch_ocpf_filer_party.py
python pipeline/build_dataset_ma.py
python pipeline/fetch_wa.py
python pipeline/parse_wa.py
python pipeline/build_dataset_wa.py
python pipeline/fetch_co.py
python pipeline/parse_co.py
python pipeline/build_dataset_co.py
python pipeline/fetch_ca.py
python pipeline/fetch_ca_filers.py
python pipeline/parse_ca.py
python pipeline/build_dataset_ca.py
python pipeline/build_dataset_states.py
python pipeline/build_projection.py
```

(California's `fetch_ca.py` is the slowest step by far -- it streams
through CAL-ACCESS's full ~15M-row itemized-expenditure history to filter
down to 2023 onward, which takes several minutes even with the
range-request optimization that avoids downloading the full archive.)

`.github/workflows/refresh-data.yml` runs this weekly and commits every
updated `docs/data/dashboard*.json` file, so the site stays current as new
filings land.

## Data sources

- FEC bulk data (no API key required): https://www.fec.gov/data/browse-data/?tab=bulk-data
  - `oppexp` -- itemized operating expenditures (Schedule B) -- where AI
    vendor payments show up
  - `cn` -- candidate master (party, office, incumbency status)
  - `ccl` -- candidate-committee linkage
  - `cm` -- committee master (for PACs/party committees not linked to a
    candidate, e.g. the RNC/DNC)
  - `independent_expenditure_{cycle}.csv` -- Schedule E, independent
    expenditures by Super PACs/hybrid PACs for or against a candidate
  - `oth` -- "any transaction from one committee to another," filtered to
    transaction type `24C` for Schedule F coordinated party expenditures
    (there is no dedicated bulk file for Schedule F alone)
- [unitedstates/congress-legislators](https://github.com/unitedstates/congress-legislators)
  -- birthdates, for the candidate-age breakdown (public domain)
- Massachusetts OCPF public API (`api.ocpf.us/search/items`, no key
  required) -- itemized expenditure (`SearchTypeCategory=B`) and subvendor
  (`SearchTypeCategory=S`) records; powers the Massachusetts tab only, kept
  fully separate from the FEC-sourced data above. Two more OCPF endpoints
  are used for matched records only: `report/{reportId}` (each report's
  real filed date) and `filer/payload/{cpfId}` (each filer's major-party
  affiliation).
- Washington PDC's documented Socrata SODA API (`data.wa.gov`, dataset
  `tijg-9zyp`, no key required) -- itemized expenditure records, paginated.
- Colorado TRACER's plain annual bulk downloads
  (`tracer.sos.colorado.gov/PublicSite/Docs/BulkDataDownloads/`), one
  `{year}_ExpenditureData.csv.zip` per year, no API or auth.
- California CAL-ACCESS's daily bulk database export
  (`campaignfinance.cdn.sos.ca.gov/dbwebexport.zip`) -- the entire legacy
  system in one ~1.5GB zip, 130+ tables. This pipeline fetches only two of
  them, both via HTTP range requests against the zip's central directory
  rather than downloading the whole archive: `EXPN_CD.TSV` (itemized
  expenditures) and the much smaller `CVR_CAMPAIGN_DISCLOSURE_CD.TSV`
  (each filing's cover page, needed to resolve filer identity -- see
  `pipeline/fetch_ca_filers.py`'s own docstring for why EXPN's own
  filer-id column can't be used directly).
- U.S. Census Bureau Vintage 2024 national and state population estimates
  (`census.gov/newsroom/press-kits/2024/national-state-population-estimates.html`)
  -- static reference data in `pipeline/config/state_population.py`, used
  only to build the Compare tab's population projection.

## Methodology, in brief

- A disbursement counts as an "AI-related" match if its payee name, purpose,
  category description, or memo text matches a pattern in
  `pipeline/config/vendors.yaml`. This is text matching against disclosure
  fields, not a review of underlying invoices or documents.
- Matches are split into **high confidence** (unambiguous vendor/product
  names, e.g. "OpenAI", "Quiller") and **medium confidence** (ambiguous words
  that also have ordinary non-AI meanings, e.g. "Gemini", "Copilot", "Grok",
  "Claude"). Only high-confidence matches feed the party/incumbency/chamber/
  age/use-case/time-series breakdowns; medium-confidence matches are shown
  separately in the vendor landscape table only.
- Every vendor also has an `era`: `generative` or `legacy` -- see
  `pipeline/config/vendors.yaml` for the founding-year research behind each
  call. Legacy-era vendors are excluded from every chart, table, and
  headline stat by default; a toggle at the top of the dashboard includes
  them, and a vendor's own detail page always shows its full history either
  way.
- Party, chamber, and incumbency breakdowns cover House and Senate candidate
  committees only (linked via the FEC's own candidate-committee linkage
  file), so they exclude PAC- and party-committee spending (which is still
  visible in the "top committees" table).
- Candidate age comes from the congress-legislators project, which covers
  people who have served in Congress. Non-incumbent challengers who have
  never held office generally are not in that dataset, so the age breakdown
  skews toward incumbents/former members; unknown ages are left unknown
  rather than estimated.
- Disclosed AI spending likely understates actual usage -- campaigns can pay
  for AI tools via corporate cards, staff reimbursement, or consultants
  without the vendor ever appearing in
  itemized disbursement text.
- The vendor and use-case taxonomies are a curated starting point (see the
  comments in `pipeline/config/vendors.yaml` for sourcing), not an
  exhaustive registry. Extend that file as new vendors surface.
- General-purpose cloud hosting (AWS, Azure, Google Cloud) is deliberately
  **not** counted as AI spend just because the provider also sells AI
  products -- only a disbursement naming a specific AI service (e.g. "AWS
  Bedrock", "Azure OpenAI") counts. Scanning all four cycles found zero such
  mentions; plain "hosting"/"cloud" line items for these providers are
  common but don't say which service was used. Google's Gemini is also
  frequently bundled into an existing Google Workspace subscription, so it
  rarely gets its own line item the way a standalone ChatGPT or Claude
  subscription does -- a real limitation of disbursement-text analysis, not
  evidence Google is used less.
- "% of total spend" divides AI spend by each committee's total reported
  operating expenditure that cycle (FEC memo entries excluded, since they
  re-describe part of a lump-sum payment already counted elsewhere -- see
  the comments in `parse_disbursements.py`). For the party/incumbency/
  chamber/age/time-series charts, the denominator is the combined spend of
  the House/Senate candidates in that slice who show at least one AI-vendor
  disbursement -- not of every House/Senate candidate that cycle -- so it
  answers "how big is AI spend relative to everything these AI-using
  campaigns spend," not "what share of all campaign spending nationally
  goes to AI."
- The weekly disclosure timeline's federal "report filed" series is an
  **approximation**, not a disclosed fact: the FEC's bulk `oppexp` file has
  no per-record filed date, only a report-type code (`RPT_TP`) and year, so
  `pipeline/lib/fec_report_dates.py` maps each code to that report type's
  statutory/calendar due date (e.g. general-election Tuesday, quarterly
  deadlines). Massachusetts's equivalent series uses OCPF's own real
  `dateFiled` field instead, fetched per report.
- The Democratic-vs-Republican split restricts to House/Senate candidate
  committees on the federal side (same scope as the other party breakdowns).
  On Massachusetts, OCPF's expenditure records carry no party field at all,
  so the split is joined in from each filer's own `partyAffiliation` on
  OCPF's filer record (fetched once per distinct filer, not per record);
  filers OCPF doesn't mark with a major-party affiliation (ballot-question
  committees, PACs, and others) are excluded from the split entirely rather
  than counted as a third category.
- "Outside spending" (independent expenditures and coordinated party
  expenditures) is spending by someone other than the candidate's own
  campaign and is kept structurally separate from every other number on the
  site -- never summed into a candidate's own totals. Schedule E's bulk file
  explicitly warns it contains both original and amended reports without
  removing the originals; this pipeline drops every filing a later amendment
  superseded (tracked via `PREV_FILE_NUM`). Schedule F's source file (`oth`)
  has no purpose field, so its category/use-case labeling is thinner than
  elsewhere on the site, and matching found exactly one qualifying
  high-confidence payment across four cycles -- coordinated party spending
  is capped by statute and, in what we found, goes overwhelmingly to
  traditional media buyers rather than named AI vendors.
- Colorado's and California's bulk sources carry no party field at all
  (unlike Massachusetts and Washington, which do), so every record on
  those two tabs -- and every Colorado/California contribution to the
  States and Compare tabs' combined party splits -- shows as "Unknown."
- California's EXPN table's own filer-id column (`CMTE_ID`) is blank on
  nearly every row; `pipeline/parse_ca.py` resolves real filer identity by
  joining each record's `FILING_ID` against a separate cover-page table
  (`pipeline/fetch_ca_filers.py`). A small number of filings without a
  resolvable cover page fall back to "Committee \<FILING_ID\>" with no
  real name.
- California's data surfaced the largest false-positive source found on
  this site: ActBlue-style "Earmarked Contribution from: LASTNAME,
  FIRSTNAME" passthrough-donation boilerplate makes up 68.6% of all raw
  California expenditure records, and donors' own first/last names
  routinely collide with bare vendor patterns purely by coincidence (e.g.
  257 of an initial 266 "Anthropic" matches were donors literally named
  Claude). `parse_ca.py` excludes that boilerplate from vendor matching
  entirely rather than chasing individual name collisions.
- The population-based national projection on the Compare tab is a
  simple population-weighted scale-up of the four states this site
  covers, not a statistical estimate -- see that section's own rendered
  methodology notes (or `pipeline/build_projection.py`'s docstring) for
  the specific ways the four covered states aren't a representative
  sample of the country.

## Repo layout

```
pipeline/                 the data pipeline (Python)
  config/vendors.yaml      AI vendor + use-case taxonomy, with sourcing notes
  config/state_population.py
                          Census Bureau Vintage 2024 population estimates,
                          used only by build_projection.py
  config/battleground_candidates_2026.json
                          roster of competitive-race candidates + campaign
                          website domains, built for the now-retired job-
                          postings feature (see "Job Postings tab (retired)")
  lib/                     shared helpers (FEC schema, vendor matching,
                          reference data, and build_state_dataset.py -- the
                          shared WA/CO/CA aggregator)
data/raw/                 downloaded FEC/legislators/state source files
                          (gitignored, large); wa/, co/, ca/ subdirectories
                          hold each state's own raw fetch output
data/processed/           filtered AI-vendor-match CSVs and per-committee/
                          per-spender total-expenditure CSVs, per cycle
                          (committed, small); ocpf_*.csv are the Massachusetts
                          equivalents (not split by cycle), including
                          ocpf_report_dates.csv, ocpf_filer_party.csv, and
                          ocpf_filer_year_totals.csv; wa_*.csv/co_*.csv/
                          ca_*.csv are the Washington/Colorado/California
                          equivalents
  job_postings/*.jsonl     scraped job postings from the retired job-postings
                          feature (kept for reference; no longer rebuilt)
docs/                     GitHub Pages site
  index.html, css/, js/    static dashboard (vanilla JS + a vendored Chart.js
                          build); app.js's state-tab rendering is shared/
                          parameterized across all four state dashboards,
                          not one module per state
  data/dashboard.json      aggregated federal data the site reads
  data/dashboard_ma.json   aggregated Massachusetts data (separate file/schema)
  data/dashboard_wa.json, dashboard_co.json, dashboard_ca.json
                          aggregated Washington/Colorado/California data
                          (same shared schema as each other, produced by
                          pipeline/lib/build_state_dataset.py)
  data/dashboard_states.json
                          the four state dashboards above, unioned into one
                          combined view (States tab)
  data/dashboard_projection.json
                          the population-based national projection shown on
                          the Compare tab
planning/                 scoping docs for signals not yet (or partially)
                          built, or built and retired -- state expansion,
                          job postings, vendor-directory mining
```
