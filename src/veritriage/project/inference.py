"""How the Project Model reaches reasoning and the report.

Two additive integration surfaces, both mirroring the Knowledge Engine bridge so
the reasoning engine has no project dependency:

1. **Reasoning signals.** ``project_reasoning_rules(model)`` returns standard
   :class:`ReasoningRule`s. They interpret *existing* evidence nodes through the
   project model (origin of the message, place in the expected lifecycle, the IP a
   scope resolves to) and cite those node IDs. Like every rule they only shift
   ranking; the project model never concludes and never enters the Evidence Graph.

2. **Report context.** ``build_project_view(model, graph, report)`` produces the
   :class:`ProjectContext` embedded in the report: topology, identified protocols,
   the lifecycle projection, and the origin breakdown of the failing evidence.

Deterministic and AI-free.
"""

from __future__ import annotations

from veritriage.graph.graph import EvidenceGraph
from veritriage.graph.model import EvidenceNode
from veritriage.models import (
    AnalysisReport,
    DutModuleView,
    DutTopologyView,
    HypothesisCategory,
    IdentifiedProtocol,
    InterfaceView,
    ProjectContext,
    ReasoningSignal,
    ResolvedScope,
    UvmComponentView,
    UvmTopologyView,
    WorkingSet,
)
from veritriage.project.lifecycle import project_lifecycle
from veritriage.project.logmap import classify_origin
from veritriage.project.model import ProjectModel
from veritriage.reasoning.signals import ReasoningRule

#: Origins that implicate something other than the DUT.
_NON_DUT_ORIGINS = {
    "vip": HypothesisCategory.TESTBENCH_ISSUE,
    "testbench": HypothesisCategory.TESTBENCH_ISSUE,
    "infrastructure": HypothesisCategory.INFRASTRUCTURE_ISSUE,
    "simulator": HypothesisCategory.INFRASTRUCTURE_ISSUE,
}

#: Lifecycle phase names that mean real design traffic was exercised.
_TRAFFIC_PHASES = {"traffic", "stimulus", "sequence", "check", "checking", "report"}


def resolve_scope(model: ProjectModel, module: str | None) -> ResolvedScope:
    """Upgrade a bare module string into a structural scope via the model."""
    resolved = ResolvedScope(module=module or "")
    if not module:
        return resolved
    lowered = module.lower()
    segments = [s for s in lowered.replace("/", ".").split(".") if s]

    ip = next(
        (
            b
            for b in model.dut.ip_blocks
            if b.name.lower() in segments
            or any(m.lower() in segments for m in b.modules)
        ),
        None,
    )
    component = next(
        (c for c in model.env.components if c.name.lower() in segments), None
    )
    interface_name = component.interface if component else None
    interface = next(
        (i for i in model.dut.interfaces if i.name == interface_name), None
    )
    owner = None
    if ip is not None:
        owner = ip.owner
    else:
        owner = next(
            (o.owner for o in model.engineering.owners if o.scope.lower() in segments),
            None,
        )
    return ResolvedScope(
        module=module,
        ip=ip.name if ip else None,
        interface=interface.name if interface else None,
        protocol_id=interface.protocol_id if interface else None,
        clock_domain=None,
        owner=owner,
    )


class ProjectLogOriginRule(ReasoningRule):
    """Failing evidence originating outside the DUT shifts blame off the design.

    If the failing messages come from the VIP, the testbench, infrastructure, or
    the simulator (per the project's log profile), raise the corresponding
    hypothesis and lower RTL_BUG. This is the concrete payoff of log intelligence.
    """

    name = "project:log-origin"

    def __init__(self, model: ProjectModel) -> None:
        self._model = model

    def evaluate(self, graph: EvidenceGraph, working_set: WorkingSet) -> ReasoningSignal | None:
        nodes = [n for n in self._nodes(graph, working_set) if n.is_failing]
        if not nodes:
            return None
        implicated: dict[HypothesisCategory, list[str]] = {}
        for node in nodes:
            text = f"{node.description} {node.raw_line or ''}"
            origin = classify_origin(text, node.module, self._model.log_profile)
            category = _NON_DUT_ORIGINS.get(origin)
            if category is not None:
                implicated.setdefault(category, []).append(node.id)
        if not implicated:
            return None
        evidence_ids = sorted({i for ids in implicated.values() for i in ids})
        weights: dict[HypothesisCategory, float] = {HypothesisCategory.RTL_BUG: -0.12}
        for category in implicated:
            weights[category] = 0.22
        origins = sorted({o.value for o in implicated})
        return ReasoningSignal(
            name=self.name,
            description=(
                "The failing messages originate outside the DUT "
                f"({', '.join(origins)}, per the project's log profile), which points "
                "away from a design bug and toward the checking environment or "
                "infrastructure."
            ),
            evidence_ids=evidence_ids,
            weights=weights,
            confidence=0.8,
        )


class ProjectLifecycleRule(ReasoningRule):
    """A run that stopped before traffic never exercised the design.

    When the lifecycle projection shows no traffic/checking phase was reached,
    raise BUILD_ISSUE and TESTBENCH_ISSUE and lower RTL_BUG: nothing in the DUT
    ran yet, so a design bug is not the leading explanation.
    """

    name = "project:lifecycle"

    def __init__(self, model: ProjectModel) -> None:
        self._model = model

    def evaluate(self, graph: EvidenceGraph, working_set: WorkingSet) -> ReasoningSignal | None:
        projection = project_lifecycle(self._model, graph)
        if projection is None or not any(p.reached for p in projection.phases):
            return None
        reached_traffic = any(
            p.reached and p.state.lower() in _TRAFFIC_PHASES for p in projection.phases
        )
        if reached_traffic:
            return None
        reached = [p for p in projection.phases if p.reached]
        evidence_ids = sorted({i for p in reached for i in p.evidence_ids})
        if not evidence_ids:
            return None
        return ReasoningSignal(
            name=self.name,
            description=(
                f"The run reached '{projection.last_reached}' and stopped at "
                f"'{projection.stopped_at}' in the expected simulation lifecycle, before "
                "any design traffic: the failure precedes real DUT activity, favoring a "
                "build or testbench-setup cause over an RTL bug."
            ),
            evidence_ids=evidence_ids,
            weights={
                HypothesisCategory.BUILD_ISSUE: 0.18,
                HypothesisCategory.TESTBENCH_ISSUE: 0.15,
                HypothesisCategory.RTL_BUG: -0.15,
            },
            confidence=0.75,
        )


class ProjectScopeRule(ReasoningRule):
    """A failing scope that resolves to a specific DUT IP sharpens the RTL story."""

    name = "project:scope-ownership"

    def __init__(self, model: ProjectModel) -> None:
        self._model = model

    def evaluate(self, graph: EvidenceGraph, working_set: WorkingSet) -> ReasoningSignal | None:
        located: list[EvidenceNode] = []
        ips: set[str] = set()
        for node in self._nodes(graph, working_set):
            if not node.is_failing:
                continue
            scope = resolve_scope(self._model, node.module)
            if scope.ip is not None:
                located.append(node)
                ips.add(scope.ip)
        if not located:
            return None
        return ReasoningSignal(
            name=self.name,
            description=(
                f"The failing scope resolves to DUT IP {', '.join(sorted(ips))} in the "
                "project model, localizing the failure to design logic."
            ),
            evidence_ids=sorted({n.id for n in located}),
            weights={HypothesisCategory.RTL_BUG: 0.10},
            confidence=0.7,
        )


def project_reasoning_rules(model: ProjectModel) -> list[ReasoningRule]:
    """The project-aware reasoning rules for one model, in deterministic order."""
    return [
        ProjectLifecycleRule(model),
        ProjectLogOriginRule(model),
        ProjectScopeRule(model),
    ]


def build_project_view(
    model: ProjectModel, graph: EvidenceGraph, report: AnalysisReport
) -> ProjectContext:
    """Assemble the report-facing ProjectContext for one run."""
    by_protocol: dict[str, list[str]] = {}
    for interface in model.dut.interfaces:
        if interface.protocol_id:
            by_protocol.setdefault(interface.protocol_id, []).append(interface.name)
    identified = [
        IdentifiedProtocol(
            protocol_id=pid, name=pid.upper(), interfaces=sorted(names), confidence=1.0
        )
        for pid, names in sorted(by_protocol.items())
    ]

    dut = DutTopologyView(
        top=model.dut.top,
        modules=[
            DutModuleView(
                name=m.name,
                parent=m.parent,
                ip=next((b.name for b in model.dut.ip_blocks if m.name in b.modules), None),
                source_file=m.source_file,
            )
            for m in model.dut.modules
        ],
        interfaces=[
            InterfaceView(
                name=i.name, protocol_id=i.protocol_id, signal_count=len(i.signals)
            )
            for i in model.dut.interfaces
        ],
        ip_blocks=[b.name for b in model.dut.ip_blocks],
        clocks=[c.name for c in model.dut.clocks],
        resets=[r.name for r in model.dut.resets],
    )

    components = [
        UvmComponentView(name=c.name, type=c.type, parent=c.parent, interface=c.interface)
        for c in model.env.components
    ]
    env = UvmTopologyView(
        components=components,
        agents=sum(1 for c in components if c.type == "agent"),
        monitors=sum(1 for c in components if c.type == "monitor"),
        scoreboards=sum(1 for c in components if c.type == "scoreboard"),
        predictors=sum(1 for c in components if c.type == "predictor"),
    )

    log_origins: dict[str, int] = {}
    for node in graph.failing():
        text = f"{node.description} {node.raw_line or ''}"
        origin = classify_origin(text, node.module, model.log_profile)
        log_origins[origin] = log_origins.get(origin, 0) + 1

    return ProjectContext(
        project_id=model.project_id,
        source_root=model.source_root,
        dut_top=model.dut.top,
        simulator=model.sim_infra.simulator_vendor,
        identified_protocols=identified,
        dut=dut,
        env=env,
        lifecycle=project_lifecycle(model, graph),
        log_origins=log_origins,
    )
