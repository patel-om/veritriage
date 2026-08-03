# Learning Engine (M13)

Status: design approved, implemented in v1.9.0. This document is the
architectural baseline for the Learning Engine. It obeys every law in the
platform baseline (Evidence Graph ownership, the AI boundary, deterministic
reasoning, agent isolation, registry-shaped extension, evidence-backed
conclusions). Prose here is intentionally free of em and en dashes per the
standing style law.

---

## 1. Vision

Through v1.8.0 VeriTriage is a stateless reasoning system with a filing
cabinet. Every completed investigation is stored in full, and almost none of it
is ever read again. M13 makes every completed investigation improve the next
one, without retraining anything and without touching a single deterministic
conclusion path.

The Learning Engine remembers. It does not decide.

---

## 2. Problem statement

One channel carries information between regressions today:

```
analyze() -> HistoryEngine.record() -> SQLite blob -> next run:
   count_signature(digest)   "seen N times"
   find_similar(record)      cosine over sparse features
        -> HistoricalContext + at most ONE appended recommendation
```

The database stores complete reports and complete Evidence Graphs, and exactly
two queries ever run against it. What is stored but never read again:

- **Agent outcomes.** v1.8.0 records what eight specialists concluded, where
  they agreed and conflicted. Nothing asks whether any of them was right.
- **Recommendation outcomes.** `useful_recommendations` and
  `false_recommendations` are written and read by nothing.
- **Wrong diagnoses.** `diagnosis == "incorrect"` is stored and never
  aggregated.
- **Signal utility.** Ranking weights are hardcoded constants that have never
  been validated against outcomes.
- **Project continuity.** The Project Model is cached per root and carries no
  history.
- **Evidence co-occurrence.** No record that a particular combination of
  signals historically meant a particular failure class.
- **Pack utility.** 42 packs and 92 patterns, with no statistics on which fire
  and which mislead.

The gap is a missing layer of persistent adaptive intelligence, not a missing
query.

---

## 3. The load-bearing law

Stated once, in the style of the M6, M7, M11, and M12 laws:

> **Learning is a pure function of recorded history.** Given the same
> `RegressionRecord`s and the same `FeedbackRecord`s, the learning artifacts are
> byte-identical. There is no online drift, no training-order dependence, and no
> hidden state. `veritriage learn` recomputes the entire corpus from the database
> and produces the same artifacts every time.

Three consequences follow, and all three are test-pinned:

1. **Learning never overrides deterministic evidence.** It produces hints and a
   bounded calibration map. It cannot create a hypothesis, alter a
   classification, change the Evidence Graph, or reorder `reasoning.hypotheses`.
2. **Learning is removable.** Deleting `.veritriage/learning.db` returns the
   platform to exact v1.8.0 behavior. The learning store is a separate file from
   the regression database on purpose: the regression database is the immutable
   record of what happened, learning is a derived, rebuildable view over it.
3. **Nothing is opaque.** Every artifact carries its observation count, its
   supporting regression IDs, and a plain-language summary. No vectors, no
   models, no weights that cannot be printed.

---

## 4. Where it belongs

New top-level package `src/veritriage/learning/`, a peer of `knowledge/`,
`agents/`, and `project/`, positioned above all of them:

```
models < graph < parsers/rules < reasoning < knowledge/waveform/engineering/project
                                                          ^
                                                      agents
                                                          ^
                                                     learning              (new)
                                                          ^
                                                pipeline < workspace < mcp/cli
```

`learning/` may import `models`, and reads `RegressionRecord` and
`FeedbackRecord` from the regression layer. It is imported by nothing below it.
Crucially, **`agents/` never imports `learning/`**: hints reach agents as plain
data on `AgentContext`, injected by the pipeline, exactly as knowledge reaches
reasoning through injected rules.

```
src/veritriage/learning/
  model.py         the artifact schemas (versioned, serializable, explainable)
  registry.py      @register_learner: the plugin seam
  learners/        one module per artifact family (seven ship in M13)
  persistence.py   LearningStore (its own SQLite file, rebuildable)
  calibration.py   reliability -> bounded, explainable influence multipliers
  engine.py        LearningEngine: observe() and recall()

src/veritriage/models/learning.py    layer-neutral report/API vocabulary
```

---

## 5. The two-phase lifecycle

Deliberately mirroring the `HistoryEngine.record` / `augment` split proven in
M4:

```
OBSERVE  (after a run completes, beside HistoryEngine.record)
    RegressionRecords + FeedbackRecords
        -> Learners (registry, sorted order)
        -> versioned LearningArtifacts
        -> LearningStore

RECALL   (before agents run, during the next analysis)
    LearningStore -> LearningContext (hints + calibration + profile)
        -> AgentContext.learning        agents gain memory
        -> Coordinator calibration      agent influence adjusts
        -> report.learning              the engineer sees it
```

Observation happens in the workspace layer, never inside `analyze()`, so the
pipeline stays a pure function of its inputs. Recall is supplied to `analyze()`
as an already-loaded `LearningContext`, exactly how M11 supplies the Project
Model.

---

## 6. The artifacts

Seven learner families ship, all sharing a common base carrying
`artifact_id`, `kind`, `schema_version`, `key`, `summary`, `observations`,
`confidence`, `supporting_regressions`, and `updated_at`. Every claim links
back to the investigations that support it.

| Artifact | Key | What it learns |
|---|---|---|
| `InvestigationPattern` | signature digest | recurring failure modes, their confirmed root causes, and the debug actions that worked |
| `EvidencePattern` | co-occurring signal set | which evidence combinations historically imply which failure class |
| `AgentReliability` | agent ID | how often a specialist led, and how often its lead matched the confirmed outcome |
| `ProjectProfile` | project key | dominant failure classes, common modules, protocols, recurring signatures, verification maturity |
| `ProtocolStatistics` | knowledge pack | how often a pack's patterns matched, and how often those matches accompanied a confirmed diagnosis |
| `RecommendationOutcome` | recommendation action | useful versus wasted votes from engineer feedback |
| `HypothesisHistory` | hypothesis category | how often a category led, and how often it was confirmed |

`FailureSignature` is deliberately **not** reimplemented here. It already exists
in `signatures/` and remains the authoritative fingerprint; learning artifacts
key off its digest. Replacing Regression Intelligence is a non-goal; learning
consumes it.

---

## 7. Confidence calibration

Calibration is the one place learning touches ranking, and it is bounded,
explainable, and off by default.

```
accuracy      = times the agent's leading category matched the confirmed outcome
multiplier    = clamp(MIN, 1.0 + (accuracy - NEUTRAL) * SLOPE, MAX)
```

Applied by the **Coordinator at merge time**, never by an agent. That placement
is what preserves agent purity: an agent still computes the same position from
the same evidence, and only its *influence on the merged finding* moves. Every
calibrated adjustment is recorded as an `AgentContribution` naming the agent,
the multiplier, and the observation count behind it, so a calibrated confidence
can be read line by line like every other confidence in the platform.

Three guards: calibration requires a minimum number of observations before it
applies at all; the multiplier is clamped to a narrow band so no amount of
history can silence or enthrone a specialist; and an empty calibration map
produces byte-identical output to v1.8.0.

---

## 8. Agents gain memory, and stay deterministic

An agent receives hints as plain data on its context and may cite them in
observations. It remains a pure function: the same `AgentContext` (including the
same learning hints) always produces the same result. What changes between runs
is the context, not the agent.

Hints never become hypotheses. A hypothesis must still cite Evidence Graph node
IDs from the current run, so history can inform an investigation but can never
manufacture evidence for one.

---

## 9. What M13 does not change

- No LLM, no embeddings, no vector database, no neural model, no hidden state.
- No change to `ReasoningEngine`, `RuleEngine`, `EvidenceSelector`,
  `rank_hypotheses`, the clause matcher, or any Knowledge Pack.
- No change to the Evidence Graph schema, `ArtifactType`, or `RelationType`.
- No agent rewritten. `Agent` and `AgentResult` are untouched.
- Regression Intelligence is untouched and still authoritative for
  "have we seen this exact failure?"
- One additive `AnalysisReport.learning` field, schema 9 to 10.

---

## 10. Laws, each pinned by a test

1. **Learning is a pure function of history.**
   (`test_learning_is_a_pure_function_of_history`.)
2. **Learning never mutates evidence or reasoning.**
   (`test_learning_never_changes_graph_or_reasoning`.)
3. **Learning is removable.** No learning store means exact v1.8.0 behavior.
   (`test_platform_without_learning_matches_previous_behaviour`.)
4. **Hints are never conclusions.** No learning artifact can produce a
   hypothesis. (`test_hints_never_become_hypotheses`.)
5. **Calibration is bounded and explainable.**
   (`test_calibration_is_bounded`, `test_calibration_is_explained_in_the_trace`.)
6. **No opaque intelligence.** No vectors, models, or vendor AI anywhere in
   `learning/`. (`test_no_models_or_embeddings_in_learning`.)
7. **Dependencies point outward.** No core package imports `learning/`, and
   `agents/` in particular does not. (`test_core_unchanged_by_learning`.)
8. **Everything links back.** Every artifact cites the regressions that
   produced it. (`test_every_artifact_links_back_to_investigations`.)
9. **A new learner is one registration.**
   (`test_new_learner_needs_only_registration`.)

---

## 11. Future compatibility

The Learning Engine is now the only component responsible for persistent
adaptive intelligence, which is precisely what makes the next generation of
techniques a plug-in rather than a redesign:

| Future capability | Lands as |
|---|---|
| Learned embeddings | an `EmbeddingProvider` in `similarity/` (the M4 seam), consumed by a learner |
| Semantic retrieval | a `Learner` that emits richer `EvidencePattern`s; the store and contracts are unchanged |
| Graph similarity | a `Learner` reading the stored Evidence Graphs already in every record |
| Reinforcement signals | more `FeedbackRecord` fields feeding `RecommendationOutcome` and `AgentReliability` |
| External AI providers | a `ReasoningProvider` (the M12 seam) that may *narrate* learned patterns, never create them |

None of these require changing `LearningEngine`, `LearningArtifact`, the store,
or the calibration contract. The one law they must respect is the one stated in
section 3: whatever they compute must be a pure, explainable function of
recorded history.
