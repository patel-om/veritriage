# TraceIQ

**Verification intelligence for semiconductor regression debug.** TraceIQ turns a raw
simulation log into structured JSON, a deterministic failure classification with
confidence and evidence, an engineering-grade HTML report, and suggested next
debugging steps - in one command.

```
traceiq analyze simulation.log
```

## Why

Today's debug flow after a regression failure is manual: open the log, grep for
errors, open the waveform, inspect signals, form a hypothesis. TraceIQ automates
the front half of that loop:

```
Regression failure
  → Collect artifacts        (simulation.log in v1)
  → Parse deterministically  (UVM / Questa / VCS / Xcelium / generic)
  → Normalize                (typed Pydantic models)
  → Correlate evidence       (rule engine, confidence-ranked)
  → Report                   (analysis.json + report.html + terminal summary)
  → Optional AI narrative    (grounded ONLY in extracted evidence)
```

**Design principles**

- AI assists engineers; it never replaces engineering judgment.
- Every conclusion carries evidence: a log line, a sim time, a snippet.
- Deterministic parsing and classification always run **before** any LLM.
- Modular plugin architecture: new parsers and rules drop in without touching
  existing code.

## Installation

Requires Python 3.11+.

```bash
pip install -e .            # core (deterministic pipeline)
pip install -e ".[ai]"      # + optional AI summary (Anthropic SDK)
pip install -e ".[dev]"     # + test tooling
```

## Usage

```bash
# Analyze a log; writes analysis.json and report.html to the current directory
traceiq analyze simulation.log

# Choose an output directory, force a parser, add an AI summary
traceiq analyze simulation.log -o out/ --parser simulation_log --ai

# Introspection
traceiq parsers
traceiq version
```

Exit codes: `0` clean run, `1` failure classified (useful for CI gating),
`2` usage error.

The AI summary uses the Anthropic API (`ANTHROPIC_API_KEY` or an `ant auth login`
profile) and receives only the deterministic findings - never the raw log.

### Library use

```python
from pathlib import Path
from traceiq.pipeline import analyze

report = analyze(Path("simulation.log"))
print(report.classification.category, report.classification.confidence)
```

## What v1 classifies

| Category | Typical signature | Confidence |
|---|---|---|
| Compile failure | syntax errors, undeclared identifiers, elaboration failures | 90 |
| Assertion failure | SVA/checker assertion fired | 90 |
| Timeout | phase/watchdog timeout, hung test | 85 |
| Testbench failure | scoreboard mismatch, compare errors | 80 |
| Fatal error | fatal message without a more specific diagnosis | 70 |
| Unknown failure | errors present, no signature matched | 30 |
| No failure | clean log | 95 |

All rule verdicts (not just the winner) appear in the report as alternatives.

## Scope of v1 - deliberately small

Simulation logs only. No waveform parsing, no RTL parsing, no RAG, no vector
databases, no multi-agent orchestration. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how those land later without
architectural change, and [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) to add a
parser or rule in ~30 lines.

## Roadmap (documented, not built)

Assertion/coverage/compile-log parsers → waveform metadata + FSDB/VCD indexing →
spec retrieval and git-history correlation → AI reasoning over correlated
evidence → VS Code extension, Slack integration, GitHub Action, MCP server.

## License

Apache-2.0
