"""
Return type from Strategy.analyze().
Contains typed actions and the updated context state.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from app.core.actions import Action
from app.core.snapshots import ContextSnapshot


@dataclass(frozen=True)
class AnalysisResult:
    """
    Returned by analyze(). Strategy never mutates state directly.
    Runner reads .actions and applies them. Runner reads .new_context
    and stores it for the next analyze() call.
    """
    actions: List[Action]
    new_context: ContextSnapshot
