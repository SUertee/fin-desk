"""Small in-memory task snapshot store for the agent gateway MVP."""

from __future__ import annotations

from app.gateways.agent_gateway.task_contracts import AgentTaskResponse


class AgentTaskStore:
    """Stores recent task responses until a durable task ledger is added."""

    def __init__(self) -> None:
        self._tasks: dict[str, AgentTaskResponse] = {}

    def save(self, response: AgentTaskResponse) -> AgentTaskResponse:
        self._tasks[response.task_id] = response
        return response

    def get(self, task_id: str) -> AgentTaskResponse | None:
        return self._tasks.get(task_id)
