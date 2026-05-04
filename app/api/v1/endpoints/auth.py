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
    # TODO: panggil AuthService.register(payload, db)
    raise HTTPException(status_code=501, detail="Implementasi di AuthService")


@router.post(
    "/login",
    response_model=BaseResponse,
    summary="Login → dapatkan JWT access token",
)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Return access_token yang digunakan di header Authorization: Bearer <token>.
    """
    # TODO: panggil AuthService.login(payload, db)
    raise HTTPException(status_code=501, detail="Implementasi di AuthService")


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