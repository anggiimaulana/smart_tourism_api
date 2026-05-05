import uuid

# app/api/v1/endpoints/auth.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, get_current_user
from app.schemas.base import BaseResponse
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UserProfileResponse

router = APIRouter()


@router.post(
    "/register",
    response_model=BaseResponse,
    status_code=201,
    summary="Registrasi user baru (role: pengunjung)",
)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Endpoint publik — tidak butuh token.
    Role default: pengunjung.
    Admin hanya bisa dibuat manual di DB atau via seed.
    """
    exists = await db.execute(
        text("SELECT 1 FROM users WHERE email = :email"),
        {"email": payload.email},
    )
    if exists.fetchone():
        raise HTTPException(status_code=409, detail="Email sudah terdaftar")

    await db.execute(
        text("""
            INSERT INTO users (id, nama, email, password_hash, role, is_active)
            VALUES (:id, :nama, :email, :password_hash, 'pengunjung', true)
        """),
        {
            "id": str(uuid.uuid4()),
            "nama": payload.nama.strip(),
            "email": payload.email,
            "password_hash": hash_password(payload.password),
        },
    )
    await db.commit()
    return BaseResponse(message="Registrasi berhasil")


@router.post(
    "/login",
    response_model=BaseResponse,
    summary="Login → dapatkan JWT access token",
)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Return access_token yang digunakan di header Authorization: Bearer <token>.
    """
    row = await db.execute(
        text("""
            SELECT id, nama, email, password_hash, role, is_active
            FROM users
            WHERE email = :email
        """),
        {"email": payload.email},
    )
    user = row.fetchone()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email atau password salah")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Akun tidak aktif")

    token = create_access_token({"sub": str(user.id), "role": user.role})
    return BaseResponse(data=TokenResponse(
        access_token=token,
        role=user.role,
        user_id=str(user.id),
        nama=user.nama,
    ))


@router.get(
    "/me",
    response_model=BaseResponse,
    summary="Profil user yang sedang login",
)
async def me(current_user=Depends(get_current_user)):
    """
    Membutuhkan header: Authorization: Bearer <token>
    """
    return BaseResponse(data=UserProfileResponse(
        id=str(current_user.id),
        nama=current_user.nama,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
    ))
