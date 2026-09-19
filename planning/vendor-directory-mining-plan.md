# Plan: Mine known political-tech directories for new AI vendors

## Objective

`pipeline/config/vendors.yaml` has been built in four documented passes:
press coverage, empirical corpus-mining of FEC text, a partisan-balance
check, and empirical corpus-mining of OCPF text. This is a proposed **fifth
pass**: rather than mining the disclosure text itself, mine curated,
purpose-built industry directories of political AI tools for candidate
vendor names, then verify each one against the existing FEC/OCPF corpora
before adding it — the same verification bar every existing entry already
had to clear (e.g. Robocent and HubDialer were investigated and explicitly
*rejected* because they aren't AI-branded).

This is the lowest-effort, highest-leverage of the three options scoped
this round: it needs **no new pipeline infrastructure**. It only produces
new `vendors.yaml` entries, which flow through the existing
`vendor_match.py` → `build_dataset.py` / `build_dataset_ma.py` → Compare
tab pipeline unchanged.

## Candidate directories

| Source | Alignment | What it offers |
|---|---|---|
| **Arena's AI Campaign Stack** (`arena.run/tool/ai-campaign-stack`) | Progressive/Democratic | A community-curated directory specifically of AI tools for progressive campaigns. Already confirmed (via web search) to include Quiller, CallTime.AI, Change Agent AI, Daisychain, RivalMind, BattlegroundAI, and DonorAtlas — all already in `vendors.yaml`, a good sanity check that prior research was thorough. Worth a systematic pass for anything listed but not yet captured. |
| **Tech.GOP** (`www.tech.gop`) | Republican | The official Republican campaign-tech directory. Search surfaced candidate names not currently in the taxonomy: **LocalistAI**, **aconservative.ai**, Numinar, Buzz360, Vottiv, Proximity. |
| **aconservative.ai** | Republican | A vendor site explicitly branded "AI-Powered Campaign Tools, Built by Conservatives, for Conservatives" — worth checking directly for its own product name(s) and any sub-vendors/partners it lists. |
| **Higher Ground Labs** (`highergroundlabs.com`) | Progressive/Democratic | A Democratic-aligned campaign-tech accelerator/investor; likely publishes a portfolio list, parallel to Startup Caucus on the GOP side. |
| **Startup Caucus** (`startupcaucus.com`) | Republican | GOP campaign-tech investment fund/incubator; likely has its own portfolio list, the GOP-side parallel to Higher Ground Labs. Surfaced in research but not yet loaded. |
| Arena's full catalogue (`arena.run/catalogue`), beyond just the AI Campaign Stack page | Progressive/Democratic | Broader than just the AI-specific sub-page; may list AI-branded vendors under other categories too. |

## Data access

All six domains were network-tested this session and are **currently
blocked by the outbound proxy** (`CONNECT tunnel failed, response 403`),
the same block every non-allowlisted domain returned; existing pipeline
domains (`api.ocpf.us`, `www.fec.gov`) returned real responses in the same
test, confirming this is a domain-allowlist gap only.

| Domain | Purpose | Status |
|---|---|---|
| `arena.run` | AI Campaign Stack + full political-tech catalogue | Blocked, needs safelisting |
| `www.tech.gop` | Republican campaign-tech directory | Blocked, needs safelisting |
| `aconservative.ai` | GOP-aligned AI vendor site | Blocked, needs safelisting |
| `highergroundlabs.com` | Democratic-aligned campaign-tech accelerator | Blocked, needs safelisting |
| `startupcaucus.com` | GOP-aligned campaign-tech investment fund | Blocked, needs safelisting |

These are read-only content pages, not APIs — no pagination/rate-limit
design needed, just fetching a handful of directory pages.

## Proposed process

This is a research/curation task, not a code-pipeline task, following the
same method `vendors.yaml`'s own comment header documents for its prior
passes:

1. **Load each directory page** and extract every distinctly-named
   product/vendor listed (not generic categories).
2. **Cross-check against `vendors.yaml`'s existing 50 entries** to find
   what's genuinely new. (Expect meaningful overlap on the Arena/Higher
   Ground Labs side, per the search-result spot-check above; Tech.GOP and
   aconservative.ai are the more likely sources of new names, since the
   taxonomy's own GOP-side research to date has been narrower — see
   `vendors.yaml`'s "third pass" note.)
3. **For each new candidate name**, apply the same verification bar every
   existing entry met before being added:
   - Confirm it as a real, distinct company/product (not a rebrand or
     sub-brand already covered).
   - Search the *existing* raw FEC (`data/raw/fec/`) and OCPF
     (`data/raw/ocpf/`) corpora already downloaded by this pipeline for the
     candidate name as a payee/purpose string — no new fetch needed, this
     reuses data already on disk.
   - If it appears: research its founding year / product generation to
     assign `era` (generative vs. legacy), assign a `group`
     (general_purpose vs. political_specific), write the same
     one-line `description` + `tags` fields added for the Compare tab, and
     add high/medium-confidence match patterns (with word-boundary and
     `exclude` handling for any ordinary-word collisions, exactly as
     documented throughout the existing file).
   - If it does *not* appear in the existing corpora: still worth adding
     proactively if the product is confirmed real and AI-branded, the same
     precedent `votersai` already sets ("too new to have surfaced in this
     dataset yet... added proactively").
4. **Re-run `parse_disbursements.py` / `parse_ocpf.py` and
   `build_dataset.py` / `build_dataset_ma.py`** (no re-fetch needed — this
   only changes the taxonomy, not the raw data) to pick up any newly-matched
   records, then verify visually in-browser as this session's established
   discipline requires before any commit.

## Risks / open questions

- **False-positive risk from directory listings.** A directory listing a
  tool as "AI-powered" is marketing copy, not proof — the same standard
  applied to CallTime.AI, Amplify.ai, etc. (era research showing they
  predate generative AI) needs to apply to any new find; a listing site
  calling something "AI" doesn't override the project's own era/confidence
  methodology.
- **Overlap is likely high** on the Democratic-aligned sources (Arena,
  Higher Ground Labs), since those were exactly the kind of press-adjacent
  sources the original taxonomy build already drew from. The GOP-aligned
  sources (Tech.GOP, aconservative.ai, Startup Caucus) are more likely to
  yield genuinely new names, given the taxonomy's own documented history of
  the Democratic-aligned discovery process outpacing the Republican-aligned
  one until the dedicated "third pass."
- **No guarantee any new name shows a real dollar match** — some, once
  checked against the existing corpora, may simply not appear (too new,
  too low-volume, or not actually paid by name in a filing), which is
  itself a legitimate, documentable finding, not a wasted step.

## Effort estimate

Smallest of the three plans. A single research pass across five-six
directory pages, cross-referenced against the existing 50-entry taxonomy
and the already-downloaded raw corpora, likely yields somewhere between
zero and a handful of genuinely new, verifiable vendors. No new
infrastructure, no new domains needed on an ongoing basis (this isn't a
recurring fetch — once mined, these directories don't need to be
re-scraped on a schedule the way FEC/OCPF data does).

## Immediate next step

Safelist all five domains above (they're all read-only reference pages,
low risk) and do the directory-reading pass — this is the fastest of the
three plans to actually start producing results.

## Verification results (2026-09-19)

Four of five domains were safelisted and read successfully; the directory
pass produced real candidate names, cross-checked against the current
50-entry `vendors.yaml`.

| Domain | Status | Finding |
|---|---|---|
| `arena.run` | ✅ Reachable | Confirmed 12 named tools. 10 already in `vendors.yaml` (Quiller, CallTime.AI, Change Agent AI, Daisychain, RivalMind, BattlegroundAI, DonorAtlas, Anthropic/Claude, Perplexity, Descript) — good validation the prior research held up. **Two new candidates: Grow Progress, Notion AI.** |
| `aconservative.ai` | ✅ Reachable | No new distinctly-AI-branded *product* beyond the site itself. It's built on GoHighLevel (generic SaaS infrastructure, not AI-specific — not a taxonomy candidate on its own). `aconservative.ai` itself is a borderline candidate: real, explicitly AI-branded, but unclear what payee name would actually appear in an FEC/OCPF filing for a service like this — needs a direct corpus search before deciding. |
| `highergroundlabs.com` | ✅ Reachable | Richest single source — 20 named tools. Most are new to the taxonomy. Highest-confidence new candidates (multiple mentions and/or explicit AI/ML branding in their own description): **Grow Progress** (2nd mention, strong signal), **Change Research** ("custom AI targeting"), **Fathom** (real, known AI meeting-transcription product), **Swayable** (real, known ML-based ad-testing company), **INTRVL** (explicit "machine learning" branding), **New/Mode** (explicit "AI strategist" in its own description). Lower-confidence / needs individual verification: Mobilize, Clipbook, Measure Studio, OpenField, Plural, Unitary, JusticeText — directory mention alone isn't proof of AI branding, matching this plan's own risk note. **Excluded as not viable vendor candidates**: Siri, Google Translate (consumer products a campaign wouldn't pay as a distinct line-item vendor) and generic "Meta programmatic ads" (already out of scope per the existing taxonomy's own hyperscaler/ad-platform exclusion). |
| `startupcaucus.com` | ✅ Reachable | Homepage highlights only 5 portfolio companies (Campaign Forecast, Trailmapper, Voter Science, Buzz360, Numinar) and **explicitly does not brand any of them as AI** on this page. Buzz360 and Numinar both cross-confirm the candidate names originally surfaced from Tech.GOP research last round — two independent sources now point at the same two names, which raises confidence they're worth checking, but neither source has actually confirmed AI branding yet. A `/portfolio` link exists for the fuller list but wasn't read this pass. |
| `www.tech.gop` | ❌ **Still blocked** | Returns `502 Bad Gateway` from the proxy — the proxy log records `"gateway answered 502 to CONNECT (policy denial or upstream failure)"`, which is ambiguous between a network-policy block and a genuine failure to reach the host. Bare `tech.gop` (no `www.`) is a clean `403` — only the `www` subdomain appears to have been added, not the apex. **This needs attention on your end**: either the apex domain `tech.gop` also needs adding, or `www.tech.gop` has a real upstream connectivity problem beyond a simple allowlist entry (possibly related to `.gop` being a newer TLD). This was the single most promising GOP-side directory identified last round and is still unverified. |

**Concrete candidate list so far** (pending the corpus-verification step the
plan already specifies — none of these are added to `vendors.yaml` yet):
Grow Progress, Notion AI, Change Research, Fathom, Swayable, INTRVL,
New/Mode, Buzz360, Numinar, and `aconservative.ai` itself as a
lower-confidence maybe. Next step is checking each against the raw
`data/raw/fec/` and `data/raw/ocpf/` corpora already on disk (no new
fetch needed) and researching era/founding-year for any that show a real
match, per the plan's existing process. Tech.GOP remains the one gap —
worth a second attempt once the connectivity issue is resolved, since it's
the directory most likely to surface additional GOP-aligned names the way
this pass did for the Democratic-aligned side.
