from pydantic import BaseModel

from app.models.enums import UserRole

# Plain `str` rather than pydantic's EmailStr: EmailStr's underlying
# email-validator library rejects RFC 6761 special-use domains (e.g. the
# internal ".local" convention used for admin@lawall.local), which is too
# strict for an internal tool.


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool

    model_config = {"from_attributes": True}
