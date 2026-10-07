#!/usr/bin/env python3
"""Look up federal campaign vendors in state filings that disclose a
vendor's OWN downstream payments, and check those downstream payments for
AI tools.

The FEC has no subvendor rule: a federal filing ends at "XYZ Strategies --
media buy." Two states this project covers go one layer further:

  * Massachusetts (OCPF subvendor reports): a vendor paid $5,000+ by a
    committee must itemize each $500+ payment it makes to a subvendor.
  * California (CAL-ACCESS EXPN): payments an agent or independent
    contractor makes on a committee's behalf are itemized with the
    contractor named in AGENT_NAML and the downstream payee in PAYEE_NAML.

So when a firm that works for federal campaigns also works for a
Massachusetts or California committee, its state filings show what tools
and services that firm itself pays for. That's a view of the firm's
toolchain, not of any specific federal client's work -- see the README.

Inputs: out/federal_vendors.csv (from federal_vendors.py),
data/raw/ocpf/subvendor.jsonl (fetch_ocpf.py), data/raw/ca/expn.jsonl and
data/raw/ca/filer_lookup.json (fetch_ca.py / fetch_ca_filers.py).
Outputs: out/subvendor_rows.csv (every state subvendor row whose primary
vendor is also a federal vendor) and out/vendor_summary.csv (one row per
matched federal vendor).
"""
from __future__ import annotations

import csv
import difflib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "pipeline"))
from names import normalize_vendor  # noqa: E402
from lib.vendor_match import Taxonomy  # noqa: E402

RAW = ROOT / "data" / "raw"
OUT = HERE / "out"

# Catches AI-indicative subvendors the curated taxonomy doesn't name yet.
# Reported separately from taxonomy matches and reviewed by hand.
GENERIC_AI = re.compile(
    r"\bA\.?I\.?\b|artificial intelligence|machine learning|\bLLM\b|generative|chatbot|"
    r"\bGPT\b|midjourney|synthesia|heygen|elevenlabs",
    re.IGNORECASE,
)


# Primary "vendors" that are really payment channels -- a committee's own
# credit card, payroll processor, or bank -- rather than a firm with its own
# toolchain. California itemizes campaign credit-card charges on Schedule G
# with the card issuer as the "agent", which is the committee's own
# spending, not a consultant's. Flagged and summarized separately.
PASS_THROUGH = re.compile(
    r"AMERICAN EXPRESS|\bAMEX\b|CHASE|CITI|CAPITAL ONE|\bBANK\b|BANCORP|\bVISA\b|MASTERCARD|"
    r"CARDMEMBER|CARD SERVICES|CREDIT CARD|CREDIT UNION|DISCOVER|BARCLAY|WELLS FARGO|PAYCHEX|ELAN FINANCIAL|"
    r"\bADP\b|GUSTO|PAYPAL|\bSTRIPE\b|ACTBLUE|WINRED|ANEDOT|INTUIT|QUICKBOOKS|PAYROLL",
)


def parse_amount(s: str) -> float:
    try:
        return float(str(s).replace("$", "").replace(",", "") or 0)
    except ValueError:
        return 0.0


def load_federal() -> dict[str, dict]:
    with open(OUT / "federal_vendors.csv", encoding="utf-8") as f:
        return {r["vendor_key"]: r for r in csv.DictReader(f)}


def ma_rows():
    with open(RAW / "ocpf" / "subvendor.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            yield {
                "state": "MA",
                "primary_vendor": r.get("vendorName") or "",
                "subvendor": r.get("subvendorName") or "",
                "purpose": r.get("purpose") or "",
                "code": "",
                "amount": parse_amount(r.get("amount")),
                "date": r.get("date") or "",
                "filer": r.get("filerFullNameReverse") or "",
                "source": f"https://www.ocpf.us/Reports/DisplayReport?menuHidden=true&id={r.get('reportId')}",
            }


def ca_filer_names() -> dict[str, str]:
    path = RAW / "ca" / "filer_lookup.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return {fid: cover["filer_name"] for fid, cover in json.load(f).items()}


def ca_latest_amendments() -> dict[str, int]:
    """FILING_ID -> highest AMEND_ID present. CAL-ACCESS's EXPN table keeps
    every version of an amended filing, so the same line item shows up once
    per amendment; only the latest version is counted."""
    latest: dict[str, int] = {}
    with open(RAW / "ca" / "expn.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            fid, aid = str(r.get("FILING_ID")), int(r.get("AMEND_ID") or 0)
            if aid > latest.get(fid, -1):
                latest[fid] = aid
    return latest


def ca_rows():
    names = ca_filer_names()
    latest = ca_latest_amendments()
    with open(RAW / "ca" / "expn.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if int(r.get("AMEND_ID") or 0) != latest.get(str(r.get("FILING_ID"))):
                continue
            agent = " ".join(x for x in (r.get("AGENT_NAMF"), r.get("AGENT_NAML")) if x).strip()
            if not agent:
                continue
            payee = " ".join(x for x in (r.get("PAYEE_NAMF"), r.get("PAYEE_NAML")) if x).strip()
            yield {
                "state": "CA",
                "primary_vendor": agent,
                "subvendor": payee,
                "purpose": r.get("EXPN_DSCR") or r.get("EXPN_CODE") or "",
                "code": r.get("EXPN_CODE") or "",
                "amount": parse_amount(r.get("AMOUNT")),
                "date": (r.get("EXPN_DATE") or "").split(" ")[0],
                "filer": names.get(str(r.get("FILING_ID")), f"Committee {r.get('FILING_ID')}"),
                "source": f"https://cal-access.sos.ca.gov/PDFGen/pdfgen.prg?filingid={r.get('FILING_ID')}&amendid={r.get('AMEND_ID')}",
            }


# Fuzzy pairs reviewed by hand and found to be different organizations.
FUZZY_REJECT = {
    ("COMPLETE DIGITAL", "COMPETE DIGITAL"),
    ("HART COMMUNICATIONS", "HARTA COMMUNICATIONS"),
    ("JESSICA MARTINEZ", "JESSICA MARTIN"),
    ("MARINE PRINTING", "MARTIN PRINTING"),
    ("REPUBLICAN PARTY OF ORANGE COUNTY", "REPUBLICAN PARTY OF PORTAGE COUNTY"),
    ("WILLIAM JAMES", "WILLIAMS JAMES"),
    ("INDEPENDENCE CAMPAIGNS", "INDEPENDENT CAMPAIGNS"),
    ("PANORAMA STRATEGIC CONSULTING", "PANORAMIC STRATEGIC CONSULTING"),
    ("WAGMAN STRATEGIES", "WAGAMAN STRATEGIES"),
}
_DIGITS = re.compile(r"\d+")


class FederalMatcher:
    """Exact normalized-name match, then a conservative fuzzy fallback
    (difflib ratio >= 0.93, same first 3 characters) for state-side typos
    like "TECHNICOLOR POLTIICAL". Fuzzy matches are recorded so they can be
    reviewed in out/fuzzy_matches.csv."""

    def __init__(self, federal: dict[str, dict]):
        self.federal = federal
        # Name variants federal_vendors.py folded into one firm.
        with open(OUT / "name_merges.csv", encoding="utf-8") as f:
            self.aliases = {r["variant_key"]: r["merged_into"] for r in csv.DictReader(f)}
        self.by_prefix: dict[str, list[str]] = defaultdict(list)
        for k in federal:
            self.by_prefix[k[:3]].append(k)
        self.cache: dict[str, str | None] = {}
        self.fuzzy: dict[str, str] = {}

    def match(self, key: str) -> str | None:
        if key in self.federal:
            return key
        if key in self.aliases:
            return self.aliases[key]
        if key in self.cache:
            return self.cache[key]
        hit = None
        if len(key) >= 8:
            close = difflib.get_close_matches(key, self.by_prefix.get(key[:3], []), n=1, cutoff=0.93)
            # Union locals, county parties, etc. differ only by a number.
            if close and (_DIGITS.findall(key) != _DIGITS.findall(close[0]) or (key, close[0]) in FUZZY_REJECT):
                close = []
            if close:
                hit = close[0]
                self.fuzzy[key] = hit
        self.cache[key] = hit
        return hit


def main() -> None:
    federal = load_federal()
    taxonomy = Taxonomy()
    matcher = FederalMatcher(federal)

    matched_rows = []
    state_primary_totals: Counter = Counter()
    for source in (ma_rows, ca_rows):
        for row in source():
            raw_key = normalize_vendor(row["primary_vendor"])
            state_primary_totals[(row["state"], raw_key)] += row["amount"]
            key = matcher.match(raw_key)
            if key is None:
                continue
            text = f"{row['subvendor']} {row['purpose']}"
            hits = [(v, conf) for v, conf in taxonomy.match_vendors(text) if conf == "high"]
            row["vendor_key"] = key
            row["pass_through"] = "Y" if PASS_THROUGH.search(key) else ""
            row["ai_vendor_ids"] = ";".join(v.id for v, _ in hits)
            row["ai_vendor_eras"] = ";".join(v.era for v, _ in hits)
            row["generic_ai_hit"] = "" if hits else (GENERIC_AI.search(text).group(0) if GENERIC_AI.search(text) else "")
            matched_rows.append(row)

    OUT.mkdir(parents=True, exist_ok=True)
    fields = ["vendor_key", "pass_through", "state", "primary_vendor", "subvendor", "purpose", "code", "amount", "date", "filer",
              "ai_vendor_ids", "ai_vendor_eras", "generic_ai_hit", "source"]
    with open(OUT / "subvendor_rows.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in sorted(matched_rows, key=lambda r: (r["vendor_key"], -r["amount"])):
            w.writerow({k: r[k] for k in fields})

    by_vendor: dict[str, dict] = defaultdict(lambda: {
        "states": set(), "records": 0, "amount": 0.0, "subvendors": Counter(),
        "ai_amount": 0.0, "ai_records": 0, "ai_tools": Counter(),
        "generic_records": 0, "generic_hits": Counter(), "filers": set(),
    })
    for r in matched_rows:
        v = by_vendor[r["vendor_key"]]
        v["states"].add(r["state"])
        v["records"] += 1
        v["amount"] += r["amount"]
        v["subvendors"][normalize_vendor(r["subvendor"]) or r["subvendor"]] += r["amount"]
        v["filers"].add(r["filer"])
        if r["ai_vendor_ids"]:
            v["ai_records"] += 1
            v["ai_amount"] += r["amount"]
            for vid in r["ai_vendor_ids"].split(";"):
                v["ai_tools"][vid] += r["amount"]
        elif r["generic_ai_hit"]:
            v["generic_records"] += 1
            v["generic_hits"][f"{r['subvendor']} ({r['purpose']})"] += r["amount"]

    with open(OUT / "vendor_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "vendor_key", "pass_through", "federal_display_name", "federal_amount", "federal_committees", "focus_candidates",
            "states", "state_filers", "state_subvendor_records", "state_subvendor_amount", "distinct_subvendors",
            "ai_tool_records", "ai_tool_amount", "ai_tools", "generic_ai_records", "generic_ai_examples",
            "top_subvendors",
        ])
        for key, v in sorted(by_vendor.items(), key=lambda kv: -float(federal[kv[0]]["federal_amount"])):
            fed = federal[key]
            w.writerow([
                key, "Y" if PASS_THROUGH.search(key) else "", fed["display_name"], fed["federal_amount"], fed["committees"], fed["focus_candidates"],
                " ".join(sorted(v["states"])), len(v["filers"]), v["records"], round(v["amount"], 2),
                len(v["subvendors"]), v["ai_records"], round(v["ai_amount"], 2),
                "; ".join(f"{t} (${a:,.0f})" for t, a in v["ai_tools"].most_common()),
                v["generic_records"], "; ".join(h for h, _ in v["generic_hits"].most_common(5)),
                "; ".join(f"{s} (${a:,.0f})" for s, a in v["subvendors"].most_common(8)),
            ])

    with open(OUT / "fuzzy_matches.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["state_name_normalized", "matched_federal_vendor_key"])
        w.writerows(sorted(matcher.fuzzy.items()))

    for st in ("MA", "CA"):
        st_total = sum(v for (s, k), v in state_primary_totals.items() if s == st and not PASS_THROUGH.search(k))
        st_matched = sum(r["amount"] for r in matched_rows if r["state"] == st and not r["pass_through"])
        st_pass = sum(v for (s, k), v in state_primary_totals.items() if s == st and PASS_THROUGH.search(k))
        print(f"{st}: ${st_matched:,.0f} of ${st_total:,.0f} non-pass-through subvendor dollars "
              f"({st_matched / st_total:.0%}) flow through firms that also work federal campaigns "
              f"(plus ${st_pass:,.0f} via credit cards/payroll/payment processors)")
    print(f"{len(matcher.fuzzy)} fuzzy name matches -- review out/fuzzy_matches.csv")
    n_state_primaries = len({k for k in state_primary_totals})
    print(f"{len(by_vendor)} federal vendors also appear as a primary vendor in state subvendor data "
          f"(of {n_state_primaries} distinct state primary vendors); {len(matched_rows)} subvendor rows -> {OUT}")


if __name__ == "__main__":
    main()
