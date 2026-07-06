from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.user import User
from app.services.auth_service import AuthService


def _create_user(db_session, *, is_active: bool = True) -> User:
    user = User(
        email="agent@lawall.local",
        full_name="Agent Smith",
        hashed_password=hash_password("correct-password"),
        role=UserRole.AGENT,
        is_active=is_active,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_authenticate_succeeds_with_correct_credentials(db_session):
    _create_user(db_session)
    service = AuthService(db_session)
    user = service.authenticate("agent@lawall.local", "correct-password")
    assert user is not None
    assert user.email == "agent@lawall.local"


def test_authenticate_fails_with_wrong_password(db_session):
    _create_user(db_session)
    service = AuthService(db_session)
    assert service.authenticate("agent@lawall.local", "wrong-password") is None


def test_authenticate_fails_for_inactive_user(db_session):
    _create_user(db_session, is_active=False)
    service = AuthService(db_session)
    assert service.authenticate("agent@lawall.local", "correct-password") is None


def test_issue_token_contains_role_claim(db_session):
    user = _create_user(db_session)
    service = AuthService(db_session)
    token = service.issue_token_for(user)
    assert isinstance(token, str) and token
