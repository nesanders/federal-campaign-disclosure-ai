"""Load the AI vendor/category taxonomy and match it against disbursement text."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "vendors.yaml"


@dataclass(frozen=True)
class CompiledPattern:
    regex: re.Pattern
    confidence: str


@dataclass(frozen=True)
class Vendor:
    id: str
    name: str
    group: str  # "general_purpose" | "political_specific"
    patterns: list[CompiledPattern]
    lean_context: str | None = None


@dataclass(frozen=True)
class Category:
    id: str
    label: str
    patterns: list[re.Pattern]


def _wrap(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


class Taxonomy:
    def __init__(self, config_path: Path = CONFIG_PATH):
        with open(config_path) as f:
            raw = yaml.safe_load(f)

        self.vendors: list[Vendor] = []
        for group in ("general_purpose", "political_specific"):
            for v in raw.get(group, []):
                compiled = [
                    CompiledPattern(_wrap(p["pattern"]), p["confidence"])
                    for p in v["patterns"]
                ]
                self.vendors.append(
                    Vendor(
                        id=v["id"],
                        name=v["name"],
                        group=group,
                        patterns=compiled,
                        lean_context=v.get("lean_context"),
                    )
                )

        self.categories: list[Category] = [
            Category(c["id"], c["label"], [_wrap(p) for p in c.get("patterns", [])])
            for c in raw.get("use_case_categories", [])
        ]

    def match_vendors(self, text: str) -> list[tuple[Vendor, str]]:
        """Return [(vendor, confidence)] for every vendor with a hit in text."""
        if not text:
            return []
        hits = []
        for vendor in self.vendors:
            best = None
            for cp in vendor.patterns:
                if cp.regex.search(text):
                    if best is None or (best == "medium" and cp.confidence == "high"):
                        best = cp.confidence
            if best:
                hits.append((vendor, best))
        return hits

    def match_categories(self, text: str) -> list[str]:
        if not text:
            return ["unspecified"]
        hits = [c.id for c in self.categories if c.id != "unspecified" and any(p.search(text) for p in c.patterns)]
        return hits or ["unspecified"]
