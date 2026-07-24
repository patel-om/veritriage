"""Log intelligence: classify log lines by origin and lifecycle phase.

Before a failure is analyzed, understand the log itself. Each message is
classified by origin (rtl, testbench, vip, simulator, infrastructure,
boilerplate, progress, phase) using the project's declared ``LogProfile`` first,
then a small built-in default set (extensible via ``@register_log_origin``), and
tagged with the lifecycle phase whose markers it matches.

This module reads artifacts only through the parser registry (parsers own raw
text); it never parses source syntax itself.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Callable

from veritriage.models import LogAnnotationView
from veritriage.project.model import LogProfile, ProjectModel

#: A default rule maps a compiled pattern (against text) to an origin label.
LogOriginRule = Callable[[str, str | None], str | None]

_DEFAULT_RULES: list[tuple[str, LogOriginRule]] = []


def register_log_origin(name: str):
    """Register a fallback log-origin rule (runs when the project profile misses)."""

    def _register(fn: LogOriginRule) -> LogOriginRule:
        _DEFAULT_RULES.append((name, fn))
        return fn

    return _register


@lru_cache(maxsize=256)
def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


def classify_origin(
    text: str, module: str | None, log_profile: LogProfile | None
) -> str:
    """Classify one message's origin.

    The project's declared log sources win (pattern matched against the module
    scope first, then the message text); built-in defaults are the fallback;
    anything unmatched is 'unknown'.
    """
    if log_profile is not None:
        for rule in log_profile.rules:
            pat = _compile(rule.pattern)
            if (module and pat.search(module)) or pat.search(text):
                return rule.origin
    for _name, fn in _DEFAULT_RULES:
        origin = fn(text, module)
        if origin is not None:
            return origin
    return "unknown"


def phase_for(text: str, model: ProjectModel) -> str | None:
    """The lifecycle phase a message belongs to, by marker match (first wins)."""
    for phase in model.lifecycle.phases:
        if any(_compile(m).search(text) for m in phase.markers):
            return phase.name
    return None


def explain_log(path: Path, model: ProjectModel | None = None) -> list[LogAnnotationView]:
    """Annotate each notable line of a log by origin and lifecycle phase.

    Parses via the registered parser (never re-reading raw text here), so log
    intelligence works on any artifact the platform already understands.
    """
    from veritriage.parsers import find_parser

    result = find_parser(path).parse(path)
    log_profile = model.log_profile if model is not None else None
    annotations: list[LogAnnotationView] = []
    for event in result.events:
        text = f"{event.message} {event.raw_line or ''}"
        annotations.append(
            LogAnnotationView(
                line_number=event.line_number,
                origin=classify_origin(text, event.component, log_profile),
                phase=phase_for(text, model) if model is not None else None,
                snippet=event.raw_line or event.message,
            )
        )
    return annotations


# --- Built-in fallback origin rules -----------------------------------------


@register_log_origin("simulator-banner")
def _simulator(text: str, module: str | None) -> str | None:
    if _compile(r"chronologic|synopsys vcs|questa|xcelium|ncsim|vlog|vcs\b|verdi").search(text):
        return "simulator"
    return None


@register_log_origin("infrastructure")
def _infrastructure(text: str, module: str | None) -> str | None:
    if _compile(r"license|no space|disk (?:full|quota)|killed|core dump|segmentation fault|nfs").search(text):
        return "infrastructure"
    return None


@register_log_origin("uvm-testbench")
def _uvm_tb(text: str, module: str | None) -> str | None:
    if module and _compile(r"uvm_test_top|\benv\b|agent|scoreboard|sequencer|monitor").search(module):
        return "testbench"
    if _compile(r"UVM_INFO|UVM_WARNING|UVM_ERROR|UVM_FATAL").search(text):
        return "testbench"
    return None
