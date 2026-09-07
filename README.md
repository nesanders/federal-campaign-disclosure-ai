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

This extends the Washington Post's September 2026 reporting on OpenAI/ChatGPT
spending in campaign filings (see `pipeline/config/vendors.yaml` for sourcing)
to a broader vendor taxonomy and a fuller set of cross-cuts, using the same
kind of public disclosure data the Post used.

**Live site:** enable GitHub Pages for this repo (Settings -> Pages -> Deploy
from branch -> `main` / `/docs`) and it will serve `docs/index.html`.

## How it works

```
pipeline/fetch_fec_bulk.py       downloads FEC bulk data (candidate master,
                                  committee master, committee-candidate
                                  linkage, itemized Schedule B disbursements)
                                  for each two-year cycle
pipeline/fetch_legislators.py    downloads unitedstates/congress-legislators
                                  (birthdates, for the age breakdown)
pipeline/parse_disbursements.py  scans Schedule B text for AI-vendor matches,
                                  and separately totals each committee's
                                  overall reported spending that cycle (the
                                  denominator for "% of total spend")
pipeline/build_dataset.py        joins matches to candidate/committee
                                  reference data, aggregates, builds the
                                  vendor/candidate/race detail pages' data,
                                  and writes docs/data/dashboard.json
docs/                            the static site (GitHub Pages source);
                                  reads docs/data/dashboard.json client-side
```

Run the whole pipeline locally:

```
pip install -r pipeline/requirements.txt
python pipeline/fetch_fec_bulk.py
python pipeline/fetch_legislators.py
python pipeline/parse_disbursements.py
python pipeline/build_dataset.py
```

`.github/workflows/refresh-data.yml` runs this weekly and commits the updated
`docs/data/dashboard.json`, so the site stays current as new filings land.

## Data sources

- FEC bulk data (no API key required): https://www.fec.gov/data/browse-data/?tab=bulk-data
  - `oppexp` -- itemized operating expenditures (Schedule B) -- where AI
    vendor payments show up
  - `cn` -- candidate master (party, office, incumbency status)
  - `ccl` -- candidate-committee linkage
  - `cm` -- committee master (for PACs/party committees not linked to a
    candidate, e.g. the RNC/DNC)
- [unitedstates/congress-legislators](https://github.com/unitedstates/congress-legislators)
  -- birthdates, for the candidate-age breakdown (public domain)

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
- Party, chamber, and incumbency breakdowns cover House and Senate candidate
  committees only (linked via the FEC's own candidate-committee linkage
  file), so they exclude PAC- and party-committee spending (which is still
  visible in the "top committees" table).
- Candidate age comes from the congress-legislators project, which covers
  people who have served in Congress. Non-incumbent challengers who have
  never held office generally are not in that dataset, so the age breakdown
  skews toward incumbents/former members; unknown ages are left unknown
  rather than estimated.
- As with the Post's original analysis, disclosed AI spending understates
  actual usage -- campaigns can pay for AI tools via corporate cards, staff
  reimbursement, or consultants without the vendor ever appearing in
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

## Repo layout

```
pipeline/                 the data pipeline (Python)
  config/vendors.yaml      AI vendor + use-case taxonomy, with sourcing notes
  lib/                     shared helpers (FEC schema, vendor matching, reference data)
data/raw/                 downloaded FEC/legislators source files (gitignored, large)
data/processed/           filtered AI-vendor-match CSVs and per-committee
                          total-expenditure CSVs, per cycle (committed, small)
docs/                     GitHub Pages site
  index.html, css/, js/    static dashboard (vanilla JS + a vendored Chart.js build)
  data/dashboard.json      aggregated data the site reads
```
