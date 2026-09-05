"""Typed state and host callbacks shared by the controller support classes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .contracts import PipelineConfig, Provider, ProviderError
from .storage import PipelineStore


class ControllerContext(ABC):
    """Declare the concrete host dependencies without initializing resources.

    PipelineController owns these fields and supplies the host callbacks;
    ProviderRuntime implements the durable provider operations. Sharing one
    base keeps the mixins' requirements checked through their combined MRO.
    """

    config: PipelineConfig
    repo_root: Path
    output_dir: Path
    store: PipelineStore

    @abstractmethod
    def _provider(self, role: str) -> Provider:
        raise NotImplementedError

    @abstractmethod
    def _as_provider_error(self, caught: Exception) -> ProviderError:
        raise NotImplementedError

    @abstractmethod
    def _validate_execution_plan_for_proposal(
        self, plan: dict[str, Any], proposal: dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def _provider_call(
        self,
        campaign_id: str,
        job_id: str,
        *,
        role: str,
        phase: str,
        prompt: str,
        schema: dict[str, Any],
        metadata: dict[str, Any],
        validator: Callable[[Any], dict[str, Any]],
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def _completed_response(
        self, campaign_id: str, job_id: str, phase: str,
        validator: Callable[[Any], dict[str, Any]],
    ) -> dict[str, Any] | None:
        raise NotImplementedError
