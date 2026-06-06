from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any
import uuid

# Import model, schema, dan database
from app.models.review import Review
from app.schemas.review import ReviewCreate
from app.core.database import get_db
from app.core.security import get_current_user 
# Mengikuti tim kamu: menggunakan BaseResponse agar format response seragam
from app.schemas.base import BaseResponse

# DISAMAKAN: APIRouter kosongan tanpa prefix di sini
router = APIRouter()

@router.post(
    "",  # Kosong karena prefix "/reviews" akan dipasang di file v1/router.py
    response_model=BaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Menambahkan ulasan baru dari pengguna",
)
async def create_review(
    payload: ReviewCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user) # Mengunci API, wajib login
):
    """
    Menyimpan data ulasan (rating & komentar) dari user yang sedang login 
    terhadap suatu tempat wisata, kuliner, atau nongkrong.
    """
    try:
        # Ambil user_id dari objek row database user yang sedang session login
        user_id = current_user.id
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="User ID tidak ditemukan dalam data session login"
            )

        # Siapkan model SQLAlchemy untuk insert ke PostgreSQL
        new_review = Review(
            user_id=uuid.UUID(str(user_id)),
            tempat_id=uuid.UUID(payload.tempat_id),
            rating=payload.rating,
            comment=payload.comment
        )

        # Eksekusi simpan ke database
        db.add(new_review)
        await db.commit()
        await db.refresh(new_review)

        # Mengikuti tim kamu: Data dibungkus di dalam BaseResponse
        result_data = {
            "id": str(new_review.id),
            "tempat_id": str(new_review.tempat_id),
            "rating": new_review.rating,
            "comment": new_review.comment,
            "created_at": new_review.created_at.isoformat() if new_review.created_at else None
        }
        
        return BaseResponse(
            message="Ulasan berhasil ditambahkan",
            data=result_data
        )

    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=f"Format UUID tempat_id salah: {str(val_err)}")
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Gagal menyimpan ulasan: {str(e)}")