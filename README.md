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

## Massachusetts tab

The site has a second, fully separate dataset: a **Massachusetts** tab
(switcher at the top of the page, defaulting to **Federal**) reading itemized
expenditure and subvendor records from OCPF, the Massachusetts Office of
Campaign and Political Finance, via its public API (`api.ocpf.us`) --
Massachusetts has no bulk-file distribution comparable to the FEC's. It uses
the same vendor taxonomy as the federal side, applied unmodified, over a
fixed date window covering the 2024 and 2026 cycles (OCPF filers report
continuously rather than in discrete federal-style two-year cycles).

The two datasets are never merged and are not directly comparable
dollar-for-dollar -- different disclosure regime, different itemization
floor ($50 per item at OCPF vs. FEC's effective $200/payee/cycle), vastly
different scale. Every card on the Massachusetts tab carries its own
"Massachusetts &middot; OCPF" pill (and every federal card a matching
"Federal &middot; FEC" one) so which dataset a given chart belongs to is
never ambiguous.

Like the Federal tab, every vendor name and filer name on the Massachusetts
tab is a link to its own detail page (`#/ma/vendor/<id>` /
`#/ma/candidate/<id>` -- OCPF calls the entity a "filer," almost always a
candidate committee, so it's labeled "candidate" here for consistency with
the Federal tab): spend over time, a Democratic-vs-Republican party split,
and every individual matched disbursement, sortable, with a one-click link
back to that record's own OCPF filing.

The search bar at the top of the page is shared by both tabs: on
Massachusetts it searches MA candidates and vendors (no "Races" filter,
since MA candidates aren't grouped into races here) and its results link to
the MA detail pages above instead of the Federal ones.

Like the Federal tab's breakdown/trend charts, the Massachusetts yearly
trend chart has a `$` / `% of total spend` toggle. The denominator is each
filer's own total reported OCPF expenditure that year -- every itemized
record, not just AI-vendor matches (`ocpf_filer_year_totals.csv`, the same
role `parse_disbursements.py`'s committee totals play for the federal
dashboard) -- summed, per year, across the filers who show at least one
AI-vendor disbursement that year specifically, matching the federal
dashboard's "relative to AI-using campaigns" framing. A filer's own detail
page shows the same "AI as % of total spend" stat the federal candidate
page does.

The legacy-vendor toggle (top of the page) is shared by both tabs too: off
by default, it hides legacy-era vendors (e.g. CallTime.AI, Grammarly,
Otter.ai) from the Massachusetts vendor chart and table the same way it
hides them from every Federal chart and table, and a legacy vendor's own
detail page still always shows its full history regardless.

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
docs/                                the static site (GitHub Pages source);
                                      reads docs/data/dashboard.json and
                                      docs/data/dashboard_ma.json client-side
```

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
```

`.github/workflows/refresh-data.yml` runs this weekly and commits the updated
`docs/data/dashboard.json` and `docs/data/dashboard_ma.json`, so the site
stays current as new filings land.

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

## Repo layout

```
pipeline/                 the data pipeline (Python)
  config/vendors.yaml      AI vendor + use-case taxonomy, with sourcing notes
  lib/                     shared helpers (FEC schema, vendor matching, reference data)
data/raw/                 downloaded FEC/legislators source files (gitignored, large)
data/processed/           filtered AI-vendor-match CSVs and per-committee/
                          per-spender total-expenditure CSVs, per cycle
                          (committed, small); ocpf_*.csv are the Massachusetts
                          equivalents (not split by cycle), including
                          ocpf_report_dates.csv, ocpf_filer_party.csv, and
                          ocpf_filer_year_totals.csv
docs/                     GitHub Pages site
  index.html, css/, js/    static dashboard (vanilla JS + a vendored Chart.js build)
  data/dashboard.json      aggregated federal data the site reads
  data/dashboard_ma.json   aggregated Massachusetts data (separate file/schema)
```
