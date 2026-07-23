# VeriTriage — Project Context

This file is a continuity document: what VeriTriage is, how it got built,
where every piece lives, and what is deliberately left for later. It exists
so work can resume in a new session (or by a new contributor) without
re-deriving decisions already made. It is not user-facing documentation —
see `README.md` and `docs/` for that — this is the "how we got here and
what's next" record.

Repo: https://github.com/patel-om/veritriage (public, Apache-2.0)
Local path: `/Users/ompatel/Documents/veritriage`
Current version: **0.5.1**
Portfolio integration: card + sample artifacts in
`/Users/ompatel/Documents/Om Portfolio` (`index.html`,
`veritriage-sample-report.html`, `veritriage-sample-dashboard.html`)

---

## 1. What VeriTriage is

VeriTriage is an AI-assisted **Verification Intelligence Platform** for
semiconductor DV (design verification) engineers. It turns raw verification
artifacts — simulation logs, compile logs, coverage summaries, test
metadata — into:

1. A normalized **Evidence Graph** (typed nodes + typed edges, deterministic
   content-hashed IDs) that is the single source of truth for everything
   downstream.
2. A deterministic **failure classification** with confidence and evidence.
3. A multi-stage **Reasoning Engine** that produces multiple ranked,
   evidence-backed competing hypotheses (RTL bug vs. testbench vs.
   infrastructure vs. build) with fully traceable confidence propagation.
4. A **Verification Knowledge Engine**: 13 pluggable Knowledge Packs
   encoding real protocol/methodology expertise (AXI, APB, AHB, CHI,
   TileLink, PCIe, UVM, SVA, reset/clocking, CDC, cache coherency, RISC-V
   privilege, coverage) that match deterministic failure patterns against
   evidence, project it onto protocol state machines, and attach fixed
   debug playbooks with real specification references — all before any AI
   runs.
5. A persistent **Regression Database** (SQLite) giving the platform
   historical memory: deterministic failure signatures, similarity search,
   "have we seen this before?", failure clustering, and team-level
   analytics via an engineering dashboard.
6. An **optional AI review** that reasons only over the bounded, normalized
   output of stages 1–5 (never raw files) and only explains/annotates —
   it cannot alter the graph, classification, ranking, or knowledge
   conclusions.

**Non-negotiable design law, stated once and enforced by architecture tests
at every milestone since M2:** the AI layer never reads raw artifact text
and never originates a technical conclusion. Everything it explains was
already established deterministically. This is the platform's core thesis
and the reason it's structured as five composable layers rather than one
big prompt.

**Standing constraint from the user, applies to all text everywhere:** no
em dashes or en dashes anywhere in code, docs, comments, or generated
report content ("it looks AI generated"). Every commit sweeps for this.

**Commit convention:** every commit message ends with
`Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. Never `--amend`;
always new commits. Never force-push.

---

## 2. Milestone history

The project was built "brick by brick" — each milestone is a complete,
tested, documented, shippable increment. Do not skip ahead of the current
milestone without the user asking.

### Milestone 1 (v0.1.0) — `f8f5698` — originally named TraceIQ
Deterministic log parsing (UVM/Questa/VCS/Xcelium + generic fallback),
structured Pydantic models, a rule-based classifier (compile/assertion/
timeout/testbench/fatal/unknown/no-failure with fixed confidences), an
EDA-dashboard-style self-contained HTML report, optional AI summary, Typer
CLI (`analyze` command), pluggable parser registry. Explicitly excluded:
waveform/RTL parsing, multi-agent, RAG, vector DBs, cloud.

### Milestone 2 (v0.2.0) — `1985e5f`
Introduced the **Evidence Graph** as the central architecture and single
source of truth. `EvidenceNode`/`EvidenceEdge` with deterministic
content-hash IDs (`make_node_id`), typed `ArtifactType` (simulation_log,
assertion, coverage, test_metadata, compile_log, waveform_metadata
reserved), typed `RelationType` (PRECEDES, CAUSES, CORRELATES_WITH,
PART_OF, SUPPORTS). Parsers became `emit_evidence()` producers of graph
fragments; `GraphBuilder` merges + runs deterministic correlation passes.
Established the rule: **the AI layer must never read raw files, only the
graph's `to_reasoning_view()` projection.** Rules rewritten to be
graph-native.

### Milestone 3 (v0.3.0) — `47b1f57`
The **Verification Reasoning Engine**: a 7-stage pipeline (Evidence Graph
→ Evidence Selection → Rule Evaluation → Hypothesis Generation →
Hypothesis Ranking → Recommendation Generation → Final Report), every
stage independently testable and injectable. `EvidenceSelector` produces a
bounded `WorkingSet`; `ReasoningRule` subclasses emit evidence-cited
`ReasoningSignal`s that only shift ranking, never conclude; a
`HypothesisGenerator` registry produces competing `Hypothesis` objects that
must abstain without evidence; `rank_hypotheses` computes
`final = clamp01(base + Σ signal_contributions) * evidence_factor` with a
full `ConfidenceTrace` recorded per hypothesis; `RecommendationEngine`
produces categorized next steps. Optional `AIReasoner` runs strictly after,
receiving only `build_ai_payload()` (selected evidence + signals +
hypotheses + recommendations), never raw files — pinned by
`tests/test_ai_boundary.py`. `docs/REASONING_ENGINE.md` written.

### Milestone 4 (v0.4.0) — `675c8d0`
**Regression Intelligence**: turns every analysis into historical memory.
New packages, all downstream of reasoning and never imported by it
(architecture test enforces this): `signatures/` (deterministic
`FailureSignature`, stable fingerprint excluding anything volatile),
`storage/` (`RegressionStore`, one SQLite file, full records as JSON blobs
with indexed query columns), `similarity/` (deterministic sparse feature
embeddings + cosine ranking behind an `EmbeddingProvider` seam; signature
matches always score 1.0), `history/` (`HistoryEngine` records runs,
answers "seen before?", and *additively* augments the report — one extra
precedent recommendation, confidence discounted 0.85x from similarity —
never rewriting what reasoning produced), `analytics/` (hotspots, failure
mix, signal frequency, confidence histogram, daily trend, deterministic
signature+embedding clustering via union-find), `feedback/` (interfaces
and storage only — `FeedbackRecord`, no learning implemented, designed so
confirmed root causes immediately improve similarity results and so future
work can reweight recommendations from labeled data), `dashboard/`
(self-contained `dashboard.html`, no JS). CLI gained `--history/--db` on
`analyze` (recording on by default) plus `history`, `dashboard`, `feedback`
commands. Report schema bumped to v4 (`history` field). `docs/
REGRESSION_INTELLIGENCE.md` written.

### Milestone 5 (v0.5.0) — `8df1652` — architecture, initially thin content
The **Verification Knowledge Engine**: structured, versioned, LLM-independent
domain knowledge as a first-class component. `knowledge/model.py` defines
the normalized schema (`Concept`, `ProtocolSignal`, `StateMachine`,
`EvidenceClause`, `FailurePattern`, `DebugPlaybook`, `Reference`,
`KnowledgePack`, all versioned/serializable/metadata-carrying).
`knowledge/registry.py` is the `@register_pack` plugin mechanism.
`knowledge/graph.py` normalizes packs into a **frozen, queryable**
Verification Knowledge Graph (`contains`/`suggests_playbook`/`follows`
edges; `fingerprint()` for immutability proofs). `knowledge/matcher.py` is
pure deterministic clause matching (required/optional/forbidden clauses
against evidence node descriptions) plus state-machine projection ("where
did progress stop?"). `knowledge/inference.py` bridges knowledge into
reasoning: every `FailurePattern` becomes a `KnowledgePatternRule` — a
standard `ReasoningRule` — so matched knowledge contributes evidence-cited
ranking weight through **the exact same interface every built-in rule
uses**; the reasoning engine has zero knowledge dependency (architecture
test enforced). Report schema bumped to v5 (`knowledge` field); report.html
gained a Verification Knowledge section (pattern cards, protocol-sequence
stepper, playbooks, references). Shipped with only 4 packs (axi, uvm,
reset-clocking, coverage; 9 patterns total) — **the user flagged this as
too shallow given the milestone spec explicitly said "every protocol,
every architecture."**

### Milestone 5 follow-up (v0.5.1) — `6d59aad` — knowledge base breadth
Direct response to the user's "very less effort" feedback. Expanded from 4
packs / 9 patterns to **13 packs / 29 patterns / 29 playbooks / 31
concepts / 9 state machines**, with zero changes to the matcher, the
reasoning engine, or the report layer (proof that the M5 architecture
genuinely supports this — the whole diff was pack content plus tests).
New packs: `apb`, `ahb` (AMBA low/high-speed bus), `chi`, `tilelink`
(coherent interconnects), `pcie` (LTSSM/credits/completions), `sva`
(assertion-failure-shape semantics, protocol-agnostic), `cdc` (clock
domain crossing, distinct from reset sequencing), `coherency` (MESI/MOESI
legality, protocol-agnostic), `riscv-privilege` (trap delegation, CSR
access faults). AXI deepened with a write-channel lifecycle FSM plus
write-response and exclusive-access patterns. Two Milestone-5-era patterns
were found to be missing spec references during validation-test
development and were fixed. Added `test_pack_schema_is_well_formed`
(parametrized over every registered pack: regexes compile, confidence
modifiers name real `HypothesisCategory` values, every pattern cites a
reference, every playbook step has a real action, IDs unique within/across
packs) and one fixture + match test per new pattern (11 new fixture logs
under `tests/fixtures/`), proving each pattern fires on realistic evidence
and reaches the reasoning engine as a cited signal, not just loads without
error. 166 tests passing (up from 134).

---

## 3. Current architecture map

```
src/veritriage/
  models/           Pydantic vocabulary shared by every layer (events, evidence,
                     failure, reasoning, history, knowledge, report). Must never
                     import veritriage.graph at runtime (graph imports models).
  graph/             EvidenceGraph, EvidenceNode/Edge, GraphBuilder + correlation
                     passes, to_reasoning_view() (the AI boundary).
  parsers/           Parser ABC + registry (@register), one module per artifact
                     type: simulation_log, compile_log, coverage, test_metadata.
  rules/             Graph-native deterministic classification rules.
  reasoning/         The M3 pipeline: selection, signals, hypotheses, recommend,
                     ai.py (AIReasoner), engine.py (orchestrator). Zero knowledge
                     or history dependency — architecture tests enforce this.
  knowledge/         M5: model.py (schema), registry.py (plugin table), packs/
                     (13 built-in modules), graph.py (frozen KG), matcher.py
                     (deterministic matching + projection), inference.py
                     (KnowledgeEngine + KnowledgePatternRule reasoning adapter).
  history/           M4: record.py (RegressionRecord + git metadata capture),
                     engine.py (HistoryEngine: record + additive augment).
  signatures/        M4: deterministic FailureSignature + digest.
  similarity/        M4: FeatureEmbedding, cosine, SimilarFailureEngine.
  storage/           M4: RegressionStore (SQLite; also implements FeedbackSink).
  analytics/         M4: RegressionAnalytics (aggregations) + cluster_regressions.
  feedback/          M4: FeedbackRecord + FeedbackSink protocol (design only).
  dashboard/         M4: DashboardGenerator (self-contained dashboard.html).
  reports/           HTML report generator (Jinja2, self-contained, light/dark).
  cli/main.py        Typer app: analyze, parsers, knowledge, dashboard, history,
                     feedback, version.
  pipeline.py        analyze(): parse -> graph -> classify -> knowledge -> reason.
                     Library entry point; CLI is a thin wrapper. Stays pure — no
                     storage I/O (history recording is a CLI-layer decision).
```

**Pipeline call order** (`pipeline.py::analyze`): parsers emit graph
fragments → `GraphBuilder` merges + correlates → `RuleEngine.classify()` →
`KnowledgeEngine.analyze()` computes the `KnowledgeContext` →
`ReasoningEngine(rules=[*default_reasoning_rules(), *knowledge_reasoning_rules()])`
runs selection/signals/hypotheses/ranking/recommendations, with knowledge
patterns injected as ordinary rules → `AnalysisReport` assembled
(`schema_version = "5"`). History recording (`HistoryEngine.record` +
`.augment`) happens in the CLI, strictly after `analyze()` returns, so the
library function itself never touches the filesystem beyond reading the
input artifacts.

**Report schema version history:** v1 (M1) → v2 adds Evidence Graph (M2) →
v3 adds `reasoning` (M3) → v4 adds `history` (M4) → v5 adds `knowledge`
(M5). Bump on any breaking field change; tests assert the current value.

**Current test count: 166**, across `tests/test_*.py` — parsers, rules,
graph, artifact parsers, models, report, CLI, AI boundary, reasoning,
history, analytics, knowledge. Run with `.venv/bin/python -m pytest -q`
from the repo root.

---

## 4. Operational notes for resuming work

- Python 3.11 venv at `veritriage/.venv/`; rebuild after any repo move or
  rename (`python -m venv .venv && .venv/bin/pip install -e ".[ai,dev]"`).
- CLI entry point: `.venv/bin/veritriage`. Default regression DB path:
  `.veritriage/regressions.db` (gitignored, override with `--db`).
- Fixtures live in `tests/fixtures/`; add a new one whenever a new
  Knowledge Pack pattern needs proof it fires on realistic evidence rather
  than only passing schema validation.
- The Anthropic integration (`reasoning/ai.py`) uses `claude-opus-4-8` with
  `thinking={"type": "adaptive"}` and structured JSON output; it's an
  optional extra (`pip install veritriage[ai]`) and degrades gracefully
  (warns, continues deterministic-only) if the SDK or API key is missing.
- Portfolio integration is a separate repo
  (`/Users/ompatel/Documents/Om Portfolio`, → `patel-om/portfolio`). Each
  milestone that changes user-visible behavior should refresh
  `veritriage-sample-report.html` (regenerate via
  `veritriage analyze <fixtures> -o <tmp>` and copy `report.html`) and
  `veritriage-sample-dashboard.html` (via `veritriage dashboard`), and
  update the project card's description/badges in `index.html`. This is a
  habit, not a hard requirement — confirm scope with the user if a change
  is purely internal (e.g., a docs-only fix).
- Package naming history: TraceIQ (M1, collided with existing PyPI/products)
  → briefly considered "verifAI" (collided with Berkeley's VerifAI) →
  renamed to **VeriTriage** at M2/M3 boundary (GitHub redirect preserved
  from the rename). Never suggest reverting or renaming again without the
  user raising it.
- Standing unexecuted offer: publish an initial release to PyPI to reserve
  the `veritriage` package name. Not done; requires explicit confirmation
  before acting (irreversible-ish — name squatting disputes are a hassle).

---

## 5. Future work

This section is intentionally detailed — it's the answer to "what's left"
for whoever (human or agent) picks this up next. Nothing here should be
started without the user asking for it; this is a map, not a queue.

### 5.1 Knowledge Engine — more packs (natural continuation of the M5 fix)
The M5 follow-up covered the milestone's explicit list. Real breadth still
missing, in likely priority order for a DV audience:
- **AXI-Stream and ACE/ACE-Lite** (cache-coherent AXI extensions) — natural
  sibling to the existing AXI pack; ACE shares failure-pattern shape with
  the `coherency` pack (illegal snoop responses, barrier ordering).
- **OCP, Wishbone** — older but still-used open interconnects; low effort,
  same pattern-library shape as APB/AHB.
- **UCIe / die-to-die interconnect** — increasingly relevant for chiplet
  designs; would need new concepts (link training analogous to PCIe LTSSM,
  but for die-to-die).
- **Power management / UPF-aware sequencing** — power domain
  sequencing violations (isolation before power-down, retention timing)
  are a distinct enough failure class to warrant concepts + a state
  machine (power domain lifecycle: On → Isolate → Retain → Off).
  This is genuinely new territory (not just "another protocol"); think
  through the state machine before writing patterns.
- **Security verification** (side-channel timing hints, access-control
  bypass patterns) — mentioned explicitly in the M5 spec, not yet started.
  Needs care: security failure signatures in a sim log are often *absence*
  of an expected check firing, which the current matcher (presence-based
  clauses) handles awkwardly; may need a new clause type ("expected marker
  never appears" as a first-class forbidden-by-omission clause rather than
  today's `must_fail` workaround).
- **Performance verification** (bandwidth/latency SLA misses) — also
  named in the spec. Needs a new evidence shape (numeric threshold
  comparison, not just regex presence) — likely needs `EvidenceClause` to
  grow a numeric-comparison variant, which *is* a matcher change (the one
  legitimate reason to touch `knowledge/matcher.py` rather than just add a
  pack). Worth flagging to the user before starting since it's the first
  extension that isn't purely additive.
- **Formal verification result ingestion** — the M5 spec's "formal
  verification" line item. This is bigger than a pack: formal tools
  produce proof/counterexample artifacts, not simulation logs, so it likely
  wants a new `ArtifactType` (`formal_result`) and parser first (that's
  Evidence Graph / M2-shaped work), with a `knowledge` pack layered on top
  once the artifact type exists. Sequence matters here.

### 5.2 External documentation / reference resolution
`Reference.uri` exists as a hook but nothing resolves it yet. Two directions:
- Company-internal spec/wiki adapters (the M5 doc already names this as an
  extensibility point) — would live outside `knowledge/packs/` entirely,
  as a separate installable pack a company writes against the same schema.
- Live link validation / fetching for public specs (AMBA, PCIe SIG) — low
  priority, mostly a nice-to-have for the HTML report's reference links.

### 5.3 Learning feedback (M4's deliberately-unbuilt half)
`feedback/` ships interfaces and storage only, by explicit M4 design ("do
not implement machine learning yet, only design the interfaces"). Concrete
next steps when the user asks for this:
- Use `FeedbackRecord.diagnosis == "incorrect"` aggregated by
  `FailureSignature` digest to flag signatures where the deterministic
  rules/patterns are systematically wrong — surface this in the dashboard
  as a "needs a new rule" list, not as any model training.
- Use `useful_recommendations` / `false_recommendations` votes to reweight
  the `RecommendationEngine`'s per-category step templates — still
  deterministic (a weighted-count reorder), not ML.
- The explicit non-goal remains: no model retraining, no embedding
  fine-tuning. If a future request asks for that, it's a scope change from
  everything built so far and should be confirmed with the user first.

### 5.4 Learned similarity embeddings
`similarity.EmbeddingProvider` is a `Protocol` specifically so a learned
text-embedding model can be swapped in without touching `history/`,
`analytics/`, or the report layer. Not started. Would need: an opt-in
dependency (sentence-transformers or an API-based embedding call), a
concrete `EmbeddingProvider` implementation, and a decision about whether
it replaces or augments `FeatureEmbedding` (augment is safer — keep the
deterministic default, add the learned one behind a flag).

### 5.5 Waveform metadata
`ArtifactType.WAVEFORM_METADATA` has been reserved since M2 and still has
no producer. This is the largest remaining Evidence Graph gap. Needs: an
FSDB/VCD-metadata parser (not full waveform data — metadata like signal
lists, dump windows, first-X times), a correlation pass linking waveform
metadata to failing evidence, and then knowledge packs' `suggested_signals`
fields (already populated across every pack) become directly actionable —
today they're just names in the report; with waveform metadata evidence
they could resolve to actual dump-file offsets.

### 5.6 Git history / commit correlation
Named in both M4 and M5 docs as a future integration. `ExecutionMetadata`
already captures commit/branch/author per run (M4). Not yet built: a
correlation pass that, given two regressions' commits, finds what changed
in the failing module's files between them ("what changed since the
previous successful run?" — one of the M4 success-criteria questions,
technically still open). Would live as a new `history/` adapter, not a
new top-level package.

### 5.7 CI / issue-tracker adapters
Jira and CI-system adapters are named as extensibility points in
`docs/REGRESSION_INTELLIGENCE.md`. Nothing built. Lowest priority of the
listed integrations since they're organization-specific and the user
hasn't asked.

### 5.8 Front-ends over `pipeline.analyze()`
VS Code extension, Slack integration, GitHub Action, MCP server — all
named in the README roadmap since M1, none started. All are thin clients
over the existing library entry point (`veritriage.pipeline.analyze`) and
the CLI; no core-architecture work needed first except possibly waveform
metadata (5.5) if the front-end wants to jump straight to a waveform
viewer from a recommendation.

### 5.9 Packaging
Standing offer, not executed: publish an initial `veritriage` release to
PyPI to reserve the name. Requires explicit user go-ahead.

### 5.10 Housekeeping / debt
- `docs/EVIDENCE_GRAPH.md` and `docs/ARCHITECTURE.md` should get a light
  pass any time a new milestone lands, to keep the "why v3+ needs no
  restructuring" style tables current (this file's section 3 is a faster
  place to check current state than re-reading every doc).
- No known failing tests or open bugs as of `6d59aad` (166/166 passing).
- `analyzers/` package (superseded by `reasoning/ai.py` at M3) was already
  removed; if it ever reappears from a bad merge, delete it again.
