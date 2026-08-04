# AI Providers (M17)

Status: design approved, implemented in v1.13.0. This document is the
architectural baseline for generative AI in VeriTriage. It obeys every law in
the platform baseline. Prose here is intentionally free of em and en dashes per
the standing style law.

---

## 1. Vision

VeriTriage produces deterministic intelligence and communicates it in tables.
M17 lets it communicate in prose, without letting prose become the source of
truth.

> **Providers render, never reason.**

A provider receives a frozen `Prompt` and returns text. It cannot see a raw
artifact, cannot reach platform state, cannot create a citation, and cannot
change a conclusion. Remove every provider and the platform loses prose and
nothing else.

---

## 2. The simplification: one provider registry, not two

M12 already shipped `agents.ReasoningProvider` with `NullProvider`,
`DeterministicProvider`, a registry, and a documented promise that a future
`AnthropicProvider` is one class plus one registration.

That seam genuinely cannot carry M17, because it is **agent-shaped**: its
request is `agent_id`, `domain`, `observations`, `hypotheses`. There is no way
to ask it for a project digest or a design walkthrough.

But building a parallel, unrelated registry would mean two registries, two
`NullProvider` semantics, two configuration paths, and two places to register a
vendor. So:

```
                    ai.LLMProvider              one vendor registry
                      ^          ^
                      |          |
   agents.ReasoningProvider    ai.renderers
   (M12, frozen, via adapter)  (summary, explanation, conversation)
```

`ai/` owns one `LLMProvider`, shaped like a **vendor** (a prompt goes in, text
comes out) rather than like a use case. The M12 `ReasoningProvider` stays frozen
and untouched and gains an adapter (`LlmReasoningProvider`) that satisfies its
interface by delegating to an `LLMProvider`.

The consequence is the point: **registering Anthropic once gives both agent
narration and every renderer.** No frozen contract moves.

---

## 3. The laws

1. **Providers render, never reason.** Generation cannot create, alter, or veto
   a conclusion. Every structured object survives generation unchanged.
2. **Structured artifacts only.** A provider's entire input is a `Prompt` built
   from cited platform objects. No raw file, log, waveform, or RTL ever reaches
   one, and `ai/` performs no file I/O at all.
3. **Grounded or stripped.** The `Prompt` declares its citation set. The
   response is scanned, and any citation outside that set is removed with the
   omission recorded. Deterministic: no model is needed to check a model.
4. **Read-only.** A provider is handed frozen data and returns a string. It has
   no handle on any store, service, graph, or report.
5. **Graceful degradation.** A provider that fails, hangs, or returns nonsense
   costs prose and nothing else. Conversation, planning, reasoning, and reports
   all continue.
6. **Deterministic until generation begins.** Prompt construction is a pure
   function of the structured input and is fully inspectable before any provider
   sees it.

---

## 4. Where it belongs

```
models < graph < ... < agents < learning < planning < design
                                    ^
                              conversation
                                    ^
                                   ai                     (new)
                                    ^
                        pipeline < workspace < mcp/cli
```

`ai/` imports `models` and `conversation` (to render `Answer` objects). Nothing
below imports `ai/`, and in particular `conversation/` stays AI-free, which its
own guard test already pins.

```
src/veritriage/ai/
  provider.py     LLMProvider Protocol, ProviderCapabilities, GenerationRequest/Response
  registry.py     @register_llm_provider, get_llm_provider, available_llm_providers
  providers/      null, echo, mock, reference
  prompt.py       PromptContext, PromptTemplate, PromptBuilder, Prompt (inspectable)
  grounding.py    citation extraction and enforcement
  renderers/      summary, explanation, conversation
  adapters.py     LlmReasoningProvider: the M12 bridge
  service.py      AIService: selection, capability discovery, health, degradation

src/veritriage/models/ai.py    layer-neutral vocabulary
```

---

## 5. The prompt is an object, not a string

Prompt construction never concatenates free text. A `PromptBuilder` consumes
structured objects and produces a frozen `Prompt` carrying:

- `system`: the role and the hard rules, from a versioned `PromptTemplate`
- `sections`: typed `PromptSection`s, each built from platform objects
- `citations`: the complete set of artifact IDs the response may reference
- `template_id` and `template_version`: what produced it

Every prompt is inspectable before generation (`preview_prompt`), so what a
provider will be asked is auditable without asking it.

---

## 6. Built-in providers

Four ship, and none calls an external API:

| Provider | Purpose |
|---|---|
| `null` | the default. Generates nothing. The platform is complete without prose. |
| `deterministic-echo` | assembles prose from the prompt's own sections. Byte-identical for byte-identical prompts, so tests can pin rendering end to end. |
| `mock` | scripted responses, including deliberately bad ones, so grounding enforcement can be tested against a hostile provider. |
| `reference` | the reference implementation a vendor integration should read: correct citation behavior, capability declaration, and failure signalling. |

A real vendor (`OpenAI`, `Anthropic`, `Google`, a local model, an MCP-hosted
provider, an enterprise gateway) is one class implementing `generate` plus one
`register_llm_provider` call.

---

## 7. Grounding

The mechanism, stated once:

```
PromptBuilder collects citations from the structured objects it was given
    -> Prompt.citations is the allowed set
    -> provider generates text
    -> grounding.enforce() scans the text for citation tokens
    -> tokens outside the allowed set are stripped, and recorded
    -> the structured object is returned regardless
```

`GeneratedView` therefore always carries both the prose and the structured
object it restates, plus `grounded` and `stripped_citations`. A client that
does not trust generation can render the structured object and ignore the
prose entirely; nothing is lost.

---

## 8. What M17 does not change

- No external API call ships. No vendor SDK is imported anywhere in `ai/`.
- No change to reasoning, agents, learning, planning, design, conversation, the
  graphs, or any report field. No schema bump.
- No provider can mutate platform state: none is given a handle to any.
- `agents.ReasoningProvider` is untouched and still frozen.

**A note on `reasoning/ai.py`.** The M3 `AIReasoner` hardcodes `import
anthropic` and a model name, and is the only vendor reference in the
repository. Your non-goal forbids changing reasoning, so it stays exactly as it
is and keeps working via `veritriage analyze --ai`. It is now the **legacy**
path: it predates every seam in this document, it cannot be swapped for another
vendor, and its job is done better by `ai/`. Stating that here rather than
leaving it as a trap for the next contributor.

---

## 9. Laws, each pinned by a test

1. **Render, never reason.** (`test_generation_never_changes_conclusions`.)
2. **Structured artifacts only; no file I/O.** (`test_ai_never_reads_raw_artifacts`.)
3. **Grounded or stripped.** A hostile provider inventing citations has them
   removed. (`test_invented_citations_are_stripped`.)
4. **Read-only.** (`test_providers_receive_no_platform_handles`.)
5. **Graceful degradation.** (`test_a_failing_provider_costs_only_prose`.)
6. **Prompts are pure and inspectable.**
   (`test_prompt_building_is_deterministic`, `test_prompts_are_inspectable`.)
7. **No vendor SDK ships.** (`test_no_vendor_sdk_in_ai`.)
8. **The M12 seam is reused, not duplicated.**
   (`test_reasoning_provider_bridges_to_one_registry`.)
9. **Dependencies point outward.** (`test_core_unchanged_by_ai`.)
10. **A new vendor is one registration.**
    (`test_new_provider_needs_only_registration`.)

---

## 10. Future compatibility

| Vendor | Lands as |
|---|---|
| OpenAI, Anthropic, Google | one `LLMProvider` class plus one registration |
| Local models (llama.cpp, Ollama, vLLM) | the same, with `ProviderCapabilities.local = True` |
| MCP-hosted providers | the same, delegating `generate` over MCP |
| Enterprise gateways | the same, plus configuration on the provider itself |

None requires changing `Conversation`, `Planning`, `Agent`, `LLMProvider`,
`PromptBuilder`, or the grounding contract. The rule they must respect is
section 3: render what you were given, cite only what you were handed, and
change nothing.
