import re
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator, ConfigDict
 
 
class RegisterRequest(BaseModel):
    nama:     str
    email:    EmailStr
    password: str
 
    @field_validator("nama")
    @classmethod
    def nama_valid(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 1 or len(v) > 150:
            raise ValueError("Nama harus antara 1–150 karakter")
        return v
 
    @field_validator("password")
    @classmethod
    def password_valid(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password minimal 8 karakter")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password harus mengandung minimal 1 huruf kapital")
        if not re.search(r"\d", v):
            raise ValueError("Password harus mengandung minimal 1 angka")
        return v
 
 
class LoginRequest(BaseModel):
    email:    EmailStr
    password: str
 
 
class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    role:         str
    user_id:      str
    nama:         str
 
 
class UserProfileResponse(BaseModel):
    """Response detail profil user yang sedang login."""
    id:         str
    nama:       str
    email:      str
    role:       str
    avatar_url: Optional[str] = None
    is_active:  bool
 
    model_config = ConfigDict(from_attributes=True)
