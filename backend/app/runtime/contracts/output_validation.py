"""Contract validation helpers for agent harness outputs."""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.models.runtime import AgentOutputValidation


ModelT = TypeVar("ModelT", bound=BaseModel)


def _format_validation_error(error: dict[str, Any]) -> str:
    location = ".".join(str(part) for part in error.get("loc", ())) or "<root>"
    message = str(error.get("msg", "validation failed"))
    error_type = str(error.get("type", "value_error"))
    return f"{location}: {message} ({error_type})"


def validate_output_contract(
    *,
    agent: str,
    contract: str,
    model_type: type[ModelT],
    payload: Any,
) -> tuple[ModelT | None, AgentOutputValidation]:
    try:
        validated = model_type.model_validate(payload)
    except ValidationError as exc:
        return None, AgentOutputValidation(
            agent=agent,
            contract=contract,
            status="failed",
            errors=[
                _format_validation_error(error)
                for error in exc.errors(include_input=False, include_url=False)
            ],
        )

    return validated, AgentOutputValidation(
        agent=agent,
        contract=contract,
        status="passed",
    )
