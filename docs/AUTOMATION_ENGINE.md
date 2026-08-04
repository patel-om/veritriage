# Automation Engine (M18)

Status: design approved, implemented in v1.14.0. This document is the
architectural baseline for event-driven automation. It obeys every law in the
platform baseline. Prose here is intentionally free of em and en dashes per the
standing style law.

---

## 1. Vision

Through v1.13.0 VeriTriage is a pure function invoked by a human. Every capability
is real and every one waits to be asked.

M18 lets the platform react. Not continuously, not autonomously debugging, and
not by running anything: by observing changes it already detects and deciding
what should follow.

> **Automation observes and decides; it never concludes and never executes.**

---

## 2. Problem statement

Every event worth reacting to already happens, is already computed
deterministically, and is then discarded:

| Moment | Already computed as | Fate today |
|---|---|---|
| An analysis completed | `analyze()` returning | returned, forgotten |
| A signature recurred | `HistoricalContext.seen_before` / `times_seen` | one report line |
| Specialists disagreed | `AgentAssessment.conflicts` | one report section |
| Learning changed | `LearningEngine.observe()` replacing artifacts | silent |
| A provider failed | `GenerationResponse.failed` | one limitation |
| A design region was touched | `DesignContext.affected_region` | one report section |

Nothing is published, nothing subscribes, and nothing follows. The information
is there; the reaction is missing.

---

## 3. The load-bearing decision: decide, never execute

Two facts forced the shape of this milestone.

**First, M9 already has an execution engine.** The proposed action list maps
almost one to one onto the orchestrator's ten registered steps
(`analyze-artifacts`, `render-report`, `summarize`, and the rest), and M9
already ships DAG scheduling, retries, failure isolation, and an execution
trace. A second action registry would sit beside a proven one.

**Second, the layering forbids it anyway.** `orchestrator/` imports
`workspace/`. An `automation/` that executed actions would sit above the
orchestrator, and the workspace could then not consume it without a cycle.

So:

> `automation/` imports **only `models`**. It publishes events, evaluates
> triggers, fires rules, and emits `ActionRequest` objects naming capabilities
> the platform already has. The **workspace** executes them, through methods it
> already exposes.

Three consequences, all improvements:

1. **No third registry.** The action vocabulary is a closed `ActionKind` enum
   dispatched by the workspace to its own existing methods. "Actions never
   execute arbitrary code" is structurally true: there is no code path to
   arbitrary code.
2. **The non-goals hold by construction.** No simulations, no CI, no webhooks,
   no OS jobs, because `automation/` performs no I/O at all, exactly like
   `planning/` and `conversation/`.
3. **Nothing is inverted.** `automation/` sits beside `planning/`, importing
   only `models`.

---

## 4. Where it belongs

```
models < graph < ... < agents < learning < planning < design < conversation
                                    ^
                               automation                       (new, imports models only)
                                    ^
                        pipeline < workspace < orchestrator/mcp/cli
```

```
src/veritriage/automation/
  bus.py        EventBus: publish, subscribe, replay, filter. Ordered, synchronous.
  triggers.py   @register_trigger + the built-in conditions
  rules.py      AutomationRule evaluation and the rule engine
  registry.py   the trigger and rule tables
  builtin.py    the shipped rules

src/veritriage/models/automation.py    layer-neutral vocabulary
```

---

## 5. Events

Every event is **immutable, versioned, content-addressed, and ordered**. Frozen
models, a deterministic `event_id` derived from kind plus payload plus sequence,
and a monotonic sequence number assigned by the bus.

Immutability is what makes the other three properties possible. Replay is only
meaningful if the log cannot have changed since it was written; ordering is only
meaningful if a sequence number cannot be reassigned; and an audit trail that
can be edited is not an audit trail. An event is a record that something
happened, and what happened does not change.

Twelve kinds ship: `analysis_completed`, `regression_detected`,
`learning_updated`, `design_changed`, `project_updated`, `plan_generated`,
`conversation_started`, `provider_failure`, `workspace_opened`,
`knowledge_updated`, `evidence_imported`, `project_indexed`, plus
`schedule_tick`.

---

## 6. The bus

Deterministic by construction:

- **Synchronous.** `publish()` runs subscribers inline and returns. No threads,
  no async, no queues, no hidden callbacks.
- **Ordered.** Events carry a monotonic sequence; subscribers run in
  registration order.
- **Replayable.** `replay()` re-runs the recorded log through the current
  subscribers and produces identical decisions, because rule evaluation is a
  pure function of the event and the payload it carries.
- **Filterable.** `events(kind=..., since=...)` over the recorded log.
- **Bounded.** The log has a cap, so a long-lived workspace cannot grow without
  limit. Dropping is from the oldest end and is reported.

A subscriber that raises is isolated and recorded, never allowed to end a
publish.

---

## 7. Triggers and rules

A `Trigger` is a declarative condition over an event and its payload. No
scripting language and no embedded code: a trigger is a registered class with
one `matches()` method, and a rule references it by ID.

```
AutomationRule(
    rule_id="recurring-regression",
    when="regression.recurring",         # a registered trigger
    then=[ActionKind.GENERATE_PLAN, ActionKind.REFRESH_LEARNING],
    ...
)
```

Evaluation produces a `RuleOutcome`: which rule fired, on which event, which
actions it requested, and why. Nothing is executed at this point, which is what
keeps rule evaluation a pure function.

---

## 8. Actions

A closed enum, each member naming a capability the workspace already has:

| ActionKind | Workspace method |
|---|---|
| `run_analysis` | `investigate` |
| `generate_report` | `render_report` |
| `generate_plan` | `build_investigation_plan` |
| `refresh_learning` | `learn_from_history` |
| `summarize_changes` | `summary` |
| `rebuild_design_graph` | `design_graph` |
| `export_bundle` | `export_bundle` |
| `notify` | recorded for a client to deliver |

An `ActionRequest` is a request, not a call. The workspace dispatches it; every
outcome (including refusal and failure) is recorded in the `ActionResult`.

---

## 9. On scheduling

Your requirements list scheduling while the non-goals forbid OS jobs. The
honest resolution: automation models a `schedule_tick` event that a caller
supplies (a CI job, a cron entry someone else owns, a future daemon). Automation
answers "what is due given this clock" and never sleeps, spawns, or polls.
Pretending to schedule without a daemon would be dead code.

---

## 10. What M18 does not change

- No simulation, no CI invocation, no webhook, no OS job, no network call, and
  no file I/O anywhere in `automation/`.
- No change to reasoning, agents, learning, planning, design, conversation, the
  graphs, or the M9 orchestrator.
- One additive `AnalysisReport.automation` field, schema 12 to 13, populated by
  the workspace after `analyze()` returns, exactly as historical context is.

---

## 11. Laws, each pinned by a test

1. **Decide, never execute.** No I/O and no execution in `automation/`.
   (`test_automation_never_executes_anything`.)
2. **Events are immutable.** (`test_events_are_immutable`.)
3. **Ordered and content-addressed.** (`test_event_ids_are_content_derived`,
   `test_sequence_is_monotonic`.)
4. **Replay is faithful.** (`test_replay_reproduces_the_same_decisions`.)
5. **Rule evaluation is pure.** (`test_rule_evaluation_is_deterministic`.)
6. **Automation never changes conclusions.**
   (`test_automation_never_changes_the_report`.)
7. **The action vocabulary is closed.** (`test_actions_are_a_closed_vocabulary`.)
8. **A broken subscriber is isolated.**
   (`test_a_broken_subscriber_never_breaks_publish`.)
9. **Dependencies point outward.** (`test_core_unchanged_by_automation`.)
10. **A new trigger or rule is one registration.**
    (`test_new_trigger_needs_only_registration`.)

---

## 12. Future compatibility

Every integration lands as a **producer of events** or a **consumer of action
requests**, never as a change to automation:

| Future capability | Lands as |
|---|---|
| GitHub Actions, Jenkins, GitLab | a CI job publishing `analysis_completed` and executing returned requests |
| Slack, VS Code | subscribers rendering events and `notify` requests |
| Enterprise schedulers | a caller publishing `schedule_tick` |
| Cloud execution | a dispatcher executing `ActionRequest`s remotely |

None requires changing `EventBus`, `Trigger`, `AutomationRule`, or `ActionKind`.
The rule they must respect is section 3: automation decides, and someone else
executes.
