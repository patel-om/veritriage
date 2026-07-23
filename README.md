# VeriTriage

**Verification intelligence for semiconductor regression debug.** VeriTriage turns
raw verification artifacts (simulation logs, compile logs, coverage summaries,
test metadata) into a normalized **Evidence Graph**, a deterministic failure
classification with confidence and evidence, an engineering-grade HTML report,
and suggested next debugging steps - in one command. A **Verification
Knowledge Engine** ships 13 pluggable Knowledge Packs spanning AMBA AXI,
APB, AHB, CHI, TileLink, PCI Express, UVM methodology, SystemVerilog
Assertions, reset sequencing, clock domain crossing, cache coherency, and
RISC-V privilege (29 deterministic failure patterns, 29 debug playbooks, 9
protocol state machines total) that match the evidence against known
failure patterns, project it onto protocol state machines to show where
progress stopped, and attach deterministic debug playbooks with real
specification references. Every analysis is also recorded into a
persistent **Regression Database**, so the platform tells you whether this
failure has been seen before, what resembled it, and what the historical
root cause was.

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
  -> Apply knowledge          (packs -> knowledge graph -> pattern match ->
                               state projection -> playbooks -> references)
  -> Reason                   (evidence selection -> signals incl. knowledge ->
                               competing hypotheses -> traceable confidence)
  -> Remember                 (regression database: signature, similarity,
                               "have we seen this before?")
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
improves scalability, explainability, and deterministic reasoning,
[docs/REASONING_ENGINE.md](docs/REASONING_ENGINE.md) for the multi-stage
reasoning pipeline: how it generates multiple ranked, evidence-backed
hypotheses with traceable confidence, and how deterministic rules and AI
collaborate without the AI ever reading a raw file, and
[docs/REGRESSION_INTELLIGENCE.md](docs/REGRESSION_INTELLIGENCE.md) for the
regression database: deterministic failure signatures, similar-failure
search, clustering, analytics, and the engineering dashboard, and
[docs/KNOWLEDGE_ENGINE.md](docs/KNOWLEDGE_ENGINE.md) for the Verification
Knowledge Engine: why structured, versioned verification knowledge beats
prompt engineering, and how to add a protocol pack.

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

# Add waveform metadata: a VCD, or a simulator-independent JSON manifest.
# VeriTriage reads metadata (signal activity, dump window), never transitions,
# and turns it into engineering observations linked to the failure.
veritriage analyze simulation.log dump.vcd -o out/
veritriage analyze simulation.log run.wave.json -o out/

# Add an AI summary grounded in the evidence graph
veritriage analyze simulation.log -o out/ --ai

# Regression intelligence (database defaults to .veritriage/regressions.db)
veritriage history                     # recent regressions in the database
veritriage dashboard -o out/           # engineering analytics dashboard
veritriage feedback reg-... --diagnosis correct --root-cause "..."
veritriage analyze simulation.log --no-history   # opt out of recording

# Introspection
veritriage parsers
veritriage knowledge      # loaded Knowledge Packs
veritriage waveform       # registered waveform adapters and their capabilities
veritriage version
```

Each run writes three artifacts to the output directory:

| File | Contents |
|---|---|
| `analysis.json` | Classification, confidence, evidence (with graph node IDs), reasoning, historical context, run summary, graph stats |
| `evidence_graph.json` | The full serialized Evidence Graph: every node and relationship |
| `report.html` | Self-contained EDA-style dashboard (light/dark), hypotheses, historical context, evidence timeline, next steps |

Each analysis is also stored in the regression database (opt out with
`--no-history`), which powers `veritriage history`, `veritriage dashboard`,
and the "seen before" context in every report.

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

Simulation logs, assertions, coverage, test metadata, compile logs, and
`waveform_metadata` are all live today. Waveform artifacts arrive through the
Waveform Intelligence Engine: a `WaveformAdapter` per format (VCD and a
simulator-independent JSON manifest ship today) normalizes signal-activity
metadata, and a format-agnostic observation engine turns it into engineering
observations (dead clock, stalled FSM, incomplete handshake, unretired
transaction) that enter the graph as evidence and correlate to failures. See
[WAVEFORM_ENGINE.md](docs/WAVEFORM_ENGINE.md). Adding an artifact type is a
parser plus an optional correlation pass; the rule engine and AI layer are
untouched by design
([checklist](docs/EVIDENCE_GRAPH.md#adding-a-new-artifact-type-checklist)).

## Roadmap (documented, not built)

More waveform adapters (FSDB, FST, WLF, transaction DBs) behind the existing
`WaveformAdapter` interface -> spec retrieval and git-history correlation as new
node types -> learned similarity embeddings behind the existing
`EmbeddingProvider` interface -> Jira/CI adapters around the RegressionRecord
vocabulary -> deeper AI reasoning over the correlated graph -> VS Code
extension, Slack integration, GitHub Action, MCP server.

## License

Apache-2.0
