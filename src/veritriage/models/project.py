"""Report and API views for the Verification Project Intelligence layer (M11).

These are *views*: the flattened, report-facing projection of a Project Model,
the same way ``models/knowledge.py`` holds views over the Knowledge Graph and
``models/engineering.py`` holds views over engineering context. The rich model
itself lives in ``veritriage.project.model``; this module stays import-light so
the models package never grows an upward dependency (it may import only its own
siblings, e.g. ``StateProgress`` for the lifecycle projection).

The Project Model never enters the Evidence Graph; it is a lens over it. A
``ProjectContext`` therefore carries structural understanding (topology,
identified protocols, expected lifecycle, log origins), not run evidence.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from veritriage.models.knowledge import StateProgress


class IdentifiedProtocol(BaseModel):
    """A protocol the DUT implements, identified via Knowledge Pack markers."""

    protocol_id: str = Field(description="Knowledge pack id, e.g. 'axi'.")
    name: str = Field(description="Human-readable protocol name.")
    interfaces: list[str] = Field(
        default_factory=list, description="DUT interfaces carrying this protocol."
    )
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="1.0 declared; lower when marker-inferred."
    )


class DutModuleView(BaseModel):
    """One design module, flattened for the report."""

    name: str
    parent: str | None = None
    ip: str | None = None
    source_file: str | None = None


class InterfaceView(BaseModel):
    """One DUT interface, flattened for the report."""

    name: str
    protocol_id: str | None = None
    signal_count: int = 0


class DutTopologyView(BaseModel):
    """The DUT's structural summary."""

    top: str | None = None
    modules: list[DutModuleView] = Field(default_factory=list)
    interfaces: list[InterfaceView] = Field(default_factory=list)
    ip_blocks: list[str] = Field(default_factory=list)
    clocks: list[str] = Field(default_factory=list)
    resets: list[str] = Field(default_factory=list)


class UvmComponentView(BaseModel):
    """One UVM component in the flattened topology."""

    name: str
    type: str = Field(description="agent/monitor/scoreboard/predictor/subscriber/env/test/...")
    parent: str | None = None
    interface: str | None = None


class UvmTopologyView(BaseModel):
    """The verification environment's structural summary."""

    components: list[UvmComponentView] = Field(default_factory=list)
    agents: int = 0
    monitors: int = 0
    scoreboards: int = 0
    predictors: int = 0


class LifecycleProjection(BaseModel):
    """The run projected onto the project's expected simulation lifecycle.

    Reuses ``StateProgress`` (phase = state) so the same rendering and
    projection logic the Knowledge Engine uses for protocol state machines
    applies to the whole-simulation lifecycle.
    """

    phases: list[StateProgress] = Field(default_factory=list)
    last_reached: str | None = Field(
        default=None, description="Deepest expected phase the evidence shows was reached."
    )
    stopped_at: str | None = Field(
        default=None, description="First expected phase the evidence never reached."
    )


class LogAnnotationView(BaseModel):
    """One log line classified by origin and lifecycle phase (log intelligence)."""

    line_number: int | None = None
    origin: str = Field(description="rtl/testbench/vip/simulator/infrastructure/boilerplate/...")
    phase: str | None = None
    snippet: str | None = None


class ResolvedScope(BaseModel):
    """A bare module string upgraded through the project model."""

    module: str
    ip: str | None = None
    interface: str | None = None
    protocol_id: str | None = None
    clock_domain: str | None = None
    owner: str | None = None

    @property
    def is_resolved(self) -> bool:
        return any((self.ip, self.interface, self.protocol_id, self.owner))


class ProjectSummary(BaseModel):
    """The bounded elevator answer to 'what is this project?'."""

    project_id: str
    source_root: str
    built_at: str
    dut_top: str | None = None
    simulator: str | None = None
    module_count: int = 0
    interface_count: int = 0
    identified_protocols: list[str] = Field(default_factory=list)
    uvm_component_count: int = 0
    lifecycle_phase_count: int = 0


class ProjectContext(BaseModel):
    """The Project Intelligence section embedded in an AnalysisReport.

    Structural understanding of the project the run belongs to, plus the
    run-specific lifecycle projection and log-origin breakdown that this
    understanding unlocks. Never contains raw source text.
    """

    project_id: str
    source_root: str
    dut_top: str | None = None
    simulator: str | None = None
    identified_protocols: list[IdentifiedProtocol] = Field(default_factory=list)
    dut: DutTopologyView = Field(default_factory=DutTopologyView)
    env: UvmTopologyView = Field(default_factory=UvmTopologyView)
    lifecycle: LifecycleProjection | None = None
    log_origins: dict[str, int] = Field(
        default_factory=dict, description="Failing-evidence count per classified origin."
    )
    notes: list[str] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (
            self.identified_protocols
            or self.dut.modules
            or self.env.components
            or self.lifecycle
        )
