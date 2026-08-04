# Design Intelligence (M15)

Status: design approved, implemented in v1.11.0. This document is the
architectural baseline for the Design Intelligence Engine. It obeys every law in
the platform baseline (Evidence Graph ownership, the AI boundary, deterministic
reasoning, agent isolation, learning purity, planning provenance,
registry-shaped extension). Prose here is intentionally free of em and en dashes
per the standing style law.

---

## 1. Vision

Through v1.10.0 VeriTriage understands *evidence*. It knows what happened in a
run, what it means, who agrees about it, what history suggests, and what to do
next. What it does not understand is the *system*: which module instantiates
which, which agent watches which interface, what crosses a clock boundary, what
a configuration object reaches.

M15 makes the platform understand structure. Deterministically, with no AI, no
HDL summarization, and no embeddings.

---

## 2. The finding that shaped this milestone

M11 already built most of the nouns. `ProjectModel` carries modules with
parents, IP blocks with member modules, interfaces with protocols and signals,
clock and reset domains with roots, an address map with target IPs, UVM
components with parents and interfaces, VIPs, a RAL, coverage groups, assertion
groups, sequences, and configuration objects. All frozen, content-addressed,
and cached.

What is missing is not nouns. It is **verbs**. Every relationship in the Project
Model exists as an unresolved string that nothing walks:

| Field | Names something | Resolved by |
|---|---|---|
| `DesignModule.parent` | a parent module | nothing |
| `ClockDomain.roots` | modules in the domain | nothing |
| `UvmComponent.interface` | an interface | nothing |
| `AddressRegion.target_ip` | an IP block | nothing |
| `Vip.protocol_id` | a Knowledge Pack | nothing |

The visible consequence is `resolve_scope()` in `project/inference.py`, which
bridges these by splitting module strings on dots and intersecting sets. That is
string matching standing in for a graph, and it cannot answer a traversal
question because there is nothing to traverse.

---

## 3. The load-bearing law

Stated once, in the style of the M6, M7, M11, M12, M13, and M14 laws:

> **The Design Graph is derived, never extracted.** `design/` performs no source
> reading whatsoever. It normalizes the existing Project Model into a typed,
> queryable graph, resolving every dangling string into a real edge. If a
> structural fact is missing, the fix is a `ProjectProvider`, not a new parser.

This is the M1 to M2 transition repeated. M1's parsers produced flat
`ParseResult`s; M2 introduced the Evidence Graph as the relational layer over
them without re-parsing anything. M15 does the same for project structure.

Three consequences, all test-pinned:

1. **Zero changes to `project/`.** Every fact the graph needs already exists in
   the Project Model. Design Intelligence is not a rival to Project
   Intelligence; it is the graph layer over it.
2. **`design/` reads no source and imports no provider.** Only a
   `ProjectProvider` may touch a source language or build tool, and that law
   stays exactly where M11 put it.
3. **The Design Graph never enters the Evidence Graph.** Evidence is what
   happened in this run; design is what the system is. Linking is by node
   reference, never by merging.

---

## 4. Why a separate graph

Three graphs now exist, and each answers a different question:

| Graph | Question | Lifetime |
|---|---|---|
| Evidence Graph | what happened in this run | one run |
| Knowledge Graph | what is true of this protocol, generally | ships with the packs |
| **Design Graph** | what this system *is* | one project, rebuilt when the model changes |

Merging any pair would destroy a property. Folding design into evidence would
make the Evidence Graph vary with a manifest edit, breaking `FailureSignature`
stability. Folding it into knowledge would make curated, versioned, shared
expertise project-specific. So it is a third graph, deliberately, with the same
shape as the first: content-hashed node IDs, typed edges, every edge carrying a
rationale.

---

## 5. Where it belongs

```
models < graph < parsers/rules < reasoning < knowledge/waveform/engineering
                                                          ^
                                                       project           (owns source ingestion)
                                                          ^
                                                       design            (new: the graph over it)
                                                          ^
                                                    agents < learning < planning
                                                          ^
                                                pipeline < workspace < mcp/cli
```

`design/` imports `models`, `graph` (for evidence cross-referencing), and
`project` (its input). Nothing below imports it.

```
src/veritriage/design/
  model.py       DesignNode, DesignEdge, NodeKind, DesignRelation, DesignGraph
  registry.py    @register_extractor: the plugin seam
  extractors/    one module per structural facet (six ship in M15)
  builder.py     build_design_graph(ProjectModel)
  query.py       DesignQuery: the deterministic structural questions
  inference.py   build_design_view: the report-facing context

src/veritriage/models/design.py    layer-neutral report/API vocabulary
```

---

## 6. The graph

**Node kinds:** `module`, `ip`, `interface`, `clock_domain`, `reset_domain`,
`address_region`, `register_block`, `uvm_component`, `vip`, `sequence`, `test`,
`coverage_group`, `assertion_group`, `config_object`, `protocol`.

**Relations**, each derived from a specific Project Model field so nothing is
guessed:

| Relation | Derived from |
|---|---|
| `instantiates` | `DesignModule.parent` |
| `owns` | `IpBlock.modules`, `UvmComponent.parent` |
| `clocked_by` | `ClockDomain.roots` (plus hierarchy inheritance, marked as inferred) |
| `reset_by` | `ResetDomain.roots` (same) |
| `monitors` | `UvmComponent(type=monitor).interface` |
| `drives` | `UvmComponent(type=driver).interface` |
| `predicts` | `UvmComponent(type=predictor/scoreboard).interface` |
| `implements` | `Interface.protocol_id`, `Vip.protocol_id` |
| `connects` | `Interface` to the IP or module it belongs to |
| `communicates_with` | two modules sharing an interface |
| `depends_on` | `AddressRegion.target_ip` |
| `covers` | `VerificationEnv.coverage` against scopes |
| `asserts` | `VerificationEnv.assertions` against scopes |
| `configured_by` | `Testbench.config_objects` |

Node IDs are content hashes (`dn-<sha1>`), so the same Project Model always
produces the same graph, byte for byte, and a node can be cited from a report,
a plan, or an MCP response without ambiguity.

Every edge carries a `rationale` naming the field it came from, and `inferred`
marking the few edges that follow hierarchy rather than an explicit declaration.
Nothing in this graph is a guess that does not say so.

---

## 7. The query model

Structural questions become deterministic traversals:

| Question | Query |
|---|---|
| Which modules participate in this failure? | `affected_region(scopes)` |
| Which UVM agent owns this interface? | `owner_of(interface)` |
| What clock domains are affected? | `clock_domains_of(scopes)` |
| Which assertions belong to this block? | `assertions_for(module)` |
| Which protocol crosses this boundary? | `protocol_map()` |
| What observes this transaction? | `observers_of(interface)` |
| What depends on this configuration? | `dependents_of(node)` |
| Where do clock domains cross? | `crossings()` |

`affected_region` is the load-bearing one: it takes the failing evidence's
scopes and returns the design neighbourhood around them, which is what makes a
failure locatable in the system rather than only in a log.

---

## 8. Integration

Design nodes are referenced, never copied:

- **Report:** `AnalysisReport.design` carries the affected region, hierarchy,
  clock topology, protocol map, verification topology, and risk hotspots.
- **Agents:** `AgentContext.design` lets a specialist ask a structural question.
  `agents/` does not import `design/`; the graph arrives as plain data, exactly
  as learning hints do.
- **Planning:** steps carry the module they touch, now resolvable to a real node.
- **Learning:** aggregates over node IDs rather than over module strings.
- **MCP and Workspace:** eight tools and six service methods.

---

## 9. What M15 does not change

- No AI. No HDL summarization. No embeddings. No source parsing anywhere in
  `design/`.
- No change to `project/`, the Evidence Graph, the Knowledge Graph, reasoning,
  agents, learning, or planning contracts.
- No new `ArtifactType`, no new `RelationType`.
- One additive `AnalysisReport.design` field, schema 11 to 12.

---

## 10. Laws, each pinned by a test

1. **Derived, never extracted.** No I/O and no provider import in `design/`.
   (`test_design_never_reads_source`.)
2. **Never enters the Evidence Graph.** The graph is identical with and without
   a design model. (`test_design_never_enters_the_evidence_graph`.)
3. **Deterministic.** Same Project Model, byte-identical graph and fingerprint.
   (`test_design_graph_is_deterministic`.)
4. **Every edge is justified.** Every edge names the field it came from, and
   inferred edges say so. (`test_every_edge_carries_a_rationale`.)
5. **No dangling references.** Every edge endpoint resolves to a real node.
   (`test_graph_has_no_dangling_edges`.)
6. **Project Intelligence is untouched.** (`test_project_package_unchanged`.)
7. **Dependencies point outward.** No core package imports `design/`.
   (`test_core_unchanged_by_design`.)
8. **A new extractor is one registration.**
   (`test_new_extractor_needs_only_registration`.)

---

## 11. Future compatibility

Every future capability lands as a consumer of the graph, not a change to it:

| Future capability | Lands as |
|---|---|
| Cross-probing, IDE hierarchy exploration | a client over `DesignQuery`; node IDs are already stable and citable |
| Waveform navigation | scope-to-node resolution, which `affected_region` already performs |
| LLM-assisted explanation | a `ReasoningProvider` (M12 seam) narrating a graph it cannot author |
| Semantic project search | an index over node names; the graph is already normalized |
| Graph embeddings | an `EmbeddingProvider` (M4 seam) over the node/edge set |
| Autonomous debugging | planning steps that already carry resolvable node references |
| Richer structure (ports, FSMs, packages) | a `ProjectProvider` capability plus one extractor |

None requires changing `DesignGraph`, `StructureExtractor`, or the query API.
The law they must respect is section 3: derive from the Project Model, and do
not read source.
