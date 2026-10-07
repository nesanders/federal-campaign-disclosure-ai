# Federal vendors, one layer down

Exploratory analysis; nothing here feeds the site in `docs/`.

FEC filings show what a federal campaign paid its consultants, but not what those consultants paid others. Massachusetts (OCPF subvendor reports) and California (CAL-ACCESS payments made by an agent or contractor on a committee's behalf) require that next layer. This analysis takes every firm federal campaigns paid and looks it up in those state filings to see what tools and services sit underneath.

## Run

```
python3 analysis/subvendors/federal_vendors.py   # FEC Schedule B 2020-26 -> out/federal_vendors.csv, out/name_merges.csv
python3 analysis/subvendors/state_subvendors.py  # MA + CA subvendor rows matched to federal vendors
python3 analysis/subvendors/report.py            # out/findings.md
```

The scripts need `data/raw/{2020,2022,2024,2026}/{oppexp,ccl,cm}.txt`, the MA subvendor data, and `data/raw/ca/expn.jsonl` + `filer_lookup.json`.

## Method

- **Federal side.** Every non-individual payee on FEC Schedule B. Memo entries (`MEMO_CD = X`) are excluded. Names are normalized (`names.py`). Variants of one firm ("Middle Seat", "Middle Seat Consulting") are merged when they share a home state; every merge is logged in `out/name_merges.csv`.
- **State side.** MA subvendor reports, plus CA expenditure rows that name an agent. CA rows keep only the latest amendment of each filing, since CAL-ACCESS stores every amendment.
- **Matching.** Firm names are matched exactly, then by merged alias, then by a conservative fuzzy match. Every fuzzy match is logged in `out/fuzzy_matches.csv`, and rejected pairs are listed in `state_subvendors.py`.
- **Pass-throughs.** Credit cards, payroll processors, and ActBlue/WinRed are flagged as pass-throughs and kept out of the totals.
- **AI.** Subvendor names and purposes are run through the project's AI vendor taxonomy (high confidence only). Generic AI language is also flagged, and those rows are reviewed by hand.

## Caveats

- A firm's state subvendor detail describes its state clients, not any particular federal campaign.
- Only MA and CA require this layer. A firm with no MA/CA work is invisible here, as is any federal account a firm runs without passing costs through to a state committee.
- Ad platforms (Google, Meta, The Trade Desk, TV stations) dominate the subvendor layer. Their AI (bidding, targeting, creative tools) is built in and never appears as a line item.
- Agencies' public AI claims (see below) are marketing, not disclosures.

## Web research on the focus candidates' firms (Oct 2026)

These claims come from the firms' or vendors' own public materials:

| Firm | Focus candidates | Public AI claims |
|---|---|---|
| Peerly | Trump, RFK Jr. | Markets "AMP AI" (built on Google Gemini) and Canvasser AI. Not in the taxonomy. |
| Cygnal | Trump, Cotton | Acquired Response:AI (2021). Markets AI-driven message testing. |
| Targeted Victory | Sullivan, Cotton | Has an in-house AI/ML lead. Uses generative AI for fundraising email and ad content. Co-founder Zac Moffatt co-leads the Leading the Future pro-AI super PAC network. |
| GMMB | Biden | Lists "Targeting, Data Science & AI" as a service. An executive has publicly discussed synthetic audiences and agentic ad buying. |
| Beacon Research (subvendor CloudResearch) | — | CloudResearch names Beacon as a partner for AI-moderated voter interviews. This matches Beacon's MA filings. |
| AI Digital (Gilliard Blanning subvendor) | — | Markets itself as an "AI-native" CTV/programmatic buyer. |
| Dynata (Fabrizio Lee subvendor) | — | Markets AI survey tools and selective synthetic data. |
| Middle Seat, Left Hook, Aisle 518, Thematic, Gambit, HSP Direct, LC Media, Swing, Red Dog | various | No public AI claims found. |
