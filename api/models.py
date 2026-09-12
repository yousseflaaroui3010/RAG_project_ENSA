from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, StrictBool, field_validator, model_validator


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    folder_path: str = Field(min_length=1)
    legal_flag: StrictBool = False

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("folder_path", mode="before")
    @classmethod
    def existing_folder(cls, value):
        if not isinstance(value, str):
            return value
        path = Path(value.strip()).expanduser().resolve()
        if not path.is_dir():
            raise ValueError("folder_path must name an existing folder")
        return str(path)


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    legal_flag: StrictBool | None = None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def at_least_one_value(self) -> WorkspaceUpdate:
        if "name" not in self.model_fields_set and "legal_flag" not in self.model_fields_set:
            raise ValueError("at least one property must be present")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("an update property may not be null")
        return self


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None

    @field_validator("question", mode="before")
    @classmethod
    def normalize_question(cls, value):
        return value.strip() if isinstance(value, str) else value
