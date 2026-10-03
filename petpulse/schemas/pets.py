"""Users and pets: request bodies (``extra="forbid"``, bounded) and API response models."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

AnimalType = Literal["dog", "cat", "bird", "rabbit", "hamster", "guinea-pig", "fish", "reptile", "other"]
Gender = Literal["male", "female", "male-neutered", "female-spayed"]


class User(BaseModel):
    """The signed-in user, as returned by ``GET /api/me``."""

    model_config = ConfigDict(frozen=True)

    uid: str
    name: str


class PetCreate(BaseModel):
    """Body of ``POST /api/pets``. Field names match the add-pet form in the UI."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=60)
    animal_type: AnimalType
    breed: str = Field(default="", max_length=80)
    age: Optional[int] = Field(default=None, ge=0, le=40)
    weight: Optional[float] = Field(default=None, ge=0, le=500, allow_inf_nan=False)
    gender: Optional[Gender] = None

    @field_validator("gender", mode="before")
    @classmethod
    def _blank_gender_is_none(cls, value: Any) -> Any:
        # The UI's "Select gender" option submits "".
        if isinstance(value, str) and not value.strip():
            return None
        return value


class Pet(BaseModel):
    """A pet as returned by the API. Stored at ``pets/{id}`` with the same fields (minus ``id``)."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    animal_type: str
    breed: str = ""
    age: Optional[int] = None
    weight: Optional[float] = None
    gender: Optional[str] = None
    owners: list[str]
    created_at: str


class DemoUser(BaseModel):
    uid: str
    name: str


class DemoLogin(BaseModel):
    """Body of ``POST /api/demo/login``: an existing demo ``uid``, or a ``name`` for a new user."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    uid: Optional[str] = Field(default=None, min_length=1, max_length=64)
    name: Optional[str] = Field(default=None, min_length=1, max_length=40)


class LoginResponse(BaseModel):
    token: str
    user: User
