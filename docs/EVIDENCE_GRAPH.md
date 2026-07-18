# The Evidence Graph

The Evidence Graph is the central architecture of TraceIQ v2 and the single
source of truth for everything downstream of parsing. This document describes
what it is, the invariants it enforces, and why the design improves
scalability, explainability, and deterministic reasoning.

## The core idea

Every verification artifact is reduced to one normalized vocabulary:

```
Artifact files                 Evidence Graph                    Consumers
--------------                 ---------------------             ------------------
simulation.log  --parse-->     EvidenceNode                      Rule engine
compile.log     --parse-->       id (content hash)               HTML / JSON report
coverage.txt    --parse-->       artifact_type                   AI reasoning layer
test_metadata   --parse-->       timestamp (sim_time)            Future: waveform jump,
(waveform: reserved)             source (path + line)            spec retrieval,
                                 module / scope                  git correlation
                                 severity, confidence
                                 attributes
                               EvidenceEdge
                                 relation (typed)
                                 rationale, confidence
```

* **Nodes** are individual verifiable observations: an error message, a fired
  assertion, a coverage hole, a test-run descriptor.
* **Edges** are typed, justified relationships: `precedes` (temporal order),
  `causes` (assertion before a fatal), `correlates_with` (coverage hole in a
  failing scope), `part_of` (failure belongs to a test run), `supports`.
* **IDs are content-derived** (SHA-1 of artifact type, path, location, and
  message), so the same inputs always produce the same graph and node IDs are
  stable references across re-runs.

The flow is strict and one-directional:

```
parse (deterministic) -> emit evidence -> build + correlate graph
     -> classify (rules over graph) -> report -> optional AI narration (graph only)
```

## The AI boundary

**The AI layer never reads raw files.** Its entire input is
`EvidenceGraph.to_reasoning_view()`: a bounded, normalized projection
containing node IDs, descriptions, severities, times, scopes, and typed edges.
Raw log text, file paths opened for reading, and unparsed content are
structurally absent from that payload.

This is enforced three ways:

1. **By construction**: `AISummarizer.summarize(report, graph)` takes models,
   not paths, and builds its prompt payload only from the reasoning view plus
   the deterministic classification.
2. **By test**: `tests/test_ai_boundary.py` pins the signature and asserts the
   summarizer module contains no file-reading calls; `tests/test_graph.py`
   asserts the reasoning view leaks no raw artifact lines.
3. **By prompt contract**: the model is instructed to cite node IDs for every
   claim, so its output is auditable against the graph.

Because the reasoning view is artifact-agnostic (it only speaks node/edge
vocabulary), **adding a new artifact type never changes the AI layer**. A
future waveform-metadata parser emits `waveform_metadata` nodes; the AI simply
sees more nodes of a new type.

## Why this architecture

### Scalability

Adding an artifact type touches exactly two places, both additive:

1. a new `Parser` subclass that emits a `GraphFragment` (registered with a
   decorator; no existing file changes), and
2. optionally, a correlation pass in `graph/builder.py` linking the new nodes
   to existing ones.

The rule engine, the report, the CLI, and the AI layer are untouched: they
already speak nodes and edges. v2 proved this shape by adding compile logs,
coverage, and test metadata without modifying the classification rules'
interfaces or the AI layer. The same holds for waveform metadata, spec
references, and git history later. Cross-artifact insight also composes for
free: once coverage nodes and failure nodes coexist, one correlation pass
links them for every current and future consumer at once.

### Explainability

Every conclusion is a walk through the graph:

* a classification's evidence items carry `node_id` references;
* each node points to an exact artifact file and line;
* each edge carries a human-readable `rationale`;
* the AI summary cites node IDs inline.

"Why does TraceIQ think this is a testbench failure?" is answerable
mechanically: follow the evidence node IDs to log lines, and the edges to the
events before and around them. There is no conclusion whose provenance ends in
"the model said so"; provenance always ends at an artifact location.

### Deterministic reasoning

* Parsers are pure line-format matchers; no heuristic ordering.
* Node IDs are content hashes; insertion order is parse order; every graph
  query preserves it. Same artifacts in, byte-identical graph out (pinned by
  `tests/test_graph.py::test_node_ids_are_deterministic`).
* Rules are pure functions of the graph, ranked by fixed confidences with a
  stable sort.
* The only nondeterministic component, the optional AI narration, sits
  strictly downstream, cannot alter the graph or the classification, and is
  constrained to the deterministic evidence as input.

The result: two engineers running TraceIQ on the same regression artifacts get
the same graph, the same classification, and the same evidence, every time.
The AI adds prose, never facts.

## Adding a new artifact type (checklist)

1. Add a value to `ArtifactType` (or use the reserved `waveform_metadata`).
2. Write a `Parser` subclass: `name`, `artifact_type`, `file_patterns`,
   `parse()`, and (for non-message artifacts) `emit_evidence()`.
3. Register it with `@register` and import it from `parsers/__init__.py`.
4. If cross-artifact links make sense, add one correlation pass in
   `graph/builder.py` with a rationale on every edge.
5. Add a fixture and tests: extraction, emission, correlation.

Nothing else changes: not the rule engine, not the report, not the AI layer.
That is the property the Evidence Graph exists to guarantee.
