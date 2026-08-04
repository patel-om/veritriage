"""Grounding: enforced, not requested.

Asking a model to cite properly and hoping is not a guarantee. The platform
already has this pattern twice (the M12 Coordinator's provider verification and
the M16 Conversation Engine's citation check): declare the allowed set, then
strip anything outside it.

Here the :class:`Prompt` declares its citation set, the response is scanned for
citation tokens, and any token not in that set is removed from the prose with
the omission recorded. Deterministic, and no model is needed to check a model.

The structured object survives regardless, which is what makes generated prose
an additional view rather than the source of truth.
"""

from __future__ import annotations

import re

from veritriage.models import Citation, Prompt

#: A citation token: [kind:id]. Kinds and IDs are constrained to the character
#: classes the platform actually mints, so ordinary bracketed prose is not
#: mistaken for a citation.
CITATION_TOKEN = re.compile(r"\[([a-z_]+):([A-Za-z0-9._\-]+)\]")


def extract(text: str) -> list[str]:
    """Every citation token appearing in a generated text, in order of first use."""
    found: list[str] = []
    for match in CITATION_TOKEN.finditer(text):
        token = match.group(0)
        if token not in found:
            found.append(token)
    return found


def enforce(text: str, prompt: Prompt) -> tuple[str, list[Citation], list[str]]:
    """Strip citations the prompt did not authorize.

    Returns the cleaned text, the citations it legitimately used, and the
    tokens that were removed. A provider inventing a reference therefore
    changes nothing except its own credibility score.
    """
    allowed = prompt.allowed_tokens
    by_token = {c.token: c for c in prompt.citations}

    used: list[Citation] = []
    stripped: list[str] = []

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        if token in allowed:
            citation = by_token[token]
            if citation not in used:
                used.append(citation)
            return token
        if token not in stripped:
            stripped.append(token)
        return ""  # an unauthorized citation is removed, not rewritten

    cleaned = CITATION_TOKEN.sub(replace, text)
    # Tidy what an excision leaves behind, without reflowing or rewriting prose.
    # Whitespace and dangling connectives only: anything more would be editing
    # generated content rather than removing an unauthorized reference.
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+(?:and|or)\s*([.,;:])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]*([.,;:])(?:[ \t]*\1)+", r"\1", cleaned)
    cleaned = re.sub(r" +([.,;:])", r"\1", cleaned)
    return cleaned.strip(), used, stripped


def grounded_ratio(text: str, prompt: Prompt) -> float:
    """Fraction of a text's citations that the prompt authorized.

    Reported rather than acted upon: a caller may surface it, and a future
    learner may aggregate it into per-provider reliability, exactly as agent
    reliability is aggregated today.
    """
    tokens = extract(text)
    if not tokens:
        return 1.0
    allowed = prompt.allowed_tokens
    return round(sum(1 for t in tokens if t in allowed) / len(tokens), 4)
