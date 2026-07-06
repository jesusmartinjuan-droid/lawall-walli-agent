"""Authentication: password verification and JWT issuance/lookup."""

from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.models.user import User
from app.repositories.user_repository import UserRepository


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)

    def authenticate(self, email: str, password: str) -> User | None:
        user = self.users.get_by_email(email.lower())
        if not user or not user.is_active:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    def issue_token_for(self, user: User) -> str:
        return create_access_token(subject=str(user.id), extra_claims={"role": user.role.value})

    def get_user_by_id(self, user_id: int) -> User | None:
        return self.users.get(user_id)
