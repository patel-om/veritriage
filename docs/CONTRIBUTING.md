# Contributing to TraceIQ

## Setup

```bash
git clone <repo> && cd traceiq
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Python 3.11+. Type hints and docstrings everywhere; keep rules and parsers pure
(no I/O outside `parse()`, no randomness anywhere).

## Adding a parser

1. Create `src/traceiq/parsers/<artifact>.py`.
2. Subclass `Parser`, set `name` and `file_patterns`, implement
   `parse(path) -> ParseResult`, and decorate with `@register`.
3. Import it from `src/traceiq/parsers/__init__.py` (registration happens on
   import).
4. Add a fixture log under `tests/fixtures/` and tests asserting the events,
   failures, and summary it extracts.

```python
from traceiq.parsers.base import Parser, ParseResult
from traceiq.parsers.registry import register

@register
class CompileLogParser(Parser):
    name = "compile_log"
    file_patterns = ("compile.log",)

    def parse(self, path):
        ...
```

Parsers must never guess: if a line doesn't match a known format, skip it.
Everything a parser emits must be traceable to a specific line.

## Adding a rule

1. Add a `Rule` subclass in `src/traceiq/rules/builtin.py` (or a new module).
2. Set `name` and `category`, implement
   `evaluate(parse_result) -> ClassificationResult | None`.
3. Abstain (`None`) unless the signature genuinely matches. Every verdict must
   include evidence (use `self._result(...)`) and at least one recommendation
   with a rationale.
4. Pick a confidence consistent with the existing ordering (specific ≻ generic)
   and add the rule to `default_rules()`.
5. Add a fixture log that triggers it and a test in `tests/test_rules.py`,
   including a test that the expected rule *outranks* the others that fire.

## Ground rules

- **Evidence or it didn't happen.** No classification, recommendation, or AI
  output without pointers into the artifacts.
- **Determinism.** Same input → same report. Rules are ranked by confidence
  with a stable sort; never rely on dict/set iteration order.
- **Additive schemas.** `analysis.json` consumers depend on it; add fields,
  don't repurpose them, and bump `schema_version` on breaking changes.
- **Tests accompany every parser/rule.** A fixture log is the spec.

## Style

- `pydantic` models for all cross-layer data; no bare dicts across boundaries.
- Docstrings on every public module, class, and function.
- Comments explain *why*, not *what*.
