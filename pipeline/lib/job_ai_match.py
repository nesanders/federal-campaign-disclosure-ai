"""Keyword classifier for whether a campaign job posting signals AI use.

This is a smaller, simpler sibling to vendor_match.py's Taxonomy: rather
than matching a large curated list of named vendors, it matches a short,
hand-picked set of AI-indicative terms against a posting's title and body
text separately, producing two confidence tiers:

  "title"         -- the term appears in the job title itself. A posting
                     titled "AI Director" or "LLM Developer" is
                     unambiguous evidence a campaign is hiring *for* AI
                     capability, not just tolerating it as a skill.
  "skill_mention" -- the term appears only in the body/description, for a
                     role whose title says nothing about AI (e.g. a
                     "County Organizer" listing lists "familiarity with
                     ChatGPT" as a plus). This is the ground-level signal
                     explicitly asked for -- a campaign investing in AI
                     fluency among ordinary field/comms/finance staff, not
                     just hiring an AI specialist.

Patterns are deliberately narrow and word-boundary-wrapped, the same
discipline vendors.yaml's own patterns use, to avoid the obvious
false-positive traps: "chair" and "affair" don't contain a standalone
"AI" token; "copilot" is excluded entirely because a literal co-pilot
(a real job the aviation/logistics world uses that term for) is a
plausible unrelated hit in a general job-board corpus, and "Microsoft
Copilot" specifically didn't appear often enough in initial spot-checks
of real postings to justify the ambiguity.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Order doesn't matter for matching; kept roughly most-to-least common.
AI_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bAI\b", re.IGNORECASE),
    re.compile(r"\bchatgpt\b", re.IGNORECASE),
    re.compile(r"\bgenerative ai\b", re.IGNORECASE),
    re.compile(r"\bartificial intelligence\b", re.IGNORECASE),
    re.compile(r"\bmachine learning\b", re.IGNORECASE),
    re.compile(r"\bllms?\b", re.IGNORECASE),
    re.compile(r"\bgpt-?\d\b", re.IGNORECASE),
]


@dataclass(frozen=True)
class AiMatch:
    confidence: str  # "title" | "skill_mention"
    snippet: str  # ~120 chars of context around the first match


def _first_match_snippet(text: str) -> str | None:
    for pattern in AI_PATTERNS:
        m = pattern.search(text)
        if m:
            start = max(0, m.start() - 60)
            end = min(len(text), m.end() + 60)
            return text[start:end].strip()
    return None


def classify(title: str, body_text: str | None) -> AiMatch | None:
    """Title match always wins (and is checked first) over a body-only
    match, even if the body also happens to contain a hit -- a posting
    titled "AI Director" is title-confidence regardless of what its body
    says, since the title match is already the strongest possible signal.
    """
    title_snippet = _first_match_snippet(title or "")
    if title_snippet:
        return AiMatch(confidence="title", snippet=title_snippet)
    if body_text:
        body_snippet = _first_match_snippet(body_text)
        if body_snippet:
            return AiMatch(confidence="skill_mention", snippet=body_snippet)
    return None
