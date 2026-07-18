# VeriTriage

**Verification intelligence for semiconductor regression debug.** VeriTriage turns
raw verification artifacts (simulation logs, compile logs, coverage summaries,
test metadata) into a normalized **Evidence Graph**, a deterministic failure
classification with confidence and evidence, an engineering-grade HTML report,
and suggested next debugging steps - in one command.

```
veritriage analyze simulation.log coverage.txt test_metadata.json
```

## Why

Today's debug flow after a regression failure is manual: open the log, grep for
errors, open the waveform, inspect signals, form a hypothesis. VeriTriage
automates the front half of that loop:

```
Regression failure
  -> Collect artifacts        (sim log, compile log, coverage, test metadata)
  -> Parse deterministically  (UVM / Questa / VCS / Xcelium / generic)
  -> Normalize                (Evidence Graph: typed nodes + typed edges)
  -> Correlate evidence       (temporal, causal, cross-artifact links)
  -> Classify                 (rule engine over the graph, confidence-ranked)
  -> Reason                   (evidence selection -> signals -> competing
                               hypotheses -> traceable confidence -> steps)
  -> Report                   (analysis.json + evidence_graph.json + report.html)
  -> Optional AI review       (reasons ONLY over selected evidence, cites node IDs)
```

**Design principles**

- AI assists engineers; it never replaces engineering judgment.
- The Evidence Graph is the single source of truth: every conclusion carries
  node IDs that trace to an artifact file and line.
- Deterministic parsing, graph building, and classification always run
  **before** any LLM; the AI layer never reads raw files.
- Modular plugin architecture: new parsers, rules, and correlation passes drop
  in without touching the rule engine or the AI layer.

See [docs/EVIDENCE_GRAPH.md](docs/EVIDENCE_GRAPH.md) for why this architecture
improves scalability, explainability, and deterministic reasoning, and
[docs/REASONING_ENGINE.md](docs/REASONING_ENGINE.md) for the multi-stage
reasoning pipeline: how it generates multiple ranked, evidence-backed
hypotheses with traceable confidence, and how deterministic rules and AI
collaborate without the AI ever reading a raw file.

## Installation

Requires Python 3.11+.

```bash
pip install -e .            # core (deterministic pipeline)
pip install -e ".[ai]"      # + optional AI summary (Anthropic SDK)
pip install -e ".[dev]"     # + test tooling
```

## Usage

```bash
# Analyze one artifact
veritriage analyze simulation.log

# Analyze a whole run: log + coverage + test metadata, correlated in one graph
veritriage analyze simulation.log compile.log coverage.txt test_metadata.json -o out/

# Add an AI summary grounded in the evidence graph
veritriage analyze simulation.log -o out/ --ai

# Introspection
veritriage parsers
veritriage version
```

Each run writes three artifacts to the output directory:

| File | Contents |
|---|---|
| `analysis.json` | Classification, confidence, evidence (with graph node IDs), run summary, graph stats |
| `evidence_graph.json` | The full serialized Evidence Graph: every node and relationship |
| `report.html` | Self-contained EDA-style dashboard (light/dark), evidence timeline, next steps |

Exit codes: `0` clean run, `1` failure classified (useful for CI gating),
`2` usage error.

The AI summary uses the Anthropic API (`ANTHROPIC_API_KEY` or an `ant auth login`
profile) and receives only the graph's normalized reasoning view - never raw
artifact text.

### Library use

```python
from pathlib import Path
from veritriage.pipeline import analyze

outcome = analyze([Path("simulation.log"), Path("coverage.txt")])
print(outcome.report.classification.category, outcome.report.classification.confidence)
print(outcome.graph.stats().node_count, "evidence nodes")
```

## What v2 classifies

| Category | Typical signature | Confidence |
|---|---|---|
| Compile failure | dedicated compile-log evidence, syntax errors, undeclared identifiers | 90 |
| Assertion failure | SVA/checker assertion fired (first-class `assertion` nodes) | 90 |
| Timeout | phase/watchdog timeout, hung test | 85 |
| Testbench failure | scoreboard mismatch, compare errors | 80 |
| Fatal error | fatal message without a more specific diagnosis | 70 |
| Unknown failure | errors present, no signature matched | 30 |
| No failure | clean artifacts | 95 |

All rule verdicts (not just the winner) appear in the report as alternatives,
and every evidence item cites its graph node.

## Artifact types in the graph

Simulation logs, assertions, coverage, test metadata, and compile logs are
live today; `waveform_metadata` is a reserved type for the future waveform
parser. Adding an artifact type is a parser plus an optional correlation pass;
the rule engine and AI layer are untouched by design
([checklist](docs/EVIDENCE_GRAPH.md#adding-a-new-artifact-type-checklist)).

## Roadmap (documented, not built)

Waveform metadata + FSDB/VCD indexing -> spec retrieval and git-history
correlation as new node types -> deeper AI reasoning over the correlated graph
-> VS Code extension, Slack integration, GitHub Action, MCP server.

## License

Apache-2.0
