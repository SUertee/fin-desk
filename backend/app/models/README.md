# models/

Pydantic models for all request/response payloads, organized by domain.

## Files

| File | Description |
|------|-------------|
| `user.py` | `UserProfile`, `AssetSnapshot`, `ProfileUpdateRequest` - user identity, assets, and profile update schema |
| `chat.py` | `ChatRequest`, `ChatResponse` - multi-agent chat payloads |
| `agent_data.py` | `FinanceAgentData`, `SummaryCard`, `AgentFinding`, `AgentAction`, `AgentAudit` - structured finance agent response data |
| `analysis.py` | `AnalyzeRequest`, `AnalyzeResponse` - transaction analysis pipeline payloads |
| `__init__.py` | Re-exports all models for `from app.models import X` |

## Usage

```python
# Direct import (preferred)
from app.models.user import UserProfile

# Package-level import (also works)
from app.models import UserProfile
```

## Conventions

- All models use Pydantic v2 `BaseModel`
- Optional fields use `Optional[T] = None`
- Lists default to `Field(default_factory=list)`
- Monetary values are `float` (AUD by default)
