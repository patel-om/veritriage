"""Deterministic phrase to Question, with a declared vocabulary.

A keyword and pattern matcher, in the same spirit as the Knowledge Engine's
clause matcher: no NLP library, no model, no statistics, no guessing. The
canonical question is a structured :class:`Question`; this module exists so a
CLI or a chat front end can offer familiar phrasings without the platform
pretending to understand language.

The important property is honesty. When a phrase is outside the vocabulary the
parser says so and the engine answers with the vocabulary it *does* understand,
rather than picking the nearest intent and being confidently wrong.

A language model later becomes a translator that produces `Question` objects
directly, at which point this module is a fallback rather than a bottleneck.
"""

from __future__ import annotations

import re

from veritriage.models import Intent, Question

#: Ordered (pattern, intent) rules. First match wins, so the more specific
#: phrasings are listed before the more general ones. Every pattern here is
#: part of the declared vocabulary and is reported by ``vocabulary()``.
_RULES: tuple[tuple[str, Intent], ...] = (
    (r"^\s*(help|what can i ask|options)\b", Intent.HELP),
    (r"\bwhy\s+(not|didn'?t|isn'?t|wasn'?t)\b", Intent.WHY_NOT),
    (r"\bwhy\b", Intent.WHY),
    (r"\b(show|list)\s+(me\s+)?(the\s+)?evidence\b", Intent.SHOW_EVIDENCE),
    (r"\bwhat evidence\b", Intent.SHOW_EVIDENCE),
    (r"\bshow only\b|\bfilter\b|\bonly show\b", Intent.FILTER),
    (r"\bcompare\b|\bdiff\b|\bversus\b|\bvs\.?\b", Intent.COMPARE),
    (r"\btrace\b|\bwhere did .* come from\b|\bprovenance\b", Intent.TRACE),
    (r"\b(go to|navigate|open|select|drill (in|down)|expand)\b", Intent.NAVIGATE),
    (r"\bsummar(y|ise|ize)\b|\boverview\b", Intent.SUMMARIZE),
    (r"\bexplain\b|\bwhat is\b|\bdescribe\b|\btell me about\b", Intent.EXPLAIN),
)

#: Trailing words stripped when extracting a target from a phrase.
_NOISE = re.compile(
    r"^(the|this|that|a|an|is|are|was|were|it|me|about|for|of|to|do|does|did)\b",
    re.IGNORECASE,
)

#: Filter phrases: "show only X" / "filter by X".
_FILTER_TARGET = re.compile(
    r"\b(?:show only|only show|filter(?:\s+by)?)\s+(.+)$", re.IGNORECASE
)

#: Explicit target markers, tried in order. IDs first (they are unambiguous),
#: then the noun following an intent verb, then the looser prepositions.
_TARGET_PATTERNS = (
    re.compile(r"\b(hyp-[a-z_]+)\b", re.IGNORECASE),
    re.compile(r"\b(ev-[0-9a-f]+)\b", re.IGNORECASE),
    re.compile(r"\b(dn-[0-9a-f]+)\b", re.IGNORECASE),
    re.compile(r"\b(step-[0-9a-f]+)\b", re.IGNORECASE),
    re.compile(r"\b(reg-[0-9a-f-]+)\b", re.IGNORECASE),
    re.compile(r"\b(ses-[0-9a-f]+)\b", re.IGNORECASE),
    re.compile(r"\bregression\s+(\S+)", re.IGNORECASE),
    re.compile(r"\b(?:agent|specialist)\s+(\w+)", re.IGNORECASE),
    re.compile(r"\b(?:module|block|scope)\s+([\w.$]+)", re.IGNORECASE),
    # The noun immediately following an intent verb: "summarize design",
    # "go to l2_cache", "explain the scoreboard". Without this a bare
    # verb-plus-noun phrase loses its target entirely.
    re.compile(
        r"\b(?:summar(?:y|ise|ize)(?:\s+of)?|overview(?:\s+of)?|explain|describe|"
        r"go\s+to|navigate\s+to|navigate|open|select|trace|why\s+not|"
        r"compare(?:\s+(?:with|to|against))?)"
        r"\s+(?:the\s+|this\s+|a\s+)?([\w.$-]+)",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:about|for|of)\s+([\w.$-]+)", re.IGNORECASE),
)


def vocabulary() -> list[str]:
    """The phrasings this parser understands, for an honest miss message."""
    return [
        "why is this classified as ... / why did ... happen",
        "why not ... / why didn't ...",
        "explain ... / what is ... / describe ...",
        "show evidence / what evidence supports this",
        "show only <artifact type or severity>",
        "compare with <session or regression id>",
        "trace <recommendation or plan step>",
        "go to <module, agent, hypothesis, or design node>",
        "summarize <evidence, agents, learning, plan, design, knowledge>",
        "help",
    ]


def parse(text: str) -> Question | None:
    """Map a phrase onto a structured question, or None when out of vocabulary.

    Returning None rather than a best guess is the point: an unparsed question
    produces an honest miss listing what can be asked, which is more useful than
    a confident answer to a question nobody asked.
    """
    if not text or not text.strip():
        return None
    lowered = text.strip().lower()

    intent = next((i for pattern, i in _RULES if re.search(pattern, lowered)), None)
    if intent is None:
        return None

    if intent is Intent.FILTER:
        match = _FILTER_TARGET.search(text)
        return Question(
            intent=intent,
            filter=match.group(1).strip() if match else None,
            text=text.strip(),
        )

    return Question(intent=intent, target=_target(text), text=text.strip())


def _target(text: str) -> str | None:
    """Extract what a phrase is about, without guessing at meaning."""
    for pattern in _TARGET_PATTERNS:
        match = pattern.search(text)
        if match:
            candidate = match.group(1).strip().strip("?.,'\"")
            candidate = _NOISE.sub("", candidate).strip()
            if candidate:
                return candidate
    return None
