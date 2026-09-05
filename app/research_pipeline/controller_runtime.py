"""Durable provider invocation and completed-response recovery."""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from functools import partial
from typing import Any

from .contracts import (
    BudgetExceededError,
    ContractError,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    canonical_json,
)
from .controller_context import ControllerContext
from .controller_utils import _estimate_tokens, _id
from .inputs import validate_inputs


class ProviderRuntime(ControllerContext):
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
        # Revalidate at the shared dispatch boundary, including resumed review
        # calls, before constructing a provider or consuming its reservation.
        validate_inputs(self.store.context(campaign_id), self.repo_root,
                        self.output_dir / campaign_id, adaptive=self.config.adaptive)
        provider_name = self.config.thinker_provider if role == "thinker" else self.config.executor_provider
        model = self.config.thinker_model if role == "thinker" else self.config.executor_model
        if provider_name == "opencode" and self.config.opencode_output_mode == "json_text":
            prompt += ("\nReturn one JSON object matching the required schema. Do not use tools, Markdown fences, or explanatory text. "
                       "The controller validates the complete object before accepting it.\nRequired JSON schema:\n"
                       + canonical_json(schema))
        provider = self._provider(role)
        input_tokens_estimate = _estimate_tokens(prompt)
        if input_tokens_estimate > self.config.context_budget:
            raise ProviderError(
                "provider request exceeds the controller context budget",
                kind="context_budget_exceeded",
                details={"requested": self.config.context_budget, "estimated": input_tokens_estimate, "provider_call_performed": False},
            )
        try:
            self.store.reserve_call(campaign_id, role)
        except RuntimeError as exc:
            budget_error = BudgetExceededError(role)
            budget_error.job_id = job_id
            self.store.set_campaign_status(campaign_id, "BUDGET_EXHAUSTED")
            raise budget_error from exc
        attempt_id = _id("attempt")
        schema_dir = self.output_dir / campaign_id / "schemas"
        schema_dir.mkdir(parents=True, exist_ok=True)
        schema_path = schema_dir / f"{phase}.json"
        schema_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        controller_limits = {
            "context_budget": {"requested": self.config.context_budget, "enforced": "prompt_utf8_estimate", "estimated_input_tokens": input_tokens_estimate},
            "output_budget": {"requested": self.config.output_budget, "enforced": "response_utf8_estimate"},
        }
        request = ProviderRequest(
            role=role,
            phase=phase,
            prompt=prompt,
            schema=schema,
            model=model,
            effort=self.config.thinker_effort if role == "thinker" else self.config.executor_effort,
            timeout_seconds=self.config.timeout_seconds,
            context_budget=self.config.context_budget,
            output_budget=self.config.output_budget,
            metadata={**metadata, "schema_path": str(schema_path), "controller_limits": controller_limits,
                      "opencode_output_mode": self.config.opencode_output_mode,
                      "persist_provider_session": partial(self.store.persist_provider_session, attempt_id)},
        )
        self.store.create_attempt(
            attempt_id,
            campaign_id,
            job_id,
            role,
            phase,
            provider_name,
            model,
            {
                "phase": phase,
                "role": role,
                "provider": provider_name,
                "model": model,
                "effort": request.effort,
                "context_budget": request.context_budget,
                "output_budget": request.output_budget,
                "opencode_output_mode": self.config.opencode_output_mode,
                "controller_limits": controller_limits,
            },
        )
        response: ProviderResponse | None = None
        provider_invoked = False
        try:
            provider_invoked = True
            response = provider.complete(request)
            if not isinstance(response, ProviderResponse):
                raise ProviderError("provider returned an invalid response object", kind="provider_contract")
            output_tokens_estimate = _estimate_tokens(canonical_json(response.payload))
            if output_tokens_estimate > self.config.output_budget:
                raise ProviderError(
                    "provider response exceeds the controller output budget",
                    kind="output_budget_exceeded",
                    details={"requested": self.config.output_budget, "estimated": output_tokens_estimate, "provider_call_performed": True},
                )
            payload = validator(response.payload)
        except (ProviderError, ContractError, TypeError, ValueError, OSError) as caught:
            if isinstance(caught, ProviderError):
                error = caught
            elif isinstance(caught, ContractError):
                error = ProviderError(str(caught), kind="malformed_json", details={"provider_call_performed": provider_invoked})
            else:
                error = self._as_provider_error(caught)
                error.details["provider_call_performed"] = provider_invoked
            error.attempt_id = attempt_id
            error.job_id = job_id
            error.details.setdefault("provider_call_performed", provider_invoked)
            usage = self._usage_record(request, response) if response is not None else None
            rejected_payload = None
            if isinstance(response, ProviderResponse) and isinstance(response.payload, Mapping):
                try:
                    if _estimate_tokens(canonical_json(response.payload)) <= self.config.output_budget:
                        rejected_payload = dict(response.payload)
                except (TypeError, ValueError):
                    pass
            self.store.finish_attempt(attempt_id, status="PAUSED" if error.kind == "interrupted_uncertain" else "FAILED", response=rejected_payload, usage=usage, error_kind=error.kind, error_message=str(error))
            self.store.set_campaign_status(campaign_id, "PAUSED" if error.retryable else "FAILED")
            raise error from caught
        usage = self._usage_record(request, response)
        self.store.finish_attempt(attempt_id, status="COMPLETED", response=payload, usage=usage)
        return payload

    @staticmethod
    def _usage_record(request: ProviderRequest, response: ProviderResponse | None) -> dict[str, Any]:
        if response is None:
            return {"provider": None, "requested_model": request.model, "reported_model": None, "provider_usage": None, "controls": {}, "controller_limits": request.metadata.get("controller_limits", {})}
        return {
            "provider": response.provider,
            "requested_model": request.model,
            "reported_model": response.reported_model,
            "provider_usage": response.usage,
            "controls": response.controls or {},
            "controller_limits": request.metadata.get("controller_limits", {}),
        }

    def _completed_response(self, campaign_id: str, job_id: str, phase: str, validator: Callable[[Any], dict[str, Any]]) -> dict[str, Any] | None:
        attempt = self.store.completed_attempt(campaign_id, job_id, phase)
        if attempt is None:
            return None
        try:
            raw = json.loads(attempt["response_json"])
            return validator(raw)
        except (json.JSONDecodeError, ContractError, ValueError) as exc:
            error = ProviderError("durable completed provider response is no longer contract-valid", kind="recovery_contract", details={"attempt_id": attempt["id"], "provider_call_performed": True})
            error.attempt_id = attempt["id"]
            error.job_id = job_id
            raise error from exc

