"""The Learning Engine (M13): persistent adaptive intelligence above everything.

Every completed investigation improves the next one, without retraining
anything and without touching a deterministic conclusion path.

The law, pinned by tests: **learning is a pure function of recorded history.**
Given the same records and the same feedback, the artifacts are byte-identical.
No online drift, no training-order dependence, no hidden state, no vectors, no
models. Evidence stays immutable, Knowledge Packs stay curated, reasoning stays
deterministic, agents stay isolated. Learning sits above all of them and
remembers.

Importing this package registers the seven built-in learners.
"""

from veritriage.learning import learners  # noqa: F401  (registers the built-ins)
from veritriage.learning.calibration import (
    MAX_MULTIPLIER,
    MIN_MULTIPLIER,
    MIN_OBSERVATIONS,
    calibration_map,
    calibration_multiplier,
)
from veritriage.learning.corpus import Corpus
from veritriage.learning.engine import LearningEngine
from veritriage.learning.persistence import LearningStore
from veritriage.learning.registry import (
    Learner,
    available_learners,
    default_learners,
    get_learner,
    register_learner,
    unregister_learner,
)

__all__ = [
    "Corpus",
    "Learner",
    "LearningEngine",
    "LearningStore",
    "MAX_MULTIPLIER",
    "MIN_MULTIPLIER",
    "MIN_OBSERVATIONS",
    "available_learners",
    "calibration_map",
    "calibration_multiplier",
    "default_learners",
    "get_learner",
    "register_learner",
    "unregister_learner",
]
