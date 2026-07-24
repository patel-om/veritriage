"""UVM Register Abstraction Layer (RAL) Knowledge Pack.

The register model: a mirror of expected register state, prediction from bus
activity, and per-field access policies (RW/RO/W1C/...). The failures are a
mirror that diverges from the DUT and an access policy the RTL does not honor.
"""

from __future__ import annotations

from veritriage.knowledge.model import (
    Concept,
    DebugPlaybook,
    EvidenceClause,
    FailurePattern,
    KnowledgePack,
    PlaybookStep,
    Reference,
)
from veritriage.knowledge.registry import register_pack

_SPEC = "UVM (IEEE 1800.2) Register Abstraction Layer"


@register_pack
def uvm_ral_pack() -> KnowledgePack:
    return KnowledgePack(
        id="uvm-ral",
        name="UVM RAL",
        version="1.0.0",
        domain="methodology",
        summary="Register model mirror/prediction and field access-policy checking.",
        concepts=[
            Concept(
                id="uvm-ral.mirror",
                name="Mirror and prediction",
                summary=(
                    "The register model keeps a mirrored value (what it believes the "
                    "DUT holds) and a desired value; a predictor updates the mirror "
                    "from observed bus activity. If prediction is wrong or a backdoor "
                    "write bypasses it, the mirror diverges and every check against it "
                    "is unreliable."
                ),
                markers=[r"\bral\b|register model", r"mirror|predict", r"desired value|mirrored value"],
                references=[Reference(source=_SPEC, section="RAL", note="Mirror/desired and prediction.")],
            ),
            Concept(
                id="uvm-ral.policy",
                name="Field access policies",
                summary=(
                    "Each field has an access policy (RW, RO, W1C, WO, RC, ...) that "
                    "defines how it responds to reads and writes. The DUT must "
                    "implement the same policy the model assumes; a mismatch (a RO "
                    "field that writes, a W1C that does not clear) is a real bug."
                ),
                markers=[r"access policy|field policy", r"\bw1c\b|\brw\b|\bro\b|\bwo\b|\brc\b", r"read-only|write-one-to-clear"],
                references=[Reference(source=_SPEC, section="RAL", note="Field access-type semantics.")],
            ),
        ],
        patterns=[
            FailurePattern(
                id="uvm-ral.mirror-mismatch",
                name="RAL mirror diverges from DUT",
                summary=(
                    "The register model's mirrored value no longer matches the DUT: "
                    "prediction failed or a write bypassed the predictor, so "
                    "model-based checks are comparing against a stale expectation."
                ),
                required=[
                    EvidenceClause(
                        name="mirror mismatch",
                        pattern=r"ral.*(?:mirror|predict).*mismatch|register (?:mirror|model).*(?:mismatch|diverg)|mirrored value.*(?:differs|mismatch).*dut",
                        must_fail=True,
                    ),
                ],
                optional_=[
                    EvidenceClause(name="ral context", pattern=r"\bral\b|register model|mirror"),
                ],
                typical_causes=[
                    "Explicit prediction disabled while the sequence writes via a different agent",
                    "Backdoor write not reflected into the mirror",
                    "Field access policy in the model disagrees with the DUT's update rule",
                ],
                ownership="testbench",
                suggested_signals=["mirrored value", "DUT register value", "predictor"],
                playbook_id="uvm-ral.mirror-debug",
                confidence_modifiers={"testbench_issue": 0.12},
                references=[Reference(source=_SPEC, section="RAL", note="Prediction keeps the mirror coherent.")],
            ),
            FailurePattern(
                id="uvm-ral.access-policy-violation",
                name="Field access policy not honored",
                summary=(
                    "A register field did not behave per its access policy: a "
                    "read-only field changed on a write, or a write-one-to-clear "
                    "field did not clear, so hardware and model disagree."
                ),
                required=[
                    EvidenceClause(
                        name="policy violated",
                        pattern=r"(?:access policy|field policy).*(?:violat|not honored)|w1c.*(?:not clear|did not clear)|read-only (?:field|register).*(?:written|modified|changed)",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "RTL update logic for the field does not implement the specified policy",
                    "Model configured with the wrong access type for the field",
                    "Side-effect (clear-on-read, W1C) implemented on the wrong event",
                ],
                ownership="design",
                suggested_signals=["field write enable", "field value", "access-type config"],
                playbook_id="uvm-ral.policy-debug",
                confidence_modifiers={"rtl_bug": 0.10, "testbench_issue": 0.04},
                references=[Reference(source=_SPEC, section="RAL", note="Access-type behavior contract.")],
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="uvm-ral.mirror-debug",
                name="RAL mirror debug",
                steps=[
                    PlaybookStep(action="Compare the mirrored value to a backdoor read of the DUT register", signals=["mirrored value", "DUT register value"]),
                    PlaybookStep(action="Confirm the predictor sees every path that writes the register", signals=["predictor"]),
                    PlaybookStep(action="Check whether a backdoor or secondary-agent write bypassed prediction"),
                    PlaybookStep(action="Verify the model's field access types match the DUT"),
                ],
            ),
            DebugPlaybook(
                id="uvm-ral.policy-debug",
                name="RAL access-policy debug",
                steps=[
                    PlaybookStep(action="Identify the field and its declared access policy"),
                    PlaybookStep(action="Drive the policy's defining access and observe the field", signals=["field value", "field write enable"]),
                    PlaybookStep(action="Compare the RTL update rule to the policy semantics"),
                    PlaybookStep(action="Confirm the model's access-type config matches", signals=["access-type config"]),
                ],
            ),
        ],
        references=[Reference(source=_SPEC, note="Primary reference for UVM RAL.")],
    )
