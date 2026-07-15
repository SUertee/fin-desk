"""Usage contract shared by runtime records and costing models."""

from pydantic import BaseModel, ConfigDict, Field


class AgentRunUsage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    request_count: int = Field(default=0, ge=0)
    model_response_count: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
