"""Vendor-name normalization shared by the federal and state sides of the
subvendor analysis, so "Bearstar Strategies, Inc." on an FEC filing and
"BEARSTAR STRATEGIES INC." on a CAL-ACCESS filing land on the same key."""
from __future__ import annotations

import re

_LEGAL_SUFFIXES = {
    "LLC", "L L C", "INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY",
    "LTD", "LIMITED", "LP", "LLP", "PLLC", "PC", "PBC",
}
_PUNCT = re.compile(r"[^A-Z0-9 ]+")
_SPACES = re.compile(r"\s+")


def normalize_vendor(name: str) -> str:
    s = (name or "").upper().replace("&", " AND ")
    s = re.split(r"\b(?:D/?B/?A|C/O|ATTN)\b", s)[0]
    s = _SPACES.sub(" ", _PUNCT.sub(" ", s)).strip()
    words = s.split(" ")
    if words and words[0] == "THE":
        words = words[1:]
    while words and words[-1] in _LEGAL_SUFFIXES:
        words = words[:-1]
    # "L L C" collapses into three single-letter words after punctuation removal.
    while len(words) >= 3 and words[-3:] == ["L", "L", "C"]:
        words = words[:-3]
    return " ".join(words)


# Trailing words firms add or drop between filings ("Middle Seat" vs.
# "Middle Seat Consulting" vs. "Middle Seat Digital"). Stripped only to find
# candidate variants; federal_vendors.py merges variants only when they also
# share a home state, and writes every merge to out/name_merges.csv.
_DESCRIPTORS = {
    "CONSULTING", "CONSULTANTS", "STRATEGIES", "STRATEGY", "DIGITAL", "GROUP", "COMMUNICATIONS",
    "ASSOCIATES", "PARTNERS", "SOLUTIONS", "AGENCY", "SERVICES", "CAMPAIGNS", "LABS",
}


def brand_key(key: str) -> str:
    words = key.split(" ")
    while len(words) > 2 and words[-1] in _DESCRIPTORS:
        words = words[:-1]
    if len(words) == 2 and words[-1] in _DESCRIPTORS:
        return key  # "BLUE STRATEGIES" -> "BLUE" would be too generic to merge on
    return " ".join(words)
