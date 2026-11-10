"""The signed-in user's profile."""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.auth import UserRead, UserUpdate
from app.services import auth as auth_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
def read_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.patch("/me")
def update_me(changes: UserUpdate, user: CurrentUser, db: DbSession) -> UserRead:
    return UserRead.model_validate(auth_service.update_profile(db, user, changes))
