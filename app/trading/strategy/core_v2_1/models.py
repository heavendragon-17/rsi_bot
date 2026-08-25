"""Compatibility exports for the immutable Core V2.1 domain models."""

from .decision_models import (
    CoreDecision,
    CoreEvent,
    CoreState,
    CyclePhase,
    DecisionKind,
    EvaluationResult,
    EventType,
    PreferredEntryZone,
    ReasonCode,
    SignalMetrics,
    TradeLevels,
)
from .input_models import (
    AltH1Snapshot,
    BtcH1Snapshot,
    BtcH4Snapshot,
    EvaluationInput,
    M15Snapshot,
    M15TrendSnapshot,
)

# Keep repr/pickle identities compatible with the original single-module API.
for _model_type in (
    AltH1Snapshot,
    BtcH1Snapshot,
    BtcH4Snapshot,
    CoreDecision,
    CoreEvent,
    CoreState,
    CyclePhase,
    DecisionKind,
    EvaluationInput,
    EvaluationResult,
    EventType,
    M15Snapshot,
    M15TrendSnapshot,
    PreferredEntryZone,
    ReasonCode,
    SignalMetrics,
    TradeLevels,
):
    _model_type.__module__ = __name__
del _model_type

__all__ = [
    "AltH1Snapshot",
    "BtcH1Snapshot",
    "BtcH4Snapshot",
    "CoreDecision",
    "CoreEvent",
    "CoreState",
    "CyclePhase",
    "DecisionKind",
    "EvaluationInput",
    "EvaluationResult",
    "EventType",
    "M15Snapshot",
    "M15TrendSnapshot",
    "PreferredEntryZone",
    "ReasonCode",
    "SignalMetrics",
    "TradeLevels",
]
