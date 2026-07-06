"""Minimal read-only user listing, reserved for future user-management screens."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import CurrentUserResponse

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[CurrentUserResponse])
def list_users(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> list[User]:
    return UserRepository(db).list(limit=500)
