# app/core/security.py
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db

# ── Bearer scheme ─────────────────────────────────────────────
# auto_error=False agar endpoint opsional-auth tidak langsung 401
bearer_scheme = HTTPBearer(auto_error=False)


# ── Password ──────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Hash password menggunakan bcrypt. Simpan hasil ini ke DB."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Bandingkan password plain dengan hash yang tersimpan di DB."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── JWT ───────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Buat JWT access token.

    Parameter data minimal harus berisi:
        {"sub": str(user.id), "role": user.role}
    """
    to_encode = data.copy()
    expire    = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


# ── Internal helper ───────────────────────────────────────────

async def _resolve_user(
    credentials: Optional[HTTPAuthorizationCredentials],
    db: AsyncSession,
    required: bool,
):
    """
    Decode JWT → ambil user dari DB.
    Jika required=False dan token tidak ada/invalid → return None.
    """
    if not credentials:
        if required:
            raise HTTPException(status_code=401, detail="Token tidak ditemukan")
        return None

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        user_id: str = payload.get("sub")
        if not user_id:
            raise JWTError("sub missing")
    except JWTError:
        if required:
            raise HTTPException(status_code=401, detail="Token tidak valid atau sudah kadaluarsa")
        return None

    row = await db.execute(
        text("SELECT id, nama, email, role, is_active FROM users WHERE id = :id"),
        {"id": user_id},
    )
    user = row.fetchone()

    if not user:
        if required:
            raise HTTPException(status_code=401, detail="User tidak ditemukan")
        return None

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Akun tidak aktif")

    return user


# ── Public Dependencies ───────────────────────────────────────

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """
    Dependency untuk endpoint yang WAJIB login.

    Penggunaan:
        async def endpoint(current_user = Depends(get_current_user)):
            print(current_user.role)
    """
    return await _resolve_user(credentials, db, required=True)


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """
    Dependency untuk endpoint yang bisa diakses dengan atau tanpa login.
    Return None jika tidak ada token / token invalid.
    """
    return await _resolve_user(credentials, db, required=False)


async def require_admin(
    current_user=Depends(get_current_user),
):
    """
    Dependency untuk endpoint khusus admin.

    Penggunaan:
        @router.post("/", dependencies=[Depends(require_admin)])
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Hanya admin yang dapat mengakses endpoint ini",
        )
    return current_user