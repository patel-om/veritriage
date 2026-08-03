# Agent Framework (M12)

Status: design approved, implemented in v1.8.0. This document is the
architectural baseline for the Agent Framework and its Coordinator. It obeys
every law in the platform baseline (Evidence Graph ownership, the AI boundary,
deterministic reasoning, registry-shaped extension, evidence-backed
conclusions). Prose here is intentionally free of em and en dashes per the
standing style law.

---

## 1. Vision

VeriTriage becomes an AI-native Verification Intelligence Platform by making AI
an *orchestration layer*, not a text generator bolted to the end of a pipeline.

The distinction matters. Through v1.7.0 the platform's only AI was
`reasoning/ai.py`: one optional call that received the finished deterministic
result and wrote prose beside it. That is AI as a leaf. M12 introduces AI as a
*shape*: specialized reasoning components, each responsible for one verification
domain, each forming and defending an evidence-backed position, coordinated by a
component that detects where they agree, where they conflict, and how much the
combined picture should be trusted.

Crucially, the shape is deterministic first. Every agent in this milestone is a
pure function of normalized evidence. Generative intelligence is a declared,
optional seam that can only add narrative, never conclusions. The architecture
separates Deterministic Intelligence from Generative Intelligence so completely
that swapping in GPT, Claude, Gemini, a local model, or an MCP AI provider is a
new class implementing one protocol, with no change to the Coordinator, to any
agent, or to any contract.

---

## 2. Problem statement

The platform already has agent *parts*, scattered across three layers under
three different names, with no agent *unit*:

- `ReasoningRule` observes a bounded working set and emits one evidence-cited
  observation with per-category weights and a confidence multiplier. It cannot
  produce a hypothesis, a recommendation, or a stated limitation. It observes
  once and stops.
- `HypothesisGenerator` produces one evidence-backed hypothesis and abstains
  when it cannot cite evidence, but is fixed at four categories and emits no
  observations.
- `KnowledgePatternRule` gives 92 domain specialists, each scoped to a single
  protocol pattern. AXI speaks four separate times and never once as "the AXI
  view of this failure".
- `waveform`, `engineering`, and `project` rule sets are subsystem specialists
  injected as peers into one flat rule list. They contribute weight, never a
  position.
- `rank_hypotheses` is already a merge function: it fuses N independent
  contributors into a ranked list with a complete `ConfidenceTrace`. It merges
  weights, not opinions, and has no concept of agreement or conflict.
- `ExecutionEngine` is already a coordinator: DAG scheduling, retries, failure
  isolation, per-step timing, and per-subsystem attribution. It coordinates
  workflow steps, not reasoning positions.

Four things are genuinely missing, and M12 supplies exactly those four:

1. a per-domain aggregation unit (one AXI view, not four AXI patterns);
2. a standard multi-part output contract (observations, hypotheses,
   recommendations, limitations, confidence, citations) reusable by every future
   agent;
3. explicit agreement and conflict detection across independent positions;
4. a place for generative intelligence to attach per domain, behind a seam,
   instead of once globally behind a vendor import.

---

## 3. The load-bearing decision

Stated once, in the style of the M6, M7, and M11 laws:

> **Agents form a second opinion, never a replacement verdict.** The Coordinator
> consumes the finished deterministic `ReasoningResult` and cross-examines it. It
> never mutates it, never reorders `reasoning.hypotheses`, and explicitly records
> whether it agrees with the deterministic ranking. When the agent layer and the
> reasoning engine disagree, the report shows both positions and says so.

This is what keeps the platform's thesis intact. `ReasoningRule` is already the
"shift the ranking" seam; adding agents there would only produce more rules.
Agents exist for the thing rules structurally cannot do: hold a position, support
it with observations, recommend action from it, and state honestly what it could
not determine.

Two corollaries follow, and both are test-pinned:

1. **Agents never read raw artifacts.** An agent is handed an `AgentContext`
   containing normalized evidence and normalized lenses. It is never handed a
   path, a file handle, a parser, an adapter, or a provider. It cannot read a raw
   artifact because it is never given one.
2. **Agents never duplicate parsing or classification.** Every fact an agent
   states traces to an Evidence Graph node ID produced by a parser, or a
   knowledge item ID produced by a pack. Agents interpret; they do not extract.

---

## 4. Where it belongs

New top-level package `src/veritriage/agents/`, above reasoning and above every
lens, below the pipeline:

```
models  <  graph  <  parsers/rules  <  reasoning  <  knowledge/waveform/engineering/project
                                                                    ^
                                                                agents          (new)
                                                                    ^
                                                          pipeline  <  workspace  <  mcp/orchestrator/collab  <  cli
```

`agents/` may import `models`, `graph`, and `knowledge` (to query the Knowledge
Graph). It never imports `parsers`, `reasoning.ai`, `workspace`, any provider,
any adapter, or any vendor SDK. Nothing below `agents/` imports it.

```
src/veritriage/agents/
  context.py       AgentContext (frozen input) + build_agent_context
  base.py          Agent ABC + the result builder that enforces the contract
  registry.py      @register_agent, available_agents, get_agent, unregister_agent
  providers.py     ReasoningProvider protocol + NullProvider + DeterministicProvider
                   + provider registry (the Deterministic/Generative boundary)
  coordinator.py   AgentCoordinator: invoke, merge, detect consensus and conflict
  builtin/         one module per built-in agent (eight ship in M12)

src/veritriage/models/agents.py    layer-neutral report/API vocabulary
```

---

## 5. The three contracts

### AgentContext (input)

Frozen. The only thing any agent ever receives:

| Field | Source |
|---|---|
| `graph` | the Evidence Graph (read-only) |
| `classification` | the rule engine's primary verdict |
| `reasoning` | the completed deterministic `ReasoningResult` |
| `knowledge` | `KnowledgeContext`: matched patterns, concepts, state projection |
| `knowledge_graph` | the frozen Knowledge Graph, for pack and pattern lookup |
| `project` | `ProjectContext` when a project model was supplied |
| `waveform` | `WaveformContext` when waveform metadata was ingested |
| `engineering` | `EngineeringContextView` when context was gathered |
| `history` | `HistoricalContext` when the run was recorded |

Structured evidence and normalized lenses. No paths. No raw text beyond the
`raw_line` already normalized into evidence nodes by parsers.

### AgentResult (output, reusable by every future agent)

```
agent_id, domain, applicable, abstained, confidence,
observations[]      statement + evidence_ids + knowledge_ids
hypotheses[]        category + statement + confidence + evidence_ids + knowledge_ids
recommendations[]   action + rationale + priority + evidence_ids
evidence_ids[]      union of everything cited
knowledge_ids[]     union of every knowledge item consulted
limitations[]       what this agent could not determine, and why
narrative           optional, provider-supplied, never load-bearing
provider            which provider produced the narrative, if any
```

Two laws borrowed from existing precedent:

- **Abstention is mandatory without evidence.** An agent that cannot cite an
  evidence node must abstain, exactly as `HypothesisGenerator` must return None
  rather than invent a hypothesis.
- **Limitations are mandatory, not optional.** Mirroring
  `WaveformContext.unavailable`, an agent declares what it could not analyze.
  Honest gaps are a feature; silent gaps are a bug.

Agent hypotheses reuse the existing `HypothesisCategory` enum rather than
inventing a taxonomy, so an agent position is directly comparable to a
deterministic hypothesis. That comparability is what makes the cross-check in
section 7 possible at all.

### Agent (the interface)

```python
class Agent(ABC):
    agent_id: ClassVar[str]
    domain: ClassVar[AgentDomain]

    def applies_to(self, context: AgentContext) -> bool: ...
    def assess(self, context: AgentContext) -> AgentResult: ...
```

Registered with `@register_agent`, matching the six registries already in the
codebase. A new agent is one registered class and nothing else, proven
executably by `test_new_agent_needs_only_registration`.

---

## 6. The Coordinator

```
Evidence Graph
     |
Reasoning Engine            (deterministic, unchanged, still the source of truth)
     |
Agent Coordinator           (invoke -> collect -> merge -> cross-check)
     |
Specialist Agents           (eight built in, any number registered)
     |
Combined Findings           (per category: who supports it, how strongly, and why)
     |
Prioritized Root Causes     (ranked, with agreement and conflict made explicit)
     |
Recommendations             (merged, deduplicated, priority-ordered)
```

Execution is deterministic throughout: agents are invoked in sorted `agent_id`
order, an agent whose `applies_to` returns False is recorded as not applicable
rather than silently skipped, and an agent that raises is isolated (recorded as a
limitation) rather than failing the run, mirroring the orchestrator's failure
isolation.

### Merge semantics

Agent hypotheses are grouped by `HypothesisCategory`. For each category the
Coordinator computes an `AgentFinding` with a fully additive, fully traceable
confidence, deliberately mirroring `rank_hypotheses`:

```
base        = the highest confidence any single agent assigned this category
corroboration = +0.05 for each additional agent independently supporting it
                (capped at +0.15)
contest     = -0.10 once, when another agent's leading position is a
              different category
final       = clamp01(base + corroboration + contest)
```

Read in English: the strongest single position, strengthened by each independent
agent that agrees, discounted when another agent leads elsewhere. Every term is
recorded as an `AgentContribution` with the agent ID and a reason, so a finding's
confidence is auditable line by line, exactly like a `ConfidenceTrace`.

Consensus per finding is one of:

- `agreement`: two or more agents support this category;
- `single_source`: exactly one agent supports it;
- `contested`: supported here, while another agent leads a different category.

### Conflict detection

A conflict is recorded when two agents' *leading* categories differ. Conflicts
are pairwise, named, and explicit: `agent_a` leads `category_a`, `agent_b` leads
`category_b`. Conflicts are surfaced, never resolved by suppression. Two agents
disagreeing is diagnostic information for the engineer, not a defect to hide.

---

## 7. The cross-check

The Coordinator records three fields that make the second-opinion law
observable rather than merely stated:

- `top_category`: the agent layer's leading category, or None;
- `reasoning_top_category`: the deterministic engine's leading hypothesis
  category, read from `ReasoningResult.hypotheses[0]`;
- `agrees_with_reasoning`: whether they match.

Nothing is reordered as a consequence. Disagreement is reported to the engineer,
because a deterministic engine and a panel of domain specialists reaching
different conclusions is precisely the moment a human should look closely.

---

## 8. Deterministic and Generative Intelligence

The separation is one small protocol, and it is the reason future AI
integrations are trivial:

```
Agent.assess(context)  ->  AgentResult                    [always deterministic]
         |
         +-- optional --> ReasoningProvider.elaborate(request) -> ProviderResponse
                                    |
                          +-- NullProvider           (default; returns nothing)
                          +-- DeterministicProvider  (templated from the agent's
                                                      own observations; no I/O)
                          +-- [future] AnthropicProvider / OpenAIProvider /
                                       GeminiProvider / LocalProvider /
                                       McpAiProvider
```

Three rules make this safe:

1. A provider receives a `ProviderRequest` built from the agent's *already
   final* result. It cannot see raw artifacts, and it runs after the conclusion
   exists.
2. A provider may only populate `narrative` and `provider`. The Coordinator
   applies nothing else from a response. A hallucinating provider is
   architecturally incapable of altering a hypothesis, a confidence, an evidence
   citation, or a recommendation.
3. The default is `NullProvider`. The platform is complete and fully useful with
   zero generative intelligence configured.

**M12 ships the protocol and two deterministic implementations, and zero
API-calling providers.** No external LLM call, no vendor SDK, no vendor-specific
model name enters this package. The existing `reasoning/ai.py` is untouched and
keeps working exactly as before; a later milestone may re-express it as an
`AnthropicProvider` behind this seam without changing the Coordinator or any
agent. That is the migration path, and it is deliberately not this milestone's
work.

---

## 9. The eight built-in agents

Every agent maps to data that already exists in the report. None invents a
source, and none parses anything.

| Agent | Domain | Reads | Position it can take |
|---|---|---|---|
| `protocol` | protocol | matched patterns from protocol and interconnect packs, state projection | where in the protocol progress stopped |
| `rtl` | rtl | failing evidence in DUT scopes, project scope resolution, waveform observations | design-side localization |
| `testbench` | testbench | methodology packs, mismatch evidence, log origin testbench or vip | checker versus DUT |
| `coverage` | coverage | coverage nodes flagged as holes plus their correlation edges | under-exercised logic near the failure |
| `regression` | regression | historical context, similar failures, confirmed root causes | new failure versus known precedent |
| `formal` | formal | formal-result evidence nodes, formal pack matches | proof, counterexample, or vacuity |
| `project` | project | lifecycle projection, log origin breakdown | did the run ever reach real design traffic |
| `knowledge` | knowledge | every matched pattern, its playbook and references | consolidated authoritative next steps |

---

## 10. What M12 does not change

- No new `ArtifactType`. No new `RelationType`. The Evidence Graph schema is
  untouched and byte-identical with agents on or off.
- No change to `ReasoningEngine`, `RuleEngine`, `EvidenceSelector`,
  `rank_hypotheses`, the clause matcher, or any Knowledge Pack.
- No existing `WorkspaceServices` method signature or behavior changes. Two
  read-only accessors are added.
- No existing MCP tool changes. Three tools are added through `register_tool`.
- One additive `AnalysisReport.agents` field, and one schema bump, 8 to 9,
  exactly as every milestone since M2 has done.

---

## 11. Laws, each pinned by a test

1. **Second opinion, never a verdict.** The agent layer never mutates the graph
   or the `ReasoningResult`, and analysis with agents enabled produces an
   identical graph and identical deterministic hypotheses to analysis without
   them. (`test_agents_never_mutate_reasoning_or_graph`,
   `test_graph_identical_with_and_without_agents`.)
2. **No raw artifacts.** No module in `agents/` performs file I/O or imports a
   parser, adapter, or provider. (`test_agents_never_read_raw_artifacts`.)
3. **No duplicated extraction.** Every cited evidence ID resolves to a real node
   in the graph. (`test_every_citation_resolves_to_a_real_node`.)
4. **Abstention without evidence.** An agent with nothing to cite abstains and
   contributes no hypothesis. (`test_agent_without_evidence_abstains`.)
5. **Generative intelligence cannot conclude.** A deliberately malicious test
   provider that tries to rewrite hypotheses and confidences changes nothing but
   the narrative. (`test_provider_cannot_alter_conclusions`.)
6. **No vendor AI in the framework.** No module in `agents/` references
   anthropic, openai, or any SDK. (`test_no_vendor_ai_in_agents`.)
7. **Dependencies point outward.** No core package imports `agents/`.
   (`test_core_unchanged_by_agents`.)
8. **Determinism.** The same context produces byte-identical assessments.
   (`test_assessment_is_deterministic`.)
9. **A new agent is one registration.** (`test_new_agent_needs_only_registration`,
   the crown jewel: a throwaway agent defined inside the test reaches the
   coordinator, the merged findings, and the report with zero core changes.)

---

## 12. Why this moves VeriTriage toward an operating system for verification

An operating system does not do the work. It defines the contract that lets
independent programs do work over shared resources, schedules them, arbitrates
their conflicts, and exposes the result through a stable interface.

Before M12 the platform had the shared resources (Evidence Graph, Knowledge
Graph, Project Model, Regression Database) and the stable interface
(`WorkspaceServices`, MCP, bundles) but no process model: every capability had to
be hand-wired into the pipeline as a rule.

M12 supplies the process model. An agent is a process: it declares whether it
applies, runs in isolation, cannot corrupt shared state, cites its sources, and
returns a uniform result. The Coordinator is the scheduler and the arbiter. The
`ReasoningProvider` protocol is the device driver interface: generative
intelligence becomes a swappable peripheral rather than a hard dependency.

The practical consequence is that the next capability, a vendor's AI, a
company-internal domain specialist, a learned model, or an MCP-hosted reasoner,
arrives as one registration against a frozen contract, and everything already
built keeps working unchanged.
