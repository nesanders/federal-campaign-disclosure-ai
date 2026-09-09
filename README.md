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
pipeline/parse_ocpf.py               scans those records for AI-vendor matches
                                      and totals how many distinct filers
                                      reported any expenditure activity at all
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
  fully separate from the FEC-sourced data above

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
                          equivalents (not split by cycle)
docs/                     GitHub Pages site
  index.html, css/, js/    static dashboard (vanilla JS + a vendored Chart.js build)
  data/dashboard.json      aggregated federal data the site reads
  data/dashboard_ma.json   aggregated Massachusetts data (separate file/schema)
```
