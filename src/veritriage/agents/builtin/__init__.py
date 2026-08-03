"""The built-in agent library.

Importing this package registers every built-in specialist. Each module is
self-contained and reaches the Coordinator through ``@register_agent`` alone:
adding a ninth agent means adding a module here (or anywhere else) and nothing
more, which ``test_new_agent_needs_only_registration`` proves executably.
"""

from veritriage.agents.builtin.coverage import CoverageAgent
from veritriage.agents.builtin.formal import FormalAgent
from veritriage.agents.builtin.knowledge import KnowledgeAgent
from veritriage.agents.builtin.project import ProjectIntelligenceAgent
from veritriage.agents.builtin.protocol import ProtocolAgent
from veritriage.agents.builtin.regression import RegressionAgent
from veritriage.agents.builtin.rtl import RtlAgent
from veritriage.agents.builtin.testbench import TestbenchAgent

__all__ = [
    "CoverageAgent",
    "FormalAgent",
    "KnowledgeAgent",
    "ProjectIntelligenceAgent",
    "ProtocolAgent",
    "RegressionAgent",
    "RtlAgent",
    "TestbenchAgent",
]
