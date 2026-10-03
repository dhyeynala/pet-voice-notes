"""The signed-in user and their pets.

- ``GET  /api/me``             -> ``{"uid", "name"}``
- ``GET  /api/me/pets``        -> ``[Pet]`` (only pets whose ``owners`` include the caller)
- ``POST /api/pets``           ``PetCreate`` -> ``Pet`` (201; id = uuid4, owners = [caller])
- ``GET  /api/pets/{pet_id}``  -> ``Pet`` (404 unless the caller owns it)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from petpulse.services import pets as pet_records
from petpulse.core.auth import current_user, require_pet_access
from petpulse.core.deps import get_store
from petpulse.schemas.pets import Pet, PetCreate, User
from petpulse.store.base import Store

router = APIRouter(tags=["pets"])


@router.get("/api/me", response_model=User)
def me(user: User = Depends(current_user)) -> User:
    return user


@router.get("/api/me/pets", response_model=list[Pet])
def my_pets(user: User = Depends(current_user), store: Store = Depends(get_store)) -> list[Pet]:
    return [pet_records.to_pet(pet) for pet in pet_records.list_pets(store, user.uid)]


@router.post("/api/pets", response_model=Pet, status_code=status.HTTP_201_CREATED)
def create_pet(body: PetCreate, user: User = Depends(current_user), store: Store = Depends(get_store)) -> Pet:
    return pet_records.to_pet(pet_records.create_pet(store, user.uid, body.model_dump()))


@router.get("/api/pets/{pet_id}", response_model=Pet)
def get_pet(pet: Pet = Depends(require_pet_access)) -> Pet:
    return pet
