# Planning Engine (M14)

Status: design approved, implemented in v1.10.0. This document is the
architectural baseline for the Planning Engine. It obeys every law in the
platform baseline (Evidence Graph ownership, the AI boundary, deterministic
reasoning, agent isolation, learning purity, registry-shaped extension,
evidence-backed conclusions). Prose here is intentionally free of em and en
dashes per the standing style law.

---

## 1. Vision

Through v1.9.0 VeriTriage explains failures. It says what is likely true, what
each specialist thinks, and what history suggests. It does not say what to do
about it, except through a static lookup table of at most three strings per
failure category.

M14 makes the platform answer the three questions an engineer actually asks in
front of a failing regression:

- What should I inspect next?
- What evidence would confirm or reject this hypothesis?
- What is the fastest path to root cause?

Reasoning determines what is likely true. Learning contributes historical
experience. Agents contribute specialized perspectives. **Planning determines
what should happen next.** It never changes conclusions; it consumes them.

---

## 2. Problem statement

Recommendations exist today from four independent producers, and every one of
them is a flat, unconditional list:

| Producer | Shape |
|---|---|
| `RecommendationEngine` | at most three hardcoded strings per hypothesis category |
| Knowledge playbooks | ordered steps, curated per pattern |
| `AgentRecommendation` | per-specialist actions, merged by append |
| `HistoryEngine.augment` | exactly one precedent step |

`reasoning/recommend.py` is the honest weak point: a static lookup table whose
`priority` is a loop counter. Five things are structurally missing, and none of
them can be added to a flat list:

1. **Branching.** "If reset deasserts late, inspect CDC synchronization;
   otherwise inspect the scoreboard prediction."
2. **Purpose.** What a step would actually tell you, and which hypotheses it
   discriminates between.
3. **Cost.** What a step is worth against what it takes, so effort goes where
   it pays.
4. **Missing evidence.** What the platform does not have, and why that matters.
5. **Completion.** How an engineer knows the investigation is finished.

---

## 3. The load-bearing law

Stated once, in the style of the M6, M7, M11, M12, and M13 laws:

> **The Planner contributes structure, never content.** Every `DebugStep` is
> derived from an artifact that already exists (a knowledge playbook step, an
> agent recommendation, a reasoning recommendation, a waveform capability gap,
> a formal verdict, or a learning artifact) and carries `derived_from`
> provenance naming it. Planning arranges, orders, branches, and values what
> other layers produced. It never writes new debug advice.

This is the same move M12 made (agents aggregate, never extract) and M13 made
(learning aggregates, never decides). It is what keeps the platform from
growing an unaudited advice generator on top of five rigorously audited layers.

Three consequences, all test-pinned:

1. **Planning never changes conclusions.** The graph, the classification, the
   reasoning hypotheses, the agent assessment, and the learning artifacts are
   byte-identical with planning on or off.
2. **Planning never executes.** No file is opened, no tool is run, no step is
   performed. A `DecisionPoint` whose condition the current evidence already
   settles is resolved deterministically; one that needs a human observation is
   rendered as an open question and left unresolved.
3. **Planning is a pure function of the report.** The same
   `AnalysisReport` always produces a byte-identical `DebugPlan`, including its
   plan ID, which is a content digest.

---

## 4. Naming: why not `InvestigationPlan`

`InvestigationPlan`, `InvestigationStep`, and `PlanStep` are already taken by
the M9 Investigation Orchestrator, exported from `veritriage.models` and
`veritriage.orchestrator`, and embedded in `InvestigationSession.plan` and
therefore inside every `.vtb` bundle.

The conceptual clash matters more than the collision. **M9's plan is what the
platform will run; M14's plan is what the engineer should do.** Machine
workflow versus human debug strategy. The vocabularies stay separate:

| M9 orchestration | M14 planning |
|---|---|
| `InvestigationPlan` | `DebugPlan` |
| `PlanStep` | `DebugStep` |
| `InvestigationStep` (the step ABC) | `StepSource` (the plugin seam) |
| `InvestigationTrace` | `PlanProgress` |

`DebugPlan` also reads naturally beside `knowledge.DebugPlaybook`, and the
relationship is deliberate: a playbook is curated and static, a plan is derived
and per-run, and a plan step may cite the playbook step it came from.

---

## 5. Where it belongs

New top-level package `src/veritriage/planning/`, above learning, below the
pipeline:

```
models < graph < parsers/rules < reasoning < knowledge/waveform/engineering/project
                                                          ^
                                                      agents
                                                          ^
                                                      learning
                                                          ^
                                                      planning              (new)
                                                          ^
                                                pipeline < workspace < mcp/cli
```

`planning/` imports only `models` and `graph`. Nothing below imports it.

```
src/veritriage/planning/
  sources/         StepSource implementations: one per upstream producer
  registry.py      @register_source: the plugin seam
  valuation.py     explainable value/effort arithmetic
  tree.py          decision points, branches, and tree assembly
  progress.py      pure-function progress: which evidence requests are satisfied
  engine.py        Planner: gather -> deduplicate -> value -> order -> branch

src/veritriage/models/planning.py    layer-neutral report/API vocabulary
```

---

## 6. The artifacts

| Artifact | What it is |
|---|---|
| `DebugPlan` | the root: ordered steps, open questions, evidence requests, completion conditions, and a content-digest ID |
| `DebugStep` | one action with purpose, the hypotheses it discriminates, required evidence, expected observations, valuation, provenance, and child branches |
| `DecisionPoint` | a question with typed outcomes, each leading to a branch |
| `PlanBranch` | the steps taken when one outcome holds |
| `EvidenceRequest` | information the platform does not have, why it matters, and which hypothesis it would settle |
| `CompletionCondition` | how an engineer knows the investigation is done |
| `StepValuation` | value, effort, and the printed arithmetic that produced the priority |
| `PlanProgress` | which evidence requests the current graph already satisfies |

Every artifact is versioned, serializable, and carries `evidence_ids` or
`derived_from`, so every element of a plan links back to something auditable.

---

## 7. Valuation and optimization

Effort goes where it pays, using integers and a recorded formula rather than
opaque scores:

```
value  = discrimination (how many competing hypotheses the step separates)
       + confidence of the hypothesis it serves
       + historical success (learning, bounded)
effort = 1 low, 2 medium, 3 high      (from the source artifact, never invented)
priority_score = round(value / effort, 4)
```

Steps sort by descending `priority_score`, ties broken by ascending effort then
step ID, so ordering is total and deterministic. `StepValuation` records every
term with a reason, so a step's position in the plan can be read line by line
exactly like a `ConfidenceTrace`.

High confidence and low cost sort earlier. Low confidence and high effort sort
later. That is the whole optimization, and it is auditable.

---

## 8. Decision trees

A `DecisionPoint` has two condition kinds, which is what lets planning branch
without executing anything:

- **`when` (auto):** a predicate over evidence already in the graph. If this
  run's evidence already settles the question, the Planner resolves the branch
  deterministically and marks it `resolved`.
- **`ask` (human):** a question only an engineer can answer by looking. The
  Planner renders it as an open question and leaves both branches in the tree.

Planning never runs a tool, opens a file, or performs a step. Interactive
planning, live debugging, and CI investigation are later increments that supply
observations back into `ask` conditions; the tree structure does not change.

---

## 9. Learning and project integration

**Learning contributes priorities, never steps.** A historically successful
debug action raises the value term of a step that already exists; a known dead
end lowers it. Both adjustments are bounded and recorded in the valuation, and
an absent learning store changes nothing. This exactly mirrors M13 calibration,
which adjusts agent influence without changing what an agent concluded.

**Project Intelligence shapes strategy.** The identified protocols and DUT
topology decide which knowledge playbooks are in scope and how scopes resolve,
so a NoC project, a CPU core, and a cache subsystem naturally produce different
plans from the same generic machinery. The Planner reads `report.project`; it
never builds a model.

---

## 10. What M14 does not change

- No LLM. No autonomous execution. No tool invocation.
- No change to `ReasoningEngine`, `RecommendationEngine`, `RuleEngine`, the
  matcher, or any Knowledge Pack. `reasoning.recommendations` stays exactly as
  it is: planning augments it and never replaces it.
- No change to any learning artifact, to the `Agent` ABC, or to any agent.
- No change to the Evidence Graph schema, `ArtifactType`, or `RelationType`.
- No change to M9 orchestration vocabulary.
- One additive `AnalysisReport.plan` field, schema 10 to 11.

---

## 11. Laws, each pinned by a test

1. **Structure, never content.** Every step names the artifact it came from.
   (`test_every_step_is_derived_from_an_existing_artifact`.)
2. **Planning never changes conclusions.**
   (`test_planning_never_changes_upstream_conclusions`.)
3. **Planning never executes.** No I/O anywhere in the package.
   (`test_planning_never_executes_anything`.)
4. **Plans are deterministic**, including the plan ID digest.
   (`test_plan_is_deterministic`.)
5. **Ordering is total and explainable.**
   (`test_steps_are_ordered_by_value_over_effort`,
   `test_valuation_arithmetic_is_recorded`.)
6. **Learning contributes priorities, never steps.**
   (`test_learning_reprioritizes_but_never_adds_steps`.)
7. **Every citation resolves** to a real graph node.
   (`test_every_plan_citation_resolves`.)
8. **Dependencies point outward.** No core package imports `planning/`.
   (`test_core_unchanged_by_planning`.)
9. **A new step source is one registration.**
   (`test_new_step_source_needs_only_registration`.)

---

## 12. Future extensibility

Planning becomes the single orchestration layer for future autonomous
capabilities, and each one lands behind an existing seam:

| Future capability | Lands as |
|---|---|
| Interactive planning | observations supplied back into `ask` conditions; tree structure unchanged |
| Live debugging | a client that resolves `DecisionPoint`s as the engineer works |
| VS Code workflows | a renderer over `DebugPlan`; `WorkspaceServices` already exposes it |
| CI investigation | `plan_progress()` gating a pipeline; already a pure function |
| LLM planning assistants | a `ReasoningProvider` (the M12 seam) narrating a plan it cannot author |
| Tool execution | a new layer above planning that consumes `DebugStep`; planning stays advisory |

None requires changing `Planner`, `DebugPlan`, `StepSource`, or the valuation
contract. The law they must respect is section 3: whatever they add must derive
from an artifact that already exists, and must not execute.
