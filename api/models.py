from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, StrictBool, field_validator, model_validator

from config import get_settings

# Read once at import time (config.get_settings() is itself lru_cache'd) so
# these Field bounds are never a second hardcoded copy of
# docs/phase2/openapi.yaml's minLength/maxLength -- config.py is the single
# source of truth (Hard technical rule) and workspaces.py already reads the
# same settings for the non-API path.
_settings = get_settings()


class WorkspaceCreate(BaseModel):
    name: str = Field(
        min_length=_settings.workspace_name_min_length,
        max_length=_settings.workspace_name_max_length,
    )
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
        candidate = Path(value.strip()).expanduser()
        # Checked BEFORE `.resolve()`, which would otherwise silently turn a
        # relative path such as "." into the server's own working directory
        # -- accepted, but pointed at the wrong folder, and the contract
        # says `folder_path` is absolute (Workspace.folder_path
        # description: "Absolute path of the user-owned source folder").
        if not candidate.is_absolute():
            raise ValueError("folder_path must be an absolute path")
        path = candidate.resolve()
        if not path.is_dir():
            raise ValueError("folder_path must name an existing folder")
        return str(path)


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=_settings.workspace_name_min_length,
        max_length=_settings.workspace_name_max_length,
    )
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
    question: str = Field(
        min_length=_settings.question_min_length,
        max_length=_settings.question_max_length,
    )
    session_id: str | None = None

    @field_validator("question", mode="before")
    @classmethod
    def normalize_question(cls, value):
        return value.strip() if isinstance(value, str) else value
