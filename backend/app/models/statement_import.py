"""Public request contracts for statement ingestion settings."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class StatementImportSettingsUpdate(BaseModel):
    folder_enabled: bool = True
    folder_subdirectory: str = ""
    auto_commit: bool = True
    email_enabled: bool = False
    email_mailbox: str = "INBOX"
    email_allowed_senders: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("folder_subdirectory")
    @classmethod
    def validate_subdirectory(cls, value: str) -> str:
        clean = value.strip().strip("/")
        if ".." in clean.split("/"):
            raise ValueError("folder subdirectory cannot contain '..'")
        return clean

    @field_validator("email_mailbox")
    @classmethod
    def validate_mailbox(cls, value: str) -> str:
        clean = value.strip()
        if not clean or len(clean) > 120:
            raise ValueError("email mailbox is invalid")
        return clean

    @field_validator("email_allowed_senders")
    @classmethod
    def normalize_senders(cls, values: list[str]) -> list[str]:
        return sorted({value.strip().lower() for value in values if value.strip()})
