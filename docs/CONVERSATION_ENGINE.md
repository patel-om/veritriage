# Conversation Engine (M16)

Status: design approved, implemented in v1.12.0. This document is the
architectural baseline for the Conversation Engine. It obeys every law in the
platform baseline (Evidence Graph ownership, the AI boundary, deterministic
reasoning, agent isolation, learning purity, planning provenance, design
derivation, registry-shaped extension). Prose here is intentionally free of em
and en dashes per the standing style law.

---

## 1. Vision

Through v1.11.0 VeriTriage produces intelligence and renders it once, into a
static report. An engineer who wants to follow a thought has to leave the
report, call an API, and join results by ID.

M16 makes the intelligence navigable. Not with a chatbot, not with an LLM, and
not by generating prose: with a structured, stateful, composable interaction
layer over artifacts that already exist.

> **Conversation navigates; it never concludes.**

---

## 2. Problem statement

VeriTriage already has a question-answering layer: 51 MCP tools, about forty
`WorkspaceServices` methods, `workspace/navigation.py` for addressing one object
by ID, and `workspace/search.py` for substring matching. Each answers exactly
one question, completely, and then forgets everything.

Four things are missing, and none of them is "a way to ask questions":

1. **Composition.** "Why is this RTL?" then "show only protocol evidence" then
   "why did the protocol agent disagree?" requires restating the full context
   every time.
2. **Navigation state.** There is no current hypothesis, current module, current
   filter, or current design node.
3. **Cross-layer joins.** Evidence to hypothesis to agent to plan step is four
   calls and a manual correlation by ID. The report performs exactly this join,
   renders it to HTML, and discards it.
4. **A uniform answer contract.** Every tool returns a different shape, so a
   client cannot render answers generically.

M16 supplies those four and reimplements no existing query.

---

## 3. The load-bearing law

Stated once, in the style of the M6, M7, M11, M12, M13, M14, and M15 laws:

> **Conversation navigates; it never concludes.** Every answer is assembled
> from artifacts that already exist, every statement carries references that
> resolve to a real artifact, and asking any number of questions leaves the
> report byte-identical. Conversation owns no intelligence.

Four consequences, all test-pinned:

1. **No invented facts.** An answer may only cite evidence node IDs, knowledge
   IDs, design node IDs, agent IDs, learning artifact IDs, plan step IDs,
   hypothesis IDs, and regression IDs that exist in the session.
2. **No mutation.** The session, its report, and its graph are unchanged by any
   number of turns.
3. **No language model.** No vendor SDK, no NLP library, no generated prose.
   Answers are assembled from platform strings.
4. **Deterministic.** The same question against the same session and the same
   navigation context yields a byte-identical answer.

---

## 4. Why not natural language, and what "conversation" means here

The canonical question is a **structured object**:

```python
Question(intent=Intent.WHY, target="hyp-rtl_bug")
```

A deterministic `parse()` maps a **declared, finite vocabulary** of phrasings
onto intents. It is a keyword and pattern matcher, in the same spirit as the
Knowledge Engine's clause matcher: no NLP library, no model, no statistics.
When it cannot parse a question it says so and returns the vocabulary it does
understand, rather than guessing at meaning.

That honesty is what makes the stated future work. A language model later
becomes a **translator that produces `Question` objects and renders `Answer`
objects**, never an owner of either. Swapping GPT, Claude, Gemini, a local
model, a voice front end, or an IDE copilot changes nothing in this package,
because none of them would be answering: they would be phrasing.

What makes this a *conversation* rather than a query API is the other three
properties: turns accumulate, navigation context carries forward, and every
answer suggests the follow-ups it makes available.

---

## 5. Where it belongs

```
models < graph < parsers/rules < reasoning < knowledge/waveform/engineering
                                                     ^
                                                  project < design
                                                     ^
                                            agents < learning < planning
                                                     ^
                                              conversation              (new)
                                                     ^
                                        pipeline < workspace < mcp/cli
```

`conversation/` imports `models`, `graph`, and `design` (for structural
navigation). It **does not import `workspace/`**: the workspace exposes
conversation, not the reverse. Nothing below imports it.

```
src/veritriage/conversation/
  context.py     ConversationContext: the session view a handler may read
  registry.py    @register_handler: one handler per intent, the plugin seam
  handlers/      explain, evidence, compare, navigate, trace, summarize
  parse.py       deterministic phrase -> Question, with a declared vocabulary
  engine.py      ConversationEngine: ask() -> Answer, carries NavigationContext

src/veritriage/models/conversation.py    layer-neutral vocabulary
```

---

## 6. The model

| Artifact | What it is |
|---|---|
| `Intent` | the finite set of things that can be asked |
| `Question` | intent plus an optional target and filter; the canonical form |
| `Reference` | a typed pointer at an existing artifact (kind, id, label) |
| `AnswerSection` | a heading, statements, and the references backing them |
| `Answer` | summary, sections, references, suggested follow-ups, limitations |
| `NavigationContext` | where the user is: hypothesis, module, agent, filter, design node |
| `ConversationTurn` | one question and its answer |
| `ConversationSession` | ordered turns plus the current navigation context |

`ConversationSession` is serializable but **not persisted by the platform**.
Navigation state belongs to the client (an IDE, a Slack thread, a CLI loop). A
sixth SQLite file for "which hypothesis am I looking at" would be storage for
something that is not intelligence.

---

## 7. Intents

Ten, each with a registered handler:

| Intent | Answers |
|---|---|
| `EXPLAIN` | what a finding, hypothesis, agent result, plan step, or design node is |
| `WHY` | why a conclusion holds, from its confidence trace and contributions |
| `WHY_NOT` | why an alternative lost, term by term |
| `SHOW_EVIDENCE` | the evidence behind the current or named subject |
| `FILTER` | narrow the view to one artifact type, severity, module, or agent |
| `COMPARE` | this run against another session or a historical regression |
| `TRACE` | the provenance chain of a recommendation or plan step |
| `NAVIGATE` | move to a module, agent, hypothesis, or design node |
| `SUMMARIZE` | one layer, bounded |
| `HELP` | what can be asked here, given the current context |

Adding an eleventh is one `@register_handler` class, proven by
`test_new_intent_needs_only_registration`.

---

## 8. Multi-layer navigation

The joins the report performs and discards become traversable:

```
evidence node -> the hypotheses citing it -> the agents backing them
              -> the learning artifacts about them
              -> the plan steps addressing them
              -> the design region containing them
              -> the knowledge patterns matching them
```

Every transition is a reference with a kind, so a client can follow it without
knowing which layer produced it. `Answer.followups` names the questions each
answer makes available, which is what allows navigation without parsing prose.

---

## 9. Report and workspace integration

Reports stay exactly as they are: static snapshots, regenerated by nobody.
Conversation **exposes** report objects rather than rebuilding them, so a
`Reference` into a hypothesis and the report's rendering of that hypothesis are
the same object.

`WorkspaceServices` gains conversation methods; MCP gains eight conversational
tools that return structured `Answer` objects rather than prose.

---

## 10. What M16 does not change

- No GPT, no Claude, no Gemini, no local model, no NLP library.
- No generated natural language: answers are assembled from platform strings.
- No change to reasoning, agents, learning, planning, design, or the graphs.
- No new persistent store.
- No report regeneration and no plan execution.
- No schema bump: conversation is a live interaction over a finished report,
  not a new report field.

---

## 11. Laws, each pinned by a test

1. **Navigates, never concludes.** (`test_conversation_never_mutates_the_session`.)
2. **Every citation resolves.** (`test_every_reference_resolves_to_a_real_artifact`.)
3. **No invented facts.** An unknown target yields an honest miss, not a guess.
   (`test_unknown_target_is_an_honest_miss`.)
4. **Deterministic.** (`test_answers_are_deterministic`.)
5. **No language model, no prose generation.** (`test_no_ai_in_conversation`.)
6. **The parser declares its vocabulary.**
   (`test_parser_declares_what_it_cannot_answer`.)
7. **Dependencies point outward.** `conversation/` never imports `workspace/`.
   (`test_conversation_never_imports_the_workspace`.)
8. **No new store.** (`test_conversation_persists_nothing`.)
9. **A new intent is one registration.**
   (`test_new_intent_needs_only_registration`.)

---

## 12. Future compatibility

| Future capability | Lands as |
|---|---|
| GPT, Claude, Gemini, local models | a translator producing `Question` objects and rendering `Answer` objects; the engine is untouched |
| Voice interfaces | the same translator with a different front end |
| VS Code copilot, IDE panels | a client over `ConversationEngine`; `Reference` kinds map to existing navigation getters |
| Slack | a client that serializes `ConversationSession` into a thread |
| Autonomous debugging | a loop that asks `TRACE` and `WHY_NOT` and acts on the references |

The contract they must respect is section 3: assemble from artifacts that
already exist, cite everything, and change nothing.
