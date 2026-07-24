"""The project provider interface: the ONLY source-aware code in the platform.

A provider's whole and only job is to turn one kind of project source (a
canonical manifest, an RTL tree, a UVM topology dump, a build/filelist, a
regression config) into a normalized, partial
:class:`~veritriage.project.model.ProjectModel`. It may read source files and
shell out to tools, but under the lossy-by-design law it emits only normalized
structure: no source text, no ASTs, no raw tool payloads survive outside the
provider. Providers never touch the Evidence Graph, reasoning, or AI.

Add a new project source (RTL, UVM dump, Makefile/filelist, regression launcher,
internal tooling) by writing a new ``ProjectProvider`` subclass and registering
it. Nothing else in the platform changes; the architecture tests in
``tests/test_project.py`` prove it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import ClassVar


class ProjectProviderError(RuntimeError):
    """Raised when a provider cannot read the source it fronts."""


class ProjectCapability(str, Enum):
    """What a provider can resolve. Missing capabilities degrade honestly."""

    HIERARCHY = "hierarchy"
    INTERFACES = "interfaces"
    CLOCKS = "clocks"
    RESETS = "resets"
    ADDRESS_MAP = "address_map"
    REGISTER_MODEL = "register_model"
    UVM_TOPOLOGY = "uvm_topology"
    SIM_FLOW = "sim_flow"
    LIFECYCLE = "lifecycle"
    LOG_PROFILE = "log_profile"


class ProjectProvider(ABC):
    """Base class for every project source provider.

    Subclasses set :attr:`name`, :attr:`source`, and :attr:`capabilities`,
    implement :meth:`available` and :meth:`collect`, and register with
    ``@register_project_provider``.
    """

    #: Unique provider name (used in provenance and the ``project`` CLI table).
    name: ClassVar[str]

    #: Provenance tag stamped on the model this provider contributes, e.g. "manifest".
    source: ClassVar[str]

    #: What this provider can resolve.
    capabilities: ClassVar[frozenset[ProjectCapability]] = frozenset()

    @classmethod
    @abstractmethod
    def available(cls, root: Path) -> bool:
        """Whether this provider can produce a model for ``root``."""
        raise NotImplementedError

    @abstractmethod
    def collect(self, root: Path):
        """Read ``root`` and return a normalized, partial ProjectModel.

        Implementations must record their version in ``provider_versions`` and
        must not retain source text. Return an empty model rather than raising
        when the source is reachable but has nothing to report.
        """
        raise NotImplementedError
