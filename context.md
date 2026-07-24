# VeriTriage - Project Context

This file is a continuity document: what VeriTriage is, how it got built,
where every piece lives, and what is deliberately left for later. It exists
so work can resume in a new session (or by a new contributor) without
re-deriving decisions already made. It is not user-facing documentation -
see `README.md` and `docs/` for that - this is the "how we got here and
what's next" record.

Repo: https://github.com/patel-om/veritriage (public, Apache-2.0)
Local path: `/Users/ompatel/Documents/veritriage`
Current version: **1.0.0**
Portfolio integration: card + sample artifacts in
`/Users/ompatel/Documents/Om Portfolio` (`index.html`,
`veritriage-sample-report.html`, `veritriage-sample-dashboard.html`)

---

## 1. What VeriTriage is

VeriTriage is an AI-assisted **Verification Intelligence Platform** for
semiconductor DV (design verification) engineers. It turns raw verification
artifacts - simulation logs, compile logs, coverage summaries, test
metadata - into:

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
   debug playbooks with real specification references - all before any AI
   runs.
5. A persistent **Regression Database** (SQLite) giving the platform
   historical memory: deterministic failure signatures, similarity search,
   "have we seen this before?", failure clustering, and team-level
   analytics via an engineering dashboard.
6. An **optional AI review** that reasons only over the bounded, normalized
   output of stages 1-5 (never raw files) and only explains/annotates -
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

The project was built "brick by brick" - each milestone is a complete,
tested, documented, shippable increment. Do not skip ahead of the current
milestone without the user asking.

### Milestone 1 (v0.1.0) - `f8f5698` - originally named TraceIQ
Deterministic log parsing (UVM/Questa/VCS/Xcelium + generic fallback),
structured Pydantic models, a rule-based classifier (compile/assertion/
timeout/testbench/fatal/unknown/no-failure with fixed confidences), an
EDA-dashboard-style self-contained HTML report, optional AI summary, Typer
CLI (`analyze` command), pluggable parser registry. Explicitly excluded:
waveform/RTL parsing, multi-agent, RAG, vector DBs, cloud.

### Milestone 2 (v0.2.0) - `1985e5f`
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

### Milestone 3 (v0.3.0) - `47b1f57`
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
hypotheses + recommendations), never raw files - pinned by
`tests/test_ai_boundary.py`. `docs/REASONING_ENGINE.md` written.

### Milestone 4 (v0.4.0) - `675c8d0`
**Regression Intelligence**: turns every analysis into historical memory.
New packages, all downstream of reasoning and never imported by it
(architecture test enforces this): `signatures/` (deterministic
`FailureSignature`, stable fingerprint excluding anything volatile),
`storage/` (`RegressionStore`, one SQLite file, full records as JSON blobs
with indexed query columns), `similarity/` (deterministic sparse feature
embeddings + cosine ranking behind an `EmbeddingProvider` seam; signature
matches always score 1.0), `history/` (`HistoryEngine` records runs,
answers "seen before?", and *additively* augments the report - one extra
precedent recommendation, confidence discounted 0.85x from similarity -
never rewriting what reasoning produced), `analytics/` (hotspots, failure
mix, signal frequency, confidence histogram, daily trend, deterministic
signature+embedding clustering via union-find), `feedback/` (interfaces
and storage only - `FeedbackRecord`, no learning implemented, designed so
confirmed root causes immediately improve similarity results and so future
work can reweight recommendations from labeled data), `dashboard/`
(self-contained `dashboard.html`, no JS). CLI gained `--history/--db` on
`analyze` (recording on by default) plus `history`, `dashboard`, `feedback`
commands. Report schema bumped to v4 (`history` field). `docs/
REGRESSION_INTELLIGENCE.md` written.

### Milestone 5 (v0.5.0) - `8df1652` - architecture, initially thin content
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
reasoning: every `FailurePattern` becomes a `KnowledgePatternRule` - a
standard `ReasoningRule` - so matched knowledge contributes evidence-cited
ranking weight through **the exact same interface every built-in rule
uses**; the reasoning engine has zero knowledge dependency (architecture
test enforced). Report schema bumped to v5 (`knowledge` field); report.html
gained a Verification Knowledge section (pattern cards, protocol-sequence
stepper, playbooks, references). Shipped with only 4 packs (axi, uvm,
reset-clocking, coverage; 9 patterns total) - **the user flagged this as
too shallow given the milestone spec explicitly said "every protocol,
every architecture."**

### Milestone 5 follow-up (v0.5.1) - `6d59aad` - knowledge base breadth
Direct response to the user's "very less effort" feedback. Expanded from 4
packs / 9 patterns to **13 packs / 29 patterns / 29 playbooks / 31
concepts / 9 state machines**, with zero changes to the matcher, the
reasoning engine, or the report layer (proof that the M5 architecture
genuinely supports this - the whole diff was pack content plus tests).
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

### Milestone 6 (v0.6.0) - Waveform Intelligence Engine
The reserved `ArtifactType.WAVEFORM_METADATA` (idle since M2) finally has a
producer. New `waveform/` package with the load-bearing split the milestone
demanded: **adapters** are the only format-aware code (`adapters/base.py`
`WaveformAdapter` ABC + capabilities, `adapters/registry.py` `@register_adapter`,
`adapters/manifest.py` for a simulator-independent JSON manifest, `adapters/vcd.py`
for VCD via header parse plus a bounded counter-only activity scan that never
retains transitions), and the **observation engine** (`model.py` normalized
`WaveformMetadata`, `observations.py` deterministic `ObservationDetector`s,
`engine.py` `WaveformEngine`) is format-agnostic: it consumes only normalized
metadata and turns it into engineering observations (dead clock, stalled FSM,
incomplete handshake, unretired transaction, unexpected reset, repeated retries,
sequence-never-started). Observations carry full provenance (detector,
source_adapter, input_signals, deterministic observation_id) and a confidence
that propagates into evidence and hypotheses; each has an `ObservationCategory`.
`waveform/parser.py` `WaveformParser` is an ordinary registered `Parser` (so
`pipeline.analyze()` handles a `.vcd`/`.wave.json` with no pipeline change),
dispatching to the adapter and projecting observations into evidence nodes.
`waveform/inference.py` mirrors the M5 knowledge bridge exactly:
`waveform_reasoning_rules()` wraps each ranking-relevant observation kind as a
standard `ReasoningRule`, and `build_waveform_context()` assembles the
report-facing `WaveformContext`. Additive edits only: one correlation pass
(`_link_waveform_observations_to_failures`) in `graph/builder.py` (links an
observation to a failure sharing a scope segment, making M5 `suggested_signals`
actionable), an optional `waveform` field on `AnalysisReport` (schema `5` -> `6`),
`pipeline.py` composition, a report section, a `waveform` CLI command,
`models/waveform.py` report views. **Adapter capabilities** give honest
degradation: VCD declares no TRANSACTIONS/PROTOCOL_ANNOTATIONS, so those
detectors are reported unavailable rather than silently passing. Two permanent
architecture laws written into `docs/ARCHITECTURE.md` and pinned by tests:
core-format isolation and lossy-by-design ingestion. The crown-jewel test
`test_new_simulator_needs_only_an_adapter` registers a throwaway fake-format
adapter inside the test and proves it reaches evidence, reasoning, and the
report with zero core changes. 28 new tests (189 total, up from 161 actual at
the M5.1 head; note the M5.1 entry's "166" was optimistic, the real count was
161). Design doc: `docs/WAVEFORM_ENGINE.md`. User-approved refinements folded
in: observation provenance, categories, adapter capability declaration,
confidence propagation, and the two laws.

### Milestone 7 (v0.7.0) - Engineering Context Engine
Answers "what changed?" before "what broke?": engineering change becomes one
more normalized evidence source, and VeriTriage grows from a verification
intelligence platform into an engineering investigation platform. New
`engineering/` package with the M6 split applied to tools: **providers** are
the only tool-aware code (`providers/base.py` `ContextProvider` ABC +
`ContextCapability`, `providers/registry.py` `@register_provider` +
`collect_context`, `providers/git.py` local git via subprocess, the platform's
ONLY git call site, `providers/manifest.py` canonical `*.engctx.json` any CI
can export), and everything downstream is tool-agnostic: `model.py` (frozen
`EngineeringContext`: bounded commits with categorized `ChangedFile`s, `CIRun`
with declared `environment_changes`, `Ownership`, `IssueRef`; lossy by design,
no diffs or patch text survive), `context.py` (evidence emission + report view
+ ownership augment), `inference.py` (4 modest-weight `ReasoningRule`s:
RTL/testbench change in failing scope, build-flow change, environment drift
toward INFRASTRUCTURE), `impact.py` (deterministic two-tier test impact:
in-run pure, historical via CLI-mapped `HistoricalRegression` slices; no
storage import), `ownership.py` (routing recommendation only, appended via the
M4 additive-augment seam; never ranking, test-enforced), `timeline.py` +
`investigation.py` (pure projections of the Evidence Graph, never new graphs,
mutation-tested). One new enum member (`ArtifactType.ENGINEERING_CHANGE`),
zero new relation types. Additive edits: correlation pass
`_link_engineering_changes_to_failures`, `analyze(engineering=...)` optional
keyword (CLI gathers via providers with `--context/--no-context`, default on,
degrades silently outside a repo; pipeline stays pure), report schema `6` ->
`7` (`engineering` field), report section, CLI commands `context`,
`investigate`, `impact`. **M4 migration:** `capture_execution_metadata` now
delegates (lazily) to `providers/git.py::execution_snapshot`, so the "no git
outside providers" law holds repo-wide with no grandfather clause. Ownership
and issues deliberately never become graph nodes. Two permanent laws in
`docs/ARCHITECTURE.md` (core-tool isolation; evidence never conclusions),
each test-pinned. Crown-jewel test `test_new_system_needs_only_a_provider`:
a fake Perforce provider defined inside the test reaches evidence,
correlation, reasoning, and the report with zero core changes. 24 new tests
(213 total). CLI tests pin `--no-context` for determinism (they run inside
the real repo). Design doc: `docs/ENGINEERING_CONTEXT_ENGINE.md` (approved
before implementation; scope, git-law migration, and default-on context all
user-confirmed).

### Milestone 8 (v0.8.0) - Verification Workspace & MCP Platform
The Verification Intelligence Core is declared architecturally complete in
*shape* (packs/adapters/providers still grow through registries); M8 builds
around it, never into it. New `workspace/` package: `session.py`
(`InvestigationSession`, frozen: report + graph + deterministic content-hash
`session_id`; identity never depends on wall-clock), `persistence.py`
(`SessionStore`, one JSON bundle per session under `.veritriage/sessions/`,
byte-identical re-save), `services.py` (`WorkspaceServices`: THE public API:
investigate with optional record_history so history augmentation happens
before the session freezes, save/load/list, summary, evidence queries +
bounded graph view, matched patterns, waveform observations, engineering
context, timeline with graph-built fallback, read-only similar_regressions
probe, deterministic compare), `navigation.py` (every report section
individually addressable: one hypothesis/pattern/observation/commit/timeline
event/evidence node, None on miss), `search.py` (deterministic evidence +
knowledge-base search). New `mcp/` package: `tools.py` (transport-agnostic
tool table, 12 v1 tools, all routing through services; `register_tool` is the
new-endpoint extension point) and `server.py` (dependency-free MCP stdio
transport: newline-delimited JSON-RPC 2.0 subset: initialize, ping,
tools/list, tools/call; protocol version 2024-11-05; tool failures return
isError results, never crash the loop). **The CLI became client number one:**
analyze/investigate route through WorkspaceServices, cli/main.py no longer
imports veritriage.pipeline (AST-verified guard), investigate saves and
prints its session id, and new commands `mcp` (serve stdio) and `sessions`
(list bundles) landed. No report schema change (v7 stays; sessions wrap it).
No core file changed except cli/main.py. Architecture guards:
cli-and-mcp-share-services, sessions-immutable, public-API-never-exposes-raw
-parser-objects (AST import analysis: the third prose-vs-code guard lesson,
now done properly), no-engine-knows-workspace, workspace-never-depends-on-AI,
mcp-tools-route-through-services, and the crown jewel
`test_new_endpoint_needs_only_a_tool` (a throwaway tool registered inside the
test is served through the real transport with zero core changes). 25 new
tests (238 total). Review decisions (user-confirmed): hand-rolled stdio over
the official SDK (zero deps, offline-testable; SDK adapter is a future thin
file), two cohesive packages instead of the spec's seven examples, full
CLI-as-client refactor. Design doc: `docs/WORKSPACE_PLATFORM.md` (approved
before implementation).

### Milestone 9 (v0.9.0) - Investigation Orchestrator
An orchestration layer that composes existing Workspace Services into complete
investigations; it schedules and observes, never concludes (every technical
conclusion still comes from the deterministic stack, unchanged). New
`orchestrator/` package: `steps.py` (`InvestigationStep` ABC +
`@register_step` + 10 built-in steps, each a thin `WorkspaceServices` call:
gather-context, analyze-artifacts, summarize, historical-lookup,
knowledge-review, waveform-review, engineering-review, build-timeline,
render-report, persist-session), `profiles.py` (`@register_profile` + 7
built-ins: fast-triage, full-investigation, regression-analysis,
protocol-debug, waveform-focused, infrastructure-review, engineering-review;
`build_plan` with deterministic plan IDs), `engine.py` (deterministic Kahn
execution: sorted-id ready frontier = the future-async seam; per-step retry
budget; failure isolation with transitive-dependent SKIP and surviving
independent branches; partial completion; `run_profile`; `resume_profile`
re-runs only non-COMPLETED steps; `attribute_subsystems` maps signals by name
prefix and recommendations by rationale marker to knowledge/waveform/
engineering/history/ownership/rules/reasoning). **Key design decision
(user-approved):** the deterministic pipeline is ONE atomic `analyze-artifacts`
step; per-subsystem visibility comes from trace attribution, NOT from
fragmenting reasoning (which would duplicate it or dismantle the core's
test-pinned composition). Vocabulary in `models/orchestration.py` (frozen
`InvestigationPlan`/`PlanStep`/`StepStatus`/`StepTrace`/`SubsystemAttribution`/
`InvestigationTrace`; `structural_view()` strips timings for determinism
comparison) so the session can reference it while the workspace stays below
the orchestrator. Additive edits only: two workspace service methods
(`gather_engineering_context`, `render_report`; both benefit MCP too), two
optional `InvestigationSession` fields (`plan`, `trace`, attached via
`model_copy` so identity is unchanged: workflow bookkeeping is never
identity), a presentation-only report "Investigation performance" section
(`HtmlReportGenerator.render(metrics=...)`, byte-identical without metrics),
CLI `run`/`profiles` commands, 5 MCP tools (run_investigation, list_profiles,
get_investigation_plan, get_investigation_trace, resume_investigation). No
core engine changed; no report schema change (sessions wrap v7). Architecture
guards: orchestrator-never-bypasses-services (AST: imports only workspace +
models + itself), core-unchanged-by-orchestration (nothing below imports it,
workspace included), plans/traces-immutable, profiles-only-compose-registered
-steps, no-AI, and the crown jewel `test_new_step_needs_only_registration` (a
throwaway step + profile run through the real engine with zero core changes).
18 new tests (256 total). Two implementation deltas from the design, both doc
-noted: models live in models/orchestration.py (layer-neutral), and
regression-analysis ships without a compare-to-precedent step (historical
matches carry regression IDs not session IDs; services.compare stays available
directly). Design doc: `docs/INVESTIGATION_ORCHESTRATOR.md` (approved before
implementation).

### Milestone 10 (v1.0.0) - Collaborative Investigation Platform
The capstone, and the version freeze. Makes investigations portable,
reviewable, reproducible engineering artifacts, and declares the public API
stable. New `collab/` package: `model.py` (frozen `InvestigationBundle` =
session + reviews + annotations + `BundleMetadata`; content-derived `bundle_id`;
sha256 integrity `fingerprint`; `seal_bundle` recomputes both on any amend;
`extra="allow"` for forward compatibility), `exchange.py` (deterministic
canonical JSON + gzip mtime=0 -> `.vtb`; lossless round-trip; auto-detects
compression on import; no raw waveform/log files embedded, only the normalized
session incl. per-node raw_line provenance), `validation.py` (deterministic
`ValidationResult`: schema-major compat, fingerprint recompute, bundle_id/
session_id consistency, dangling-annotation + dangling-edge + dangling-
hypothesis detection, unknown-extension warnings), `review.py` (5 verdicts:
approved/needs_investigation/incorrect_diagnosis/incomplete_evidence/
false_positive; `add_review` returns a new sealed bundle), `annotation.py`
(`@register_annotation_target` registry + 6 built-in kinds: evidence,
knowledge-pattern, waveform-observation, engineering-commit, recommendation,
execution-step; `add_annotation` rejects unknown kinds and dangling targets),
`comparison.py` (explanatory diff across classification/evidence/knowledge/
waveform/engineering/recommendations/trace/metadata with a human summary
sentence). **Reviews and annotations layer on top; the session is never
mutated and reasoning is never affected** (deep-compare tests). Additive
integration only: WorkspaceServices gains bundle methods (export/import/
validate/review/annotate/compare/collaboration_view) that reach collab via
LAZY imports so services stays the boundary with no import-time coupling; an
optional report Collaboration section (`render(collaboration=...)`, plain data,
byte-identical without it); CLI `bundle` sub-app (export/import/validate/
compare) + `review`/`annotate` commands; 7 MCP tools (export/import/validate/
compare_bundles/get_bundle_metadata/list_reviews/list_annotations). No core
engine changed; NO report schema change (collab lives in the bundle, not the
report). collab imports only workspace + models (AST-verified); nothing below
imports collab. Crown jewel `test_new_annotation_target_needs_only_registration`
(a throwaway target kind validates and round-trips with zero core changes). 22
new tests (278 total). Version freeze: pyproject Development Status -> 5 -
Production/Stable; the public API (WorkspaceServices, MCP tool table,
orchestrator step/profile registries, .vtb format) is declared stable. Review
decisions (user-confirmed): ship AS v1.0.0, include raw_line in bundles, one
collab/ package. Design doc: `docs/COLLABORATION_PLATFORM.md` (approved before
implementation).

**As of v1.0.0 the core is complete and stable.** Future milestones are
integrations and ecosystem adoption over existing seams (section 5.8), never
core expansion.

### Knowledge Base Expansion program (post-1.0, content-only)

A user-approved drive to make the Verification Knowledge Engine *elite in
breadth*: grow from 13 packs toward a broad, deep library across four domain
tiers. Every tier is additive content exactly like the M5.1 expansion - new
`knowledge/packs/` modules plus one realistic fixture per pattern - with zero
change to `EvidenceClause`, the matcher, the Knowledge Graph, reasoning, or
the report. Backward compatible; minor-version releases.

- **Tier 1 (v1.1.0) - RISC-V & CPU/ISA depth.** Six new packs beside the
  existing `riscv-privilege`: `riscv-atomics` (LR/SC forward progress, AMO
  aq/rl ordering), `riscv-vector` (illegal vtype, tail/mask undisturbed
  policy, vl element-count), `riscv-memory-model` (RVWMO ordering, FENCE
  enforcement), `riscv-interrupts` (PLIC priority inversion, claim/complete
  gateway, mie/mip masking), `riscv-pmp` (access-fault miss, NAPOT/TOR
  boundary decode), `riscv-debug` (abstract-command cmderr, halt-request
  timeout). 14 new patterns/playbooks, 3 new state machines, 14 fixtures.
  Breadth floors in `test_knowledge.py` raised (>=18 packs, >=40 patterns/
  playbooks/concepts). 19 packs / 44 patterns total; 298 tests (up from 278).
- **Tier 2 (v1.2.0) - Interconnect & NoC.** Five new packs: `axi-stream`
  (TLAST packet framing, backpressure deadlock), `ace` (snoop CR response,
  barrier ordering), `noc` (routing deadlock, credit underflow, HOL blocking
  + packet-lifecycle state machine), `cxl` (Flex Bus negotiation, CXL.mem
  completion), `ucie` (die-to-die training, lane repair/degrade). 11 new
  patterns/playbooks, 1 state machine, 11 fixtures. Floors raised (>=24
  packs, >=55 patterns). 24 packs / 55 patterns / 53 playbooks / 54 concepts;
  314 tests.
- **Tier 3 (v1.3.0) - Memory & Serial IO.** Nine new packs: `ddr` (command
  timing, refresh discipline), `hbm` (channel decode, per-channel refresh),
  `usb` (transaction handshake, USB3 LTSSM), `ethernet` (MAC FCS, PCS block
  lock), `mipi` (D-PHY HS sync, CSI-2 ECC/CRC), `i2c-i3c` (I2C ACK, I3C IBI),
  `spi` (CPOL/CPHA, CS framing), `uart` (framing, RX overrun), `jtag` (TAP FSM
  + IR/DR scan, with a TAP state machine). 18 new patterns/playbooks, 1 state
  machine, 18 fixtures. As planned, only presence-expressible failure modes
  ship; memory-timing SLA and performance patterns still wait on the future
  numeric-clause upgrade (5.1) - each such pack notes this in its docstring.
  Floors raised (>=33 packs, >=72 patterns). 33 packs / 73 patterns / 71
  playbooks / 72 concepts; 341 tests.
- **Tier 4 (v1.4.0) - Methodology & fundamentals depth.** Seven new packs:
  `uvm-ral` (mirror/prediction, field access policy), `uvm-phasing`
  (objection leak, phase order), `uvm-tlm` (port connectivity, analysis
  drop), `formal` (counterexample, vacuous pass, inconclusive bound),
  `low-power` (isolation, retention + the On/Isolate/Retain/Off power-domain
  state machine), `dft` (scan-chain integrity, MBIST signature),
  `x-propagation` (uninitialized-X read, X through control). 15 new
  patterns/playbooks, 1 state machine, 15 fixtures. As flagged: `low-power`
  ships the new power-domain state machine; `formal` reads formal-tool *log
  results* only (native proof-artifact ingestion still wants a dedicated
  ArtifactType, 5.1). Floors raised (>=40 packs, >=86 patterns). Final:
  **40 packs / 88 patterns / 86 playbooks / 86 concepts / 15 state machines**;
  363 tests.

**Knowledge Base Expansion (Tiers 1-4, v1.1.0-v1.4.0).** The engine grew from
13 packs to 40 across six domains (interconnect, CPU/ISA, memory, serial IO,
coherency, methodology/fundamentals) with no change to `EvidenceClause`, the
matcher, the Knowledge Graph, reasoning, or the report - proving the M5
registry architecture scales to elite breadth on content alone.

### Clause expressiveness upgrade (v1.5.0) - the one sanctioned matcher change

The first change to `knowledge/matcher.py` and `EvidenceClause` since M5, and
the single legitimate one flagged in section 5.1. Strictly additive and
backward compatible (the 363 pre-existing tests passed unchanged before any
new pack was added):
- **Numeric clauses.** New `NumericConstraint` (op in gt/ge/lt/le/eq/ne +
  value) on `EvidenceClause.numeric`. The clause's regex locates a number
  (first capture group, else first number in the match) and the node matches
  only when the value satisfies the threshold. Turns "the word latency
  appears" into "latency over 1000 ns".
- **Omission clauses.** New `EvidenceClause.absent`: as a *required* clause it
  is satisfied when NO node matches, a first-class "this expected marker never
  appeared" replacing the old must_fail/pattern="." trick.
- **Unlocked packs.** `performance` (latency/bandwidth SLA misses via numeric
  clauses) and `security` (access-control bypass, unverified secure boot via
  omission clauses) - the two domains named in the M5 spec that presence-only
  matching could not express. Dedicated unit tests pin the numeric boundary
  (fires at 3200 ns, silent at 200 ns) and omission semantics (blocked the
  moment the expected check appears).

Final: **42 packs / 92 patterns / 90 playbooks / 90 concepts / 15 state
machines**; 373 tests. Section 5.1's numeric-comparison and
forbidden-by-omission items are now resolved; native formal proof-artifact
ingestion (a new ArtifactType) remains the only deferred knowledge item.

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
                     or history dependency - architecture tests enforce this.
  knowledge/         M5: model.py (schema), registry.py (plugin table), packs/
                     (13 built-in modules), graph.py (frozen KG), matcher.py
                     (deterministic matching + projection), inference.py
                     (KnowledgeEngine + KnowledgePatternRule reasoning adapter).
  waveform/          M6: model.py (normalized WaveformMetadata + observations),
                     adapters/ (base+registry+manifest+vcd; the ONLY format-aware
                     code), observations.py + engine.py (format-agnostic detectors),
                     parser.py (WaveformParser: Evidence Graph seam), inference.py
                     (waveform_reasoning_rules + build_waveform_context). Never
                     imported by reasoning; architecture tests enforce isolation.
  engineering/       M7: model.py (frozen EngineeringContext + capabilities),
                     providers/ (base+registry+git+manifest; the ONLY tool-aware
                     code, and the only git call site in the platform),
                     parser.py (*.engctx.json artifact seam), context.py
                     (evidence emission + view + ownership augment), inference.py
                     (engineering_reasoning_rules), impact.py (two-tier test
                     impact), ownership.py (routing only), timeline.py +
                     investigation.py (pure graph projections). Never imported
                     by reasoning; architecture tests enforce isolation.
  workspace/         M8: session.py (immutable InvestigationSession), services.py
                     (WorkspaceServices, THE public API every client consumes),
                     persistence.py (session bundles), navigation.py (addressable
                     report sections), search.py (deterministic search). Imports
                     the core; NOTHING in the core imports it (guard-enforced).
  mcp/               M8: tools.py (transport-agnostic tool table over services,
                     24 tools incl. 5 M9 orchestration + 7 M10 collaboration
                     tools, register_tool extension point), server.py
                     (dependency-free MCP stdio JSON-RPC transport). Serve with
                     `veritriage mcp`.
  orchestrator/      M9: steps.py (InvestigationStep + register_step + 10 built-in
                     steps), profiles.py (register_profile + 7 profiles +
                     build_plan), engine.py (deterministic execution, trace,
                     attribution, run_profile + resume_profile). Imports ONLY the
                     workspace + models vocabulary; nothing below imports it.
  collab/            M10: model.py (frozen InvestigationBundle + fingerprint),
                     exchange.py (.vtb export/import), validation.py, review.py,
                     annotation.py (register_annotation_target + 6 kinds),
                     comparison.py (explanatory diff). Imports ONLY workspace +
                     models; nothing below imports it. Reached via WorkspaceServices
                     (lazy import); clients never import collab directly.
  history/           M4: record.py (RegressionRecord + git metadata capture),
                     engine.py (HistoryEngine: record + additive augment).
  signatures/        M4: deterministic FailureSignature + digest.
  similarity/        M4: FeatureEmbedding, cosine, SimilarFailureEngine.
  storage/           M4: RegressionStore (SQLite; also implements FeedbackSink).
  analytics/         M4: RegressionAnalytics (aggregations) + cluster_regressions.
  feedback/          M4: FeedbackRecord + FeedbackSink protocol (design only).
  dashboard/         M4: DashboardGenerator (self-contained dashboard.html).
  reports/           HTML report generator (Jinja2, self-contained, light/dark).
  cli/main.py        Typer app: analyze, parsers, knowledge, waveform, context,
                     investigate, impact, mcp, sessions, run, profiles, bundle
                     (export/import/validate/compare), review, annotate, dashboard,
                     history, feedback, version. Since M8 a WorkspaceServices client
                     (never imports veritriage.pipeline); M9 run/profiles drive the
                     orchestrator; M10 bundle/review/annotate drive collaboration.
  pipeline.py        analyze(): parse -> graph -> classify -> knowledge -> reason.
                     Waveform artifacts and context manifests parse like any other
                     (registered Parsers); waveform + engineering reasoning rules
                     join the rule set beside knowledge rules; build_waveform_context
                     and build_engineering_view fill the report; ownership augment
                     appends last. analyze(engineering=...) accepts CLI-collected
                     context so the library stays pure, no provider or storage I/O
                     (context gathering and history recording are CLI decisions).
```

**Pipeline call order** (`pipeline.py::analyze`): parsers emit graph
fragments → `GraphBuilder` merges + correlates → `RuleEngine.classify()` →
`KnowledgeEngine.analyze()` computes the `KnowledgeContext` →
`ReasoningEngine(rules=[*default_reasoning_rules(), *knowledge_reasoning_rules(), *waveform_reasoning_rules(), *engineering_reasoning_rules()])`
runs selection/signals/hypotheses/ranking/recommendations, with knowledge
patterns, waveform observations, and engineering changes all injected as
ordinary rules → `AnalysisReport` assembled (`schema_version = "7"`,
`waveform` field via `build_waveform_context` and `engineering` field via
`build_engineering_view`). History recording (`HistoryEngine.record` +
`.augment`) happens in the CLI, strictly after `analyze()` returns, so the
library function itself never touches the filesystem beyond reading the
input artifacts.

**Report schema version history:** v1 (M1) → v2 adds Evidence Graph (M2) →
v3 adds `reasoning` (M3) → v4 adds `history` (M4) → v5 adds `knowledge`
(M5) → v6 adds `waveform` (M6) → v7 adds `engineering` (M7). Bump on any
breaking field change; tests assert the current value (`test_cli.py`).

**Current test count: 278**, across `tests/test_*.py`: parsers, rules,
graph, artifact parsers, models, report, CLI, AI boundary, reasoning,
history, analytics, knowledge, waveform, engineering, workspace/MCP,
orchestrator, collaboration. Run with `.venv/bin/python -m pytest -q` from
the repo root.

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
  habit, not a hard requirement - confirm scope with the user if a change
  is purely internal (e.g., a docs-only fix).
- Package naming history: TraceIQ (M1, collided with existing PyPI/products)
  → briefly considered "verifAI" (collided with Berkeley's VerifAI) →
  renamed to **VeriTriage** at M2/M3 boundary (GitHub redirect preserved
  from the rename). Never suggest reverting or renaming again without the
  user raising it.
- Standing unexecuted offer: publish an initial release to PyPI to reserve
  the `veritriage` package name. Not done; requires explicit confirmation
  before acting (irreversible-ish - name squatting disputes are a hassle).

---

## 5. Future work

This section is intentionally detailed - it's the answer to "what's left"
for whoever (human or agent) picks this up next. Nothing here should be
started without the user asking for it; this is a map, not a queue.

### 5.1 Knowledge Engine - more packs (natural continuation of the M5 fix)
The M5 follow-up covered the milestone's explicit list. Real breadth still
missing, in likely priority order for a DV audience:
- **AXI-Stream and ACE/ACE-Lite** (cache-coherent AXI extensions) - natural
  sibling to the existing AXI pack; ACE shares failure-pattern shape with
  the `coherency` pack (illegal snoop responses, barrier ordering).
- **OCP, Wishbone** - older but still-used open interconnects; low effort,
  same pattern-library shape as APB/AHB.
- **UCIe / die-to-die interconnect** - increasingly relevant for chiplet
  designs; would need new concepts (link training analogous to PCIe LTSSM,
  but for die-to-die).
- **Power management / UPF-aware sequencing** - power domain
  sequencing violations (isolation before power-down, retention timing)
  are a distinct enough failure class to warrant concepts + a state
  machine (power domain lifecycle: On → Isolate → Retain → Off).
  This is genuinely new territory (not just "another protocol"); think
  through the state machine before writing patterns.
- **Security verification** (side-channel timing hints, access-control
  bypass patterns) - mentioned explicitly in the M5 spec, not yet started.
  Needs care: security failure signatures in a sim log are often *absence*
  of an expected check firing, which the current matcher (presence-based
  clauses) handles awkwardly; may need a new clause type ("expected marker
  never appears" as a first-class forbidden-by-omission clause rather than
  today's `must_fail` workaround).
- **Performance verification** (bandwidth/latency SLA misses) - also
  named in the spec. Needs a new evidence shape (numeric threshold
  comparison, not just regex presence) - likely needs `EvidenceClause` to
  grow a numeric-comparison variant, which *is* a matcher change (the one
  legitimate reason to touch `knowledge/matcher.py` rather than just add a
  pack). Worth flagging to the user before starting since it's the first
  extension that isn't purely additive.
- **Formal verification result ingestion** - the M5 spec's "formal
  verification" line item. This is bigger than a pack: formal tools
  produce proof/counterexample artifacts, not simulation logs, so it likely
  wants a new `ArtifactType` (`formal_result`) and parser first (that's
  Evidence Graph / M2-shaped work), with a `knowledge` pack layered on top
  once the artifact type exists. Sequence matters here.

### 5.2 External documentation / reference resolution
`Reference.uri` exists as a hook but nothing resolves it yet. Two directions:
- Company-internal spec/wiki adapters (the M5 doc already names this as an
  extensibility point) - would live outside `knowledge/packs/` entirely,
  as a separate installable pack a company writes against the same schema.
- Live link validation / fetching for public specs (AMBA, PCIe SIG) - low
  priority, mostly a nice-to-have for the HTML report's reference links.

### 5.3 Learning feedback (M4's deliberately-unbuilt half)
`feedback/` ships interfaces and storage only, by explicit M4 design ("do
not implement machine learning yet, only design the interfaces"). Concrete
next steps when the user asks for this:
- Use `FeedbackRecord.diagnosis == "incorrect"` aggregated by
  `FailureSignature` digest to flag signatures where the deterministic
  rules/patterns are systematically wrong - surface this in the dashboard
  as a "needs a new rule" list, not as any model training.
- Use `useful_recommendations` / `false_recommendations` votes to reweight
  the `RecommendationEngine`'s per-category step templates - still
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
it replaces or augments `FeatureEmbedding` (augment is safer - keep the
deterministic default, add the learned one behind a flag).

### 5.5 Waveform metadata - DONE in M6 (v0.6.0)
Delivered by the Waveform Intelligence Engine. `ArtifactType.WAVEFORM_METADATA`
now has a producer via `WaveformParser` + adapters (VCD and a JSON manifest;
FSDB/FST/WLF are documented next adapters). The correlation pass
`_link_waveform_observations_to_failures` links observations to failing
evidence sharing a scope segment, and knowledge packs' `suggested_signals` are
now actionable in practice. Remaining follow-ups worth a future milestone:
richer transaction/handshake inference from raw VCD (today VCD honestly
declares no TRANSACTIONS/PROTOCOL_ANNOTATIONS capability and reports those
analyses unavailable); a numeric-threshold observation kind for timing/perf
(would want the same numeric `EvidenceClause` variant flagged in 5.1, so
coordinate the two); resolving observation scopes to actual dump-file offsets
so a report link can jump straight into the viewer. See
`docs/WAVEFORM_ENGINE.md`.

### 5.6 Git history / commit correlation - LARGELY DONE in M7 (v0.7.0)
Delivered by the Engineering Context Engine, which superseded the M4-era
plan of "a new history/ adapter" with a first-class `engineering/` package
(providers are a general seam, not a git-only one; the M7 spec was explicit
about this). Shipped: recent-commit collection (git provider), change ->
failure correlation pass, change-category reasoning signals, ownership
routing, two-tier test impact, timeline, investigation view.
`capture_execution_metadata` now delegates to the git provider. Remaining
follow-up worth a future increment: cross-regression diffing ("what changed
between THIS run's commit and the last green run's commit?"), which needs
the regression DB's per-run commits joined with a provider diff query;
would live as a new history-aware analysis in `engineering/impact.py` or a
`history/` consumer, still behind the provider seam.

### 5.7 CI / issue-tracker adapters - seam now exists (M7)
The `ContextProvider` interface (M7) is exactly the seam these plug into:
a Jenkins/GitHub-Actions/Jira/DOORS integration is one registered provider
class, proven by `test_new_system_needs_only_a_provider`. The canonical
`*.engctx.json` manifest already lets any CI feed context without a
dedicated provider. Live API providers remain unbuilt (organization
specific; the user hasn't asked).

### 5.8 Front-ends and clients - MCP DONE in M8 (v0.8.0); rest are thin clients
The MCP server shipped in M8 (`veritriage mcp`, 12 tools over stdio), and
the client seam moved up a level: front-ends are no longer "thin clients
over `pipeline.analyze()`" but thin clients over `WorkspaceServices` (in
process) or the MCP tools (out of process); `pipeline.analyze()` is now an
internal detail only the service layer calls. Remaining, in rough order of
value: **VS Code extension** (everything it needs exists: sessions,
navigation getters for lazy trees, search; it is a rendering shell),
Claude Code / Cursor onboarding docs (an `mcpServers` config snippet is all
a user needs), Slack integration, GitHub Action (run `veritriage analyze`
in CI, upload the session bundle + report as artifacts). None require core
or workspace changes; `test_new_endpoint_needs_only_a_tool` is the proof.

### 5.9 Packaging
Standing offer, not executed: publish an initial `veritriage` release to
PyPI to reserve the name. Requires explicit user go-ahead.

### 5.10 Housekeeping / debt
- `docs/EVIDENCE_GRAPH.md` and `docs/ARCHITECTURE.md` should get a light
  pass any time a new milestone lands, to keep the "why v3+ needs no
  restructuring" style tables current (this file's section 3 is a faster
  place to check current state than re-reading every doc).
- No known failing tests or open bugs as of M10 / v1.0.0 (278/278 passing).
- `analyzers/` package (superseded by `reasoning/ai.py` at M3) was already
  removed; if it ever reappears from a bad merge, delete it again.
