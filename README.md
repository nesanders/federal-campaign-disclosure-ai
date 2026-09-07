# Federal Campaign Disclosure AI Dashboard

A GitHub Pages dashboard that reads public FEC campaign-finance disclosures for
U.S. House and Senate candidates to see how AI vendors show up in campaign
spending: which vendors, what they're reportedly used for, how usage differs
by party/incumbency/candidate age/chamber, and how each has changed across
recent election cycles.

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
pipeline/parse_disbursements.py  scans Schedule B text for AI-vendor matches
                                  using pipeline/config/vendors.yaml
pipeline/build_dataset.py        joins matches to candidate/committee
                                  reference data, aggregates, and writes
                                  docs/data/dashboard.json
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

## Repo layout

```
pipeline/                 the data pipeline (Python)
  config/vendors.yaml      AI vendor + use-case taxonomy, with sourcing notes
  lib/                     shared helpers (FEC schema, vendor matching, reference data)
data/raw/                 downloaded FEC/legislators source files (gitignored, large)
data/processed/           filtered AI-vendor-match CSVs per cycle (committed, small)
docs/                     GitHub Pages site
  index.html, css/, js/    static dashboard (vanilla JS + a vendored Chart.js build)
  data/dashboard.json      aggregated data the site reads
```
